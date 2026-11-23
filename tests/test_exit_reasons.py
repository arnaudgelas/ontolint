"""Why a run exited 2 (issue #175): the ``exit`` object of the report, and one helper for every exit-2 path.

The exit code itself does not change (0 clean, 1 gated findings, 2 tool failure).  What is new is the reason:

* a run that wrote a report and exited 2 (a rule failed, timed out or is unsupported; a budget on an untaken
  measurement; a measurement that could not be computed) says why in the report: ``exit`` in JSON, a
  notification and ``ontolintExit`` in SARIF, and lines in the text;
* a run that exited 2 before it had a report (an input that does not parse, a policy rejected as ``GOV020``, an
  unknown rule, a usage error, an internal error, ...) states its reason on stderr, through one helper
  (:func:`ontolint.exit_reasons.refuse`) that a test here proves is the only way ``cli.py`` leaves with 2.
"""

from __future__ import annotations

import ast
import json
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from jsonschema.validators import validator_for
from test_report_schema import SCHEMA

from ontolint import cli, engine, exit_reasons
from ontolint.cli import main
from ontolint.exit_reasons import KINDS, ExitReason, report_reasons
from ontolint.models import ExecutionStatus
from ontolint.reporting import (
    FileReport,
    RunReport,
    render_report,
    run_exit_code,
    to_json,
    to_sarif_report,
)
from ontolint.rules import measurements
from ontolint.rules.registry import default_registry

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
KITCHEN = str(FIXTURES / "kitchen_sink.ttl")
QUALITY = str(FIXTURES / "quality" / "before.ttl")
CLI_SOURCE = ROOT / "src" / "ontolint" / "cli.py"
SECRET = "https://user:hunter2@example.test/x"

type Run = Callable[..., tuple[int, str, str]]


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Run:
    def go(*argv: str) -> tuple[int, str, str]:
        capsys.readouterr()
        code = main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return go


@pytest.fixture
def refusals(monkeypatch: pytest.MonkeyPatch) -> list[ExitReason]:
    """Every reason the CLI refuses with, in order: the helper is wrapped, not replaced."""
    seen: list[ExitReason] = []
    real = cli.refuse

    def spy(reason: ExitReason, **kwargs: Any) -> int:
        seen.append(reason)
        return real(reason, **kwargs)

    monkeypatch.setattr(cli, "refuse", spy)
    return seen


def _break_rule_module(monkeypatch: pytest.MonkeyPatch, rule: str, message: str) -> None:
    def boom(_ctx: Any) -> None:
        raise ValueError(message)

    monkeypatch.setitem(engine.FAMILY_RUNNERS, default_registry().get(rule).module, boom)


def _break_measurement(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_ctx: Any, _term: object) -> bool:
        raise ValueError(f"boom {SECRET}")

    monkeypatch.setattr(measurements, "is_unlabelled", boom)


def _json(out: str) -> dict[str, Any]:
    document: dict[str, Any] = json.loads(out)
    return document


def _reasons(document: dict[str, Any]) -> list[dict[str, Any]]:
    reasons: list[dict[str, Any]] = document["exit"]["reasons"]
    return reasons


# --- a run that wrote a report: one fixture per cause --------------------------------------------------------------


def test_a_rule_that_raises_is_a_rule_failed_reason(run: Run, monkeypatch: pytest.MonkeyPatch) -> None:
    _break_rule_module(monkeypatch, "LEX004", "it broke")
    code, out, _ = run(KITCHEN, "--format", "json", "--fail-on", "never")
    assert code == 2
    document = _json(out)
    assert document["exit"]["code"] == 2
    reasons = [r for r in _reasons(document) if r["rule"] == "LEX004"]
    assert reasons == [
        {
            "kind": "rule_failed",
            "message": "ValueError: it broke",
            "rule": "LEX004",
            "path": "kitchen_sink.ttl",
        }
    ]


def test_an_unsupported_backend_is_a_rule_unsupported_reason(run: Run, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ontolint.engine.shutil.which", lambda _: None)
    code, out, _ = run(KITCHEN, "--owl-profile", "EL", "--format", "json", "--fail-on", "never")
    assert code == 2
    (reason,) = _reasons(_json(out))
    assert reason["kind"] == "rule_unsupported"
    assert reason["rule"] == "SEM001"
    assert "docker executable was not found" in reason["message"]


def test_a_robot_timeout_is_a_rule_timeout_reason(run: Run, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ontolint.engine.shutil.which", lambda _: "docker")

    def slow(command: list[str], **_: Any) -> Any:
        raise subprocess.TimeoutExpired(command, 1)

    monkeypatch.setattr("ontolint.adapters.robot.subprocess.run", slow)
    code, out, _ = run(KITCHEN, "--owl-profile", "EL", "--format", "json", "--fail-on", "never")
    assert code == 2
    (reason,) = _reasons(_json(out))
    assert reason["kind"] == "rule_timeout"
    assert reason["rule"] == "SEM001"
    assert "did not finish" in reason["message"]


def test_a_failed_measurement_is_a_measurement_failed_reason(run: Run, monkeypatch: pytest.MonkeyPatch) -> None:
    _break_measurement(monkeypatch)
    code, out, _ = run(KITCHEN, "--format", "json", "--ignore", "METRIC", "--measurements")
    assert code == 2
    reasons = _reasons(_json(out))
    assert reasons
    assert {r["kind"] for r in reasons} == {"measurement_failed"}
    assert all(r["measurement"] and r["path"] == "kitchen_sink.ttl" for r in reasons)


def test_a_budget_on_an_untaken_measurement_is_a_budget_unmeasured_reason(tmp_path: Path, run: Run) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"quality_budgets": {"shacl_class_target_coverage": {"minimum": 0}}}), "utf-8")
    code, out, _ = run("--config", str(policy), "--select", "METRIC014", "--format", "json", KITCHEN)
    assert code == 2
    (reason,) = _reasons(_json(out))
    assert reason["kind"] == "budget_unmeasured"
    assert reason["rule"] == "METRIC014"
    assert "shacl_class_target_coverage: no SHACL shapes graph was supplied" in reason["message"]


def test_several_causes_come_out_in_a_deterministic_order(run: Run, monkeypatch: pytest.MonkeyPatch) -> None:
    _break_rule_module(monkeypatch, "LEX004", "it broke")
    _break_measurement(monkeypatch)
    argv = (KITCHEN, QUALITY, "--format", "json", "--measurements", "--fail-on", "never")
    first = _json(run(*argv)[1])
    second = _json(run(*argv)[1])
    assert _reasons(first) == _reasons(second)
    kinds = [r["kind"] for r in _reasons(first)]
    # Rules first (file by file, in the order they ran), then measurements (file by file, in the order computed).
    assert kinds == sorted(kinds, key=lambda k: k == "measurement_failed")
    assert "rule_failed" in kinds
    assert "measurement_failed" in kinds
    paths = [r["path"] for r in _reasons(first) if r["kind"] == "rule_failed"]
    assert paths == sorted(paths, key=[f["path"] for f in first["files"]].index)


# --- a run that exits 0 or 1 has no reasons -----------------------------------------------------------------------


@pytest.mark.parametrize("fail_on", ["never", "error"])
def test_a_run_that_exits_0_or_1_has_no_exit_object(run: Run, fail_on: str) -> None:
    code, out, _ = run(KITCHEN, "--format", "json", "--fail-on", fail_on)
    assert code in (0, 1)
    assert "exit" not in _json(out)
    sarif = _json(run(KITCHEN, "--format", "sarif", "--fail-on", fail_on)[1])
    properties = sarif["runs"][0]["invocations"][0]["properties"]
    assert "ontolintExit" not in properties


def test_skipped_rules_are_no_reason(run: Run) -> None:
    # Rules skipped for a missing input are listed as skipped, never as a cause of exit 2.
    code, out, _ = run(KITCHEN, "--format", "json", "--fail-on", "never", "--select", "SHQ001")
    assert code == 0
    assert "exit" not in _json(out)


def test_exit_reasons_exist_exactly_when_the_report_says_exit_2(run: Run, monkeypatch: pytest.MonkeyPatch) -> None:
    _break_rule_module(monkeypatch, "LEX004", "it broke")
    _, out, _ = run(KITCHEN, "--format", "json", "--fail-on", "never")
    document = _json(out)
    assert document["execution_summary"]["failed"] >= 1
    assert document["exit"] == {"code": 2, "reasons": document["exit"]["reasons"]}


# --- the same reasons in SARIF, in text, and on stderr --------------------------------------------------------------


def test_sarif_carries_the_reasons_and_a_failed_measurement_is_not_a_successful_execution(
    run: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bug (#175): ``executionSuccessful`` stayed true when the run exited 2 for a measurement that failed."""
    _break_measurement(monkeypatch)
    code, out, _ = run(KITCHEN, "--format", "sarif", "--ignore", "METRIC", "--measurements")
    assert code == 2
    invocation = _json(out)["runs"][0]["invocations"][0]
    assert invocation["exitCode"] == 2
    assert invocation["executionSuccessful"] is False
    errors = [n for n in invocation["toolExecutionNotifications"] if n["level"] == "error"]
    assert errors
    assert all("measurement" in n["message"]["text"] for n in errors)
    exit_property = invocation["properties"]["ontolintExit"]
    assert exit_property["code"] == 2
    assert {r["kind"] for r in exit_property["reasons"]} == {"measurement_failed"}


def test_sarif_and_json_state_the_same_reasons(run: Run, monkeypatch: pytest.MonkeyPatch) -> None:
    _break_rule_module(monkeypatch, "LEX004", "it broke")
    _break_measurement(monkeypatch)
    argv = (KITCHEN, "--measurements", "--fail-on", "never")
    from_json = _json(run(*argv, "--format", "json")[1])["exit"]
    from_sarif = _json(run(*argv, "--format", "sarif")[1])["runs"][0]["invocations"][0]["properties"]["ontolintExit"]
    assert from_json == from_sarif


def test_text_lists_the_reasons_after_the_findings(run: Run, monkeypatch: pytest.MonkeyPatch) -> None:
    _break_rule_module(monkeypatch, "LEX004", "it broke")
    code, out, err = run(KITCHEN, "--fail-on", "never")
    assert code == 2
    assert "Exit status 2: " in out
    assert "  - rule_failed: LEX004 for kitchen_sink.ttl: ValueError: it broke" in out
    assert "TOOL001: rule LEX004 failed for kitchen_sink.ttl: ValueError: it broke" in err  # stderr is unchanged


def test_the_text_of_a_run_that_exits_0_or_1_is_unchanged(run: Run) -> None:
    for fail_on in ("never", "error"):
        _, out, _ = run(KITCHEN, "--fail-on", fail_on)
        assert "Exit status" not in out


def test_every_stderr_tool_line_has_a_reason(run: Run, monkeypatch: pytest.MonkeyPatch) -> None:
    _break_rule_module(monkeypatch, "LEX004", "it broke")
    _break_measurement(monkeypatch)
    _, out, err = run(KITCHEN, "--measurements", "--format", "json", "--fail-on", "never")
    tool_lines = [line for line in err.splitlines() if line.startswith("TOOL001:")]
    assert len(tool_lines) == len(_reasons(_json(out)))


def test_a_message_never_carries_a_credential(run: Run, monkeypatch: pytest.MonkeyPatch) -> None:
    _break_rule_module(monkeypatch, "LEX004", f"cannot read {SECRET}")
    _break_measurement(monkeypatch)
    for fmt in ("json", "sarif", "text", "markdown"):
        _, out, err = run(KITCHEN, "--measurements", "--format", fmt, "--fail-on", "never")
        assert "hunter2" not in out + err, fmt
    assert "hunter2" not in repr(report_reasons(_report_with(failed=("m", f"x {SECRET}"))))


def _report_with(*, failed: tuple[str, str]) -> RunReport:
    file = FileReport("a.ttl", "a.ttl", (), failed_measurements=(failed,))
    return RunReport((file,), ())


def test_reasons_are_one_line_each() -> None:
    reasons = report_reasons(_report_with(failed=("m", "first\nsecond\x1b[31m")))
    assert [r.message for r in reasons] == ["first\\nsecond\\x1b[31m"]


def test_the_exit_object_validates_against_the_schema(run: Run, monkeypatch: pytest.MonkeyPatch) -> None:
    _break_rule_module(monkeypatch, "LEX004", "it broke")
    _break_measurement(monkeypatch)
    document = _json(run(KITCHEN, "--measurements", "--format", "json", "--fail-on", "never")[1])
    validator = validator_for(SCHEMA)(SCHEMA)
    assert not list(validator.iter_errors(document))
    broken = {**document, "exit": {"code": "2", "reasons": []}}
    assert list(validator.iter_errors(broken))


def test_report_reasons_follow_run_exit_code() -> None:
    """The reasons and the exit code are decided by the same two sources, so they cannot disagree."""
    clean = RunReport((FileReport("a.ttl", "a.ttl", ()),), ())
    assert report_reasons(clean) == ()
    assert run_exit_code(clean, "error") == 0
    broken = _report_with(failed=("m", "why"))
    assert run_exit_code(broken, "error") == 2
    assert [r.kind for r in report_reasons(broken)] == ["measurement_failed"]
    assert "exit" in to_json(broken)
    assert "ontolintExit" in to_sarif_report(broken)["runs"][0]["invocations"][0]["properties"]
    assert "Exit status 2" in render_report(broken, "text")


def test_unsupported_is_never_a_timeout_and_a_timeout_never_unsupported() -> None:
    from ontolint.exit_reasons import execution_reason
    from ontolint.models import RuleExecution

    timed_out = RuleExecution("SHQ010", ExecutionStatus.FAILED, "ValidationTimeout: SHACL validation did not finish")
    gone = RuleExecution("SHQ010", ExecutionStatus.FAILED, "WorkerGone: the validation worker exited")
    unsupported = RuleExecution("SEM001", ExecutionStatus.UNSUPPORTED, "the docker executable was not found")
    assert execution_reason("a.ttl", timed_out).kind == "rule_timeout"
    assert execution_reason("a.ttl", gone).kind == "rule_failed"
    assert execution_reason("a.ttl", unsupported).kind == "rule_unsupported"


# --- a run that exited 2 before it had a report: one fixture per cause ---------------------------------------------


def test_an_unparseable_file(tmp_path: Path, run: Run, refusals: list[ExitReason]) -> None:
    bad = tmp_path / "bad.ttl"
    bad.write_text("this is not turtle {", encoding="utf-8")
    code, out, err = run(str(bad))
    assert (code, out) == (2, "")
    assert err.startswith("INPUT001: RDF input parsing failed")
    assert [r.kind for r in refusals] == ["input_unparseable"]


def test_a_policy_rejected_as_gov020(tmp_path: Path, run: Run, refusals: list[ExitReason]) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"version": 99}), encoding="utf-8")
    code, out, err = run("--config", str(policy), KITCHEN)
    assert (code, out) == (2, "")
    assert err.startswith("GOV020: policy file rejected:")
    assert [r.kind for r in refusals] == ["policy_rejected"]


def test_an_unknown_selector_is_a_configuration_failure(run: Run, refusals: list[ExitReason]) -> None:
    code, _, err = run("--select", "NOPE999", KITCHEN)
    assert code == 2
    assert err.startswith("TOOL001: configuration failed:")
    assert [r.kind for r in refusals] == ["config_invalid"]


def test_an_unknown_rule_to_explain(run: Run, refusals: list[ExitReason]) -> None:
    code, out, err = run("--explain", "NOPE999")
    assert (code, out) == (2, "")
    assert err.startswith("TOOL001: unknown rule 'NOPE999'")
    assert [r.kind for r in refusals] == ["unknown_rule"]


def test_a_missing_shapes_file(run: Run, refusals: list[ExitReason]) -> None:
    code, _, err = run("--shapes", "/nonexistent/shapes.ttl", KITCHEN)
    assert code == 2
    assert err
    assert [r.kind for r in refusals] == ["input_rejected"]


def test_an_unreadable_quality_baseline(run: Run, refusals: list[ExitReason]) -> None:
    code, _, err = run("--quality-baseline", "/nonexistent/quality.json", KITCHEN)
    assert code == 2
    assert err.startswith("TOOL001:")
    assert [r.kind for r in refusals] == ["snapshot_unreadable"]


def test_a_snapshot_that_cannot_be_written(tmp_path: Path, run: Run, refusals: list[ExitReason]) -> None:
    target = tmp_path / "missing" / "snapshot.json"
    code, _, err = run("--write-quality-snapshot", str(target), QUALITY)
    assert code == 2
    assert err.startswith("TOOL001:")
    assert [r.kind for r in refusals] == ["output_failed"]


def test_a_report_that_cannot_be_written(tmp_path: Path, run: Run, refusals: list[ExitReason]) -> None:
    target = tmp_path / "missing" / "report.json"
    code, _, err = run("--output", str(target), "--format", "json", KITCHEN, "--fail-on", "never")
    assert code == 2
    assert err.startswith("TOOL001:")
    assert [r.kind for r in refusals] == ["output_failed"]


def test_a_usage_error(capsys: pytest.CaptureFixture[str], refusals: list[ExitReason]) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--no-such-option", KITCHEN])
    assert raised.value.code == 2
    err = capsys.readouterr().err
    assert "error: unrecognized arguments: --no-such-option" in err
    assert err.startswith("usage: ")
    assert [r.kind for r in refusals] == ["usage"]


def test_a_usage_problem_found_after_parsing(run: Run, refusals: list[ExitReason]) -> None:
    with pytest.raises(SystemExit) as raised:
        run("--write-dqv", "/tmp/x.ttl", KITCHEN)
    assert raised.value.code == 2
    assert [r.kind for r in refusals] == ["usage"]


def test_an_internal_error(monkeypatch: pytest.MonkeyPatch, run: Run, refusals: list[ExitReason]) -> None:
    def boom(_argv: object) -> int:
        raise RuntimeError("a bug")

    monkeypatch.setattr(cli, "_main", boom)
    code, _, err = run(KITCHEN)
    assert code == 2
    assert "RuntimeError: a bug" in err  # the traceback, as before
    assert [r.kind for r in refusals] == ["internal_error"]


def test_a_refusal_prints_its_message_through_the_redaction(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.stderr", cli.RedactingStream(__import__("sys").stderr))
    assert exit_reasons.refuse(ExitReason("input_rejected", f"INPUT001: cannot read {SECRET}")) == 2
    assert "hunter2" not in capsys.readouterr().err


def test_a_run_that_exits_0_or_1_makes_no_refusal(run: Run, refusals: list[ExitReason]) -> None:
    assert run(KITCHEN, "--fail-on", "never")[0] == 0
    assert run(KITCHEN)[0] == 1
    assert refusals == []


def test_a_refusal_with_an_unknown_kind_is_a_bug() -> None:
    with pytest.raises(ValueError, match="unknown exit reason kind"):
        ExitReason("not_a_kind", "x")


# --- every exit-2 path of cli.py goes through the helper ---------------------------------------------------------


def _calls(tree: ast.AST, name: str) -> Iterator[ast.Call]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name:
            yield node


def _is_exit_2(node: ast.expr | None) -> bool:
    return (isinstance(node, ast.Constant) and node.value == 2 and not isinstance(node.value, bool)) or (
        isinstance(node, ast.Name) and node.id in {"TOOL_FAILURE_EXIT", "TOOL_FAILURE"}
    )


def test_cli_leaves_with_2_only_through_refuse() -> None:
    """The enumeration the issue asks for: no ``return 2``, no ``code = 2``, no ``SystemExit(2)``, no ``parser.error``."""
    tree = ast.parse(CLI_SOURCE.read_text(encoding="utf-8"))
    bare: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Return) and _is_exit_2(node.value):
            bare.append(node.lineno)
        if isinstance(node, ast.Assign) and _is_exit_2(node.value):
            bare.append(node.lineno)
        if isinstance(node, ast.IfExp) and (_is_exit_2(node.body) or _is_exit_2(node.orelse)):
            bare.append(node.lineno)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"error", "exit"}:
            bare.append(node.lineno)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "SystemExit":
            bare.append(node.lineno)
    assert bare == [], f"exit 2 without a reason at cli.py line(s) {bare}: go through refuse(ExitReason(...))"


def test_every_refuse_call_names_a_known_kind() -> None:
    tree = ast.parse(CLI_SOURCE.read_text(encoding="utf-8"))
    calls = list(_calls(tree, "refuse"))
    assert len(calls) >= 12  # every exit-2 path found in the survey of #175
    kinds: set[str] = set()
    for call in calls:
        assert call.args, f"line {call.lineno}: refuse() takes a reason"
        reason = call.args[0]
        assert isinstance(reason, ast.Call), f"line {call.lineno}: build the ExitReason in the call"
        assert isinstance(reason.func, ast.Name) and reason.func.id == "ExitReason"
        first = reason.args[0]
        assert isinstance(first, ast.Constant), f"line {call.lineno}: the kind is a literal"
        kinds.add(first.value)
    assert kinds <= KINDS
    # Each kind the CLI refuses with is exercised above; the rest come from reports.
    assert kinds == KINDS - {"rule_failed", "rule_timeout", "rule_unsupported", "budget_unmeasured", "measurement_failed"}

