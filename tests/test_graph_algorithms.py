"""Property-based tests for graph helpers used by ontology hierarchy checks."""

from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from ontolint.ontolint import FIXES, SEVERITY, Linter, main

TOOL_FAILURE_EXIT = 2


@st.composite
def directed_graphs(draw: st.DrawFn) -> tuple[list[URIRef], set[tuple[URIRef, URIRef]]]:
    """Return a small directed graph, including isolated nodes and self-loops."""
    size = draw(st.integers(min_value=0, max_value=8))
    nodes = [URIRef(f"https://example.test/node/{index}") for index in range(size)]
    possible_edges = [(source, target) for source in nodes for target in nodes]
    edges = set(draw(st.sets(st.sampled_from(possible_edges), max_size=len(possible_edges)))) if nodes else set()
    return nodes, edges


def _reachable(edges: set[tuple[URIRef, URIRef]], source: URIRef, target: URIRef) -> bool:
    adjacency: dict[URIRef, set[URIRef]] = defaultdict(set)
    for left, right in edges:
        adjacency[left].add(right)

    pending = deque([source])
    seen = {source}
    while pending:
        node = pending.popleft()
        if node == target:
            return True
        for neighbour in adjacency[node]:
            if neighbour not in seen:
                seen.add(neighbour)
                pending.append(neighbour)
    return False


@given(directed_graphs())
def test_components_matches_mutual_reachability(
    graph: tuple[list[URIRef], set[tuple[URIRef, URIRef]]],
) -> None:
    """Tarjan output partitions every node exactly by mutual reachability."""
    nodes, edges = graph

    components = Linter.components(nodes, edges)

    assert set().union(*components) == set(nodes)
    assert sum(map(len, components)) == len(nodes)
    for left in nodes:
        for right in nodes:
            same_component = any(left in component and right in component for component in components)
            assert same_component == (_reachable(edges, left, right) and _reachable(edges, right, left))


@given(directed_graphs())
def test_linter_reports_exactly_the_cyclic_subclass_components(
    graph: tuple[list[URIRef], set[tuple[URIRef, URIRef]]],
) -> None:
    """Generated RDF hierarchies produce one CLS003 finding per cyclic component."""
    nodes, edges = graph
    ontology = Graph()
    for node in nodes:
        ontology.add((node, RDF.type, OWL.Class))
    for child, parent in edges:
        ontology.add((child, RDFS.subClassOf, parent))

    findings = Linter(ontology).run()
    reported_focuses = {URIRef(finding.focus) for finding in findings if finding.rule == "CLS003"}
    expected_focuses = {
        min(component, key=str)
        for component in Linter.components(nodes, edges)
        if len(component) > 1 or any((node, node) in edges for node in component)
    }

    assert reported_focuses == expected_focuses


@pytest.mark.parametrize(
    ("base", "iri", "expected"),
    [
        ("https://example.test/onto#", "https://example.test/onto#Term", True),
        ("https://example.test/onto", "https://example.test/onto/Term", True),
        ("https://example.test/onto", "https://example.test/ontology/Term", False),
    ],
)
def test_local_requires_a_namespace_boundary(base: str, iri: str, expected: bool) -> None:
    """A base IRI must not accidentally include a similarly prefixed namespace."""
    linter = Linter.__new__(Linter)
    linter.base = base

    assert linter.local(URIRef(iri)) is expected


def test_invalid_policy_is_reported_as_a_tool_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Operational failures remain machine-readable linter diagnostics."""
    policy = tmp_path / "invalid-policy.json"
    policy.write_text("{", encoding="utf-8")

    assert main(["ontology.ttl", "--config", str(policy)]) == TOOL_FAILURE_EXIT

    assert capsys.readouterr().err.startswith("TOOL001: configuration failed: JSONDecodeError:")


def test_rule_registry_has_a_remediation_for_every_diagnostic() -> None:
    """Every selectable diagnostic has a valid severity and actionable remediation."""
    assert set(SEVERITY) == set(FIXES)
    assert set(SEVERITY.values()) <= {"error", "warning", "info"}
    assert all(remediation.strip() for remediation in FIXES.values())


@pytest.mark.parametrize("rule", sorted(SEVERITY))
def test_every_registered_rule_can_be_emitted(rule: str) -> None:
    """Prevent new rule IDs from failing in the common finding-construction path."""
    linter = Linter(Graph())

    linter.add(rule, URIRef("https://example.test/focus"), "test finding")

    assert linter.issues[0].rule == rule
    assert linter.issues[0].severity == SEVERITY[rule]
    assert linter.issues[0].suggestion == FIXES[rule]
