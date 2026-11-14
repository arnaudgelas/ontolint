"""A shapes graph that breaks SHACL-SHACL (issue #62): one summary, one line per result, each printed once.

pySHACL meta-validates the shapes graph (``meta_shacl=True``) and raises before it validates any data; that is no
verdict on the data, so SHACL001 stays ``failed`` and the run exits 2 (OPS018).  What changes is what is printed:
the rule-execution line says only that the shapes graph does not conform to SHACL-SHACL, and stderr (the TOOL001
line) lists one masked, capped line per MetaSHACL result, with the SHQ rule that names the same defect.  A pySHACL
report is never printed whole, and a failure that is not a MetaSHACL verdict keeps its own detail.
"""

# ruff: noqa: PLR2004, SLF001

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

import pyshacl
import pytest
from rdflib import Graph

from ontolint import Linter
from ontolint.adapters import shacl
from ontolint.adapters.shacl import ShapesNotWellFormed, bounded_shacl_issues, shacl_issues
from ontolint.cli import main
from ontolint.models import ExecutionStatus

PREFIXES = (
    "@prefix : <https://example.test/onto#> .\n@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
    "@prefix sh: <http://www.w3.org/ns/shacl#> .\n@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
)
DATA = PREFIXES + ":Person a owl:Class .\n:alice a :Person .\n"
NAME = "https://example.test/onto#NameShape"
SUMMARY = "the shapes graph does not conform to SHACL-SHACL"
# The issue's reproduction: a property shape without a path that a node shape refers to.
NO_PATH = (
    PREFIXES
    + ":Person a owl:Class .\n:alice a :Person .\n"
    + ":PersonShape a sh:NodeShape ; sh:targetClass :Person ; sh:property :NameShape .\n"
    + ":NameShape a sh:PropertyShape ; sh:minCount 1 .\n"
)
FAILED = 2


def _graph(text: str) -> Graph:
    return Graph().parse(data=text, format="turtle")


def _raised(shapes: str, data: str = DATA) -> ShapesNotWellFormed:
    with pytest.raises(ShapesNotWellFormed) as caught:
        shacl_issues(_graph(data), _graph(shapes))
    return caught.value


def _run(tmp_path: Path, shapes: str, *argv: str) -> tuple[int, Path, Path]:
    (tmp_path / "data.ttl").write_text(DATA, encoding="utf-8")
    (tmp_path / "shapes.ttl").write_text(shapes, encoding="utf-8")
    out = tmp_path / "out.txt"
    code = main([str(tmp_path / "data.ttl"), "--shapes", str(tmp_path / "shapes.ttl"), "--output", str(out), *argv])
    return code, out, tmp_path


# --- the reproduction ---------------------------------------------------------------------------------------------


def test_the_adapter_raises_one_summary_and_one_line_per_result() -> None:
    failure = _raised(NO_PATH)

    assert failure.summary == SUMMARY
    assert str(failure) == "\n".join((SUMMARY, *failure.results))
    # The missing path and the xone of the shape that follows from it: two results, no pySHACL report text.
    assert len(failure.results) == 2
    assert "Validation Report" not in str(failure)
    assert "Conforms:" not in str(failure)
    path_line = next(line for line in failure.results if "sh:path:" in line)
    assert path_line.startswith(f"{NAME}: sh:path: ")
    assert path_line.endswith("(SHQ023)")
    assert "\n" not in path_line


def test_the_result_that_follows_from_a_missing_path_points_at_the_same_rule() -> None:
    xone = next(line for line in _raised(NO_PATH).results if "exactly one shape" in line)

    assert xone.startswith(f"{NAME}: ")
    assert xone.endswith("(SHQ023)")


def test_the_run_still_fails_and_the_execution_names_no_pyshacl_text() -> None:
    execution = Linter(_graph(DATA), _graph(NO_PATH)).execute(["SHACL001"]).executions[0]

    assert execution.status is ExecutionStatus.FAILED
    assert execution.detail == SUMMARY
    assert len(execution.results) == 2
    assert "Validation Report" not in execution.detail + "".join(execution.results)


def test_the_cli_prints_the_results_once_on_stderr_and_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "data.ttl").write_text(DATA, encoding="utf-8")
    (tmp_path / "shapes.ttl").write_text(NO_PATH, encoding="utf-8")
    argv = [str(tmp_path / "data.ttl"), "--shapes", str(tmp_path / "shapes.ttl"), "--select", "SHQ023,SHACL001"]

    assert main(argv) == FAILED
    captured = capsys.readouterr()

    assert f"[FAILED     ] SHACL001: {SUMMARY}\n" in captured.out + "\n"
    assert "SHQ023" in captured.out  # the finding the issue says the user is pointed at
    assert "Validation Report" not in captured.out + captured.err
    assert "Conforms: False" not in captured.out + captured.err
    err = captured.err
    # One TOOL001 line, then the results, indented; nothing from pySHACL's logger.
    assert err.count(f"TOOL001: rule SHACL001 failed for {tmp_path / 'data.ttl'}: {SUMMARY}\n") == 1
    assert err.count(f"  {NAME}: sh:path: ") == 1
    assert err.count("SHACL File does not validate") == 0
    result_lines = [line for line in err.splitlines() if line.startswith(f"  {NAME}: ")]
    assert len(result_lines) == 2
    assert not any("Fix:" in line for line in err.splitlines())


def test_the_json_report_carries_the_summary_and_the_results(tmp_path: Path) -> None:
    code, out, _ = _run(tmp_path, NO_PATH, "--select", "SHACL001", "--format", "json")

    assert code == FAILED
    (execution,) = [e for f in json.loads(out.read_text())["files"] for e in f["executions"] if e["rule"] == "SHACL001"]
    assert execution["status"] == "failed"
    assert execution["detail"] == SUMMARY
    assert len(execution["results"]) == 2
    assert any(line.startswith(f"{NAME}: sh:path: ") for line in execution["results"])


def test_the_json_executions_of_a_rule_that_has_no_results_are_unchanged(tmp_path: Path) -> None:
    code, out, _ = _run(
        tmp_path,
        PREFIXES + ":S a sh:NodeShape ; sh:targetClass :Person ; sh:nodeKind sh:IRI .\n",
        "--select",
        "SHACL001",
        "--format",
        "json",
    )

    assert code == 0
    (execution,) = [e for f in json.loads(out.read_text())["files"] for e in f["executions"] if e["rule"] == "SHACL001"]
    assert execution == {"rule": "SHACL001", "status": "executed", "detail": ""}


def test_the_sarif_notification_carries_the_results(tmp_path: Path) -> None:
    code, out, _ = _run(tmp_path, NO_PATH, "--select", "SHACL001", "--format", "sarif")

    assert code == FAILED
    invocation = json.loads(out.read_text())["runs"][0]["invocations"][0]
    (note,) = [n for n in invocation["toolExecutionNotifications"] if n["associatedRule"]["id"] == "SHACL001"]
    assert note["message"]["text"] == f"Rule SHACL001 failed: {SUMMARY}"
    assert len(note["properties"]["results"]) == 2


def test_a_markdown_summary_names_only_the_summary(tmp_path: Path) -> None:
    code, out, _ = _run(tmp_path, NO_PATH, "--select", "SHACL001", "--format", "markdown")

    assert code == FAILED
    assert SUMMARY in out.read_text()
    assert "Validation Report" not in out.read_text()


def test_pyshacl_does_not_log_the_report_itself(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """pySHACL logs the whole report at ERROR on its own logger, to stderr: that is the second copy of the issue."""
    _run(tmp_path, NO_PATH, "--select", "SHACL001")

    assert "Validation Report" not in capsys.readouterr().err


def test_the_logger_filter_is_removed_afterwards() -> None:
    before = list(logging.getLogger("pyshacl-validate").filters)
    _raised(NO_PATH)

    assert logging.getLogger("pyshacl-validate").filters == before


def test_a_budgeted_run_reports_the_same_summary_and_results() -> None:
    inline = _raised(NO_PATH)
    with pytest.raises(Exception, match=SUMMARY) as caught:
        bounded_shacl_issues(_graph(DATA), _graph(NO_PATH), 120.0)
    # The worker's failure carries the exception's text: the summary, then each result on its own line.
    assert getattr(caught.value, "cause_type", "") == "ShapesNotWellFormed"
    assert getattr(caught.value, "detail", "") == str(inline)


def test_a_budgeted_cli_run_prints_the_results_once(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "data.ttl").write_text(DATA, encoding="utf-8")
    (tmp_path / "shapes.ttl").write_text(NO_PATH, encoding="utf-8")
    argv = [str(tmp_path / "data.ttl"), "--shapes", str(tmp_path / "shapes.ttl"), "--select", "SHACL001"]

    assert main([*argv, "--max-validation-seconds", "120"]) == FAILED
    captured = capsys.readouterr()

    assert captured.out.count(SUMMARY) == 1
    assert captured.err.count(f"  {NAME}: sh:path: ") == 1
    assert "Validation Report" not in captured.out + captured.err


# --- a valid shapes graph and genuine failures are untouched ------------------------------------------------------


def test_a_well_formed_shapes_graph_is_validated_as_before() -> None:
    shapes = PREFIXES + ":S a sh:NodeShape ; sh:targetClass :Person ; sh:property [ sh:path :name ; sh:minCount 1 ] .\n"

    findings = shacl_issues(_graph(DATA), _graph(shapes))

    assert [f.rule for f in findings] == ["SHACL001"]
    assert "Less than 1 values" in findings[0].message


def test_a_crash_that_is_not_a_metashacl_verdict_is_still_a_tool_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def crash(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("internal pySHACL error")

    monkeypatch.setattr(pyshacl, "validate", crash)

    execution = Linter(_graph(DATA), _graph(NO_PATH)).execute(["SHACL001"]).executions[0]

    assert execution.status is ExecutionStatus.FAILED
    assert execution.detail == "RuntimeError: internal pySHACL error"
    assert execution.results == ()


def test_a_reportable_error_that_is_not_the_metashacl_one_keeps_its_text(monkeypatch: pytest.MonkeyPatch) -> None:
    from pyshacl.errors import ReportableRuntimeError  # noqa: PLC0415

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise ReportableRuntimeError("Cannot use SHACL-JS in SPARQL Remote Graph Mode.")

    monkeypatch.setattr(pyshacl, "validate", refuse)

    execution = Linter(_graph(DATA), _graph(NO_PATH)).execute(["SHACL001"]).executions[0]

    assert execution.detail == "ReportableRuntimeError: Cannot use SHACL-JS in SPARQL Remote Graph Mode."
    assert execution.results == ()


def test_a_metashacl_message_for_a_shapes_graph_that_conforms_is_not_believed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The text alone does not make a verdict: the shapes graph is meta-validated again, and a pass is a crash."""
    from pyshacl.errors import ReportableRuntimeError  # noqa: PLC0415

    def claim(*_args: object, **_kwargs: object) -> None:
        raise ReportableRuntimeError(f"{shacl.META_SHACL_PREFIX}.\nsomething else")

    monkeypatch.setattr(pyshacl, "validate", claim)
    valid = PREFIXES + ":S a sh:NodeShape ; sh:targetClass :Person .\n"

    with pytest.raises(ReportableRuntimeError):
        shacl_issues(_graph(DATA), _graph(valid))
    execution = Linter(_graph(DATA), _graph(valid)).execute(["SHACL001"]).executions[0]
    assert execution.detail.startswith("ReportableRuntimeError: ")
    assert execution.results == ()


# --- the pointer names a rule that really fires --------------------------------------------------------------------

# Each shapes graph breaks SHACL-SHACL in a way an SHQ rule names: (shapes, the rule that must be pointed at).
POINTED = {
    "no path": (":S a sh:NodeShape ; sh:property [ sh:minCount 1 ] .", "SHQ023"),
    "several paths": (":S a sh:NodeShape ; sh:property [ sh:path :a, :b ] .", "SHQ023"),
    "a typed property shape with no path": (":P a sh:PropertyShape ; sh:maxCount 1 .", "SHQ023"),
    "a string minCount": (':S a sh:NodeShape ; sh:property [ sh:path :a ; sh:minCount "x" ] .', "SHQ008"),
    "a decimal maxLength": (":S a sh:NodeShape ; sh:property [ sh:path :a ; sh:maxLength 1.5 ] .", "SHQ008"),
    "a derived-type maxCount": (
        ':S a sh:NodeShape ; sh:property [ sh:path :a ; sh:maxCount "1"^^xsd:int ] .',
        "SHQ008",
    ),
    "a literal targetClass": (':S a sh:NodeShape ; sh:targetClass "lit" .', "SHQ022"),
    "a blank targetSubjectsOf": (":S a sh:NodeShape ; sh:targetSubjectsOf [ ] .", "SHQ022"),
    "a literal severity": (':S a sh:NodeShape ; sh:severity "high" .', "SHQ014"),
}


@pytest.mark.parametrize("name", sorted(POINTED))
def test_a_pointer_names_a_rule_that_fires_on_the_same_shape(name: str) -> None:
    shapes, rule = POINTED[name]
    text = PREFIXES + shapes + "\n"
    failure = _raised(text)

    assert any(line.endswith(f"({rule})") for line in failure.results), failure.results
    pointed = set(_foci(failure, rule))
    fired = {finding.focus for finding in Linter(_graph(DATA), _graph(text)).execute([rule]).findings}
    assert pointed
    assert pointed <= fired, (pointed, fired)


def _foci(failure: ShapesNotWellFormed, rule: str) -> list[str]:
    return [line.split(": ", 1)[0] for line in failure.results if line.endswith(f"({rule})")]


# The gaps PR #46 kept ("Known gaps kept") stay unreported by SHQ: MetaSHACL is then the only signal, and the line
# says what is wrong without pointing at a rule that would not find it.  (A typed sh:NodeShape with sh:path is not one
# of them: SHACL-SHACL accepts it, and pySHACL then refuses it with a ShapeLoadError, which stays a tool failure.)
UNPOINTED = {
    "uniqueLang on a node shape": ":S a sh:NodeShape ; sh:uniqueLang true .",
    "two severities": ":S a sh:NodeShape ; sh:severity sh:Info, sh:Warning .",
}


@pytest.mark.parametrize("name", sorted(UNPOINTED))
def test_a_known_gap_is_reported_without_a_pointer(name: str) -> None:
    failure = _raised(PREFIXES + UNPOINTED[name] + "\n")

    assert failure.results
    assert not any(re.search(r"\(SHQ\d+\)$", line) for line in failure.results), failure.results
    shq = Linter(_graph(DATA), _graph(PREFIXES + UNPOINTED[name] + "\n")).execute(["SHQ023", "SHQ012", "SHQ014"])
    assert shq.findings == ()  # the gap is real: nothing but SHACL001 can say it


# --- masking, one line, a cap ---------------------------------------------------------------------------------------


def test_a_userinfo_in_a_focus_is_masked_in_the_execution_and_on_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shapes = PREFIXES + "<https://user:hunter2@example.test/Shape> a sh:PropertyShape ; sh:minCount 1 .\n"
    (tmp_path / "data.ttl").write_text(DATA, encoding="utf-8")
    (tmp_path / "shapes.ttl").write_text(shapes, encoding="utf-8")

    code = main([str(tmp_path / "data.ttl"), "--shapes", str(tmp_path / "shapes.ttl"), "--select", "SHACL001"])
    captured = capsys.readouterr()

    assert code == FAILED
    assert "hunter2" not in captured.out + captured.err
    assert "https://example.test/Shape" in captured.err or "example.test/Shape" in captured.err
    execution = Linter(_graph(DATA), _graph(shapes)).execute(["SHACL001"]).executions[0]
    assert "hunter2" not in "".join(execution.results)


def test_a_control_or_bidi_character_is_written_as_an_escape_on_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shapes = PREFIXES + "<https://example.test/a\\u202Eb\\u0007> a sh:PropertyShape ; sh:minCount 1 .\n"
    (tmp_path / "data.ttl").write_text(DATA, encoding="utf-8")
    (tmp_path / "shapes.ttl").write_text(shapes, encoding="utf-8")

    code = main([str(tmp_path / "data.ttl"), "--shapes", str(tmp_path / "shapes.ttl"), "--select", "SHACL001"])
    err = capsys.readouterr().err

    assert code == FAILED
    assert chr(0x202E) not in err
    assert "\x07" not in err
    assert "\\u202E" in err


def test_a_long_result_line_is_cut() -> None:
    long = "x" * 2_000
    shapes = PREFIXES + f"<https://example.test/{long}> a sh:PropertyShape ; sh:minCount 1 .\n"

    failure = _raised(shapes)

    assert failure.results
    assert all(len(line) <= shacl.MAX_RESULT_LINE + len(shacl.ELLIPSIS) + len(" (SHQ023)") for line in failure.results)
    assert any(shacl.ELLIPSIS + " (SHQ023)" in line for line in failure.results)
    assert any(line.endswith(shacl.ELLIPSIS) or "(SHQ023)" in line for line in failure.results)


def test_the_results_are_capped_and_the_rest_counted() -> None:
    count = shacl.MAX_RESULT_LINES + 7
    shapes = PREFIXES + "".join(f":P{i} a sh:PropertyShape ; sh:minCount 1 .\n" for i in range(count))

    failure = _raised(shapes)

    shown = failure.results
    assert len(shown) == shacl.MAX_RESULT_LINES + 1
    omitted = count - shacl.MAX_RESULT_LINES  # a bare property shape fails only sh:xone: one result each
    assert shown[-1] == f"... and {omitted} more result(s) not shown"


def test_the_results_are_sorted_and_do_not_depend_on_the_hash_seed() -> None:
    shapes = PREFIXES + "".join(f":P{i} a sh:PropertyShape ; sh:minCount 1 .\n" for i in range(5))

    lines = _raised(shapes).results

    assert list(lines) == sorted(lines)


def test_a_blank_shape_is_named_by_its_content_not_its_parser_label() -> None:
    a = _raised(PREFIXES + ":S a sh:NodeShape ; sh:property [ sh:minCount 1 ] .\n").results
    b = _raised(PREFIXES + ":S a sh:NodeShape ; sh:property [ sh:minCount 1 ] .\n").results

    assert a == b
    assert all("_:" not in line or re.search(r"_:[0-9a-f]{8,}", line) for line in a)


def test_the_cost_is_linear_in_the_number_of_results() -> None:
    def seconds(count: int) -> float:
        shapes = PREFIXES + "".join(f":P{i} a sh:PropertyShape ; sh:minCount 1 .\n" for i in range(count))
        started = time.perf_counter()
        _raised(shapes)
        return time.perf_counter() - started

    seconds(5)  # warm the SHACL-SHACL graph
    small, large = seconds(60), seconds(240)

    assert large < max(small, 0.05) * 12  # 4x the shapes: well under quadratic growth (16x)


def test_the_execution_dict_has_a_results_key_only_when_there_are_results() -> None:
    from ontolint.models import RuleExecution  # noqa: PLC0415
    from ontolint.reporting import _execution_dicts  # noqa: PLC0415

    plain = RuleExecution("SHACL001", ExecutionStatus.FAILED, "boom")
    rich = RuleExecution("SHACL001", ExecutionStatus.FAILED, SUMMARY, ("a", "b"))

    assert _execution_dicts([plain]) == [{"rule": "SHACL001", "status": "failed", "detail": "boom"}]
    dicts: list[dict[str, Any]] = _execution_dicts([rich])  # type: ignore[assignment]
    assert dicts[0]["results"] == ["a", "b"]


def test_a_node_shape_with_a_path_is_a_pyshacl_load_error_not_a_metashacl_verdict() -> None:
    execution = (
        Linter(_graph(DATA), _graph(PREFIXES + ":S a sh:NodeShape ; sh:targetClass :Person ; sh:path :p .\n"))
        .execute(["SHACL001"])
        .executions[0]
    )

    assert execution.status is ExecutionStatus.FAILED
    assert execution.detail.startswith("ShapeLoadError: A shape defined as a NodeShape cannot be the subject")
    assert execution.results == ()


@pytest.mark.parametrize(("extra", "last"), [(0, None), (1, "... and 1 more result(s) not shown")])
def test_the_cap_applies_after_exactly_twenty_results(extra: int, last: str | None) -> None:
    count = shacl.MAX_RESULT_LINES + extra
    shapes = PREFIXES + "".join(f":P{i} a sh:PropertyShape ; sh:minCount 1 .\n" for i in range(count))

    shown = _raised(shapes).results

    assert len(shown) == shacl.MAX_RESULT_LINES + (1 if last else 0)
    assert (shown[-1] == last) if last else all(line.endswith("(SHQ023)") for line in shown)


def test_a_result_line_ends_with_its_pointer_even_when_the_text_is_cut() -> None:
    shapes = PREFIXES + f"<https://example.test/{'y' * 500}> a sh:PropertyShape ; sh:minCount 1 .\n"

    (line,) = _raised(shapes).results

    assert line.endswith(f"{shacl.ELLIPSIS} (SHQ023)")
    assert len(line) == shacl.MAX_RESULT_LINE + len(shacl.ELLIPSIS) + len(" (SHQ023)")
