"""Precision regressions for the OBO rules, taken from reviews of real OBO Foundry files."""

from __future__ import annotations

from rule_harness import graph

from ontolint import Linter

HEAD = """\
@prefix obo: <http://purl.obolibrary.org/obo/> .
@prefix oio: <http://www.geneontology.org/formats/oboInOwl#> .
"""
BFO_STYLE = """
<http://purl.obolibrary.org/obo/bfo.owl> a owl:Ontology ;
    <http://purl.org/dc/elements/1.1/title> "Basic Formal Ontology" ;
    <http://purl.org/dc/elements/1.1/description> "d" ;
    dcterms:license <https://creativecommons.org/licenses/by/4.0/> ;
    owl:versionIRI <http://purl.obolibrary.org/obo/bfo/2019-08-26/bfo.owl> .
obo:BFO_0000001 a owl:Class ; rdfs:label "entity" ; obo:IAO_0000600 "An elucidation." .
obo:BFO_0000002 a owl:Class ; rdfs:label "continuant" ; rdfs:subClassOf obo:BFO_0000001 ;
    obo:IAO_0000600 "Another." .
<http://purl.obolibrary.org/obo/envo#envoAstro> a owl:AnnotationProperty .
obo:RO_HOM0000001 a owl:ObjectProperty ; rdfs:label "in homology relationship with" ;
    obo:IAO_0000115 "d" ; dcterms:source "x" .
obo:BFO_0000003 a owl:Class ; rdfs:label "Kupffer cell" ; obo:IAO_0000600 "e" ;
    rdfs:subClassOf obo:BFO_0000001 .
obo:FOO_9 a owl:NamedIndividual ; owl:deprecated true .
"""


def _rules(turtle: str) -> list[str]:
    result = Linter(graph(HEAD + turtle), None).execute([f"OBO{n:03d}" for n in range(1, 13)])
    return sorted({f.rule for f in result.findings})


def test_bfo_style_ontology_is_clean() -> None:
    found = _rules(BFO_STYLE)
    assert found == [], found


def test_obsolete_term_is_exempt_from_every_term_rule() -> None:
    turtle = (
        '<http://purl.obolibrary.org/obo/pato#x> a owl:Class ; owl:deprecated true ; rdfs:label "obsolete_x" ;'
        ' obo:IAO_0100001 obo:PATO_1 ; obo:IAO_0000115 "d" .'
    )
    assert _rules(turtle) == []
