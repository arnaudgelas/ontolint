"""A console that cannot encode the report degrades it instead of failing the run (issue #150).

``--format text`` and ``--format markdown`` print an IRI as it is.  On a stdout whose encoding cannot hold a character
(a Windows pipe under cp1252, or any system with ``PYTHONIOENCODING=cp1252``) the whole report used to be lost:
``TOOL001: report output failed: UnicodeEncodeError`` and exit 2, whatever the findings were.  The report is now
written with the characters the console cannot hold as ``\\uXXXX`` escapes (``backslashreplace``, what JSON and SARIF
always do), a ``TOOL002`` note on stderr says so, and the exit code is the findings': an encoding is a property of the
terminal, not of the ontology.  ``--output`` is UTF-8 and exact, and still fails on text UTF-8 cannot hold.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from ontolint import main

ONTOLOGY = (
    "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
    "<https://example.test/o> a owl:Ontology .\n"
    '<https://example.test/o#日本語Café> a owl:Class ; rdfs:label "A"@en .\n'
)
"""One class IRI that cp1252 cannot encode (Japanese) and a letter it can (e acute)."""
CP1252 = {"PYTHONUTF8": "0", "PYTHONIOENCODING": "cp1252"}
SURROGATE_TTL = (
    "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
    "@prefix m: <https://example.test/m#> .\n"
    "<https://example.test/onto> a owl:Ontology .\n"
    '<https://example.test/onto#A> a owl:Class ; m:in "\\uD800" .\n'
)
MODULE = "https://example.test/m#in"
FINDINGS, TOOL_FAILURE = 1, 2
NOTE = "TOOL002: warning: the console encoding cannot represent every character of the report"


def _cli(*args: str, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(  # noqa: S603 -- this interpreter, fixed module, test arguments
        [sys.executable, "-m", "ontolint", *args],
        cwd=cwd,
        capture_output=True,
        env={**os.environ, **(env or {})},
        timeout=180,
        check=False,
    )


@pytest.fixture
def source(tmp_path: Path) -> Path:
    (tmp_path / "u.ttl").write_text(ONTOLOGY, encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("kind", ["text", "markdown"])
def test_a_report_the_console_cannot_encode_is_degraded_and_the_exit_code_is_the_findings(
    source: Path, kind: str
) -> None:
    done = _cli("u.ttl", "--format", kind, cwd=source, env=CP1252)
    assert done.returncode == FINDINGS, done.stderr  # not 2: the report was written
    text = done.stdout.decode("cp1252")
    assert "\\u65e5\\u672c\\u8a9e" in text  # what cp1252 cannot hold is escaped ...
    assert "Café" in text  # ... and what it can hold is not
    assert NOTE in done.stderr.decode("ascii")
    assert b"TOOL001" not in done.stderr and b"Traceback" not in done.stderr


@pytest.mark.parametrize("kind", ["text", "markdown"])
def test_the_exit_code_is_still_driven_by_the_findings_alone(source: Path, kind: str) -> None:
    done = _cli("u.ttl", "--format", kind, "--fail-on", "never", cwd=source, env=CP1252)
    assert done.returncode == 0, done.stderr
    assert NOTE in done.stderr.decode("ascii")


def test_a_console_that_can_encode_the_report_gets_it_unchanged_and_no_note(source: Path) -> None:
    done = _cli("u.ttl", "--fail-on", "never", cwd=source, env={"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    assert done.returncode == 0
    assert "日本語" in done.stdout.decode("utf-8")
    assert b"TOOL002" not in done.stderr


def test_the_output_file_stays_exact_utf_8_and_the_note_is_not_printed(source: Path) -> None:
    done = _cli("u.ttl", "--fail-on", "never", "--output", "r.txt", cwd=source, env=CP1252)
    assert done.returncode == 0, done.stderr
    assert "日本語" in (source / "r.txt").read_text(encoding="utf-8")
    assert b"TOOL002" not in done.stderr


def test_json_and_sarif_are_unchanged(source: Path) -> None:
    for kind in ("json", "sarif"):
        done = _cli("u.ttl", "--format", kind, "--fail-on", "never", cwd=source, env=CP1252)
        assert done.returncode == 0 and "\\u65e5" in done.stdout.decode("ascii")
        assert b"TOOL002" not in done.stderr


# --- in process: the lone surrogate, and a stream that is not a console ----------------------------------------------


class _Stdout(io.TextIOWrapper):
    """A stdout over bytes with a chosen encoding, as a pipe under that code page is."""

    def __init__(self, encoding: str) -> None:
        self.raw_bytes = io.BytesIO()
        super().__init__(self.raw_bytes, encoding=encoding, write_through=True)


def _run_with(encoding: str, source: Path, monkeypatch: pytest.MonkeyPatch, *argv: str) -> tuple[int, str, str, Any]:
    out = _Stdout(encoding)
    err = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    monkeypatch.chdir(source)
    code = main([*argv])
    out.flush()
    return code, out.raw_bytes.getvalue().decode(encoding), err.getvalue(), out


def test_an_ascii_stdout_escapes_everything_that_is_not_ascii(source: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    code, out, err, _ = _run_with("ascii", source, monkeypatch, "u.ttl", "--fail-on", "never")
    assert code == 0
    assert "\\u65e5\\u672c\\u8a9eCaf\\xe9" in out
    assert NOTE in err


def test_a_lone_surrogate_in_a_report_is_escaped_on_stdout_like_json_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The module name is a literal the text report prints as it is; utf-8 cannot hold a lone surrogate either."""
    (tmp_path / "s.ttl").write_text(SURROGATE_TTL, encoding="utf-8")
    code, out, err, _ = _run_with(
        "utf-8", tmp_path, monkeypatch, "s.ttl", "--module-annotation", MODULE, "--fail-on", "never"
    )
    assert code == 0, err
    assert "\\ud800" in out and NOTE in err


def test_a_run_that_is_a_failure_for_another_reason_keeps_its_exit_code(
    source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, _, err, _ = _run_with("ascii", source, monkeypatch, "missing.ttl")
    assert code == TOOL_FAILURE and "INPUT001" in err and NOTE not in err
