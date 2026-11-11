"""Metamorphic relations of baselines: accepting a run's findings accepts exactly them, wherever they are linted again.

README "Policy and baselines" and "Several files" (BASELINE-V2, TODO.md "Baseline identity"): a baseline records each
finding's version 1 hash and, per report path, its message-independent identity.  A finding is accepted by its hash
or, when its identity is not shared with another finding of the file, by its identity.  So a run is fully accepted by
its own baseline, by the baseline of an isomorphic copy, and a one-file baseline carries over to a multi-file run
(and the reverse), except for findings that share an identity, which are matched by hash only.
"""

from __future__ import annotations

import json
import random
from typing import Any

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st
from hypothesis_strategies import budget, roundtrip_triple_lists
from hypothesis_strategies import build_graph as build
from metamorphic_support import cli_json, serialisable, workdir
from rdflib import BNode, Graph

pytestmark = pytest.mark.slow


def relabelled(triples: list, seed: int) -> list:
    """An isomorphic copy of ``triples`` in which every blank node has a fresh random label."""
    rng = random.Random(seed)  # noqa: S311 -- not cryptographic, only a permutation.
    labels = sorted({n for t in triples for n in t if isinstance(n, BNode)}, key=str)
    mapping = {n: BNode(f"QBNB{name}") for n, name in zip(labels, rng.sample(range(10_000), len(labels)), strict=True)}
    return [tuple(mapping.get(n, n) for n in t) for t in triples]


def graph_of(triples: list) -> Graph:
    """The graph of the usable triples, which must not be empty."""
    graph = build(serialisable(triples))
    assume(len(graph))
    return graph


def baseline_of(path: str) -> dict[str, Any]:
    """The baseline file ``path`` as JSON."""
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def per_file(document: dict[str, Any], path: str) -> list[dict[str, Any]]:
    """The findings of the report path ``path``."""
    return [f for f in document["findings"] if f["path"] == path]


@budget(0.5)
@given(roundtrip_triple_lists())
def test_a_runs_own_baseline_accepts_all_of_its_findings(triples: list) -> None:
    """RELATION (baseline round trip): ``--write-baseline`` then ``--baseline`` on the same input leaves zero
    findings, no stale entry and exit 0, although the run without the baseline fails at ``--fail-on info``."""
    graph = graph_of(triples)

    with workdir() as root:
        (root / "g.ttl").write_text(graph.serialize(format="turtle"), encoding="utf-8")
        code, document = cli_json("g.ttl", "--fail-on", "info", "--write-baseline", "baseline.json")
        assume(document["findings"])  # Nothing to accept: the relation would be vacuous.
        assert code == 1
        accepted_code, accepted = cli_json(
            "g.ttl", "--fail-on", "info", "--baseline", "baseline.json", "--fail-on-stale-baseline"
        )

    assert accepted_code == 0
    assert accepted["findings"] == []
    assert accepted["summary"] == {}
    assert accepted["baseline"] == {"stale_fingerprints": []}


@budget(0.5)
@given(roundtrip_triple_lists(), st.integers(0, 2**31), st.randoms(use_true_random=False))
def test_the_baseline_of_a_run_accepts_a_relabelled_and_shuffled_copy_of_the_input(
    triples: list, seed: int, rnd: random.Random
) -> None:
    """RELATION (baseline round trip, isomorphic copy): a baseline written from a graph accepts every finding of an
    isomorphic copy whose blank nodes are relabelled and whose N-Triples lines are shuffled, under another name."""
    original = graph_of(triples)
    copy = build(relabelled(sorted(original, key=str), seed))
    lines = [line for line in copy.serialize(format="nt").split("\n") if line]
    rnd.shuffle(lines)

    with workdir() as root:
        (root / "g.ttl").write_text(original.serialize(format="turtle"), encoding="utf-8")
        (root / "copy.nt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        _, document = cli_json("g.ttl", "--write-baseline", "baseline.json")
        assume(document["findings"])
        code, accepted = cli_json("copy.nt", "--fail-on", "info", "--baseline", "baseline.json")

    assert accepted["findings"] == []
    assert accepted["baseline"] == {"stale_fingerprints": []}
    assert code == 0


@budget(0.25)
@given(roundtrip_triple_lists(), roundtrip_triple_lists())
def test_a_one_file_baseline_matches_its_file_in_a_multi_file_run_and_the_reverse(first: list, second: list) -> None:
    """RELATION (baseline identity across runs): the baseline of ``a.ttl`` alone accepts every finding of ``a.ttl``
    in a run of ``a.ttl`` and ``b.ttl`` whose identity is not shared by another finding of that file, leaves the
    shared ones (matched by hash only, and a multi-file hash includes the path) and every finding of ``b.ttl``
    untouched; the baseline of both files accepts the unshared findings of ``a.ttl`` linted alone, and every entry
    it holds for any other finding is stale."""
    graphs = [graph_of(first), graph_of(second)]

    with workdir() as root:
        for name, graph in zip(("a.ttl", "b.ttl"), graphs, strict=True):
            (root / name).write_text(graph.serialize(format="turtle"), encoding="utf-8")
        _, alone = cli_json("a.ttl", "--write-baseline", "alone.json")
        _, together = cli_json("a.ttl", "b.ttl", "--write-baseline", "together.json")
        assume(together["findings"])
        _, forward = cli_json("a.ttl", "b.ttl", "--baseline", "alone.json")
        _, backward = cli_json("a.ttl", "--baseline", "together.json")
        one, many = baseline_of("alone.json"), baseline_of("together.json")

    shared = len(one["fingerprints"]) - len(one["identities"].get("a.ttl", {}))  # Findings of a.ttl sharing an identity
    assert len(per_file(forward, "a.ttl")) == shared
    assert per_file(forward, "b.ttl") == per_file(together, "b.ttl")

    shared_in_many = len(per_file(together, "a.ttl")) - len(many["identities"].get("a.ttl", {}))
    assert shared_in_many == shared  # The identity of a finding does not depend on the other file.
    assert len(backward["findings"]) == shared
    unmatched = len(many["fingerprints"]) - len(many["identities"].get("a.ttl", {}))
    assert len(backward["baseline"]["stale_fingerprints"]) == unmatched
