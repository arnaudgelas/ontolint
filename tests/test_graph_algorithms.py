"""Property-based tests for graph helpers used by ontology hierarchy checks."""

from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from ontolint.graph import hierarchy_depths, reachable, strongly_connected_components, transitively_redundant_edges
from ontolint.ontolint import FIXES, SEVERITY, Linter, main
from ontolint.rules.classes import _chain_lengths

TOOL_FAILURE_EXIT = 2
PROPERTY_TEST_SETTINGS = settings(max_examples=150, deadline=None, print_blob=True)
EXTERNAL_NODE = URIRef("https://external.example/node")


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


@PROPERTY_TEST_SETTINGS
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


@PROPERTY_TEST_SETTINGS
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
    components = {
        frozenset(node for node in nodes if _reachable(edges, root, node) and _reachable(edges, node, root))
        for root in nodes
    }
    expected_focuses = {
        min(component, key=str)
        for component in components
        if len(component) > 1 or any((node, node) in edges for node in component)
    }

    assert reported_focuses == expected_focuses


@PROPERTY_TEST_SETTINGS
@given(directed_graphs())
def test_directed_edges_only_returns_allowed_rdf_edges(
    graph: tuple[list[URIRef], set[tuple[URIRef, URIRef]]],
) -> None:
    """Non-local resources must not leak into hierarchy graph analysis."""
    nodes, edges = graph
    rdf_graph = Graph()
    for source, target in edges:
        rdf_graph.add((source, RDFS.subClassOf, target))
    rdf_graph.add((EXTERNAL_NODE, RDFS.subClassOf, nodes[0] if nodes else EXTERNAL_NODE))

    assert Linter.directed_edges(rdf_graph, RDFS.subClassOf, set(nodes)) == edges


def test_reachable_distinguishes_direct_paths_ignored_edges_and_missing_targets() -> None:
    left, middle, right = (URIRef(f"https://example.test/{name}") for name in ("left", "middle", "right"))
    adjacency = {left: {middle}, middle: {right}}

    assert Linter.reachable(adjacency, left, right)
    assert not Linter.reachable(adjacency, left, right, ignore=(middle, right))
    assert not Linter.reachable(adjacency, right, left)


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


def _reference_depths(nodes: list[URIRef], edges: set[tuple[URIRef, URIRef]]) -> dict[URIRef, int]:
    """Straight port of the legacy recursive CLS005 ``depth`` helper (small graphs only)."""
    children: dict[URIRef, set[URIRef]] = defaultdict(set)
    for child, parent in edges:
        children[parent].add(child)
    cyclic = {n for comp in Linter.components(nodes, edges) if len(comp) > 1 for n in comp}
    memo: dict[URIRef, int] = {}
    processing: set[URIRef] = set()

    def depth(c: URIRef) -> int:
        if c in memo:
            return memo[c]
        if c in processing or c in cyclic:
            return 0
        processing.add(c)
        result = 1 + max((depth(x) for x in children[c] if x != c), default=0)
        processing.remove(c)
        memo[c] = result
        return result

    return {c: depth(c) for c in nodes}


@settings(max_examples=500, deadline=None, print_blob=True)
@given(directed_graphs())
def test_hierarchy_depths_matches_recursive_reference(
    graph: tuple[list[URIRef], set[tuple[URIRef, URIRef]]],
) -> None:
    """Iterative depths equal the legacy recursion for cycles, self-loops, diamonds and isolates."""
    nodes, edges = graph

    assert hierarchy_depths(nodes, edges) == _reference_depths(nodes, edges)


def test_hierarchy_depths_documented_edge_cases() -> None:
    a, b, c, d, e = (URIRef(f"https://example.test/{x}") for x in "abcde")
    # Diamond a <- {b, c} <- d, but d <-> e is a cycle (depth 0), c has a self-loop (ignored).
    edges = {(b, a), (c, a), (d, b), (d, c), (c, c), (e, d), (d, e)}
    assert hierarchy_depths([a, b, c, d, e], edges) == {a: 2, b: 1, c: 1, d: 0, e: 0}
    assert hierarchy_depths([], []) == {}
    assert hierarchy_depths([a], [(a, a), (a, URIRef("https://external.example/x"))]) == {a: 1}


def test_hierarchy_depths_handles_100k_deep_chain() -> None:
    size = 100_000
    nodes = list(range(size))
    depths = hierarchy_depths(nodes, ((i + 1, i) for i in range(size - 1)))

    assert depths[0] == size
    assert depths[size - 1] == 1


@st.composite
def mostly_acyclic_graphs(draw: st.DrawFn) -> tuple[list[URIRef], set[tuple[URIRef, URIRef]]]:
    """Return a larger graph biased towards DAGs (edges to higher indexes), with a few random back-edges."""
    size = draw(st.integers(min_value=0, max_value=14))
    nodes = [URIRef(f"https://example.test/node/{index}") for index in range(size)]
    forward = [(nodes[i], nodes[j]) for i in range(size) for j in range(i + 1, size)]
    edges = set(draw(st.sets(st.sampled_from(forward), max_size=len(forward)))) if forward else set()
    if nodes and draw(st.booleans()):
        edges.add((draw(st.sampled_from(nodes)), draw(st.sampled_from(nodes))))
    return nodes, edges


@settings(max_examples=500, deadline=None, print_blob=True)
@given(st.one_of(directed_graphs(), mostly_acyclic_graphs()))
def test_transitively_redundant_edges_matches_per_edge_search(
    graph: tuple[list[URIRef], set[tuple[URIRef, URIRef]]],
) -> None:
    """The reachability-bitset algorithm flags exactly the edges the legacy per-edge BFS flagged."""
    nodes, edges = graph
    supers: dict[URIRef, set[URIRef]] = defaultdict(set)
    for child, parent in edges:
        supers[child].add(parent)
    expected = {(c, p) for c, p in edges if reachable(supers, c, p, ignore=(c, p))}

    assert transitively_redundant_edges(edges, strongly_connected_components(nodes, edges)) == expected


def _legacy_chain_length(start: URIRef, children: dict[URIRef, set[URIRef]]) -> int:
    length, node, seen = 0, start, set[URIRef]()
    while len(children[node]) == 1 and node not in seen:
        seen.add(node)
        node = next(iter(children[node]))
        length += 1
    return length


@settings(max_examples=500, deadline=None, print_blob=True)
@given(st.one_of(directed_graphs(), mostly_acyclic_graphs()))
def test_chain_lengths_match_legacy_walk(graph: tuple[list[URIRef], set[tuple[URIRef, URIRef]]]) -> None:
    """Memoised CLS007 chain lengths equal the legacy walk from every class, cycles included."""
    nodes, edges = graph
    children: defaultdict[URIRef, set[URIRef]] = defaultdict(set)
    for child, parent in edges:
        children[parent].add(child)
    expected = {n: _legacy_chain_length(n, children) for n in nodes}

    assert _chain_lengths(nodes, children) == expected


def test_linter_handles_chain_far_beyond_recursion_limit() -> None:
    """CLS005/CLS007 use iterative algorithms, so a 5000-deep chain lints without RecursionError."""
    size = 5_000
    graph = Graph()
    nodes = [URIRef(f"https://example.test/chain/{index}") for index in range(size)]
    for index, node in enumerate(nodes):
        graph.add((node, RDF.type, OWL.Class))
        if index:
            graph.add((node, RDFS.subClassOf, nodes[index - 1]))

    findings = Linter(graph).run()

    assert {f.focus for f in findings if f.rule == "CLS005"} == {str(nodes[0])}  # one finding per deep branch
