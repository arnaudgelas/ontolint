"""Property tests for graph algorithms against brute-force oracles: RDF lists, hierarchy closure, blank-node depth."""

from __future__ import annotations

from collections import defaultdict
from itertools import product
from random import Random

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st
from hypothesis_strategies import BASE, FOREIGN, budget
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS
from rdflib.term import Node

from ontolint import Linter
from ontolint.engine import build_context
from ontolint.policy import Policy
from ontolint.rules.hierarchy_quality import Hierarchy
from ontolint.rules.runtime import PropertyClosure
from ontolint.rules.safety import MAX_BLANK_NODE_DEPTH, _condensed_depths
from ontolint.rules.support import DESCRIPTIONS, list_items

pytestmark = pytest.mark.slow

NODES = [URIRef(f"{BASE}n{i}") for i in range(7)]
CELLS = [BNode(f"QBNA{i}") for i in range(6)]
MEMBERS = [URIRef(f"{BASE}m{i}") for i in range(4)] + [Literal("lit"), CELLS[0]]


# --- RDF lists ---------------------------------------------------------------------------------------


@budget(1)
@given(st.lists(st.sampled_from(MEMBERS), max_size=8), st.integers(0, 10))
def test_list_items_reads_a_well_formed_list_up_to_the_limit(members: list[Node], limit: int) -> None:
    """INVARIANT: a well-formed list of n members is returned verbatim when n <= limit, otherwise None."""
    graph = Graph()
    cells = [BNode(f"cell{i}") for i in range(len(members))]
    for index, (cell, member) in enumerate(zip(cells, members, strict=True)):
        graph.add((cell, RDF.first, member))
        graph.add((cell, RDF.rest, cells[index + 1] if index + 1 < len(cells) else RDF.nil))
    head: Node = cells[0] if cells else RDF.nil

    result = list_items(graph, head, limit=limit)

    assert result == (members if len(members) <= limit else None)
    assert Linter.list_items(graph, head, limit=limit) == result


def _oracle_list(
    firsts: dict[Node, list[Node]], rests: dict[Node, list[Node]], head: Node, limit: int
) -> list[Node] | None:
    """Independent definition: every cell on the path has exactly one first and one rest; no repeats; ends at nil."""
    items: list[Node] = []
    visited: list[Node] = []
    node = head
    while node != RDF.nil:
        if node in visited or len(items) >= limit:
            return None
        visited.append(node)
        if len(firsts.get(node, [])) != 1 or len(rests.get(node, [])) != 1:
            return None
        items.append(firsts[node][0])
        node = rests[node][0]
    return items


list_triples = st.lists(
    st.tuples(
        st.sampled_from(CELLS),
        st.sampled_from((RDF.first, RDF.rest, RDF.first, RDF.rest, RDFS.label)),
        st.sampled_from([*CELLS, *MEMBERS[:4], RDF.nil, RDF.nil, Literal("x")]),
    ),
    max_size=14,
)


@budget(2)
@given(list_triples, st.sampled_from([*CELLS, RDF.nil, MEMBERS[0], Literal("x")]), st.integers(0, 8))
def test_list_items_matches_an_independent_definition_on_arbitrary_cell_soup(
    triples: list[tuple[Node, URIRef, Node]], head: Node, limit: int
) -> None:
    """INVARIANT: list_items agrees with 'unique cells, one first, one rest, ends at nil' and terminates."""
    graph = Graph()
    firsts: dict[Node, list[Node]] = defaultdict(list)
    rests: dict[Node, list[Node]] = defaultdict(list)
    for s, p, o in triples:
        graph.add((s, p, o))
    for s, o in graph.subject_objects(RDF.first):
        firsts[s].append(o)
    for s, o in graph.subject_objects(RDF.rest):
        rests[s].append(o)

    assert list_items(graph, head, limit=limit) == _oracle_list(firsts, rests, head, limit)


# --- Hierarchy ---------------------------------------------------------------------------------------

edge_sets = st.sets(st.tuples(st.sampled_from(NODES), st.sampled_from(NODES)), max_size=14)


def _closure(edges: set[tuple[URIRef, URIRef]], start: URIRef) -> set[URIRef]:
    """Nodes reachable from ``start`` through one or more edges, by naive fixpoint iteration."""
    reached: set[URIRef] = set()
    changed = True
    while changed:
        changed = False
        for child, parent in edges:
            if (child == start or child in reached) and parent not in reached:
                reached.add(parent)
                changed = True
    return reached


@budget(1)
@given(edge_sets)
def test_hierarchy_ancestors_equal_the_transitive_closure(edges: set[tuple[URIRef, URIRef]]) -> None:
    """INVARIANT: ancestors(x) is every class reachable by >= 1 super edge; x itself only when on a cycle."""
    supers: dict[URIRef, set[URIRef]] = defaultdict(set)
    children: dict[URIRef, set[URIRef]] = defaultdict(set)
    for child, parent in edges:
        supers[child].add(parent)
        children[parent].add(child)
    hierarchy = Hierarchy({k: frozenset(v) for k, v in supers.items()}, {k: frozenset(v) for k, v in children.items()})

    for node in NODES:
        assert hierarchy.ancestors(node) == _closure(edges, node)
    assert set(hierarchy.edges()) == edges


@budget(1)
@given(edge_sets, st.sets(st.sampled_from(NODES), max_size=7), st.booleans())
def test_hierarchy_build_keeps_only_edges_between_declared_classes_without_self_loops(
    edges: set[tuple[URIRef, URIRef]], declared: set[URIRef], with_foreign_parent: bool
) -> None:
    """INVARIANT: Hierarchy.build indexes exactly the subClassOf edges between declared classes (no self-loops)."""
    graph = Graph()
    for node in declared:
        graph.add((node, RDF.type, OWL.Class))
    for child, parent in edges:
        graph.add((child, RDFS.subClassOf, parent))
    if with_foreign_parent:
        for node in declared:
            graph.add((node, RDFS.subClassOf, URIRef(FOREIGN + "Outside")))
            graph.add((node, RDFS.subClassOf, BNode("restriction")))

    hierarchy = Hierarchy.build(build_context(graph, None, Policy()))

    expected = {(c, p) for c, p in edges if c in declared and p in declared and c != p}
    assert set(hierarchy.edges()) == expected
    assert {(c, p) for p, cs in hierarchy.children.items() for c in cs} == expected


# --- Definition predicates: the rdfs:subPropertyOf closure ------------------------------------------

PROPERTY_NODES: list[Node] = [
    *(URIRef(f"{BASE}def{i}") for i in range(7)),
    BNode("QBNP0"),
    BNode("QBNP1"),
    *DESCRIPTIONS[:3],
]


def _oracle_descriptions(edges: set[tuple[Node, Node]]) -> set[Node]:
    """Fixed point: add ``s`` whenever ``s rdfs:subPropertyOf o`` and ``o`` is already in the set."""
    closure: set[Node] = set(DESCRIPTIONS)
    changed = True
    while changed:
        changed = False
        for sub, sup in edges:
            if sup in closure and sub not in closure:
                closure.add(sub)
                changed = True
    return {node for node in closure if isinstance(node, URIRef)}


@budget(1)
@given(
    st.sets(st.tuples(st.sampled_from(PROPERTY_NODES), st.sampled_from(PROPERTY_NODES)), max_size=20),
    st.randoms(use_true_random=False),
)
def test_descriptions_are_the_subproperty_closure_of_the_seeds(edges: set[tuple[Node, Node]], rng: Random) -> None:
    """INVARIANT: ctx.descriptions is the defaults, then the IRIs below them sorted, whatever the order or cycles."""
    triples = [(sub, RDFS.subPropertyOf, sup) for sub, sup in sorted(edges, key=str)]
    graph = Graph()
    for triple in triples:
        graph.add(triple)
    descriptions = build_context(graph, None, Policy()).descriptions

    assert set(descriptions) == _oracle_descriptions(edges)
    assert len(descriptions) == len(set(descriptions))
    assert descriptions[: len(DESCRIPTIONS)] == DESCRIPTIONS
    tail = descriptions[len(DESCRIPTIONS) :]
    assert list(tail) == sorted(tail, key=str)
    rng.shuffle(triples)
    shuffled = Graph()
    for triple in triples:
        shuffled.add(triple)
    assert build_context(shuffled, None, Policy()).descriptions == descriptions


def _oracle_closure(edges: set[tuple[Node, bool, Node]], seeds: tuple[Node, ...], stop: frozenset[Node]) -> set[Node]:
    """Fixed point: add ``s`` (not stopped) when ``s ⊑ o`` or ``s ≡ o`` or ``o ≡ s`` and ``o`` is in the set."""
    closure: set[Node] = set(seeds)
    changed = True
    while changed:
        changed = False
        for one, equivalent, other in edges:
            pairs = [(one, other), (other, one)] if equivalent else [(one, other)]
            for sub, sup in pairs:
                if sup in closure and sub not in closure and sub not in stop:
                    closure.add(sub)
                    changed = True
    return {node for node in closure if isinstance(node, URIRef)}


@budget(1)
@given(
    st.sets(st.tuples(st.sampled_from(PROPERTY_NODES), st.booleans(), st.sampled_from(PROPERTY_NODES)), max_size=20),
    st.frozensets(st.sampled_from([node for node in PROPERTY_NODES if isinstance(node, URIRef)]), max_size=3),
    st.randoms(use_true_random=False),
)
def test_the_property_closure_follows_subproperties_and_equivalences(
    edges: set[tuple[Node, bool, Node]], stop: frozenset[URIRef], rng: Random
) -> None:
    """INVARIANT: PropertyClosure.below is the seeds, then the unstopped IRIs below them sorted, in any order."""
    seeds = DESCRIPTIONS[:2]
    triples = [
        (one, OWL.equivalentProperty if equivalent else RDFS.subPropertyOf, other)
        for one, equivalent, other in sorted(edges, key=str)
    ]
    graph = Graph()
    for triple in triples:
        graph.add(triple)
    below = PropertyClosure(graph).below(seeds, stop)

    assert set(below) == _oracle_closure(edges, seeds, stop)
    assert below[: len(seeds)] == seeds
    tail = below[len(seeds) :]
    assert list(tail) == sorted(set(tail), key=str)
    rng.shuffle(triples)
    shuffled = Graph()
    for triple in triples:
        shuffled.add(triple)
    assert PropertyClosure(shuffled).below(seeds, stop) == below


# --- SEC004 blank-node depth -------------------------------------------------------------------------

bnode_edges = st.sets(st.tuples(st.integers(0, 6), st.integers(0, 6)), max_size=16)


def _reaches(edges: set[tuple[int, int]], size: int) -> list[list[bool]]:
    reach = [[i == j or (i, j) in edges for j in range(size)] for i in range(size)]
    for k, i, j in product(range(size), repeat=3):
        reach[i][j] = reach[i][j] or (reach[i][k] and reach[k][j])
    return reach


def _oracle_depths(edges: set[tuple[int, int]], size: int) -> dict[int, int]:
    """Depth = 1 + the longest chain of other strongly connected components below a node (Floyd-Warshall oracle)."""
    reach = _reaches(edges, size)
    component = [frozenset(j for j in range(size) if reach[i][j] and reach[j][i]) for i in range(size)]
    memo: dict[frozenset[int], int] = {}

    def depth(comp: frozenset[int]) -> int:
        if comp not in memo:
            below = {component[c] for m in comp for (a, c) in edges if a == m} - {comp}
            memo[comp] = 1 + max((depth(b) for b in below), default=0)
        return memo[comp]

    return {i: depth(component[i]) for i in range(size)}


@budget(2)
@given(bnode_edges, st.randoms(use_true_random=False))
def test_condensed_depths_match_a_brute_force_oracle_and_ignore_labels(
    edges: set[tuple[int, int]], rnd: object
) -> None:
    """INVARIANT: SEC004 depths equal 1 + longest condensation path, independent of node labels and edge order."""
    nodes = sorted({n for e in edges for n in e})
    names = [f"q{n}" for n in range(7)]
    order = list(range(7))
    rnd.shuffle(order)  # type: ignore[attr-defined]
    expected = _oracle_depths(edges, 7)

    for labels in (names, [f"zz{order[n]:02d}" for n in range(7)]):
        children: dict[Node, list[Node]] = defaultdict(list)
        for a, b in sorted(edges, key=lambda e: (e[1], e[0])):
            children[BNode(labels[a])].append(BNode(labels[b]))
        depths = _condensed_depths(children)
        assert set(depths) == {BNode(labels[n]) for n in nodes}
        assert all(depths[BNode(labels[n])] == expected[n] for n in nodes)


@budget(1)
@given(st.integers(MAX_BLANK_NODE_DEPTH - 3, MAX_BLANK_NODE_DEPTH + 3), st.one_of(st.none(), st.integers(1, 100)))
def test_sec004_fires_exactly_when_a_blank_node_chain_exceeds_the_limit(length: int, back_edge_to: int | None) -> None:
    """INVARIANT: a chain of n nested blank nodes is reported iff n > limit; a cycle closing at k counts as k levels."""
    chain = [BNode(f"chain{i}") for i in range(length)]
    graph = Graph()
    owner = URIRef(f"{BASE}A")
    graph.add((owner, RDFS.subClassOf, chain[0]))
    for a, b in zip(chain, chain[1:], strict=False):
        graph.add((a, OWL.someValuesFrom, b))
    depth = length
    if back_edge_to is not None:
        assume(back_edge_to < length)
        graph.add((chain[-1], OWL.someValuesFrom, chain[back_edge_to]))
        depth = back_edge_to + 1

    findings = [f for f in Linter(graph).run() if f.rule == "SEC004" and "nested" in f.message]

    assert bool(findings) == (depth > MAX_BLANK_NODE_DEPTH)
    if findings:
        assert [f.focus for f in findings] == [str(owner)]
        assert f"nested {depth} levels" in findings[0].message
