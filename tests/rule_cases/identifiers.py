"""Cases for IRI001-IRI003."""

from __future__ import annotations

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF
from rule_harness import built, rule_cases, ttl


def _class(iri: str) -> Graph:
    g = Graph()
    g.add((URIRef(iri), RDF.type, OWL.Class))
    return g


CASES = {
    "IRI001": rule_cases(
        [
            built("whitespace in IRI", lambda: _class("https://example.test/with space")),
            built("relative IRI", lambda: _class("relative-term")),
        ],
        [ttl("absolute IRI", "ex:A a owl:Class .")],
    ),
    "IRI002": rule_cases(
        [ttl("ontology IRI ends in .owl", "<https://example.test/onto.owl> a owl:Ontology .")],
        [
            ttl("extensionless ontology IRI", "<https://example.test/onto> a owl:Ontology ."),
            ttl("extension on a term is fine", "<https://example.test/term.owl> a owl:Class ."),
            ttl("OBO PURL ontology IRI", "<http://purl.obolibrary.org/obo/envo.owl> a owl:Ontology ."),
        ],
    ),
    "IRI003": rule_cases(
        [
            ttl(
                "same local name, two namespaces",
                "<https://a.test/Same> a owl:Class . <https://b.test/Same> a owl:Class .",
            ),
            ttl("case-only collision within one kind", "ex:Agent a owl:Class . ex:agent a owl:Class ."),
        ],
        [
            ttl("distinct local names", "<https://a.test/One> a owl:Class . <https://b.test/Two> a owl:Class ."),
            ttl("class and property of the same name", "ex:Agent a owl:Class . ex:agent a owl:ObjectProperty ."),
            ttl(
                "deprecated terms",
                "<https://a.test/Same> a owl:Class ; owl:deprecated true . <https://b.test/Same> a owl:Class .",
            ),
        ],
    ),
}
