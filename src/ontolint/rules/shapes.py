"""Quality rules for a user-supplied SHACL shapes graph: SHQ001-SHQ006."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from rdflib import Graph, Literal
from rdflib.namespace import OWL, RDF, RDFS, SH
from rdflib.term import Node

from ontolint.models import Requirement, RuleBackend, RuleScope, RuleSpec, Severity

if TYPE_CHECKING:
    from .runtime import RuleContext


CONSTRAINT_PREDICATES = (
    SH.minCount,
    SH.maxCount,
    SH.datatype,
    SH["class"],
    SH.pattern,
    SH["in"],
    SH.node,
    SH["not"],
    SH.sparql,
)


SPECS: tuple[RuleSpec, ...] = (
    RuleSpec(
        "SHQ001",
        "SHQ",
        "Property shape without sh:name",
        Severity.INFO,
        "Add sh:name to property shapes to support generated forms and documentation.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.SHAPES,
        "shapes",
        Requirement.SHAPES,
    ),
    RuleSpec(
        "SHQ002",
        "SHQ",
        "Property shape without sh:description",
        Severity.INFO,
        "Add sh:description to non-trivial property shapes.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.SHAPES,
        "shapes",
        Requirement.SHAPES,
    ),
    RuleSpec(
        "SHQ003",
        "SHQ",
        "Constraint-bearing shape without sh:message",
        Severity.INFO,
        "Add sh:message to constraint-bearing shapes for better diagnostics.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.SHAPES,
        "shapes",
        Requirement.SHAPES,
    ),
    RuleSpec(
        "SHQ004",
        "SHQ",
        "Node shape without label or comment",
        Severity.INFO,
        "Add label and comment to published node shapes.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.SHAPES,
        "shapes",
        Requirement.SHAPES,
    ),
    RuleSpec(
        "SHQ005",
        "SHQ",
        "Multiple shape annotations in one language",
        Severity.WARNING,
        "Use one annotation per language for each SHACL name/description/message.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.SHAPES,
        "shapes",
        Requirement.SHAPES,
    ),
    RuleSpec(
        "SHQ006",
        "SHQ",
        "Instantiated class without shape target",
        Severity.WARNING,
        "Add a shape targeting this class, or exempt it from data-quality validation.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.SHAPES,
        "shapes",
        Requirement.SHAPES,
    ),
)


def run(ctx: RuleContext) -> None:
    """Run all shape-quality rules; a no-op when no shapes graph was supplied."""
    sg = ctx.shapes
    if sg is None:
        return
    node_shapes = set(sg.subjects(RDF.type, SH.NodeShape))
    property_shapes = set(sg.subjects(RDF.type, SH.PropertyShape)) | set(sg.objects(None, SH.property))
    _documentation(ctx, sg, node_shapes, property_shapes)
    _messages_and_languages(ctx, sg, node_shapes | property_shapes)
    _class_targets(ctx, sg, node_shapes)


def _documentation(ctx: RuleContext, sg: Graph, node_shapes: set[Node], property_shapes: set[Node]) -> None:
    for shape in node_shapes:
        if (shape, RDFS.label, None) not in sg or (shape, RDFS.comment, None) not in sg:
            ctx.add("SHQ004", shape, "Node shape lacks rdfs:label or rdfs:comment.")
    for shape in property_shapes:
        if (shape, SH.name, None) not in sg:
            ctx.add("SHQ001", shape, "Property shape lacks sh:name.")
        if (shape, SH.description, None) not in sg:
            ctx.add("SHQ002", shape, "Property shape lacks sh:description.")


def _messages_and_languages(ctx: RuleContext, sg: Graph, shapes: set[Node]) -> None:
    for shape in shapes:
        has_constraint = any(p in CONSTRAINT_PREDICATES for p in sg.predicates(shape, None))
        if has_constraint and (shape, SH.message, None) not in sg:
            ctx.add("SHQ003", shape, "Constraint-bearing shape lacks sh:message.")
        for p in (SH.name, SH.description, SH.message):
            counts = Counter((o.language or "und").lower() for o in sg.objects(shape, p) if isinstance(o, Literal))
            if any(n > 1 for n in counts.values()):
                ctx.add("SHQ005", shape, f"Multiple {p} values in the same language.")


def _class_targets(ctx: RuleContext, sg: Graph, node_shapes: set[Node]) -> None:
    targeted = set(sg.objects(None, SH.targetClass))
    targeted |= {s for s in sg.subjects(RDF.type, RDFS.Class) if s in node_shapes}
    targeted |= {s for s in sg.subjects(RDF.type, OWL.Class) if s in node_shapes}
    for c in ctx.classes:
        if ctx.context.subjects_by_type.get(c) and c not in targeted:
            ctx.add(
                "SHQ006",
                c,
                "Class has directly typed instances, but no direct sh:targetClass or implicit class target.",
            )
