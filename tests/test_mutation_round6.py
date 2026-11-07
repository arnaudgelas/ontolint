"""Round 6 mutation survivors: SHACL pre-check, lexical, OBO, SKOS and ownership edge cases."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS
from rule_harness import BASE, graph

from ontolint import Linter
from ontolint.adapters import shacl
from ontolint.adapters.shacl import check_graph
from ontolint.engine import build_context, execute
from ontolint.policy import Policy
from ontolint.rules import skos, skos_integrity, support

EX = "http://example.org/"


def _fired(body: str, **options: Any) -> list[tuple[str, str]]:
    ctx = build_context(graph(body), None, Policy.from_mapping(options))
    return [(f.focus, f.message) for f in execute(ctx, ["LEX013"]).findings]


def test_owning_term_beyond_depth_without_named_owner_is_node() -> None:
    g = Graph()
    p = URIRef(EX + "p")
    chain = [BNode(f"c{i}") for i in range(support.OWNER_DEPTH + 3)]
    for upper, lower in zip(chain[1:], chain, strict=False):
        g.add((upper, p, lower))
    assert support.owning_term(g, chain[0]) is chain[0]


def test_iri_scan_repeated_and_non_iri_terms() -> None:
    g = Graph()
    good = URIRef(EX + "ok")
    g.add((good, URIRef(EX + "p"), good))
    g.add((good, URIRef(EX + "q"), Literal("bad iri {")))
    assert shacl._first_unserialisable_iri(g) is None
    g.add((good, URIRef(EX + "r"), URIRef(EX + "bad{")))
    assert shacl._first_unserialisable_iri(g) == EX + "bad{"


def test_walk_list_stops_at_cell_outside_list() -> None:
    lists = shacl._Lists("g", {}, set())
    assert shacl._walk_list(URIRef(EX + "x"), lists, strict=True) == 0
    assert lists.reached == set()


def test_check_graph_default_is_strict() -> None:
    g = Graph()
    cells = [BNode(f"n{i}") for i in range(shacl.MAX_LIST_LENGTH + 1)]
    for a, b in zip(cells, [*cells[1:], RDF.nil], strict=True):
        g.add((a, RDF.first, Literal("x")))
        g.add((a, RDF.rest, b))
    try:
        check_graph(g, "g")
    except shacl.ShapesRejected as err:
        assert "longer than" in str(err)
    else:
        raise AssertionError("expected rejection")
    check_graph(g, "g", strict=False)


def test_shared_tail_in_data_graph_not_diagnosed() -> None:
    g = Graph()
    tail, a, b = BNode("t"), BNode("a"), BNode("b")
    g.add((tail, RDF.first, Literal(1)))
    g.add((tail, RDF.rest, RDF.nil))
    for head in (a, b):
        g.add((head, RDF.first, Literal(0)))
        g.add((head, RDF.rest, tail))
    check_graph(g, "data graph", strict=False)
    try:
        check_graph(g, "g")
    except shacl.ShapesRejected as err:
        assert "shared" in str(err)
    else:
        raise AssertionError("expected rejection")


def _shared_tail_graph() -> Graph:
    g = Graph()
    tail = BNode("t")
    g.add((tail, RDF.first, Literal(1)))
    g.add((tail, RDF.rest, RDF.nil))
    for name in "ab":
        head = BNode(name)
        g.add((head, RDF.first, Literal(0)))
        g.add((head, RDF.rest, tail))
    return g


def test_pyshacl_failure_on_data_graph_with_shared_tail_is_reraised(monkeypatch: pytest.MonkeyPatch) -> None:
    import pyshacl  # noqa: PLC0415

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(pyshacl, "validate", boom)
    try:
        shacl.shacl_issues(_shared_tail_graph(), Graph())
    except shacl.ShapesRejected:
        raise AssertionError("a shared tail is legal in the data graph") from None
    except RuntimeError as err:
        assert str(err) == "boom"
    else:
        raise AssertionError("expected the pySHACL error")


def test_lex013_predicate_both_label_and_description_rejects_value_nodes() -> None:
    extra = "https://example.test/onto#both"
    body = f'ex:A a owl:Class ; <{extra}> [ rdf:value "text" ] .'
    found = _fired(body, extra_label_predicates=[extra], extra_definition_predicates=[extra])
    assert found == [(BASE + "A", f"{extra} value is not a literal.")]


def test_lex013_description_only_predicate_accepts_value_nodes() -> None:
    extra = "https://example.test/onto#desc"
    body = f'ex:A a owl:Class ; <{extra}> [ rdf:value "text" ] .'
    assert _fired(body, extra_definition_predicates=[extra]) == []


def test_schemes_of_ignores_non_iri_endpoints() -> None:
    g = Graph()
    scheme, concept = URIRef(EX + "s"), URIRef(EX + "c")
    g.add((scheme, SKOS.hasTopConcept, BNode("c")))
    g.add((BNode("s"), SKOS.hasTopConcept, concept))
    g.add((concept, SKOS.inScheme, Literal("s")))
    g.add((BNode("c2"), SKOS.topConceptOf, scheme))
    assert dict(skos_integrity._schemes_of(g)) == {}
    g.add((scheme, SKOS.hasTopConcept, concept))
    assert dict(skos_integrity._schemes_of(g)) == {concept: {scheme}}


def test_needs_label_returns_real_booleans() -> None:
    g = Graph()
    c = URIRef(EX + "c")
    ctx: Any = SimpleNamespace(g=g, labels=(RDFS.label,))
    g.add((c, SKOS.historyNote, Literal("retired")))
    assert skos._needs_label(ctx, c) is False
    g.remove((c, SKOS.historyNote, None))
    assert skos._needs_label(ctx, c) is True
    g.add((c, RDFS.label, Literal("x")))
    assert skos._needs_label(ctx, c) is False


def test_obo008_parentless_class_stays_flagged_beside_unknown_ancestors() -> None:
    g = Graph()
    a, b, u = (URIRef(EX + n) for n in "abu")
    for cls in (a, b):
        g.add((cls, RDF.type, OWL.Class))
    g.add((b, RDFS.subClassOf, u))
    g.add((u, RDFS.subClassOf, OWL.Thing))
    result = Linter(g, None).execute(["OBO008"])
    assert [f.focus for f in result.findings] == [str(a)]
