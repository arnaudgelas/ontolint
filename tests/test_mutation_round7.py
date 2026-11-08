"""Round 7 mutation survivors: CLI bounds, policy merge, FAIR and policy-rule helpers, worker wire format."""

# ruff: noqa: PLR2004

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, XSD

from ontolint import Linter
from ontolint import cli as cli_module
from ontolint.loader import _decode_graph, _decode_term, _encode_term
from ontolint.policy import MAX_PARSE_SECONDS, Policy
from ontolint.rules import fair_offline, policy_rules

FIXTURES = Path(__file__).parent / "fixtures"
EX = "http://example.org/"


def test_max_parse_seconds_option_accepts_exactly_the_maximum() -> None:
    assert cli_module._positive_seconds(f"{MAX_PARSE_SECONDS:g}") == MAX_PARSE_SECONDS


def test_unsupported_policy_version_exits_with_status_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = tmp_path / "policy.json"
    config.write_text(json.dumps({"policy_version": 2}))
    assert cli_module.main(["--config", str(config), str(FIXTURES / "clean.ttl")]) == 2
    assert "GOV020: policy file rejected" in capsys.readouterr().err


def test_identifier_problems_of_a_blank_node_is_an_empty_list() -> None:
    assert fair_offline._identifier_problems(BNode()) == []


def test_linter_keeps_the_policy_languages_when_none_are_given() -> None:
    policy = Policy(languages=("fr",), base=EX)
    linter = Linter(Graph(), policy=policy)
    assert linter.rule_context.policy.languages == ("fr",)
    assert linter.rule_context.policy.base == EX


def _context(body: str) -> object:
    g = Graph()
    g.parse(data="@prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix ex: <http://example.org/> .\n" + body)
    return Linter(g, base=EX).rule_context


def test_has_value_is_false_without_values() -> None:
    ctx = _context("ex:t a owl:Class .")
    assert policy_rules._has_value(ctx, URIRef(EX + "t"), URIRef(EX + "p")) is False  # type: ignore[arg-type]


def test_individuals_keep_only_owned_named_iris() -> None:
    ctx = _context("ex:mine a owl:NamedIndividual . <http://other.test/theirs> a owl:NamedIndividual .")
    assert sorted(policy_rules._individuals(ctx)) == [URIRef(EX + "mine")]  # type: ignore[arg-type]


def test_worker_wire_format_keeps_the_lexical_form() -> None:
    literal = Literal("01", datatype=XSD.integer, normalize=False)
    decoded = _decode_term(_encode_term(literal))
    assert isinstance(decoded, Literal)
    assert str(decoded) == "01"
    assert decoded.datatype == XSD.integer


def test_worker_wire_format_rebinds_default_prefixes() -> None:
    payload = {"namespaces": [["owl", "http://other.test/owl#"]], "triples": []}
    graph = _decode_graph(payload)
    assert dict(graph.namespaces())["owl"] == URIRef("http://other.test/owl#")
    assert (OWL.Class, RDF.type, None) not in graph
