"""Steps that once grew quadratically must stay linear, so a regression fails here, not for a user.

0.4.0 shipped two quadratic steps: the source locator counted newlines from the start of the text
for every term, and CLS017 recomputed a set difference over all classes for every class.  A
40,000-class file took 30 s.  Each test times only its step (no parsing, which is linear and would
hide the quadratic term) at two sizes and compares them, so it holds on slow runners: quadrupling
the input must cost well under the sixteen-fold time of a quadratic step.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import pytest
from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF

from ontolint import Linter
from ontolint.source_locations import build_source_index

pytestmark = pytest.mark.slow

SMALL = 5_000
LARGE = 4 * SMALL
MAX_RATIO = 8.0  # linear growth gives about 4; a quadratic step gives about 16


def _best_of_two(step: Callable[[], object]) -> float:
    best = float("inf")
    for _attempt in range(2):  # the faster run discards one-off scheduling noise
        started = time.perf_counter()
        step()
        best = min(best, time.perf_counter() - started)
    return best


def _classes(count: int) -> tuple[str, Graph]:
    text = "".join(f"<https://example.test/C{i}> a <{OWL.Class}> .\n" for i in range(count))
    graph = Graph()
    for i in range(count):
        graph.add((URIRef(f"https://example.test/C{i}"), RDF.type, OWL.Class))
    return text, graph


def _locate(count: int) -> float:
    text, graph = _classes(count)
    data = text.encode()
    return _best_of_two(lambda: build_source_index(data, "nt", "file:///a.nt", graph).locations)


def _cls017(count: int) -> float:
    _text, graph = _classes(count)
    return _best_of_two(lambda: Linter(graph).execute(["CLS017"]))


@pytest.mark.parametrize("step", [_locate, _cls017], ids=["source-locator", "CLS017"])
def test_the_step_grows_linearly_with_the_number_of_classes(step: Callable[[int], float]) -> None:
    small, large = step(SMALL), step(LARGE)
    assert large / small < MAX_RATIO, f"{SMALL} classes: {small:.3f} s, {LARGE} classes: {large:.3f} s"
