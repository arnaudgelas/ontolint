"""SHACL authoring checks over the supplied shapes graph: a documented subset of SHQ007-SHQ027.

Implemented: SHQ007, 008, 011, 013, 017-021 and 024-027.

Every check is a structural lint of the asserted shapes graph (no SHACL engine, no entailment, no
network).  Rules are skipped by the engine when no shapes graph is supplied; ``run`` is also a no-op
then.  Each check is deliberately conservative: it flags constructs that are invalid or unsatisfiable
according to the SHACL specification, or well-known authoring pitfalls, and stays silent when a value
cannot be interpreted with certainty.
"""

from __future__ import annotations

import math
import re
import warnings
from collections import defaultdict
from collections.abc import Callable
from decimal import Decimal
from typing import TYPE_CHECKING

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SH, XSD
from rdflib.term import Node

from ontolint.models import Requirement, RuleBackend, RuleScope, RuleSpec, Severity

from .support import list_items

if TYPE_CHECKING:
    from .runtime import RuleContext

type Check = Callable[["RuleContext", Graph, Node], None]

LOGICAL_PARAMETERS = (SH["and"], SH["or"], SH.xone)
TARGET_PREDICATES = (SH.targetClass, SH.targetNode, SH.targetSubjectsOf, SH.targetObjectsOf)
REFERENCE_PREDICATES = (
    SH.node,
    SH["not"],
    SH["and"],
    SH["or"],
    SH.xone,
    SH.property,
    SH.qualifiedValueShape,
)
SHAPE_PREDICATES = (
    SH.path,
    SH.property,
    SH.node,
    SH.minCount,
    SH.maxCount,
    SH.datatype,
    SH["class"],
    SH.nodeKind,
    SH.pattern,
    SH["in"],
    SH.closed,
    SH.deactivated,
    SH.severity,
    SH.minLength,
    SH.maxLength,
    SH.minInclusive,
    SH.maxInclusive,
    SH.minExclusive,
    SH.maxExclusive,
    SH.uniqueLang,
    SH.languageIn,
    SH["and"],
    SH["or"],
    SH.xone,
    SH["not"],
    SH.qualifiedValueShape,
    *TARGET_PREDICATES,
)
REGEX_FLAGS = {"i": re.IGNORECASE, "s": re.DOTALL, "m": re.MULTILINE, "x": re.VERBOSE}
# XPath-only regex escapes that Python cannot compile although they are valid SHACL patterns.
MIN_LOGICAL_MEMBERS = 2
XPATH_ONLY_ESCAPES = re.compile(r"\\[pPiIcC]")


def _spec(rule_id: str, title: str, severity: Severity, suggestion: str, category: str = "deterministic") -> RuleSpec:
    return RuleSpec(
        rule_id,
        "SHQ",
        title,
        severity,
        suggestion,
        category,
        RuleBackend.RDFLIB,
        RuleScope.SHAPES,
        "shacl_authoring",
        Requirement.SHAPES,
    )


SPECS: tuple[RuleSpec, ...] = (
    _spec(
        "SHQ007", "Shape with sh:minCount greater than sh:maxCount", Severity.ERROR, "Make sh:minCount <= sh:maxCount."
    ),
    _spec(
        "SHQ008", "Cardinality value is not a non-negative integer", Severity.ERROR, "Use a non-negative xsd:integer."
    ),
    _spec(
        "SHQ011",
        "Invalid sh:pattern regular expression",
        Severity.ERROR,
        "Fix the sh:pattern expression (and sh:flags) so it compiles.",
        "heuristic",
    ),
    _spec(
        "SHQ013",
        "Shape combining sh:datatype and sh:class",
        Severity.WARNING,
        "Remove one: a literal cannot be an instance of a class, so the shape cannot be satisfied.",
    ),
    _spec(
        "SHQ017",
        "Shape with sh:minLength greater than sh:maxLength",
        Severity.ERROR,
        "Make sh:minLength <= sh:maxLength.",
    ),
    _spec(
        "SHQ018",
        "Shape with an empty numeric range",
        Severity.ERROR,
        "Make the lower bound smaller than the upper bound (min/max Inclusive/Exclusive).",
    ),
    _spec(
        "SHQ019",
        "sh:node or sh:property refers to an undefined shape",
        Severity.WARNING,
        "Define the referenced shape in the shapes graph or correct the IRI.",
        "heuristic",
    ),
    _spec(
        "SHQ020",
        "Deactivated shape left in the shapes graph",
        Severity.INFO,
        "Remove the shape or re-enable it; sh:deactivated true silently disables validation.",
        "heuristic",
    ),
    _spec(
        "SHQ021",
        "Node shape that is neither targeted nor referenced",
        Severity.WARNING,
        "Add a target (for example sh:targetClass) or reference the shape from another shape.",
        "heuristic",
    ),
    _spec(
        "SHQ024",
        "Closed shape that does not ignore rdf:type",
        Severity.INFO,
        "Add rdf:type to sh:ignoredProperties, otherwise every typed focus node violates the closed shape.",
        "heuristic",
    ),
    _spec(
        "SHQ025",
        "sh:and, sh:or or sh:xone with fewer than two members",
        Severity.INFO,
        "Inline the single member or add the missing alternatives; an empty sh:or can never hold.",
        "heuristic",
    ),
    _spec(
        "SHQ026",
        "Node shape with several property shapes for the same path",
        Severity.INFO,
        "Merge the property shapes that constrain the same sh:path.",
        "heuristic",
    ),
    _spec(
        "SHQ027",
        "Shape targets a local class the ontology does not declare",
        Severity.WARNING,
        "Fix the sh:targetClass IRI or declare the class in the ontology.",
        "heuristic",
    ),
)


# --- helpers ---------------------------------------------------------------------------------


def _natural(term: Node | None) -> int | None:
    """Return ``term`` as a non-negative integer, or ``None`` when it is not one."""
    if isinstance(term, Literal) and isinstance(term.value, int) and not isinstance(term.value, bool):
        return term.value if term.value >= 0 else None
    return None


def _number(term: Node) -> Decimal | float | int | None:
    """Return the numeric value of a literal (booleans excluded), or ``None``."""
    if isinstance(term, Literal) and isinstance(term.value, int | float | Decimal) and not isinstance(term.value, bool):
        return term.value
    return None


def _is_nan(number: Decimal | float) -> bool:
    return number.is_nan() if isinstance(number, Decimal) else math.isnan(number)


def _single(sg: Graph, shape: Node, predicate: URIRef) -> Node | None:
    values = list(sg.objects(shape, predicate))
    return values[0] if len(values) == 1 else None


def _shapes(sg: Graph) -> list[Node]:
    found: set[Node] = set(sg.subjects(RDF.type, SH.NodeShape)) | set(sg.subjects(RDF.type, SH.PropertyShape))
    found |= {o for o in sg.objects(None, SH.property) if isinstance(o, URIRef | BNode)}
    for predicate in SHAPE_PREDICATES:
        found |= set(sg.subjects(predicate, None))
    return sorted(found, key=str)


def _is_property_shape(sg: Graph, shape: Node) -> bool:
    return (shape, RDF.type, SH.PropertyShape) in sg or (None, SH.property, shape) in sg or (shape, SH.path, None) in sg


def _is_node_shape(sg: Graph, shape: Node) -> bool:
    return (shape, RDF.type, SH.NodeShape) in sg and not _is_property_shape(sg, shape)


def _is_true(term: Node) -> bool:
    return isinstance(term, Literal) and term.datatype == XSD.boolean and term.value is True


# --- per-shape checks ------------------------------------------------------------------------


def _ordered_pair(
    ctx: RuleContext, sg: Graph, shape: Node, bounds: tuple[URIRef, URIRef], report: tuple[str, str]
) -> None:
    lo, hi = _single(sg, shape, bounds[0]), _single(sg, shape, bounds[1])
    lo_n, hi_n = _natural(lo), _natural(hi)
    if lo_n is not None and hi_n is not None and lo_n > hi_n:
        ctx.add(report[0], shape, report[1].format(lo=lo_n, hi=hi_n), confidence="deterministic")


def _cardinality_order(ctx: RuleContext, sg: Graph, shape: Node) -> None:
    message = "sh:minCount {lo} exceeds sh:maxCount {hi}."
    _ordered_pair(ctx, sg, shape, (SH.minCount, SH.maxCount), ("SHQ007", message))


def _length_order(ctx: RuleContext, sg: Graph, shape: Node) -> None:
    message = "sh:minLength {lo} exceeds sh:maxLength {hi}."
    _ordered_pair(ctx, sg, shape, (SH.minLength, SH.maxLength), ("SHQ017", message))


def _cardinality_values(ctx: RuleContext, sg: Graph, shape: Node) -> None:
    for predicate in (SH.minCount, SH.maxCount):
        for value in sg.objects(shape, predicate):
            if _natural(value) is None:
                ctx.add(
                    "SHQ008",
                    shape,
                    f"{predicate.n3(sg.namespace_manager)} value {value!s} is not a non-negative integer.",
                )


def _regex(ctx: RuleContext, sg: Graph, shape: Node) -> None:
    flags = 0
    for flag in sg.objects(shape, SH.flags):
        flags |= sum(REGEX_FLAGS.get(ch, 0) for ch in str(flag))
    for pattern in sg.objects(shape, SH.pattern):
        if not isinstance(pattern, Literal):
            continue
        text = str(pattern)
        if XPATH_ONLY_ESCAPES.search(text):
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                re.compile(text, flags)
        except (re.error, RecursionError, OverflowError) as exc:
            ctx.add("SHQ011", shape, f"sh:pattern does not compile: {exc}", confidence="heuristic")


def _logical_members(ctx: RuleContext, sg: Graph, shape: Node) -> None:
    for predicate in LOGICAL_PARAMETERS:
        for head in sg.objects(shape, predicate):
            items = None if isinstance(head, Literal) else list_items(sg, head)
            if items is not None and len(items) < MIN_LOGICAL_MEMBERS:
                ctx.add("SHQ025", shape, f"{predicate.n3(sg.namespace_manager)} has {len(items)} member(s).")


def _datatype_and_class(ctx: RuleContext, sg: Graph, shape: Node) -> None:
    if (shape, SH.datatype, None) in sg and (shape, SH["class"], None) in sg:
        ctx.add("SHQ013", shape, "Shape has both sh:datatype and sh:class; no value can satisfy both.")


def _range_bounds(
    sg: Graph, shape: Node, inclusive: URIRef, exclusive: URIRef
) -> list[tuple[Decimal | float | int, bool]]:
    out: list[tuple[Decimal | float | int, bool]] = []
    for predicate, strict in ((inclusive, False), (exclusive, True)):
        for value in sg.objects(shape, predicate):
            number = _number(value)
            if number is not None and not _is_nan(number):
                out.append((number, strict))
    return out


def _numeric_range(ctx: RuleContext, sg: Graph, shape: Node) -> None:
    lows = _range_bounds(sg, shape, SH.minInclusive, SH.minExclusive)
    highs = _range_bounds(sg, shape, SH.maxInclusive, SH.maxExclusive)
    for low, low_strict in lows:
        for high, high_strict in highs:
            if low > high or (low == high and (low_strict or high_strict)):
                ctx.add("SHQ018", shape, f"Numeric bounds {low} and {high} admit no value.")


def _deactivated(ctx: RuleContext, sg: Graph, shape: Node) -> None:
    if any(_is_true(v) for v in sg.objects(shape, SH.deactivated)):
        ctx.add("SHQ020", shape, "Shape is deactivated with sh:deactivated true.")


def _closed_without_type(ctx: RuleContext, sg: Graph, shape: Node) -> None:
    if not any(_is_true(v) for v in sg.objects(shape, SH.closed)):
        return
    ignored = [list_items(sg, head) for head in sg.objects(shape, SH.ignoredProperties)]
    if not any(items is not None and RDF.type in items for items in ignored):
        ctx.add("SHQ024", shape, "Closed shape does not list rdf:type in sh:ignoredProperties.")


def _duplicate_paths(ctx: RuleContext, sg: Graph, shape: Node) -> None:
    by_path: dict[Node, list[Node]] = defaultdict(list)
    for prop in sg.objects(shape, SH.property):
        paths = list(sg.objects(prop, SH.path))
        if len(paths) == 1 and isinstance(paths[0], URIRef) and (prop, SH.qualifiedValueShape, None) not in sg:
            by_path[paths[0]].append(prop)
    for path, props in sorted(by_path.items(), key=lambda kv: str(kv[0])):
        if len(props) > 1:
            ctx.add("SHQ026", shape, f"{len(props)} property shapes constrain the same path {path!s}.")


def _undefined_references(ctx: RuleContext, sg: Graph, shape: Node) -> None:
    for predicate in (SH.node, SH.property):
        for target in sg.objects(shape, predicate):
            if isinstance(target, URIRef) and (target, None, None) not in sg:
                ctx.add("SHQ019", shape, f"{predicate.n3(sg.namespace_manager)} refers to undefined shape {target!s}.")


def _unused_node_shape(ctx: RuleContext, sg: Graph, shape: Node, referenced: set[Node]) -> None:
    if not _is_node_shape(sg, shape) or shape in referenced:
        return
    targeted = any((shape, p, None) in sg for p in TARGET_PREDICATES)
    implicit = any((shape, RDF.type, c) in sg for c in (RDFS.Class, OWL.Class))
    if not targeted and not implicit and not any(_is_true(v) for v in sg.objects(shape, SH.deactivated)):
        ctx.add("SHQ021", shape, "Node shape has no target and no other shape refers to it.")


def _referenced_shapes(sg: Graph) -> set[Node]:
    referenced: set[Node] = set()
    for predicate in REFERENCE_PREDICATES:
        for value in sg.objects(None, predicate):
            items = list_items(sg, value) if predicate in LOGICAL_PARAMETERS else None
            referenced |= set(items) if items is not None else {value}
    return referenced


def _undeclared_targets(ctx: RuleContext, sg: Graph, shape: Node) -> None:
    if not ctx.policy.base:
        return
    for target in sg.objects(shape, SH.targetClass):
        if ctx.local(target) and target not in ctx.classes and target not in ctx.terms:
            ctx.add("SHQ027", shape, f"sh:targetClass {target!s} is not declared as a class in the ontology.")


SHAPE_CHECKS: tuple[Check, ...] = (
    _cardinality_order,
    _length_order,
    _cardinality_values,
    _regex,
    _logical_members,
    _datatype_and_class,
    _numeric_range,
    _deactivated,
    _closed_without_type,
    _duplicate_paths,
    _undefined_references,
    _undeclared_targets,
)


def run(ctx: RuleContext) -> None:
    """Run the SHACL authoring checks; a no-op when no shapes graph was supplied."""
    sg = ctx.shapes
    if sg is None:
        return
    referenced = _referenced_shapes(sg)
    for shape in _shapes(sg):
        for check in SHAPE_CHECKS:
            check(ctx, sg, shape)
        _unused_node_shape(ctx, sg, shape, referenced)
