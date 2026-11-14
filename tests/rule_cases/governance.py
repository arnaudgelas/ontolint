"""Cases for GOV001-GOV003."""

from __future__ import annotations

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL
from rule_harness import BASE, Case, graph, rule_cases, ttl


def _deprecated_blank_property() -> Graph:
    """A blank property, deprecated and used: not RDF, but a graph built through the API may hold one."""
    data, prop = graph("ex:i a owl:Thing ."), BNode()
    data.add((prop, OWL.deprecated, Literal(True)))
    data.add((URIRef(BASE + "i"), prop, URIRef(BASE + "j")))
    return data


CASES = {
    "GOV001": rule_cases(
        [
            ttl(
                "deprecated class used as superclass",
                "ex:Old a owl:Class ; owl:deprecated true . ex:A a owl:Class ; rdfs:subClassOf ex:Old .",
            ),
            ttl("deprecated property used", "ex:old a owl:ObjectProperty ; owl:deprecated true . ex:i ex:old ex:j ."),
            ttl("deprecated blank node used", "_:old owl:deprecated true . ex:A a owl:Class ; ex:p _:old ."),
            ttl("deprecated blank node in a list", "_:old owl:deprecated true . ex:A a owl:Class ; ex:p ( _:old ) ."),
            Case("deprecated blank property used", build=_deprecated_blank_property),
        ],
        [
            ttl("deprecated but unused", "ex:Old a owl:Class ; owl:deprecated true ."),
            ttl("current term used", "ex:New a owl:Class . ex:A a owl:Class ; rdfs:subClassOf ex:New ."),
        ],
    ),
    "GOV002": rule_cases(
        [
            ttl("literal import target", '<https://example.test/onto> a owl:Ontology ; owl:imports "not an iri" .'),
            ttl("blank import target", "<https://example.test/onto> a owl:Ontology ; owl:imports [ ex:p 1 ] ."),
        ],
        [
            ttl(
                "IRI import target",
                "<https://example.test/onto> a owl:Ontology ; owl:imports <https://example.test/other> .",
            )
        ],
    ),
    "GOV003": rule_cases(
        [ttl("equivalent to undeclared local class", "ex:A a owl:Class ; owl:equivalentClass ex:Undeclared .")],
        [ttl("equivalent to declared class", "ex:A a owl:Class ; owl:equivalentClass ex:B . ex:B a owl:Class .")],
    ),
}
