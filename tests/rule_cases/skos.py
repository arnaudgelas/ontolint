"""Cases for SKOS001-SKOS006."""

from __future__ import annotations

from rule_harness import BASE, rule_cases, ttl

OTHER = "@prefix o: <http://other.test/> .\n"

CASES = {
    "SKOS001": rule_cases(
        [
            ttl("two prefLabels in a language", 'ex:c a skos:Concept ; skos:prefLabel "a"@en, "b"@en .'),
            ttl("tags differ only in case", 'ex:c a skos:Concept ; skos:prefLabel "a"@en, "b"@EN .'),
            ttl("two untagged prefLabels", 'ex:c a skos:Concept ; skos:prefLabel "a", "b"^^xsd:string .'),
        ],
        [
            ttl("one prefLabel per language", 'ex:c a skos:Concept ; skos:prefLabel "a"@en, "a"@fr .'),
            ttl("same label, tag case differs", 'ex:c a skos:Concept ; skos:prefLabel "a"@en, "a"@EN .'),
            ttl("same label, plain and xsd:string", 'ex:c a skos:Concept ; skos:prefLabel "a", "a"^^xsd:string .'),
            ttl("one untagged and one tagged", 'ex:c a skos:Concept ; skos:prefLabel "a", "b"@en .'),
            ttl("IRI value is not a label", 'ex:c a skos:Concept ; skos:prefLabel ex:x, "a"@en .'),
            ttl("not a concept", 'ex:c a owl:Class ; skos:prefLabel "a"@en, "b"@en .'),
            ttl(
                "concept not owned",
                OTHER + 'o:c a skos:Concept ; skos:prefLabel "a"@en, "b"@en .',
                base=BASE,
            ),
        ],
    ),
    "SKOS002": rule_cases(
        [
            ttl(
                "same literal as pref and alt label",
                'ex:c a skos:Concept ; skos:prefLabel "a"@en ; skos:altLabel "a"@en .',
            ),
            ttl("untagged pref and hidden label", 'ex:c skos:prefLabel "a" ; skos:hiddenLabel "a" .'),
            ttl("alt and hidden label of a non-concept", 'ex:x skos:altLabel "a"@en ; skos:hiddenLabel "a"@en .'),
            ttl("tag case differs", 'ex:c skos:prefLabel "a"@en ; skos:altLabel "a"@EN .'),
            ttl("plain and xsd:string", 'ex:c skos:prefLabel "a" ; skos:altLabel "a"^^xsd:string .'),
            ttl("blank node", '[] skos:prefLabel "a" ; skos:altLabel "a" .'),
            ttl("blank value", "ex:c skos:prefLabel _:v ; skos:altLabel _:v . _:v ex:p 1 ."),
        ],
        [
            ttl("distinct literals", 'ex:c a skos:Concept ; skos:prefLabel "a"@en ; skos:altLabel "b"@en .'),
            ttl("same text, other language", 'ex:c skos:prefLabel "a"@en ; skos:altLabel "a"@fr .'),
            ttl("same text, untagged and tagged", 'ex:c skos:prefLabel "a" ; skos:altLabel "a"@en .'),
            ttl("repeated in one property", 'ex:c skos:altLabel "a"@en, "a"@EN .'),
            ttl(
                "resource not owned",
                OTHER + 'o:c a skos:Concept ; skos:prefLabel "a"@en ; skos:altLabel "a"@en .',
                base=BASE,
            ),
        ],
    ),
    "SKOS003": rule_cases(
        [
            ttl("broader cycle", "ex:a a skos:Concept ; skos:broader ex:b . ex:b a skos:Concept ; skos:broader ex:a ."),
            ttl("self broader", "ex:a a skos:Concept ; skos:broader ex:a ."),
        ],
        [ttl("acyclic broader", "ex:a a skos:Concept ; skos:broader ex:b . ex:b a skos:Concept .")],
    ),
    "SKOS004": rule_cases(
        [ttl("no prefLabel", "ex:c a skos:Concept .")],
        [
            ttl("prefLabel present", 'ex:c a skos:Concept ; skos:prefLabel "c"@en .'),
            ttl("rdfs:label fallback", 'ex:c a skos:Concept ; rdfs:label "c" .'),
            ttl("deprecated", "ex:c a skos:Concept ; owl:deprecated true ."),
            ttl("history note", 'ex:c a skos:Concept ; skos:historyNote "Moved." .'),
        ],
    ),
    "SKOS005": rule_cases(
        [ttl("not in a scheme", "ex:c a skos:Concept .")],
        [ttl("inScheme", "ex:c a skos:Concept ; skos:inScheme ex:s . ex:s a skos:ConceptScheme .")],
    ),
    "SKOS006": rule_cases(
        [
            ttl(
                "top concept with broader",
                "ex:c a skos:Concept ; skos:topConceptOf ex:s ; skos:broader ex:d . ex:d a skos:Concept .",
            ),
            ttl(
                "top concept of a blank scheme",
                "ex:c a skos:Concept ; skos:topConceptOf [ ex:p 1 ] ; skos:broader ex:d .",
            ),
        ],
        [ttl("top concept without broader", "ex:c a skos:Concept ; skos:topConceptOf ex:s .")],
    ),
}
