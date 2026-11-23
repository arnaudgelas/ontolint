"""Catalogue identity and per-rule counts in the JSON and SARIF reports (issue #173).

``catalogue`` says which rule set produced a report (ontolint version, a sha256 of the canonical catalogue, the
number of rows); ``rule_counts`` says, for every implemented rule, what happened to it in this run and how many
findings it gave, so a consumer needs no reparsing. Both are additive (``docs/report-compatibility.md``): the schema
version stays 1.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import re
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from jsonschema.validators import validator_for
from test_differential import CLI_CASES, FIXTURES, _fake_robot

from ontolint._version import package_version
from ontolint.catalogue import canonical_catalogue, catalogue_sha256, load_catalogue
from ontolint.cli import main
from ontolint.models import ExecutionStatus, Finding, RuleExecution
from ontolint.reporting import FileReport, RunReport, to_json, to_sarif_report
from ontolint.rules.registry import default_registry

ROOT = Path(__file__).parent.parent
REPORT_SCHEMA = json.loads((ROOT / "src" / "ontolint" / "schemas" / "lint-report.v1.schema.json").read_text("utf-8"))
SARIF_SCHEMA = json.loads((Path(__file__).parent / "schemas" / "sarif-schema-2.1.0.json").read_text("utf-8"))
IMPLEMENTED = sorted(spec.rule_id for spec in default_registry().all())
MINIMUM_ROWS = 300
STATUSES = {"executed", "skipped", "unsupported", "failed", "not_selected"}


def _json(monkeypatch: pytest.MonkeyPatch, *args: str, source: str = "kitchen_sink.ttl") -> dict[str, Any]:
    monkeypatch.chdir(FIXTURES)
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        main([source, "--format", "json", "--fail-on", "never", *args])
    return json.loads(out.getvalue())


def _counts(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entry["rule"]: entry for entry in document["rule_counts"]}


# --- the catalogue object -----------------------------------------------------------------------------------------


def test_the_report_names_the_catalogue_that_produced_it(monkeypatch: pytest.MonkeyPatch) -> None:
    document = _json(monkeypatch)
    assert document["schema_version"] == 1
    catalogue = document["catalogue"]
    assert catalogue == {
        "ontolint_version": package_version(),
        "sha256": catalogue_sha256(),
        "rule_count": len(load_catalogue()),
    }
    assert re.fullmatch(r"[0-9a-f]{64}", catalogue["sha256"])


def _rows() -> list[dict[str, str]]:
    return [
        {"rule_id": "B001", "family": "B", "title": "Second", "status": "implemented", "category": "x", "backend": "y"},
        {"rule_id": "A001", "family": "A", "title": "First", "status": "proposed", "category": "x", "backend": "y"},
    ]


def test_the_catalogue_hash_does_not_depend_on_the_order_of_the_rows() -> None:
    rows = _rows()
    assert catalogue_sha256(rows) == catalogue_sha256(list(reversed(rows)))
    assert canonical_catalogue(rows).decode("utf-8").splitlines()[0].startswith('["A001"')


@pytest.mark.parametrize("column", ["rule_id", "family", "title", "status", "category", "backend"])
def test_the_catalogue_hash_changes_when_any_field_of_a_row_changes(column: str) -> None:
    rows = _rows()
    changed = copy.deepcopy(rows)
    changed[0][column] += "!"
    assert catalogue_sha256(changed) != catalogue_sha256(rows)


def test_the_catalogue_hash_changes_when_a_row_is_added_or_removed() -> None:
    rows = _rows()
    assert catalogue_sha256(rows[:1]) != catalogue_sha256(rows)
    assert catalogue_sha256(rows + [{**rows[0], "rule_id": "C001"}]) != catalogue_sha256(rows)


def test_the_hash_of_the_packaged_catalogue_is_the_same_on_every_call_and_a_real_digest() -> None:
    assert catalogue_sha256() == catalogue_sha256()
    assert len(load_catalogue()) > MINIMUM_ROWS


# --- rule_counts --------------------------------------------------------------------------------------------------


def test_there_is_one_count_per_implemented_rule_sorted_by_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    document = _json(monkeypatch)
    assert [entry["rule"] for entry in document["rule_counts"]] == IMPLEMENTED
    for entry in document["rule_counts"]:
        assert set(entry) >= {"rule", "status", "findings", "baselined"}
        assert entry["status"] in STATUSES
        assert entry["findings"] >= 0 and entry["baselined"] >= 0


def test_the_counts_add_up_to_the_findings(monkeypatch: pytest.MonkeyPatch) -> None:
    document = _json(monkeypatch)
    assert sum(entry["findings"] for entry in document["rule_counts"]) == len(document["findings"])
    by_rule: dict[str, int] = {}
    for finding in document["findings"]:
        by_rule[finding["rule"]] = by_rule.get(finding["rule"], 0) + 1
    assert {rule: e["findings"] for rule, e in _counts(document).items() if e["findings"]} == by_rule
    assert sum(entry["baselined"] for entry in document["rule_counts"]) == 0  # no baseline was read


def test_baselined_findings_are_counted_apart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(FIXTURES)
    baseline = tmp_path / "baseline.json"
    main(["kitchen_sink.ttl", "--write-baseline", str(baseline), "--fail-on", "never"])
    whole = _json(monkeypatch)
    accepted = _json(monkeypatch, "--baseline", str(baseline))
    assert accepted["findings"] == []
    assert sum(entry["findings"] for entry in accepted["rule_counts"]) == 0
    assert sum(entry["baselined"] for entry in accepted["rule_counts"]) == len(whole["findings"])
    assert {r: e["baselined"] for r, e in _counts(accepted).items() if e["baselined"]} == {
        r: e["findings"] for r, e in _counts(whole).items() if e["findings"]
    }


def test_a_rule_the_run_did_not_select_is_not_selected_never_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    only = _counts(_json(monkeypatch, "--select", "OWL001,OWL002"))
    assert only["OWL001"]["status"] == "executed" and only["OWL002"]["status"] == "executed"
    assert only["LEX001"] == {"rule": "LEX001", "status": "not_selected", "findings": 0, "baselined": 0}
    ignored = _counts(_json(monkeypatch, "--ignore", "OWL001"))
    assert ignored["OWL001"]["status"] == "not_selected" and ignored["OWL002"]["status"] == "executed"
    default = _counts(_json(monkeypatch))
    assert default["OBO001"]["status"] == "not_selected"  # an opt-in family
    assert _counts(_json(monkeypatch, "--profile", "obo"))["OBO001"]["status"] == "executed"


def test_a_selected_rule_with_no_finding_is_executed_with_zero_findings(monkeypatch: pytest.MonkeyPatch) -> None:
    counts = _counts(_json(monkeypatch, "--select", "OWL001", source="clean.ttl"))
    assert counts["OWL001"] == {"rule": "OWL001", "status": "executed", "findings": 0, "baselined": 0}


def test_a_failed_rule_keeps_its_status_and_its_findings_are_still_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    document = _json(
        monkeypatch, "--shapes", "reports/inputs/illformed_shapes.ttl", "--select", "SHACL001", source="clean.ttl"
    )
    assert _counts(document)["SHACL001"]["status"] == "failed"
    assert document["execution_summary"]["failed"] == 1


def test_an_unsupported_rule_keeps_its_status(monkeypatch: pytest.MonkeyPatch) -> None:
    argv, robot = CLI_CASES["json_robot_unsupported"]
    monkeypatch.setattr(
        "ontolint.engine.shutil.which", lambda _: "docker" if robot is not None and robot >= 0 else None
    )
    monkeypatch.setattr("ontolint.ontolint.subprocess.run", _fake_robot(max(robot or 0, 0)))
    monkeypatch.chdir(FIXTURES)
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        main(argv)
    document = json.loads(out.getvalue())
    unsupported = {rule for rule, e in _counts(document).items() if e["status"] == "unsupported"}
    assert unsupported
    assert unsupported == {e["rule"] for e in document["files"][0]["executions"] if e["status"] == "unsupported"}


def test_a_rule_that_failed_on_one_of_several_files_is_failed_for_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """The status of a rule over several files is the worst one: failed, unsupported, skipped, executed."""
    ok = FileReport("a.ttl", "a.ttl", (), (RuleExecution("ONT001", ExecutionStatus.EXECUTED),))
    bad = FileReport("b.ttl", "b.ttl", (), (RuleExecution("ONT001", ExecutionStatus.FAILED, "boom"),))
    spec = default_registry().get("ONT001")
    for files, expected in (((ok, bad), "failed"), ((bad, ok), "failed"), ((ok, ok), "executed")):
        assert _counts(to_json(RunReport(files, (spec,))))["ONT001"]["status"] == expected


# --- the same input gives the same counts, whatever the order -----------------------------------------------------


def test_the_same_input_gives_the_same_catalogue_and_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    first, second = _json(monkeypatch), _json(monkeypatch)
    assert first["catalogue"] == second["catalogue"] and first["rule_counts"] == second["rule_counts"]


def test_the_counts_do_not_depend_on_the_order_of_the_rules_or_the_executions() -> None:
    registry = default_registry()
    specs = tuple(registry.get(rule) for rule in ("ONT001", "OWL001", "LEX001"))
    finding = Finding("OWL001", "warning", "https://example.test/A", "m", "s")
    executions = tuple(RuleExecution(spec.rule_id, ExecutionStatus.EXECUTED) for spec in specs)
    report = RunReport((FileReport("a.ttl", "a.ttl", (finding,), executions),), specs)
    shuffled = RunReport((FileReport("a.ttl", "a.ttl", (finding,), executions[::-1]),), specs[::-1])
    assert to_json(report)["rule_counts"] == to_json(shuffled)["rule_counts"]
    assert to_json(report)["catalogue"] == to_json(shuffled)["catalogue"]


def test_a_finding_of_a_rule_that_has_no_execution_record_still_counts_as_executed() -> None:
    finding = Finding("OWL001", "warning", "https://example.test/A", "m", "s")
    counts = _counts(to_json(RunReport((FileReport("a.ttl", "a.ttl", (finding,)),))))
    assert counts["OWL001"]["status"] == "executed" and counts["OWL001"]["findings"] == 1
    assert sum(e["findings"] for e in counts.values()) == 1


# --- the schema and SARIF -----------------------------------------------------------------------------------------


def test_the_report_with_the_new_keys_validates_against_the_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    validator = validator_for(REPORT_SCHEMA)(REPORT_SCHEMA)
    validator.validate(_json(monkeypatch))
    document = _json(monkeypatch)
    document["rule_counts"][0]["status"] = "crashed"
    assert not validator.is_valid(document)
    document = _json(monkeypatch)
    del document["catalogue"]["sha256"]
    assert not validator.is_valid(document)


def _sarif(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.chdir(FIXTURES)
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        main(["kitchen_sink.ttl", "--format", "sarif", "--fail-on", "never"])
    return json.loads(out.getvalue())


def test_the_sarif_run_carries_the_same_catalogue_and_counts_in_its_properties(monkeypatch: pytest.MonkeyPatch) -> None:
    run = _sarif(monkeypatch)["runs"][0]
    document = _json(monkeypatch)
    assert run["properties"]["ontolintCatalogue"] == document["catalogue"]
    assert run["properties"]["ontolintRuleCounts"] == document["rule_counts"]


def test_the_sarif_report_with_the_new_properties_still_validates(monkeypatch: pytest.MonkeyPatch) -> None:
    validate: Callable[[Any], None] = validator_for(SARIF_SCHEMA)(SARIF_SCHEMA).validate
    validate(_sarif(monkeypatch))
    report = RunReport((FileReport("a.ttl", "a.ttl", ()),))
    validate(to_sarif_report(replace(report)))
