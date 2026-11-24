"""Opt-in large-ontology resource benchmarks (``ONTOLINT_BENCH=1``), run weekly by ``benchmarks.yml``.

Memory is asserted as a peak of Python allocations under ``tracemalloc``, roughly 5-10x the numbers measured on a
developer laptop (see docs/performance.md): allocations do not depend on the speed of the runner.  Time is asserted
only as a growth ratio between two sizes (``tests/scaling_support.py``), never as a number of seconds, which a hosted
runner cannot promise; the seconds of a run are in the job log (``--durations``) and in the retained profiles.
"""

from __future__ import annotations

import os
import tracemalloc

import pytest
import synthetic
from rdflib import Graph
from scaling_support import GROWTH, assert_grows_linearly

from ontolint import Linter

pytestmark = [
    pytest.mark.benchmark,
    pytest.mark.skipif(os.environ.get("ONTOLINT_BENCH") != "1", reason="set ONTOLINT_BENCH=1 to run benchmarks"),
]

MEGABYTE = 1024 * 1024


def _within(graph: Graph, megabytes: float) -> int:
    """Lint ``graph`` once under ``tracemalloc``; its peak must stay under ``megabytes``.  Returns the findings."""
    tracemalloc.start()
    try:
        findings = Linter(graph).run()
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < megabytes * MEGABYTE, f"{peak / MEGABYTE:.0f} MB exceeds {megabytes} MB"
    return len(findings)


def test_deep_chain_within_budget() -> None:
    assert _within(synthetic.deep_chain(500), 50) > 0


def test_very_deep_chain_has_no_recursion_error() -> None:
    """Chains far beyond the interpreter recursion limit lint without RecursionError."""
    assert _within(synthetic.deep_chain(3_000), 100) > 0


def test_hundred_thousand_deep_chain_within_budget() -> None:
    assert _within(synthetic.deep_chain(100_000), 500) > 0


def test_wide_tree_within_budget() -> None:
    _within(synthetic.wide_tree(20_000), 150)


def test_dense_multi_parent_dag_within_budget() -> None:
    _within(synthetic.dense_dag(4_000), 100)


def test_fifty_thousand_term_vocabulary_within_budget() -> None:
    _within(synthetic.many_labels(50_000), 500)


# The small size of each scenario; the large one is ``GROWTH`` times as big.  The sizes keep a run to some seconds.
SCALING = {
    "deep chain": (synthetic.deep_chain, 1_000),
    "wide tree": (synthetic.wide_tree, 2_500),
    "dense DAG": (synthetic.dense_dag, 500),
    "vocabulary": (synthetic.many_labels, 5_000),
}


@pytest.mark.parametrize("name", sorted(SCALING))
def test_linting_grows_linearly_with_the_ontology(name: str) -> None:
    """The whole linter at two sizes: the quadratic steps of 0.4.0 (CLS004, CLS007) were found by exactly this."""
    factory, size = SCALING[name]
    small, large = factory(size), factory(GROWTH * size)

    assert_grows_linearly(lambda: Linter(small).run(), lambda: Linter(large).run(), name, attempts=3)
