"""Cases for LEX001-LEX009, including the style-sample-size boundary of LEX007."""

from __future__ import annotations

from rule_harness import Case, rule_cases, ttl

_STYLE_TERMS = ("ex:a_b", "ex:c_d", "ex:eF", "ex:gH")


def _styles(n: int) -> str:
    return " ".join(f"{term} a owl:Class ." for term in _STYLE_TERMS[:n])


def _labelled(count: int, odd: str, *, prefix: str = "c", kind: str = "owl:Class") -> str:
    """``count`` terms: all labelled in lower case except one labelled ``odd``."""
    lines = [f'ex:{prefix}{i} a {kind} ; rdfs:label "term {i}" .' for i in range(count - 1)]
    lines.append(f'ex:{prefix}odd a {kind} ; rdfs:label "{odd}" .')
    return "\n".join(lines)


CASES = {
    "LEX001": rule_cases(
        [
            ttl("no label", "ex:A a owl:Class ."),
            ttl(
                "a sub-property of rdfs:comment", 'ex:c rdfs:subPropertyOf rdfs:comment . ex:A a owl:Class ; ex:c "A" .'
            ),
            ttl(
                "a sub-property of skos:altLabel",
                "skos:altLabel rdfs:subPropertyOf rdfs:label . ex:alt rdfs:subPropertyOf skos:altLabel . "
                'ex:A a owl:Class ; ex:alt "A" .',
            ),
        ],
        [
            ttl("rdfs:label", 'ex:A a owl:Class ; rdfs:label "A" .'),
            ttl("deprecated terms are exempt", "ex:A a owl:Class ; owl:deprecated true ."),
            ttl(
                "label through a chain of sub-properties",
                "ex:l2 rdfs:subPropertyOf ex:l1 . ex:l1 rdfs:subPropertyOf skos:prefLabel . "
                'ex:A a owl:Class ; ex:l2 "A" .',
            ),
            ttl(
                "label through an equivalent",
                'ex:name owl:equivalentProperty rdfs:label . ex:A a owl:Class ; ex:name "A" .',
            ),
        ],
    ),
    "LEX002": rule_cases(
        [
            ttl("no definition", "ex:A a owl:Class ."),
            ttl(
                "equivalent to a non-definition", "ex:d owl:equivalentProperty ex:q . ex:A a owl:Class ; ex:d 'An A.' ."
            ),
        ],
        [
            ttl("skos:definition", 'ex:A a owl:Class ; skos:definition "An A." .'),
            ttl("skos:scopeNote", 'ex:A a owl:Class ; skos:scopeNote "Use for As." .'),
            ttl("skos:note", 'ex:A a owl:Class ; skos:note "About A." .'),
            ttl(
                "definition through a chain of sub-properties",
                "ex:d2 rdfs:subPropertyOf ex:d1 . ex:d1 rdfs:subPropertyOf skos:definition . "
                "ex:A a owl:Class ; ex:d2 'An A.' .",
            ),
            ttl(
                "definition through an equivalent",
                "ex:d owl:equivalentProperty ex:q . ex:q rdfs:subPropertyOf skos:definition . "
                "ex:A a owl:Class ; ex:d 'An A.' .",
            ),
        ],
    ),
    "LEX003": rule_cases(
        [ttl("two labels in one language", 'ex:A a owl:Class ; rdfs:label "A"@en, "Aye"@en .')],
        [
            ttl("one label per language", 'ex:A a owl:Class ; rdfs:label "A"@en, "A"@fr .'),
            ttl("prefLabel and rdfs:label", 'ex:A a owl:Class ; skos:prefLabel "A"@en ; rdfs:label "1 A"@en .'),
            ttl(
                "a specialised label beside rdfs:label",
                'ex:short rdfs:subPropertyOf rdfs:label . ex:A a owl:Class ; rdfs:label "Aye"@en ; ex:short "A"@en .',
            ),
        ],
    ),
    "LEX004": rule_cases(
        [
            ttl(
                "same label on two terms",
                'ex:A a owl:Class ; rdfs:label "Same" . ex:B a owl:Class ; rdfs:label "Same" .',
            )
        ],
        [
            ttl(
                "collection and concept share a label",
                'ex:A a skos:Concept ; skos:prefLabel "Same" . ex:B a skos:Collection ; skos:prefLabel "Same" .',
            ),
            ttl(
                "scheme and concept share a label",
                'ex:A a skos:Concept ; skos:prefLabel "Same" . ex:B a skos:ConceptScheme ; skos:prefLabel "Same" .',
            ),
            ttl(
                "case-only difference", 'ex:A a owl:Class ; rdfs:label "Same" . ex:B a owl:Class ; rdfs:label "same" .'
            ),
            ttl(
                "class and property share a label",
                'ex:A a owl:Class ; rdfs:label "agent" . ex:p a owl:ObjectProperty ; rdfs:label "agent" .',
            ),
            ttl(
                "deprecated term",
                'ex:A a owl:Class ; rdfs:label "S" . ex:B a owl:Class ; owl:deprecated true ; rdfs:label "S" .',
            ),
            ttl(
                "obsolete label",
                'ex:A a owl:Class ; rdfs:label "obsolete S" . ex:B a owl:Class ; rdfs:label "obsolete S" .',
            ),
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
            ttl(
                "opaque numeric identifiers do not count as underscore style",
                "ex:X_0000001 a owl:Class . ex:X_0000002 a owl:Class . ex:eF a owl:Class . ex:gH a owl:Class .",
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
            Case("one upper-case class among ten lower-case", _labelled(10, "Thing"), boundary=True),
            Case(
                "one upper-case property among ten lower-case",
                _labelled(10, "Relates", prefix="p", kind="owl:ObjectProperty"),
                boundary=True,
            ),
        ],
        [
            Case("nine labels are too few", _labelled(9, "Thing"), boundary=True),
            ttl("lower-case class alone", 'ex:A a owl:Class ; rdfs:label "thing" .'),
            ttl("non-alphabetic first character", 'ex:A a owl:Class ; rdfs:label "3d thing" .'),
            Case(
                "balanced conventions",
                "\n".join(
                    _labelled(10, "Thing").splitlines()[:5]
                    + [f'ex:u{i} a owl:Class ; rdfs:label "Up {i}" .' for i in range(6)]
                ),
                boundary=True,
            ),
        ],
    ),
}
