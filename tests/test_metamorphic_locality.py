"""Metamorphic relations: repeating a triple changes nothing, and an unrelated island changes nothing nearby.

Duplicates: RDF is a set of triples, so a file that states a triple twice (or ten times) is the same graph and
must give the same findings, through the loader and the CLI.

Locality: adding a well-formed, independent island (a fresh owned class with a label and a definition) must not
remove or alter a finding about the rest of the graph.  That holds exactly for per-term rules, whose verdict is a
function of the one term; whole-graph rules (ratios, counts, ontology header) may legitimately move.
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Iterable

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st
from hypothesis_strategies import BASE, budget, roundtrip_triple_lists, triple_lists
from hypothesis_strategies import build_graph as build
from metamorphic_support import cli_json, document_keys, keys, lint_all, serialisable, workdir
from rdflib import Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from ontolint.loader import load_graph
from ontolint.models import Finding, RuleScope
from ontolint.paths import resolve_inputs
from ontolint.policy import Policy
from ontolint.rules.registry import default_registry

pytestmark = pytest.mark.slow

# PER_TERM: every rule whose spec declares ``scope: term`` (docs/rules.md "Scope: term"; ``RuleSpec.scope``).  The
# scope is the rule's own statement that it reports on one declared term from what is asserted about that term, so
# a term that is not mentioned by an added island keeps its findings.  Rules of scope ontology, vocabulary, axiom,
# shapes or input compare terms, count them, or look at the header, and are only asserted weakly below.
PER_TERM = frozenset(spec.rule_id for spec in default_registry().all() if spec.scope is RuleScope.TERM)
# Whole-graph ratios and tallies (METRIC*): an island that is labelled and defined lowers the unlabelled and
# undocumented ratios and raises the sample size, so these findings can legitimately disappear or reword.
WHOLE_GRAPH = frozenset(spec.rule_id for spec in default_registry().all() if spec.family == "METRIC")

ISLAND = URIRef(BASE + "IslandQ")
ISLAND_TRIPLES = (
    (ISLAND, RDF.type, OWL.Class),
    (ISLAND, RDFS.label, Literal("Island zq", lang="en")),
    (ISLAND, SKOS.definition, Literal("An independent class that the rest of the graph never mentions.", lang="en")),
)
POLICY = Policy(base=BASE)  # A fixed base: the island must not change which namespace counts as the owned one.


def load(text: str, suffix: str) -> list[Finding]:
    """Findings of ``text`` read from a file with ``suffix`` through the real loader."""
    with workdir() as root:
        (root / f"graph{suffix}").write_text(text, encoding="utf-8")
        graph = load_graph(resolve_inputs([f"graph{suffix}"], root)[0], Policy(), root)
    return lint_all(graph)


def foci(findings: Iterable[Finding], rules: Iterable[str]) -> dict[str, set[str]]:
    """The set of focus terms per rule, for the given rules."""
    wanted = set(rules)
    out: dict[str, set[str]] = {}
    for f in findings:
        if f.rule in wanted:
            out.setdefault(f.rule, set()).add(f.focus)
    return out


@budget(1)
@given(roundtrip_triple_lists(), st.integers(2, 4), st.randoms(use_true_random=False))
def test_repeating_triples_changes_nothing_through_the_loader(triples: list, copies: int, rnd: random.Random) -> None:
    """RELATION (idempotence): an N-Triples file that states every triple ``copies`` times, in shuffled order,
    and a graph that has its own triples added again give the findings of the graph stated once."""
    graph = build(serialisable(triples))
    assume(len(graph))
    lines = [x for x in graph.serialize(format="nt").split("\n") if x]
    repeated = lines * copies
    rnd.shuffle(repeated)

    assert keys(load("\n".join(repeated) + "\n", ".nt")) == keys(load("\n".join(lines) + "\n", ".nt"))
    expected = keys(lint_all(graph))
    for triple in list(graph):
        graph.add(triple)
    assert keys(lint_all(graph)) == expected


@budget(0.3)
@given(roundtrip_triple_lists(), st.integers(2, 3))
def test_the_cli_reports_the_same_findings_when_every_triple_is_repeated(triples: list, copies: int) -> None:
    """RELATION (idempotence, CLI): ``--format json`` on a file with every triple repeated agrees with the file
    that states each once on exit code, summary and findings."""
    graph = build(serialisable(triples))
    assume(len(graph))
    lines = [x for x in graph.serialize(format="nt").split("\n") if x]

    with workdir() as root:
        (root / "once.nt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (root / "many.nt").write_text("\n".join(lines * copies) + "\n", encoding="utf-8")
        code, reference = cli_json("once.nt")
        many_code, document = cli_json("many.nt")

    assert many_code == code
    assert document_keys(document) == document_keys(reference)
    assert document["summary"] == reference["summary"]


@budget(1)
@given(triple_lists(20))
def test_an_independent_island_keeps_every_per_term_finding_of_the_original(triples: list) -> None:
    """RELATION (locality): adding a labelled, defined island class keeps every per-term finding of the original
    graph unchanged (same rule, severity, focus, message), and the only new per-term findings are about the island.
    For the other rules, except METRIC, every focus the original reported is still reported (the island may
    add foci, never take one away); nothing is asserted about METRIC findings, which are ratios."""
    original = build(serialisable(triples))
    assume(len(original))
    extended = build([*original, *ISLAND_TRIPLES])
    assume(len(extended) == len(original) + len(ISLAND_TRIPLES))  # The island must really be new.
    before, after = lint_all(original, POLICY), lint_all(extended, POLICY)

    old = Counter(keys(f for f in before if f.rule in PER_TERM))
    new = Counter(keys(f for f in after if f.rule in PER_TERM))
    assert not old - new, "an island removed or altered a per-term finding"
    assert all(focus == str(ISLAND) for _, _, focus, _ in new - old), "a per-term finding appeared elsewhere"

    others = {s.rule_id for s in default_registry().all()} - PER_TERM - WHOLE_GRAPH
    old_foci, new_foci = foci(before, others), foci(after, others)
    assert all(focuses <= new_foci.get(rule, set()) for rule, focuses in old_foci.items())
