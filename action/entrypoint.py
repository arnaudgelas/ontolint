"""The steps of the ontolint GitHub Action (``action.yml``): install the pinned release, run it.

    python action/entrypoint.py install   # ontolint == the version of this checkout, from the package index
    python action/entrypoint.py run       # one Markdown report for the step summary, one SARIF report

``action.yml`` runs both with the Python of a fresh virtual environment, after it has installed the
dependencies from ``action/requirements.txt`` by hash.  Every input reaches this script as an environment
variable (``INPUT_FILES``, ``INPUT_ARGS``, ``INPUT_FAIL_ON``, ``INPUT_SARIF_FILE``, ``INPUT_SUMMARY``), never
inside a shell command, and is checked before anything runs.

What the Action refuses to do, because it runs in the caller's CI:

* install anything but the one version in the ``pyproject.toml`` of the commit the caller pinned;
* hand ontolint the caller's secrets: the child process gets an allow-list of environment variables;
* let ontolint's output become a workflow command: every run is wrapped in ``::stop-commands::``, with a token
  drawn for that run, and stderr is merged into stdout so the runner sees one ordered stream;
* write the SARIF report outside the workspace.

The standard library only, apart from ``ontolint.github``, which escapes the annotations this script prints.
"""

from __future__ import annotations

import os
import re
import secrets
import subprocess
import sys
import tempfile
import tomllib
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

INDEX = "https://pypi.org/simple"  # never the caller's UV_INDEX_URL or PIP_INDEX_URL
RELEASE = re.compile(r"\d+\.\d+\.\d+")
FAIL_ON = ("error", "warning", "info", "never")
# Options that would change what the Action writes or stop ontolint from writing a report.  argparse accepts any
# unambiguous prefix of a long option, so a token is refused when it is a prefix of one of these.
OWNED_OPTIONS = ("--format", "--output", "--measurements", "--list-rules", "--explain", "--version", "--help")
CHILD_ENVIRONMENT = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT")


class InputError(Exception):
    """An input or the checkout is not what the Action accepts; the message says what to change."""


@dataclass(frozen=True)
class Settings:
    files: list[str]
    extra: list[str]
    fail_on: str
    sarif_file: Path
    summary: bool
    step_summary: Path | None
    github_output: Path | None
    runner_temp: Path | None


def _escape_data(text: str) -> str:
    """Escape ``text`` for a workflow command; before ontolint is installed, keep only harmless characters."""
    try:
        from ontolint.github import escape_data  # noqa: PLC0415 -- not installed while the Action installs it.
    except ImportError:
        return re.sub(r"[^A-Za-z0-9 ._=/'-]", "?", text)
    return escape_data(text)


def pinned_version(root: Path) -> str:
    """The version in ``root/pyproject.toml``; the Action installs exactly this release and nothing newer."""
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    if not isinstance(version, str) or not RELEASE.fullmatch(version):
        raise InputError(f"pyproject.toml has version {version!r}; the Action installs only an exact release version")
    return version


def install_command(uv: str, python: str, version: str) -> list[str]:
    """Install ``ontolint==version`` into the environment of ``python``; its dependencies are already there."""
    return [
        *(uv, "pip", "install", "--python", python, "--default-index", INDEX),
        *("--no-deps", "--only-binary", ":all:", f"ontolint=={version}"),
    ]


def _lines(name: str, value: str) -> list[str]:
    """One entry per non-blank line; control characters other than the line break are refused."""
    for char in value:
        if char not in "\r\n" and unicodedata.category(char) == "Cc":
            raise InputError(f"{name}: control character {char!r} in the value")
    return [line.strip() for line in value.splitlines() if line.strip()]


def _extra_arguments(value: str) -> list[str]:
    arguments = _lines("args", value)
    for argument in arguments:
        option = argument.split("=", 1)[0]
        if argument.startswith("--") and len(option) > len("--") and any(f.startswith(option) for f in OWNED_OPTIONS):
            raise InputError(f"args: {argument!r} is not allowed, the Action chooses the report format and file")
    return arguments


def _report_path(value: str, workspace: Path) -> Path:
    lines = _lines("sarif-file", value)
    if len(lines) != 1:
        raise InputError("sarif-file: give exactly one path")
    path = (workspace / lines[0]).resolve()
    if path == workspace or not path.is_relative_to(workspace):
        raise InputError(f"sarif-file: {lines[0]!r} is outside the workspace")
    return path


def read_settings(env: Mapping[str, str]) -> Settings:
    """Check every input; raise ``InputError`` for the first that is wrong."""
    workspace = Path(env.get("GITHUB_WORKSPACE") or Path.cwd()).resolve()
    files = _lines("files", env.get("INPUT_FILES", ""))
    if not files:
        raise InputError("files: name at least one file or directory, one per line")
    for name in files:
        if name.startswith("-"):
            raise InputError(f"files: {name!r} starts with '-' and would be read as an option")
    fail_on = env.get("INPUT_FAIL_ON", "").strip()
    if fail_on and fail_on not in FAIL_ON:
        raise InputError(f"fail-on: {fail_on!r} is not one of {', '.join(FAIL_ON)}")
    summary = env.get("INPUT_SUMMARY", "true").strip()
    if summary not in ("true", "false"):
        raise InputError(f"summary: {summary!r} is not 'true' or 'false'")
    step_summary, github_output = env.get("GITHUB_STEP_SUMMARY"), env.get("GITHUB_OUTPUT")
    return Settings(
        files=files,
        extra=_extra_arguments(env.get("INPUT_ARGS", "")),
        fail_on=fail_on,
        sarif_file=_report_path(env.get("INPUT_SARIF_FILE", ""), workspace),
        summary=summary == "true",
        step_summary=Path(step_summary) if step_summary else None,
        github_output=Path(github_output) if github_output else None,
        runner_temp=Path(env["RUNNER_TEMP"]) if env.get("RUNNER_TEMP") else None,
    )


def report_command(command: Sequence[str], settings: Settings, fmt: str, output: Path) -> list[str]:
    """The ontolint invocation that writes one report; the order is the inputs, then what the Action decides."""
    fail_on = ["--fail-on", settings.fail_on] if settings.fail_on else []
    return [*command, *settings.files, *settings.extra, *fail_on, "--format", fmt, "--output", str(output)]


def child_environment(env: Mapping[str, str]) -> dict[str, str]:
    """The environment ontolint runs in: the few variables a process needs, none of the caller's secrets."""
    kept = {name: env[name] for name in CHILD_ENVIRONMENT if name in env}
    return {**kept, "PYTHONUTF8": "1"}


def _run_wrapped(argv: Sequence[str], env: Mapping[str, str]) -> int:
    """Run one report with workflow commands switched off, so nothing it prints can be read as one."""
    token = secrets.token_hex(16)
    print(f"::stop-commands::{token}", flush=True)
    try:
        return subprocess.run(  # noqa: S603 -- argv is the interpreter, the module and checked inputs.
            argv, env=child_environment(env), stderr=subprocess.STDOUT, check=False
        ).returncode
    finally:
        print(f"::{token}::", flush=True)


def _append(path: Path, data: bytes) -> None:
    with path.open("ab") as handle:
        handle.write(data if data.endswith(b"\n") else data + b"\n")


def run(settings: Settings, command: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    """Write the Markdown summary and the SARIF report; return the exit status ontolint gave (the worst of them)."""
    command = command or [sys.executable, "-m", "ontolint"]
    env = os.environ if env is None else env
    settings.sarif_file.parent.mkdir(parents=True, exist_ok=True)
    codes = []
    markdown = None
    if settings.summary:
        # A private directory (mode 0700) that the runner removes with its temporary directory at the job's end.
        markdown = Path(tempfile.mkdtemp(prefix="ontolint-action-", dir=settings.runner_temp)) / "summary.md"
        codes.append(_run_wrapped(report_command(command, settings, "markdown", markdown), env))
        if settings.step_summary is None:
            print("GITHUB_STEP_SUMMARY is not set; the Markdown summary was not appended.")
        elif markdown.exists():
            _append(settings.step_summary, markdown.read_bytes())
    codes.append(_run_wrapped(report_command(command, settings, "sarif", settings.sarif_file), env))
    code = max(codes)
    if settings.github_output is not None:
        kept = markdown if markdown is not None and markdown.exists() else ""
        outputs = {"exit-code": code, "sarif-file": settings.sarif_file, "summary-file": kept}
        _append(settings.github_output, "".join(f"{name}={value}\n" for name, value in outputs.items()).encode())
    return code


def _run(argv: Sequence[str]) -> int:
    return subprocess.run(list(argv), check=False).returncode  # noqa: S603 -- a fixed argv.


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in ("install", "run"):
        print("usage: entrypoint.py {install|run}", file=sys.stderr)
        raise SystemExit(2)
    try:
        if args[0] == "install":
            root = Path(os.environ.get("ONTOLINT_ACTION_ROOT") or Path(__file__).resolve().parent.parent)
            return _run(install_command("uv", sys.executable, pinned_version(root)))
        return run(read_settings(os.environ))
    except InputError as exc:
        print(f"::error::{_escape_data(f'ontolint action: {exc}')}", flush=True)
        return 2


if __name__ == "__main__":
    sys.exit(main())
