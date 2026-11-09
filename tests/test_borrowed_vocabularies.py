"""Annotation properties borrowed from well-known vocabularies are not the linted ontology's terms.

OWL 2 DL requires a file to declare the annotation properties it uses (SEM001 reports them otherwise),
so a small module declares ``skos:definition``, ``dcterms:title``, ... next to its own terms.  When the
ontology IRI owns none of the terms and no namespace dominates, ownership used to fall back to "own
everything" and the borrowed declarations drew label, definition and namespace findings.
"""

from __future__ import annotations

import pytest
from rdflib import Graph, URIRef

from ontolint.engine import build_context, execute
from ontolint.ownership import Ownership, OwnershipMode, is_well_known
from ontolint.policy import Policy

PREFIXES = """\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix dct: <http://purl.org/dc/terms/> .
@prefix dcat: <http://www.w3.org/ns/dcat#> .
@prefix obo: <http://purl.obolibrary.org/obo/> .
@prefix ex: <https://example.test/ontology/core#> .
"""
# The layout seen in practice: the header IRI (…/meta) owns none of the terms (…/core#), five own
# terms, seven borrowed annotation properties declared for OWL 2 DL.
MODULE = """\
<https://example.test/ontology/meta> a owl:Ontology ;
    dct:title "Meta module"@en ; dct:description "Shared annotation properties."@en ;
    dct:creator "Someone" ; dct:created "2026-10-19" ; dcat:contactPoint <mailto:someone@example.test> .
skos:definition a owl:AnnotationProperty .
dct:title a owl:AnnotationProperty .
dct:description a owl:AnnotationProperty .
dct:creator a owl:AnnotationProperty .
dct:created a owl:AnnotationProperty .
dcat:contactPoint a owl:AnnotationProperty .
obo:IAO_0000115 a owl:AnnotationProperty ; rdfs:label "definition"@en .
ex:Status a owl:Class ; rdfs:label "Status"@en ; skos:definition "How firm a term is."@en .
ex:status a owl:AnnotationProperty ; rdfs:label "status"@en ; skos:definition "Points at a Status."@en .
ex:note a owl:AnnotationProperty ; rdfs:label "note"@en ; skos:definition "A note."@en .
ex:source a owl:AnnotationProperty ; rdfs:label "source"@en ; skos:definition "A source."@en .
ex:capture a owl:AnnotationProperty ; rdfs:label "capture"@en ; skos:definition "A capture."@en .
"""
BORROWED = (
    "http://www.w3.org/2004/02/skos/core#definition",
    "http://purl.org/dc/terms/title",
    "http://purl.org/dc/terms/description",
    "http://purl.org/dc/terms/creator",
    "http://purl.org/dc/terms/created",
    "http://www.w3.org/ns/dcat#contactPoint",
    "http://purl.obolibrary.org/obo/IAO_0000115",
)
RULES = ("LEX001", "LEX002", "METRIC003", "IRI005", "IRI008")


def _findings(body: str, rules: tuple[str, ...] = RULES) -> list[tuple[str, str]]:
    graph = Graph().parse(data=PREFIXES + body, format="turtle")
    ctx = build_context(graph, None, Policy())
    return sorted((f.rule, f.focus) for f in execute(ctx, list(rules)).findings)


def test_borrowed_annotation_properties_draw_no_finding() -> None:
    assert _findings(MODULE) == []


def test_borrowed_terms_are_not_owned_and_the_own_namespace_is() -> None:
    graph = Graph().parse(data=PREFIXES + MODULE, format="turtle")
    ctx = build_context(graph, None, Policy())
    ownership = ctx.context.ownership
    assert ownership.dominant_namespace == "https://example.test/ontology/core#"
    assert not any(ownership.owns(URIRef(iri)) for iri in BORROWED)
    assert {str(t) for t in ctx.terms} == {
        f"https://example.test/ontology/core#{name}" for name in ("Status", "status", "note", "source", "capture")
    }


def test_own_terms_are_still_judged() -> None:
    assert _findings(MODULE + "ex:undocumented a owl:AnnotationProperty .\n", ("LEX001", "LEX002")) == [
        ("LEX001", "https://example.test/ontology/core#undocumented"),
        ("LEX002", "https://example.test/ontology/core#undocumented"),
    ]


def test_without_a_dominant_namespace_borrowed_terms_stay_foreign() -> None:
    # Own terms in two namespaces, neither above half: the fallback owns everything except the borrowed.
    ownership = Ownership.for_terms(
        None,
        [],
        [URIRef("https://a.test/ns#A"), URIRef("https://b.test/ns#B"), URIRef("http://purl.org/dc/terms/title")],
    )
    assert ownership.mode is OwnershipMode.ALL
    assert ownership.owns(URIRef("https://a.test/ns#A"))
    assert ownership.owns(URIRef("https://b.test/ns#B"))
    assert not ownership.owns(URIRef("http://purl.org/dc/terms/title"))


def test_a_file_declaring_only_borrowed_terms_keeps_owning_them() -> None:
    ownership = Ownership.for_terms(
        None, [], [URIRef("http://purl.org/dc/terms/title"), URIRef("http://www.w3.org/2004/02/skos/core#note")]
    )
    assert ownership.mode is OwnershipMode.ALL
    assert ownership.owns(URIRef("http://purl.org/dc/terms/title"))


def test_the_vocabulary_itself_owns_its_terms() -> None:
    # schema.org's own file has no ontology header owning https://schema.org/ and a few foreign terms.
    declared = [URIRef(f"https://schema.org/T{i}") for i in range(8)] + [URIRef("https://other.test/ns#X")]
    ownership = Ownership.for_terms(None, [], declared)
    assert ownership.dominant_namespace == "https://schema.org/"
    assert ownership.owns(URIRef("https://schema.org/T0"))
    # and so does a header naming it: SKOS linted on its own
    skos = Ownership.for_terms(
        None,
        [URIRef("http://www.w3.org/2004/02/skos/core")],
        [URIRef("http://www.w3.org/2004/02/skos/core#Concept"), URIRef("http://purl.org/dc/terms/title")],
    )
    assert skos.owns(URIRef("http://www.w3.org/2004/02/skos/core#Concept"))
    assert not skos.owns(URIRef("http://purl.org/dc/terms/title"))


@pytest.mark.parametrize(
    ("iri", "expected"),
    [
        ("http://purl.obolibrary.org/obo/IAO_0000115", True),
        ("http://purl.obolibrary.org/obo/ENVO_00000001", False),
        ("https://schema.org/name", True),
        ("http://purl.org/dc/terms/title", True),
        ("http://purl.org/dc/termsX/title", False),
    ],
)
def test_is_well_known(iri: str, expected: bool) -> None:  # noqa: FBT001 -- parametrised expectation
    assert is_well_known(URIRef(iri)) is expected
    assert not is_well_known("http://purl.org/dc/terms/title")  # a str is not an IRI node
