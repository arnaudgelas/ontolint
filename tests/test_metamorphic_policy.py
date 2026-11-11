"""Metamorphic relations of the policy knobs: each one changes only what it documents.

* ``--fail-on`` (README "Exit codes") sets the severity that fails the run, in the order ``info`` (any finding),
  ``warning``, ``error``, ``never``: raising it can only turn exit 1 into exit 0, and never alters the report.
* ``severity_overrides`` in a ``--config`` file change the severity of that rule's findings and nothing else.
* ``--profile`` (README "Selecting rules and profiles") bundles a rule selection, overrides and a default
  ``--fail-on``; the table there fixes how the profiles relate to the default run.

``ontolint --help`` shows no ``--min-severity``-style output filter, so there is no such relation to test.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from hypothesis import assume, example, given
from hypothesis import strategies as st
from hypothesis_strategies import budget, roundtrip_triple_lists
from hypothesis_strategies import build_graph as build
from metamorphic_support import Key, cli_json, document_keys, norm, serialisable, workdir
from rdflib import URIRef
from rdflib.namespace import OWL, RDF

pytestmark = pytest.mark.slow

ONTOLOGY = URIRef("https://example.test/onto")
SEVERITIES = ("error", "warning", "info")
# README "Exit codes": ``--fail-on`` names the lowest severity that fails the run; ``never`` never does.
FAIL_ON = ("info", "warning", "error", "never")  # From the strictest to the most lenient.
RANK = {"error": 0, "warning": 1, "info": 2}
# README profile table: ``minimal`` selects these families; ``strict`` drops SEC007 and makes ONT003 an error.
MINIMAL_FAMILIES = ("ONT", "IRI", "DATA", "SKOS", "SHACL", "SEM")
OPT_IN = {"obo": "OBO", "fair": "FAIR"}


def family(rule: str) -> str:
    """The family prefix of a rule id (``LEX001`` is ``LEX``)."""
    return rule.rstrip("0123456789")


def write(graph_triples: list, name: str = "g.ttl") -> None:
    """Write the graph as Turtle into the working directory."""
    graph = build(serialisable(graph_triples))
    assume(len(graph))
    with open(name, "w", encoding="utf-8") as handle:
        handle.write(graph.serialize(format="turtle"))


@budget(0.5)
@given(roundtrip_triple_lists())
def test_raising_fail_on_never_turns_exit_zero_into_exit_one(triples: list) -> None:
    """RELATION (``--fail-on`` monotonicity): with the same findings, the exit code never grows as the threshold
    goes info, warning, error, never; it is 1 exactly when a finding reaches the threshold; the report is unchanged."""
    with workdir():
        write(triples)
        runs = {level: cli_json("g.ttl", "--fail-on", level) for level in FAIL_ON}

    codes = [runs[level][0] for level in FAIL_ON]
    assert codes == sorted(codes, reverse=True), dict(zip(FAIL_ON, codes, strict=True))
    assert codes[-1] == 0
    reference = runs["never"][1]
    severities = {f["severity"] for f in reference["findings"]}
    for level in FAIL_ON[:-1]:
        assert runs[level][0] == int(any(RANK[s] <= RANK[level] for s in severities)), level
        assert runs[level][1] == reference


@budget(0.5)
@given(roundtrip_triple_lists(), st.data())
def test_a_severity_override_changes_only_the_severity_of_that_rules_findings(
    triples: list, data: st.DataObject
) -> None:
    """RELATION (severity override locality): with ``severity_overrides`` for some rules, every finding keeps its
    rule, focus, message and count; the overridden rules' findings take the new severity, all others keep theirs;
    the rule metadata reports the effective severity."""
    with workdir():
        write(triples)
        _, reference = cli_json("g.ttl")
        present = sorted({f["rule"] for f in reference["findings"]})
        assume(present)
        overrides = data.draw(st.dictionaries(st.sampled_from(present), st.sampled_from(SEVERITIES), min_size=1))
        with open("policy.json", "w", encoding="utf-8") as handle:
            json.dump({"severity_overrides": overrides}, handle)
        _, document = cli_json("g.ttl", "--config", "policy.json")

    def identity(doc: dict[str, Any]) -> list[tuple[str, str, str]]:
        return sorted((f["rule"], f["focus"], f["message"]) for f in doc["findings"])

    assert identity(document) == identity(reference)
    expected: list[Key] = sorted(
        (str(f["rule"]), str(overrides.get(f["rule"], f["severity"])), norm(f["focus"]), norm(f["message"]))
        for f in reference["findings"]
    )
    assert document_keys(document) == expected
    for rule in document["rules"]:
        assert rule["severity"] == overrides.get(rule["id"], rule["default_severity"]), rule["id"]


# An ontology header with an unfollowed import and no licence: SEC007 (dropped by ``strict``) and ONT003 (raised).
HEADER = [
    (ONTOLOGY, RDF.type, OWL.Ontology),
    (ONTOLOGY, OWL.imports, URIRef("https://other.example/ns")),
]


@budget(0.5)
@example(HEADER)
@given(roundtrip_triple_lists())
def test_profiles_relate_to_the_default_run_as_the_readme_table_says(triples: list) -> None:
    """RELATION (profile strictness order): ``recommended`` and ``ci`` give the default run's findings, ``minimal``
    exactly its findings of the ONT, IRI, DATA, SKOS, SHACL and SEM families, ``strict`` the default findings
    without SEC007 and with ONT003 an error, ``obo`` and ``fair`` the default findings plus only OBO or FAIR ones;
    and with each profile's own default ``--fail-on`` the exit code never falls along minimal, recommended, ci,
    strict."""
    with workdir():
        write(triples)
        default = cli_json("g.ttl")
        runs = {
            name: cli_json("g.ttl", "--profile", name)
            for name in ("minimal", "recommended", "ci", "strict", "obo", "fair")
        }

    base = document_keys(default[1])
    assert document_keys(runs["recommended"][1]) == base
    assert document_keys(runs["ci"][1]) == base
    assert document_keys(runs["minimal"][1]) == [k for k in base if family(k[0]) in MINIMAL_FAMILIES]
    strict = [(r, "error" if r == "ONT003" else s, f, m) for r, s, f, m in base if r != "SEC007"]
    assert document_keys(runs["strict"][1]) == sorted(strict)
    for name, opt_in_family in OPT_IN.items():
        keys = document_keys(runs[name][1])
        assert [k for k in keys if family(k[0]) != opt_in_family] == base
        assert all(family(k[0]) == opt_in_family for k in keys if k not in base)

    chain = [runs[name][0] for name in ("minimal", "recommended", "ci", "strict")]
    assert chain == sorted(chain), chain
    assert runs["recommended"][0] == default[0]
