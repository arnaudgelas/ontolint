"""Cases for GOV004, GOV008-GOV014 and GOV017 (graph-local governance metadata)."""

from __future__ import annotations

from rule_harness import BASE, rule_cases, ttl

_PREFIXES = (
    "@prefix dc: <http://purl.org/dc/elements/1.1/> .\n"
    "@prefix vs: <http://www.w3.org/2003/06/sw-vocab-status/ns#> .\n"
    "@prefix schema: <http://schema.org/> .\n"
    "@prefix obo: <http://purl.obolibrary.org/obo/> .\n"
    "@prefix foaf: <http://xmlns.com/foaf/0.1/> .\n"
    "@prefix pav: <http://purl.org/pav/> .\n"
)


def _terms(count: int, annotated: int, annotation: str) -> str:
    """``count`` local classes, the first ``annotated`` carrying ``annotation``."""
    lines = [
        f"ex:T{i} a owl:Class ; {annotation} ." if i < annotated else f"ex:T{i} a owl:Class ." for i in range(count)
    ]
    return _PREFIXES + "\n".join(lines)


def _coverage_cases(annotation: str) -> tuple[list, list]:  # type: ignore[type-arg]
    positive = [
        ttl("3 of 4 annotated", _terms(4, 3, annotation)),
        ttl("2 of 4 annotated is a majority tie", _terms(4, 2, annotation)),
    ]
    negative = [
        ttl("1 of 4 annotated", _terms(4, 1, annotation)),
        ttl("none annotated", _terms(4, 0, annotation)),
        ttl("all annotated", _terms(4, 4, annotation)),
        ttl("3 terms is below the sample", _terms(3, 2, annotation)),
    ]
    return positive, negative


_ATTRIBUTION = _coverage_cases('dcterms:creator "A"')
_DATES = _coverage_cases('dcterms:created "2024-01-01"')
_STATUS = _coverage_cases("vs:term_status 'stable'")

CASES = {
    "GOV004": rule_cases(
        [
            ttl("no contact", 'ex:o a owl:Ontology ; dcterms:creator "A" ; dcterms:license ex:l .'),
            ttl(
                "second ontology lacks contact",
                _PREFIXES + 'ex:o a owl:Ontology ; dcterms:publisher "P" . ex:p a owl:Ontology .',
            ),
        ],
        [
            ttl("publisher", _PREFIXES + 'ex:o a owl:Ontology ; dcterms:publisher "P" .'),
            ttl("contributor", _PREFIXES + 'ex:o a owl:Ontology ; dcterms:contributor "P" .'),
            ttl("dc publisher", _PREFIXES + 'ex:o a owl:Ontology ; dc:publisher "P" .'),
            ttl("dc contributor", _PREFIXES + 'ex:o a owl:Ontology ; dc:contributor "P" .'),
            ttl("foaf maintainer", _PREFIXES + "ex:o a owl:Ontology ; foaf:maintainer ex:m ."),
            ttl("foaf mbox", _PREFIXES + "ex:o a owl:Ontology ; foaf:mbox <mailto:a@b.test> ."),
            ttl("schema maintainer", _PREFIXES + "ex:o a owl:Ontology ; schema:maintainer ex:m ."),
            ttl(
                "dcat contact point and doap maintainer",
                "@prefix dcat: <http://www.w3.org/ns/dcat#> . @prefix doap: <http://usefulinc.com/ns/doap#> ."
                "ex:o a owl:Ontology ; dcat:contactPoint ex:c . ex:q a owl:Ontology ; doap:maintainer ex:m .",
            ),
            ttl("no ontology", "ex:A a owl:Class ."),
        ],
    ),
    "GOV008": rule_cases(
        [
            ttl("deprecated bare", "ex:A a owl:Class ; owl:deprecated true ."),
            ttl("deprecated property bare", "ex:p a owl:ObjectProperty ; owl:deprecated true ."),
        ],
        [
            ttl("replacement", _PREFIXES + "ex:A a owl:Class ; owl:deprecated true ; dcterms:isReplacedBy ex:B ."),
            ttl("obo replacement", _PREFIXES + "ex:A a owl:Class ; owl:deprecated true ; obo:IAO_0100001 ex:B ."),
            ttl("comment reason", "ex:A a owl:Class ; owl:deprecated true ; rdfs:comment 'merged' ."),
            ttl("history note reason", "ex:A a owl:Class ; owl:deprecated true ; skos:historyNote 'merged' ."),
            ttl("obo reason", _PREFIXES + "ex:A a owl:Class ; owl:deprecated true ; obo:IAO_0000231 'dup' ."),
            ttl("not deprecated", "ex:A a owl:Class ."),
            ttl("deprecated false", "ex:A a owl:Class ; owl:deprecated false ."),
            ttl(
                "foreign deprecated term with base",
                "ex:A a owl:Class ; owl:deprecated true .",
                base="https://other.test/",
            ),
        ],
    ),
    "GOV009": rule_cases(*_ATTRIBUTION),
    "GOV010": rule_cases(*_DATES),
    "GOV011": rule_cases(
        [
            ttl("version info, no history", 'ex:o a owl:Ontology ; owl:versionInfo "1" .'),
            ttl("version iri, no history", "ex:o a owl:Ontology ; owl:versionIRI ex:o1 ."),
        ],
        [
            ttl("unversioned", "ex:o a owl:Ontology ."),
            ttl(
                "change note on term",
                _PREFIXES + 'ex:o a owl:Ontology ; owl:versionInfo "1" . ex:A a owl:Class ; skos:changeNote "x" .',
            ),
            ttl("history note", 'ex:o a owl:Ontology ; owl:versionInfo "1" ; skos:historyNote "x" .'),
            ttl(
                "vann changes",
                "@prefix vann: <http://purl.org/vocab/vann/> ."
                'ex:o a owl:Ontology ; owl:versionInfo "1" ; vann:changes <https://x.test/log> .',
            ),
            ttl("prior version", 'ex:o a owl:Ontology ; owl:versionInfo "1" ; owl:priorVersion ex:o0 .'),
        ],
    ),
    "GOV012": rule_cases(*_STATUS),
    "GOV013": rule_cases(
        [
            ttl("subclass of obsolete class", "ex:Old a owl:DeprecatedClass . ex:A rdfs:subClassOf ex:Old ."),
            ttl("range obsolete class", "ex:Old a owl:DeprecatedClass . ex:p rdfs:range ex:Old ."),
            ttl("instance of obsolete class", "ex:Old a owl:DeprecatedClass . ex:i a ex:Old ."),
            ttl("obsolete property used", "ex:q a owl:DeprecatedProperty . ex:a ex:q ex:b ."),
            ttl("restriction on obsolete property", "ex:q a owl:DeprecatedProperty . [] owl:onProperty ex:q ."),
        ],
        [
            ttl("unused", "ex:Old a owl:DeprecatedClass ."),
            ttl(
                "label and replacement only",
                _PREFIXES
                + "ex:Old a owl:DeprecatedClass ; rdfs:label 'o' ."
                + " ex:A rdfs:seeAlso ex:Old ; dcterms:isReplacedBy ex:Old .",
            ),
            ttl("self reference", "ex:Old a owl:DeprecatedClass ; rdfs:subClassOf ex:Old ."),
            ttl(
                "obsolete refers to obsolete",
                "ex:Old a owl:DeprecatedClass . ex:Old2 a owl:DeprecatedClass ; rdfs:subClassOf ex:Old .",
            ),
            ttl(
                "referrer deprecated",
                "ex:Old a owl:DeprecatedClass . ex:A owl:deprecated true ; rdfs:subClassOf ex:Old .",
            ),
            ttl(
                "owl:deprecated true is GOV001's",
                "ex:Old a owl:DeprecatedClass ; owl:deprecated true . ex:A rdfs:subClassOf ex:Old .",
            ),
            ttl("plain class", "ex:Old a owl:Class . ex:A rdfs:subClassOf ex:Old ."),
            ttl(
                "obsolete property referrer deprecated",
                "ex:q a owl:DeprecatedProperty . ex:a ex:q ex:b ; owl:deprecated true .",
            ),
            ttl(
                "obsolete property used by obsolete",
                "ex:q a owl:DeprecatedProperty . ex:z a owl:DeprecatedClass . ex:z ex:q ex:b .",
            ),
        ],
    ),
    "GOV014": rule_cases(
        [
            ttl(
                "foreign class with subclass axiom",
                "<https://other.test/Thing> a owl:Class ; rdfs:subClassOf ex:A .",
                base=BASE,
            ),
            ttl(
                "foreign property with domain",
                "<https://other.test/p> a owl:ObjectProperty ; rdfs:domain ex:A .",
                base=BASE,
            ),
            ttl(
                "foreign concept with equivalence",
                "<https://other.test/c> a skos:Concept ; owl:equivalentClass ex:A .",
                base=BASE,
            ),
        ],
        [
            ttl("foreign stub without axioms", "<https://other.test/Thing> a owl:Class .", base=BASE),
            ttl("no base", "<https://other.test/Thing> a owl:Class ; rdfs:subClassOf ex:A ."),
            ttl("local axioms", "ex:B a owl:Class ; rdfs:subClassOf ex:A .", base=BASE),
            ttl("core namespace term", "owl:Thing a owl:Class ; rdfs:subClassOf ex:A .", base=BASE),
            ttl("undeclared foreign subject", "<https://other.test/Thing> rdfs:subClassOf ex:A .", base=BASE),
        ],
    ),
    "GOV017": rule_cases(
        [
            ttl("version info, no review", 'ex:o a owl:Ontology ; owl:versionInfo "1" .'),
            ttl("version iri, no review", "ex:o a owl:Ontology ; owl:versionIRI ex:o1 ."),
        ],
        [
            ttl("unversioned", "ex:o a owl:Ontology ."),
            ttl("date accepted", 'ex:o a owl:Ontology ; owl:versionInfo "1" ; dcterms:dateAccepted "2024-01-01" .'),
            ttl(
                "term reviewed", _PREFIXES + 'ex:o a owl:Ontology ; owl:versionInfo "1" . ex:A schema:reviewedBy ex:r .'
            ),
            ttl("curated by", _PREFIXES + 'ex:o a owl:Ontology ; owl:versionInfo "1" ; pav:curatedBy ex:r .'),
        ],
    ),
}
