"""Source positions survive escapes, lost prefixes, truncated text and odd IRIs; a blank node is found by its id."""

from __future__ import annotations

import pytest
from rdflib import BNode, Graph, URIRef

from ontolint.models import Finding
from ontolint.rules.support import stable_blank_id
from ontolint.source_locations import build_source_index

X = "http://x/"
PUBLIC_ID = "file:///a"


def _positions(data: str, fmt: str, graph: Graph | None = None) -> dict[str, tuple[int, int | None]]:
    """Parse ``data`` (unless a graph is given) and return the ``(line, column)`` of each located term."""
    if graph is None:
        graph = Graph().parse(data=data, format=fmt, publicID=PUBLIC_ID)
    index = build_source_index(data.encode(), fmt, PUBLIC_ID, graph)
    return {str(node): (found.line, found.column) for node, found in index.locations.items()}


def _finding(focus: str) -> Finding:
    return Finding("ONT001", "warning", focus, "message", "fix")


def test_a_blank_node_is_found_by_its_stable_id_beside_iris() -> None:
    graph = Graph()
    graph.add((BNode("b"), URIRef(X + "p"), URIRef(X + "t")))
    data = "_:b <http://x/p> <http://x/t> .\n"
    index = build_source_index(data.encode(), "nt", PUBLIC_ID, graph)
    by_blank, by_iri = _finding(stable_blank_id(graph, BNode("b"))), _finding(X + "p")

    found = index.for_findings(graph, [by_blank, by_iri, _finding(X + "elsewhere")])

    assert {f: (loc.line, loc.column) for f, loc in found.items()} == {by_blank: (1, 1), by_iri: (1, 5)}


def test_a_prefix_lost_to_a_namespace_declared_twice_costs_only_its_own_names() -> None:
    # rdflib keeps one prefix per namespace, so `a:` is unknown to the graph after the parse.
    located = _positions("@prefix a: <http://x/> . @prefix b: <http://x/> .\na:one b:p b:two .\n", "turtle")

    assert located == {X + "p": (2, 7), X + "two": (2, 11)}


def test_an_escaped_quote_in_a_string_does_not_end_it_early() -> None:
    located = _positions('@prefix e: <http://x/> .\ne:s e:p "a\\"b e:fake" ; e:q e:t .\n', "turtle")

    assert X + "fake" not in located
    assert located[X + "t"] == (2, 29)


def test_a_backslash_in_an_iri_does_not_end_it_early() -> None:
    located = _positions("@prefix e: <http://x/> .\n<http://x/\\u0058> e:p e:t .\n", "turtle")

    assert located[X + "t"] == (2, 23)


@pytest.mark.parametrize(
    ("data", "located"),
    [
        ("<http://x/s> <http://x/p> <http://x/unterminated", {X + "s": (1, 1), X + "p": (1, 14)}),
        ('<http://x/s> <http://x/p> "never closed', {X + "s": (1, 1), X + "p": (1, 14)}),
        ('<http://x/s> <http://x/p> """never \\" closed', {X + "s": (1, 1), X + "p": (1, 14)}),
    ],
)
def test_truncated_text_keeps_the_positions_before_the_cut(
    data: str, located: dict[str, tuple[int, int | None]]
) -> None:
    graph = Graph()
    graph.add((URIRef(X + "s"), URIRef(X + "p"), URIRef(X + "o")))

    assert _positions(data, "nt", graph) == located


def test_an_rdf_id_names_the_node_at_its_element() -> None:
    xml = (
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:e="http://x/">'
        '<rdf:Description rdf:ID="foo"><e:p>1</e:p></rdf:Description></rdf:RDF>'
    )

    assert _positions(xml, "xml") == {"file:///a#foo": (1, 86)}


def _json_ld_graph(*names: str) -> Graph:
    graph = Graph()
    for name in names:
        graph.add((URIRef(name), URIRef(X + "p"), URIRef(X + "o")))
    return graph


def test_a_json_ld_context_list_may_hold_null() -> None:
    document = '{"@context":[null,{"e":"http://x/"}],"@id":"e:a","e:p":{"@id":"e:b"}}'

    assert _positions(document, "json-ld", _json_ld_graph(X + "a", X + "b")) == {X + "a": (1, 44), X + "b": (1, 63)}


def test_a_json_ld_term_that_cannot_be_resolved_is_left_out_of_the_context() -> None:
    document = '{"@context":{"e":"http://x/","bad":"s://]"},"@id":"e:a","e:p":{"@id":"e:b"}}'

    assert _positions(document, "json-ld", _json_ld_graph(X + "a", X + "b")) == {X + "a": (1, 51), X + "b": (1, 70)}


def test_a_json_ld_id_that_cannot_be_resolved_costs_only_itself() -> None:
    document = '{"@context":{"e":"s://"},"@id":"e:]","http://x/p":{"@id":"http://x/b"}}'

    assert _positions(document, "json-ld", _json_ld_graph("s://]", X + "b")) == {X + "b": (1, 58)}
