"""The GitHub Action (``action.yml`` and ``action/entrypoint.py``): its inputs, its run, its pins.

The Action runs in other people's CI, so these tests pin what it must never do: install anything but one
hashed, exact version, interpolate an input into a shell, let ontolint's output become a workflow command,
hand the child process the caller's secrets, or write outside the workspace.
"""

# ruff: noqa: PLR2004

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from ontolint import main

ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
SCRIPT = ROOT / "action" / "entrypoint.py"
spec = importlib.util.spec_from_file_location("entrypoint", SCRIPT)
assert spec is not None
assert spec.loader is not None
entrypoint = importlib.util.module_from_spec(spec)
sys.modules["entrypoint"] = entrypoint
spec.loader.exec_module(entrypoint)

ACTION = (ROOT / "action.yml").read_text()
WORKFLOWS = ROOT / ".github" / "workflows"
SHA_PIN = re.compile(r"uses: (?P<repo>[\w./-]+)@(?P<sha>[0-9a-f]{40}) # v\d+\.\d+\.\d+\n")
USES = re.compile(r"^\s*(?:- )?uses: (?P<what>\S+)", re.MULTILINE)
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
KITCHEN, CLEAN = str(FIXTURES / "kitchen_sink.ttl"), str(FIXTURES / "clean.ttl")


def _env(workspace: Path, **inputs: str) -> dict[str, str]:
    """The environment a step gets: one ``INPUT_*`` per input, plus the files the runner points at."""
    env = {
        "INPUT_FILES": CLEAN,
        "INPUT_ARGS": "",
        "INPUT_FAIL_ON": "",
        "INPUT_SARIF_FILE": "ontolint.sarif",
        "INPUT_SUMMARY": "true",
        "GITHUB_WORKSPACE": str(workspace),
        "RUNNER_TEMP": str(workspace),
        "GITHUB_OUTPUT": str(workspace / "github_output"),
        "GITHUB_STEP_SUMMARY": str(workspace / "step_summary"),
    }
    env.update({f"INPUT_{name.upper()}": value for name, value in inputs.items()})
    return env


def _outputs(workspace: Path) -> dict[str, str]:
    text = (workspace / "github_output").read_text()
    return dict(line.split("=", 1) for line in text.splitlines())


def _stub(tmp_path: Path, body: str) -> list[str]:
    """A stand-in for ``python -m ontolint``: it receives the argv the Action builds."""
    script = tmp_path / "stub.py"
    script.write_text("import os, sys\n" + body)
    return [sys.executable, str(script)]


# -- the version the Action installs -------------------------------------------------------------


def test_the_action_installs_the_version_of_the_checkout_it_was_pinned_to() -> None:
    assert entrypoint.pinned_version(ROOT) == VERSION


@pytest.mark.parametrize("version", ["0.1", "1.2.3rc1", "1.2.3.dev0", "latest", "1.2.3 --pre", ">=1"])
def test_only_an_exact_release_version_is_installed(tmp_path: Path, version: str) -> None:
    (tmp_path / "pyproject.toml").write_text(f'[project]\nname = "ontolint"\nversion = "{version}"\n')
    with pytest.raises(entrypoint.InputError, match="exact release version"):
        entrypoint.pinned_version(tmp_path)


def test_ontolint_is_installed_from_the_index_by_exact_version_without_its_dependencies() -> None:
    argv = entrypoint.install_command("uv", "/venv/bin/python", "1.2.3")
    assert argv == [
        "uv",
        "pip",
        "install",
        "--python",
        "/venv/bin/python",
        "--default-index",
        "https://pypi.org/simple",
        "--no-deps",
        "--only-binary",
        ":all:",
        "ontolint==1.2.3",
    ]


def test_dependencies_come_from_the_hash_locked_file_and_it_matches_the_lock() -> None:
    if shutil.which("uv") is None:
        pytest.skip("uv is not installed")
    exported = subprocess.run(  # noqa: S603 -- fixed argv.
        ["uv", "export", "--frozen", "--no-dev", "--no-emit-project", "--format", "requirements-txt", "--no-header"],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert (ROOT / "action" / "requirements.txt").read_text() == exported
    assert "--hash=sha256:" in exported
    assert not [line for line in exported.splitlines() if line.startswith("ontolint")], (
        "the project itself is not in it"
    )


# -- the inputs ----------------------------------------------------------------------------------


def test_a_default_run_asks_for_one_markdown_and_one_sarif_report(tmp_path: Path) -> None:
    settings = entrypoint.read_settings(_env(tmp_path, files="a.ttl\nb.ttl", args="--profile\nstrict"))
    assert settings.files == ["a.ttl", "b.ttl"]
    assert entrypoint.report_command(["py", "-m", "ontolint"], settings, "markdown", Path("out.md")) == [
        "py",
        "-m",
        "ontolint",
        "a.ttl",
        "b.ttl",
        "--profile",
        "strict",
        "--format",
        "markdown",
        "--output",
        "out.md",
    ]


def test_fail_on_is_passed_only_when_set(tmp_path: Path) -> None:
    unset = entrypoint.read_settings(_env(tmp_path))
    assert "--fail-on" not in entrypoint.report_command(["x"], unset, "sarif", Path("o"))
    chosen = entrypoint.read_settings(_env(tmp_path, fail_on="warning"))
    assert entrypoint.report_command(["x"], chosen, "sarif", Path("o"))[-6:-4] == ["--fail-on", "warning"]


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("files", "", "files"),
        ("files", "  \n\n", "files"),
        ("files", "-x.ttl", "starts with '-'"),
        ("files", "a.ttl\n--select", "starts with '-'"),
        ("files", "a\x00b.ttl", "control character"),
        ("files", "a\x1b[31m.ttl", "control character"),
        ("fail_on", "sometimes", "fail-on"),
        ("summary", "yes", "summary"),
        ("sarif_file", "", "sarif-file"),
        ("sarif_file", "../escape.sarif", "outside the workspace"),
        ("sarif_file", "/etc/cron.d/x", "outside the workspace"),
        ("sarif_file", "out/../../x", "outside the workspace"),
        ("sarif_file", "a\nb", "exactly one path"),
        ("args", "--format\njson", "--format"),
        ("args", "--format=json", "--format"),
        ("args", "--form=json", "is not allowed"),
        ("args", "--output=x", "--output"),
        ("args", "--out\nx", "is not allowed"),
        ("args", "--list-rules", "--list-rules"),
        ("args", "--explain\nSEC001", "--explain"),
        ("args", "--version", "--version"),
        ("args", "--measurements", "--measurements"),
    ],
)
def test_inputs_that_would_break_the_action_are_refused(tmp_path: Path, name: str, value: str, message: str) -> None:
    with pytest.raises(entrypoint.InputError, match=re.escape(message)):
        entrypoint.read_settings(_env(tmp_path, **{name: value}))


def test_a_report_inside_the_workspace_is_accepted_even_when_nested(tmp_path: Path) -> None:
    settings = entrypoint.read_settings(_env(tmp_path, sarif_file="reports/out.sarif"))
    assert settings.sarif_file == (tmp_path / "reports" / "out.sarif").resolve()


def test_a_symlink_cannot_carry_the_report_out_of_the_workspace(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(entrypoint.InputError, match="outside the workspace"):
        entrypoint.read_settings(_env(workspace, sarif_file="link/out.sarif"))


# -- the run -------------------------------------------------------------------------------------


def test_a_run_writes_the_sarif_report_the_summary_and_the_outputs(tmp_path: Path) -> None:
    code = entrypoint.run(entrypoint.read_settings(_env(tmp_path, files=KITCHEN, fail_on="error")))
    assert code == main([KITCHEN, "--fail-on", "error", "--format", "json", "--output", str(tmp_path / "j")]) == 1
    sarif = json.loads((tmp_path / "ontolint.sarif").read_text())
    assert sarif["version"] == "2.1.0"
    assert sarif["runs"][0]["results"]
    summary = (tmp_path / "step_summary").read_text()
    assert summary.startswith("## ontolint ")
    assert "**Failed**" in summary
    outputs = _outputs(tmp_path)
    assert outputs["exit-code"] == "1"
    assert outputs["sarif-file"] == str(tmp_path / "ontolint.sarif")
    assert Path(outputs["summary-file"]).read_text() == summary


def test_a_clean_run_exits_zero(tmp_path: Path) -> None:
    assert entrypoint.run(entrypoint.read_settings(_env(tmp_path, fail_on="never"))) == 0
    assert _outputs(tmp_path)["exit-code"] == "0"


def test_the_summary_is_appended_not_replaced(tmp_path: Path) -> None:
    (tmp_path / "step_summary").write_text("earlier step\n")
    entrypoint.run(entrypoint.read_settings(_env(tmp_path)))
    text = (tmp_path / "step_summary").read_text()
    assert text.startswith("earlier step\n")
    assert "## ontolint " in text


def test_the_summary_can_be_switched_off_and_the_sarif_report_stays(tmp_path: Path) -> None:
    entrypoint.run(entrypoint.read_settings(_env(tmp_path, summary="false")))
    assert not (tmp_path / "step_summary").exists()
    assert (tmp_path / "ontolint.sarif").exists()
    assert _outputs(tmp_path)["summary-file"] == ""


def test_without_a_summary_file_the_run_still_lints_and_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env = _env(tmp_path)
    del env["GITHUB_STEP_SUMMARY"]
    assert entrypoint.run(entrypoint.read_settings(env)) == 0
    assert "GITHUB_STEP_SUMMARY is not set" in capsys.readouterr().out


def test_a_tool_failure_is_exit_two_and_still_writes_the_outputs(tmp_path: Path) -> None:
    code = entrypoint.run(entrypoint.read_settings(_env(tmp_path, files=str(tmp_path / "missing.ttl"))))
    assert code == 2
    assert _outputs(tmp_path)["exit-code"] == "2"


def test_both_reports_are_attempted_even_when_the_first_run_fails(tmp_path: Path) -> None:
    command = _stub(
        tmp_path,
        "out = sys.argv[sys.argv.index('--output') + 1]\n"
        "open(out, 'w').write('x')\n"
        f"open({str(tmp_path / 'log')!r}, 'a').write(sys.argv[sys.argv.index('--format') + 1] + '\\n')\n"
        "sys.exit(2 if 'markdown' in sys.argv else 1)\n",
    )
    settings = entrypoint.read_settings(_env(tmp_path))
    assert entrypoint.run(settings, command, {}) == 2
    assert (tmp_path / "log").read_text().split() == ["markdown", "sarif"]


def test_ontolint_output_cannot_inject_workflow_commands(tmp_path: Path, capfd: pytest.CaptureFixture[str]) -> None:
    command = _stub(
        tmp_path,
        "print('::set-env name=PWNED::1', flush=True)\nprint('::error::hostile', file=sys.stderr, flush=True)\n"
        "out = sys.argv[sys.argv.index('--output') + 1]\nopen(out, 'w').write('x')\n",
    )
    entrypoint.run(entrypoint.read_settings(_env(tmp_path)), command)
    captured = capfd.readouterr()
    assert captured.err == "", "stderr is merged into stdout so the runner sees one ordered stream"
    lines = captured.out.splitlines()
    stops = [line for line in lines if line.startswith("::stop-commands::")]
    assert len(stops) == 2  # one around each report
    assert len(set(stops)) == 2  # a fresh token every time
    for stop in stops:
        token = stop.removeprefix("::stop-commands::")
        assert len(token) >= 32
        begin, end = lines.index(stop), lines.index(f"::{token}::")
        assert lines[begin + 1 : end] == ["::set-env name=PWNED::1", "::error::hostile"]


def test_the_child_gets_no_secret_of_the_caller(tmp_path: Path) -> None:
    command = _stub(
        tmp_path,
        "out = sys.argv[sys.argv.index('--output') + 1]\n"
        "open(out, 'w').write(repr(sorted(k for k in os.environ if k.startswith(('GITHUB_', 'INPUT_', 'ACTIONS_')))"
        " + [os.environ.get('TOKEN', '-'), os.environ.get('PATH', '-')]))\n",
    )
    env = _env(tmp_path) | {
        "TOKEN": "s3cret",
        "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "oidc",
        "GITHUB_TOKEN": "t",
        "PATH": "/p",
    }
    entrypoint.run(entrypoint.read_settings(env), command, env)
    seen = (tmp_path / "ontolint.sarif").read_text()
    assert seen == "[" + "'-', '/p'" + "]"


def test_the_environment_given_to_the_child_is_an_allow_list() -> None:
    env = {"PATH": "/bin", "HOME": "/h", "LANG": "C", "SECRET": "x", "GITHUB_TOKEN": "y", "INPUT_FILES": "z"}
    assert entrypoint.child_environment(env) == {"PATH": "/bin", "HOME": "/h", "LANG": "C", "PYTHONUTF8": "1"}


# -- the entry point -----------------------------------------------------------------------------


def test_main_reports_a_bad_input_as_an_escaped_error_annotation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for key, value in _env(tmp_path, files="-100%\nx").items():
        monkeypatch.setenv(key, value)
    assert entrypoint.main(["run"]) == 2
    assert (
        capsys.readouterr().out
        == "::error::ontolint action: files: '-100%25' starts with '-' and would be read as an option\n"
    )


def test_a_message_that_would_start_a_command_is_escaped(capsys: pytest.CaptureFixture[str]) -> None:
    assert entrypoint._escape_data("a%b\r\nc") == "a%25b%0D%0Ac"
    assert capsys.readouterr().out == ""


def test_main_refuses_an_unknown_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        entrypoint.main(["publish"])
    assert raised.value.code == 2
    assert "usage" in capsys.readouterr().err


def test_main_install_runs_the_exact_install_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ran: list[list[str]] = []
    monkeypatch.setattr(entrypoint, "_run", lambda argv: ran.append(argv) or 0)
    monkeypatch.setenv("ONTOLINT_ACTION_ROOT", str(ROOT))
    assert entrypoint.main(["install"]) == 0
    assert ran[0][-1] == f"ontolint=={VERSION}"
    assert ran[0][:3] == ["uv", "pip", "install"]


def test_main_install_stops_at_the_installer_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(entrypoint, "_run", lambda argv: 7)
    monkeypatch.setenv("ONTOLINT_ACTION_ROOT", str(ROOT))
    assert entrypoint.main(["install"]) == 7


# -- the definition ------------------------------------------------------------------------------


def test_action_yml_is_a_composite_action_with_documented_inputs_and_outputs() -> None:
    assert re.search(r"^runs:\n  using: composite$", ACTION, re.MULTILINE)
    for name in ("files", "args", "fail-on", "sarif-file", "summary"):
        assert re.search(rf"^  {name}:\n    description: .+", ACTION, re.MULTILINE), name
    for name in ("sarif-file", "summary-file", "exit-code"):
        assert re.search(rf"^  {name}:\n    description: .+\n    value: .+", ACTION, re.MULTILINE), name
    assert re.search(r"^  files:\n(?:    .+\n)*    required: true", ACTION, re.MULTILINE)


def test_every_action_the_definition_uses_is_pinned_to_a_commit() -> None:
    used = [m["what"] for m in USES.finditer(ACTION)]
    assert used, "the Action uses setup-uv"
    assert len(SHA_PIN.findall(ACTION)) == len(used)


def test_action_yml_pins_the_same_uv_as_the_workflows() -> None:
    ci = (WORKFLOWS / "ci.yml").read_text()
    pin = re.search(r"astral-sh/setup-uv@\w{40} # v[\d.]+", ci)
    assert pin is not None
    assert pin.group(0) in ACTION
    version = re.search(r'uv-version: "([\d.]+)"|version: "([\d.]+)"', ci)
    assert version is not None
    assert f'version: "{version.group(1) or version.group(2)}"' in ACTION


def _run_scripts() -> list[str]:
    return re.findall(r"^ +run: \|\n((?:(?: {8,}).*\n|\n)+)", ACTION, re.MULTILINE)


def test_no_expression_is_interpolated_into_a_shell_script() -> None:
    scripts = _run_scripts()
    assert len(scripts) == 2
    assert all("${{" not in script for script in scripts)
    assert len(re.findall(r"^ +run: ", ACTION, re.MULTILINE)) == len(scripts), "every run is a block scalar"


def test_inputs_reach_the_entry_point_only_through_the_environment() -> None:
    expressions = re.findall(r"\$\{\{ (.+?) \}\}", ACTION)
    assert sorted(e for e in expressions if e.startswith("inputs.")) == [
        "inputs.args",
        "inputs.fail-on",
        "inputs.files",
        "inputs.sarif-file",
        "inputs.summary",
    ]
    for name in re.findall(r"^ +(\w+): \$\{\{ inputs\.", ACTION, re.MULTILINE):
        assert name.startswith("INPUT_")


def test_the_action_asks_for_no_secret_and_echoes_none() -> None:
    assert "secrets." not in ACTION
    assert "github.token" not in ACTION
    assert "GITHUB_TOKEN" not in ACTION
    assert "set -x" not in ACTION
    assert not re.search(r"\becho\b.*\$\{?(INPUT|GITHUB_TOKEN)", ACTION)


def test_the_action_never_installs_the_latest_or_from_anywhere_but_the_lock_and_the_pin() -> None:
    assert "--require-hashes" in ACTION
    assert "action/requirements.txt" in ACTION
    assert "--upgrade" not in ACTION
    assert "git+" not in ACTION
    assert "@latest" not in ACTION


def test_the_release_proves_the_action_at_the_tag_it_is_publishing() -> None:
    release = (WORKFLOWS / "release.yml").read_text()
    pin = re.search(r"uses: arnaudgelas/ontolint@v(\d+\.\d+\.\d+)\n", release)
    assert pin is not None, "release.yml must run the Action at the new tag"
    assert pin.group(1) == VERSION, "scripts/bump_version.py rewrites this pin; run it for the release"
    assert re.search(r"^  action:\n(?:.*\n)*?    needs: verify$", release, re.MULTILINE)


def test_the_release_job_that_runs_the_action_has_read_only_permissions() -> None:
    release = (WORKFLOWS / "release.yml").read_text()
    job = re.search(r"^  action:\n((?:    .*\n|\n)+)", release, re.MULTILINE)
    assert job is not None
    assert "security-events" not in job.group(1)
    assert "write" not in job.group(1)


@pytest.mark.skipif(shutil.which("actionlint") is None, reason="actionlint is not installed")
def test_the_workflows_pass_actionlint() -> None:
    result = subprocess.run(  # noqa: S603 -- fixed argv.
        ["actionlint", *map(str, sorted(WORKFLOWS.glob("*.yml")))],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck is not installed")
def test_the_shell_in_the_action_passes_shellcheck(tmp_path: Path) -> None:
    scripts = _run_scripts()
    assert scripts
    for index, script in enumerate(scripts):
        path = tmp_path / f"step{index}.sh"
        path.write_text("#!/usr/bin/env bash\n" + "\n".join(line[8:] for line in script.splitlines()) + "\n")
        result = subprocess.run(["shellcheck", str(path)], capture_output=True, text=True, check=False)  # noqa: S603, S607
        assert result.returncode == 0, result.stdout
