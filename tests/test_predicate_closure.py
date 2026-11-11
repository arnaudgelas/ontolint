"""One property closure for labels, definitions and LEX002's notes (issue #15).

``closure(seeds, stop)`` is the seeds and every IRI ``p`` with a path ``p → … → seed`` whose steps are
``rdfs:subPropertyOf`` (sub to super) or ``owl:equivalentProperty`` (either way) and which passes through
no node of ``stop``.  ``ctx.labels`` closes the configured label predicates (``ctx.configured_labels``;
stop: ``skos:altLabel`` and ``skos:hiddenLabel``), ``ctx.descriptions`` the definition predicates (no
stop), and LEX002 its SKOS documentation notes (stop: SKOS's change, editorial and history notes and
``skos:example``).  The
sub-property-only closure of the definitions (0.11.0) is covered in ``test_definition_predicates.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rdflib import Graph, URIRef
from rdflib.namespace import RDFS, SKOS

from ontolint.cli import main
from ontolint.engine import build_context, execute
from ontolint.policy import Policy
from ontolint.rules.runtime import PropertyClosure
from ontolint.rules.support import DESCRIPTIONS, LABELS

PREFIXES = """\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix obo: <http://purl.obolibrary.org/obo/> .
@prefix ex: <https://example.test/onto#> .
"""
ONTO = "<https://example.test/onto> a owl:Ontology . "
NS = "https://example.test/onto#"
A = NS + "A"
B = NS + "B"
EXTRA = "https://example.test/vocab#gloss"
UNLABELLED = 6  # the classes of the METRIC001 example that LEX001 reports
# What the SKOS RDF schema states about its own labels and notes, as a merged import of it would.
SKOS_SCHEMA = (
    "skos:prefLabel rdfs:subPropertyOf rdfs:label . skos:altLabel rdfs:subPropertyOf rdfs:label . "
    "skos:hiddenLabel rdfs:subPropertyOf rdfs:label . "
    + " ".join(
        f"skos:{name} rdfs:subPropertyOf skos:note ."
        for name in ("definition", "scopeNote", "example", "historyNote", "editorialNote", "changeNote")
    )
    + " "
)


def _graph(body: str) -> Graph:
    return Graph().parse(data=PREFIXES + body, format="turtle")


def fired(body: str, rule: str, **policy: object) -> list[str]:
    ctx = build_context(_graph(body), None, Policy.from_mapping(policy))
    return [f.focus for f in execute(ctx, [rule]).findings]


def _labels(body: str, **policy: object) -> tuple[URIRef, ...]:
    return build_context(_graph(body), None, Policy.from_mapping(policy)).labels


def _descriptions(body: str, **policy: object) -> tuple[URIRef, ...]:
    return build_context(_graph(body), None, Policy.from_mapping(policy)).descriptions


def _ex(*names: str) -> tuple[URIRef, ...]:
    return tuple(URIRef(NS + name) for name in names)


def _chain(length: int, seed: str) -> str:
    """``ex:d<length> ⊑ … ⊑ ex:d1 ⊑ seed``."""
    links = [f"ex:d{i + 1} rdfs:subPropertyOf ex:d{i} . " for i in range(1, length)]
    return f"ex:d1 rdfs:subPropertyOf {seed} . " + "".join(links)


# --- The closure itself ---------------------------------------------------------------------------------


def test_the_closure_is_sorted_after_the_seeds_and_skips_blank_nodes_and_stops() -> None:
    graph = _graph(
        "ex:z rdfs:subPropertyOf _:b . _:b owl:equivalentProperty skos:definition . "
        "ex:a owl:equivalentProperty ex:z . ex:s rdfs:subPropertyOf skos:definition . ex:t rdfs:subPropertyOf ex:s ."
    )
    closure = PropertyClosure(graph)
    assert closure.below((SKOS.definition,)) == (SKOS.definition, *_ex("a", "s", "t", "z"))
    # A stop node is neither returned nor walked through.
    assert closure.below((SKOS.definition,), frozenset(_ex("s"))) == (SKOS.definition, *_ex("a", "z"))
    # A seed in the stop set stays a seed.
    assert closure.below((SKOS.definition, RDFS.label), frozenset({RDFS.label})) == (
        SKOS.definition,
        RDFS.label,
        *_ex("a", "s", "t", "z"),
    )
    assert closure.below((SKOS.definition,)) is closure.below((SKOS.definition,))  # cached


def test_an_empty_graph_closes_to_its_seeds() -> None:
    assert PropertyClosure(Graph()).below(LABELS) == LABELS


# --- (a) label predicates -------------------------------------------------------------------------------


@pytest.mark.parametrize("seed", ["rdfs:label", "skos:prefLabel"])
@pytest.mark.parametrize("length", [1, 3])
def test_a_transitive_subproperty_of_a_label_predicate_is_a_label(length: int, seed: str) -> None:
    term = f"ex:A a owl:Class ; ex:d{length} 'A'@en ."
    assert fired(ONTO + _chain(length, seed) + term, "LEX001") == []
    assert fired(ONTO + term, "LEX001") == [A]
    assert _labels(_chain(length, seed)) == (*LABELS, *sorted(_ex(*(f"d{i}" for i in range(1, length + 1))), key=str))


def test_a_subproperty_of_an_extra_label_predicate_is_a_label() -> None:
    body = ONTO + f"ex:short rdfs:subPropertyOf <{EXTRA}> . ex:A a owl:Class ; ex:short 'A' ."
    assert fired(body, "LEX001") == [A]
    assert fired(body, "LEX001", extra_label_predicates=[EXTRA]) == []
    assert _labels(body, extra_label_predicates=[EXTRA]) == (*LABELS, URIRef(EXTRA), *_ex("short"))


def test_a_label_subproperty_cycle_terminates_and_counts() -> None:
    body = (
        ONTO + "ex:l1 rdfs:subPropertyOf ex:l2 . ex:l2 rdfs:subPropertyOf ex:l1 . ex:l1 rdfs:subPropertyOf ex:l1 . "
        "ex:l1 rdfs:subPropertyOf rdfs:label . rdfs:label rdfs:subPropertyOf ex:l2 . ex:A a owl:Class ; ex:l2 'A' ."
    )
    assert fired(body, "LEX001") == []
    assert _labels(body) == (*LABELS, *_ex("l1", "l2"))


def test_a_subproperty_of_a_description_is_not_a_label() -> None:
    # rdfs:comment is a definition predicate: ex:c is a definition (LEX002), never a label (LEX001).
    body = ONTO + "ex:c rdfs:subPropertyOf rdfs:comment . ex:A a owl:Class ; ex:c 'An A.' ."
    assert fired(body, "LEX001") == [A]
    assert fired(body, "LEX002") == []
    assert _labels(body) == LABELS


def test_alternative_labels_never_join_the_label_closure() -> None:
    # The SKOS schema puts altLabel and hiddenLabel below rdfs:label; LEX001 and METRIC001 still ignore them.
    body = (
        ONTO
        + SKOS_SCHEMA
        + "ex:alt rdfs:subPropertyOf skos:altLabel . ex:A a owl:Class ; skos:altLabel 'A' ; ex:alt 'Aa' ."
    )
    assert _labels(body) == LABELS
    assert fired(body, "LEX001") == [A]
    hidden = body + " ex:hid owl:equivalentProperty skos:hiddenLabel . ex:B a owl:Class ; ex:hid 'B' ."
    assert fired(hidden, "LEX001") == [A, B]


def test_a_superproperty_of_a_label_predicate_is_not_a_label() -> None:
    body = ONTO + "rdfs:label rdfs:subPropertyOf ex:name . ex:A a owl:Class ; ex:name 'A' ."
    assert fired(body, "LEX001") == [A]
    assert _labels(body) == LABELS


def test_an_iri_valued_label_subproperty_is_still_no_label() -> None:
    body = ONTO + "ex:l rdfs:subPropertyOf rdfs:label . ex:A a owl:Class ; ex:l ex:B ."
    assert fired(body, "LEX001") == [A]
    assert fired(body, "LEX013") == [A]


def test_a_deprecated_label_subproperty_still_labels() -> None:
    body = ONTO + "ex:l rdfs:subPropertyOf rdfs:label ; owl:deprecated true . ex:A a owl:Class ; ex:l 'A' ."
    assert fired(body, "LEX001") == []


@pytest.mark.parametrize("value", ["'<b>A</b>'", "'<b>A</b>'@en", "'R&amp;D'@fr-CA"])
def test_lex018_checks_label_subproperties_in_any_language(value: str) -> None:
    chain = "ex:l rdfs:subPropertyOf ex:m . ex:m rdfs:subPropertyOf skos:prefLabel . "
    body = ONTO + chain + f"ex:A a owl:Class ; rdfs:label 'A' ; ex:l {value} ."
    assert fired(body, "LEX018") == [A]
    assert fired(body.replace("skos:prefLabel", "rdfs:comment"), "LEX018") == []


# BFO 2020's pattern: each class has an rdfs:label and two untagged specification labels below it.
BFO_LABELS = (
    "ex:owlLabel rdfs:subPropertyOf rdfs:label . ex:clifLabel rdfs:subPropertyOf rdfs:label . "
    "ex:A a owl:Class ; rdfs:label 'continuant'@en ; ex:owlLabel 'continuant' ; ex:clifLabel 'Continuant' . "
)


@pytest.mark.parametrize("rule", ["LEX003", "LEX006"])
def test_specialised_labels_are_not_second_main_labels(rule: str) -> None:
    # LEX003 and LEX006 judge the main labels: 0.12.0 behaviour, which the closure must not change.
    assert fired(ONTO + BFO_LABELS, rule) == []
    asserted = BFO_LABELS.replace("ex:owlLabel 'continuant'", "rdfs:label 'continuant'")
    assert fired(ONTO + asserted.replace("ex:clifLabel", "rdfs:label"), rule) == [A]
    pref = (
        ONTO + "ex:pref rdfs:subPropertyOf skos:prefLabel . ex:A a owl:Class ; ex:pref 'A'@en ; rdfs:label '1 A'@en ."
    )
    assert fired(pref, rule) == []


def test_lex001_lex005_and_lex018_judge_specialised_labels() -> None:
    body = ONTO + BFO_LABELS.replace("rdfs:label 'continuant'@en ; ", "").replace("'Continuant'", "' <b>C</b>'")
    assert fired(body, "LEX001") == []
    assert fired(body, "LEX005") == [A]
    assert fired(body, "LEX018") == [A]


def test_lex008_accepts_any_label_in_the_language() -> None:
    # LEX008 is "Missing label in a required language": a coverage question, like LEX001, so any label
    # in the language counts, a specialised one included.  Only absence is reported, so the BFO
    # pattern cannot make it fire.
    body = ONTO + "ex:short rdfs:subPropertyOf rdfs:label . ex:A a owl:Class ; rdfs:label 'A'@en ; ex:short 'A'@fr ."
    assert fired(body, "LEX008", languages=["en", "fr"]) == []
    assert fired(body, "LEX008", languages=["en", "fr", "de"]) == [A]
    assert fired(body.replace("ex:short 'A'@fr", "skos:altLabel 'A'@fr"), "LEX008", languages=["fr"]) == [A]
    assert fired(ONTO + BFO_LABELS, "LEX008", languages=["en"]) == []


def test_lex004_and_cls010_compare_main_labels_only() -> None:
    shared = (
        ONTO + "ex:short rdfs:subPropertyOf rdfs:label . ex:P a owl:Class ; rdfs:label 'P' . "
        "ex:A a owl:Class ; rdfs:subClassOf ex:P ; rdfs:label 'Alpha' ; ex:short 'X' . "
        "ex:B a owl:Class ; rdfs:subClassOf ex:P ; rdfs:label 'Beta' ; ex:short 'X' . "
    )
    assert fired(shared, "LEX004") == []
    assert fired(shared, "CLS010") == []
    assert fired(shared.replace("ex:short 'X'", "rdfs:label 'X'"), "LEX004") == [A]
    assert sorted(fired(shared.replace("ex:short 'X'", "rdfs:label 'X'"), "CLS010")) == [A, B]


# A term with no configured label: the labels below the configured predicates are its main labels.
PREF = ONTO + "ex:pref rdfs:subPropertyOf skos:prefLabel . ex:name rdfs:subPropertyOf rdfs:label . "


def test_lex001_and_lex008_agree_on_a_term_labelled_only_below_skos_preflabel() -> None:
    body = PREF + "ex:A a owl:Class ; ex:pref 'Chair'@en ."
    assert A not in fired(body, "LEX001")
    assert A not in fired(body, "LEX008", languages=["en"])
    assert A in fired(body, "LEX008", languages=["en", "fr"])
    assert A in fired(body.replace("ex:pref", "skos:altLabel"), "LEX008", languages=["en"])


@pytest.mark.parametrize(
    ("rule", "terms", "expected", "policy"),
    [
        ("LEX003", "ex:A a owl:Class ; ex:pref 'A'@en , 'Alpha'@en .", [A], {}),
        ("LEX003", "ex:A a owl:Class ; ex:name 'A'@en , 'Alpha'@en .", [A], {}),
        # The preferred family wins, as skos:prefLabel does over rdfs:label.
        ("LEX003", "ex:A a owl:Class ; ex:pref 'A'@en ; ex:name 'Alpha'@en .", [], {}),
        ("LEX006", "ex:A a owl:Class ; ex:pref 'Lamp' , 'Lampe'@fr .", [A], {}),
        ("LEX006", "ex:A a owl:Class ; ex:pref 'Lamp'@en , 'Lampe'@fr .", [], {}),
        ("LEX008", "ex:A a owl:Class ; ex:pref 'A'@en ; ex:name 'A'@fr .", [], {"languages": ["en", "fr"]}),
        ("LEX004", "ex:A a owl:Class ; ex:pref 'Chair'@en . ex:B a owl:Class ; ex:pref 'Chair'@en .", [A], {}),
        ("LEX004", "ex:A a owl:Class ; ex:pref 'Chair'@en . ex:B a owl:Class ; rdfs:label 'Chair'@en .", [A], {}),
        ("LEX015", "ex:A a owl:Class ; ex:pref 'A'@en ; skos:altLabel 'A'@en .", [A], {}),
        (
            "LEX016",
            "ex:A a owl:Class ; ex:pref 'Chair'@en . "
            "ex:B a owl:Class ; rdfs:label 'Seat'@en ; skos:altLabel 'Chair'@en .",
            [B],
            {},
        ),
        (
            "CLS010",
            "ex:P a owl:Class ; ex:pref 'P' . ex:A a owl:Class ; rdfs:subClassOf ex:P ; ex:pref 'X' . "
            "ex:B a owl:Class ; rdfs:subClassOf ex:P ; ex:name 'X' .",
            [A, B],
            {},
        ),
    ],
)
def test_the_main_labels_fall_back_to_the_closure_without_a_configured_label(
    rule: str, terms: str, expected: list[str], policy: dict[str, object]
) -> None:
    assert sorted(f for f in fired(PREF + terms, rule, **policy) if f in (A, B)) == expected


# A configured label in one language must not hide a preferred label (a sub-property of
# skos:prefLabel, hence a skos:prefLabel by entailment) in another.
BESIDE = "ex:A a owl:Class ; rdfs:label 'Table'@fr ; "


@pytest.mark.parametrize(
    ("rule", "terms", "expected", "policy"),
    [
        ("LEX008", BESIDE + "ex:pref 'Table'@en .", [], {"languages": ["en"]}),
        ("LEX003", "ex:A a owl:Class ; skos:prefLabel 'A'@en ; ex:pref 'Alpha'@en .", [A], {}),
        ("LEX003", "ex:A a owl:Class ; rdfs:label '1 A'@en ; ex:pref 'A'@en .", [], {}),
        ("LEX006", BESIDE + "ex:pref 'Table' .", [A], {}),
        ("LEX004", BESIDE + "ex:pref 'Chair'@en . ex:B a owl:Class ; rdfs:label 'Chair'@en .", [A], {}),
        ("LEX015", BESIDE + "ex:pref 'Desk'@en ; skos:altLabel 'Desk'@en .", [A], {}),
        (
            "LEX016",
            BESIDE + "ex:pref 'Chair'@en . ex:B a owl:Class ; rdfs:label 'Seat'@en ; skos:altLabel 'Chair'@en .",
            [B],
            {},
        ),
        (
            "CLS010",
            "ex:P a owl:Class ; rdfs:label 'P' . "
            "ex:A a owl:Class ; rdfs:subClassOf ex:P ; rdfs:label 'Alpha'@fr ; ex:pref 'X' . "
            "ex:B a owl:Class ; rdfs:subClassOf ex:P ; rdfs:label 'Beta'@fr ; ex:pref 'X' .",
            [A, B],
            {},
        ),
    ],
)
def test_a_preferred_label_subproperty_is_a_main_label_beside_a_configured_one(
    rule: str, terms: str, expected: list[str], policy: dict[str, object]
) -> None:
    assert sorted(f for f in fired(PREF + terms, rule, **policy) if f in (A, B)) == expected


def test_specialised_labels_stay_out_of_the_main_labels_in_every_language() -> None:
    # BFO 2020: two untagged specification labels below rdfs:label beside a tagged rdfs:label are not
    # main labels in the untagged group either (no second label, no mixing, no collision).
    other = BFO_LABELS.replace("ex:A", "ex:B").replace("'continuant'@en", "'occurrent'@en")
    other = other.replace(
        "ex:owlLabel rdfs:subPropertyOf rdfs:label . ex:clifLabel rdfs:subPropertyOf rdfs:label . ", ""
    )
    for rule in ("LEX003", "LEX004", "LEX006", "LEX015", "LEX016", "CLS010"):
        assert fired(ONTO + BFO_LABELS + other, rule) == [], rule


def test_an_extra_label_predicate_is_a_main_label_for_lex015_and_lex016() -> None:
    body = ONTO + f"ex:A a owl:Class ; <{EXTRA}> 'A'@en ; skos:altLabel 'A'@en . "
    assert fired(body, "LEX015", extra_label_predicates=[EXTRA]) == [A]
    other = (
        ONTO
        + f"ex:A a owl:Class ; <{EXTRA}> 'Chair'@en . ex:B a owl:Class ; rdfs:label 'B' ; skos:altLabel 'Chair'@en ."
    )
    assert fired(other, "LEX016", extra_label_predicates=[EXTRA]) == [B]


def test_a_label_subproperty_declared_in_an_import_labels_the_root_terms(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # As for definitions since 0.11.0: under --follow-imports the import closure is the ontology, so an
    # imported ``⊑ rdfs:label`` axiom (MOD's mod:acronym) makes the root file's values labels.
    module = tmp_path / "vocab.ttl"
    module.write_text(
        PREFIXES + "<https://example.test/vocab> a owl:Ontology .\nex:acronym rdfs:subPropertyOf rdfs:label .\n",
        encoding="utf-8",
    )
    root = tmp_path / "root.ttl"
    root.write_text(
        PREFIXES + f"<https://example.test/onto> a owl:Ontology ; owl:imports <{module.as_uri()}> .\n"
        "ex:A a owl:Class ; ex:acronym 'BFO.' ; skos:definition 'An A.'@en .\n",
        encoding="utf-8",
    )
    out = tmp_path / "r.json"
    argv = [str(root), "--select", "LEX001,LEX012", "--format", "json", "--output", str(out), "--fail-on", "never"]

    def rules() -> list[tuple[str, str]]:
        return [(f["rule"], f["focus"]) for f in json.loads(out.read_text(encoding="utf-8"))["findings"]]

    main([*argv, "--follow-imports"])
    assert rules() == [("LEX012", A)]
    main(argv)
    assert rules() == [("LEX001", A)]
    capsys.readouterr()


def test_cls015_accepts_a_specialised_label() -> None:
    kids = " ".join(f"ex:K{i} a owl:Class ; rdfs:label 'K{i}' ; rdfs:subClassOf ex:P ." for i in range(6))
    body = ONTO + "ex:short rdfs:subPropertyOf rdfs:label . ex:P a owl:Class ; ex:short 'P' . " + kids
    assert fired(body, "CLS015") == []
    assert fired(body.replace("ex:short 'P'", "ex:other 'P'"), "CLS015") == [NS + "P"]


def test_metric001_counts_exactly_lex001_with_label_subproperties() -> None:
    chain = (
        "ex:l2 rdfs:subPropertyOf ex:l1 . ex:l1 owl:equivalentProperty ex:l0 . ex:l0 rdfs:subPropertyOf rdfs:label . "
    )
    classes = [f"ex:C{i} a owl:Class ; ex:l2 'C{i}' ." for i in range(4)]
    classes += [f"ex:D{i} a owl:Class ; ex:l2 ex:B ." for i in range(3)]  # an IRI is not a label
    classes += [f"ex:E{i} a owl:Class ; ex:alt 'E{i}' ." for i in range(3)]  # an alternative label is not one
    body = ONTO + chain + "ex:alt rdfs:subPropertyOf skos:altLabel . " + " ".join(classes)
    policy = Policy.from_mapping({"metric_min_sample": 1, "metric_max_unlabelled_ratio": 0.0})
    findings = execute(build_context(_graph(body), None, policy), ["LEX001", "METRIC001"]).findings
    assert len([f for f in findings if f.rule == "LEX001"]) == UNLABELLED
    assert [f.message for f in findings if f.rule == "METRIC001"] == ["6 of 10 classes lack a label (0.60 > 0.00)."]


def test_obo_rules_keep_their_fixed_predicates() -> None:
    # OBO's DEFINITION_PREDICATES stay IAO-only by design: neither a sub-property nor an equivalent of
    # IAO_0000115 satisfies OBO003, though both satisfy LEX002.
    for link in ("rdfs:subPropertyOf", "owl:equivalentProperty"):
        body = ONTO + f"ex:d {link} obo:IAO_0000115 . ex:A a owl:Class ; rdfs:label 'A' ; ex:d 'An A.' ."
        assert fired(body, "OBO003") == [A]
        assert fired(body, "LEX002") == []


# --- (b) owl:equivalentProperty -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "links",
    [
        "ex:d owl:equivalentProperty skos:definition .",
        "skos:definition owl:equivalentProperty ex:d .",  # symmetric
        "ex:d owl:equivalentProperty ex:q . ex:q rdfs:subPropertyOf skos:definition .",  # p ≡ q ⊑ def
        "ex:d rdfs:subPropertyOf ex:q . ex:q owl:equivalentProperty obo:IAO_0000115 .",  # p ⊑ q ≡ def
        "ex:d owl:equivalentProperty ex:q . ex:r owl:equivalentProperty ex:q . ex:r rdfs:subPropertyOf rdfs:comment .",
        "ex:d owl:equivalentProperty ex:d . ex:d owl:equivalentProperty ex:q . ex:q owl:equivalentProperty ex:d . "
        "ex:q owl:equivalentProperty skos:definition .",  # cycles and a self-loop
    ],
)
def test_an_equivalent_of_a_definition_predicate_counts(links: str) -> None:
    term = "ex:A a owl:Class ; rdfs:label 'A' ; ex:d 'An A is a thing.' ."
    assert fired(ONTO + links + " " + term, "LEX002") == []
    assert fired(ONTO + term, "LEX002") == [A]
    assert URIRef(NS + "d") in _descriptions(links)


@pytest.mark.parametrize(
    "links",
    [
        "ex:d owl:equivalentProperty ex:q .",  # equivalent to an unrelated predicate only
        "ex:d owl:equivalentProperty rdfs:label .",  # a label, not a definition
        "ex:d owl:equivalentProperty rdfs:seeAlso .",
        "skos:definition rdfs:subPropertyOf ex:q . ex:d owl:equivalentProperty ex:q .",  # beside a super-property
    ],
)
def test_an_equivalent_of_a_non_definition_predicate_does_not_count(links: str) -> None:
    term = "ex:A a owl:Class ; rdfs:label 'A' ; ex:d 'An A is a thing.' ."
    assert fired(ONTO + links + " " + term, "LEX002") == [A]
    assert _descriptions(links) == DESCRIPTIONS


def test_an_equivalent_of_a_label_predicate_is_a_label() -> None:
    body = ONTO + "ex:name owl:equivalentProperty rdfs:label . ex:A a owl:Class ; ex:name 'A' ."
    assert fired(body, "LEX001") == []
    assert _labels(body) == (*LABELS, *_ex("name"))


def test_equivalent_definition_predicates_reach_every_consumer() -> None:
    chain = ONTO + "ex:def owl:equivalentProperty skos:definition . "
    assert fired(chain + "ex:A a owl:Class ; rdfs:label 'A' ; ex:def ex:B .", "LEX013") == [A]
    assert fired(chain + "ex:A a owl:Class ; rdfs:label 'A' ; ex:def '' .", "LEX019") == [A]
    assert fired(chain + "ex:A a owl:Class ; rdfs:label 'A thing' ; ex:def 'A thing' .", "LEX017") == [A]
    described = chain.replace(ONTO, "<https://example.test/onto> a owl:Ontology ; ex:def 'Described.' . ")
    assert fired(described, "ONT006") == []
    classes = "ex:A a owl:Class ; ex:def 'An A.' . ex:B a owl:Class ; ex:def 'A B.' ."
    assert fired(chain + classes, "METRIC002", metric_min_sample=1, metric_max_undefined_ratio=0.0) == []


# --- (c) sub-properties of LEX002's SKOS documentation notes --------------------------------------------


def _documented(links: str) -> bool:
    term = "ex:A a owl:Class ; rdfs:label 'A' ; ex:n 'About A.' ."
    return fired(ONTO + links + " " + term, "LEX002") == []


@pytest.mark.parametrize(
    "links",
    [
        "ex:n rdfs:subPropertyOf skos:note .",
        "ex:n rdfs:subPropertyOf skos:scopeNote .",
        "ex:n rdfs:subPropertyOf ex:m . ex:m rdfs:subPropertyOf skos:note .",
        "ex:n owl:equivalentProperty skos:scopeNote .",
        "ex:n owl:equivalentProperty ex:m . ex:m rdfs:subPropertyOf skos:note . ex:m rdfs:subPropertyOf ex:n .",
        SKOS_SCHEMA + "ex:n rdfs:subPropertyOf skos:scopeNote .",
    ],
)
def test_a_subproperty_of_a_documentation_note_satisfies_lex002(links: str) -> None:
    assert _documented(links)


@pytest.mark.parametrize(
    "links",
    [
        "",
        "skos:note rdfs:subPropertyOf ex:n .",  # a super-property of a note is not one
        "ex:n owl:equivalentProperty ex:m .",
        # SKOS's notes about the record rather than the meaning stay out, even below skos:note.
        SKOS_SCHEMA + "ex:n rdfs:subPropertyOf skos:editorialNote .",
        SKOS_SCHEMA + "ex:n rdfs:subPropertyOf skos:historyNote .",
        SKOS_SCHEMA + "ex:n owl:equivalentProperty skos:changeNote .",
        SKOS_SCHEMA + "ex:n rdfs:subPropertyOf skos:example .",
    ],
)
def test_other_notes_do_not_satisfy_lex002(links: str) -> None:
    assert not _documented(links)


@pytest.mark.parametrize("name", ["editorialNote", "historyNote", "changeNote", "example"])
def test_skos_record_notes_do_not_satisfy_lex002_under_the_skos_schema(name: str) -> None:
    assert fired(ONTO + SKOS_SCHEMA + f"ex:A a owl:Class ; rdfs:label 'A' ; skos:{name} 'x' .", "LEX002") == [A]


def test_lex002_does_not_judge_what_a_note_says() -> None:
    # A known false negative: a vocabulary that declares a non-descriptive property below skos:note
    # documents its terms with it, as a bare ``skos:note "3"`` does (0.12.0).
    order = "ex:A a owl:Class ; rdfs:label 'A' ; ex:order '3' ."
    assert fired(ONTO + "ex:order rdfs:subPropertyOf skos:note . " + order, "LEX002") == []
    assert fired(ONTO + order.replace("ex:order", "skos:note"), "LEX002") == []


def test_a_note_subproperty_is_not_a_definition_for_the_other_rules() -> None:
    chain = ONTO + "ex:n rdfs:subPropertyOf skos:note . "
    assert URIRef(NS + "n") not in _descriptions(chain)
    assert fired(chain + "ex:A a owl:Class ; rdfs:label 'A thing' ; ex:n 'A thing' .", "LEX017") == []
    assert fired(chain + "ex:A a owl:Class ; rdfs:label 'A' ; ex:n '' .", "LEX019") == []
    classes = "ex:A a owl:Class ; ex:n 'An A.' . ex:B a owl:Class ; ex:n 'A B.' ."
    assert fired(chain + classes, "METRIC002", metric_min_sample=1, metric_max_undefined_ratio=0.0) != []
