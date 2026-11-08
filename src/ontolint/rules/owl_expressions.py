"""OWL class-expression, restriction and individual-assertion rules: OWL031-OWL045.

Every rule is purely graph-local and sound without a reasoner: each reports a structural defect or a
direct contradiction visible in the asserted triples (no entailment is materialised).
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from typing import TYPE_CHECKING

from rdflib import BNode, Literal, URIRef
from rdflib.namespace import OWL, RDFS, XSD
from rdflib.term import Node

from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity

from .support import list_items, owning_term

if TYPE_CHECKING:
    from .runtime import RuleContext


def _spec(rule_id: str, title: str, severity: Severity, suggestion: str) -> RuleSpec:
    return RuleSpec(
        rule_id,
        "OWL",
        title,
        severity,
        suggestion,
        "deterministic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "owl_expressions",
    )


SPECS: tuple[RuleSpec, ...] = (
    _spec(
        "OWL031",
        "Malformed or empty class-expression list",
        Severity.ERROR,
        "Give owl:unionOf, owl:intersectionOf, owl:oneOf and owl:disjointUnionOf a well-formed, non-empty RDF list.",
    ),
    _spec(
        "OWL032",
        "Single-operand union or intersection",
        Severity.INFO,
        "Replace an owl:unionOf or owl:intersectionOf with one operand by that operand.",
    ),
    _spec(
        "OWL033",
        "Duplicate operand in class-expression list",
        Severity.WARNING,
        "Remove the repeated member from the owl:unionOf, owl:intersectionOf or owl:oneOf list.",
    ),
    _spec(
        "OWL034",
        "Restriction with missing or invalid owl:onProperty",
        Severity.ERROR,
        "Give every owl:Restriction exactly one owl:onProperty (or owl:onProperties) pointing to a property.",
    ),
    _spec(
        "OWL035",
        "Restriction without a constraint",
        Severity.ERROR,
        "Add an owl:someValuesFrom, owl:allValuesFrom, owl:hasValue, owl:hasSelf or cardinality constraint.",
    ),
    _spec(
        "OWL036",
        "Invalid cardinality restriction",
        Severity.ERROR,
        "Use a non-negative integer for cardinalities and add owl:onClass/owl:onDataRange to qualified ones.",
    ),
    _spec(
        "OWL037",
        "Minimum cardinality exceeds maximum cardinality",
        Severity.ERROR,
        "Make the lower cardinality bound at most the upper bound within one restriction.",
    ),
    _spec(
        "OWL038",
        "Existential restriction on owl:Nothing",
        Severity.ERROR,
        "Remove the restriction or use a satisfiable filler; no individual can be an instance of owl:Nothing.",
    ),
    _spec(
        "OWL039",
        "Vacuous restriction",
        Severity.INFO,
        "Remove a restriction that every individual satisfies (allValuesFrom owl:Thing, minimum cardinality 0).",
    ),
    _spec(
        "OWL040",
        "Restriction mixes object and datatype property kinds",
        Severity.ERROR,
        "Use class fillers and resources with object properties, and datatypes and literals with datatype properties.",
    ),
    _spec(
        "OWL041",
        "Contradictory owl:complementOf cycle",
        Severity.ERROR,
        "Break the odd-length owl:complementOf cycle; a class cannot be the complement of itself.",
    ),
    _spec(
        "OWL042",
        "Class subclass of or equivalent to its own complement",
        Severity.ERROR,
        "Remove the axiom relating a class to its own owl:complementOf expression.",
    ),
    _spec(
        "OWL043",
        "Contradictory or tautological operands in union or intersection",
        Severity.WARNING,
        "Review an intersection of complements/disjoint classes or a union of a class and its complement.",
    ),
    _spec(
        "OWL044",
        "Individuals identical through owl:sameAs chains but asserted different",
        Severity.ERROR,
        "Remove the conflicting owl:sameAs or owl:differentFrom assertion; nothing differs from itself.",
    ),
    _spec(
        "OWL045",
        "Malformed owl:AllDifferent or owl:AllDisjointClasses",
        Severity.WARNING,
        "Give the axiom one well-formed member list with at least two distinct members.",
    ),
)

_MAX_LIST = 1_000_000
_MIN_DISTINCT_MEMBERS = 2
_COUNT = re.compile(r"\+?[0-9]+")

_UNQUALIFIED = (OWL.minCardinality, OWL.maxCardinality, OWL.cardinality)
_QUALIFIED = (OWL.minQualifiedCardinality, OWL.maxQualifiedCardinality, OWL.qualifiedCardinality)
_CARDINALITIES = (*_UNQUALIFIED, *_QUALIFIED)
_CONSTRAINTS = (OWL.allValuesFrom, OWL.someValuesFrom, OWL.hasValue, OWL.hasSelf, *_CARDINALITIES)
_SET_OPERATORS = (OWL.unionOf, OWL.intersectionOf, OWL.oneOf, OWL.disjointUnionOf)


def _name(node: Node) -> str:
    return str(node) if isinstance(node, URIRef) else f"_:{node}" if isinstance(node, BNode) else repr(node)


def _short(predicate: Node) -> str:
    return "owl:" + str(predicate).removeprefix(str(OWL))


def _count(value: Node) -> int | None:
    """Return a cardinality value if its lexical form is a non-negative integer."""
    if isinstance(value, Literal) and _COUNT.fullmatch(str(value).strip()):
        return int(str(value).strip())
    return None


def _counts(ctx: RuleContext, restriction: Node, predicate: Node) -> list[int]:
    return [n for o in ctx.g.objects(restriction, predicate) if (n := _count(o)) is not None]


def run(ctx: RuleContext) -> None:
    """Run all class-expression, restriction and individual rules."""
    _operator_lists(ctx)
    restrictions = sorted(ctx.context.subjects_by_type.get(OWL.Restriction, frozenset()), key=str)
    for restriction in restrictions:
        _restriction(ctx, restriction)
    _complements(ctx)
    _identity(ctx)
    _pairwise_axioms(ctx)


# --- operator lists (OWL031-OWL033, OWL043) --------------------------------------------------


def _operator_lists(ctx: RuleContext) -> None:
    g = ctx.g
    for predicate in _SET_OPERATORS:
        label = _short(predicate)
        for subject, head in sorted(g.subject_objects(predicate), key=lambda pair: (str(pair[0]), str(pair[1]))):
            items = list_items(g, head, limit=_MAX_LIST)
            if items is None:
                ctx.add("OWL031", subject, f"{label} does not point to a well-formed RDF list.", confidence="certain")
                continue
            if not items:
                ctx.add("OWL031", subject, f"{label} list is empty.", confidence="certain")
                continue
            if predicate in (OWL.unionOf, OWL.intersectionOf) and len(items) == 1:
                ctx.add("OWL032", subject, f"{label} has a single operand ({_name(items[0])}).", confidence="certain")
            if predicate != OWL.disjointUnionOf and len(set(items)) != len(items):
                ctx.add("OWL033", subject, f"{label} list repeats a member.", confidence="certain")
            if predicate in (OWL.unionOf, OWL.intersectionOf):
                _operands(ctx, subject, predicate, items)


def _operands(ctx: RuleContext, subject: Node, predicate: Node, items: list[Node]) -> None:
    """OWL043: a union or intersection whose operands make the expression trivial or unsatisfiable.

    Boundary with OWL025: disjoint classes that are also asserted subclasses or equivalents of each other
    are an axiom conflict, reported there; this rule only judges the operand list of one expression.
    """
    g = ctx.g
    members = set(items)
    union = predicate == OWL.unionOf
    label = _short(predicate)
    pairs: set[tuple[str, str]] = set()
    for member in members:
        for other in g.objects(member, OWL.complementOf):
            if other in members:
                pairs.add((min(_name(member), _name(other)), max(_name(member), _name(other))))
        if not union:
            for other in g.objects(member, OWL.disjointWith):
                if other in members:
                    pairs.add((min(_name(member), _name(other)), max(_name(member), _name(other))))
    effect = "is equivalent to owl:Thing" if union else "is unsatisfiable"
    for left, right in sorted(pairs):
        kind = "complementary" if union else "complementary or disjoint"
        ctx.add(
            "OWL043",
            subject,
            f"{label} contains {kind} operands {left} and {right}; it {effect}.",
            confidence="certain",
        )
    if union and OWL.Thing in members:
        ctx.add("OWL043", subject, f"{label} contains owl:Thing; it is equivalent to owl:Thing.", confidence="certain")
    if not union and OWL.Nothing in members:
        ctx.add("OWL043", subject, f"{label} contains owl:Nothing; it is unsatisfiable.", confidence="certain")


# --- restrictions (OWL034-OWL040) ------------------------------------------------------------


def _report(ctx: RuleContext, code: str, restriction: Node, message: str, *, confidence: str = "heuristic") -> None:
    """Emit a restriction finding; the focus stays the stable blank-node identity, the message names the owner."""
    owner = owning_term(ctx.g, restriction)
    if isinstance(owner, URIRef):
        properties = sorted({str(p) for p in ctx.g.objects(restriction, OWL.onProperty) if isinstance(p, URIRef)})
        where = f"restriction on {', '.join(properties)}" if properties else "restriction"
        message = f"{owner} ({where}): {message}"
    ctx.add(code, restriction, message, confidence=confidence)


def _restriction(ctx: RuleContext, restriction: Node) -> None:
    g = ctx.g
    on_property = list(g.objects(restriction, OWL.onProperty))
    on_properties = list(g.objects(restriction, OWL.onProperties))
    if not on_property and not on_properties:
        _report(ctx, "OWL034", restriction, "Restriction has no owl:onProperty.", confidence="certain")
    elif len(on_property) > 1:
        _report(ctx, "OWL034", restriction, "Restriction has more than one owl:onProperty.", confidence="certain")
    for value in on_property:
        if isinstance(value, Literal):
            _report(ctx, "OWL034", restriction, f"owl:onProperty points to literal {value!r}.", confidence="certain")
    if not any((restriction, constraint, None) in g for constraint in _CONSTRAINTS):
        _report(
            ctx,
            "OWL035",
            restriction,
            "Restriction has no value, cardinality or self constraint.",
            confidence="certain",
        )
    _cardinalities(ctx, restriction)
    _existential_nothing(ctx, restriction)
    _vacuous(ctx, restriction)
    _property_kind(ctx, restriction, on_property)


def _cardinalities(ctx: RuleContext, restriction: Node) -> None:
    g = ctx.g
    for predicate in _CARDINALITIES:
        for value in g.objects(restriction, predicate):
            if _count(value) is None:
                _report(
                    ctx,
                    "OWL036",
                    restriction,
                    f"{_short(predicate)} value {value!r} is not a non-negative integer.",
                    confidence="certain",
                )
    qualified = any((restriction, p, None) in g for p in _QUALIFIED)
    if qualified and (restriction, OWL.onClass, None) not in g and (restriction, OWL.onDataRange, None) not in g:
        _report(
            ctx,
            "OWL036",
            restriction,
            "Qualified cardinality has neither owl:onClass nor owl:onDataRange.",
            confidence="certain",
        )
    for group in (_UNQUALIFIED, _QUALIFIED):
        minimum, maximum, exact = (_counts(ctx, restriction, p) for p in group)
        lower = max([*minimum, *exact], default=None)
        upper = min([*maximum, *exact], default=None)
        if lower is not None and upper is not None and lower > upper:
            _report(
                ctx,
                "OWL037",
                restriction,
                f"Lower cardinality bound {lower} exceeds upper bound {upper}.",
                confidence="certain",
            )


def _existential_nothing(ctx: RuleContext, restriction: Node) -> None:
    g = ctx.g
    if (restriction, OWL.someValuesFrom, OWL.Nothing) in g:
        _report(
            ctx, "OWL038", restriction, "owl:someValuesFrom owl:Nothing can never be satisfied.", confidence="certain"
        )
    if (restriction, OWL.onClass, OWL.Nothing) in g:
        for predicate in (OWL.minQualifiedCardinality, OWL.qualifiedCardinality):
            if any(n > 0 for n in _counts(ctx, restriction, predicate)):
                _report(
                    ctx,
                    "OWL038",
                    restriction,
                    f"{_short(predicate)} above 0 on owl:Nothing can never be satisfied.",
                    confidence="certain",
                )


def _vacuous(ctx: RuleContext, restriction: Node) -> None:
    g = ctx.g
    if (restriction, OWL.allValuesFrom, OWL.Thing) in g:
        _report(
            ctx, "OWL039", restriction, "owl:allValuesFrom owl:Thing holds for every individual.", confidence="certain"
        )
    for predicate in (OWL.minCardinality, OWL.minQualifiedCardinality):
        if 0 in _counts(ctx, restriction, predicate):
            _report(
                ctx, "OWL039", restriction, f"{_short(predicate)} 0 holds for every individual.", confidence="certain"
            )


def _datatype_like(ctx: RuleContext, node: Node) -> bool:
    if isinstance(node, URIRef) and (str(node).startswith(str(XSD)) or node == RDFS.Literal):
        return True
    return RDFS.Datatype in ctx.context.types_by_subject.get(node, frozenset())


def _class_like(ctx: RuleContext, node: Node) -> bool:
    if node in (OWL.Thing, OWL.Nothing) or node in ctx.classes:
        return True
    return bool(ctx.context.types_by_subject.get(node, frozenset()) & {OWL.Class, OWL.Restriction})


def _property_kind(ctx: RuleContext, restriction: Node, on_property: list[Node]) -> None:
    g = ctx.g
    for prop in on_property:
        types = ctx.context.types_by_subject.get(prop, frozenset())
        is_object, is_data = OWL.ObjectProperty in types, OWL.DatatypeProperty in types
        if not isinstance(prop, URIRef) or is_object == is_data:
            continue
        problems: list[str] = []
        fillers = [o for p in (OWL.someValuesFrom, OWL.allValuesFrom) for o in g.objects(restriction, p)]
        values = list(g.objects(restriction, OWL.hasValue))
        if is_object:
            problems += [f"literal hasValue {v!r}" for v in values if isinstance(v, Literal)]
            problems += [f"datatype filler {_name(f)}" for f in fillers if _datatype_like(ctx, f)]
            problems += [f"owl:onDataRange {_name(f)}" for f in g.objects(restriction, OWL.onDataRange)]
        else:
            problems += [f"resource hasValue {_name(v)}" for v in values if not isinstance(v, Literal)]
            problems += [
                f"class filler {_name(f)}" for f in fillers if _class_like(ctx, f) and not _datatype_like(ctx, f)
            ]
            problems += [f"owl:onClass {_name(f)}" for f in g.objects(restriction, OWL.onClass)]
        kind = "object" if is_object else "datatype"
        for problem in problems:
            _report(
                ctx,
                "OWL040",
                restriction,
                f"Restriction on {kind} property {prop} uses {problem}.",
                confidence="certain",
            )


# --- complements (OWL041, OWL042) ------------------------------------------------------------


def _complements(ctx: RuleContext) -> None:
    g = ctx.g
    adjacent: dict[Node, set[Node]] = defaultdict(set)
    for expression, operand in g.subject_objects(OWL.complementOf):
        if isinstance(operand, Literal):
            continue
        adjacent[expression].add(operand)
        adjacent[operand].add(expression)
        if (operand, RDFS.subClassOf, expression) in g:
            ctx.add(
                "OWL042",
                operand,
                f"Class is a subclass of its own complement {_name(expression)}.",
                confidence="certain",
            )
        if (operand, OWL.equivalentClass, expression) in g or (expression, OWL.equivalentClass, operand) in g:
            ctx.add(
                "OWL042",
                operand,
                f"Class is equivalent to its own complement {_name(expression)}.",
                confidence="certain",
            )
    _odd_cycles(ctx, adjacent)


def _odd_cycles(ctx: RuleContext, adjacent: dict[Node, set[Node]]) -> None:
    color: dict[Node, int] = {}
    for start in sorted(adjacent, key=str):
        if start in color:
            continue
        color[start] = 0
        stack, culprit = [start], None
        while stack:
            node = stack.pop()
            for neighbour in sorted(adjacent[node], key=str):
                if neighbour not in color:
                    color[neighbour] = 1 - color[node]
                    stack.append(neighbour)
                elif color[neighbour] == color[node] and culprit is None:
                    culprit = node
        if culprit is not None:
            ctx.add("OWL041", culprit, "owl:complementOf assertions form an odd cycle (a class equals its complement).")


# --- individuals (OWL044, OWL045) ------------------------------------------------------------


def _find(parent: dict[Node, Node], node: Node) -> Node:
    root = node
    while parent.get(root, root) != root:
        root = parent[root]
    while parent.get(node, node) != root:
        parent[node], node = root, parent[node]
    return root


def _members(ctx: RuleContext, axiom: Node, predicates: Iterable[Node]) -> list[list[Node] | None]:
    return [list_items(ctx.g, head, limit=_MAX_LIST) for p in predicates for head in ctx.g.objects(axiom, p)]


def _identity(ctx: RuleContext) -> None:
    """OWL044: identity conflicts that need the ``owl:sameAs`` closure or an ``owl:AllDifferent`` axiom.

    A direct conflict (``a owl:differentFrom a``, or ``owl:sameAs`` and ``owl:differentFrom`` asserted
    between the same two individuals) is OWL026's; reporting it here too would flag one defect twice.
    """
    g = ctx.g
    parent: dict[Node, Node] = {}
    for a, b in g.subject_objects(OWL.sameAs):
        if not isinstance(b, Literal):
            parent[_find(parent, a)] = _find(parent, b)
    for a, b in sorted(g.subject_objects(OWL.differentFrom), key=lambda pair: (str(pair[0]), str(pair[1]))):
        direct = a == b or (a, OWL.sameAs, b) in g or (b, OWL.sameAs, a) in g
        if isinstance(b, Literal) or direct:
            continue
        if _find(parent, a) == _find(parent, b):
            ctx.add(
                "OWL044",
                a,
                f"Individual is asserted different from {_name(b)}, but a chain of owl:sameAs makes them the same.",
                confidence="certain",
            )
    _all_different_conflicts(ctx, parent)


def _all_different_conflicts(ctx: RuleContext, parent: dict[Node, Node]) -> None:
    for axiom in sorted(ctx.context.subjects_by_type.get(OWL.AllDifferent, frozenset()), key=str):
        for items in _members(ctx, axiom, (OWL.members, OWL.distinctMembers)):
            roots: dict[Node, Node] = {}
            for item in dict.fromkeys(items or ()):
                root = _find(parent, item)
                if root in roots:
                    ctx.add(
                        "OWL044",
                        axiom,
                        f"owl:AllDifferent contains {_name(roots[root])} and {_name(item)}, asserted the same.",
                        confidence="certain",
                    )
                roots.setdefault(root, item)


def _pairwise_axioms(ctx: RuleContext) -> None:
    kinds = (
        (OWL.AllDifferent, "owl:AllDifferent", (OWL.members, OWL.distinctMembers)),
        (OWL.AllDisjointClasses, "owl:AllDisjointClasses", (OWL.members,)),
    )
    for type_, label, predicates in kinds:
        for axiom in sorted(ctx.context.subjects_by_type.get(type_, frozenset()), key=str):
            lists = _members(ctx, axiom, predicates)
            if not lists:
                ctx.add("OWL045", axiom, f"{label} has no member list.", confidence="certain")
            elif len(lists) > 1:
                ctx.add("OWL045", axiom, f"{label} has more than one member list.", confidence="certain")
            for items in lists:
                if items is None:
                    ctx.add("OWL045", axiom, f"{label} member list is malformed.", confidence="certain")
                elif len(items) < _MIN_DISTINCT_MEMBERS:
                    ctx.add("OWL045", axiom, f"{label} has fewer than two members.", confidence="certain")
                elif len(set(items)) != len(items):
                    ctx.add("OWL045", axiom, f"{label} repeats a member.", confidence="certain")
