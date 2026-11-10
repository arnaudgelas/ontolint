"""Definition and label predicates: OBO/PROV defaults and the policy-configurable extras."""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import pytest
from rdflib import BNode, Graph, URIRef
from rdflib.namespace import RDFS, SKOS

from ontolint.cli import main
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
    assert DESCRIPTIONS[-4:] == (
        URIRef("http://purl.obolibrary.org/obo/IAO_0000115"),
        URIRef("http://purl.obolibrary.org/obo/IAO_0000600"),
        URIRef("http://www.w3.org/ns/prov#definition"),
        URIRef("http://www.ontologyrepository.com/CommonCoreOntologies/definition"),
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


def test_a_cco_1x_definition_counts() -> None:
    # SDC's vendored CCO 1.x: every class carries cco:definition and no skos:definition.
    body = (
        "<https://example.test/onto> a owl:Ontology . ex:A a owl:Class ; rdfs:label 'A'@en ; "
        "<http://www.ontologyrepository.com/CommonCoreOntologies/definition> 'An A is a thing.'@en ."
    )
    assert fired(body, "LEX002") == []


def test_a_subproperty_of_a_definition_predicate_counts() -> None:
    body = (
        "<https://example.test/onto> a owl:Ontology . ex:def rdfs:subPropertyOf skos:definition . "
        "ex:A a owl:Class ; rdfs:label 'A'@en ; ex:def 'An A is a thing.'@en ."
    )
    assert fired(body, "LEX002") == []
    assert fired(body.replace("ex:def rdfs:subPropertyOf skos:definition . ", ""), "LEX002") == [
        "https://example.test/onto#A"
    ]


def _stderr(tmp_path: Path, capsys: pytest.CaptureFixture[str], body: str) -> str:
    path = tmp_path / "o.ttl"
    path.write_text(PREFIXES + body, encoding="utf-8")
    main([str(path), "--select", "LEX002", "--fail-on", "never", "--output", str(tmp_path / "r.txt")])
    return capsys.readouterr().err


def test_an_unknown_definition_predicate_is_suggested(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    terms = "".join(f"ex:C{i} a owl:Class ; <https://v.test/termDefinition> 'Def {i}.'@en .\n" for i in range(12))
    err = _stderr(tmp_path, capsys, "<https://example.test/onto> a owl:Ontology .\n" + terms)
    assert "TOOL005: note: 12 of the 12 terms LEX002 reports" in err
    assert "<https://v.test/termDefinition>" in err


def test_no_suggestion_for_a_few_terms_or_an_unrelated_predicate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    few = "".join(f"ex:C{i} a owl:Class ; <https://v.test/termDefinition> 'Def {i}.'@en .\n" for i in range(3))
    assert "TOOL005" not in _stderr(tmp_path, capsys, few)
    other = "".join(f"ex:C{i} a owl:Class ; <https://v.test/note> 'Note {i}.'@en .\n" for i in range(12))
    assert "TOOL005" not in _stderr(tmp_path, capsys, other)


def test_header_metadata_on_a_node_naming_the_ontology_counts() -> None:
    # MOD describes itself on <…/mod#>, which names the ontology <…/mod> with owl:ontologyIRI.
    body = (
        "@prefix dcterms: <http://purl.org/dc/terms/> .\n"
        "<https://example.test/mod> a owl:Ontology .\n"
        "<https://example.test/mod#> owl:ontologyIRI <https://example.test/mod> ;\n"
        "    dcterms:license <https://creativecommons.org/licenses/by/4.0/> ; owl:versionInfo '3.2' ;\n"
        "    dcterms:creator 'Someone' ; dcterms:created '2024-01-01' ; rdfs:comment 'A vocabulary.' ;\n"
        "    dcterms:publisher 'An organisation' .\n"
    )
    for rule in ("ONT003", "ONT004", "ONT005", "ONT006", "GOV004"):
        assert fired(body, rule) == [], rule
    assert fired(body.replace("owl:ontologyIRI", "rdfs:seeAlso"), "ONT003") == ["https://example.test/mod"]


def _cli(tmp_path: Path, capsys: pytest.CaptureFixture[str], text: str, rule: str) -> tuple[list[str], str]:
    path = tmp_path / "o.ttl"
    path.write_text(text, encoding="utf-8")
    out = tmp_path / "r.json"
    main([str(path), "--select", rule, "--format", "json", "--fail-on", "never", "--output", str(out)])
    messages = [f["message"] for f in json.loads(out.read_text(encoding="utf-8"))["findings"]]
    return messages, capsys.readouterr().err


def test_ont003_mentions_a_licence_named_only_in_an_spdx_comment(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Tractus-X: "# SPDX-License-Identifier: CC-BY-4.0" in the file header, no dcterms:license.
    header = PREFIXES + "<https://example.test/onto> a owl:Ontology .\n"
    messages, _err = _cli(tmp_path, capsys, "# SPDX-License-Identifier: CC-BY-4.0\n" + header, "ONT003")
    assert messages == [
        "Ontology has no license annotation. The file names CC-BY-4.0 only in an SPDX comment; "
        "state it with dcterms:license."
    ]
    assert _cli(tmp_path, capsys, header, "ONT003")[0] == ["Ontology has no license annotation."]


def test_rdflib_warnings_do_not_leak_onto_stderr(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # MOD: an ill-typed date made RDFLib print a traceback while parsing.
    text = PREFIXES + "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\nex:a ex:issued '2024-06-2'^^xsd:date .\n"
    _messages, err = _cli(tmp_path, capsys, text, "ONT001")
    assert err == ""


# --- rdfs:subPropertyOf closure (LEX002-CLOSURE) --------------------------------------------------------

A = "https://example.test/onto#A"
ONTO = "<https://example.test/onto> a owl:Ontology . "
ONTO_NS = "https://example.test/onto#"


def _chain(length: int, seed: str) -> str:
    """``ex:d<length-1> ⊑ … ⊑ ex:d1 ⊑ seed``: a definition annotation ``length`` sub-property steps below ``seed``."""
    links = [f"ex:d{i + 1} rdfs:subPropertyOf ex:d{i} . " for i in range(1, length)]
    return f"ex:d1 rdfs:subPropertyOf {seed} . " + "".join(links)


def _descriptions(body: str, **policy: object) -> tuple[URIRef, ...]:
    graph = Graph().parse(data=PREFIXES + body, format="turtle")
    return build_context(graph, None, Policy.from_mapping(policy)).descriptions


@pytest.mark.parametrize("seed", ["skos:definition", "rdfs:comment", "obo:IAO_0000115"])
@pytest.mark.parametrize("length", [2, 5])
def test_a_transitive_subproperty_of_a_definition_predicate_counts(length: int, seed: str) -> None:
    term = f"ex:A a owl:Class ; rdfs:label 'A'@en ; ex:d{length} 'An A is a thing.'@en ."
    assert fired(ONTO + _chain(length, seed) + term, "LEX002") == []
    # The exact example of the 2026-11-10 review.
    todo = (
        "ex:def2 rdfs:subPropertyOf ex:def1 . ex:def1 rdfs:subPropertyOf skos:definition . "
        "ex:A a owl:Class ; rdfs:label 'A'@en ; ex:def2 'An A is a thing.'@en ."
    )
    assert fired(ONTO + todo, "LEX002") == []


def test_a_subproperty_cycle_terminates_and_counts() -> None:
    body = (
        ONTO + "ex:def1 rdfs:subPropertyOf ex:def2 . ex:def2 rdfs:subPropertyOf ex:def1 . "
        "ex:def1 rdfs:subPropertyOf skos:definition . "
        "ex:A a owl:Class ; rdfs:label 'A'@en ; ex:def2 'An A is a thing.'@en ."
    )
    assert fired(body, "LEX002") == []
    loops = body + " ex:def1 rdfs:subPropertyOf ex:def1 . skos:definition rdfs:subPropertyOf ex:def2 ."
    assert fired(loops, "LEX002") == []
    descriptions = _descriptions(loops)
    assert descriptions.count(URIRef("http://www.w3.org/2004/02/skos/core#definition")) == 1
    assert descriptions == (*DESCRIPTIONS, URIRef(ONTO_NS + "def1"), URIRef(ONTO_NS + "def2"))


def test_a_deep_subproperty_chain_does_not_recurse() -> None:
    # rdflib's Graph.transitive_subjects recurses once per link and raises RecursionError here.
    length = sys.getrecursionlimit() * 3
    graph = Graph()
    links = [URIRef(f"{ONTO_NS}d{i}") for i in range(length)]
    graph.add((links[0], RDFS.subPropertyOf, SKOS.definition))
    for sub, sup in itertools.pairwise(links):
        graph.add((sup, RDFS.subPropertyOf, sub))
    descriptions = build_context(graph, None, Policy()).descriptions
    assert len(descriptions) == len(set(descriptions)) == len(DESCRIPTIONS) + length
    assert set(descriptions[len(DESCRIPTIONS) :]) == set(links)


def test_a_chain_that_never_reaches_a_definition_predicate_does_not_count() -> None:
    term = "ex:A a owl:Class ; rdfs:label 'A'@en ; ex:def2 'An A is a thing.'@en ."
    assert fired(ONTO + "ex:def2 rdfs:subPropertyOf ex:def1 . " + term, "LEX002") == [A]
    descriptions = _descriptions("ex:def2 rdfs:subPropertyOf ex:def1 .")
    assert URIRef(ONTO_NS + "def1") not in descriptions
    assert URIRef(ONTO_NS + "def2") not in descriptions
    # The walk goes downwards only: a super-property of a definition predicate is not one.
    upward = ONTO + "skos:definition rdfs:subPropertyOf ex:def1 . ex:A a owl:Class ; rdfs:label 'A' ; ex:def1 'x' ."
    assert fired(upward, "LEX002") == [A]
    assert _descriptions("skos:definition rdfs:subPropertyOf ex:def1 .") == DESCRIPTIONS


def test_a_broken_chain_does_not_count() -> None:
    body = (
        ONTO + "ex:def3 rdfs:subPropertyOf ex:def2 . ex:def1 rdfs:subPropertyOf skos:definition . "
        "ex:A a owl:Class ; rdfs:label 'A'@en ; ex:def3 'An A is a thing.'@en ."
    )
    assert fired(body, "LEX002") == [A]


def test_a_chain_through_a_blank_node_counts_but_the_node_is_not_a_predicate() -> None:
    chain = "ex:p rdfs:subPropertyOf _:b . _:b rdfs:subPropertyOf skos:definition . "
    descriptions = _descriptions(chain)
    assert URIRef(ONTO_NS + "p") in descriptions
    assert not any(isinstance(node, BNode) for node in descriptions)
    assert descriptions == (*DESCRIPTIONS, URIRef(ONTO_NS + "p"))
    assert fired(ONTO + chain + "ex:A a owl:Class ; rdfs:label 'A' ; ex:p 'An A.' .", "LEX002") == []


def test_derived_definition_predicates_are_sorted_and_follow_the_seeds() -> None:
    body = "ex:z rdfs:subPropertyOf skos:definition . ex:a rdfs:subPropertyOf skos:definition ."
    assert _descriptions(body) == (*DESCRIPTIONS, URIRef(ONTO_NS + "a"), URIRef(ONTO_NS + "z"))
    # Two linked seeds are neither repeated nor moved.
    assert _descriptions("skos:definition rdfs:subPropertyOf rdfs:comment .") == DESCRIPTIONS


def test_transitive_definition_predicates_reach_every_consumer() -> None:
    chain = ONTO + "ex:def2 rdfs:subPropertyOf ex:def1 . ex:def1 rdfs:subPropertyOf skos:definition . "
    assert fired(chain + "ex:A a owl:Class ; rdfs:label 'A' ; ex:def2 ex:B .", "LEX013") == [A]
    assert fired(chain + "ex:A a owl:Class ; rdfs:label 'A' ; ex:def2 '' .", "LEX019") == [A]
    assert fired(chain + "ex:A a owl:Class ; rdfs:label 'A thing' ; ex:def2 'A thing' .", "LEX017") == [A]
    described = chain.replace(ONTO, "<https://example.test/onto> a owl:Ontology ; ex:def2 'Described.' . ")
    assert fired(described, "ONT006") == []
    classes = "ex:A a owl:Class ; ex:def2 'An A.' . ex:B a owl:Class ; ex:def2 'A B.' ."
    assert fired(chain + classes, "METRIC002", metric_min_sample=1, metric_max_undefined_ratio=0.0) == []


def test_tool005_does_not_suggest_a_transitively_known_predicate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    chain = "<https://v.test/termDefinition> rdfs:subPropertyOf ex:mid . ex:mid rdfs:subPropertyOf skos:definition .\n"
    terms = "".join(f"ex:C{i} a owl:Class ; <https://v.test/termDefinition> 'Def {i}.'@en .\n" for i in range(12))
    path = tmp_path / "o.ttl"
    path.write_text(PREFIXES + "<https://example.test/onto> a owl:Ontology .\n" + chain + terms, encoding="utf-8")
    out = tmp_path / "r.json"
    code = main([str(path), "--select", "LEX002", "--format", "json", "--output", str(out)])
    assert "TOOL005" not in capsys.readouterr().err
    assert json.loads(out.read_text(encoding="utf-8"))["findings"] == []
    assert code == 0


def test_a_definition_subproperty_declared_in_an_import_counts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = tmp_path / "annotations.ttl"
    module.write_text(
        PREFIXES + "<https://example.test/annotations> a owl:Ontology .\n"
        "ex:def2 rdfs:subPropertyOf ex:def1 . ex:def1 rdfs:subPropertyOf skos:definition .\n",
        encoding="utf-8",
    )
    root = tmp_path / "root.ttl"
    root.write_text(
        PREFIXES + f"<https://example.test/onto> a owl:Ontology ; owl:imports <{module.as_uri()}> .\n"
        "ex:A a owl:Class ; rdfs:label 'A'@en ; ex:def2 'An A is a thing.'@en .\n",
        encoding="utf-8",
    )
    out = tmp_path / "r.json"
    argv = [str(root), "--select", "LEX002", "--format", "json", "--output", str(out)]
    assert main([*argv, "--follow-imports"]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["findings"] == []
    main([*argv, "--fail-on", "never"])  # without the import the chain is unknown
    assert [f["focus"] for f in json.loads(out.read_text(encoding="utf-8"))["findings"]] == [A]
    capsys.readouterr()
