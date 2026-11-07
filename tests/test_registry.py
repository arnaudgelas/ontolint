"""Registry, catalogue and execution-status contracts."""

from __future__ import annotations

import csv
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF
from rule_cases import load_cases
from rule_harness import graph as rule_graph

from ontolint import Linter, engine
from ontolint.catalogue import BACKEND_IDS, implemented_rows, load_catalogue, planned_rows
from ontolint.models import (
    CatalogueStatus,
    ExecutionStatus,
    Requirement,
    RuleBackend,
    RuleExecution,
    RuleScope,
    RuleSpec,
    Severity,
)
from ontolint.ontolint import FIXES, SEVERITY
from ontolint.policy import Policy
from ontolint.profiles import is_opt_in
from ontolint.reporting import render_executions, summarise_executions
from ontolint.rules.registry import RuleRegistry, UnknownSelectorError, default_registry
from ontolint.rules.specs import RULE_SPECS

ROOT = Path(__file__).parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://example.test/onto#"
CATALOGUE_ROW_COUNT = 307
IMPLEMENTED_COUNT = len(implemented_rows())  # derived: rule groups flip catalogue rows independently
EXECUTED, SKIPPED, UNSUPPORTED, FAILED = (
    ExecutionStatus.EXECUTED,
    ExecutionStatus.SKIPPED,
    ExecutionStatus.UNSUPPORTED,
    ExecutionStatus.FAILED,
)


def _kitchen(*, shapes: bool = False, **kwargs: Any) -> Linter:
    graph = Graph().parse(FIXTURES / "kitchen_sink.ttl")
    shapes_graph = Graph().parse(FIXTURES / "kitchen_shapes.ttl") if shapes else None
    return Linter(graph, shapes_graph, base=BASE, **kwargs)


def _statuses(result: Any) -> dict[str, ExecutionStatus]:
    return {x.rule_id: x.status for x in result.executions}


# --- catalogue vs registry -------------------------------------------------------------------


def test_catalogue_is_complete_typed_and_has_unique_ids() -> None:
    rows = load_catalogue()
    assert len(rows) == CATALOGUE_ROW_COUNT
    assert len({row.rule_id for row in rows}) == CATALOGUE_ROW_COUNT
    assert len(implemented_rows()) == IMPLEMENTED_COUNT
    assert len(planned_rows()) == CATALOGUE_ROW_COUNT - IMPLEMENTED_COUNT
    assert {row.status for row in planned_rows()} == {CatalogueStatus.PROPOSED}
    assert all(row.backend and row.test_requirement for row in rows)


def test_packaged_catalogue_is_identical_to_the_canonical_data_file() -> None:
    packaged = ROOT / "src" / "ontolint" / "data" / "rule_catalogue.csv"
    assert packaged.read_bytes() == (ROOT / "data" / "rule_catalogue.csv").read_bytes()
    with packaged.open(encoding="utf-8", newline="") as file:
        assert [row["rule_id"] for row in csv.DictReader(file)] == [row.rule_id for row in load_catalogue()]


def test_every_implemented_catalogue_row_has_exactly_one_matching_spec() -> None:
    registry = default_registry()
    specs = [spec.rule_id for spec in RULE_SPECS]
    assert len(specs) == len(set(specs)) == len(registry) == IMPLEMENTED_COUNT
    for row in implemented_rows():
        assert specs.count(row.rule_id) == 1
        spec = registry.get(row.rule_id)
        assert (spec.family, spec.category, spec.backend) == (row.family, row.category, row.backend_id)
        assert spec.title == row.title
        assert "implemented diagnostic" not in spec.title


def test_no_registry_rule_is_missing_from_or_unimplemented_in_the_catalogue() -> None:
    status = {row.rule_id: row.status for row in load_catalogue()}
    assert {spec.rule_id for spec in RULE_SPECS} == {
        rid for rid, s in status.items() if s is CatalogueStatus.IMPLEMENTED
    }
    assert all(row.backend_id is None for row in planned_rows() if row.backend not in BACKEND_IDS)


def test_severity_and_fix_views_derive_from_the_registry() -> None:
    assert {spec.rule_id: spec.severity.value for spec in RULE_SPECS} == SEVERITY
    assert {spec.rule_id: spec.suggestion for spec in RULE_SPECS} == FIXES
    assert all(spec.suggestion and spec.severity in Severity for spec in RULE_SPECS)


def test_requirements_follow_backends() -> None:
    registry = default_registry()
    assert registry.get("SHACL001").requires is Requirement.SHAPES
    assert registry.get("SEM001").requires is Requirement.OWL_PROFILE
    assert {s.rule_id for s in RULE_SPECS if s.requires is Requirement.SHAPES} == {
        "SHACL001",
        *(s.rule_id for s in RULE_SPECS if s.family == "SHQ"),
    }
    assert {"SHQ001", "SHQ006", "SHQ007", "SHQ027"} <= {s.rule_id for s in RULE_SPECS if s.family == "SHQ"}
    assert {s.scope for s in RULE_SPECS if s.backend is RuleBackend.CLI} == {RuleScope.INPUT, RuleScope.TOOL}


# --- reachability ----------------------------------------------------------------------------

REACH_CASES: tuple[dict[str, Any], ...] = (
    {},
    {"languages": ("en", "fr"), "depth_limit": 2, "inheritance_limit": 1, "soup_limit": 1},
)


def _emitted_by_module() -> dict[str, set[str]]:
    emitted: dict[str, set[str]] = {module: set() for module in engine.FAMILY_RUNNERS}
    for kwargs in REACH_CASES:
        for module, runner in engine.FAMILY_RUNNERS.items():
            linter = _kitchen(shapes=True, **kwargs)
            runner(linter.rule_context)
            emitted[module] |= {f.rule for f in linter.rule_context.findings}
    odd = Graph()
    odd.add((URIRef("relative-ontology.rdf"), RDF.type, OWL.Ontology))
    odd.add((URIRef("https://example.test/with space"), RDF.type, OWL.Class))
    odd.add((URIRef("https://example.test/a/Same"), RDF.type, OWL.Class))
    odd.add((URIRef("https://example.test/b/Same"), RDF.type, OWL.Class))
    for graph in (Graph(), odd):  # missing ontology header; malformed IRI and local-name collision
        for module, runner in engine.FAMILY_RUNNERS.items():
            linter = Linter(graph)
            runner(linter.rule_context)
            emitted[module] |= {f.rule for f in linter.rule_context.findings}
    # Rules whose trigger the shared fixtures do not contain are reached through their own positive
    # rule cases (tests/rule_cases); the module still has to be the only one that emits them.
    cases = load_cases()
    for spec in RULE_SPECS:
        if spec.backend is not RuleBackend.RDFLIB or spec.rule_id not in cases:
            continue
        for case in cases[spec.rule_id].positive:
            data = case.build() if case.build else rule_graph(case.turtle)
            shapes = rule_graph(case.shapes) if case.shapes is not None else None
            for module, runner in engine.FAMILY_RUNNERS.items():
                linter = Linter(data, shapes, **case.options)
                runner(linter.rule_context)
                emitted[module] |= {f.rule for f in linter.rule_context.findings if f.rule == spec.rule_id}
    return emitted


def test_every_graph_rule_is_emitted_by_its_declared_module_only() -> None:
    emitted = _emitted_by_module()
    declared: dict[str, set[str]] = {module: set() for module in engine.FAMILY_RUNNERS}
    for spec in RULE_SPECS:
        if spec.backend is RuleBackend.RDFLIB:
            declared[spec.module].add(spec.rule_id)
    assert emitted == declared  # every graph rule is reachable from the fixtures or its own positive case
    assert {s.module for s in RULE_SPECS if s.backend is not RuleBackend.RDFLIB} == {""}


# --- registry behaviour ----------------------------------------------------------------------


def _spec(rule_id: str, family: str) -> RuleSpec:
    return RuleSpec(
        rule_id, family, "t", Severity.INFO, "fix", "heuristic", RuleBackend.RDFLIB, RuleScope.TERM, "lexical"
    )


def test_registry_rejects_duplicates_and_selects_by_id_or_family() -> None:
    registry = RuleRegistry([_spec("LEX002", "LEX"), _spec("LEX001", "LEX"), _spec("OWL001", "OWL")])
    with pytest.raises(ValueError, match="duplicate rule identifier: LEX001"):
        registry.register(_spec("LEX001", "LEX"))
    assert [s.rule_id for s in registry.select(["lex"])] == ["LEX001", "LEX002"]
    assert [s.rule_id for s in registry.select(["owl001", "LEX002"])] == ["LEX002", "OWL001"]
    assert "OWL001" in registry and "OWL999" not in registry
    assert len(registry.select([])) == len(registry)


def test_unknown_selectors_are_rejected_not_ignored() -> None:
    registry = default_registry()
    with pytest.raises(UnknownSelectorError, match="LEX999, NOPE") as info:
        registry.select(["LEX001", "nope", "LEX999"])
    assert info.value.selectors == ("LEX999", "NOPE")
    with pytest.raises(KeyError):
        registry.get("LEX999")
    with pytest.raises(UnknownSelectorError):
        _kitchen().execute(["LEX999"])


# --- execution status ------------------------------------------------------------------------


def test_run_records_exactly_one_execution_per_rule_and_matches_linter_run() -> None:
    result = _kitchen(shapes=True).execute()
    expected = _kitchen(shapes=True).run()
    default_ids = sorted(rule_id for rule_id in SEVERITY if not is_opt_in(default_registry().get(rule_id).family))
    assert [x.rule_id for x in result.executions] == default_ids
    graph_findings = tuple(f for f in result.findings if f.rule != "SHACL001")
    assert graph_findings == tuple(expected)
    statuses = _statuses(result)
    assert statuses["SHACL001"] is EXECUTED
    assert statuses["SHQ001"] is EXECUTED and statuses["LEX001"] is EXECUTED
    assert statuses["SEM001"] is SKIPPED
    assert statuses["INPUT001"] is statuses["TOOL001"] is SKIPPED
    assert all(x.detail for x in result.executions if x.status is not EXECUTED)


def test_missing_shapes_skips_shape_rules_with_a_reason_instead_of_passing() -> None:
    result = _kitchen().execute()
    skipped = {x.rule_id: x.detail for x in result.with_status(SKIPPED)}
    for rule_id in ("SHACL001", *(f"SHQ00{i}" for i in range(1, 7))):
        assert "shapes" in skipped[rule_id]
    assert not any(f.rule.startswith(("SHQ", "SHACL")) for f in result.findings)
    assert "no SHACL shapes graph" in render_executions(result.executions)


def test_robot_is_skipped_unsupported_failed_or_executed_depending_on_availability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ontology = tmp_path / "o.ttl"
    ontology.write_text("", encoding="utf-8")
    linter = _kitchen()
    request = engine.RobotRequest(ontology, "DL")

    assert "not requested" in linter.execute(["SEM001"]).executions[0].detail

    monkeypatch.setattr(engine.shutil, "which", lambda _name: None)
    unsupported = linter.execute(["SEM001"], robot=request)
    assert _statuses(unsupported) == {"SEM001": UNSUPPORTED}
    assert "docker" in unsupported.executions[0].detail and not unsupported.findings

    monkeypatch.setattr(engine.shutil, "which", lambda _name: "/usr/bin/docker")
    missing = linter.execute(["SEM001"], robot=replace(request, ontology=tmp_path / "absent.ttl"))
    assert _statuses(missing) == {"SEM001": FAILED}
    assert "FileNotFoundError" in missing.executions[0].detail

    def fake_run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="bad profile")

    monkeypatch.setattr("ontolint.adapters.robot.subprocess.run", fake_run)
    executed = linter.execute(["SEM001"], robot=request)
    assert _statuses(executed) == {"SEM001": EXECUTED}
    assert [f.rule for f in executed.findings] == ["SEM001"]


def test_missing_pyshacl_is_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(engine, "find_spec", lambda _name: None)
    result = _kitchen(shapes=True).execute(["SHACL001"])
    assert _statuses(result) == {"SHACL001": UNSUPPORTED}
    assert "pySHACL" in result.executions[0].detail and not result.findings


def test_failing_shacl_adapter_is_a_failed_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_: Any) -> None:
        raise RuntimeError("shacl exploded")

    monkeypatch.setattr(engine, "shacl_issues", boom)
    result = _kitchen(shapes=True).execute(["SHACL001"])
    assert _statuses(result) == {"SHACL001": FAILED}
    assert result.executions[0].detail == "RuntimeError: shacl exploded"


def test_rule_module_that_raises_marks_its_rules_failed_without_crashing(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_ctx: object) -> None:
        raise ValueError("lexical exploded")

    monkeypatch.setitem(engine.FAMILY_RUNNERS, "lexical", boom)
    result = _kitchen().execute(["LEX", "ONT"])
    statuses = _statuses(result)
    lexical_ids = {s.rule_id for s in RULE_SPECS if s.module == "lexical"}
    assert {s for r, s in statuses.items() if r in lexical_ids} == {FAILED}
    assert {s for r, s in statuses.items() if r.startswith("LEX") and r not in lexical_ids} == {EXECUTED}
    assert {s for r, s in statuses.items() if r.startswith("ONT")} == {EXECUTED}
    assert all(x.detail == "ValueError: lexical exploded" for x in result.with_status(FAILED))
    assert result.findings and not any(f.rule in lexical_ids for f in result.findings)
    expected_failed = len(lexical_ids)
    expected_executed = len(statuses) - expected_failed
    assert summarise_executions(result.executions) == {
        "executed": expected_executed,
        "skipped": 0,
        "unsupported": 0,
        "failed": expected_failed,
    }


def test_selection_limits_execution_and_findings_and_policy_ignores_are_skipped() -> None:
    linter = _kitchen()
    by_id = linter.execute(["LEX001", "ont003"])
    assert [x.rule_id for x in by_id.executions] == ["LEX001", "ONT003"]
    assert {f.rule for f in by_id.findings} <= {"LEX001", "ONT003"}

    graph = Graph().parse(FIXTURES / "kitchen_sink.ttl")
    ctx = engine.build_context(graph, None, Policy(base=BASE, ignored_rules=frozenset({"LEX001"})))
    result = engine.execute(ctx, ["LEX"])
    assert _statuses(result)["LEX001"] is SKIPPED and result.executions[0].detail == "ignored by policy"
    assert "LEX001" not in {f.rule for f in result.findings}
    assert _statuses(result)["LEX002"] is EXECUTED


def test_execution_report_helpers() -> None:
    executions = [
        RuleExecution("A001", EXECUTED),
        RuleExecution("A002", SKIPPED, "because"),
        RuleExecution("A003", UNSUPPORTED, "no tool"),
    ]
    assert summarise_executions(executions) == {"executed": 1, "skipped": 1, "unsupported": 1, "failed": 0}
    text = render_executions(executions)
    assert text.splitlines()[0] == "Rule execution: 1 executed, 1 skipped, 1 unsupported, 0 failed"
    assert "[SKIPPED    ] A002: because" in text and "A001" not in text


def test_lex007_message_lists_styles_in_sorted_order() -> None:
    message = next(f.message for f in _kitchen().run() if f.rule == "LEX007")
    assert message == "Mixed identifier styles: {'camel': 19, 'hyphen': 1, 'other': 30, 'underscore': 1}."
