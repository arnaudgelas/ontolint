"""Steps that once grew quadratically must stay linear, so a regression fails here, not for a user.

0.4.0 shipped two quadratic steps: the source locator counted newlines from the start of the text
for every term, and CLS017 recomputed a set difference over all classes for every class.  A
40,000-class file took 30 s.  Each test times only its step (no parsing, which is linear and would
hide the quadratic term) at two sizes and compares them, so it holds on slow runners: quadrupling
the input must cost well under the sixteen-fold time of a quadratic step.
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
from ontolint.rules.runtime import PropertyClosure
from ontolint.rules.support import DESCRIPTIONS, LABELS
from ontolint.source_locations import build_source_index

pytestmark = pytest.mark.slow

SMALL = 5_000
LARGE = 4 * SMALL
MAX_RATIO = 8.0  # linear growth gives about 4; a quadratic step gives about 16


def _best_of(step: Callable[[], object]) -> float:
    best = float("inf")
    for _attempt in range(5):  # the fastest run discards scheduling noise from a loaded machine
        started = time.perf_counter()
        step()
        best = min(best, time.perf_counter() - started)
    return best


def _classes(count: int) -> tuple[str, Graph]:
    text = "".join(f"<https://example.test/C{i}> a <{OWL.Class}> .\n" for i in range(count))
    graph = Graph()
    for i in range(count):
        graph.add((URIRef(f"https://example.test/C{i}"), RDF.type, OWL.Class))
    return text, graph


def _locate(count: int) -> float:
    text, graph = _classes(count)
    data = text.encode()
    return _best_of(lambda: build_source_index(data, "nt", "file:///a.nt", graph).locations)


def _cls017(count: int) -> float:
    _text, graph = _classes(count)
    return _best_of(lambda: Linter(graph).execute(["CLS017"]))


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


def _graph_index(count: int) -> float:
    store, default = _dataset(count)
    return _best_of(lambda: build_graph_index(store, default, "file:///w/"))


def _finding_graphs(count: int) -> float:
    store, default = _dataset(count)
    index = build_graph_index(store, default, "file:///w/")
    findings = [Finding("LEX002", "info", f"https://example.test/C{i}", "m", "s") for i in range(count)]
    return _best_of(lambda: finding_graphs(Graph(), index, findings))


def _closure(count: int) -> float:
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

    return _best_of(step)


def _shared_headers(count: int) -> float:
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
    return _best_of(lambda: shared_identities([item], [loaded], Policy()))


@pytest.mark.parametrize(
    "step",
    [_locate, _cls017, _graph_index, _finding_graphs, _closure, _shared_headers],
    ids=["source-locator", "CLS017", "graph-index", "finding-graphs", "property-closure", "shared-headers"],
)
def test_the_step_grows_linearly_with_the_number_of_classes(step: Callable[[int], float]) -> None:
    small, large = step(SMALL), step(LARGE)
    assert large / small < MAX_RATIO, f"{SMALL} classes: {small:.3f} s, {LARGE} classes: {large:.3f} s"
