"""OWL modelling rules: OWL001-OWL011, OWL013-OWL015, DATA001, DATA002.

OWL012 (self-equivalence) is emitted by :mod:`ontolint.rules.classes`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rdflib import Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD
from rdflib.term import Node

from ontolint.context import PROPERTY_TYPES
from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity

from .support import list_items

if TYPE_CHECKING:
    from .runtime import RuleContext


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
        if not domains:
            ctx.add("OWL005", p, "Property has no asserted rdfs:domain.")
        if not ranges:
            ctx.add("OWL006", p, "Property has no asserted rdfs:range.")


def _inverse_and_characteristics(ctx: RuleContext, data_props: set[Node]) -> None:
    g = ctx.g
    for p, q in g.subject_objects(OWL.inverseOf):
        if p == q:
            ctx.add("OWL007", p, "Property declared inverse of itself.", confidence="certain")
        if p != q and (p, RDF.type, OWL.SymmetricProperty) in g:
            ctx.add("OWL008", p, f"Symmetric property also declared inverse of {q}.")
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
    for restriction in ctx.g.subjects(OWL.allValuesFrom, None):
        # allValuesFrom alone is fully valid OWL. Review only.
        if (restriction, OWL.someValuesFrom, None) not in ctx.g:
            ctx.add("OWL011", restriction, "Universal restriction does not imply any property value.")


def _object_property_assertions(ctx: RuleContext, object_props: set[Node]) -> None:
    for p in object_props:
        for s, o in ctx.g.subject_objects(p):
            if isinstance(o, Literal):
                ctx.add("OWL013", s, f"Object property {p} points to literal {o!r}.", confidence="certain")


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
                ):
                    ctx.add("DATA001", s, f"{p} has range {datatype} but value has datatype {o.datatype}.")


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
