"""Cases for ONT001-ONT006."""

from __future__ import annotations

from rule_harness import rule_cases, ttl

ONT = "<https://example.test/onto> a owl:Ontology"

CASES = {
    "ONT001": rule_cases(
        [ttl("no owl:Ontology", "ex:A a owl:Class .")],
        [ttl("ontology declared", f"{ONT} .")],
    ),
    "ONT002": rule_cases(
        [ttl("two ontologies", f"{ONT} . <https://example.test/other> a owl:Ontology .")],
        [ttl("one ontology", f"{ONT} .")],
    ),
    "ONT003": rule_cases(
        [ttl("no license", f"{ONT} .")],
        [ttl("dcterms:license", f"{ONT} ; dcterms:license <https://example.test/license> .")],
    ),
    "ONT004": rule_cases(
        [ttl("no version", f"{ONT} .")],
        [ttl("versionInfo", f'{ONT} ; owl:versionInfo "1.0" .')],
    ),
    "ONT005": rule_cases(
        [
            ttl("no provenance", f"{ONT} ."),
            ttl("creator without created", f'{ONT} ; dcterms:creator "me" .'),
        ],
        [ttl("creator and created", f'{ONT} ; dcterms:creator "me" ; dcterms:created "2026-01-01" .')],
    ),
    "ONT006": rule_cases(
        [ttl("no description", f"{ONT} .")],
        [ttl("rdfs:comment", f'{ONT} ; rdfs:comment "An ontology." .')],
    ),
}
