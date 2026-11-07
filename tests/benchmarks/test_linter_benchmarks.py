"""Opt-in large-ontology resource-budget benchmarks (``ONTOLINT_BENCH=1``).

Each scenario runs the full public ``Linter`` once for wall time and once under
``tracemalloc`` for peak Python allocations. Budgets are roughly 5-10x the
numbers measured on a developer laptop (see docs/performance.md) so they catch
complexity regressions without flaking on slow CI runners.
"""

from __future__ import annotations

import os
import time
import tracemalloc
from dataclasses import dataclass

import pytest
import synthetic
from rdflib import Graph

from ontolint import Linter

pytestmark = [
    pytest.mark.benchmark,
    pytest.mark.skipif(os.environ.get("ONTOLINT_BENCH") != "1", reason="set ONTOLINT_BENCH=1 to run benchmarks"),
]

MEGABYTE = 1024 * 1024


@dataclass(frozen=True)
class Budget:
    seconds: float
    megabytes: float


def _run_within(graph: Graph, budget: Budget) -> int:
    start = time.perf_counter()
    findings = Linter(graph).run()
    elapsed = time.perf_counter() - start
    assert elapsed < budget.seconds, f"{elapsed:.1f}s exceeds {budget.seconds}s"

    tracemalloc.start()
    try:
        Linter(graph).run()
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < budget.megabytes * MEGABYTE, f"{peak / MEGABYTE:.0f} MB exceeds {budget.megabytes} MB"
    return len(findings)


def test_deep_chain_within_budget() -> None:
    assert _run_within(synthetic.deep_chain(500), Budget(seconds=2, megabytes=50)) > 0


def test_very_deep_chain_has_no_recursion_error() -> None:
    """Chains far beyond the interpreter recursion limit lint without RecursionError."""
    assert _run_within(synthetic.deep_chain(3_000), Budget(seconds=5, megabytes=100)) > 0


def test_hundred_thousand_deep_chain_within_budget() -> None:
    assert _run_within(synthetic.deep_chain(100_000), Budget(seconds=40, megabytes=500)) > 0


def test_wide_tree_within_budget() -> None:
    _run_within(synthetic.wide_tree(20_000), Budget(seconds=10, megabytes=150))


def test_dense_multi_parent_dag_within_budget() -> None:
    _run_within(synthetic.dense_dag(4_000), Budget(seconds=5, megabytes=100))


def test_fifty_thousand_term_vocabulary_within_budget() -> None:
    _run_within(synthetic.many_labels(50_000), Budget(seconds=40, megabytes=500))
