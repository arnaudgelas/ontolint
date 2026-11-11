"""Properties of the METRIC rules: they count what the per-term rules report, and thresholds are strict."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis_strategies import budget, rdf_graphs
from rdflib import Graph, URIRef
from rdflib.namespace import OWL

from ontolint.engine import build_context
from ontolint.models import Finding
from ontolint.policy import METRIC_RATIO_DEFAULTS, Policy
from ontolint.rules import classes, lexical, metrics, owl
from ontolint.rules.runtime import RuleContext

pytestmark = pytest.mark.slow

COUNT = re.compile(r"^(\d+) of (\d+) ")


def _run(graph: Graph, **thresholds: Any) -> RuleContext:
    ctx = build_context(graph, None, replace(Policy(), metric_min_sample=1, **thresholds))
    for module in (lexical, classes, owl, metrics):
        module.run(ctx)
    return ctx


def _count(findings: list[Finding], rule: str) -> int:
    (found,) = [f.message for f in findings if f.rule == rule] or [""]
    match = COUNT.match(found)
    return int(match.group(1)) if match else 0


@given(rdf_graphs)
@budget()
def test_metric001_counts_the_classes_lex001_reports(graph: Graph) -> None:
    ctx = _run(graph, metric_max_unlabelled_ratio=0.0)
    owned = {str(c) for c in ctx.classes if ctx.local(c)}
    lex = {f.focus for f in ctx.findings if f.rule == "LEX001" and f.focus in owned}
    assert _count(ctx.findings, "METRIC001") == len(lex)


@given(rdf_graphs)
@budget()
def test_metric005_counts_the_classes_cls001_reports(graph: Graph) -> None:
    ctx = _run(graph, metric_max_orphan_ratio=0.0)
    cls = {f.focus for f in ctx.findings if f.rule == "CLS001" and ctx.local(URIRef(f.focus))}
    assert _count(ctx.findings, "METRIC005") == len(cls)


@given(rdf_graphs)
@budget()
def test_metric008_counts_the_properties_owl005_and_owl006_both_report(graph: Graph) -> None:
    ctx = _run(graph, metric_max_unsigned_property_ratio=0.0)
    typed = ctx.context.subjects_by_type
    props = {str(p) for kind in (OWL.ObjectProperty, OWL.DatatypeProperty) for p in typed.get(kind, ()) if ctx.local(p)}
    no_domain = {f.focus for f in ctx.findings if f.rule == "OWL005"}
    no_range = {f.focus for f in ctx.findings if f.rule == "OWL006"}
    assert _count(ctx.findings, "METRIC008") == len(props & no_domain & no_range)


@given(rdf_graphs, st.sampled_from(sorted(METRIC_RATIO_DEFAULTS)))
@budget()
def test_a_threshold_equal_to_the_printed_value_never_fires(graph: Graph, key: str) -> None:
    """Strict comparison: forcing a ratio rule, then setting its limit to the value it printed, silences it."""
    forced = {"metric_min_language_coverage": 1.0}.get(key, 0.0)
    rule = {
        "metric_max_unlabelled_ratio": "METRIC001",
        "metric_max_undefined_ratio": "METRIC002",
        "metric_max_undocumented_property_ratio": "METRIC003",
        "metric_max_orphan_ratio": "METRIC005",
        "metric_max_unsigned_property_ratio": "METRIC008",
        "metric_min_language_coverage": "METRIC009",
        "metric_max_foreign_reference_ratio": "METRIC010",
        "metric_max_blank_node_ratio": "METRIC013",
    }[key]
    found = [f for f in _run(graph, **{key: forced}).findings if f.rule == rule]
    if not found:
        return
    match = re.match(r"^(\d+) of (\d+) ", found[0].message)
    assert match
    value = int(match.group(1)) / int(match.group(2))
    assert not [f for f in _run(graph, **{key: value}).findings if f.rule == rule]


@given(
    rdf_graphs,
    st.sampled_from(sorted(METRIC_RATIO_DEFAULTS)),
    st.floats(0, 1),
    st.floats(0, 1),
)
@budget()
def test_a_looser_threshold_never_adds_a_finding(graph: Graph, key: str, a: float, b: float) -> None:
    low, high = sorted((a, b))
    rules = {f.rule for f in _run(graph, **{key: low}).findings if f.rule.startswith("METRIC")}
    loose = {f.rule for f in _run(graph, **{key: high}).findings if f.rule.startswith("METRIC")}
    if key == "metric_min_language_coverage":  # a minimum: raising it fires more
        assert rules <= loose
    else:
        assert loose <= rules
