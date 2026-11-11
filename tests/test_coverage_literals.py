"""_curie shortens the four core namespaces and leaves any other IRI whole."""

from __future__ import annotations

import pytest
from rdflib import URIRef

from ontolint.rules.literals import _curie  # noqa: PLC2701 -- the helper's fallback is not reachable from a graph.


@pytest.mark.parametrize(
    ("iri", "expected"),
    [
        ("http://www.w3.org/2001/XMLSchema#integer", "xsd:integer"),
        ("http://www.w3.org/2000/01/rdf-schema#Literal", "rdfs:Literal"),
        ("http://www.w3.org/1999/02/22-rdf-syntax-ns#first", "rdf:first"),
        ("http://www.w3.org/2002/07/owl#onDatatype", "owl:onDatatype"),
        ("https://example.test/onto#custom", "https://example.test/onto#custom"),
    ],
)
def test_curie(iri: str, expected: str) -> None:
    assert _curie(URIRef(iri)) == expected
