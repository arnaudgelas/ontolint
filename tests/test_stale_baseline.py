"""OPS003: baseline fingerprints that match no finding are reported, and can fail a CI run."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ontolint.cli import main

OWL_CLASS = "<http://www.w3.org/2002/07/owl#Class>"
TWO_CLASSES = f"<https://example.test/A> a {OWL_CLASS} .\n<https://example.test/B> a {OWL_CLASS} .\n"
ONE_CLASS = f"<https://example.test/A> a {OWL_CLASS} .\n"
STALE_NOTE = "fingerprint(s) match no finding of this run"


@pytest.fixture
def stale(tmp_path: Path) -> tuple[Path, Path]:
    """A baseline written for two classes, and the same file after one class (and its findings) left."""
    source = tmp_path / "a.ttl"
    source.write_text(TWO_CLASSES, encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    main([str(source), "--write-baseline", str(baseline), "--fail-on", "never", "--output", str(tmp_path / "x")])
    source.write_text(ONE_CLASS, encoding="utf-8")
    return source, baseline


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    code = main(list(argv))
    return code, capsys.readouterr().out


def test_json_lists_the_stale_fingerprints(stale: tuple[Path, Path], capsys: pytest.CaptureFixture[str]) -> None:
    source, baseline = stale
    code, out = _run(capsys, str(source), "--baseline", str(baseline), "--format", "json", "--fail-on", "never")
    written = set(json.loads(baseline.read_text(encoding="utf-8"))["fingerprints"])
    listed = json.loads(out)["baseline"]["stale_fingerprints"]
    assert code == 0
    assert listed
    assert listed == sorted(listed)
    assert set(listed) < written


def test_text_and_sarif_say_the_baseline_has_stale_entries(
    stale: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    source, baseline = stale
    _code, text = _run(capsys, str(source), "--baseline", str(baseline), "--fail-on", "never")
    assert STALE_NOTE in text
    _code, sarif = _run(capsys, str(source), "--baseline", str(baseline), "--format", "sarif", "--fail-on", "never")
    notes = [n["message"]["text"] for n in json.loads(sarif)["runs"][0]["invocations"][0]["toolExecutionNotifications"]]
    assert any(STALE_NOTE in note for note in notes)


def test_fail_on_stale_baseline_turns_a_clean_run_into_exit_1(
    stale: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    source, baseline = stale
    args = [str(source), "--baseline", str(baseline), "--fail-on", "never"]
    assert _run(capsys, *args)[0] == 0
    assert _run(capsys, *args, "--fail-on-stale-baseline")[0] == 1


def test_a_matching_baseline_is_not_stale(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "a.ttl"
    source.write_text(TWO_CLASSES, encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    main([str(source), "--write-baseline", str(baseline), "--fail-on", "never", "--output", str(tmp_path / "x")])
    args = [str(source), "--baseline", str(baseline), "--fail-on-stale-baseline", "--fail-on", "never"]
    code, out = _run(capsys, *args, "--format", "json")
    assert code == 0
    assert json.loads(out)["baseline"] == {"stale_fingerprints": []}
    assert STALE_NOTE not in _run(capsys, *args)[1]


def test_without_a_baseline_the_json_has_no_baseline_key(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "a.ttl"
    source.write_text(ONE_CLASS, encoding="utf-8")
    assert "baseline" not in json.loads(_run(capsys, str(source), "--format", "json", "--fail-on", "never")[1])


def test_fail_on_stale_baseline_needs_a_baseline(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main([str(tmp_path / "a.ttl"), "--fail-on-stale-baseline"])
