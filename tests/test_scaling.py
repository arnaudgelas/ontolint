"""Steps that once grew quadratically must stay linear, so a regression fails here, not for a user.

0.4.0 shipped two quadratic steps: the source locator counted newlines from the start of the text
for every term, and CLS017 recomputed a set difference over all classes for every class.  A
40,000-class file took 30 s.  A draft of SHQ011's rewriting of a pattern for Python searched the rest
of the text for the ``}`` of every ``\\p{``, so a megabyte of unclosed ``\\p{`` took seconds.  Messages
found their blank-node labels with one pattern over every label of the graph, so each message cost as
much as the labels.  Each test times only its step (no parsing, which is linear and would hide the
quadratic term) at two sizes and compares them, so it holds on slow runners: multiplying the input by
eight must cost well under the sixty-four-fold time of a quadratic step.  The time is CPU time,
alternated between the sizes, as a run beside other workers is slowed by them as a whole and the
larger input more.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

import pytest
from rdflib import BNode, Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS
from rdflib.plugins.stores.memory import Memory

from ontolint import Linter
from ontolint.datasets import build_graph_index, finding_graphs
from ontolint.declarations import shared_identities
from ontolint.loader import LoadedGraph
from ontolint.models import Finding
from ontolint.paths import resolve_inputs
from ontolint.policy import Policy
from ontolint.rules.runtime import PropertyClosure, _BlankNames  # noqa: PLC2701 -- the rewriting is timed alone.
from ontolint.rules.shacl_authoring import pattern_problem
from ontolint.rules.support import DESCRIPTIONS, LABELS
from ontolint.source_locations import build_source_index

pytestmark = pytest.mark.slow

GROWTH = 8  # a wide step keeps linear and quadratic times apart when a busy machine inflates both
SMALL = 10_000
LARGE = GROWTH * SMALL
MAX_RATIO = GROWTH**2 / 2  # a quadratic step gives at least 64; a linear one 8, up to 24 as its dicts outgrow the cache


Step = Callable[[], object]


def _best_times(small: Step, large: Step) -> tuple[float, float]:
    """The fastest of several runs of each step, alternating them so both see the same load on a busy machine."""
    best = [float("inf"), float("inf")]
    for _attempt in range(5):  # the fastest run discards scheduling noise from a loaded machine
        for side, step in enumerate((small, large)):
            started = time.process_time()
            step()
            best[side] = min(best[side], time.process_time() - started)
    return best[0], best[1]


def _classes(count: int) -> tuple[str, Graph]:
    text = "".join(f"<https://example.test/C{i}> a <{OWL.Class}> .\n" for i in range(count))
    graph = Graph()
    for i in range(count):
        graph.add((URIRef(f"https://example.test/C{i}"), RDF.type, OWL.Class))
    return text, graph


def _locate(count: int) -> Step:
    text, graph = _classes(count)
    data = text.encode()
    return lambda: build_source_index(data, "nt", "file:///a.nt", graph).locations


def _cls017(count: int) -> Step:
    _text, graph = _classes(count)
    return lambda: Linter(graph).execute(["CLS017"])


def _dataset(count: int) -> tuple[Memory, BNode]:
    """``count`` classes spread over ten named graphs, each labelled in the default graph too."""
    store = Memory()
    default = BNode()
    named = [Graph(store=store, identifier=URIRef(f"https://example.test/g{i}")) for i in range(10)]
    for i in range(count):
        term = URIRef(f"https://example.test/C{i}")
        named[i % 10].add((term, RDF.type, OWL.Class))
        Graph(store=store, identifier=default).add((term, RDFS.label, URIRef(f"https://example.test/L{i}")))
    return store, default


def _graph_index(count: int) -> Step:
    store, default = _dataset(count)
    return lambda: build_graph_index(store, default, "file:///w/")


def _finding_graphs(count: int) -> Step:
    store, default = _dataset(count)
    index = build_graph_index(store, default, "file:///w/")
    findings = [Finding("LEX002", "info", f"https://example.test/C{i}", "m", "s") for i in range(count)]
    return lambda: finding_graphs(Graph(), index, findings)


def _closure(count: int) -> Step:
    """A chain of ``count`` properties below skos:definition, alternating sub-property and equivalence links,
    each with a cycle back to the chain's head, and a star of ``count`` sub-properties of rdfs:label."""
    graph = Graph()
    chain = [URIRef(f"https://example.test/d{i}") for i in range(count)]
    graph.add((chain[0], RDFS.subPropertyOf, SKOS.definition))
    for i in range(1, count):
        link = RDFS.subPropertyOf if i % 2 else OWL.equivalentProperty
        graph.add((chain[i], link, chain[i - 1]))
        graph.add((chain[0], RDFS.subPropertyOf, chain[i]))
        graph.add((URIRef(f"https://example.test/l{i}"), RDFS.subPropertyOf, RDFS.label))

    def step() -> None:
        closure = PropertyClosure(graph)
        assert len(closure.below(DESCRIPTIONS)) == len(DESCRIPTIONS) + count
        closure.below(LABELS)

    return step


def _shared_headers(count: int) -> Step:
    """ONT007 over a dataset of ``count / 5`` named graphs that each repeat one ontology header (the first draft
    of ONT007 built each graph by scanning every triple of the file, so the step grew with the square of the
    graphs)."""
    store, default = Memory(), BNode()
    for i in range(count // 5):
        named = Graph(store=store, identifier=URIRef(f"https://example.test/g{i}"))
        named.add((URIRef("https://example.test/o"), RDF.type, OWL.Ontology))
        named.add((URIRef(f"https://example.test/C{i}"), RDF.type, OWL.Class))
    index = build_graph_index(store, default, "file:///w/")
    (item,) = resolve_inputs(["d.trig"], Path.cwd())
    source_index = build_source_index(b"", "nt", "file:///w/d.trig", Graph())
    loaded = LoadedGraph(Graph(store=store, identifier=default), source_index, graphs=index)
    return lambda: shared_identities([item], [loaded], Policy())


def _distinct_shared_headers(count: int) -> Step:
    """ONT007 over a dataset of ``count / 5`` pairs of named graphs, each pair repeating its own ontology header
    (the first draft of ONT007 checked each finding against the findings of every other IRI, so the step grew
    with the square of the shared IRIs)."""
    store, default = Memory(), BNode()
    for i in range(count // 5):
        for side in "ab":
            named = Graph(store=store, identifier=URIRef(f"https://example.test/g{i}{side}"))
            named.add((URIRef(f"https://example.test/o{i}"), RDF.type, OWL.Ontology))
            named.add((URIRef(f"https://example.test/C{i}{side}"), RDF.type, OWL.Class))
    index = build_graph_index(store, default, "file:///w/")
    (item,) = resolve_inputs(["d.trig"], Path.cwd())
    source_index = build_source_index(b"", "nt", "file:///w/d.trig", Graph())
    loaded = LoadedGraph(Graph(store=store, identifier=default), source_index, graphs=index)
    return lambda: shared_identities([item], [loaded], Policy())


def _blank_labels(count: int) -> Step:
    """``count`` messages that each name one of ``count`` blank classes, labelled as a JSON-LD file labels them."""
    graph = Graph()
    for i in range(count):
        graph.add((BNode(f"b{i}"), RDF.type, OWL.Class))
    messages = [f"Class _:b{i} is blank." for i in range(count)]

    def step() -> None:
        names = _BlankNames(graph)
        for message in messages:
            names.rewrite(message)

    return step


@pytest.mark.parametrize(
    "step",
    [
        _locate,
        _cls017,
        _graph_index,
        _finding_graphs,
        _closure,
        _shared_headers,
        _distinct_shared_headers,
        _blank_labels,
    ],
    ids=[
        "source-locator",
        "CLS017",
        "graph-index",
        "finding-graphs",
        "property-closure",
        "shared-headers",
        "distinct-shared-headers",
        "blank-labels",
    ],
)
def test_the_step_grows_linearly_with_the_number_of_classes(step: Callable[[int], Step]) -> None:
    small, large = _best_times(step(SMALL), step(LARGE))
    assert large / small < MAX_RATIO, f"{SMALL} classes: {small:.3f} s, {LARGE} classes: {large:.3f} s"


PATTERN_SMALL = 120_000  # characters of sh:pattern
PATTERN_LARGE = GROWTH * PATTERN_SMALL


@pytest.mark.parametrize("unit", ["\\p{", "\\p{a", "[\\p{", "[a-[\\p{"], ids=["escape", "name", "class", "subtraction"])
def test_the_sh_pattern_judgement_grows_linearly_with_the_pattern(unit: str) -> None:
    # No \\p{ has its }: searching the rest of the text for it, from each one, is quadratic.
    def judge(size: int) -> Step:
        text = unit * (size // len(unit))
        return lambda: pattern_problem(text, "")

    small, large = _best_times(judge(PATTERN_SMALL), judge(PATTERN_LARGE))
    assert large / small < MAX_RATIO, f"{PATTERN_SMALL} chars: {small:.3f} s, {PATTERN_LARGE} chars: {large:.3f} s"
