"""The cross-platform smoke suite: parsing, the worker, the command line and the package on Linux, macOS and Windows.

Every test here carries the ``smoke`` marker (``pytest -m smoke``; ``scripts/gate.py --smoke`` runs exactly this
selection), and ``.github/workflows/smoke.yml`` runs it on all three systems for each pull request.  The whole suite
stays on the three-minute side on purpose: the full gate runs on Linux only, and this file is what the other two
systems must still pass.

What the suite is for, by the risk it covers:

* **parsing** -- CRLF line endings, a non-ASCII and a spaced path, and a baseline written by one run and read by
  another keep POSIX-style report paths on every system (a ``\\`` in a path would change every fingerprint).
* **worker** -- ``multiprocessing`` starts a child with ``spawn`` on macOS and Windows (Linux ``fork`` hides a task
  that cannot be pickled or an entry point without a ``__main__`` guard); :mod:`ontolint.worker` always asks for
  ``spawn``, so these tests run the same lifecycle everywhere and a failure on one system is a real finding.
* **command line** -- exit codes through a real interpreter, and a report that cannot be encoded on a console that is
  not UTF-8 (Windows pipes default to the ANSI code page): documented as ``TOOL001``, exit 2, never a traceback.
* **package** -- a built wheel, installed into a fresh environment, starts through its console script and
  ``python -m``; on Windows the script is a launcher ``.exe`` that nothing else exercises.

A test that can only mean something on one system says so with a marker that gives its reason
(``windows_only``, ``posix_only``), never with a silent skip; ``test_platform_skips.py`` fails the suite otherwise.
"""

from __future__ import annotations

import json
import multiprocessing
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from ontolint import main
from ontolint.worker import WorkerGone, WorkerTimeout, run_bounded

pytestmark = pytest.mark.smoke

ROOT = Path(__file__).parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
TOOL_FAILURE = 2
FINDINGS = 1

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="drive letters and backslashes exist on Windows only")
posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX permission bits; Windows ignores chmod for read access"
)

ONTOLOGY = (
    "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
    "<https://example.test/o> a owl:Ontology .\n"
    '<https://example.test/o#A> a owl:Class ; rdfs:label "A"@en .\n'
)
"""A small ontology with findings (no licence, no definition ...), so a run exits 1 unless told otherwise."""

NON_ASCII_ONTOLOGY = ONTOLOGY.replace("o#A>", "o#日本語Café>")
"""The same, with a class IRI that neither cp1252 nor ASCII can encode (Japanese letters) and one it can (e acute)."""


def _write(path: Path, text: str, *, crlf: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))
    return path


def _cli(*args: str, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[bytes]:
    """Run ``python -m ontolint`` in a fresh interpreter, with a bounded wait."""
    return subprocess.run(  # noqa: S603 -- this interpreter, fixed module, test arguments
        [sys.executable, "-m", "ontolint", *args],
        cwd=cwd,
        capture_output=True,
        env={**os.environ, **(env or {})},
        timeout=180,
        check=False,
    )


def _report(capsys: pytest.CaptureFixture[str], argv: Sequence[str]) -> dict[str, Any]:
    main([*argv, "--format", "json", "--fail-on", "never"])
    return json.loads(capsys.readouterr().out)


# --- parsing ---------------------------------------------------------------------------------------------------


def test_crlf_files_parse_and_report_the_same_findings_as_lf_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A checkout with ``core.autocrlf`` (Windows) turns every ``\\n`` of a fixture into ``\\r\\n``."""
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / "lf.ttl", ONTOLOGY)
    _write(tmp_path / "crlf.ttl", ONTOLOGY, crlf=True)
    lf = _report(capsys, ["lf.ttl"])["findings"]
    crlf = _report(capsys, ["crlf.ttl"])["findings"]
    assert lf
    assert [(f["rule"], f["focus"], f["message"]) for f in crlf] == [(f["rule"], f["focus"], f["message"]) for f in lf]


@pytest.mark.parametrize("name", ["plain.ttl", "café 日本.ttl"])
def test_report_paths_are_relative_and_posix_whatever_the_name_and_system(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / "sub dir" / name, ONTOLOGY)
    report = _report(capsys, [str(Path("sub dir") / name)])
    assert {f["path"] for f in report["findings"]} == {f"sub dir/{name}"}


def test_a_baseline_written_on_one_run_accepts_the_findings_of_another(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The baseline names files with ``/`` and survives being read back (encoding, line endings, separators)."""
    monkeypatch.chdir(tmp_path)
    source = str(_write(tmp_path / "onto" / "a.ttl", ONTOLOGY).relative_to(tmp_path))
    assert main([source, "--write-baseline", "base.json", "--fail-on", "never"]) == 0
    capsys.readouterr()
    text = (tmp_path / "base.json").read_text(encoding="utf-8")
    assert "\\" not in text
    assert "onto/a.ttl" in text
    assert main([source, "--baseline", "base.json", "--fail-on-stale-baseline"]) == 0


def test_two_spellings_of_one_path_make_one_report_where_the_file_system_ignores_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """macOS and Windows file systems are case-insensitive by default, Linux's are not: assert what each does."""
    monkeypatch.chdir(tmp_path)
    _write(tmp_path / "a.ttl", ONTOLOGY)
    insensitive = (tmp_path / "A.ttl").exists()
    if not insensitive:
        _write(tmp_path / "A.ttl", ONTOLOGY)  # a second file on a case-sensitive file system
    paths = {f["path"] for f in _report(capsys, ["a.ttl", "A.ttl"])["findings"]}
    assert len(paths) == (1 if insensitive else 2)


# --- the worker ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Echo:
    text: str

    def prepare(self) -> None:
        pass

    def run(self) -> bytes:
        return json.dumps({"echo": self.text, "pid": os.getpid()}).encode()


@dataclass(frozen=True)
class _Hang:
    def prepare(self) -> None:
        pass

    def run(self) -> bytes:
        import time  # noqa: PLC0415 -- the child imports it after unpickling

        time.sleep(600)
        return b"{}"  # pragma: no cover - the parent stops the worker first


@dataclass(frozen=True)
class _Die:
    def prepare(self) -> None:
        pass

    def run(self) -> bytes:
        os._exit(7)


def test_the_worker_answers_from_another_process_started_with_spawn() -> None:
    reply = run_bounded(_Echo("héllo 日本"), 120.0, name="smoke")
    assert reply["echo"] == "héllo 日本"
    assert reply["pid"] != os.getpid()
    assert multiprocessing.active_children() == []


def test_the_worker_is_stopped_and_reaped_when_its_budget_is_spent() -> None:
    """``terminate`` is ``SIGTERM`` on POSIX and ``TerminateProcess`` on Windows; both must leave no child."""
    with pytest.raises(WorkerTimeout):
        run_bounded(_Hang(), 0.5, name="smoke")
    assert multiprocessing.active_children() == []


def test_a_worker_that_exits_without_an_answer_is_reported_as_gone() -> None:
    with pytest.raises(WorkerGone):
        run_bounded(_Die(), 30.0, name="smoke")
    assert multiprocessing.active_children() == []


def test_a_budgeted_run_in_a_fresh_interpreter_gives_the_report_of_an_unbudgeted_one(tmp_path: Path) -> None:
    """Both workers (parse and SHACL) re-import the entry point under ``spawn``: it needs its ``__main__`` guard."""
    args = ["kitchen_sink.ttl", "--shapes", "kitchen_shapes.ttl", "--format", "json", "--fail-on", "never"]
    plain = _cli(*args, cwd=FIXTURES)
    budgeted = _cli(*args, "--max-parse-seconds", "120", "--max-validation-seconds", "120", cwd=FIXTURES)
    assert plain.returncode == budgeted.returncode == 0, budgeted.stderr.decode("utf-8", "replace")
    assert json.loads(budgeted.stdout) == json.loads(plain.stdout)
    assert json.loads(plain.stdout)["findings"]


# --- the command line ------------------------------------------------------------------------------------------


def test_exit_codes_through_a_real_interpreter(tmp_path: Path) -> None:
    assert _cli("clean.ttl", cwd=FIXTURES).returncode == 0
    assert _cli("kitchen_sink.ttl", cwd=FIXTURES).returncode == FINDINGS
    missing = _cli("missing.ttl", cwd=FIXTURES)
    assert missing.returncode == TOOL_FAILURE
    assert b"INPUT001" in missing.stderr
    assert b"Traceback" not in missing.stderr


def test_a_console_that_is_not_utf8_gets_every_format_and_text_degrades_with_a_note(tmp_path: Path) -> None:
    """Python on Windows encodes a pipe with the ANSI code page (cp1252); the two variables ask for it on any system.

    JSON and SARIF are escaped to ASCII. Text and markdown used to fail with TOOL001 and exit 2 (issue #150): they are
    now written with what cp1252 cannot hold as ``\\uXXXX`` escapes, TOOL002 says so, and the exit code is the run's.
    """
    cp1252 = {"PYTHONUTF8": "0", "PYTHONIOENCODING": "cp1252"}
    _write(tmp_path / "u.ttl", NON_ASCII_ONTOLOGY)
    for kind in ("json", "sarif"):
        done = _cli("u.ttl", "--format", kind, "--fail-on", "never", cwd=tmp_path, env=cp1252)
        assert done.returncode == 0, done.stderr
        assert "\\u65e5" in done.stdout.decode("ascii")
    for kind in ("text", "markdown"):
        done = _cli("u.ttl", "--format", kind, "--fail-on", "never", cwd=tmp_path, env=cp1252)
        assert done.returncode == 0, done.stderr
        assert "\\u65e5\\u672c\\u8a9eCaf\u00e9" in done.stdout.decode("cp1252")
        assert b"TOOL002: warning: the console encoding" in done.stderr
        assert b"TOOL001" not in done.stderr and b"Traceback" not in done.stderr
    done = _cli("u.ttl", "--fail-on", "never", "--output", "r.txt", cwd=tmp_path, env=cp1252)  # --output is UTF-8
    assert done.returncode == 0, done.stderr
    assert "日本語" in (tmp_path / "r.txt").read_text(encoding="utf-8")


@windows_only
def test_a_drive_letter_path_outside_the_working_directory_is_reported_with_forward_slashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    elsewhere = _write(tmp_path / "other" / "a.ttl", ONTOLOGY)
    monkeypatch.chdir(ROOT)
    (path,) = {f["path"] for f in _report(capsys, [str(elsewhere)])["findings"]}
    assert path[1:3] == ":/", path
    assert "\\" not in path
    main([str(elsewhere), "--format", "sarif", "--fail-on", "never"])
    uri = json.loads(capsys.readouterr().out)["runs"][0]["results"][0]["locations"][0]["physicalLocation"][
        "artifactLocation"
    ]["uri"]
    assert uri.startswith("file:///"), uri
    assert "\\" not in uri


@posix_only
@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0, reason="root reads files whatever their mode")
def test_a_file_the_user_cannot_read_is_a_tool_failure_not_a_traceback(tmp_path: Path) -> None:
    locked = _write(tmp_path / "locked.ttl", ONTOLOGY)
    locked.chmod(0)
    try:
        done = _cli("locked.ttl", cwd=tmp_path)
    finally:
        locked.chmod(0o600)
    assert done.returncode == TOOL_FAILURE
    assert b"INPUT001" in done.stderr
    assert b"Traceback" not in done.stderr


# --- the package -----------------------------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv builds and installs the wheel")
def test_the_built_wheel_installs_and_starts_through_its_script_and_python_m(tmp_path: Path) -> None:
    """Build the wheel, install it (with its dependencies) into an empty environment, and lint a file with it."""
    uv = shutil.which("uv")
    assert uv is not None
    dist, env = tmp_path / "dist", tmp_path / "venv"
    subprocess.run([uv, "build", "--wheel", "--out-dir", str(dist), str(ROOT)], check=True, timeout=300)  # noqa: S603
    (wheel,) = dist.glob("ontolint-*.whl")
    subprocess.run([uv, "venv", "--python", sys.executable, str(env)], check=True, timeout=120)  # noqa: S603
    bindir, suffix = (env / "Scripts", ".exe") if sys.platform == "win32" else (env / "bin", "")
    python = bindir / f"python{suffix}"
    subprocess.run([uv, "pip", "install", "--python", str(python), str(wheel)], check=True, timeout=600)  # noqa: S603
    sample = _write(tmp_path / "a.ttl", ONTOLOGY)
    for command in ([str(bindir / f"ontolint{suffix}")], [str(python), "-m", "ontolint"]):
        version = subprocess.run(  # noqa: S603
            [*command, "--version"], capture_output=True, text=True, timeout=120, check=False, cwd=tmp_path
        )
        assert version.returncode == 0, version.stderr
        assert version.stdout.startswith("ontolint ")
        done = subprocess.run(  # noqa: S603
            [*command, str(sample), "--format", "json", "--fail-on", "never", "--max-parse-seconds", "120"],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
            cwd=tmp_path,
        )
        assert done.returncode == 0, done.stderr
        assert json.loads(done.stdout)["findings"]
    catalogue = subprocess.run(  # noqa: S603
        [
            str(python),
            "-c",
            "import importlib.resources as r; print(r.files('ontolint.data').joinpath('rule_catalogue.csv').is_file())",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert catalogue.stdout.strip() == "True", catalogue.stderr
