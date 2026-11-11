"""Quality rules for a user-supplied SHACL shapes graph: SHQ001-SHQ006."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SH, XSD
from rdflib.term import Node

from ontolint.models import Requirement, RuleBackend, RuleScope, RuleSpec, Severity

if TYPE_CHECKING:
    from .runtime import RuleContext


# SHACL 2.1.1: a shape declares a constraint when it has values for all mandatory parameters of a constraint
# component.  These are the single mandatory parameters of the SHACL Core components (section 4) whose validation
# results name the shape itself as sh:sourceShape, and SHACL-SPARQL's sh:sparql (section 5); sh:property is not
# one, its results are the property shape's (4.7.2).
CONSTRAINT_PREDICATES = frozenset(
    (
        SH["class"],
        SH.datatype,
        SH.nodeKind,
        SH.minCount,
        SH.maxCount,
        SH.minExclusive,
        SH.minInclusive,
        SH.maxExclusive,
        SH.maxInclusive,
        SH.minLength,
        SH.maxLength,
        SH.pattern,
        SH.languageIn,
        SH.equals,
        SH.disjoint,
        SH.lessThan,
        SH.lessThanOrEquals,
        SH["not"],
        SH["and"],
        SH["or"],
        SH.xone,
        SH.node,
        SH.hasValue,
        SH["in"],
        SH.sparql,
    )
)
# Parameters whose constraint produces no validation result when the value is false (4.4.5, 4.8.1).
SWITCH_PREDICATES = (SH.uniqueLang, SH.closed)
# 4.7.3: sh:qualifiedValueShape and a qualified count are the mandatory parameters of a qualified constraint.
QUALIFIED_COUNTS = (SH.qualifiedMinCount, SH.qualifiedMaxCount)


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
    property_shapes = set(sg.subjects(RDF.type, SH.PropertyShape))
    property_shapes |= {o for o in sg.objects(None, SH.property) if isinstance(o, URIRef | BNode)}  # SHACL 2.1
    _documentation(ctx, sg, node_shapes, property_shapes)
    _messages_and_languages(ctx, sg, node_shapes | property_shapes)
    _class_targets(ctx, sg)


def _documentation(ctx: RuleContext, sg: Graph, node_shapes: set[Node], property_shapes: set[Node]) -> None:
    for shape in node_shapes:
        if (shape, RDFS.label, None) not in sg or (shape, RDFS.comment, None) not in sg:
            ctx.add("SHQ004", shape, "Node shape lacks rdfs:label or rdfs:comment.")
    for shape in property_shapes:
        if (shape, SH.name, None) not in sg:
            ctx.add("SHQ001", shape, "Property shape lacks sh:name.")
        if (shape, SH.description, None) not in sg:
            ctx.add("SHQ002", shape, "Property shape lacks sh:description.")


def _is_boolean(term: Node, value: bool) -> bool:
    return isinstance(term, Literal) and term.datatype == XSD.boolean and term.value is value


def _declares_constraint(sg: Graph, shape: Node) -> bool:
    """SHQ003: whether ``shape`` declares a constraint that can produce a validation result (SHACL 2.1.1, 3.4)."""
    if any(_is_boolean(o, True) for o in sg.objects(shape, SH.deactivated)):
        return False  # 2.1.6: all RDF terms conform to a deactivated shape
    if any(p in CONSTRAINT_PREDICATES for p in sg.predicates(shape, None)):
        return True
    if any(not _is_boolean(o, False) for p in SWITCH_PREDICATES for o in sg.objects(shape, p)):
        return True
    return (shape, SH.qualifiedValueShape, None) in sg and any((shape, p, None) in sg for p in QUALIFIED_COUNTS)


def _messages_and_languages(ctx: RuleContext, sg: Graph, shapes: set[Node]) -> None:
    for shape in shapes:
        if _declares_constraint(sg, shape) and (shape, SH.message, None) not in sg:
            ctx.add("SHQ003", shape, "Constraint-bearing shape lacks sh:message.")
        for p in (SH.name, SH.description, SH.message):
            counts = Counter((o.language or "und").lower() for o in sg.objects(shape, p) if isinstance(o, Literal))
            if any(n > 1 for n in counts.values()):
                ctx.add("SHQ005", shape, f"Multiple {p} values in the same language.", subject=(p,))


def _class_targets(ctx: RuleContext, sg: Graph) -> None:
    """SHQ006: a class with direct instances that no class target reaches, through its superclasses too.

    SHACL 2.1.3.2: a class target holds every SHACL instance of the class, and SHACL 1.1 makes an instance of a
    subclass one, through the ``rdfs:subClassOf`` triples of the data graph.  2.1.3.3: a shape typed
    ``sh:NodeShape`` or ``sh:PropertyShape`` that is also a class in the shapes graph targets its instances.
    """
    shapes = set(sg.subjects(RDF.type, SH.NodeShape)) | set(sg.subjects(RDF.type, SH.PropertyShape))
    covered = set(sg.objects(None, SH.targetClass))
    covered |= {s for c in (RDFS.Class, OWL.Class) for s in sg.subjects(RDF.type, c) if s in shapes}
    stack = list(covered)
    while stack:  # every subclass, in the data graph, of a targeted class is covered as well
        for sub in ctx.g.subjects(RDFS.subClassOf, stack.pop()):
            if sub not in covered:
                covered.add(sub)
                stack.append(sub)
    for c in ctx.classes:
        if ctx.context.subjects_by_type.get(c) and c not in covered:
            ctx.add(
                "SHQ006",
                c,
                "Class has directly typed instances, but no direct sh:targetClass or implicit class target.",
            )
