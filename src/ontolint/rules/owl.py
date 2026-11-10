"""OWL modelling rules: OWL001-OWL011, OWL013-OWL015, DATA001, DATA002.

OWL012 (self-equivalence) is emitted by :mod:`ontolint.rules.classes`.

All rules read the asserted graph only: no import is followed and nothing is inferred (no
``rdfs:subPropertyOf``, ``rdfs:subClassOf`` or ``owl:inverseOf`` closure).  "Owned" means
``ctx.local`` (:mod:`ontolint.ownership`); "declared" means typed by the named class in an asserted
``rdf:type`` triple.  ``ctx.properties`` is the set of owned IRIs typed ``owl:ObjectProperty``,
``owl:DatatypeProperty``, ``owl:AnnotationProperty`` or ``rdf:Property``; ``ctx.classes`` the owned IRIs
typed ``owl:Class`` or ``rdfs:Class``.  The OWL 2 references are the Structural Specification (SS), its
RDF mapping (MAP) and the Direct Semantics (DS).  Specifications:

* **OWL001.** Every IRI that is the subject or the object of an ``rdfs:subClassOf`` triple, is owned,
  is not in ``ctx.classes`` and is neither ``owl:Thing`` nor ``owl:Nothing``; one finding per IRI.
  Blank nodes (restrictions, class expressions) and foreign IRIs are not reported; an IRI declared
  only as something else (a property, an ``owl:Restriction``) is.  ``owl:equivalentClass`` and
  ``owl:disjointWith`` are not inspected.  Warning, heuristic: SS 5.8.1 requires a class used in an
  axiom to be declared, but tools infer the type and the IRI may be a typo; locality is a judgement.
* **OWL002.** Every owned IRI that is the subject of an ``rdfs:domain`` or ``rdfs:range`` triple and is
  not typed by one of the four property types above (a type such as ``owl:TransitiveProperty`` or
  ``owl:FunctionalProperty`` alone does not count); one finding per IRI and per predicate.  Warning,
  heuristic: SS 5.8.1 requires the declaration, but RDFS tools read the triple anyway.
* **OWL003.** Every node, owned or not, IRI or blank, typed both ``owl:ObjectProperty`` and
  ``owl:DatatypeProperty``.  Annotation-property punning is OWL030's.  Error, certain: SS 5.8.1 forbids
  one IRI to be declared both an object and a data property, so the graph is not OWL 2 DL; the condition
  is exact.
* **OWL004.** Every property in ``ctx.properties`` with more than one distinct ``rdfs:domain`` object,
  and separately every one with more than one distinct ``rdfs:range`` object (named or anonymous: a
  single ``owl:unionOf`` counts as one).  Undeclared and foreign properties are not reported.  Warning,
  certain: the count is exact and DS gives the axioms conjunctive meaning, but the intersection may be
  intended, so the finding asks for review.
* **OWL005 / OWL006.** Every property in ``ctx.properties`` with no ``rdfs:domain`` (``rdfs:range``)
  triple and no ``schema:domainIncludes`` (``schema:rangeIncludes``, ``http`` or ``https``) or
  ``dcam:domainIncludes`` (``dcam:rangeIncludes``) triple.  Excluded: a property with ``owl:deprecated``
  ``true`` or ``1``, and one typed ``owl:AnnotationProperty`` but neither object nor datatype property.
  A domain implied through ``owl:inverseOf`` or a superproperty is not considered.  Info, heuristic: a
  missing domain or range is legal and often deliberate.
* **OWL007.** Every subject of an ``owl:inverseOf`` triple whose object is the same node, declared or
  not.  Warning, certain: ``InverseObjectProperties(p p)`` is valid and means p is symmetric (DS), so the
  triple is exact but probably a mistake or an indirect ``owl:SymmetricProperty``.
* **OWL008.** For every ``owl:inverseOf`` triple between two different nodes, each of the two that is
  typed ``owl:SymmetricProperty`` (the axiom is symmetric, so the symmetric property may be on either
  side); the message names the other one.  A self-inverse is OWL007's.  Warning, heuristic: valid OWL 2,
  but it makes the two properties equivalent, which is rarely intended.
* **OWL009.** Every subject of an ``owl:inverseOf`` triple where either side is typed
  ``owl:DatatypeProperty``, and every node typed ``owl:DatatypeProperty`` and one of
  ``owl:SymmetricProperty``, ``owl:TransitiveProperty``, ``owl:AsymmetricProperty`` or
  ``owl:InverseFunctionalProperty``.  ``owl:FunctionalProperty`` is allowed on data properties;
  ``owl:ReflexiveProperty`` and ``owl:IrreflexiveProperty`` are OWL016's.  Ownership is not checked.
  Warning, certain: these axioms take object property expressions only (SS 9.2, DS Table 6), so the
  graph is not OWL 2 DL.
* **OWL010.** Every subject of an ``owl:propertyChainAxiom`` whose object is a well-formed RDF list of
  exactly one member.  A malformed list and an empty list (``rdf:nil``) are not reported.  Ownership is
  not checked.  Info, certain: SS 9.2.1 and MAP Table 16 require at least two chain members, so the
  axiom is not OWL 2.
* **OWL011.** Every node with an ``owl:allValuesFrom`` value that does not also carry
  ``owl:someValuesFrom``, unless: the filler is a datatype (an XSD IRI, a node typed ``rdfs:Datatype``,
  or one with ``owl:onDatatype`` / ``owl:datatypeComplementOf``); one ``owl:onProperty`` value is
  typed ``owl:DatatypeProperty``; a *sibling* restriction on one of its ``owl:onProperty`` values
  requires a value (``owl:someValuesFrom``, ``owl:hasValue``, ``owl:hasSelf``, or ``owl:minCardinality``,
  ``owl:minQualifiedCardinality``, ``owl:cardinality`` or ``owl:qualifiedCardinality`` of at least 1); or
  the owning term (the first IRI reached upwards through incoming triples, at most eight hops) is a
  foreign IRI.  Siblings are the other ``rdfs:subClassOf`` / ``owl:equivalentClass`` objects of a class
  holding the restriction that way, the other members of an ``owl:intersectionOf`` list holding it, and
  the superclasses and equivalents of the classes defined by that intersection; inherited existentials
  are not followed.  The focus is the owning term; for a restriction no IRI holds, the smallest IRI it
  is ``rdfs:subClassOf`` / ``owl:equivalentClass`` of (a general class axiom), else the blank node
  itself.  Info, heuristic: ``ObjectAllValuesFrom`` is satisfied vacuously by an individual with no
  value (DS Table 4), which is legal but often not what the modeller meant.
* **OWL012.** (in :mod:`ontolint.rules.classes`) Every class in ``ctx.classes`` that is the subject and
  the object of one ``owl:equivalentClass`` triple.  Info, heuristic: a tautology, harmless but noise.
* **OWL013.** Every subject of a triple whose predicate is typed ``owl:ObjectProperty`` (owned or not)
  and whose object is a literal; one finding per subject, property and literal.  Warning, certain: an
  object property assertion needs an individual (DS 2.2: literals are not in the object domain), so the
  graph is not OWL 2 DL.
* **OWL014.** Every subject of a triple whose predicate is typed ``owl:DatatypeProperty`` (owned or
  not) and whose object is an IRI or a blank node.  Warning, certain: the converse of OWL013 (MAP 3.2.5
  maps such a triple to no axiom).
* **OWL015.** Only when an explicit ``base`` is configured: every owned predicate of the graph not in
  ``ctx.properties`` (built-in and foreign predicates are not owned).  Warning, heuristic: SS 5.8.1
  wants the declaration, and locality is the configured base's judgement.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rdflib import BNode, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD
from rdflib.term import Node

from ontolint.context import PROPERTY_TYPES
from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity
from ontolint.ownership import OwnershipMode

from .support import list_items, owning_term, stable_blank_id

if TYPE_CHECKING:
    from collections.abc import Callable

    from rdflib import Graph

    from .runtime import RuleContext

SCHEMA_HTTP = "http://schema.org/"
SCHEMA_HTTPS = "https://schema.org/"
DCAM = "http://purl.org/dc/dcam/"
# Vocabularies that declare a property's domain/range without rdfs:domain/rdfs:range semantics.
DOMAIN_SUBSTITUTES = (
    URIRef(SCHEMA_HTTP + "domainIncludes"),
    URIRef(SCHEMA_HTTPS + "domainIncludes"),
    URIRef(DCAM + "domainIncludes"),
)
RANGE_SUBSTITUTES = (
    URIRef(SCHEMA_HTTP + "rangeIncludes"),
    URIRef(SCHEMA_HTTPS + "rangeIncludes"),
    URIRef(DCAM + "rangeIncludes"),
)
_DATATYPE_EXPRESSIONS = (OWL.onDatatype, OWL.datatypeComplementOf)

# The XSD integer types and their inclusive value bounds (None = unbounded).  Turtle writes every plain
# number as xsd:integer, so a value is checked against a narrower integer range by value, not by name.
_INTEGER_BOUNDS: dict[Node, tuple[int | None, int | None]] = {
    XSD.integer: (None, None),
    XSD.nonNegativeInteger: (0, None),
    XSD.positiveInteger: (1, None),
    XSD.nonPositiveInteger: (None, 0),
    XSD.negativeInteger: (None, -1),
    XSD.long: (-(2**63), 2**63 - 1),
    XSD.int: (-(2**31), 2**31 - 1),
    XSD.short: (-(2**15), 2**15 - 1),
    XSD.byte: (-(2**7), 2**7 - 1),
    XSD.unsignedLong: (0, 2**64 - 1),
    XSD.unsignedInt: (0, 2**32 - 1),
    XSD.unsignedShort: (0, 2**16 - 1),
    XSD.unsignedByte: (0, 2**8 - 1),
}


def is_deprecated(g: Graph, term: Node) -> bool:
    """Return whether ``term`` carries ``owl:deprecated true``."""
    return any(
        isinstance(o, Literal) and str(o).strip().lower() in ("true", "1") for o in g.objects(term, OWL.deprecated)
    )


def namespace_of(iri: object) -> str:
    """Return the IRI up to and including the last ``#`` or ``/``."""
    text = str(iri)
    cut = max(text.rfind("#"), text.rfind("/"))
    return text[: cut + 1] if cut >= 0 else text


def owned_checker(ctx: RuleContext) -> Callable[[object], bool]:
    """Return a predicate telling whether an IRI is a term the linted ontology itself defines or could define.

    Without an explicit base or derivable ontology namespace every non-built-in IRI counts as owned, which
    would make foreign targets (``foaf:Person``) look local; the predicate then also requires the IRI to sit
    in a namespace that holds a declared term of the file.
    """
    if ctx.context.ownership.mode is not OwnershipMode.ALL:
        return ctx.local
    namespaces = {namespace_of(t) for t in ctx.terms}
    return lambda node: ctx.local(node) and namespace_of(node) in namespaces


CHARACTERISTIC_TYPES = (
    OWL.SymmetricProperty,
    OWL.TransitiveProperty,
    OWL.AsymmetricProperty,
    OWL.InverseFunctionalProperty,
)


SPECS: tuple[RuleSpec, ...] = (
    RuleSpec(
        "OWL001",
        "OWL",
        "Undeclared class in subclass axiom",
        Severity.WARNING,
        "Explicitly declare local classes used in class axioms.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "owl",
    ),
    RuleSpec(
        "OWL002",
        "OWL",
        "Undeclared property in domain or range axiom",
        Severity.WARNING,
        "Explicitly declare local properties used in schema axioms.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "owl",
    ),
    RuleSpec(
        "OWL003",
        "OWL",
        "Property typed as both object and datatype property",
        Severity.ERROR,
        "Do not simultaneously declare a property as both owl:ObjectProperty and owl:DatatypeProperty.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "owl",
    ),
    RuleSpec(
        "OWL004",
        "OWL",
        "Multiple domains or ranges mean intersection",
        Severity.WARNING,
        "Review conjunction semantics of multiple rdfs:domain/rdfs:range; use owl:unionOf if intended.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "owl",
    ),
    RuleSpec(
        "OWL005",
        "OWL",
        "Property without domain",
        Severity.INFO,
        "Consider declaring domain or explaining why a global domain is inappropriate.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "owl",
    ),
    RuleSpec(
        "OWL006",
        "OWL",
        "Property without range",
        Severity.INFO,
        "Consider declaring range or explaining why a global range is inappropriate.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "owl",
    ),
    RuleSpec(
        "OWL007",
        "OWL",
        "Property declared inverse of itself",
        Severity.WARNING,
        "Replace self-inverse modeling with owl:SymmetricProperty when this is intentional.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "owl",
    ),
    RuleSpec(
        "OWL008",
        "OWL",
        "Symmetric property also declared with an inverse",
        Severity.WARNING,
        "Review redundant or unintended inverse axioms on symmetric properties.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "owl",
    ),
    RuleSpec(
        "OWL009",
        "OWL",
        "Datatype property with object-property characteristic",
        Severity.WARNING,
        "Use object properties for owl:inverseOf and symmetric/transitive property semantics.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "owl",
    ),
    RuleSpec(
        "OWL010",
        "OWL",
        "Single-operand property chain",
        Severity.INFO,
        "Review an owl:propertyChainAxiom whose RDF list has only one element.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "owl",
    ),
    RuleSpec(
        "OWL011",
        "OWL",
        "Universal restriction without existence",
        Severity.INFO,
        "Check intended allValuesFrom semantics; it does not imply existence of a value.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "owl",
    ),
    RuleSpec(
        "OWL013",
        "OWL",
        "Object property asserted with a literal value",
        Severity.WARNING,
        "An object-property assertion should point to a resource, not a literal.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "owl",
    ),
    RuleSpec(
        "OWL014",
        "OWL",
        "Datatype property asserted with a resource value",
        Severity.WARNING,
        "A datatype-property assertion should point to a literal.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "owl",
    ),
    RuleSpec(
        "OWL015",
        "OWL",
        "Undeclared local predicate",
        Severity.WARNING,
        "Declare a local predicate as a property (or exclude it from schema-only policy).",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "owl",
    ),
    RuleSpec(
        "DATA001",
        "DATA",
        "Value datatype conflicts with property range",
        Severity.WARNING,
        "Check a property assertion for range/type confusion.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "owl",
    ),
    RuleSpec(
        "DATA002",
        "DATA",
        "Property usage conflicts with subject type",
        Severity.WARNING,
        "Check a property assertion for datatype/object-property confusion.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "owl",
    ),
)


def run(ctx: RuleContext) -> None:
    """Run all OWL rules."""
    subjects_by_type = ctx.context.subjects_by_type
    object_props = set(subjects_by_type.get(OWL.ObjectProperty, frozenset()))
    data_props = set(subjects_by_type.get(OWL.DatatypeProperty, frozenset()))
    for p in object_props & data_props:
        ctx.add("OWL003", p, "Property is typed as both object and datatype property.", confidence="certain")
    _domains_and_ranges(ctx)
    _inverse_and_characteristics(ctx, data_props)
    _property_chains(ctx)
    _universal_restrictions(ctx)
    _object_property_assertions(ctx, object_props)
    _datatype_property_assertions(ctx, data_props)
    _domain_disjointness(ctx)
    _undeclared_terms(ctx)


def _domains_and_ranges(ctx: RuleContext) -> None:
    for p in ctx.properties:
        domains = set(ctx.context.domains_by_property.get(p, frozenset()))
        ranges = set(ctx.context.ranges_by_property.get(p, frozenset()))
        if len(domains) > 1:
            ctx.add(
                "OWL004",
                p,
                f"Multiple asserted domains ({len(domains)}) mean intersection, not union.",
                confidence="certain",
            )
        if len(ranges) > 1:
            ctx.add(
                "OWL004",
                p,
                f"Multiple asserted ranges ({len(ranges)}) mean intersection, not union.",
                confidence="certain",
            )
        if is_deprecated(ctx.g, p) or _annotation_only(ctx.g, p):
            continue
        if not domains and not any((p, q, None) in ctx.g for q in DOMAIN_SUBSTITUTES):
            ctx.add("OWL005", p, "Property has no asserted rdfs:domain.")
        if not ranges and not any((p, q, None) in ctx.g for q in RANGE_SUBSTITUTES):
            ctx.add("OWL006", p, "Property has no asserted rdfs:range.")


def _annotation_only(g: Graph, p: Node) -> bool:
    """Annotation properties conventionally carry no domain or range."""
    return (p, RDF.type, OWL.AnnotationProperty) in g and not any(
        (p, RDF.type, t) in g for t in (OWL.ObjectProperty, OWL.DatatypeProperty)
    )


def _inverse_and_characteristics(ctx: RuleContext, data_props: set[Node]) -> None:
    g = ctx.g
    for p, q in g.subject_objects(OWL.inverseOf):
        if p == q:
            ctx.add("OWL007", p, "Property declared inverse of itself.", confidence="certain")
        # InverseObjectProperties is symmetric: "q owl:inverseOf p" gives the symmetric p an inverse too.
        for symmetric, other in ((p, q), (q, p)):
            if p != q and (symmetric, RDF.type, OWL.SymmetricProperty) in g:
                ctx.add("OWL008", symmetric, f"Symmetric property also declared inverse of {other}.")
        if p in data_props or q in data_props:
            ctx.add("OWL009", p, "owl:inverseOf involves a datatype property.", confidence="certain")
    for t in CHARACTERISTIC_TYPES:
        for p in g.subjects(RDF.type, t):
            if p in data_props:
                ctx.add("OWL009", p, f"Datatype property declared {t}.", confidence="certain")


def _property_chains(ctx: RuleContext) -> None:
    for p, chain in ctx.g.subject_objects(OWL.propertyChainAxiom):
        items = list_items(ctx.g, chain)
        if items is not None and len(items) == 1:
            ctx.add("OWL010", p, "Property-chain axiom has one operand.", confidence="certain")


def _universal_restrictions(ctx: RuleContext) -> None:
    g = ctx.g
    for restriction, filler in sorted(g.subject_objects(OWL.allValuesFrom), key=lambda t: (str(t[0]), str(t[1]))):
        # allValuesFrom alone is fully valid OWL. Review only.
        if (restriction, OWL.someValuesFrom, None) in g:
            continue
        # A malformed restriction may carry several owl:onProperty values: sort them by a label-free name so the
        # message depends neither on triple order nor on the parser's blank-node labels.
        on_properties = sorted(g.objects(restriction, OWL.onProperty), key=lambda p: _property_name(g, p))
        if _is_datatype(g, filler) or any((p, RDF.type, OWL.DatatypeProperty) in g for p in on_properties):
            continue  # "all values are xsd:gDay" is the idiomatic way to type a datatype property.
        if _existence_alongside(g, restriction, set(on_properties)):
            continue  # a closure axiom: "some p B" and "only p B" on the same class

        owner = owning_term(g, restriction)
        if isinstance(owner, URIRef) and not ctx.local(owner):
            continue  # an axiom of an imported or merged vocabulary (BFO, ...), not of the linted ontology
        on = f" on {', '.join(_property_name(g, p) for p in on_properties)}" if on_properties else ""
        if owner == restriction:
            # A general class axiom ("[ owl:allValuesFrom ... ] rdfs:subClassOf ex:X"): no term uses it, so
            # report it on the named class it is an axiom about, with the property, instead of a bare blank node.
            target = _gci_class(g, restriction)
            if target is not None:
                message = f"Universal restriction{on} in a general class axiom about {target} does not imply any value."
                ctx.add("OWL011", target, message)
                continue
            on = ""  # unchanged wording for a free-standing restriction
        ctx.add("OWL011", owner, f"Universal restriction{on} does not imply any property value.")


_CLASS_AXIOMS = (RDFS.subClassOf, OWL.equivalentClass)
_MIN_CARDINALITIES = (OWL.minCardinality, OWL.minQualifiedCardinality, OWL.cardinality, OWL.qualifiedCardinality)


def _intersection_lists(g: Graph, node: Node) -> list[tuple[Node, list[Node]]]:
    """The ``owl:intersectionOf`` expressions that list ``node`` as a member, with their members."""
    found: list[tuple[Node, list[Node]]] = []
    for cell in g.subjects(RDF.first, node):
        head, seen = cell, {cell}
        while (parent := next(g.subjects(RDF.rest, head), None)) is not None and parent not in seen:
            seen.add(parent)
            head = parent
        for expression in g.subjects(OWL.intersectionOf, head):
            members = list_items(g, head)
            if members is not None:
                found.append((expression, members))
    return found


def _conjuncts(g: Graph, restriction: Node) -> set[Node]:
    """Class expressions that hold for the same instances as ``restriction``: its siblings in one class.

    The siblings are the other superclasses and equivalents of a class that has ``restriction`` as a
    superclass or equivalent, and the other members of an ``owl:intersectionOf`` that lists it (with the
    superclasses and equivalents of the classes defined by that intersection).
    """
    holders = {h for p in _CLASS_AXIOMS for h in g.subjects(p, restriction)}
    conjuncts: set[Node] = set()
    for expression, members in _intersection_lists(g, restriction):
        conjuncts.update(members)
        holders.update(h for p in _CLASS_AXIOMS for h in g.subjects(p, expression))
    for holder in holders:
        conjuncts.update(o for p in _CLASS_AXIOMS for o in g.objects(holder, p))
    for node in list(conjuncts):
        for listed in (list_items(g, head) for head in g.objects(node, OWL.intersectionOf)):
            conjuncts.update(listed or ())
    conjuncts.discard(restriction)
    return conjuncts


def _existential(g: Graph, node: Node) -> bool:
    """Whether the restriction ``node`` requires at least one value (some, hasValue, hasSelf, min >= 1)."""
    if any((node, p, None) in g for p in (OWL.someValuesFrom, OWL.hasValue, OWL.hasSelf)):
        return True
    for p in _MIN_CARDINALITIES:
        for value in g.objects(node, p):
            try:
                if isinstance(value, Literal) and int(str(value).strip()) >= 1:
                    return True
            except ValueError:
                continue
    return False


def _existence_alongside(g: Graph, restriction: Node, on_properties: set[Node]) -> bool:
    """Whether a sibling restriction of ``restriction`` on one of its properties requires a value."""
    return bool(on_properties) and any(
        _existential(g, sibling) and any(p in on_properties for p in g.objects(sibling, OWL.onProperty))
        for sibling in _conjuncts(g, restriction)
    )


def _gci_class(g: Graph, restriction: Node) -> URIRef | None:
    """The named class a general class axiom on ``restriction`` is about, if there is one."""
    named = sorted(
        o for p in (RDFS.subClassOf, OWL.equivalentClass) for o in g.objects(restriction, p) if isinstance(o, URIRef)
    )
    return named[0] if named else None


def _property_name(g: Graph, node: Node) -> str:
    return stable_blank_id(g, node) if isinstance(node, BNode) else str(node)


def _is_datatype(g: Graph, filler: Node) -> bool:
    if isinstance(filler, URIRef) and str(filler).startswith(str(XSD)):
        return True
    return (filler, RDF.type, RDFS.Datatype) in g or any((filler, p, None) in g for p in _DATATYPE_EXPRESSIONS)


def _object_property_assertions(ctx: RuleContext, object_props: set[Node]) -> None:
    for p in object_props:
        for s, o in ctx.g.subject_objects(p):
            if isinstance(o, Literal):
                ctx.add("OWL013", s, f"Object property {p} points to literal {o.n3()}.", confidence="certain")


def _datatype_property_assertions(ctx: RuleContext, data_props: set[Node]) -> None:
    for p in data_props:
        expected = set(ctx.context.ranges_by_property.get(p, frozenset()))
        for s, o in ctx.g.subject_objects(p):
            if not isinstance(o, Literal):
                ctx.add("OWL014", s, f"Datatype property {p} points to resource {o}.", confidence="certain")
            elif len(expected) == 1:
                datatype = next(iter(expected))
                if (
                    str(datatype).startswith(str(XSD))
                    and o.datatype != datatype
                    and not (datatype == XSD.string and o.datatype in (None, RDF.langString))
                    and not _in_value_space(o, datatype)
                ):
                    ctx.add("DATA001", s, f"{p} has range {datatype} but value has datatype {o.datatype}.")


def _in_value_space(value: Literal, datatype: Node) -> bool:
    """Whether an integer-typed ``value`` lies in the value space of the integer or decimal ``datatype``.

    OWL 2 types data by value: ``1`` (an ``xsd:integer`` in Turtle) is a valid ``xsd:positiveInteger``,
    and every integer is an ``xsd:decimal``.  Any other pair of differing datatypes is left to DATA001.
    """
    if value.datatype not in _INTEGER_BOUNDS:
        return False
    try:
        number = int(str(value).strip())
    except ValueError:  # an ill-typed lexical form, such as "abc"^^xsd:integer
        return False
    if datatype == XSD.decimal:
        return True
    if datatype not in _INTEGER_BOUNDS:
        return False
    low, high = _INTEGER_BOUNDS[datatype]
    return (low is None or number >= low) and (high is None or number <= high)


def _domain_disjointness(ctx: RuleContext) -> None:
    g = ctx.g
    for p in ctx.properties:
        for domain in g.objects(p, RDFS.domain):
            for s in ctx.context.subjects_by_predicate.get(p, frozenset()):
                for actual in ctx.context.types_by_subject.get(s, frozenset()):
                    if (actual, OWL.disjointWith, domain) in g or (domain, OWL.disjointWith, actual) in g:
                        ctx.add(
                            "DATA002",
                            s,
                            f"Usage of {p} infers {domain} but subject is explicitly typed {actual}, "
                            "declared disjoint.",
                        )


def _undeclared_terms(ctx: RuleContext) -> None:
    g = ctx.g
    for usage, indexed in (
        ("rdfs:domain", ctx.context.domains_by_property),
        ("rdfs:range", ctx.context.ranges_by_property),
    ):
        for p in indexed:
            if isinstance(p, URIRef) and ctx.local(p) and not any((p, RDF.type, t) in g for t in PROPERTY_TYPES):
                ctx.add("OWL002", p, f"Predicate used with {usage} but not declared property.")
    for c in set(g.subjects(RDFS.subClassOf, None)) | set(g.objects(None, RDFS.subClassOf)):
        if isinstance(c, URIRef) and ctx.local(c) and c not in ctx.classes and c not in (OWL.Thing, OWL.Nothing):
            ctx.add("OWL001", c, "URI used in subclass axiom but not explicitly declared a class.")
    # Treat undeclared predicates as suspicious only within explicit base namespaces.
    if ctx.policy.base:
        for p in ctx.context.predicates:
            if ctx.local(p) and p not in ctx.properties:
                ctx.add("OWL015", p, "Local predicate is not explicitly declared as a property.")
