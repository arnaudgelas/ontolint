"""Exact-expectation tests for the SKOS/LEX precision fixes found on real thesauri (UNESCO, STW)."""

from __future__ import annotations

import pytest
from rdflib import URIRef
from rule_harness import BASE, graph

from ontolint import Linter
from ontolint.context import GraphContext
from ontolint.ownership import (
    DOMINANT_PERCENT,
    MINOR_OWNED_PERCENT,
    Ownership,
    OwnershipMode,
    namespace_of_iri,
)
from ontolint.rules import skos_integrity

SKOS_CORE = "http://www.w3.org/2004/02/skos/core#"


def run(rule: str, turtle: str, **options: object) -> list[tuple[str, str]]:
    result = Linter(graph(turtle), **options).execute([rule])  # type: ignore[arg-type]
    return sorted((f.focus.removeprefix(BASE), f.message) for f in result.findings)


def foci(rule: str, turtle: str) -> list[str]:
    return [focus for focus, _ in run(rule, turtle)]


# --- SKOS020 / SKOS021 -------------------------------------------------------------------------

IN_S = "skos:inScheme ex:s"


def test_skos021_collection_sharing_a_name_with_a_concept_is_not_a_clash() -> None:
    body = f'ex:a a skos:Concept ; {IN_S} ; skos:prefLabel "Water"@en . ex:b a skos:Collection ; {IN_S} ; '
    assert foci("SKOS021", body + 'skos:prefLabel "Water"@en .') == []


def test_skos021_two_collections_are_not_a_clash() -> None:
    body = f'ex:a a skos:Collection ; {IN_S} ; skos:prefLabel "W"@en . ex:b a skos:Collection ; {IN_S} ; '
    assert foci("SKOS021", body + 'skos:prefLabel "W"@en .') == []


def test_skos021_untyped_member_is_not_a_concept() -> None:
    body = f'ex:a a skos:Concept ; {IN_S} ; skos:prefLabel "W"@en . ex:b {IN_S} ; skos:prefLabel "W"@en .'
    assert foci("SKOS021", body) == []


def test_skos021_two_concepts_still_clash_with_exact_message() -> None:
    body = (
        f'ex:a a skos:Concept ; {IN_S} ; skos:prefLabel "Water"@en . '
        f'ex:b a skos:Concept ; {IN_S} ; skos:prefLabel "water"@EN .'
    )
    expected = "skos:prefLabel 'water' (en) is shared by 2 concepts of " + BASE + "s."
    assert run("SKOS021", body) == [("a", expected), ("b", expected)]


def test_skos021_concept_subclass_counts_as_a_concept() -> None:
    body = (
        "ex:Sub rdfs:subClassOf skos:Concept . "
        f'ex:a a ex:Sub ; {IN_S} ; skos:prefLabel "W"@en . ex:b a skos:Concept ; {IN_S} ; skos:prefLabel "W"@en .'
    )
    assert foci("SKOS021", body) == ["a", "b"]


@pytest.mark.parametrize("deprecated", ["true", '"true"^^xsd:boolean'])
def test_skos021_deprecated_concept_is_skipped_but_live_pair_is_not(deprecated: str) -> None:
    clash = (
        f'ex:a a skos:Concept ; {IN_S} ; skos:prefLabel "W"@en . ex:b a skos:Concept ; {IN_S} ; skos:prefLabel "W"@en .'
    )
    old = f'ex:c a skos:Concept ; owl:deprecated {deprecated} ; {IN_S} ; skos:prefLabel "W"@en .'
    assert foci("SKOS021", clash + old) == ["a", "b"]
    # a deprecated twin leaves a single live concept: nothing to report
    assert foci("SKOS021", f'ex:a a skos:Concept ; {IN_S} ; skos:prefLabel "W"@en .' + old) == []
    # owl:deprecated false does not exempt
    live = old.replace(deprecated, "false")
    assert foci("SKOS021", f'ex:a a skos:Concept ; {IN_S} ; skos:prefLabel "W"@en .' + live) == ["a", "c"]


def test_skos020_applies_the_same_member_filter() -> None:
    two = f'ex:a a skos:Concept ; {IN_S} ; skos:notation "1" . ex:b a skos:Concept ; {IN_S} ; skos:notation "1" .'
    assert foci("SKOS020", two) == ["a", "b"]
    coll = f'ex:a a skos:Concept ; {IN_S} ; skos:notation "1" . ex:b a skos:Collection ; {IN_S} ; skos:notation "1" .'
    assert foci("SKOS020", coll) == []
    old = f'ex:a a skos:Concept ; {IN_S} ; skos:notation "1" . ex:b a skos:Concept ; owl:deprecated true ; {IN_S} ; '
    assert foci("SKOS020", old + 'skos:notation "1" .') == []


def test_skos021_scheme_membership_is_required() -> None:
    assert (
        foci("SKOS021", 'ex:a a skos:Concept ; skos:prefLabel "W" . ex:b a skos:Concept ; skos:prefLabel "W" .') == []
    )
    assert skos_integrity.MINIMUM_SHARED == 2  # noqa: PLR2004


# --- SKOS004 -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "reported"),
    [
        ("ex:c a skos:Concept .", True),
        ('ex:c a skos:Concept ; skos:prefLabel "c"@en .', False),
        ('ex:c a skos:Concept ; rdfs:label "c" .', False),
        ('ex:c a skos:Concept ; skos:altLabel "c" .', True),
        ("ex:c a skos:Concept ; rdfs:label ex:other .", True),
        ("ex:c a skos:Concept ; owl:deprecated true .", False),
        ("ex:c a skos:Concept ; owl:deprecated false .", True),
        ('ex:c a skos:Concept ; skos:historyNote "Merged into ex:d." .', False),
        ('ex:c a skos:Concept ; owl:deprecated true ; skos:historyNote "x" .', False),
    ],
)
def test_skos004_matrix(body: str, reported: bool) -> None:
    expected = [("c", "Concept has no skos:prefLabel.")] if reported else []
    assert run("SKOS004", body) == expected


# --- SKOS002 -----------------------------------------------------------------------------------


def test_skos002_names_literal_language_and_properties() -> None:
    assert run("SKOS002", 'ex:c a skos:Concept ; skos:prefLabel "Water"@en ; skos:altLabel "Water"@en .') == [
        ("c", "Literal 'Water' (en) appears in skos:prefLabel and skos:altLabel.")
    ]
    assert run("SKOS002", 'ex:c a skos:Concept ; skos:altLabel "W" ; skos:hiddenLabel "W" .') == [
        ("c", "Literal 'W' (no language) appears in skos:altLabel and skos:hiddenLabel.")
    ]


def test_skos002_reports_each_clashing_literal_and_ignores_language_mismatch() -> None:
    body = 'ex:c a skos:Concept ; skos:prefLabel "A"@en, "B"@en ; skos:altLabel "A"@en, "B"@en, "A"@fr .'
    assert run("SKOS002", body) == [
        ("c", "Literal 'A' (en) appears in skos:prefLabel and skos:altLabel."),
        ("c", "Literal 'B' (en) appears in skos:prefLabel and skos:altLabel."),
    ]
    assert run("SKOS002", 'ex:c a skos:Concept ; skos:prefLabel "A"@en ; skos:altLabel "A"@fr .') == []


def test_skos002_three_properties_listed_together() -> None:
    body = 'ex:c a skos:Concept ; skos:prefLabel "A" ; skos:altLabel "A" ; skos:hiddenLabel "A" .'
    assert run("SKOS002", body) == [
        ("c", "Literal 'A' (no language) appears in skos:prefLabel and skos:altLabel and skos:hiddenLabel.")
    ]


# --- SKOS018 -----------------------------------------------------------------------------------


def test_skos018_suggestion_explains_how_to_ignore_it() -> None:
    body = "ex:a skos:broader ex:b, ex:c . ex:b skos:broader ex:c ."
    result = Linter(graph(body)).execute(["SKOS018"])
    assert [f.focus.removeprefix(BASE) for f in result.findings] == ["a"]
    assert "--ignore SKOS018" in result.findings[0].suggestion
    assert "parallel classification" in result.findings[0].suggestion


# --- LEX013 ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "reported"),
    [
        ('ex:A a owl:Class ; skos:definition [ rdf:value "An A." ] .', False),
        ('ex:A a owl:Class ; skos:definition ex:d . ex:d rdf:value "An A." .', False),
        ("ex:A a owl:Class ; skos:definition [] .", True),
        ("ex:A a owl:Class ; skos:definition ex:d .", True),
        ('ex:A a owl:Class ; skos:definition [ rdfs:comment "x" ] .', True),
        ('ex:A a owl:Class ; rdfs:comment [ rdf:value "An A." ] .', False),
        # rdf:value does not make a label node acceptable
        ('ex:A a owl:Class ; rdfs:label [ rdf:value "A" ] .', True),
        ('ex:A a owl:Class ; skos:prefLabel ex:l . ex:l rdf:value "A" .', True),
    ],
)
def test_lex013_matrix(body: str, reported: bool) -> None:
    assert (foci("LEX013", body) == ["A"]) is reported


# --- LEX002 ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("predicate", "documented"),
    [
        ("skos:scopeNote", True),
        ("skos:note", True),
        ("skos:definition", True),
        ("rdfs:comment", True),
        ("skos:editorialNote", False),
        ("skos:historyNote", False),
        ("skos:example", False),
    ],
)
def test_lex002_documentation_predicates(predicate: str, documented: bool) -> None:
    body = f'ex:A a owl:Class ; rdfs:label "A" ; {predicate} "Text." .'
    assert (foci("LEX002", body) == []) is documented


def test_lex002_notes_are_not_definitions_for_other_rules() -> None:
    assert foci("LEX017", 'ex:A a owl:Class ; rdfs:label "A" ; skos:note "A" .') == []
    assert foci("LEX020", 'ex:A a owl:Class ; skos:note "Same." . ex:B a owl:Class ; skos:note "Same." .') == []


# --- LEX003 ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "count"),
    [
        ('skos:prefLabel "A"@en ; rdfs:label "1 A"@en', None),
        ('skos:prefLabel "A"@en ; rdfs:label "1 A"@en, "2 A"@en', None),
        ('skos:prefLabel "A"@en, "B"@en', 2),
        ('rdfs:label "A"@en, "B"@en', 2),
        ('rdfs:label "A"@en, "B"@en, "C"@en', 3),
        ('skos:prefLabel "A"@en ; rdfs:label "B"@fr', None),
        ('skos:prefLabel "A"@en, "B"@fr ; rdfs:label "C"@fr', None),
    ],
)
def test_lex003_counts_one_label_family(body: str, count: int | None) -> None:
    expected = [] if count is None else [("A", f"{count} labels for language en.")]
    assert run("LEX003", f"ex:A a skos:Concept ; {body} .") == expected


# --- LEX004 ------------------------------------------------------------------------------------


@pytest.mark.parametrize("other", ["skos:Collection", "skos:ConceptScheme"])
def test_lex004_ignores_collections_and_schemes(other: str) -> None:
    body = f'ex:A a skos:Concept ; skos:prefLabel "Same" . ex:B a {other} ; skos:prefLabel "Same" .'
    assert foci("LEX004", body) == []
    assert foci("LEX004", f'ex:A a {other} ; rdfs:label "S" . ex:B a {other} ; rdfs:label "S" .') == []


def test_lex004_still_reports_concept_pairs_and_names_both() -> None:
    body = 'ex:A a skos:Concept ; skos:prefLabel "Same" . ex:B a skos:Concept ; skos:prefLabel "Same" .'
    assert run("LEX004", body) == [("A", f"Duplicate label 'Same'@und for {BASE}A, {BASE}B")]


def test_lex004_collection_does_not_hide_a_real_duplicate() -> None:
    body = (
        'ex:A a skos:Concept ; skos:prefLabel "Same" . ex:B a skos:Concept ; skos:prefLabel "Same" . '
        'ex:C a skos:Collection ; skos:prefLabel "Same" .'
    )
    assert run("LEX004", body) == [("A", f"Duplicate label 'Same'@und for {BASE}A, {BASE}B")]


# --- OWL034-OWL040 messages --------------------------------------------------------------------


def _owl(rule: str, body: str) -> list[tuple[str, str]]:
    result = Linter(graph(body)).execute([rule])
    return sorted((f.focus, f.message) for f in result.findings)


def test_owl035_message_names_owner_and_property() -> None:
    [(focus, message)] = _owl("OWL035", "ex:C rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:p ] .")
    assert focus.startswith("_:") and len(focus) == len("_:") + 12
    assert message == f"{BASE}C (restriction on {BASE}p): Restriction has no value, cardinality or self constraint."


def test_owl034_without_property_says_plain_restriction() -> None:
    [(_, message)] = _owl("OWL034", "ex:C rdfs:subClassOf [ a owl:Restriction ; owl:someValuesFrom ex:D ] .")
    assert message == f"{BASE}C (restriction): Restriction has no owl:onProperty."


def test_owl034_lists_every_property_sorted() -> None:
    [(_, message)] = _owl(
        "OWL034", "ex:C rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:q, ex:p ; owl:someValuesFrom ex:D ] ."
    )
    assert message == f"{BASE}C (restriction on {BASE}p, {BASE}q): Restriction has more than one owl:onProperty."


def test_restriction_without_named_owner_keeps_the_plain_message() -> None:
    [(focus, message)] = _owl("OWL035", "[ a owl:Restriction ; owl:onProperty ex:p ] .")
    assert focus.startswith("_:")
    assert message == "Restriction has no value, cardinality or self constraint."


def test_owner_text_does_not_change_the_stable_focus() -> None:
    plain = _owl("OWL035", "ex:C rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:p ] .")
    again = _owl("OWL035", "ex:C rdfs:subClassOf [ owl:onProperty ex:p ; a owl:Restriction ] .")
    assert plain == again


@pytest.mark.parametrize(
    ("rule", "restriction"),
    [
        ("OWL036", "owl:minCardinality 'x' "),
        ("OWL037", "owl:minCardinality 3 ; owl:maxCardinality 1 "),
        ("OWL038", "owl:someValuesFrom owl:Nothing "),
        ("OWL039", "owl:allValuesFrom owl:Thing "),
    ],
)
def test_other_restriction_rules_prefix_the_owner(rule: str, restriction: str) -> None:
    result = _owl(rule, f"ex:C rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:p ; {restriction}] .")
    assert result
    assert all(message.startswith(f"{BASE}C (restriction on {BASE}p): ") for _, message in result)


def test_owl040_message_names_owner() -> None:
    body = (
        "ex:p a owl:ObjectProperty . "
        "ex:C rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:p ; owl:hasValue 'x' ] ."
    )
    [(_, message)] = _owl("OWL040", body)
    assert message == (
        f"{BASE}C (restriction on {BASE}p): Restriction on object property {BASE}p "
        "uses literal hasValue rdflib.term.Literal('x')."
    )


# --- ownership ---------------------------------------------------------------------------------

HEADER_NS = "https://header.test/onto"
HEADER_TERM = "https://header.test/onto#"
BIG_NS = "https://vocab.test/concept/"
OTHER_NS = "https://other.test/x#"
THIRD_NS = "https://third.test/y#"


def _terms(spec: dict[str, int]) -> list[URIRef]:
    return [URIRef(f"{ns}t{i}") for ns, count in spec.items() for i in range(count)]


def _ownership(spec: dict[str, int]) -> Ownership:
    return Ownership.for_terms(None, [URIRef(HEADER_NS)], _terms(spec))


def test_constants_document_the_boundaries() -> None:
    assert (MINOR_OWNED_PERCENT, DOMINANT_PERCENT) == (5, 50)


def test_namespace_of_iri() -> None:
    assert namespace_of_iri("https://a.test/x#y") == "https://a.test/x#"
    assert namespace_of_iri("https://a.test/x/y") == "https://a.test/x/"
    assert namespace_of_iri("https://a.test/x#y/z") == "https://a.test/x#y/"
    assert namespace_of_iri("urn:isbn") is None


def test_dominant_namespace_is_added_below_five_percent() -> None:
    own = _ownership({HEADER_TERM: 4, BIG_NS: 51, OTHER_NS: 45})  # 4% owned, 51% dominant
    assert own.mode is OwnershipMode.DERIVED
    assert own.dominant_namespace == BIG_NS
    assert BIG_NS in own.prefixes
    assert HEADER_NS in own.prefixes
    assert own.owns(URIRef(BIG_NS + "t0"))
    assert own.owns(URIRef(HEADER_TERM + "t0"))
    assert not own.owns(URIRef(OTHER_NS + "t0"))


def test_five_percent_exactly_is_not_widened() -> None:
    own = _ownership({HEADER_TERM: 5, BIG_NS: 60, OTHER_NS: 35})  # 5% owned (limit), 60% dominant
    assert own.dominant_namespace is None
    assert not own.owns(URIRef(BIG_NS + "t0"))
    assert own.owns(URIRef(HEADER_TERM + "t0"))


def test_just_below_five_percent_is_widened() -> None:
    own = _ownership({HEADER_TERM: 19, BIG_NS: 381})  # 19/400 = 4.75%
    assert own.dominant_namespace == BIG_NS


def test_fifty_percent_exactly_is_not_dominant() -> None:
    own = _ownership({HEADER_TERM: 4, BIG_NS: 50, OTHER_NS: 46})  # 4% owned, 50% (limit)
    assert own.dominant_namespace is None
    assert not own.owns(URIRef(BIG_NS + "t0"))


def test_fifty_one_percent_is_dominant() -> None:
    own = _ownership({HEADER_TERM: 4, BIG_NS: 51, OTHER_NS: 45})
    assert own.dominant_namespace == BIG_NS


def test_no_dominant_namespace_means_no_widening() -> None:
    own = _ownership({HEADER_TERM: 4, BIG_NS: 32, OTHER_NS: 32, THIRD_NS: 32})
    assert own.dominant_namespace is None
    assert own.prefixes == (HEADER_NS,)


def test_dominant_namespace_with_large_owned_share_is_not_widened() -> None:
    own = _ownership({HEADER_TERM: 30, BIG_NS: 60, OTHER_NS: 10})
    assert own.dominant_namespace is None


def test_nothing_owned_still_falls_back_to_all() -> None:
    own = _ownership({BIG_NS: 60, OTHER_NS: 40})
    assert own.mode is OwnershipMode.ALL
    assert own.dominant_namespace is None


def test_base_mode_is_unchanged() -> None:
    own = Ownership.for_terms(BIG_NS, [URIRef(HEADER_NS)], _terms({HEADER_TERM: 4, BIG_NS: 96}))
    assert own.mode is OwnershipMode.BASE
    assert own.dominant_namespace is None


def test_duplicate_declarations_do_not_skew_the_shares() -> None:
    terms = _terms({HEADER_TERM: 5, BIG_NS: 95})
    own = Ownership.for_terms(None, [URIRef(HEADER_NS)], [*terms, *terms[:5]])
    assert own.dominant_namespace is None  # 5 of 100 distinct terms: at the limit


STW_CONCEPTS = 100


def _stw_like(concepts: int) -> str:
    lines = [
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
        "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .",
        "@prefix stw: <http://zbw.eu/stw/descriptor/> .",
        "<http://www.w3.org/2004/02/skos/core> a owl:Ontology .",
        "skos:Concept a owl:Class .",
        "skos:prefLabel a owl:AnnotationProperty .",
    ]
    lines += [
        f"stw:D{i} a skos:Concept ; skos:inScheme <http://zbw.eu/stw> ; skos:broader stw:D0 ." for i in range(concepts)
    ]
    return "\n".join(lines)


def test_stw_like_input_lints_the_vocabulary_not_skos_core() -> None:
    g = graph(_stw_like(STW_CONCEPTS))  # only the header namespace is derived
    context = GraphContext.build(g)
    assert context.ownership.dominant_namespace == "http://zbw.eu/stw/descriptor/"
    assert len(context.concepts) == STW_CONCEPTS
    result = Linter(g).execute(["SKOS004"])
    assert len(result.findings) == STW_CONCEPTS  # every concept lacks a label
    assert {f.focus.rsplit("/", 1)[0] for f in result.findings} == {"http://zbw.eu/stw/descriptor"}


def test_stw_like_input_with_a_base_is_unchanged() -> None:
    context = GraphContext.build(graph(_stw_like(STW_CONCEPTS)), base="http://zbw.eu/stw/descriptor/")
    assert context.ownership.mode is OwnershipMode.BASE
    assert len(context.concepts) == STW_CONCEPTS


def test_small_skos_only_file_keeps_derived_behaviour() -> None:
    # 2 header terms and 2 concepts: the header owns 50% of the terms, so nothing is widened
    context = GraphContext.build(graph(_stw_like(2)))
    assert context.ownership.dominant_namespace is None
    assert context.concepts == frozenset()
