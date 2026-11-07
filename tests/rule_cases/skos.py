"""Cases for SKOS001-SKOS006."""

from __future__ import annotations

from rule_harness import rule_cases, ttl

CASES = {
    "SKOS001": rule_cases(
        [ttl("two prefLabels in a language", 'ex:c a skos:Concept ; skos:prefLabel "a"@en, "b"@en .')],
        [ttl("one prefLabel per language", 'ex:c a skos:Concept ; skos:prefLabel "a"@en, "a"@fr .')],
    ),
    "SKOS002": rule_cases(
        [
            ttl(
                "same literal as pref and alt label",
                'ex:c a skos:Concept ; skos:prefLabel "a"@en ; skos:altLabel "a"@en .',
            )
        ],
        [ttl("distinct literals", 'ex:c a skos:Concept ; skos:prefLabel "a"@en ; skos:altLabel "b"@en .')],
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
        [ttl("prefLabel present", 'ex:c a skos:Concept ; skos:prefLabel "c"@en .')],
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
            )
        ],
        [ttl("top concept without broader", "ex:c a skos:Concept ; skos:topConceptOf ex:s .")],
    ),
}
