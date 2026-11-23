"""SHACL shape-authoring quality heuristics over the supplied shapes graph: SHQ009, 010, 012, 014-016, 022, 023.

Implemented: SHQ009 (``sh:in`` list), SHQ010 (``sh:languageIn`` tags), SHQ012 (``sh:uniqueLang`` on a
non-language-tagged datatype or outside a property shape), SHQ014 (``sh:severity`` outside the SHACL
vocabulary), SHQ015 (``sh:flags``: a letter other than ``s``, ``m``, ``i``, ``x`` and ``q``, which SHQ011 drops
when it compiles the pattern, or flags without a pattern), SHQ016 (recursive shape references), SHQ022
(non-IRI shape targets) and SHQ023 (property shape without exactly one ``sh:path``).

Every check is a structural lint of the asserted shapes graph (no SHACL engine, no entailment, no network) that
complements, and never repeats, the checks of ``shapes`` (SHQ001-006) and ``shacl_authoring`` (SHQ007-027).  The
rules are skipped when no shapes graph is supplied; ``run`` is also a no-op then.  The data graph is never read.

A *shape* here is a node typed ``sh:NodeShape`` or ``sh:PropertyShape``, an IRI or blank node value of
``sh:property``, or an IRI or blank node subject of any ``sh:`` predicate. A *list* is a well-formed RDF list as
:func:`~.support.list_items` reads it (at most 500 members, no cycle); a value that is no list is not judged by
SHQ009, SHQ010 and SHQ016. References are to the SHACL Recommendation (2017-07-20); section and table numbers and
quoted phrases of the cited specifications were not independently verified (issues #182 and #247). Statements about
Apache Jena 4.10.0 were measured by hand (``docs/severity-decisions.md``, "Reproduce") and are not committed as
fixtures or run in CI (issue #207). Every finding is recorded ``heuristic``, the default confidence, although most
conditions are exact. Specifications:

* **SHQ009.** Every value of ``sh:in`` on a shape that is a list with no member ("empty"), or with a member
  repeated, compared as RDF terms ("repeats n member(s)": the number of surplus members, ``"a"`` and
  ``"a"^^xsd:string`` being one term); one finding of each kind per shape. ``"4"^^xsd:byte``, ``4`` and ``"4"`` are
  distinct (4.8.3: "matching of literals needs to be exact"); rdflib's normalisation of lexical forms
  (``"01"^^xsd:integer`` is read as ``1``) is kept. Excluded: a literal value or a malformed list. Warning: an empty
  list fails every value node; a repeated member is harmless but usually a copy error.
* **SHQ010.** Every member of an ``sh:languageIn`` list on a shape that is not a basic language range (4.4.4,
  RFC 4647 2.1: ``1*8ALPHA *("-" 1*8alphanum)`` or ``*``), or that is a literal with a language tag or a
  datatype other than ``xsd:string`` (4.4.4: "each member ... is a literal with datatype xsd:string"); one
  finding per member, an IRI or blank member is "not a well-formed language tag".  Excluded: an empty list,
  a malformed list, a literal value; the registry of BCP 47 subtags is not consulted (``xx-YY`` passes).
  A member repeated verbatim gives one finding.  Warning: a malformed range matches no tag, so it admits
  nothing; the list rejects every value node only when none of its members is well formed (``('en' 'e1')``
  still accepts ``"en"``).
* **SHQ012.** Two defects.  (1) Every shape with ``sh:uniqueLang true`` (an ``xsd:boolean`` literal whose value
  is true) and an IRI ``sh:datatype`` other than ``rdf:langString``; one finding per datatype.  Excluded:
  ``sh:uniqueLang`` ``"true"`` (a string), no ``sh:datatype``, a literal datatype.  Info: the constraint only
  sees value nodes that already violate ``sh:datatype``, so it is vacuous for conforming data.  (2) Every shape
  with any ``sh:uniqueLang`` value (``false`` and a string included) that is not a property shape (the set of
  SHQ023: no ``sh:path``, not typed ``sh:PropertyShape``, not a value of ``sh:property``), whatever its type,
  because 4.4.5 allows the parameter in property shapes only and SHACL-SHACL (``shsh:NodeShapeShape``,
  ``uniqueLang-scope``) rejects it on any other shape, so SHACL001 fails with ``the shapes graph does not
  conform to SHACL-SHACL`` and no engine run accepts the shapes graph; one finding per shape, and the MetaSHACL
  result line carries ``(SHQ012)``.  Excluded: a shape with a path, which is a property shape (a typed
  node shape with a path is SHQ023's: it reports the path), and a property shape without a path, which SHQ023
  reports.  The
  decision is to report it here, not in a rule of its own (the defect is the same parameter in the wrong place),
  and not to leave the gap (a lint run that said nothing about a shapes graph no engine accepts).  Defect (2)
  is reported at the rule's Info, like defect (1), although it makes SHACL001 fail; the finding passes no
  severity of its own.
* **SHQ014.** Every value of ``sh:severity`` on a shape that is not an IRI (2.1.4: "each value of sh:severity ... is
  an IRI"), or is an IRI in the ``sh:`` namespace other than ``sh:Info``, ``sh:Warning`` and ``sh:Violation``; and
  every shape with more than one distinct value (2.1.4: "a shape has at most one value for sh:severity"), reported
  once as "several" whatever the values are (as SHQ023 does for ``sh:path``), on top of the finding of each value
  that is not a severity. Excluded: any IRI outside ``sh:`` ("any IRI can be used as a severity"); one value named
  twice, which is one RDF triple. Decided (issue #138): any subject of an ``sh:`` predicate counts as a shape here,
  a node whose only ``sh:`` triple is ``sh:severity`` and an ``owl:Class`` that carries a severity included, though
  SHACL-SHACL does not check such a node and pySHACL accepts two values on it; the strict reading would need a list
  of what makes a shape (SHACL 2.1.3) kept in step with the specification, for a finding that costs one warning on a
  node that uses the SHACL vocabulary. Warning: a literal or several values make the shape ill-formed (SHACL-SHACL
  rejects the shapes graph: SHACL001 fails); an unknown ``sh:`` IRI is most likely a typo, but processors accept it.
* **SHQ015.** Every value of ``sh:flags`` on a shape that is not a literal made only of ``s``, ``m``, ``i``,
  ``x`` and ``q`` (F&O 3.1 5.6.2; ``q`` is XPath 3.0, ``s``, ``m``, ``i`` and ``x`` XPath 2.0, which SPARQL
  1.1 REGEX cites), and every shape with ``sh:flags`` but no ``sh:pattern`` (4.4.3: an optional parameter of
  ``sh:PatternConstraintComponent``).  The empty string and repeated letters are valid.  Excluded: the
  datatype of the flags literal.  Error for an unknown letter: it is an error in XPath (FORX0001) and engines
  differ, pySHACL 0.40.2 ignoring the letter (the shapes graph conforms) while Apache Jena 4.10.0 stops with an
  unsupported-flag error (exit 2); SHQ011 compiles the pattern without it.  Warning for flags without a
  pattern, which engines ignore.  The rule is registered at error and the second condition reports its own
  severity.
* **SHQ016.** Every shape on a cycle of the "refers to" relation of 3.4.3: ``sh:node``, ``sh:property``,
  ``sh:not`` and ``sh:qualifiedValueShape`` values and ``sh:and``, ``sh:or`` and ``sh:xone`` list members that
  are IRIs or blank nodes; a self-reference counts.  One finding per shape, naming the size of its strongly
  connected component.  Excluded: targets and ``sh:in`` or ``sh:languageIn`` lists.  Info: "the validation
  with recursive shapes is not defined in SHACL", so the result depends on the processor; recursion may be
  intended.
* **SHQ022.** Every value of ``sh:targetClass``, ``sh:targetSubjectsOf`` or ``sh:targetObjectsOf`` that is not
  an IRI (2.1.3.2, 2.1.3.4, 2.1.3.5 require IRIs; a literal ``sh:targetClass`` is ill-formed, 2.1).  Excluded:
  ``sh:targetNode``, which may be a literal.  Warning: the target selects nothing.
* **SHQ023.** Every property shape that has no ``sh:path`` ("none") or more than one distinct value
  ("several").  A property shape is a node typed ``sh:PropertyShape`` or an IRI or blank node value of
  ``sh:property``, which must have exactly one path (2.3: "SHACL instances of sh:PropertyShape have one value
  for the property sh:path"; 4.7.2: the values of ``sh:property`` are property shapes), and any subject of
  ``sh:path``, which has at most one (2.3: "a shape has at most one value for sh:path").  A list (sequence path)
  or a blank path is one value.  Also every node typed ``sh:NodeShape`` that has an ``sh:path`` ("node shape"),
  which 2.2 forbids: SHACL-SHACL accepts it, but pySHACL refuses every such shape with a ``ShapeLoadError``
  (deactivated, unreferenced or also typed ``sh:PropertyShape`` included), so SHACL001 fails.  It was a kept gap
  ("not reported on purpose", left to SHACL-SHACL as for the other gaps of issue #62), but SHACL-SHACL does not
  see it, so the user got pySHACL's own text and no pointer; issue #96 reports it here, with no new rule.
  A node shape with several paths gets both findings.
  Excluded: the path is not checked for well-formedness.  Warning: the shape is ill-formed, and a
  processor may reject the shapes graph or validate either path.

Fixtures: ``tests/rule_cases/shacl_quality.py``, ``tests/test_mutation_shacl_quality.py`` and
``tests/test_shq_specification.py``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import RDF, SH, XSD
from rdflib.term import Node

from ontolint.models import Requirement, RuleBackend, RuleScope, RuleSpec, Severity

from .support import list_items, shape_term, term_key, term_text, value_text

if TYPE_CHECKING:
    from .runtime import RuleContext

type Check = Callable[["RuleContext", Graph, Node], None]

# RFC 4647 section 2.1 basic language range, which SHACL 4.4.4 names: a BCP 47 tag shape, or the wildcard.
LANGUAGE_TAG = re.compile(r"[A-Za-z]{1,8}(-[A-Za-z0-9]{1,8})*|\*")
XPATH_FLAGS = frozenset("smixq")
SEVERITIES = (SH.Info, SH.Warning, SH.Violation)
TARGET_NAMES = {SH.targetClass: "sh:targetClass", SH.targetSubjectsOf: "sh:targetSubjectsOf"}
TARGET_NAMES[SH.targetObjectsOf] = "sh:targetObjectsOf"
SHAPE_NS = str(SH)
LOGICAL_PARAMETERS = (SH["and"], SH["or"], SH.xone)
DIRECT_REFERENCES = (SH.node, SH.property, SH["not"], SH.qualifiedValueShape)
MIN_CYCLE = 2


def _spec(rule_id: str, title: str, severity: Severity, suggestion: str) -> RuleSpec:
    return RuleSpec(
        rule_id,
        "SHQ",
        title,
        severity,
        suggestion,
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.SHAPES,
        "shacl_quality",
        Requirement.SHAPES,
    )


SPECS: tuple[RuleSpec, ...] = (
    _spec(
        "SHQ009",
        "sh:in list that is empty or repeats members",
        Severity.WARNING,
        "Remove duplicate members; an empty sh:in list can never be satisfied.",
    ),
    _spec(
        "SHQ010",
        "sh:languageIn with a malformed language tag",
        Severity.WARNING,
        'List well-formed BCP 47 language tags as plain literals, for example "en" or "fr-CA".',
    ),
    _spec(
        "SHQ012",
        "sh:uniqueLang on a shape with a non-language-tagged datatype or outside a property shape",
        Severity.INFO,
        "Drop sh:uniqueLang or use sh:datatype rdf:langString; other datatypes never carry a language tag. "
        "Put sh:uniqueLang in a property shape (one with sh:path).",
    ),
    _spec(
        "SHQ014",
        "sh:severity outside the SHACL severity vocabulary or with several values",
        Severity.WARNING,
        "Give a shape one sh:severity: sh:Info, sh:Warning or sh:Violation, or a custom IRI outside sh:.",
    ),
    _spec(
        "SHQ015",
        "Invalid sh:flags value or sh:flags without sh:pattern",
        Severity.ERROR,
        "Use only the flags s, m, i, x and q, and put sh:flags next to the sh:pattern it modifies.",
    ),
    _spec(
        "SHQ016",
        "Shape that is part of a recursive reference cycle",
        Severity.INFO,
        "Break the cycle: recursive shape references have implementation-defined validation behaviour.",
    ),
    _spec(
        "SHQ022",
        "Shape target value that is not an IRI",
        Severity.WARNING,
        "Use an IRI for sh:targetClass, sh:targetSubjectsOf and sh:targetObjectsOf.",
    ),
    _spec(
        "SHQ023",
        "Property shape without exactly one sh:path",
        Severity.WARNING,
        "Give every property shape exactly one sh:path.",
    ),
)


# --- helpers ---------------------------------------------------------------------------------


def _is_true(term: Node) -> bool:
    return isinstance(term, Literal) and term.datatype == XSD.boolean and term.value is True


def _shapes(sg: Graph) -> list[Node]:
    """Return subjects that use the SHACL vocabulary, typed shapes and property-shape objects, sorted."""
    found: set[Node] = set(sg.subjects(RDF.type, SH.NodeShape)) | set(sg.subjects(RDF.type, SH.PropertyShape))
    found |= {o for o in sg.objects(None, SH.property) if isinstance(o, URIRef | BNode)}
    found |= {s for s, p in sg.subject_predicates() if isinstance(s, URIRef | BNode) and str(p).startswith(SHAPE_NS)}
    return sorted(found, key=str)


# --- per-shape checks ------------------------------------------------------------------------


def _in_list(ctx: RuleContext, sg: Graph, shape: Node) -> None:
    for head in sg.objects(shape, SH["in"]):
        items = None if isinstance(head, Literal) else list_items(sg, head)
        if items is None:
            continue
        if not items:
            ctx.add("SHQ009", shape, "sh:in list is empty; no value can satisfy it.", subject=(SH["in"], "empty"))
        elif (distinct := len({term_key(item) for item in items})) < len(items):
            ctx.add(
                "SHQ009",
                shape,
                f"sh:in list repeats {len(items) - distinct} member(s).",
                subject=(SH["in"], "repeated"),
            )


def _language_in(ctx: RuleContext, sg: Graph, shape: Node) -> None:
    for head in sg.objects(shape, SH.languageIn):
        items = None if isinstance(head, Literal) else list_items(sg, head)
        for item in items or ():
            if isinstance(item, Literal) and (item.language is not None or item.datatype not in (None, XSD.string)):
                message = f"sh:languageIn member {term_text(item)} is not an xsd:string literal."
                ctx.add("SHQ010", shape, message, subject=(item,))
            elif not isinstance(item, Literal) or LANGUAGE_TAG.fullmatch(str(item)) is None:
                ctx.add(
                    "SHQ010",
                    shape,
                    f"sh:languageIn member {value_text(item)} is not a well-formed language tag.",
                    subject=(shape_term(item),),
                )


def _unique_lang(ctx: RuleContext, sg: Graph, shape: Node) -> None:
    if not any(_is_true(v) for v in sg.objects(shape, SH.uniqueLang)):
        return
    for datatype in sg.objects(shape, SH.datatype):
        if isinstance(datatype, URIRef) and datatype != RDF.langString:
            ctx.add(
                "SHQ012",
                shape,
                f"sh:uniqueLang is vacuous with sh:datatype {datatype!s}; only rdf:langString values have a language.",
                subject=(datatype,),
            )


def has_unique_lang_scope_defect(sg: Graph, shape: Node, property_shapes: set[Node]) -> bool:
    """Whether SHQ012 reports ``shape`` for ``sh:uniqueLang`` outside a property shape (SHACL 4.4.5)."""
    return shape not in property_shapes and (shape, SH.uniqueLang, None) in sg


def _unique_lang_scope(ctx: RuleContext, sg: Graph, shape: Node, property_shapes: set[Node]) -> None:
    if has_unique_lang_scope_defect(sg, shape, property_shapes):
        ctx.add(
            "SHQ012",
            shape,
            "sh:uniqueLang is used on a shape with no sh:path; SHACL 4.4.5 allows it only in a property shape.",
            subject=(SH.uniqueLang, "node shape"),
        )


def _severity(ctx: RuleContext, sg: Graph, shape: Node) -> None:
    count = len(set(sg.objects(shape, SH.severity)))
    if count > 1:
        message = f"Shape has {count} sh:severity values; SHACL 2.1.4 allows one."
        ctx.add("SHQ014", shape, message, subject=(SH.severity, "several"))
    for value in sg.objects(shape, SH.severity):
        if value in SEVERITIES:
            continue
        if not isinstance(value, URIRef) or str(value).startswith(SHAPE_NS):
            ctx.add(
                "SHQ014",
                shape,
                f"sh:severity value {value_text(value)} is not sh:Info, sh:Warning or sh:Violation.",
                subject=(shape_term(value),),
            )


def _flags(ctx: RuleContext, sg: Graph, shape: Node) -> None:
    values = list(sg.objects(shape, SH.flags))
    for flag in values:
        if not isinstance(flag, Literal) or not set(str(flag)) <= XPATH_FLAGS:
            ctx.add(
                "SHQ015",
                shape,
                f"sh:flags value {value_text(flag)} is not made of the flags s, m, i, x and q.",
                subject=(shape_term(flag),),
            )
    if values and (shape, SH.pattern, None) not in sg:
        ctx.add("SHQ015", shape, "sh:flags is used without an sh:pattern.", subject=(SH.pattern,), severity="warning")


def _targets(ctx: RuleContext, sg: Graph, shape: Node) -> None:
    for predicate, name in TARGET_NAMES.items():
        for value in sg.objects(shape, predicate):
            if not isinstance(value, URIRef):
                ctx.add(
                    "SHQ022",
                    shape,
                    f"{name} value {value_text(value)} is not an IRI.",
                    subject=(predicate, shape_term(value)),
                )


def property_shape_nodes(sg: Graph) -> set[Node]:
    """The property shapes of ``sg`` (SHQ023): a subject of ``sh:path`` is one (SHACL 2.3), and a node typed
    ``sh:PropertyShape`` or an IRI or blank node value of ``sh:property`` must be."""
    shapes = set(sg.subjects(RDF.type, SH.PropertyShape)) | set(sg.subjects(SH.path, None))
    return shapes | {o for o in sg.objects(None, SH.property) if isinstance(o, URIRef | BNode)}


def is_node_shape_with_path(sg: Graph, shape: Node) -> bool:
    """Whether ``shape`` is typed ``sh:NodeShape`` and has an ``sh:path``: SHACL 2.2 forbids it, and pySHACL refuses
    it as a ``ShapeLoadError`` for every such shape (deactivated, unreferenced or typed ``sh:PropertyShape`` too)."""
    return (shape, RDF.type, SH.NodeShape) in sg and (shape, SH.path, None) in sg


def has_path_defect(sg: Graph, shape: Node, property_shapes: set[Node]) -> bool:
    """Whether SHQ023 reports ``shape``: a node shape with a path, or a property shape without exactly one."""
    if is_node_shape_with_path(sg, shape):
        return True
    return shape in property_shapes and len(set(sg.objects(shape, SH.path))) != 1


def _property_path(ctx: RuleContext, sg: Graph, shape: Node, property_shapes: set[Node]) -> None:
    if is_node_shape_with_path(sg, shape):
        ctx.add("SHQ023", shape, "Node shape has an sh:path.", subject=(SH.path, "node shape"))
    if shape not in property_shapes:
        return
    count = len(set(sg.objects(shape, SH.path)))
    if count == 0:
        ctx.add("SHQ023", shape, "Property shape has no sh:path.", subject=(SH.path, "none"))
    elif count > 1:
        ctx.add("SHQ023", shape, f"Property shape has {count} sh:path values.", subject=(SH.path, "several"))


# --- recursion (SHQ016) ----------------------------------------------------------------------


def _references(sg: Graph, shape: Node) -> list[Node]:
    out: set[Node] = set()
    for predicate in DIRECT_REFERENCES:
        out |= {o for o in sg.objects(shape, predicate) if isinstance(o, URIRef | BNode)}
    for predicate in LOGICAL_PARAMETERS:
        for head in sg.objects(shape, predicate):
            items = None if isinstance(head, Literal) else list_items(sg, head)
            out |= {i for i in items or () if isinstance(i, URIRef | BNode)}
    return sorted(out, key=str)


def _pop_component(stack: list[Node], on_stack: set[Node], root: Node) -> list[Node]:
    component: list[Node] = []
    while True:
        member = stack.pop()
        on_stack.discard(member)
        component.append(member)
        if member == root:
            return component


def _cyclic_shapes(sg: Graph, shapes: list[Node]) -> dict[Node, int]:
    """Return ``{shape: size of its strongly connected component}`` for shapes on a reference cycle."""
    edges = {shape: _references(sg, shape) for shape in shapes}
    index: dict[Node, int] = {}
    low: dict[Node, int] = {}
    on_stack: set[Node] = set()
    stack: list[Node] = []
    cyclic: dict[Node, int] = {}
    for root in shapes:
        if root in index:
            continue
        index[root] = low[root] = len(index)
        stack.append(root)
        on_stack.add(root)
        work: list[tuple[Node, int]] = [(root, 0)]
        while work:
            node, position = work.pop()
            successors = edges.get(node, [])
            if position < len(successors):
                work.append((node, position + 1))
                target = successors[position]
                if target not in index:
                    index[target] = low[target] = len(index)
                    stack.append(target)
                    on_stack.add(target)
                    work.append((target, 0))
                elif target in on_stack:
                    low[node] = min(low[node], index[target])
                continue
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                component = _pop_component(stack, on_stack, node)
                if len(component) >= MIN_CYCLE or node in edges.get(node, []):
                    cyclic.update(dict.fromkeys(component, len(component)))
    return cyclic


SHAPE_CHECKS: tuple[Check, ...] = (_in_list, _language_in, _unique_lang, _severity, _flags, _targets)


def run(ctx: RuleContext) -> None:
    """Run the SHACL quality checks; a no-op when no shapes graph was supplied."""
    sg = ctx.shapes
    if sg is None:
        return
    shapes = _shapes(sg)
    property_shapes = property_shape_nodes(sg)
    for shape in shapes:
        for check in SHAPE_CHECKS:
            check(ctx, sg, shape)
        _property_path(ctx, sg, shape, property_shapes)
        _unique_lang_scope(ctx, sg, shape, property_shapes)
    for shape, size in _cyclic_shapes(sg, shapes).items():
        ctx.add("SHQ016", shape, f"Shape is part of a reference cycle of {size} shape(s).", subject=())
