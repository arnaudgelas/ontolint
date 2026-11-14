"""Properties of the measurement engine on random graphs: the METRIC rules print their measurements, and each
measurement keeps the invariants of its kind (``docs/measurements.md``)."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import replace

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis_strategies import BASE, class_iris, rdf_graphs
from hypothesis_strategies import budget as budget_
from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SH

from ontolint.engine import build_context
from ontolint.graph import hierarchy_depths
from ontolint.policy import Policy
from ontolint.redaction import redact_userinfo
from ontolint.rules import measurements, metrics, shapes
from ontolint.rules.measurements import CountRatio, TermRatio, TermValues, count, measure, owned_classes, ratio
from ontolint.rules.runtime import EMPTY_FOCUS, RuleContext
from ontolint.rules.support import directed_edges

pytestmark = pytest.mark.slow

# Every METRIC rule reports whenever its population is not empty, so each message shows its measurement.
FORCED = replace(
    Policy(),
    metric_min_sample=1,
    metric_max_imports=0,
    metric_max_unlabelled_ratio=0.0,
    metric_max_undefined_ratio=0.0,
    metric_max_undocumented_property_ratio=0.0,
    metric_max_mean_fanout=0.0,
    metric_max_orphan_ratio=0.0,
    metric_min_property_class_ratio=1e9,
    metric_max_property_class_ratio=1e9,
    metric_max_unsigned_property_ratio=0.0,
    metric_min_language_coverage=1.0,
    metric_max_foreign_reference_ratio=0.0,
    metric_min_definition_words=1e9,
    metric_max_blank_node_ratio=0.0,
)
NUMBERS = re.compile(
    r"^(\d+) (?:of (\d+) |properties for (\d+) |parent classes have (\S+) |distinct|defined classes"
    r" average (\S+) )"
)
COVERAGE = {"METRIC001": "class_label_coverage", "METRIC002": "class_definition_coverage"}
COVERAGE["METRIC003"] = "property_documentation_coverage"
SHARES = {
    "METRIC005": "orphan_classes",
    "METRIC008": "unsigned_properties",
    "METRIC009": "label_language_coverage",
    "METRIC010": "foreign_references",
    "METRIC013": "blank_subjects",
}


def _forced(graph: Graph) -> tuple[RuleContext, dict[str, tuple[str, ...]]]:
    ctx = build_context(graph, None, FORCED)
    metrics.run(ctx)
    printed = {}
    for finding in ctx.findings:
        match = NUMBERS.match(finding.message)
        assert match is not None, finding.message
        printed[finding.rule] = tuple(part for part in match.groups() if part is not None)
    return ctx, printed


def _mean(part: int, whole: int, limit: float) -> str:
    return metrics._vs(part / whole, limit)[0]


def _expected(ctx: RuleContext) -> dict[str, tuple[str, ...]]:  # noqa: C901 -- one branch per rule.
    """What each forced METRIC message prints, from the measurements alone."""
    expected: dict[str, tuple[str, ...]] = {}
    for rule, measurement_id in COVERAGE.items():
        covered, total = ratio(ctx, measurement_id)
        if total - covered:
            expected[rule] = (str(total - covered), str(total))
    for rule, measurement_id in SHARES.items():
        part, whole = ratio(ctx, measurement_id)
        if rule == "METRIC009":  # fires below full coverage, printing the tagged count
            if part < whole:
                expected[rule] = (str(part), str(whole))
        elif part:
            expected[rule] = (str(part), str(whole))
    edges, parents = ratio(ctx, "class_fanout")
    if parents:
        expected["METRIC004"] = (str(parents), _mean(edges, parents, 0.0))
    relations, classes = ratio(ctx, "relation_properties_per_class")
    if classes:
        expected["METRIC006"] = (str(relations), str(classes))
    if imports := count(ctx, "unresolved_imports"):
        expected["METRIC011"] = (str(imports),)
    words, defined = ratio(ctx, "definition_length")
    if defined:
        expected["METRIC012"] = (str(defined), _mean(words, defined, 1e9))
    return expected


@given(rdf_graphs)
@budget_()
def test_every_forced_metric_message_prints_its_measurement(graph: Graph) -> None:
    ctx, printed = _forced(graph)
    assert printed == _expected(ctx)


@given(rdf_graphs)
@budget_(0.5)
def test_a_measurement_depends_neither_on_thresholds_nor_on_the_rules_that_ran(graph: Graph) -> None:
    forced, _printed = _forced(graph)
    plain = build_context(graph, None, Policy())  # default thresholds, and no rule ran on it
    assert {spec.id: measure(plain, spec.id) for spec in measurements.SPECS} == {
        spec.id: measure(forced, spec.id) for spec in measurements.SPECS
    }


def _components(classes: Iterable[URIRef], edges: Iterable[tuple[URIRef, URIRef]]) -> int:
    """A naive oracle: repeatedly merge any two groups an edge joins."""
    groups = [{c} for c in classes]
    for child, parent in edges:
        joined = [g for g in groups if child in g or parent in g]
        if len(joined) == 2:  # noqa: PLR2004 -- the two ends of the edge.
            groups = [g for g in groups if g not in joined] + [joined[0] | joined[1]]
    return len(groups)


@given(rdf_graphs)
@budget_()
def test_hierarchy_measurements_keep_their_invariants(graph: Graph) -> None:
    ctx = build_context(graph, None, Policy())
    classes = owned_classes(ctx)
    depth = measure(ctx, "class_depth")
    assert isinstance(depth, TermValues)
    cyclic = measure(ctx, "cyclic_classes")
    assert isinstance(cyclic, TermRatio)
    # Every owned class is in one bucket, or on a cycle and in none.
    assert set(depth.values) == classes - cyclic.numerator
    assert cyclic.numerator <= cyclic.denominator == classes
    assert min(depth.values.values(), default=1) >= 1
    edges = directed_edges(ctx.g, RDFS.subClassOf, ctx.classes)
    assert max(depth.values.values(), default=0) == max(hierarchy_depths(ctx.classes, edges).values(), default=0)
    within = classes - {OWL.Thing}
    oracle = _components(within, ((c, p) for c, p in edges if c in within and p in within and c != p))
    assert count(ctx, "hierarchy_components") == oracle
    assert (count(ctx, "hierarchy_components") == 0) == (not within)


@given(rdf_graphs)
@budget_()
def test_ratios_keep_the_order_of_their_parts(graph: Graph) -> None:
    ctx = build_context(graph, Graph(), Policy())
    for spec in measurements.SPECS:
        found = measure(ctx, spec.id)
        if spec.id == "relation_properties_per_class":
            continue  # no order: properties over classes
        if isinstance(found, TermRatio | CountRatio):
            numerator, denominator = ratio(ctx, spec.id)
            assert 0 <= numerator <= denominator, spec.id
        if isinstance(found, TermRatio):
            assert found.numerator <= found.denominator, spec.id
    edges, parents = ratio(ctx, "class_fanout")
    assert edges >= parents
    foreign = measure(ctx, "foreign_references")
    assert isinstance(foreign, CountRatio)
    assert foreign.by_namespace is not None
    assert sum(n for _namespace, n in foreign.by_namespace) == foreign.numerator
    assert [namespace for namespace, _n in foreign.by_namespace] == sorted({ns for ns, _n in foreign.by_namespace})


@st.composite
def class_targets(draw: st.DrawFn) -> Graph:
    """A shapes graph of explicit and implicit class targets, some of them on owned classes."""
    shapes_graph = Graph()
    for index in range(draw(st.integers(0, 3))):
        shapes_graph.add((URIRef(f"{BASE}Shape{index}"), SH.targetClass, draw(class_iris)))
    for target in draw(st.lists(class_iris, max_size=2)):
        shapes_graph.add((target, RDF.type, draw(st.sampled_from([SH.NodeShape, SH.PropertyShape]))))
        shapes_graph.add((target, RDF.type, draw(st.sampled_from([RDFS.Class, OWL.Class, SH.NodeShape]))))
    return shapes_graph


@given(rdf_graphs, class_targets())
@budget_()
def test_shq006_reports_the_instantiated_owned_classes_no_target_reaches(graph: Graph, shapes_graph: Graph) -> None:
    ctx = build_context(graph, shapes_graph, Policy())
    found = measure(ctx, "shacl_class_target_coverage")
    assert isinstance(found, TermRatio)
    with ctx.naming_shapes():
        shapes.run(ctx)
    instantiated = {c for c in found.denominator if ctx.context.subjects_by_type.get(c)}
    left = {redact_userinfo(str(c)) or EMPTY_FOCUS for c in instantiated - found.numerator}
    assert {f.focus for f in ctx.findings if f.rule == "SHQ006"} == left
