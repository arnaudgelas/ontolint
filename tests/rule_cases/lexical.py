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
                'ex:A a owl:Class ; rdfs:label "Same" . ex:B a owl:Class ; rdfs:label "Same" .',
            )
        ],
        [
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
