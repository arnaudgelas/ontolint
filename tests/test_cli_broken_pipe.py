"""A reader that closes its end of stdout or stderr (``ontolint ... | head``) ends the run quietly with exit 141.

Python ignores SIGPIPE, so a write to a closed pipe raises ``BrokenPipeError``; a small output stays in the buffer
and fails at the interpreter's last flush instead (exit 120, "Exception ignored").  Neither may show: no traceback,
no noise, and a status that is not 1, the verdict "findings".  141 is 128 + SIGPIPE, what a shell reports for the
tools the closed pipe kills (``cat``, ``grep``, ``git``).  Exit 2 keeps its place: a run that failed says so.

The subprocess tests close the read end of an ``os.pipe`` before the run starts, so every write fails, whatever the
timing; the "reader leaves after one line" test is the ``| head -1`` of the issue.  They are POSIX only: Windows
reports a closed pipe as ``OSError`` (EINVAL), which is not handled (see README "Exit codes").
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from ontolint.cli import _release, main

PIPE_CLOSED = 141  # 128 + SIGPIPE
TOOL_FAILURE = 2
FLUSHES_IN_A_RUN = 2  # one after the write, one on the way out of ``main``
KITCHEN = str(Path(__file__).parent / "fixtures" / "kitchen_sink.ttl")

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="Windows reports a closed pipe as OSError (EINVAL)")


def _ontology(path: Path, classes: int) -> str:
    lines = [
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
        "@prefix : <https://example.test/onto#> .",
        "<https://example.test/onto> a owl:Ontology .",
        *(f":C{i} a owl:Class ." for i in range(classes)),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def _cli(*args: str) -> list[str]:
    return [sys.executable, "-m", "ontolint", *args]


def _with_stdout_reader_gone(*args: str) -> subprocess.CompletedProcess[str]:
    read_end, write_end = os.pipe()
    os.close(read_end)
    try:
        return subprocess.run(_cli(*args), stdout=write_end, stderr=subprocess.PIPE, text=True, check=False)  # noqa: S603
    finally:
        os.close(write_end)


@posix_only
@pytest.mark.parametrize(
    ("lints_a_file", "args"),
    [
        pytest.param(True, (), id="text-report"),
        pytest.param(True, ("--format", "json"), id="json-report"),
        pytest.param(True, ("--format", "sarif"), id="sarif-report"),
        pytest.param(True, ("--format", "markdown"), id="markdown-report"),
        pytest.param(False, ("--version",), id="version"),
        pytest.param(False, ("--list-rules",), id="list-rules"),
        pytest.param(False, ("--list-rules", "--format", "json"), id="list-rules-json"),
        pytest.param(False, ("--explain", "LEX001"), id="explain"),
    ],
)
def test_stdout_with_no_reader_is_exit_141_with_nothing_on_stderr(
    tmp_path: Path, lints_a_file: bool, args: tuple[str, ...]
) -> None:
    command = (_ontology(tmp_path / "a.ttl", 3), *args) if lints_a_file else args
    done = _with_stdout_reader_gone(*command)
    assert done.stderr == ""  # no traceback, no "Exception ignored ... BrokenPipeError"
    assert done.returncode == PIPE_CLOSED


@posix_only
def test_help_with_no_reader_is_silent_and_exits_as_help_does() -> None:
    done = _with_stdout_reader_gone("--help")
    assert done.stderr == ""
    assert done.returncode == 0


@posix_only
@pytest.mark.parametrize("fmt", ["text", "json", "sarif"])
def test_a_reader_that_stops_after_the_first_line_ends_the_run_quietly(tmp_path: Path, fmt: str) -> None:
    """``ontolint BIG --format F | head -1``: a report far larger than the pipe, read for one line only."""
    ontology = _ontology(tmp_path / "big.ttl", 4000)
    process = subprocess.Popen(  # noqa: S603
        _cli(ontology, "--format", fmt), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    assert process.stdout is not None and process.stderr is not None
    first = process.stdout.readline()
    process.stdout.close()
    stderr = process.stderr.read()
    process.stderr.close()
    returncode = process.wait()
    assert first.strip() != ""
    assert stderr == ""
    assert returncode == PIPE_CLOSED


@posix_only
def test_a_reader_that_reads_everything_changes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The same report and exit status through a real pipe as in process: the fix must not touch a normal run."""
    ontology = _ontology(tmp_path / "a.ttl", 3)
    done = subprocess.run(_cli(ontology, "--format", "json"), capture_output=True, text=True, check=False)  # noqa: S603
    code = main([ontology, "--format", "json"])
    in_process = capsys.readouterr()
    assert done.stdout == in_process.out and done.stdout != ""
    assert done.stderr == in_process.err == ""
    assert done.returncode == code
    assert json.loads(done.stdout)["schema_version"] == 1


@posix_only
def test_stderr_with_no_reader_is_exit_141_before_any_report(tmp_path: Path) -> None:
    """``2>&1 | head``: a diagnostic written to a closed stderr ends the run; nothing is left to report on."""
    ontology = _ontology(tmp_path / "a.ttl", 3)
    read_end, write_end = os.pipe()
    os.close(read_end)
    try:
        done = subprocess.run(  # noqa: S603
            _cli(ontology, "--base", "https://nowhere.example/"),
            stdout=subprocess.PIPE,
            stderr=write_end,
            text=True,
            check=False,
        )
    finally:
        os.close(write_end)
    assert done.returncode == PIPE_CLOSED
    assert done.stdout == ""


class _ClosedStdout:
    """A stdout whose reader has gone: ``write`` fails at once, or only ``flush`` does (the buffered case)."""

    def __init__(self, *, fail_on: str) -> None:
        self.fail_on = fail_on
        self.written: list[str] = []

    def write(self, text: str) -> int:
        if self.fail_on == "write":
            raise BrokenPipeError(32, "Broken pipe")
        self.written.append(text)
        return len(text)

    def flush(self) -> None:
        if self.fail_on == "flush":
            raise BrokenPipeError(32, "Broken pipe")


@pytest.fixture
def lint(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> Any:
    """Run the CLI in process with a closed stdout of the given kind; return ``(exit code, stderr)``."""

    def _lint(fail_on: str, *argv: str) -> tuple[int, str]:
        monkeypatch.setattr(sys, "stdout", _ClosedStdout(fail_on=fail_on))
        code = main(list(argv))
        return code, capsys.readouterr().err

    return _lint


@pytest.mark.parametrize("fail_on", ["write", "flush"])
@pytest.mark.parametrize("argv", [(KITCHEN,), (KITCHEN, "--format", "json"), ("--version",), ("--list-rules",)])
def test_in_process_a_closed_stdout_is_exit_141_and_silent(lint: Any, fail_on: str, argv: tuple[str, ...]) -> None:
    code, err = lint(fail_on, *argv)
    assert (code, err) == (PIPE_CLOSED, "")


def test_in_process_exit_141_replaces_the_verdict_not_a_tool_failure(lint: Any) -> None:
    """With a finding at the threshold the run would exit 1; undelivered, it exits 141, never 1 or 0."""
    code, _ = lint("write", KITCHEN, "--fail-on", "info")
    assert code == PIPE_CLOSED
    code, _ = lint("write", KITCHEN, "--fail-on", "never")
    assert code == PIPE_CLOSED


def test_in_process_exit_2_outranks_141_and_its_diagnostics_still_reach_stderr(
    lint: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("ontolint.engine.shutil.which", lambda _: "docker")

    def boom(*_: Any, **__: Any) -> Any:
        raise OSError("docker daemon unreachable")

    monkeypatch.setattr("ontolint.ontolint.subprocess.run", boom)
    code, err = lint("write", KITCHEN, "--owl-profile", "EL")
    assert code == TOOL_FAILURE
    assert "SEM001 failed" in err and "Traceback" not in err


def test_a_broken_pipe_raised_inside_the_lint_is_still_a_tool_failure(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only writes to the standard streams are treated as a closed reader; a ``BrokenPipeError`` from, say, a
    subprocess pipe inside the lint is the failure it always was (TOOL001, exit 2), never a silent 141."""

    def boom(*_: Any, **__: Any) -> Any:
        raise BrokenPipeError(32, "Broken pipe")

    monkeypatch.setattr("ontolint.cli._lint_file", boom)
    code = main([KITCHEN])
    err = capsys.readouterr().err
    assert code == TOOL_FAILURE
    assert err.startswith("TOOL001: lint execution failed: BrokenPipeError")


def test_a_closed_stdout_with_an_output_file_is_not_involved(tmp_path: Path, lint: Any) -> None:
    """``--output FILE`` writes no report to stdout, so a closed stdout changes nothing."""
    report = tmp_path / "report.json"
    code, err = lint("write", KITCHEN, "--format", "json", "--output", str(report))
    assert code in (0, 1)
    assert err == ""
    assert json.loads(report.read_text(encoding="utf-8"))["schema_version"] == 1


@pytest.mark.parametrize("fail_on", ["write", "flush"])
def test_in_process_help_with_a_closed_stdout_exits_as_help_does(
    fail_on: str, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """argparse swallows a failed write; the flush that follows must not raise either (it is released instead)."""
    monkeypatch.setattr(sys, "stdout", _ClosedStdout(fail_on=fail_on))
    with pytest.raises(SystemExit) as stop:
        main(["--help"])
    assert stop.value.code == 0
    assert capsys.readouterr().err == ""


def test_in_process_help_without_a_stdout_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    """``pythonw`` and some embedding applications have ``sys.stdout = None``; ``--help`` has always coped."""
    monkeypatch.setattr(sys, "stdout", None)
    with pytest.raises(SystemExit) as stop:
        main(["--help"])
    assert stop.value.code == 0


class _ClosedStderr:
    def write(self, _: str) -> int:
        raise BrokenPipeError(32, "Broken pipe")

    def flush(self) -> None:
        raise BrokenPipeError(32, "Broken pipe")


def test_in_process_a_closed_stderr_is_exit_141(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The first diagnostic (TOOL002: ``--base`` selects no term) finds no reader on stderr."""
    ontology = _ontology(tmp_path / "a.ttl", 3)
    monkeypatch.setattr(sys, "stderr", _ClosedStderr())
    assert main([ontology, "--base", "https://nowhere.example/"]) == PIPE_CLOSED


class _Stdout:
    """A stdout of another kind: ``write`` only, a ``flush`` that fails (first or later), or one that holds output."""

    def __init__(self, *, flush: Any = None, fail_flush_from: int = 1, error: OSError | None = None) -> None:
        self.text = ""
        self.flushes = 0
        self.fail_flush_from = fail_flush_from
        self.error = error
        if flush is None:
            self.flush = None  # type: ignore[assignment]  # a stdout with no flush at all

    def write(self, text: str) -> int:
        self.text += text
        return len(text)

    def flush(self) -> None:  # replaced by ``None`` in ``__init__`` when the object has none
        self.flushes += 1
        if self.error is not None and self.flushes >= self.fail_flush_from:
            raise self.error


def test_in_process_info_commands_without_a_stdout_are_silent_no_ops(monkeypatch: pytest.MonkeyPatch) -> None:
    """``print`` has always treated ``sys.stdout = None`` (``pythonw``, ``>&-``) as nothing to write to."""
    monkeypatch.setattr(sys, "stdout", None)
    assert main(["--version"]) == 0
    assert main(["--list-rules"]) == 0


def test_in_process_a_stdout_with_no_flush_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    stdout = _Stdout()
    monkeypatch.setattr(sys, "stdout", stdout)
    assert main(["--version"]) == 0
    assert stdout.text.startswith("ontolint ")
    assert main([KITCHEN, "--format", "json"]) in (0, 1)
    assert json.loads(stdout.text.split("\n", 1)[1])["schema_version"] == 1


def test_in_process_a_late_flush_failure_never_replaces_the_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    """``main``'s last flush swallows what is not a closed pipe; the interpreter reports it at exit, as before."""
    stdout = _Stdout(flush=True, fail_flush_from=2, error=OSError(28, "No space left on device"))
    monkeypatch.setattr(sys, "stdout", stdout)
    assert main(["--version"]) == 0  # the second flush, in ``main``'s ``finally``, raised OSError
    assert stdout.flushes == FLUSHES_IN_A_RUN


def test_in_process_help_with_a_failing_flush_still_exits_as_help_does(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdout", _Stdout(flush=True, error=OSError(28, "No space left on device")))
    with pytest.raises(SystemExit) as stop:
        main(["--help"])
    assert stop.value.code == 0  # not the OSError of the flush


def test_in_process_a_report_that_cannot_be_flushed_is_tool001(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A full disk is not a closed reader: it is the report-output failure ``--output`` already has."""
    monkeypatch.setattr(sys, "stdout", _Stdout(flush=True, error=OSError(28, "No space left on device")))
    code = main([KITCHEN])
    assert code == TOOL_FAILURE
    assert capsys.readouterr().err.startswith("TOOL001: report output failed: OSError: ")


class _Stderr:
    """A stderr that fails on the lines containing ``fail_on`` (all of them when it is empty) and keeps the rest."""

    def __init__(self, fail_on: str = "") -> None:
        self.fail_on = fail_on
        self.text = ""

    def write(self, text: str) -> int:
        if self.fail_on in text:
            raise BrokenPipeError(32, "Broken pipe")
        self.text += text
        return len(text)

    def flush(self) -> None:
        return None


def test_in_process_a_stderr_that_closes_after_the_report_keeps_the_exit_status(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The report was delivered; only the TOOL001 line for the failed rule finds no reader: the run still says 2."""
    monkeypatch.setattr("ontolint.engine.shutil.which", lambda _: "docker")

    def boom(*_: Any, **__: Any) -> Any:
        raise OSError("docker daemon unreachable")

    monkeypatch.setattr("ontolint.ontolint.subprocess.run", boom)
    stderr = _Stderr(fail_on="SEM001")
    monkeypatch.setattr(sys, "stderr", stderr)
    code = main([KITCHEN, "--owl-profile", "EL", "--format", "json"])
    assert code == TOOL_FAILURE  # not 141: the report is out
    assert json.loads(capsys.readouterr().out)["schema_version"] == 1


def test_in_process_an_unknown_rule_with_a_closed_stderr_is_still_exit_2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stderr", _ClosedStderr())
    assert main(["--explain", "NOPE999"]) == TOOL_FAILURE


@posix_only
def test_release_points_a_dead_pipe_at_the_null_device() -> None:
    """After ``_release`` a write to the descriptor succeeds (it goes nowhere) instead of raising EPIPE."""
    read_end, write_end = os.pipe()
    os.close(read_end)

    class _Stream:
        def fileno(self) -> int:
            return write_end

    try:
        with pytest.raises(BrokenPipeError):
            os.write(write_end, b"x")
        _release(_Stream())  # type: ignore[arg-type]  # a stream with just a descriptor
        assert os.write(write_end, b"x") == 1
    finally:
        os.close(write_end)
