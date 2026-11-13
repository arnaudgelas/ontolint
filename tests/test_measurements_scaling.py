"""The hierarchy measurements walk iteratively: a 100k-deep chain or 100k isolated classes never recurse."""

from __future__ import annotations

import pytest
from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from ontolint.engine import build_context
from ontolint.policy import Policy
from ontolint.rules.measurements import TermValues, count, measure

pytestmark = pytest.mark.slow

SIZE = 100_000
NS = "https://example.test/deep#"


def _classes(chained: bool) -> Graph:
    graph = Graph()
    graph.add((URIRef("https://example.test/deep"), RDF.type, OWL.Ontology))
    for index in range(SIZE):
        term = URIRef(f"{NS}C{index}")
        graph.add((term, RDF.type, OWL.Class))
        if chained and index:
            graph.add((term, RDFS.subClassOf, URIRef(f"{NS}C{index - 1}")))
    return graph


def test_a_100k_deep_chain_is_one_component_100k_levels_deep() -> None:
    ctx = build_context(_classes(chained=True), None, Policy())
    depth = measure(ctx, "class_depth")
    assert isinstance(depth, TermValues)
    assert max(depth.values.values()) == SIZE
    assert count(ctx, "hierarchy_components") == 1


def test_100k_isolated_classes_are_100k_components_at_the_top() -> None:
    ctx = build_context(_classes(chained=False), None, Policy())
    depth = measure(ctx, "class_depth")
    assert isinstance(depth, TermValues)
    assert set(depth.values.values()) == {1}
    assert count(ctx, "hierarchy_components") == SIZE
