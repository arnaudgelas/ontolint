"""Exact message, ordering, limits and metadata of SEC007 (the ``owl:imports`` note)."""

# ruff: noqa: PLR2004

from __future__ import annotations

from rdflib import Graph
from rule_harness import graph

from ontolint import Linter
from ontolint.models import ExecutionStatus, Finding, RuleBackend, RuleScope, Severity
from ontolint.rules import imports_note

HEAD = "<https://example.test/onto> a owl:Ontology"


def run(data: Graph) -> list[Finding]:
    result = Linter(data, None).execute(["SEC007"])
    assert {x.status for x in result.executions} == {ExecutionStatus.EXECUTED}
    return list(result.findings)


def test_spec_is_an_info_rdflib_ontology_rule() -> None:
    (spec,) = imports_note.SPECS
    assert (spec.rule_id, spec.family, spec.title) == ("SEC007", "SEC", "owl:imports not followed")
    assert (spec.severity, spec.backend, spec.scope) == (Severity.INFO, RuleBackend.RDFLIB, RuleScope.ONTOLOGY)
    assert spec.module == "imports_note"
    assert spec.category == "deterministic"
    assert "--ignore SEC007" in spec.suggestion


def test_single_import_message_is_singular_and_exact() -> None:
    (finding,) = run(graph(f"{HEAD} ; owl:imports <https://example.test/other> ."))
    assert finding.focus == "(imports)"
    assert finding.message == "1 owl:import was not followed: https://example.test/other."
    assert finding.severity == "info"
    assert finding.confidence == "certain"


def test_imports_are_sorted_distinct_and_counted_across_ontologies() -> None:
    data = graph(
        f"{HEAD} ; owl:imports <https://z.test/b>, <https://a.test/a> . "
        "<https://example.test/two> owl:imports <https://a.test/a> ."
    )
    (finding,) = run(data)
    assert finding.message == "2 owl:imports were not followed: https://a.test/a, https://z.test/b."


def test_list_is_truncated_after_ten_with_the_remainder_counted() -> None:
    targets = ", ".join(f"<https://example.test/i{n:02d}>" for n in range(12))
    (finding,) = run(graph(f"{HEAD} ; owl:imports {targets} ."))
    listed = ", ".join(f"https://example.test/i{n:02d}" for n in range(10))
    assert finding.message == f"12 owl:imports were not followed: {listed} and 2 more."
    exactly = ", ".join(f"<https://example.test/i{n:02d}>" for n in range(10))
    (finding,) = run(graph(f"{HEAD} ; owl:imports {exactly} ."))
    assert finding.message.endswith("i09.")
    assert "more" not in finding.message


def test_no_imports_no_finding() -> None:
    assert run(graph(f"{HEAD} .")) == []
