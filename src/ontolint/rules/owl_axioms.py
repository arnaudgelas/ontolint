"""OWL axiom and property-characteristic rules: OWL016-OWL030.

All rules are asserted-graph checks; nothing is entailed and no reasoner is involved.  Subproperty,
subclass and equivalence relations are read as asserted, never closed transitively.  A property's kind
is read from its explicit ``rdf:type owl:ObjectProperty`` / ``owl:DatatypeProperty`` only (a
characteristic such as ``owl:TransitiveProperty`` does not make it an object property).  No rule is
restricted to owned terms: every subject of the graph is checked, imported or not.  Every finding is
``certain`` except OWL023's.  Their specifications:

* **OWL016.** A node typed ``owl:DatatypeProperty`` and ``owl:ReflexiveProperty`` or
  ``owl:IrreflexiveProperty``; one finding per characteristic.  The other object-only characteristics
  (symmetric, asymmetric, transitive, inverse-functional) on a datatype property are OWL009's.
  *Error:* (ir)reflexivity axioms take an object property expression, so the graph is not OWL 2 DL.
* **OWL017.** A node typed both ``owl:SymmetricProperty`` and ``owl:AsymmetricProperty``.
  *Error:* consistent, but the property can hold between no individuals (an unsatisfiable property).
* **OWL018.** A node typed ``owl:ReflexiveProperty`` and ``owl:IrreflexiveProperty``, or
  ``owl:ReflexiveProperty`` and ``owl:AsymmetricProperty`` (asymmetry implies irreflexivity); one
  finding per pair.  Reflexive with symmetric, and irreflexive with asymmetric, are compatible.
  *Error:* every individual must then relate to itself and must not, so the ontology is inconsistent.
* **OWL019.** A node typed ``owl:FunctionalProperty``, ``owl:InverseFunctionalProperty``,
  ``owl:IrreflexiveProperty`` or ``owl:AsymmetricProperty`` that is itself typed
  ``owl:TransitiveProperty`` or is the subject of an ``owl:propertyChainAxiom`` whose well-formed list
  has at least two operands; one finding per characteristic.  Non-simplicity is not inherited: a
  property with a transitive or chain-defined sub-property, sub-property inverse or equivalent
  (non-simple by OWL 2 Structural Specification section 11.1) is not reported, nor are non-simple
  properties in cardinality, ``owl:hasSelf`` or property-disjointness axioms.  A one-operand chain is
  OWL010's.  *Error:* violates the OWL 2 DL global restriction on simple properties.
* **OWL020.** A strongly connected component of two or more IRIs in the asserted
  ``rdfs:subPropertyOf`` graph; one finding per component, on its lexically first member, naming all of
  them.  Self-loops, edges to or from blank nodes, and ``owl:equivalentProperty`` are ignored.
  *Warning:* valid OWL; the cycle only entails that its members are equivalent, which is usually
  unintended.
* **OWL021.** A triple ``p rdfs:subPropertyOf q`` or ``p owl:equivalentProperty q`` where one side is
  typed ``owl:ObjectProperty`` and not ``owl:DatatypeProperty`` and the other the reverse; reported on
  ``p``.  An untyped side, or one typed both kinds (OWL003's), is not reported.
  *Error:* sub- and equivalent-property axioms relate properties of one kind; not OWL 2 DL.
* **OWL022.** An ``rdfs:range`` IRI that conflicts with the kind of a property typed one kind only.  For
  an object property: a datatype, that is an ``xsd:`` IRI, ``rdfs:Literal``, ``rdf:langString``,
  ``rdf:XMLLiteral``, ``rdf:HTML``, ``rdf:PlainLiteral``, ``owl:real``, ``owl:rational`` or any node typed
  ``rdfs:Datatype``.  For a datatype property: ``owl:Thing`` or a node typed ``owl:Class``.  A range
  typed both ``owl:Class`` and ``rdfs:Datatype`` (OWL030's) and a blank-node range are not reported.
  *Error:* an object property's range is a class expression and a datatype property's a data range;
  not OWL 2 DL.
* **OWL023.** An IRI related by ``owl:inverseOf``, in either direction, to two or more other IRIs; one
  finding per such property.  Self-inverse and blank-node inverses are ignored (OWL007 has the former).
  *Warning, heuristic:* valid OWL; the inverses are entailed equivalent, which may be intended.
* **OWL024.** Two properties declared disjoint, by ``owl:propertyDisjointWith`` or as members of one
  ``owl:AllDisjointProperties`` list, that are also related by an asserted ``rdfs:subPropertyOf`` or
  ``owl:equivalentProperty`` in either direction, or a property declared disjoint with itself
  (including a member repeated in a group).  One finding per unordered pair, on its lexically first
  member.  Pairs involving ``owl:bottomObjectProperty`` or ``owl:bottomDataProperty`` are skipped, as is
  a group whose ``owl:members`` list is malformed or longer than 200 members.
  *Error:* the sub-property (or both equivalents) can hold between nothing: an unsatisfiable property.
* **OWL025.** The same as OWL024 for classes: ``owl:disjointWith`` and ``owl:AllDisjointClasses``
  against ``rdfs:subClassOf`` and ``owl:equivalentClass``, skipping pairs with ``owl:Nothing``.  An
  intersection of disjoint classes is a class expression, OWL043's; a repeated group member is also
  OWL045's.  *Error:* the subclass (or both equivalents) is unsatisfiable.
* **OWL026.** A triple ``a owl:differentFrom a``, or ``a owl:differentFrom b`` with ``a owl:sameAs b``
  or ``b owl:sameAs a``; one finding per unordered pair.  ``owl:AllDifferent`` and ``owl:sameAs``
  chains are OWL044's.  *Error:* the ontology is inconsistent.
* **OWL027.** An ``owl:NegativePropertyAssertion`` whose ``owl:sourceIndividual``,
  ``owl:assertionProperty`` and ``owl:targetIndividual`` or ``owl:targetValue`` form a triple that is
  asserted; reported on the source.  Literals match as RDF terms after RDFLib's lexical normalisation
  (``"01"^^xsd:integer`` matches ``"1"^^xsd:integer``; ``"1.0"^^xsd:decimal`` does not), and an
  incomplete assertion is skipped.  *Error:* inconsistent.
* **OWL028.** A triple ``a p a`` where ``p`` is typed ``owl:IrreflexiveProperty``; reported on ``a``.
  *Error:* inconsistent.
* **OWL029.** For ``p`` typed ``owl:AsymmetricProperty``: a triple ``a p a``, or both ``a p b`` and
  ``b p a`` (reported once, on the lexically lesser node).  Literal objects are ignored.
  *Error:* inconsistent.
* **OWL030.** A node typed both ``owl:Class`` and ``rdfs:Datatype``, or ``owl:AnnotationProperty`` and
  ``owl:ObjectProperty`` or ``owl:DatatypeProperty``.  Object with datatype property is OWL003's; class
  with property or individual punning is legal and not reported.  *Error:* breaks the OWL 2 typing
  constraints (Structural Specification section 5.8.1); not OWL 2 DL.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD
from rdflib.term import Node

from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity

from .support import LITERAL_RANGES, list_items

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

# Empty by definition: disjointness with them, or subsumption by them, is no conflict (OWL024/OWL025).
BOTTOM_PROPERTIES = frozenset({OWL.bottomObjectProperty, OWL.bottomDataProperty})
BOTTOM_CLASSES = frozenset({OWL.Nothing})
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
            ctx.add("OWL016", p, f"Datatype property is declared {type_}.", confidence="certain", subject=(type_,))


def _contradictory_characteristics(ctx: RuleContext) -> None:
    symmetric, asymmetric = _typed(ctx, OWL.SymmetricProperty), _typed(ctx, OWL.AsymmetricProperty)
    reflexive, irreflexive = _typed(ctx, OWL.ReflexiveProperty), _typed(ctx, OWL.IrreflexiveProperty)
    for p in _ordered(symmetric & asymmetric):
        ctx.add("OWL017", p, "Property is declared both symmetric and asymmetric.", confidence="certain")
    for p in _ordered(reflexive & irreflexive):
        ctx.add(
            "OWL018",
            p,
            "Property is declared both reflexive and irreflexive.",
            confidence="certain",
            subject=(OWL.ReflexiveProperty, OWL.IrreflexiveProperty),
        )
    for p in _ordered(reflexive & asymmetric):
        ctx.add(
            "OWL018",
            p,
            "Property is declared both reflexive and asymmetric.",
            confidence="certain",
            subject=(OWL.ReflexiveProperty, OWL.AsymmetricProperty),
        )


def _property_iri(g: Graph, node: Node) -> URIRef | None:
    """The IRI a property expression is about: an IRI itself, or ``x`` for a blank ``[ owl:inverseOf x ]``."""
    if isinstance(node, URIRef):
        return node
    if isinstance(node, BNode):
        inverses = list(g.objects(node, OWL.inverseOf))
        if len(inverses) == 1 and isinstance(inverses[0], URIRef):
            return inverses[0]
    return None


def _chained(g: Graph) -> set[Node]:
    """Subjects of an ``owl:propertyChainAxiom`` whose well-formed list has two or more operands."""
    chained: set[Node] = set()
    for p, chain in g.subject_objects(OWL.propertyChainAxiom):
        items = list_items(g, chain)
        if items is not None and len(items) >= MIN_CHAIN_LENGTH:
            chained.add(p)
    return chained


def _composites(ctx: RuleContext, chained: set[Node]) -> dict[URIRef, str]:
    """Composite properties (SS 11.1), by IRI, with what makes each composite, as the messages word it.

    An expression is composite when it or its inverse is transitive or the super-property of a chain of two or
    more properties, or when it is ``owl:topObjectProperty`` or ``owl:bottomObjectProperty``.
    """
    composite: dict[URIRef, str] = {OWL.topObjectProperty: "the top object property"}
    composite[OWL.bottomObjectProperty] = "the bottom object property"
    for kind, nodes in (("defined by a property chain", chained), ("transitive", _typed(ctx, OWL.TransitiveProperty))):
        for node in nodes:
            iri = _property_iri(ctx.g, node)
            if iri is not None:
                composite[iri] = kind  # transitive, written last, wins over a chain
    return composite


def _non_simple(ctx: RuleContext, chained: set[Node]) -> dict[URIRef, tuple[URIRef, str]]:
    """Every non-simple property (OWL 2 SS 11.1), by IRI, with a composite property it is reached from and its kind.

    SS 11.1 defines ``→`` over object property expressions: ``OPE1 → OPE2`` for ``SubObjectPropertyOf(OPE1
    OPE2)``, both ways for ``EquivalentObjectProperties``, ``OPE1 → INV(OPE2)`` and ``INV(OPE2) → OPE1`` for
    ``InverseObjectProperties(OPE1 OPE2)``, ``OPE → INV(OPE)`` for ``SymmetricObjectProperty``, and with every
    ``A → B`` also ``INV(A) → INV(B)``.  A property is non-simple when a composite expression reaches it through
    ``→*``.  A property and its inverse are composite together, and every edge comes with its inverse edge, so
    one of them is reached exactly when the other is: the walk can drop the direction of inversion and run over
    IRIs, where the inverse axiom links its two IRIs both ways and the symmetric one adds nothing.  A blank
    ``[ owl:inverseOf x ]`` stands for ``x``.  The walk is iterative and expands each IRI once, from the sorted
    composites, so a cycle ends it and the witness is the first composite that reaches the property.
    """
    g = ctx.g
    edges: dict[URIRef, set[URIRef]] = {}
    for predicate, both_ways in (
        (RDFS.subPropertyOf, False),
        (OWL.equivalentProperty, True),
        (OWL.inverseOf, True),
    ):
        for s, o in g.subject_objects(predicate):
            if predicate == OWL.inverseOf and not (isinstance(s, URIRef) and isinstance(o, URIRef)):
                continue  # a blank subject is an inverse expression, not an InverseObjectProperties axiom
            sub, sup = _property_iri(g, s), _property_iri(g, o)
            if sub is None or sup is None:
                continue
            edges.setdefault(sub, set()).add(sup)
            if both_ways:
                edges.setdefault(sup, set()).add(sub)
    composites = _composites(ctx, chained)
    reached: dict[URIRef, tuple[URIRef, str]] = {iri: (iri, kind) for iri, kind in composites.items()}
    for root in sorted(composites, key=str):
        stack = [root]
        while stack:
            for nxt in sorted(edges.get(stack.pop(), ()), key=str):
                if nxt not in reached:
                    reached[nxt] = reached[root]
                    stack.append(nxt)
    return reached


def _non_simple_properties(ctx: RuleContext) -> None:
    transitive = _typed(ctx, OWL.TransitiveProperty)
    chained = _chained(ctx.g)
    non_simple = _non_simple(ctx, chained)
    data_only = _data_only(ctx)  # outside the object property hierarchy
    for label, type_ in SIMPLE_ONLY_CHARACTERISTICS:
        for p in _ordered(_typed(ctx, type_)):
            if p in transitive or p in chained:
                reason = "transitive" if p in transitive else "defined by a property chain"
                message = f"Property is {reason} (non-simple) but declared {label}."
            elif isinstance(p, URIRef) and p in non_simple and p not in data_only:
                witness, kind = non_simple[p]
                if witness == p:
                    message = f"Property is {kind} (non-simple) but declared {label}."
                else:
                    message = f"Property is non-simple through {witness}, which is {kind}, but declared {label}."
            else:
                continue
            ctx.add("OWL019", p, message, confidence="certain", subject=(type_,))


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
        ctx.add("OWL020", component[0], f"rdfs:subPropertyOf cycle among: {names}.", confidence="certain", subject=())


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
                    subject=(predicate, q),
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
                ctx.add("OWL022", p, f"Object property has datatype range {r}.", confidence="certain", subject=(r,))
    for p in _ordered(_data_only(ctx)):
        for r in _ordered(ranges.get(p, frozenset())):
            is_class = r == OWL.Thing or OWL.Class in _types_of(ctx, r)
            if isinstance(r, URIRef) and is_class and RDFS.Datatype not in _types_of(ctx, r):
                ctx.add("OWL022", p, f"Datatype property has class range {r}.", confidence="certain", subject=(r,))


def _multiple_inverses(ctx: RuleContext) -> None:
    inverses: dict[Node, set[Node]] = {}
    for p, q in ctx.g.subject_objects(OWL.inverseOf):
        if p != q and isinstance(p, URIRef) and isinstance(q, URIRef):
            inverses.setdefault(p, set()).add(q)
            inverses.setdefault(q, set()).add(p)
    for p in _ordered(set(inverses)):
        if len(inverses[p]) > 1:
            names = ", ".join(str(n) for n in _ordered(inverses[p]))
            ctx.add("OWL023", p, f"Property has several distinct inverses: {names}.", subject=())


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
    bottoms = BOTTOM_PROPERTIES if kind == "property" else BOTTOM_CLASSES
    seen: set[frozenset[Node]] = set()
    for a, b in sorted(pairs, key=lambda pair: (str(pair[0]), str(pair[1]))):
        key = frozenset((a, b))
        if key in seen or key & bottoms:
            continue
        seen.add(key)
        if a == b:
            relation = "is declared disjoint with itself"
        elif any((x, predicate, y) in g for predicate in (sub_predicate, equiv_predicate) for x, y in ((a, b), (b, a))):
            relation = f"is disjoint with {b} but also asserted a sub{kind} of or equivalent to it"
        else:
            continue
        ctx.add(code, a, f"The {kind} {relation}.", confidence="certain", subject=(b,))


def _same_and_different(ctx: RuleContext) -> None:
    g = ctx.g
    seen: set[frozenset[Node]] = set()
    for a, b in sorted(g.subject_objects(OWL.differentFrom), key=lambda pair: (str(pair[0]), str(pair[1]))):
        key = frozenset((a, b))
        if key in seen:
            continue
        seen.add(key)
        if a == b:
            ctx.add("OWL026", a, "Individual is declared different from itself.", confidence="certain", subject=(a,))
        elif (a, OWL.sameAs, b) in g or (b, OWL.sameAs, a) in g:
            ctx.add(
                "OWL026",
                a,
                f"Individual is both owl:sameAs and owl:differentFrom {b}.",
                confidence="certain",
                subject=(b,),
            )


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
                            subject=(p, target),
                        )


def _irreflexive_usage(ctx: RuleContext) -> None:
    for p in _ordered(_typed(ctx, OWL.IrreflexiveProperty)):
        for s, o in ctx.g.subject_objects(p):
            if s == o:
                ctx.add(
                    "OWL028",
                    s,
                    f"Irreflexive property {p} relates the individual to itself.",
                    confidence="certain",
                    subject=(p,),
                )


def _asymmetric_usage(ctx: RuleContext) -> None:
    g = ctx.g
    for p in _ordered(_typed(ctx, OWL.AsymmetricProperty)):
        for s, o in g.subject_objects(p):
            if isinstance(o, Literal):
                continue
            if s == o:
                ctx.add(
                    "OWL029",
                    s,
                    f"Asymmetric property {p} relates the individual to itself.",
                    confidence="certain",
                    subject=(p,),
                )
            elif str(s) < str(o) and (o, p, s) in g:
                ctx.add(
                    "OWL029",
                    s,
                    f"Asymmetric property {p} is asserted in both directions with {o}.",
                    confidence="certain",
                    subject=(p, o),
                )


def _illegal_punning(ctx: RuleContext) -> None:
    for node in _ordered(_typed(ctx, OWL.Class) & _typed(ctx, RDFS.Datatype)):
        ctx.add(
            "OWL030",
            node,
            "Term is declared both owl:Class and rdfs:Datatype.",
            confidence="certain",
            subject=(OWL.Class, RDFS.Datatype),
        )
    both = _typed(ctx, OWL.ObjectProperty) | _typed(ctx, OWL.DatatypeProperty)
    for node in _ordered(_typed(ctx, OWL.AnnotationProperty) & both):
        ctx.add(
            "OWL030",
            node,
            "Term is declared both an annotation property and an object/datatype property.",
            confidence="certain",
            subject=(OWL.AnnotationProperty,),
        )
