"""Cases for IRI015, LEX018 and LEX021."""

from __future__ import annotations

from rule_harness import rule_cases, ttl


def _namespace_mix(readable: int, opaque: int) -> str:
    lines = [f"ex:Name{chr(97 + i // 26)}{chr(97 + i % 26)}x a owl:Class ." for i in range(readable)]
    lines += [f"ex:T{1000 + i} a owl:Class ." for i in range(opaque)]
    return " ".join(lines)


CASES = {
    "IRI015": rule_cases(
        [
            ttl("numeric and readable", "ex:Person a owl:Class . ex:T0001234 a owl:Class ."),
            ttl("prefixed number and readable", "ex:hasPart a owl:ObjectProperty . ex:BFO_0000001 a owl:Class ."),
            ttl("minority of exactly 10%", _namespace_mix(9, 1)),
        ],
        [
            ttl("one outlier among eleven terms (below 10%)", _namespace_mix(10, 1)),
            ttl("all readable", "ex:Person a owl:Class . ex:hasPart a owl:ObjectProperty ."),
            ttl("all opaque", "ex:T0001234 a owl:Class . ex:T0001235 a owl:Class ."),
            ttl(
                "different namespaces",
                "<https://a.test/Person> a owl:Class . <https://b.test/T0001234> a owl:Class .",
            ),
        ],
    ),
    "LEX018": rule_cases(
        [
            ttl("html tag", 'ex:A a owl:Class ; rdfs:label "<b>Thing</b>" .'),
            ttl("entity", 'ex:A a owl:Class ; skos:prefLabel "R&amp;D" .'),
            ttl("alt label numeric entity", 'ex:A a owl:Class ; skos:altLabel "a&#233;b" .'),
        ],
        [
            ttl("plain", 'ex:A a owl:Class ; rdfs:label "R&D" .'),
            ttl("comparison signs", 'ex:A a owl:Class ; rdfs:label "a < b > c" .'),
            ttl("disambiguator in angle brackets", 'ex:A a owl:Class ; rdfs:label "Gnathostomata <vertebrates>" .'),
            ttl("comment is ignored", 'ex:A a owl:Class ; rdfs:comment "<b>x</b>" .'),
        ],
    ),
    "LEX021": rule_cases(
        [
            ttl("decomposed e-acute", 'ex:A a owl:Class ; rdfs:label "Cafe\\u0301" .'),
            ttl("alt label", 'ex:A a owl:Class ; skos:altLabel "Cafe\\u0301"@fr .'),
        ],
        [
            ttl("composed", 'ex:A a owl:Class ; rdfs:label "Caf\\u00e9" .'),
            ttl("ascii", 'ex:A a owl:Class ; rdfs:label "Cafe" .'),
        ],
    ),
}
