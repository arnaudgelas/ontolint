"""Cases for GOV001-GOV003."""

from __future__ import annotations

from rule_harness import rule_cases, ttl

CASES = {
    "GOV001": rule_cases(
        [
            ttl(
                "deprecated class used as superclass",
                "ex:Old a owl:Class ; owl:deprecated true . ex:A a owl:Class ; rdfs:subClassOf ex:Old .",
            ),
            ttl("deprecated property used", "ex:old a owl:ObjectProperty ; owl:deprecated true . ex:i ex:old ex:j ."),
        ],
        [
            ttl("deprecated but unused", "ex:Old a owl:Class ; owl:deprecated true ."),
            ttl("current term used", "ex:New a owl:Class . ex:A a owl:Class ; rdfs:subClassOf ex:New ."),
        ],
    ),
    "GOV002": rule_cases(
        [ttl("literal import target", '<https://example.test/onto> a owl:Ontology ; owl:imports "not an iri" .')],
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
