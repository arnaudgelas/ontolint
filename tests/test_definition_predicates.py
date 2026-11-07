"""Definition and label predicates: OBO/PROV defaults and the policy-configurable extras."""

from __future__ import annotations

import pytest
from rdflib import Graph, URIRef

from ontolint.engine import build_context, execute
from ontolint.policy import Policy
from ontolint.rules.support import DESCRIPTIONS, LABELS

PREFIXES = """\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix obo: <http://purl.obolibrary.org/obo/> .
@prefix prov: <http://www.w3.org/ns/prov#> .
@prefix ex: <https://example.test/onto#> .
"""
EXTRA = "https://example.test/vocab#gloss"


def fired(body: str, rule: str, **policy: object) -> list[str]:
    graph = Graph().parse(data=PREFIXES + body, format="turtle")
    ctx = build_context(graph, None, Policy.from_mapping(policy))
    return [f.focus for f in execute(ctx, [rule]).findings]


def context(**mapping: object):  # noqa: ANN201
    return build_context(Graph(), None, Policy.from_mapping(mapping))


def test_default_constants() -> None:
    assert DESCRIPTIONS[-3:] == (
        URIRef("http://purl.obolibrary.org/obo/IAO_0000115"),
        URIRef("http://purl.obolibrary.org/obo/IAO_0000600"),
        URIRef("http://www.w3.org/ns/prov#definition"),
    )
    assert URIRef("http://www.w3.org/2004/02/skos/core#scopeNote") not in DESCRIPTIONS
    assert URIRef("http://www.w3.org/2004/02/skos/core#altLabel") not in LABELS
    assert (
        URIRef("http://www.w3.org/2000/01/rdf-schema#label"),
        URIRef("http://www.w3.org/2004/02/skos/core#prefLabel"),
    ) == LABELS


@pytest.mark.parametrize("predicate", ["obo:IAO_0000115", "obo:IAO_0000600", "prov:definition"])
def test_obo_and_prov_definitions_satisfy_lex002(predicate: str) -> None:
    assert fired(f'ex:A a owl:Class ; rdfs:label "A" ; {predicate} "A defined thing." .', "LEX002") == []


def test_scope_note_is_not_a_definition() -> None:
    # A scope note is documentation for LEX002 (see test_precision_skos.py) but not a definition for the
    # other rules: it is not in the shared DESCRIPTIONS.
    assert fired('ex:A a owl:Class ; rdfs:label "A" ; skos:scopeNote "note" .', "LEX002") == []
    assert fired('ex:A a owl:Class ; rdfs:label "A" ; skos:scopeNote "A" .', "LEX017") == []
    assert fired('ex:A a owl:Class ; rdfs:label "A" ; skos:scopeNote "" .', "LEX019") == []


def test_extra_definition_predicate_from_policy() -> None:
    body = f'ex:A a owl:Class ; rdfs:label "A" ; <{EXTRA}> "A defined thing." .'
    assert fired(body, "LEX002") == ["https://example.test/onto#A"]
    assert fired(body, "LEX002", extra_definition_predicates=[EXTRA]) == []


def test_extra_label_predicate_from_policy() -> None:
    body = f'ex:A a owl:Class ; rdfs:comment "A defined thing." ; <{EXTRA}> "A" .'
    assert fired(body, "LEX001") == ["https://example.test/onto#A"]
    assert fired(body, "LEX001", extra_label_predicates=[EXTRA]) == []


def test_extra_predicates_are_ordered_after_defaults_without_duplicates() -> None:
    ctx = context(extra_definition_predicates=[EXTRA, str(DESCRIPTIONS[0])], extra_label_predicates=[EXTRA, EXTRA])
    assert ctx.descriptions == (*DESCRIPTIONS, URIRef(EXTRA))
    assert ctx.labels == (*LABELS, URIRef(EXTRA))


def test_defaults_without_policy_extras() -> None:
    ctx = context()
    assert ctx.descriptions == DESCRIPTIONS
    assert ctx.labels == LABELS


@pytest.mark.parametrize("field", ["extra_definition_predicates", "extra_label_predicates"])
@pytest.mark.parametrize(
    "value",
    ["http://x.test/a", [1], ["not an iri"], ["http://x.test/a b"], [""], ["http://x.test/<a>"], ["//x.test/a"]],
)
def test_invalid_extra_predicates_are_rejected(field: str, value: object) -> None:
    with pytest.raises(ValueError, match=field):
        Policy.from_mapping({field: value})


@pytest.mark.parametrize("field", ["extra_definition_predicates", "extra_label_predicates"])
def test_valid_extra_predicates_are_stored_as_tuples(field: str) -> None:
    policy = Policy.from_mapping({field: ["urn:x:a", "https://x.test/b", "urn:x:a"]})
    assert getattr(policy, field) == ("urn:x:a", "https://x.test/b")
    assert getattr(Policy.from_mapping({}), field) == ()


def test_ont006_accepts_obo_definition_and_extra_predicate() -> None:
    assert fired("ex:O a owl:Ontology .", "ONT006") == ["https://example.test/onto#O"]
    assert fired('ex:O a owl:Ontology ; obo:IAO_0000115 "Described." .', "ONT006") == []
    body = f'ex:O a owl:Ontology ; <{EXTRA}> "Described." .'
    assert fired(body, "ONT006") == ["https://example.test/onto#O"]
    assert fired(body, "ONT006", extra_definition_predicates=[EXTRA]) == []


def test_metric002_counts_obo_and_extra_definitions() -> None:
    body = f'ex:A a owl:Class ; obo:IAO_0000115 "x" . ex:B a owl:Class ; <{EXTRA}> "y" .'
    strict = {"metric_min_sample": 1, "metric_max_undefined_ratio": 0.0}
    assert fired(body, "METRIC002", **strict) == ["urn:ontolint:graph"]  # only the OBO definition counts
    assert (
        fired(
            body, "METRIC002", metric_min_sample=1, metric_max_undefined_ratio=0.0, extra_definition_predicates=[EXTRA]
        )
        == []
    )
    assert fired(body, "METRIC002", metric_min_sample=1, metric_max_undefined_ratio=0.5) == []


def test_metric001_counts_extra_labels() -> None:
    body = f'ex:A a owl:Class ; <{EXTRA}> "A" .'
    assert fired(body, "METRIC001", metric_min_sample=1, metric_max_unlabelled_ratio=0.0) != []
    assert (
        fired(body, "METRIC001", metric_min_sample=1, metric_max_unlabelled_ratio=0.0, extra_label_predicates=[EXTRA])
        == []
    )


def test_lex018_checks_extra_label_predicates() -> None:
    body = f'ex:A a owl:Class ; rdfs:label "A" ; <{EXTRA}> "<b>A</b>" .'
    assert fired(body, "LEX018") == []
    assert fired(body, "LEX018", extra_label_predicates=[EXTRA]) == ["https://example.test/onto#A"]


def test_lex013_checks_extra_predicates_for_non_literals() -> None:
    body = f'ex:A a owl:Class ; rdfs:label "A" ; <{EXTRA}> ex:B .'
    assert fired(body, "LEX013") == []
    assert fired(body, "LEX013", extra_label_predicates=[EXTRA]) == ["https://example.test/onto#A"]
    assert fired(body, "LEX013", extra_definition_predicates=[EXTRA]) == ["https://example.test/onto#A"]
