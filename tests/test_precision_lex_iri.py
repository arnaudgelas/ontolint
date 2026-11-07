"""Exact-expectation tests for the precision changes of LEX001/004/007/009/010/018, IRI002/003/004/005/013/015."""

from __future__ import annotations

import pytest
from rule_harness import BASE, graph

from ontolint import Linter
from ontolint.models import Severity
from ontolint.rules import identifiers, iri_lexical_extras, iri_quality, lexical

OBO = "http://purl.obolibrary.org/obo/"


def run(rule: str, turtle: str, **options: object) -> list[tuple[str, str, str]]:
    result = Linter(graph(turtle), **options).execute([rule])  # type: ignore[arg-type]
    return sorted((f.focus, f.message, f.confidence) for f in result.findings)


def foci(rule: str, turtle: str) -> list[str]:
    return [focus for focus, _, _ in run(rule, turtle)]


# --- LEX001 ----------------------------------------------------------------------------------------


def test_lex001_confidence_depends_on_unrecognised_label_predicates() -> None:
    assert run("LEX001", "ex:A a owl:Class .") == [(BASE + "A", "Term has no label.", "certain")]
    assert run("LEX001", 'ex:A a owl:Class ; ex:hasName "A" .') == [(BASE + "A", "Term has no label.", "heuristic")]
    assert run("LEX001", 'ex:A a owl:Class ; ex:displayLabel "A" .')[0][2] == "heuristic"
    assert run("LEX001", 'ex:A a owl:Class ; ex:title "A" .')[0][2] == "heuristic"
    # a non-literal or an unrelated predicate does not lower the confidence
    assert run("LEX001", "ex:A a owl:Class ; ex:hasName ex:B .")[0][2] == "certain"
    assert run("LEX001", 'ex:A a owl:Class ; ex:note "A" .')[0][2] == "certain"
    # a recognised label predicate means there is no finding at all
    assert run("LEX001", 'ex:A a owl:Class ; skos:prefLabel "A" .') == []


def test_lex002_accepts_obo_and_prov_definitions() -> None:
    for predicate in (OBO + "IAO_0000115", OBO + "IAO_0000600", "http://www.w3.org/ns/prov#definition"):
        assert run("LEX002", f'ex:A a owl:Class ; <{predicate}> "An A." .') == []


# --- LEX004 ----------------------------------------------------------------------------------------


def test_lex004_message_severity_and_case_sensitivity() -> None:
    assert [s.severity for s in lexical.SPECS if s.rule_id == "LEX004"] == [Severity.INFO]
    found = run("LEX004", 'ex:B a owl:Class ; rdfs:label " Same " . ex:A a owl:Class ; rdfs:label "Same" .')
    assert found == [(BASE + "A", f"Duplicate label 'Same'@und for {BASE}A, {BASE}B", "heuristic")]
    assert run("LEX004", 'ex:A a owl:Class ; rdfs:label "Same" . ex:B a owl:Class ; rdfs:label "same" .') == []


def test_lex004_skips_kind_mixes_deprecated_and_obsolete() -> None:
    assert run("LEX004", 'ex:A a owl:Class ; rdfs:label "x" . ex:p a owl:ObjectProperty ; rdfs:label "x" .') == []
    assert foci("LEX004", 'ex:p a owl:ObjectProperty ; rdfs:label "x" . ex:q a owl:DatatypeProperty ; rdfs:label "x" .')
    assert foci("LEX004", 'ex:A a owl:Class ; rdfs:label "x" . ex:B a skos:Concept ; rdfs:label "x" .') == []
    deprecated = 'ex:A a owl:Class ; rdfs:label "x" . ex:B a owl:Class ; owl:deprecated true ; rdfs:label "x" .'
    assert run("LEX004", deprecated) == []
    assert run("LEX004", deprecated.replace("owl:deprecated true", "owl:deprecated false"))
    for label in ("obsolete x", "Obsolete x"):
        assert (
            run("LEX004", f'ex:A a owl:Class ; rdfs:label "{label}" . ex:B a owl:Class ; rdfs:label "{label}" .') == []
        )
    assert foci(
        "LEX004", 'ex:A a owl:Class ; rdfs:label "an obsolete x" . ex:B a owl:Class ; rdfs:label "an obsolete x" .'
    )


# --- LEX007 ----------------------------------------------------------------------------------------


def test_lex007_ignores_opaque_identifiers() -> None:
    opaque = "ex:BFO_0000001 a owl:Class . ex:ENVO_00000892 a owl:Class . ex:T-1234 a owl:Class ."
    assert run("LEX007", opaque + " ex:a_b a owl:Class .") == []
    # opaque names also do not count towards the sample size
    assert run("LEX007", opaque + " ex:a_b a owl:Class . ex:cD a owl:Class . ex:eF a owl:Class .") == []
    found = run("LEX007", opaque + " ex:a_b a owl:Class . ex:cD a owl:Class . ex:eF a owl:Class . ex:gH a owl:Class .")
    assert found == [("(vocabulary)", "Mixed identifier styles: {'camel': 3, 'underscore': 1}.", "heuristic")]


# --- LEX009 ----------------------------------------------------------------------------------------


def _labels(count: int, *, lower: int, kind: str = "owl:Class") -> str:
    return "\n".join(f'ex:t{i} a {kind} ; rdfs:label "{"w" if i < lower else "W"}ord {i}" .' for i in range(count))


@pytest.mark.parametrize(
    ("count", "lower", "flagged"),
    [
        (10, 10, 0),
        (10, 9, 1),
        (10, 8, 2),
        (10, 7, 0),
        (10, 3, 0),
        (10, 2, 2),
        (9, 8, 0),
        (11, 9, 2),
        (11, 8, 0),
        (20, 16, 4),
        (20, 15, 0),
    ],
)
def test_lex009_majority_boundaries(count: int, lower: int, flagged: int) -> None:
    # The dominant case must cover at least 80 percent of at least 10 labels.
    assert len(run("LEX009", _labels(count, lower=lower))) == flagged


def test_lex009_message_and_targets() -> None:
    found = run("LEX009", _labels(10, lower=9))
    assert found == [
        (
            BASE + "t9",
            "Class label begins with upper case, but 9 of 10 class labels begin with lower case (style review).",
            "heuristic",
        )
    ]
    found = run("LEX009", _labels(10, lower=1, kind="owl:ObjectProperty"))
    assert found == [
        (
            BASE + "t0",
            "Property label begins with lower case, but 9 of 10 property labels begin with upper case (style review).",
            "heuristic",
        )
    ]


def test_lex009_kinds_are_judged_separately_and_nine_labels_are_too_few() -> None:
    classes = _labels(10, lower=10)
    properties = "\n".join(f'ex:p{i} a owl:ObjectProperty ; rdfs:label "Rel {i}" .' for i in range(9))
    assert run("LEX009", classes + "\n" + properties) == []
    ten = properties + '\nex:p9 a owl:ObjectProperty ; rdfs:label "rel" .'
    assert foci("LEX009", classes + "\n" + ten) == [BASE + "p9"]


def test_lex009_non_alphabetic_labels_do_not_count() -> None:
    nine = _labels(9, lower=9)
    assert run("LEX009", nine + '\nex:x a owl:Class ; rdfs:label "3d" .') == []
    assert foci("LEX009", nine + '\nex:x a owl:Class ; rdfs:label "Odd" .\nex:y a owl:Class ; rdfs:label "3d" .') == [
        BASE + "x"
    ]


# --- LEX010 ----------------------------------------------------------------------------------------


def _verbatim(total: int, equal: int) -> str:
    lines = [f'ex:hasPart{i} a owl:ObjectProperty ; rdfs:label "hasPart{i}" .' for i in range(equal)]
    lines += [f'ex:other{i} a owl:ObjectProperty ; rdfs:label "other {i}" .' for i in range(total - equal)]
    return "\n".join(lines)


def test_lex010_aggregates_when_most_labels_equal_the_local_name() -> None:
    onto = "<https://example.test/onto> a owl:Ontology .\n"
    found = run("LEX010", onto + _verbatim(10, 6))
    assert found == [
        (
            "https://example.test/onto",
            "6 of 10 labelled terms use their identifier as the label (e.g. 'hasPart0').",
            "heuristic",
        )
    ]
    # without an ontology the finding is attached to the vocabulary
    assert foci("LEX010", _verbatim(10, 6)) == ["(vocabulary)"]


def test_lex010_boundaries() -> None:
    # exactly half is not "more than half": per-term findings
    assert foci("LEX010", _verbatim(10, 5)) == [f"{BASE}hasPart{i}" for i in range(5)]
    assert len(foci("LEX010", _verbatim(10, 6))) == 1
    # fewer than ten labelled terms are never aggregated
    assert foci("LEX010", _verbatim(9, 9)) == [f"{BASE}hasPart{i}" for i in range(9)]
    assert len(foci("LEX010", _verbatim(10, 10))) == 1


def test_lex010_single_words_count_towards_the_majority_only() -> None:
    plain = "\n".join(f'ex:Person{i} a owl:Class ; rdfs:label "Person{i}" .' for i in range(9))
    camel = 'ex:hasPart a owl:ObjectProperty ; rdfs:label "hasPart" .'
    assert foci("LEX010", plain + "\n" + camel) == ["(vocabulary)"]
    assert run("LEX010", plain) == []


# --- LEX018 ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "flagged"),
    [
        ("Gnathostomata <vertebrates>", False),
        ("Gnathostomata <jawed vertebrates> ", False),
        ("<vertebrates>", True),
        ("Gnathostomata<vertebrates>", True),
        ("Gnathostomata <vertebrates> more", True),
        ("x <b>", True),
        ("x <br>", True),
        ("x </i>", True),
        ("x <br/>", True),
        ("x <a href='u'>", True),
        ("x <vertebrates> &amp;", True),
        ("x <b>y</b>", True),
    ],
)
def test_lex018_disambiguators(label: str, flagged: bool) -> None:
    assert bool(run("LEX018", f'ex:A a owl:Class ; rdfs:label "{label}" .')) is flagged


def test_lex018_helper() -> None:
    assert iri_lexical_extras._without_disambiguator("a <b c>") == "a"
    assert iri_lexical_extras._without_disambiguator("a <b>") == "a <b>"
    assert iri_lexical_extras._without_disambiguator("a<b c>") == "a<b c>"


# --- IRI015 ----------------------------------------------------------------------------------------


def _mix(readable: int, opaque: int) -> str:
    letters = "abcdefghijklmnopqrstuvwxyz"
    names = [f"Name{letters[i // 26]}{letters[i % 26]}x" for i in range(readable)]
    names += [f"T{1000 + i}" for i in range(opaque)]
    return " ".join(f"ex:{n} a owl:Class ." for n in names)


@pytest.mark.parametrize(
    ("readable", "opaque", "fires"),
    [(9, 1, True), (10, 1, False), (1, 9, True), (1, 10, False), (5, 5, True), (91, 10, False), (90, 10, True)],
)
def test_iri015_minority_threshold(readable: int, opaque: int, fires: bool) -> None:
    assert bool(run("IRI015", _mix(readable, opaque))) is fires


# --- IRI002 / IRI003 -------------------------------------------------------------------------------


def test_iri002_obo_purls_are_exempt() -> None:
    assert foci("IRI002", f"<{OBO}envo.owl> a owl:Ontology .") == []
    assert foci("IRI002", f"<{OBO}envo/imports/x.owl> a owl:Ontology .") == []
    assert foci("IRI002", "<http://purl.obolibrary.org.example/envo.owl> a owl:Ontology .") != []
    assert foci("IRI002", "<http://purl.obolibrary.org/other/envo.owl> a owl:Ontology .") != []


def test_iri003_kinds_and_deprecation() -> None:
    assert run("IRI003", "ex:Agent a owl:Class . ex:agent a owl:ObjectProperty .") == []
    assert run("IRI003", "ex:Agent a owl:Class . ex:agent a skos:Concept .") == []
    found = run("IRI003", "ex:Agent a owl:Class . ex:agent a owl:Class .")
    assert found == [(BASE + "Agent", f"Local-name collision across IRIs: {BASE}Agent, {BASE}agent", "heuristic")]
    assert foci("IRI003", "ex:p a owl:ObjectProperty . ex:P a owl:DatatypeProperty .") == [BASE + "P"]
    both = "ex:Agent a owl:Class, owl:ObjectProperty . ex:agent a owl:Class ."
    assert foci("IRI003", both) == [BASE + "Agent"]
    assert foci("IRI003", "ex:A a owl:Class ; owl:deprecated true . <https://b.test/A> a owl:Class .") == []
    assert foci("IRI003", "ex:A a owl:Class ; owl:deprecated false . <https://b.test/A> a owl:Class .") != []


# --- IRI004 / IRI005 -------------------------------------------------------------------------------


def test_iri004_obo_exempt_other_still_fires() -> None:
    assert foci("IRI004", f"<{OBO}x.owl> a owl:Ontology . <{OBO}X_0000001> a owl:Class .") == []
    assert foci("IRI004", "<https://a.test/o> a owl:Ontology . <https://b.test/X> a owl:Class .") == [
        "https://a.test/o"
    ]


def test_iri005_counts_owned_terms_and_obo_subsets() -> None:
    owned = "<https://a.test/o> a owl:Ontology . <https://a.test/o#A> a owl:Class . <https://a.test/o/B> a owl:Class ."
    assert foci("IRI005", owned) == ["(vocabulary)"]
    foreign = "<https://elsewhere.test/ns#X> a owl:Class ."
    assert foci("IRI005", "<https://a.test/o> a owl:Ontology . <https://a.test/o/B> a owl:Class ." + foreign) == []
    obo = f"<{OBO}x.owl> a owl:Ontology . <{OBO}x#slim> a owl:AnnotationProperty . <{OBO}X_0000001> a owl:Class ."
    assert foci("IRI005", obo) == []
    # outside an OBO ontology the same mix is reported
    plain = (
        "<https://a.test/o> a owl:Ontology . <https://a.test/o#slim> a owl:Class . <https://a.test/o/X_1> a owl:Class ."
    )
    assert foci("IRI005", plain) == ["(vocabulary)"]
    # an OBO hash term in a non-OBO ontology is still counted
    mixed = f"<https://a.test/o> a owl:Ontology . <{OBO}x#slim> a owl:Class . <{OBO}X_1> a owl:Class ."
    assert foci("IRI005", mixed) != []


# --- IRI013 ----------------------------------------------------------------------------------------


def test_iri013_reports_once_per_namespace() -> None:
    ttl_ = (
        "<https://a.test/v1/B> a owl:Class . <https://a.test/v1/A> a owl:Class . <https://a.test/v2/A> a owl:Class ."
        " <https://a.test/plain/A> a owl:Class ."
    )
    assert run("IRI013", ttl_) == [
        (
            "https://a.test/v1/",
            "2 term IRIs in this namespace embed a version or date segment (e.g. https://a.test/v1/A).",
            "heuristic",
        ),
        (
            "https://a.test/v2/",
            "1 term IRIs in this namespace embed a version or date segment (e.g. https://a.test/v2/A).",
            "heuristic",
        ),
    ]
    assert run("IRI013", "<https://a.test/plain/A> a owl:Class .") == []


def test_specs_unchanged_elsewhere() -> None:
    assert {s.rule_id for s in identifiers.SPECS} == {"IRI001", "IRI002", "IRI003"}
    assert iri_quality.OBO_NAMESPACE == OBO
