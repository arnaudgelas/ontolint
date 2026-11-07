"""Precision regressions for the offline FAIR rules, taken from reviews of real ontology headers."""

from __future__ import annotations

from rule_harness import graph

from ontolint import Linter

IDS = ["FAIR004", "FAIR006", "FAIR007", "FAIR011", "FAIR017"]
OBO_STYLE = """
<http://purl.obolibrary.org/obo/envo.owl> a owl:Ontology ;
    dcterms:license <https://creativecommons.org/publicdomain/zero/1.0/> ;
    dcterms:creator <https://orcid.org/0000-0002-1825-0097> ;
    dcterms:contributor <https://orcid.org/0000-0002-1694-233X>, "Free text name" ;
    owl:versionIRI <http://purl.obolibrary.org/obo/envo/releases/2026-10-23/envo.owl> .
"""
W3C_STYLE = """
<http://www.w3.org/ns/dcat> a owl:Ontology ;
    dcterms:license <https://creativecommons.org/licenses/by/4.0/> ;
    owl:versionIRI <http://www.w3.org/ns/dcat3> .
<http://www.w3.org/2006/time> a owl:Ontology ;
    owl:versionIRI <http://www.w3.org/2006/time#2016> ;
    dcterms:license <https://creativecommons.org/licenses/by/4.0/> .
<http://www.w3.org/ns/org#> a owl:Ontology ;
    dcterms:license <http://www.opendatacommons.org/licenses/pddl/1.0/> .
<http://xmlns.com/foaf/0.1/> a owl:Ontology .
"""


def _rules(turtle: str) -> list[str]:
    result = Linter(graph(turtle), None).execute(IDS)
    return sorted({f.rule for f in result.findings})


def test_obo_foundry_header_is_clean() -> None:
    found = _rules(OBO_STYLE)
    assert found == [], found


def test_w3c_and_foaf_namespaces_are_clean() -> None:
    found = _rules(W3C_STYLE)
    assert found == [], found


def test_rules_are_silent_without_an_ontology_header_or_metadata() -> None:
    assert _rules('ex:A a owl:Class ; rdfs:label "A" ; dcterms:license "MIT" ; owl:deprecated true .') == []
    assert _rules("<http://purl.org/example/o> a owl:Ontology .") == []
