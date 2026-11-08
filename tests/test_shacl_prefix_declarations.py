"""A SHACL-SPARQL prefix declaration (``owl:Ontology`` plus ``sh:declare``) is not a second ontology."""

from __future__ import annotations

from rdflib import Graph

from ontolint import Linter

# The SHACL recommendation declares SPARQL prefixes on an owl:Ontology node; next to the real ontology header
# of a shapes file that node is a prefix declaration, not a second ontology.
PREFIX_DECLARATION = """@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> . @prefix ex: <https://example.test/> .
@prefix dct: <http://purl.org/dc/terms/> .
<https://example.test/shapes> a owl:Ontology ; dct:title "Shapes"@en .
<https://example.test/shapes#Prefixes> a owl:Ontology ;
  sh:declare [ sh:prefix "ex" ; sh:namespace "https://example.test/"^^xsd:anyURI ] .
ex:S a sh:NodeShape ; sh:targetClass ex:K ;
  sh:property [ sh:path ex:p ; sh:minCount 1 ] , [ sh:path ex:q ; sh:maxCount 1 ] ,
    [ sh:path ex:r ; sh:datatype xsd:string ] ;
  sh:sparql [ sh:select "SELECT $this WHERE { $this ex:p ex:p }" ;
    sh:prefixes <https://example.test/shapes#Prefixes> ] .
"""


def _rules(turtle: str) -> set[str]:
    return {
        f.rule for f in Linter(Graph().parse(data=turtle, format="turtle")).execute(["ONT", "IRI", "METRIC"]).findings
    }


def test_a_shacl_prefix_declaration_is_not_a_second_ontology() -> None:
    assert _rules(PREFIX_DECLARATION).isdisjoint({"ONT002", "IRI016", "METRIC013"})


def test_a_real_second_ontology_is_still_reported() -> None:
    second = PREFIX_DECLARATION + '<https://example.test/other> a owl:Ontology ; dct:title "Other"@en .\n'
    assert "ONT002" in _rules(second)


def test_a_lone_ontology_that_declares_prefixes_is_still_the_ontology() -> None:
    lone = """@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
<https://example.test/o#x> a owl:Ontology ;
  sh:declare [ sh:prefix "ex" ; sh:namespace "https://example.test/"^^xsd:anyURI ] .
"""
    assert "IRI016" in _rules(lone)
