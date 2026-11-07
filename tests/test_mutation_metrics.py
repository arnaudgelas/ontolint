"""Targeted tests that pin behaviour the mutation run found unobserved (metrics rules)."""

# ruff: noqa: SLF001

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from typing import Any

import pytest
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS
from rule_harness import BASE

from ontolint import engine
from ontolint.models import Finding
from ontolint.policy import Policy
from ontolint.rules import metrics


def _run(data: Graph, rule: str, **thresholds: Any) -> list[Finding]:
    policy = replace(Policy(), metric_min_sample=1, **thresholds)
    ctx = engine.build_context(data, None, policy)
    metrics.run(ctx)
    return [f for f in ctx.findings if f.rule == rule]


def _ex(name: str) -> URIRef:
    return URIRef(BASE + name)


def _cls(g: Graph, name: str) -> URIRef:
    g.add((_ex(name), RDF.type, OWL.Class))
    return _ex(name)


@pytest.mark.parametrize(
    ("iri", "expected"),
    [("http://a.test/b#c", "http://a.test/b#"), ("http://a.test/b", "http://a.test/"), ("/a", "/"), ("urn", "urn")],
)
def test_namespace_cuts_after_the_last_separator(iri: str, expected: str) -> None:
    assert metrics._namespace(URIRef(iri)) == expected


def test_hierarchy_is_immutable() -> None:
    h = metrics._Hierarchy({}, {})
    with pytest.raises(FrozenInstanceError):
        h.parents = {}  # type: ignore[misc]


def test_metric012_counts_only_class_definitions() -> None:
    g = Graph()
    c = _cls(g, "C")
    g.add((c, RDFS.comment, Literal("one two three four five")))
    p = _ex("p")
    g.add((p, RDF.type, OWL.ObjectProperty))
    g.add((p, RDFS.comment, Literal("short")))
    assert _run(g, "METRIC012") == []


def test_metric012_does_not_fire_when_mean_equals_threshold() -> None:
    g = Graph()
    g.add((_cls(g, "C"), RDFS.comment, Literal("one two three four")))
    assert _run(g, "METRIC012", metric_min_definition_words=4.0) == []
    assert len(_run(g, "METRIC012", metric_min_definition_words=4.5)) == 1


def test_metric010_does_not_fire_when_ratio_equals_limit() -> None:
    g = Graph()
    a = _cls(g, "A")
    g.add((a, RDFS.subClassOf, _ex("B")))
    g.add((a, RDFS.subClassOf, URIRef("http://elsewhere.test/X")))
    assert _run(g, "METRIC010", metric_max_foreign_reference_ratio=0.5) == []
    assert len(_run(g, "METRIC010", metric_max_foreign_reference_ratio=0.4)) == 1


def test_metric013_does_not_fire_when_ratio_equals_limit() -> None:
    g = Graph()
    g.add((_ex("s"), RDFS.label, Literal("x")))
    g.add((BNode(), RDFS.label, Literal("y")))
    assert _run(g, "METRIC013", metric_max_blank_node_ratio=0.5) == []
    assert len(_run(g, "METRIC013", metric_max_blank_node_ratio=0.4)) == 1
