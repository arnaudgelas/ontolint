"""Contract tests for reusable policy, rule metadata, and graph primitives."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

from ontolint import Linter
from ontolint.graph import strongly_connected_components
from ontolint.models import ExecutionStatus, RuleExecution, RuleSpec, Severity
from ontolint.policy import Policy
from ontolint.rules import RuleRegistry

EX = Namespace("https://example.test/")


def test_rule_registry_is_deterministic_and_selects_by_rule_or_family() -> None:
    specifications = (
        RuleSpec("OWL001", "OWL", "First", Severity.WARNING, "fix", "heuristic", "RDFLib"),
        RuleSpec("LEX001", "LEX", "Second", Severity.INFO, "fix", "certain", "RDFLib"),
    )
    registry = RuleRegistry(reversed(specifications))

    assert [spec.rule_id for spec in registry.all()] == ["LEX001", "OWL001"]
    assert [spec.rule_id for spec in registry.select([])] == ["LEX001", "OWL001"]
    assert [spec.rule_id for spec in registry.select(["owl"])] == ["OWL001"]
    assert [spec.rule_id for spec in registry.select(["LEX001"])] == ["LEX001"]
    with pytest.raises(ValueError, match="duplicate"):
        registry.register(specifications[0])


def test_policy_validates_json_shapes_and_preserves_immutable_values() -> None:
    policy = Policy.from_mapping(
        {
            "base": str(EX),
            "languages": ["EN"],
            "depth_limit": 4,
            "inheritance_limit": 2,
            "soup_limit": 8,
            "ignored_rules": ["CLS002"],
            "severity_overrides": {"LEX001": "error"},
        }
    )

    assert policy.languages == ("en",)
    assert policy.ignored_rules == frozenset({"CLS002"})
    assert policy.severity_mapping == {"LEX001": "error"}
    assert RuleExecution("LEX001", ExecutionStatus.SKIPPED, "profile").status == ExecutionStatus.SKIPPED
    with pytest.raises(FrozenInstanceError):
        policy.base = "https://changed.example/"  # type: ignore[misc] -- immutable policy is a public contract.
    with pytest.raises(ValueError, match="thresholds"):
        Policy.from_mapping({"depth_limit": True})
    with pytest.raises(ValueError, match="severity_overrides"):
        Policy.from_mapping({"severity_overrides": {"LEX001": "fatal"}})
    with pytest.raises(ValueError, match="base"):
        Policy.from_mapping({"base": 1})
    with pytest.raises(ValueError, match="languages"):
        Policy.from_mapping({"languages": "en"})
    with pytest.raises(ValueError, match="ignored_rules"):
        Policy.from_mapping({"ignored_rules": [1]})
    with pytest.raises(ValueError, match="severity_overrides must map"):
        Policy.from_mapping({"severity_overrides": []})
    with pytest.raises(ValueError, match="severity_overrides must map"):
        Policy.from_mapping({"severity_overrides": {"LEX001": 1}})


def test_rule_metadata_models_are_immutable() -> None:
    spec = RuleSpec("LEX001", "LEX", "Label", Severity.WARNING, "fix", "heuristic", "RDFLib")
    execution = RuleExecution("LEX001", ExecutionStatus.EXECUTED)

    with pytest.raises(FrozenInstanceError):
        spec.title = "changed"  # type: ignore[misc] -- immutable registry data cannot drift during a run.
    with pytest.raises(FrozenInstanceError):
        execution.status = ExecutionStatus.FAILED  # type: ignore[misc] -- execution records are values.


def test_iterative_scc_handles_a_taxonomy_deeper_than_python_recursion_limit() -> None:
    nodes = [URIRef(f"https://example.test/{index}") for index in range(6_000)]
    edges = list(zip(nodes, nodes[1:], strict=False))

    components = strongly_connected_components(nodes, edges)

    assert len(components) == len(nodes)
    assert all(len(component) == 1 for component in components)


def test_scc_ignores_edges_with_a_node_outside_the_requested_graph() -> None:
    left, right, external = EX.left, EX.right, URIRef("https://external.example/node")

    components = strongly_connected_components((left, right), ((left, right), (right, external)))

    assert {frozenset(component) for component in components} == {frozenset({left}), frozenset({right})}


def test_unicode_whitespace_and_language_string_rules_have_expected_semantics() -> None:
    graph = Graph()
    invalid = URIRef("https://example.test/contains\u2003whitespace")
    property_ = EX.string_property
    graph.add((invalid, RDF.type, OWL.Class))
    graph.add((property_, RDF.type, OWL.DatatypeProperty))
    graph.add((property_, RDFS.range, XSD.string))
    graph.add((EX.subject, property_, Literal("bonjour", lang="fr")))

    rules = {finding.rule for finding in Linter(graph).run()}

    assert "IRI001" in rules
    assert "DATA001" not in rules


def test_lexical_capitalization_selection_is_independent_of_graph_insertion_order() -> None:
    findings: list[set[str]] = []
    for labels in ((Literal("zebra"), Literal("Apple")), (Literal("Apple"), Literal("zebra"))):
        graph = Graph()
        graph.add((EX.Class, RDF.type, OWL.Class))
        for label in labels:
            graph.add((EX.Class, RDFS.label, label))
        findings.append({finding.rule for finding in Linter(graph).run()})

    assert findings == [{"CLS001", "CLS002", "LEX002", "LEX003", "ONT001"}] * 2


def test_lexical_capitalization_handles_plain_and_language_tagged_labels() -> None:
    graph = Graph()
    graph.add((EX.Class, RDF.type, OWL.Class))
    graph.add((EX.Class, RDFS.label, Literal("Apple")))
    graph.add((EX.Class, RDFS.label, Literal("zebra", lang="en")))

    rules = {finding.rule for finding in Linter(graph).run()}

    assert "LEX006" in rules
