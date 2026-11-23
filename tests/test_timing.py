"""Opt-in ``--timing`` (issue #174): ``timing`` in JSON, ``ontolintTiming`` in SARIF, a footer in text.

What is measured: ``load_ms`` is the time spent reading the inputs (ontologies, shapes graph, pattern library);
``units_ms`` is the time of each unit that ran rules (a rule module for the graph rules, one adapter per adapter
rule), failed or not; ``rules_ms`` gives each rule that ran the time of its unit (rules of one module share it: do
not add them up); ``total_ms`` is the wall time from the start of the run to the end of the last rule, writing the
report excluded.  All integers, milliseconds, rounded to the nearest.  The flag is off by default and the output
without it is byte for byte what it was; the timing is in no baseline, fingerprint, quality snapshot, DQV file or
Markdown summary.  The clock is a parameter (``main(argv, clock=...)``), so these tests are deterministic.
"""

from __future__ import annotations

import contextlib
import io
import json
from collections.abc import Callable
from importlib import resources
from pathlib import Path
from typing import Any

import pytest
from jsonschema.validators import validator_for
from test_differential import FIXTURES

from ontolint import engine
from ontolint.cli import main
from ontolint.timing import Recorder

ROOT = Path(__file__).parent.parent
SCHEMA = json.loads(
    (resources.files("ontolint") / "schemas" / "lint-report.v1.schema.json").read_text(encoding="utf-8")
)
LINT = ["kitchen_sink.ttl", "--format", "json", "--fail-on", "never"]


class FakeClock:
    """A clock that advances by one millisecond per reading, so every duration is a count of readings."""

    def __init__(self, step: float = 0.001) -> None:
        self.calls = 0
        self.step = step

    def __call__(self) -> float:
        self.calls += 1
        return self.calls * self.step


def _run(argv: list[str], monkeypatch: pytest.MonkeyPatch, clock: Callable[[], float] | None = None) -> tuple[int, str]:
    monkeypatch.chdir(FIXTURES)
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = main(argv, clock=clock) if clock is not None else main(argv)
    return code, out.getvalue()


def _json(argv: list[str], monkeypatch: pytest.MonkeyPatch, clock: Callable[[], float] | None = None) -> dict[str, Any]:
    return json.loads(_run(argv, monkeypatch, clock)[1])


# --- the flag is off by default ---


def test_without_the_flag_there_is_no_timing_anywhere(monkeypatch: pytest.MonkeyPatch) -> None:
    assert "timing" not in _json(LINT, monkeypatch)
    sarif = _json(["kitchen_sink.ttl", "--format", "sarif", "--fail-on", "never"], monkeypatch)
    assert "ontolintTiming" not in sarif["runs"][0]["invocations"][0]["properties"]
    assert "Timing:" not in _run(["kitchen_sink.ttl", "--fail-on", "never"], monkeypatch)[1]


def test_the_flag_is_in_the_help_and_the_readme() -> None:
    assert "--timing" in (ROOT / "README.md").read_text(encoding="utf-8")
    help_text = io.StringIO()
    with contextlib.redirect_stdout(help_text), pytest.raises(SystemExit):
        main(["--help"])
    assert "--timing" in help_text.getvalue()


# --- the keys ---


def test_with_the_flag_the_json_report_has_a_timing_object_that_validates(monkeypatch: pytest.MonkeyPatch) -> None:
    document = _json([*LINT, "--timing"], monkeypatch, FakeClock())
    timing = document["timing"]
    assert set(timing) == {"total_ms", "load_ms", "units_ms", "rules_ms"}
    assert all(isinstance(timing[key], int) and timing[key] >= 0 for key in ("total_ms", "load_ms"))
    assert timing["units_ms"] and timing["rules_ms"]
    validator_for(SCHEMA)(SCHEMA).validate(document)


def test_a_fake_clock_gives_exact_values(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeClock()
    document = _json([*LINT, "--timing"], monkeypatch, clock)
    timing = document["timing"]
    assert timing["total_ms"] == clock.calls - 1  # one reading at the start, one at the end, 1 ms per reading
    assert timing["load_ms"] >= 1
    assert all(ms >= 1 for ms in timing["units_ms"].values())  # a unit is read twice, 1 ms apart at least
    assert set(timing["rules_ms"].values()) <= set(timing["units_ms"].values())


def test_a_rule_that_ran_has_the_time_of_its_unit_and_a_rule_that_did_not_run_has_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _json([*LINT, "--timing", "--select", "OWL001,OWL002,SHACL001"], monkeypatch, FakeClock())
    timing = document["timing"]
    assert timing["rules_ms"]["OWL001"] == timing["rules_ms"]["OWL002"] == timing["units_ms"]["owl"]
    assert "SHACL001" not in timing["rules_ms"]  # no shapes graph: skipped, never zero
    assert "LEX001" not in timing["rules_ms"]  # not selected


def test_recorder_rounds_to_the_nearest_millisecond_and_adds_a_unit_that_runs_twice() -> None:
    readings = iter([0.0, 0.0, 0.0004, 0.0004, 0.0006, 0.0006, 0.0011, 0.01])
    recorder = Recorder(lambda: next(readings))
    with recorder.load():
        pass  # 0.0 -> 0.0004: 0 ms
    with recorder.unit("owl", ["OWL001"]):
        pass  # 0.0004 -> 0.0006: 0.2 ms
    with recorder.unit("owl", ["OWL002"]):
        pass  # 0.0006 -> 0.0011: 0.5 ms; the unit totals 0.7 ms
    timing = recorder.finish()
    assert (timing.load_ms, timing.units_ms, timing.rules_ms, timing.total_ms) == (
        0,
        {"owl": 1},
        {"OWL001": 1, "OWL002": 1},
        10,
    )


# --- nothing else changes ---


def _without_timing(document: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in document.items() if key != "timing"}


def test_two_runs_differ_only_in_the_timing_subtree(monkeypatch: pytest.MonkeyPatch) -> None:
    plain = _json(LINT, monkeypatch)
    timed = _json([*LINT, "--timing"], monkeypatch)
    again = _json([*LINT, "--timing"], monkeypatch)
    assert _without_timing(timed) == plain == _without_timing(again)


def test_timing_with_a_baseline_changes_neither_findings_nor_exit_status(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    baseline = tmp_path / "baseline.json"
    monkeypatch.chdir(FIXTURES)
    assert main(["populated.ttl", "--write-baseline", str(baseline), "--fail-on", "never"]) == 0
    argv = ["kitchen_sink.ttl", "--format", "json", "--baseline", str(baseline), "--fail-on", "error"]
    code_plain, out_plain = _run(argv, monkeypatch)
    code_timed, out_timed = _run([*argv, "--timing"], monkeypatch)
    assert code_plain == code_timed
    assert _without_timing(json.loads(out_timed)) == json.loads(out_plain)


@pytest.mark.parametrize(
    "extra",
    [
        ["--format", "markdown"],
        ["--write-baseline", "{out}"],
        ["--write-quality-snapshot", "{out}"],
        ["--write-dqv", "{out}"],
    ],
    ids=["markdown", "baseline", "quality-snapshot", "dqv"],
)
def test_the_timing_is_in_no_baseline_snapshot_dqv_or_markdown_file(
    extra: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def written(timing: bool) -> tuple[str, str]:
        out = tmp_path / f"out{int(timing)}"
        argv = [
            "clean.ttl",
            "--fail-on",
            "never",
            *(a.replace("{out}", str(out)) for a in extra),
            *(["--timing"] if timing else []),
        ]
        _code, stdout = _run(argv, monkeypatch)
        return stdout, out.read_text(encoding="utf-8") if out.exists() else ""

    plain, timed = written(False), written(True)
    assert plain[1] == timed[1]  # the file, when the option writes one
    if "markdown" in extra[-1]:
        assert plain[0] == timed[0]  # the Markdown summary


# --- failures still have a time ---


def test_a_rule_module_that_raises_still_records_its_time(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_ctx: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setitem(engine.FAMILY_RUNNERS, "owl", boom)
    document = _json([*LINT, "--timing", "--select", "OWL001"], monkeypatch, FakeClock())
    execution = next(x for x in document["files"][0]["executions"] if x["rule"] == "OWL001")
    assert execution["status"] == "failed"
    assert document["timing"]["units_ms"]["owl"] >= 1
    assert document["timing"]["rules_ms"]["OWL001"] >= 1


def test_an_adapter_that_times_out_still_records_its_time(monkeypatch: pytest.MonkeyPatch) -> None:
    def slow(_ctx: object) -> list[object]:
        raise TimeoutError("shapes validation exceeded the time budget")

    monkeypatch.setattr(engine, "_shacl_with_background", slow)
    argv = ["clean.ttl", "--format", "json", "--fail-on", "never", "--shapes", "clean_shapes.ttl", "--timing"]
    document = _json(argv, monkeypatch, FakeClock())
    execution = next(x for x in document["files"][0]["executions"] if x["rule"] == "SHACL001")
    assert execution["status"] == "failed"
    assert document["timing"]["rules_ms"]["SHACL001"] >= 1
    assert document["timing"]["units_ms"]["adapter:SHACL001"] >= 1


# --- SARIF and text ---


def test_sarif_carries_the_timing_in_the_invocation_properties(monkeypatch: pytest.MonkeyPatch) -> None:
    sarif = _json(["kitchen_sink.ttl", "--format", "sarif", "--fail-on", "never", "--timing"], monkeypatch, FakeClock())
    properties = sarif["runs"][0]["invocations"][0]["properties"]
    assert set(properties["ontolintTiming"]) == {"total_ms", "load_ms", "units_ms", "rules_ms"}
    assert properties["executionSummary"]  # the existing property is untouched


def test_the_text_report_ends_with_a_timing_footer(monkeypatch: pytest.MonkeyPatch) -> None:
    text = _run(["kitchen_sink.ttl", "--fail-on", "never", "--timing"], monkeypatch, FakeClock())[1]
    footer = text.rstrip("\n").splitlines()[-1]
    assert footer.startswith("Timing: total ") and " ms; load " in footer and "slowest: " in footer
