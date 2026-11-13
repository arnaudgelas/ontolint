"""Pin the last surviving mutants of the rule helpers (round 5)."""

from __future__ import annotations

from rdflib import BNode, Graph, URIRef
from rdflib.namespace import RDF, RDFS
from rule_harness import BASE, graph

from ontolint import Linter
from ontolint.engine import build_context
from ontolint.policy import Policy
from ontolint.rules import class_heuristics, classes, governance, measurements, owl, support

EX = "http://example.org/ns#"


def _ctx(g: Graph):  # noqa: ANN202
    return build_context(g, None, Policy())


def _focus(rule: str, turtle: str, depth_limit: int = 10) -> list[str]:
    result = Linter(graph(turtle), depth_limit=depth_limit).execute([rule])
    return sorted(f.focus.removeprefix(BASE) for f in result.findings)


def test_metaclasses_ignore_blank_subclasses() -> None:
    g = Graph()
    g.add((URIRef(EX + "Meta"), RDFS.subClassOf, RDFS.Class))
    g.add((BNode("b"), RDFS.subClassOf, RDFS.Class))
    assert class_heuristics._metaclasses(_ctx(g)) == {URIRef(EX + "Meta")}


def test_metaclasses_terminate_on_cycles() -> None:
    g = Graph()
    a, b = URIRef(EX + "A"), URIRef(EX + "B")
    for s, o in ((a, RDFS.Class), (b, a), (a, b)):
        g.add((s, RDFS.subClassOf, o))
    assert class_heuristics._metaclasses(_ctx(g)) == {a, b}


def test_has_individuals_false_without_classes() -> None:
    assert classes._has_individuals(_ctx(Graph())) is False


def _populated(owned: int, populated: int) -> str:
    turtle = "".join(f"ex:C{i} a owl:Class . " for i in range(owned))
    return turtle + "".join(f"ex:i{i} a ex:C{i} . " for i in range(populated))


def test_cls002_quarter_share_is_populated_boundary() -> None:
    assert _focus("CLS002", _populated(4, 1)) == ["C1", "C2", "C3"]
    assert _focus("CLS002", _populated(5, 1)) == []


def test_cls005_reports_deep_class_under_cyclic_parent() -> None:
    t = (
        "ex:X a owl:Class . ex:Y a owl:Class . ex:X rdfs:subClassOf ex:Y . ex:Y rdfs:subClassOf ex:X . "
        "ex:D a owl:Class ; rdfs:subClassOf ex:X . ex:E a owl:Class ; rdfs:subClassOf ex:D . "
        "ex:F a owl:Class ; rdfs:subClassOf ex:E ."
    )
    assert _focus("CLS005", t, depth_limit=1) == ["D"]


def test_cls005_cyclic_nodes_never_reported_even_below_zero() -> None:
    t = (
        "ex:X a owl:Class . ex:Y a owl:Class . ex:X rdfs:subClassOf ex:Y . ex:Y rdfs:subClassOf ex:X . "
        "ex:L a owl:Class ."
    )
    assert _focus("CLS005", t, depth_limit=-1) == ["L"]


def test_list_owners_skip_first_and_revisited_rest() -> None:
    g = Graph()
    c1, c2, item = BNode("c1"), BNode("c2"), URIRef(EX + "T")
    s, p = URIRef(EX + "s"), URIRef(EX + "p")
    g.add((c1, RDF.first, item))
    g.add((c1, RDF.rest, c2))
    g.add((c2, RDF.rest, c1))
    g.add((s, p, c1))
    ctx = _ctx(g)
    assert governance._list_owners(ctx, item) == set()
    assert governance._list_owners(ctx, c1) == {(s, p)}


def test_structural_blank_is_false_for_non_blank() -> None:
    assert measurements._is_structural_blank(Graph(), URIRef(EX + "a")) is False


def test_namespace_of_boundaries() -> None:
    assert owl.namespace_of("http://a/b") == "http://a/"
    assert owl.namespace_of("http://a#b") == "http://a#"
    assert owl.namespace_of("/x") == "/"
    assert owl.namespace_of("#x") == "#"
    assert owl.namespace_of("abc") == "abc"


def test_owning_term_without_parents_is_node() -> None:
    b = BNode("lonely")
    assert support.owning_term(Graph(), b) is b


def test_owning_term_survives_blank_self_loop_and_cycle() -> None:
    g = Graph()
    b1, b2, owner = BNode("b1"), BNode("b2"), URIRef(EX + "O")
    p = URIRef(EX + "p")
    g.add((b1, p, b1))
    g.add((b2, p, b1))
    g.add((b1, p, b2))
    assert support.owning_term(g, b1) is b1
    g.add((owner, p, b2))
    assert support.owning_term(g, b1) == owner


def test_content_digest_depth_and_cycle_bounds() -> None:
    g = Graph()
    outer, inner = BNode("o"), BNode("i")
    p = URIRef(EX + "p")
    g.add((outer, p, inner))
    assert support._content_digest(g, outer, 0, frozenset()) == "B"
    assert support._content_digest(g, outer, 1, frozenset()) == f"B({p}>B)"
    assert support._content_digest(g, outer, 2, frozenset()) == f"B({p}>B())"
    g.add((inner, p, outer))
    assert support._content_digest(g, outer, 5, frozenset()) == f"B({p}>B({p}>B))"
