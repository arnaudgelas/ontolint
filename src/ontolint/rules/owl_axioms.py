"""OWL axiom and property-characteristic rules: OWL016-OWL030.

All rules are asserted-graph checks; nothing is entailed and no reasoner is involved.  Subproperty,
subclass and equivalence relations are read as asserted, never closed transitively.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rdflib import Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD
from rdflib.term import Node

from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity

from .support import list_items

if TYPE_CHECKING:
    from .runtime import RuleContext


MAX_GROUP_MEMBERS = 200  # Members read from one owl:AllDisjoint* list.
MIN_CHAIN_LENGTH = 2

SPECS: tuple[RuleSpec, ...] = (
    RuleSpec(
        "OWL016",
        "OWL",
        "Reflexivity characteristic on datatype property",
        Severity.ERROR,
        "Remove owl:ReflexiveProperty/owl:IrreflexiveProperty; they apply to object properties only.",
        "deterministic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "owl_axioms",
    ),
    RuleSpec(
        "OWL017",
        "OWL",
        "Property both symmetric and asymmetric",
        Severity.ERROR,
        "Keep only one of owl:SymmetricProperty and owl:AsymmetricProperty; together they leave the property empty.",
        "deterministic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "owl_axioms",
    ),
    RuleSpec(
        "OWL018",
        "OWL",
        "Reflexive property also irreflexive or asymmetric",
        Severity.ERROR,
        "Remove the contradictory characteristic; a reflexive property cannot be irreflexive or asymmetric.",
        "deterministic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "owl_axioms",
    ),
    RuleSpec(
        "OWL019",
        "OWL",
        "Non-simple property in simple-property axiom",
        Severity.ERROR,
        "Drop functional, inverse-functional, irreflexive or asymmetric from transitive or chain-defined properties.",
        "deterministic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "owl_axioms",
    ),
    RuleSpec(
        "OWL020",
        "OWL",
        "Property subPropertyOf cycle",
        Severity.WARNING,
        "Break the owl:subPropertyOf cycle or replace it with owl:equivalentProperty if the properties are equivalent.",
        "deterministic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "owl_axioms",
    ),
    RuleSpec(
        "OWL021",
        "OWL",
        "Sub-property or equivalent property of a different kind",
        Severity.ERROR,
        "Relate object properties only to object properties and datatype properties only to datatype properties.",
        "deterministic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "owl_axioms",
    ),
    RuleSpec(
        "OWL022",
        "OWL",
        "Property range conflicts with property kind",
        Severity.ERROR,
        "Use datatype ranges for datatype properties and class ranges for object properties.",
        "deterministic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "owl_axioms",
    ),
    RuleSpec(
        "OWL023",
        "OWL",
        "Property with several distinct inverses",
        Severity.WARNING,
        "Review owl:inverseOf axioms; distinct inverses of one property are equivalent to each other.",
        "deterministic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "owl_axioms",
    ),
    RuleSpec(
        "OWL024",
        "OWL",
        "Disjoint properties that are sub-property or equivalent",
        Severity.ERROR,
        "Remove the disjointness or the sub-property/equivalence axiom; the property can have no assertions.",
        "deterministic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "owl_axioms",
    ),
    RuleSpec(
        "OWL025",
        "OWL",
        "Disjoint classes that are subclass or equivalent",
        Severity.ERROR,
        "Remove the disjointness or the subclass/equivalence axiom; the class cannot have instances.",
        "deterministic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "owl_axioms",
    ),
    RuleSpec(
        "OWL026",
        "OWL",
        "Individuals both same and different",
        Severity.ERROR,
        "Remove either the owl:sameAs or the owl:differentFrom assertion; the ontology is inconsistent.",
        "deterministic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "owl_axioms",
    ),
    RuleSpec(
        "OWL027",
        "OWL",
        "Negative property assertion contradicts a positive assertion",
        Severity.ERROR,
        "Remove the NegativePropertyAssertion or the contradicting positive triple.",
        "deterministic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "owl_axioms",
    ),
    RuleSpec(
        "OWL028",
        "OWL",
        "Irreflexive property used reflexively",
        Severity.ERROR,
        "Remove the assertion relating an individual to itself or drop owl:IrreflexiveProperty.",
        "deterministic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "owl_axioms",
    ),
    RuleSpec(
        "OWL029",
        "OWL",
        "Asymmetric property asserted in both directions",
        Severity.ERROR,
        "Remove one direction (or a self-assertion) or drop owl:AsymmetricProperty.",
        "deterministic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "owl_axioms",
    ),
    RuleSpec(
        "OWL030",
        "OWL",
        "Illegal punning of declaration kinds",
        Severity.ERROR,
        "Do not declare one IRI as both class and datatype, or as annotation property and object/datatype property.",
        "deterministic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "owl_axioms",
    ),
)

LITERAL_RANGES = frozenset({RDFS.Literal, RDF.langString, RDF.XMLLiteral, RDF.HTML})
SIMPLE_ONLY_CHARACTERISTICS = (
    ("functional", OWL.FunctionalProperty),
    ("inverse-functional", OWL.InverseFunctionalProperty),
    ("irreflexive", OWL.IrreflexiveProperty),
    ("asymmetric", OWL.AsymmetricProperty),
)


def run(ctx: RuleContext) -> None:
    """Run all OWL axiom rules."""
    _reflexivity_on_datatype_properties(ctx)
    _contradictory_characteristics(ctx)
    _non_simple_properties(ctx)
    _subproperty_cycles(ctx)
    _property_kind_mismatches(ctx)
    _range_kind_conflicts(ctx)
    _multiple_inverses(ctx)
    _disjoint_conflicts(ctx, "OWL024", OWL.propertyDisjointWith, OWL.AllDisjointProperties, "property")
    _disjoint_conflicts(ctx, "OWL025", OWL.disjointWith, OWL.AllDisjointClasses, "class")
    _same_and_different(ctx)
    _negative_assertions(ctx)
    _irreflexive_usage(ctx)
    _asymmetric_usage(ctx)
    _illegal_punning(ctx)


def _typed(ctx: RuleContext, type_: Node) -> frozenset[Node]:
    return ctx.context.subjects_by_type.get(type_, frozenset())


def _ordered(nodes: frozenset[Node] | set[Node]) -> list[Node]:
    return sorted(nodes, key=str)


def _reflexivity_on_datatype_properties(ctx: RuleContext) -> None:
    data_props = _typed(ctx, OWL.DatatypeProperty)
    for type_ in (OWL.ReflexiveProperty, OWL.IrreflexiveProperty):
        for p in _ordered(_typed(ctx, type_) & data_props):
            ctx.add("OWL016", p, f"Datatype property is declared {type_}.", confidence="certain")


def _contradictory_characteristics(ctx: RuleContext) -> None:
    symmetric, asymmetric = _typed(ctx, OWL.SymmetricProperty), _typed(ctx, OWL.AsymmetricProperty)
    reflexive, irreflexive = _typed(ctx, OWL.ReflexiveProperty), _typed(ctx, OWL.IrreflexiveProperty)
    for p in _ordered(symmetric & asymmetric):
        ctx.add("OWL017", p, "Property is declared both symmetric and asymmetric.", confidence="certain")
    for p in _ordered(reflexive & irreflexive):
        ctx.add("OWL018", p, "Property is declared both reflexive and irreflexive.", confidence="certain")
    for p in _ordered(reflexive & asymmetric):
        ctx.add("OWL018", p, "Property is declared both reflexive and asymmetric.", confidence="certain")


def _non_simple_properties(ctx: RuleContext) -> None:
    g = ctx.g
    transitive = _typed(ctx, OWL.TransitiveProperty)
    chained: set[Node] = set()
    for p, chain in g.subject_objects(OWL.propertyChainAxiom):
        items = list_items(g, chain)
        if items is not None and len(items) >= MIN_CHAIN_LENGTH:
            chained.add(p)
    for label, type_ in SIMPLE_ONLY_CHARACTERISTICS:
        for p in _ordered(_typed(ctx, type_) & (transitive | chained)):
            reason = "transitive" if p in transitive else "defined by a property chain"
            ctx.add(
                "OWL019",
                p,
                f"Property is {reason} (non-simple) but declared {label}.",
                confidence="certain",
            )


def _pop_component(stack: list[Node], on_stack: set[Node], root: Node) -> list[Node]:
    component: list[Node] = []
    while True:
        member = stack.pop()
        on_stack.discard(member)
        component.append(member)
        if member == root:
            return sorted(component, key=str)


def _strongly_connected(edges: dict[Node, set[Node]]) -> list[list[Node]]:
    """Return the strongly connected components with more than one node (iterative Tarjan)."""
    index: dict[Node, int] = {}
    low: dict[Node, int] = {}
    stack: list[Node] = []
    on_stack: set[Node] = set()
    components: list[list[Node]] = []
    counter = 0
    for root in sorted(edges, key=str):
        if root in index:
            continue
        work: list[tuple[Node, list[Node]]] = [(root, sorted(edges.get(root, ()), key=str))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, pending = work[-1]
            if pending:
                child = pending.pop()
                if child not in index:
                    index[child] = low[child] = counter
                    counter += 1
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, sorted(edges.get(child, ()), key=str)))
                elif child in on_stack:
                    low[node] = min(low[node], index[child])
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                component = _pop_component(stack, on_stack, node)
                if len(component) > 1:
                    components.append(component)
    return components


def _subproperty_cycles(ctx: RuleContext) -> None:
    edges: dict[Node, set[Node]] = {}
    for p, q in ctx.g.subject_objects(RDFS.subPropertyOf):
        if isinstance(p, URIRef) and isinstance(q, URIRef) and p != q:
            edges.setdefault(p, set()).add(q)
            edges.setdefault(q, set())
    for component in _strongly_connected(edges):
        names = ", ".join(str(n) for n in component)
        ctx.add("OWL020", component[0], f"rdfs:subPropertyOf cycle among: {names}.", confidence="certain")


def _object_only(ctx: RuleContext) -> frozenset[Node]:
    return _typed(ctx, OWL.ObjectProperty) - _typed(ctx, OWL.DatatypeProperty)


def _data_only(ctx: RuleContext) -> frozenset[Node]:
    return _typed(ctx, OWL.DatatypeProperty) - _typed(ctx, OWL.ObjectProperty)


def _property_kind_mismatches(ctx: RuleContext) -> None:
    object_only, data_only = _object_only(ctx), _data_only(ctx)
    for predicate in (RDFS.subPropertyOf, OWL.equivalentProperty):
        for p, q in ctx.g.subject_objects(predicate):
            if (p in object_only and q in data_only) or (p in data_only and q in object_only):
                kind = "object" if p in object_only else "datatype"
                other = "datatype" if kind == "object" else "object"
                ctx.add(
                    "OWL021",
                    p,
                    f"{kind.capitalize()} property is related by {predicate} to {other} property {q}.",
                    confidence="certain",
                )


def _is_datatype_term(ctx: RuleContext, node: Node) -> bool:
    return (
        isinstance(node, URIRef)
        and (node in LITERAL_RANGES or str(node).startswith(str(XSD)) or RDFS.Datatype in _types_of(ctx, node))
        and OWL.Class not in _types_of(ctx, node)
    )


def _types_of(ctx: RuleContext, node: Node) -> frozenset[Node]:
    return ctx.context.types_by_subject.get(node, frozenset())


def _range_kind_conflicts(ctx: RuleContext) -> None:
    ranges = ctx.context.ranges_by_property
    for p in _ordered(_object_only(ctx)):
        for r in _ordered(ranges.get(p, frozenset())):
            if _is_datatype_term(ctx, r):
                ctx.add("OWL022", p, f"Object property has datatype range {r}.", confidence="certain")
    for p in _ordered(_data_only(ctx)):
        for r in _ordered(ranges.get(p, frozenset())):
            is_class = r == OWL.Thing or OWL.Class in _types_of(ctx, r)
            if isinstance(r, URIRef) and is_class and RDFS.Datatype not in _types_of(ctx, r):
                ctx.add("OWL022", p, f"Datatype property has class range {r}.", confidence="certain")


def _multiple_inverses(ctx: RuleContext) -> None:
    inverses: dict[Node, set[Node]] = {}
    for p, q in ctx.g.subject_objects(OWL.inverseOf):
        if p != q and isinstance(p, URIRef) and isinstance(q, URIRef):
            inverses.setdefault(p, set()).add(q)
            inverses.setdefault(q, set()).add(p)
    for p in _ordered(set(inverses)):
        if len(inverses[p]) > 1:
            names = ", ".join(str(n) for n in _ordered(inverses[p]))
            ctx.add("OWL023", p, f"Property has several distinct inverses: {names}.")


def _disjoint_conflicts(ctx: RuleContext, code: str, pair_predicate: Node, group_type: Node, kind: str) -> None:
    """OWL024/OWL025: a disjointness *axiom* contradicted by a subsumption or equivalence axiom between the same pair.

    Boundary with OWL043: an intersection of disjoint or complementary operands is an unsatisfiable class
    *expression*, reported there; this rule only compares axioms between two named members.
    """
    g = ctx.g
    pairs: set[tuple[Node, Node]] = set(g.subject_objects(pair_predicate))
    for group in g.subjects(RDF.type, group_type):
        for head in g.objects(group, OWL.members):
            members = list_items(g, head, limit=MAX_GROUP_MEMBERS)
            if members is not None:
                pairs.update((a, b) for i, a in enumerate(members) for b in members[i + 1 :])
    sub_predicate = RDFS.subPropertyOf if kind == "property" else RDFS.subClassOf
    equiv_predicate = OWL.equivalentProperty if kind == "property" else OWL.equivalentClass
    seen: set[frozenset[Node]] = set()
    for a, b in sorted(pairs, key=lambda pair: (str(pair[0]), str(pair[1]))):
        key = frozenset((a, b))
        if key in seen or OWL.Nothing in key:
            continue
        seen.add(key)
        if a == b:
            relation = "is declared disjoint with itself"
        elif any((x, predicate, y) in g for predicate in (sub_predicate, equiv_predicate) for x, y in ((a, b), (b, a))):
            relation = f"is disjoint with {b} but also asserted a sub{kind} of or equivalent to it"
        else:
            continue
        ctx.add(code, a, f"The {kind} {relation}.", confidence="certain")


def _same_and_different(ctx: RuleContext) -> None:
    g = ctx.g
    seen: set[frozenset[Node]] = set()
    for a, b in sorted(g.subject_objects(OWL.differentFrom), key=lambda pair: (str(pair[0]), str(pair[1]))):
        key = frozenset((a, b))
        if key in seen:
            continue
        seen.add(key)
        if a == b:
            ctx.add("OWL026", a, "Individual is declared different from itself.", confidence="certain")
        elif (a, OWL.sameAs, b) in g or (b, OWL.sameAs, a) in g:
            ctx.add("OWL026", a, f"Individual is both owl:sameAs and owl:differentFrom {b}.", confidence="certain")


def _negative_assertions(ctx: RuleContext) -> None:
    g = ctx.g
    for assertion in g.subjects(RDF.type, OWL.NegativePropertyAssertion):
        targets = [*g.objects(assertion, OWL.targetIndividual), *g.objects(assertion, OWL.targetValue)]
        for s in g.objects(assertion, OWL.sourceIndividual):
            for p in g.objects(assertion, OWL.assertionProperty):
                for target in targets:
                    if (s, p, target) in g:
                        ctx.add(
                            "OWL027",
                            s,
                            f"Negative assertion on {p} with {target} contradicts an asserted triple.",
                            confidence="certain",
                        )


def _irreflexive_usage(ctx: RuleContext) -> None:
    for p in _ordered(_typed(ctx, OWL.IrreflexiveProperty)):
        for s, o in ctx.g.subject_objects(p):
            if s == o:
                ctx.add(
                    "OWL028", s, f"Irreflexive property {p} relates the individual to itself.", confidence="certain"
                )


def _asymmetric_usage(ctx: RuleContext) -> None:
    g = ctx.g
    for p in _ordered(_typed(ctx, OWL.AsymmetricProperty)):
        for s, o in g.subject_objects(p):
            if isinstance(o, Literal):
                continue
            if s == o:
                ctx.add("OWL029", s, f"Asymmetric property {p} relates the individual to itself.", confidence="certain")
            elif str(s) < str(o) and (o, p, s) in g:
                ctx.add(
                    "OWL029",
                    s,
                    f"Asymmetric property {p} is asserted in both directions with {o}.",
                    confidence="certain",
                )


def _illegal_punning(ctx: RuleContext) -> None:
    for node in _ordered(_typed(ctx, OWL.Class) & _typed(ctx, RDFS.Datatype)):
        ctx.add("OWL030", node, "Term is declared both owl:Class and rdfs:Datatype.", confidence="certain")
    both = _typed(ctx, OWL.ObjectProperty) | _typed(ctx, OWL.DatatypeProperty)
    for node in _ordered(_typed(ctx, OWL.AnnotationProperty) & both):
        ctx.add(
            "OWL030",
            node,
            "Term is declared both an annotation property and an object/datatype property.",
            confidence="certain",
        )
