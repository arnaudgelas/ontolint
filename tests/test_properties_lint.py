"""Whole-linter properties: no crashes, determinism, and consistency of rule selection with the full run."""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis_strategies import (
    RULE_IDS,
    budget,
    canonical,
    linter_options,
    policies,
    rdf_graphs,
    shapes_graphs,
    triple_lists,
)
from hypothesis_strategies import build_graph as build
from rdflib import BNode, Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from ontolint import Linter
from ontolint.engine import build_context, execute
from ontolint.models import ExecutionStatus, Finding
from ontolint.policy import Policy
from ontolint.profiles import is_opt_in
from ontolint.rules.registry import default_registry
from ontolint.rules.specs import SEVERITY

pytestmark = pytest.mark.slow

SEVERITIES = {"error", "warning", "info"}
CONFIDENCES = {"certain", "heuristic"}
SPECS = default_registry().all()
OPT_IN_IDS = tuple(s.rule_id for s in SPECS if is_opt_in(s.family))
Key = tuple[str, str, str, str]


def keys(findings: Iterable[Finding], *, relabel: bool = False) -> list[Key]:
    """Order-independent comparison form: ``(rule, focus, message, severity)``, optionally blank-node blind."""
    fix = canonical if relabel else str
    return sorted((f.rule, fix(f.focus), fix(f.message), f.severity) for f in findings)


def lint_all(graph: Graph, policy: Policy | None = None, shapes: Graph | None = None) -> list[Finding]:
    """Run every rule (opt-in families included) and return the findings."""
    result = execute(build_context(graph, shapes, policy or Policy()), RULE_IDS)
    assert not result.with_status(ExecutionStatus.FAILED), result.with_status(ExecutionStatus.FAILED)
    return list(result.findings)


def relabelled(triples: list, seed: int) -> list:
    """Return ``triples`` with every blank node renamed to a fresh random label (an isomorphic copy)."""
    rng = random.Random(seed)  # noqa: S311 -- not cryptographic, only a permutation.
    labels = {n for t in triples for n in t if isinstance(n, BNode)}
    names = rng.sample(range(10_000), len(labels))
    mapping = {n: BNode(f"QBNB{name}") for n, name in zip(sorted(labels, key=str), names, strict=True)}
    return [tuple(mapping.get(n, n) for n in t) for t in triples]  # type: ignore[misc]


# --- 1. never crash ----------------------------------------------------------------------------------


@budget(2)
@given(rdf_graphs, policies())
def test_every_rule_module_survives_any_graph_and_policy(graph: Graph, policy: Policy) -> None:
    """INVARIANT: no rule module raises (no FAILED execution) for any graph and policy; findings are valid."""
    result = execute(build_context(graph, None, policy), RULE_IDS)

    assert not result.with_status(ExecutionStatus.FAILED), result.with_status(ExecutionStatus.FAILED)
    for finding in result.findings:
        assert finding.rule in SEVERITY
        assert finding.severity in SEVERITIES
        assert finding.confidence in CONFIDENCES
        assert finding.message.strip(), finding
        assert finding.focus, finding
        assert finding.suggestion.strip()
    assert len(result.executions) == len(RULE_IDS)


@budget(2)
@given(rdf_graphs, linter_options())
def test_linter_facade_run_and_execute_never_crash(graph: Graph, options: dict) -> None:
    """INVARIANT: ``Linter(...).run()`` returns valid findings for any graph and any Linter option set."""
    findings = Linter(graph, **options).run()

    assert all(f.rule in SEVERITY and f.severity in SEVERITIES and f.message and f.focus for f in findings)
    assert not any(is_opt_in(default_registry().get(f.rule).family) for f in findings)


@budget(0.5)
@given(rdf_graphs, shapes_graphs())
def test_shapes_graphs_only_ever_fail_as_shacl001(graph: Graph, shapes: tuple[Graph, bool]) -> None:
    """INVARIANT: with a shapes graph only SHACL001 may fail, and only when the shapes are deliberately malformed."""
    shapes_graph, malformed = shapes

    result = execute(build_context(graph, shapes_graph, Policy()), RULE_IDS)

    failed = {x.rule_id for x in result.with_status(ExecutionStatus.FAILED)}
    assert failed <= {"SHACL001"}
    # pySHACL fails on a data graph only when a violation message must describe a node with an IRI rdflib cannot
    # serialise or a malformed list; the adapter reports that as ShapesRejected, so valid shapes never fail otherwise.
    if not malformed:
        for execution in result.with_status(ExecutionStatus.FAILED):
            assert execution.detail.startswith("ShapesRejected:"), execution.detail


# --- 2. determinism ----------------------------------------------------------------------------------


@budget(3)
@given(triple_lists(20), st.randoms(use_true_random=False), policies())
def test_findings_do_not_depend_on_triple_insertion_order(triples: list, rnd: random.Random, policy: Policy) -> None:
    """INVARIANT: the same set of triples inserted in a different order yields identical findings (all rules)."""
    shuffled = list(triples)
    rnd.shuffle(shuffled)

    assert keys(lint_all(build(triples), policy)) == keys(lint_all(build(shuffled), policy))


@budget(3)
@given(triple_lists(20), st.integers(0, 2**31), policies())
def test_findings_do_not_depend_on_blank_node_labels(triples: list, seed: int, policy: Policy) -> None:
    """INVARIANT: an isomorphic copy with all blank nodes renamed yields the same findings up to blank-node labels."""
    copy = relabelled(triples, seed)
    original, other = build(triples), build(copy)
    assert len(original) == len(other)

    assert keys(lint_all(original, policy), relabel=True) == keys(lint_all(other, policy), relabel=True)


@budget(3)
@given(triple_lists(20), st.integers(0, 2**31), st.randoms(use_true_random=False))
def test_findings_are_stable_under_relabelling_and_shuffling_together(
    triples: list, seed: int, rnd: random.Random
) -> None:
    """INVARIANT: relabelling and shuffling at once (default policy, no base) still gives identical findings."""
    other = relabelled(triples, seed)
    rnd.shuffle(other)

    assert keys(lint_all(build(triples)), relabel=True) == keys(lint_all(build(other)), relabel=True)


def test_owl011_does_not_depend_on_triple_order_for_a_restriction_with_two_properties() -> None:
    """A malformed restriction with two owl:onProperty values must be reported identically for any insertion order."""
    cls, prop_p, prop_q, node = (
        URIRef("https://example.test/onto#A"),
        URIRef("https://example.test/onto#p"),
        URIRef("https://example.test/onto#q"),
        BNode("r"),
    )
    common = [(cls, RDF.type, OWL.Class), (node, OWL.allValuesFrom, cls), (cls, RDFS.subClassOf, node)]
    forward = keys(lint_all(build([*common, (node, OWL.onProperty, prop_p), (node, OWL.onProperty, prop_q)])))
    backward = keys(lint_all(build([*common, (node, OWL.onProperty, prop_q), (node, OWL.onProperty, prop_p)])))

    assert forward == backward


def test_findings_always_have_a_non_empty_focus() -> None:
    """INVARIANT: every finding names what it is about, even for the empty IRI (``URIRef('')``)."""
    findings = lint_all(build([(URIRef(""), RDF.type, OWL.Class)]))

    assert findings
    assert all(f.focus for f in findings)


@budget(2)
@given(rdf_graphs, linter_options())
def test_two_runs_in_one_process_agree_and_run_matches_execute(graph: Graph, options: dict) -> None:
    """INVARIANT: repeated runs agree exactly (order included), and ``run()`` equals a default ``execute()``."""
    first, second = Linter(graph, **options).run(), Linter(graph, **options).run()
    executed = Linter(graph, **options).execute().findings

    assert first == second
    assert first == list(executed)


@budget(1)
@given(rdf_graphs, st.sampled_from((None, "https://example.test/onto#", "https://other.example/ns#")))
def test_relabelled_copy_agrees_with_and_without_a_base(graph: Graph, base: str | None) -> None:
    """INVARIANT: a blank-node-relabelled copy of a graph gives the same findings with a base and without."""
    triples = list(graph)
    policy = Policy(base=base)
    one = keys(lint_all(build(triples), policy), relabel=True)
    two = keys(lint_all(build(relabelled(triples, 7)), policy), relabel=True)

    assert one == two


# --- 3. selection consistency with the full run ------------------------------------------------------


@budget(2)
@given(rdf_graphs, st.sets(st.sampled_from(RULE_IDS), min_size=1, max_size=30))
def test_selecting_rules_yields_exactly_the_full_runs_findings_for_them(graph: Graph, chosen: set[str]) -> None:
    """INVARIANT: findings of a rule subset == the full run's findings restricted to that subset (order included)."""
    full = lint_all(graph)

    subset = execute(build_context(graph, None, Policy()), sorted(chosen)).findings

    assert list(subset) == [f for f in full if f.rule in chosen]


@budget(2)
@given(rdf_graphs, st.sets(st.sampled_from(RULE_IDS), max_size=40))
def test_policy_ignored_rules_remove_exactly_their_findings(graph: Graph, ignored: set[str]) -> None:
    """INVARIANT: ``ignored_rules`` removes exactly those rules' findings and marks them skipped."""
    full = lint_all(graph)

    result = execute(build_context(graph, None, Policy(ignored_rules=frozenset(ignored))), RULE_IDS)

    assert list(result.findings) == [f for f in full if f.rule not in ignored]
    skipped = {x.rule_id for x in result.executions if x.detail == "ignored by policy"}
    assert skipped == ignored


@budget(2)
@given(rdf_graphs)
def test_opt_in_rules_only_appear_when_selected(graph: Graph) -> None:
    """INVARIANT: OBO rules are absent from default runs and present, unchanged, in an explicit selection."""
    default = Linter(graph).execute()
    default_run = Linter(graph).run()
    explicit = Linter(graph).execute(["OBO"])

    assert not {f.rule for f in default.findings} & set(OPT_IN_IDS)
    assert not {f.rule for f in default_run} & set(OPT_IN_IDS)
    assert {x.rule_id for x in explicit.executions} == set(OPT_IN_IDS)
    assert {f.rule for f in explicit.findings} <= set(OPT_IN_IDS)
    full = lint_all(graph)
    assert list(explicit.findings) == [f for f in full if f.rule in set(OPT_IN_IDS)]
    assert list(default.findings) == [f for f in full if f.rule not in set(OPT_IN_IDS)]


@budget(2)
@given(rdf_graphs, linter_options())
def test_findings_are_deduplicated_sorted_and_counted_once(graph: Graph, options: dict) -> None:
    """INVARIANT: no ``(rule, focus, message)`` repeats and findings are ordered by severity, rule, focus, message."""
    findings = Linter(graph, **options).run()

    identities = Counter((f.rule, f.focus, f.message) for f in findings)
    assert all(count == 1 for count in identities.values())
    order = ("error", "warning", "info")
    ranks = [(order.index(f.severity), f.rule, f.focus, f.message) for f in findings]
    assert ranks == sorted(ranks)


# --- determinism across processes --------------------------------------------------------------------

CHILD = """
import json, sys
from rdflib import BNode, Graph, Literal, URIRef
from ontolint.engine import build_context, execute
from ontolint.policy import Policy
from ontolint.rules.specs import SEVERITY

def node(spec):
    kind, value, lang, datatype = spec
    if kind == "u":
        return URIRef(value)
    if kind == "b":
        return BNode(value)
    return Literal(value, lang=lang, datatype=URIRef(datatype) if datatype else None)

out = []
for triples in json.load(sys.stdin):
    graph = Graph()
    for triple in triples:
        graph.add(tuple(node(n) for n in triple))
    result = execute(build_context(graph, None, Policy()), sorted(SEVERITY))
    out.append([[f.rule, f.focus, f.message, f.severity] for f in result.findings])
print(json.dumps(out))
"""


def _encode(node: object) -> list:
    if isinstance(node, BNode):
        return ["b", str(node), None, None]
    if isinstance(node, URIRef):
        return ["u", str(node), None, None]
    return ["l", str(node), getattr(node, "language", None), str(getattr(node, "datatype", None) or "") or None]


def _lint_in_child(graphs: list[list], hash_seed: int) -> list:
    payload = json.dumps([[[_encode(n) for n in t] for t in triples] for triples in graphs])
    done = subprocess.run(  # noqa: S603 -- fixed interpreter and script.
        [sys.executable, "-c", CHILD],
        input=payload,
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONHASHSEED": str(hash_seed)},
    )
    return json.loads(done.stdout)


@budget(0.05, floor=3)
@given(st.lists(triple_lists(20), min_size=6, max_size=6))
def test_findings_do_not_depend_on_the_string_hash_seed(graphs: list[list]) -> None:
    """INVARIANT: set/dict iteration order driven by PYTHONHASHSEED never changes the findings."""
    first, second = _lint_in_child(graphs, 1), _lint_in_child(graphs, 4242)

    def canon(run: list) -> list:
        return [sorted([r, canonical(f), canonical(m), s] for r, f, m, s in graph) for graph in run]

    assert canon(first) == canon(second)
