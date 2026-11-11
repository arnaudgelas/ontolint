"""Quality rules for a user-supplied SHACL shapes graph: SHQ001-SHQ006.

The rules read the asserted shapes graph (``--shapes``) and, for SHQ006 only, the data graph (the
linted ontology, the whole closure under ``--follow-imports``).  No SHACL engine runs, nothing is
entailed, ``rdfs:subClassOf`` in the shapes graph is not followed (so a shape typed by a subclass of
``sh:NodeShape`` is not one) and ``owl:imports`` of the shapes graph are not loaded.  The rules are
skipped when no shapes graph is supplied.  References are to the SHACL Recommendation (2017-07-20).
In this module a *node shape* is a node typed ``sh:NodeShape``; a *property shape* is a node typed
``sh:PropertyShape`` or an IRI or blank node that is a value of ``sh:property``.  That is narrower than
SHACL 2.3 (any subject of ``sh:path``) on purpose: SHQ001 and SHQ002 judge the property shapes a form
shows, not a property shape used as a condition inside ``sh:or``.  Every finding is ``heuristic``: the
documentation rules are conventions, and SHQ005 and SHQ006 read "should" statements.  Specifications:

* **SHQ001.** Every property shape without an ``sh:name`` triple (any object: an IRI or an untagged
  literal counts).  Excluded: a literal value of ``sh:property`` (SHACL 2.1: a shape is an IRI or a
  blank node), and a property shape reached only through ``sh:or``, ``sh:and``, ``sh:xone``,
  ``sh:not``, ``sh:node`` or ``sh:qualifiedValueShape`` or only targeted directly.  Info: ``sh:name``
  is non-validating (2.3.2.1) and only helps forms and documentation.
* **SHQ002.** The same for ``sh:description``.  Info, for the same reason.
* **SHQ003.** Every node or property shape that declares a constraint able to produce a validation
  result and has no ``sh:message`` triple: 2.1.5 copies a shape's messages into its validation results
  and has no other use for them.  A shape declares a constraint when it has values for all mandatory
  parameters of a constraint component (2.1.1).  The components are those of SHACL Core section 4 whose
  validation results name the shape itself as ``sh:sourceShape``, and SHACL-SPARQL's (section 5).  Each
  of these parameters counts with any value: ``sh:class``, ``sh:datatype``, ``sh:nodeKind``,
  ``sh:minCount``, ``sh:maxCount``, ``sh:minExclusive``, ``sh:minInclusive``, ``sh:maxExclusive``,
  ``sh:maxInclusive``, ``sh:minLength``, ``sh:maxLength``, ``sh:pattern``, ``sh:languageIn``,
  ``sh:equals``, ``sh:disjoint``, ``sh:lessThan``, ``sh:lessThanOrEquals``, ``sh:not``, ``sh:and``,
  ``sh:or``, ``sh:xone``, ``sh:node``, ``sh:hasValue``, ``sh:in`` and ``sh:sparql``.
  ``sh:qualifiedValueShape`` counts only with an ``sh:qualifiedMinCount`` or ``sh:qualifiedMaxCount``
  (4.7.3 makes both of a pair mandatory).  ``sh:closed`` and ``sh:uniqueLang`` count unless they are
  false (an ``xsd:boolean`` literal: ``false`` or ``"0"^^xsd:boolean``), as 4.8.1 and 4.4.5 produce a
  validation result only "if $closed is true" and "if $uniqueLang is true"; any other value is true,
  the ``sh:ByTypes`` of the SHACL 1.2 draft, or ill-formed (3.4.2: the results are undefined).
  Excluded: a shape with ``sh:deactivated`` true (``true`` or ``"1"^^xsd:boolean``; 2.1.6: all RDF
  terms conform to it, and 3.4: its validation results are empty); ``sh:property`` (its results are
  the property shape's, 4.7.2); a parameter without its mandatory partner (``sh:qualifiedValueShape``
  alone, ``sh:qualifiedMinCount`` or ``sh:qualifiedMaxCount`` alone); the optional parameters alone
  (``sh:flags``, ``sh:ignoredProperties``, ``sh:qualifiedValueShapesDisjoint``); ``sh:closed false``
  and ``sh:uniqueLang false``; targets, ``sh:severity`` and the non-validating properties; a message
  on another shape.  Known gap: other values that make a constraint vacuous (``sh:minCount 0``, an
  empty ``sh:and`` list) still count, as the values are not evaluated.  Info: without ``sh:message`` a
  processor still reports the violation with its own text (2.1.5).
* **SHQ004.** Every node shape without an ``rdfs:label`` triple or without an ``rdfs:comment`` triple
  (both are needed).  Excluded: untyped node shapes; ``skos:prefLabel``, ``sh:name`` and
  ``dcterms:description`` do not count, as a shape is not an ontology term.  Info: documentation only.
* **SHQ005.** For each node or property shape and each of ``sh:name``, ``sh:description`` and
  ``sh:message``, one finding when two literal values share a language tag, compared case-insensitively
  (BCP 47); untagged literals share one tag.  IRI values are not counted.  Warning: 2.1.5 says a shape
  "should not have more than one value for sh:message with the same language tag" and 2.3.2.1 says
  the same of ``sh:name`` and ``sh:description``; a tool showing one of them picks arbitrarily.
* **SHQ006.** Every class of ``ctx.classes`` (owned, typed ``owl:Class`` or ``rdfs:Class``) with a
  directly typed instance in the data graph that no class target reaches: neither the class nor one of
  its superclasses (``rdfs:subClassOf``, transitively, in the data graph, as SHACL 1.1 defines a SHACL
  instance and 2.1.3.2 requires) is a value of ``sh:targetClass`` on any node, or is itself typed
  ``sh:NodeShape`` or ``sh:PropertyShape`` and ``rdfs:Class`` or ``owl:Class`` in the shapes graph
  (an implicit class target, 2.1.3.3; SHACL requires ``rdfs:Class``, ``owl:Class`` is accepted).
  Excluded: ``sh:targetNode``, ``sh:targetSubjectsOf``, ``sh:targetObjectsOf`` and SHACL-AF targets,
  which may also reach the instances; instances only through a subclass; foreign classes.  Known gap: the
  target of a deactivated shape still covers its class, though 2.1.6 validates nothing there.  The message
  still says "no direct sh:targetClass" (unchanged, so that baselines keep matching).  Warning: such
  instances are never validated, which is usually an oversight, but validation coverage may be partial
  by design.

Fixtures: ``tests/rule_cases/shapes.py`` and ``tests/test_shq_specification.py``.
"""

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
