"""Cases for LEX001-LEX009, including the style-sample-size boundary of LEX007."""

from __future__ import annotations

from rule_harness import Case, rule_cases, ttl

_STYLE_TERMS = ("ex:a_b", "ex:c_d", "ex:eF", "ex:gH")


def _styles(n: int) -> str:
    return " ".join(f"{term} a owl:Class ." for term in _STYLE_TERMS[:n])


CASES = {
    "LEX001": rule_cases(
        [ttl("no label", "ex:A a owl:Class .")],
        [
            ttl("rdfs:label", 'ex:A a owl:Class ; rdfs:label "A" .'),
            ttl("deprecated terms are exempt", "ex:A a owl:Class ; owl:deprecated true ."),
        ],
    ),
    "LEX002": rule_cases(
        [ttl("no definition", "ex:A a owl:Class .")],
        [ttl("skos:definition", 'ex:A a owl:Class ; skos:definition "An A." .')],
    ),
    "LEX003": rule_cases(
        [ttl("two labels in one language", 'ex:A a owl:Class ; rdfs:label "A"@en, "Aye"@en .')],
        [ttl("one label per language", 'ex:A a owl:Class ; rdfs:label "A"@en, "A"@fr .')],
    ),
    "LEX004": rule_cases(
        [
            ttl(
                "same label on two terms",
                'ex:A a owl:Class ; rdfs:label "Same" . ex:B a owl:Class ; rdfs:label "same" .',
            )
        ],
        [
            ttl("different labels", 'ex:A a owl:Class ; rdfs:label "One" . ex:B a owl:Class ; rdfs:label "Two" .'),
            ttl(
                "same text, other language",
                'ex:A a owl:Class ; rdfs:label "S"@en . ex:B a owl:Class ; rdfs:label "S"@fr .',
            ),
        ],
    ),
    "LEX005": rule_cases(
        [
            ttl("padded label", 'ex:A a owl:Class ; rdfs:label " padded " .'),
            ttl("blank label", 'ex:A a owl:Class ; rdfs:label "" .'),
        ],
        [ttl("trimmed label", 'ex:A a owl:Class ; rdfs:label "A" .')],
    ),
    "LEX006": rule_cases(
        [ttl("plain and tagged", 'ex:A a owl:Class ; rdfs:label "A", "A"@en .')],
        [
            ttl("only tagged", 'ex:A a owl:Class ; rdfs:label "A"@en .'),
            ttl("only plain", 'ex:A a owl:Class ; rdfs:label "A" .'),
        ],
    ),
    "LEX007": rule_cases(
        [Case("four terms, two styles (sample size)", _styles(4), boundary=True)],
        [
            Case("three terms (below sample size)", _styles(3), boundary=True),
            ttl(
                "four terms, one style",
                "ex:a_b a owl:Class . ex:c_d a owl:Class . ex:e_f a owl:Class . ex:g_h a owl:Class .",
            ),
        ],
    ),
    "LEX008": rule_cases(
        [ttl("required language missing", 'ex:A a owl:Class ; rdfs:label "A"@en .', languages=("fr",))],
        [
            ttl("required language present", 'ex:A a owl:Class ; rdfs:label "A"@fr .', languages=("fr",)),
            ttl("no languages required", 'ex:A a owl:Class ; rdfs:label "A"@en .'),
        ],
    ),
    "LEX009": rule_cases(
        [
            ttl("lower-case class label", 'ex:A a owl:Class ; rdfs:label "thing" .'),
            ttl("upper-case property label", 'ex:p a owl:ObjectProperty ; rdfs:label "Relates" .'),
        ],
        [
            ttl("capitalised class", 'ex:A a owl:Class ; rdfs:label "Thing" .'),
            ttl("lower-case property", 'ex:p a owl:ObjectProperty ; rdfs:label "relates" .'),
            ttl("non-alphabetic first character", 'ex:A a owl:Class ; rdfs:label "3d thing" .'),
        ],
    ),
}
