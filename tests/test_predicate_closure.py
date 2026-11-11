"""One property closure for definitions: sub-properties and equivalences (issue #15).

``closure(seeds, stop)`` is the seeds and every IRI ``p`` with a path ``p → … → seed`` whose steps are
``rdfs:subPropertyOf`` (sub to super) or ``owl:equivalentProperty`` (either way) and which passes through
no node of ``stop``.  ``ctx.descriptions`` closes the definition predicates (no stop).  The
sub-property-only closure of the definitions (0.11.0) is covered in ``test_definition_predicates.py``.
"""

from __future__ import annotations

import pytest
from rdflib import Graph, URIRef
from rdflib.namespace import RDFS, SKOS

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


def test_equivalent_definition_predicates_reach_every_consumer() -> None:
    chain = ONTO + "ex:def owl:equivalentProperty skos:definition . "
    assert fired(chain + "ex:A a owl:Class ; rdfs:label 'A' ; ex:def ex:B .", "LEX013") == [A]
    assert fired(chain + "ex:A a owl:Class ; rdfs:label 'A' ; ex:def '' .", "LEX019") == [A]
    assert fired(chain + "ex:A a owl:Class ; rdfs:label 'A thing' ; ex:def 'A thing' .", "LEX017") == [A]
    described = chain.replace(ONTO, "<https://example.test/onto> a owl:Ontology ; ex:def 'Described.' . ")
    assert fired(described, "ONT006") == []
    classes = "ex:A a owl:Class ; ex:def 'An A.' . ex:B a owl:Class ; ex:def 'A B.' ."
    assert fired(chain + classes, "METRIC002", metric_min_sample=1, metric_max_undefined_ratio=0.0) == []


def test_obo_rules_keep_their_fixed_predicates() -> None:
    # OBO's DEFINITION_PREDICATES stay IAO-only by design: neither a sub-property nor an equivalent of
    # IAO_0000115 satisfies OBO003, though both satisfy LEX002.
    for link in ("rdfs:subPropertyOf", "owl:equivalentProperty"):
        body = ONTO + f"ex:d {link} obo:IAO_0000115 . ex:A a owl:Class ; rdfs:label 'A' ; ex:d 'An A.' ."
        assert fired(body, "OBO003") == [A]
        assert fired(body, "LEX002") == []
