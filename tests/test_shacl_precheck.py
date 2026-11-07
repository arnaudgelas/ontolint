"""The SHACL pre-check refuses graphs that crash or stall pySHACL, and changes nothing for valid ones."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import RDF

from ontolint import Linter
from ontolint.adapters import shacl
from ontolint.adapters.shacl import MAX_LIST_LENGTH, ShapesRejected, check_graph, shacl_issues
from ontolint.models import ExecutionStatus

FIXTURES = Path(__file__).parent / "fixtures"
PREFIXES = (
    "@prefix sh: <http://www.w3.org/ns/shacl#> . "
    "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> . @prefix : <http://e/> .\n"
)
LIST_LEN = 200


def _graph(body: str) -> Graph:
    return Graph().parse(data=PREFIXES + body, format="turtle")


def _language_shapes(count: int) -> Graph:
    langs = " ".join(f'"l{i}"' for i in range(count))
    return _graph(f":S a sh:NodeShape ; sh:targetNode :a ; sh:languageIn ({langs}) .")


def test_401_item_list_is_rejected() -> None:
    with pytest.raises(ShapesRejected, match="longer than 400"):
        check_graph(_language_shapes(MAX_LIST_LENGTH + 1), "shapes graph")


def test_400_item_list_is_accepted() -> None:
    check_graph(_language_shapes(MAX_LIST_LENGTH), "shapes graph")


def test_ten_200_item_lists_are_rejected() -> None:
    items = " ".join(f'"l{i}"' for i in range(LIST_LEN))
    body = "".join(f":S{n} a sh:NodeShape ; sh:languageIn ({items}) .\n" for n in range(10))
    with pytest.raises(ShapesRejected, match="too many long"):
        check_graph(_graph(body), "shapes graph")


def test_pure_rest_cycle_is_rejected() -> None:
    graph = _graph("_:a rdf:first 1 ; rdf:rest _:b . _:b rdf:first 2 ; rdf:rest _:a .")
    with pytest.raises(ShapesRejected, match="cyclic"):
        check_graph(graph, "shapes graph")


HEAD_INTO_CYCLE = "_:h rdf:first 0 ; rdf:rest _:a . _:a rdf:first 1 ; rdf:rest _:b . _:b rdf:first 2 ; rdf:rest _:a ."


@pytest.mark.parametrize("strict", [True, False])
def test_head_into_cycle_is_rejected_in_every_mode(strict: bool) -> None:
    with pytest.raises(ShapesRejected, match="cyclic"):
        check_graph(_graph(HEAD_INTO_CYCLE), "any graph", strict=strict)


def test_cell_with_two_rests_is_rejected() -> None:
    graph = _graph("_:a rdf:first 1 ; rdf:rest rdf:nil , _:b . _:b rdf:first 2 ; rdf:rest rdf:nil .")
    with pytest.raises(ShapesRejected, match="several rdf:rest"):
        check_graph(graph, "shapes graph")


def test_list_shared_by_two_heads_is_rejected() -> None:
    body = "_:x rdf:first 1 ; rdf:rest _:t . _:y rdf:first 2 ; rdf:rest _:t . _:t rdf:first 3 ; rdf:rest rdf:nil ."
    with pytest.raises(ShapesRejected, match="shared"):
        check_graph(_graph(body), "shapes graph")


SHARED_TAIL = "_:x rdf:first 1 ; rdf:rest _:t . _:y rdf:first 2 ; rdf:rest _:t . _:t rdf:first 3 ; rdf:rest rdf:nil ."


def test_shared_tail_is_legal_rdf_and_only_the_shapes_graph_rejects_it() -> None:
    check_graph(_graph(SHARED_TAIL), "data graph", strict=False)
    with pytest.raises(ShapesRejected, match="shared"):
        check_graph(_graph(SHARED_TAIL), "shapes graph", strict=True)


def test_data_graph_may_hold_a_large_enumeration() -> None:
    """The quadratic cost was measured on the shapes graph only; data graphs keep their long lists."""
    check_graph(_language_shapes(MAX_LIST_LENGTH * 5), "data graph", strict=False)
    with pytest.raises(ShapesRejected, match="longer than 400"):
        check_graph(_language_shapes(MAX_LIST_LENGTH * 5), "shapes graph", strict=True)


def test_check_graph_rejects_a_pure_cycle_in_any_mode() -> None:
    graph = _graph("_:a rdf:first 1 ; rdf:rest _:b . _:b rdf:first 2 ; rdf:rest _:a .")
    with pytest.raises(ShapesRejected, match="cyclic"):
        check_graph(graph, "data graph", strict=False)


def _with_bad_iri() -> Graph:
    graph = Graph()
    graph.add((URIRef("http://e/s"), URIRef("http://e/a}b"), Literal("x")))
    return graph


def test_unserialisable_iri_in_shapes_is_rejected() -> None:
    with pytest.raises(ShapesRejected, match="IRI"):
        check_graph(_with_bad_iri(), "shapes graph")
    with pytest.raises(ShapesRejected, match="shapes graph"):
        shacl_issues(Graph(), _with_bad_iri())


def test_odd_iri_in_the_data_graph_is_accepted_when_no_violation_mentions_it() -> None:
    """IRI001 reports odd IRIs; SHACL validation of the rest of the file must still run."""
    assert shacl_issues(_with_bad_iri(), _graph(":S a sh:NodeShape .")) == []


CRASHING_SHAPES = ":S a sh:NodeShape ; sh:targetClass :C ; sh:property [ sh:path :p ; sh:minCount 1 ] ."


def _crashing_data() -> Graph:
    data = _graph("_:b a :C .")
    (node,) = data.subjects(RDF.type, URIRef("http://e/C"))
    data.add((node, URIRef("http://e/x}y"), Literal(1)))
    return data


def test_pyshacl_failure_caused_by_an_odd_data_iri_is_reported_as_shapes_rejected() -> None:
    """The violation message must describe a blank node carrying the odd IRI, which makes rdflib raise."""
    with pytest.raises(ShapesRejected, match=r"data graph contains an IRI that cannot be serialised.*pySHACL failed"):
        shacl_issues(_crashing_data(), _graph(CRASHING_SHAPES))


CYCLE = "_:a rdf:first 1 ; rdf:rest _:b . _:b rdf:first 2 ; rdf:rest _:a ."


def test_a_cyclic_list_in_the_data_graph_is_accepted_until_pyshacl_fails_on_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pyshacl  # noqa: PLC0415 -- same lazy import as the adapter.

    data = _graph(CYCLE)
    assert shacl_issues(data, _graph(":S a sh:NodeShape .")) == []

    def boom(*args: object, **kwargs: object) -> None:
        raise ValueError("List contains a recursive rdf:rest reference")

    monkeypatch.setattr(pyshacl, "validate", boom)
    with pytest.raises(ShapesRejected, match=r"data graph contains a cyclic rdf:list.*ValueError: List contains"):
        shacl_issues(data, _graph(":S a sh:NodeShape ."))


def test_pyshacl_failure_with_clean_iris_is_not_rewritten(monkeypatch: pytest.MonkeyPatch) -> None:
    import pyshacl  # noqa: PLC0415 -- same lazy import as the adapter.

    def boom(*args: object, **kwargs: object) -> None:
        raise KeyError("unrelated")

    monkeypatch.setattr(pyshacl, "validate", boom)
    with pytest.raises(KeyError, match="unrelated"):
        shacl_issues(_graph("_:b a :C ."), _graph(CRASHING_SHAPES))


@pytest.mark.filterwarnings("ignore::pyshacl.errors.ShapeRecursionWarning")
def test_self_referential_first_and_recursive_node_are_accepted() -> None:
    cell = BNode()
    loop = Graph()
    loop.add((cell, RDF.first, cell))
    loop.add((cell, RDF.rest, RDF.nil))
    check_graph(loop, "shapes graph")
    check_graph(_graph(":S a sh:NodeShape ; sh:targetNode :a ; sh:node :S ."), "shapes graph")
    assert shacl_issues(Graph(), _graph(":S a sh:NodeShape ; sh:targetNode :a ; sh:node :S .")) == []


@pytest.mark.parametrize(
    ("data", "shapes"), [("clean.ttl", "clean_shapes.ttl"), ("kitchen_sink.ttl", "kitchen_shapes.ttl")]
)
def test_valid_inputs_pass_and_results_are_unchanged(data: str, shapes: str, monkeypatch: pytest.MonkeyPatch) -> None:
    g, sg = Graph().parse(FIXTURES / data), Graph().parse(FIXTURES / shapes)
    check_graph(sg, "shapes graph")
    with_check = shacl_issues(g, sg)
    monkeypatch.setattr(shacl, "check_graph", lambda graph, name, *, strict=True: None)
    assert shacl_issues(g, sg) == with_check


def test_engine_reports_rejected_shapes_quickly() -> None:
    start = time.monotonic()
    result = Linter(Graph().parse(FIXTURES / "clean.ttl"), _language_shapes(1735)).execute()
    assert time.monotonic() - start < 1.0
    failed = [e for e in result.with_status(ExecutionStatus.FAILED) if e.rule_id == "SHACL001"]
    assert len(failed) == 1
    assert failed[0].detail.startswith("ShapesRejected:")
