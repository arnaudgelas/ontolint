"""Graph-local governance-metadata rules: GOV004, GOV008-GOV014 and GOV017.

Every rule reads the asserted graph only; nothing is resolved over the network and no policy file is
consulted (thresholds are module constants).  Ontology-level rules fire once per ``owl:Ontology``.
Term-level attribution, date and status rules only flag *stragglers*: they stay silent unless at
least half of the declared local terms already carry the metadata, so ontologies that never record
it are not buried in findings.  Release-oriented rules (GOV011, GOV017) only apply to ontologies that
declare a version.  GOV005, GOV006, GOV007 and GOV015 are deliberately absent: ONT003/ONT004 already
cover licence and version metadata, and no agreed vocabulary exists for the rest.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rdflib import Literal, URIRef
from rdflib.namespace import DC, DCTERMS, OWL, RDF, RDFS, SKOS, XSD
from rdflib.term import Node

from ontolint.context import KINDS
from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity

from .support import META_CREATOR, describing_nodes

if TYPE_CHECKING:
    from .runtime import RuleContext

MIN_CONSISTENCY_TERMS = 4  # Declared local terms needed before a term-level coverage rule can fire.
MAJORITY_FACTOR = 2  # A convention exists when ``MAJORITY_FACTOR * covered >= total``.

_OBO = "http://purl.obolibrary.org/obo/"
_PROV = "http://www.w3.org/ns/prov#"
_PAV = "http://purl.org/pav/"
_SCHEMA = "http://schema.org/"
_FOAF = "http://xmlns.com/foaf/0.1/"
_DOAP = "http://usefulinc.com/ns/doap#"
_DCAT = "http://www.w3.org/ns/dcat#"
_VS = "http://www.w3.org/2003/06/sw-vocab-status/ns#"
_VANN = "http://purl.org/vocab/vann/"
_ADMS = "http://www.w3.org/ns/adms#"
_BIBO = "http://purl.org/ontology/bibo/"

CONTACT_PREDICATES = (
    DCTERMS.publisher,
    DCTERMS.contributor,
    DC.publisher,
    DC.contributor,
    URIRef(_DCAT + "contactPoint"),
    URIRef(_FOAF + "maintainer"),
    URIRef(_FOAF + "mbox"),
    URIRef(_DOAP + "maintainer"),
    URIRef(_SCHEMA + "maintainer"),
)
REPLACEMENT_PREDICATES = (DCTERMS.isReplacedBy, URIRef(_OBO + "IAO_0100001"))
REASON_PREDICATES = (
    RDFS.comment,
    SKOS.historyNote,
    SKOS.changeNote,
    SKOS.editorialNote,
    URIRef(_OBO + "IAO_0000231"),
)
ATTRIBUTION_PREDICATES = (*META_CREATOR, DCTERMS.contributor, DC.contributor, URIRef(_PAV + "createdBy"))
DATE_PREDICATES = (DCTERMS.created, DCTERMS.modified, DCTERMS.issued, DCTERMS.date, DC.date)
STATUS_PREDICATES = (
    URIRef(_VS + "term_status"),
    URIRef(_OBO + "IAO_0000114"),
    URIRef(_ADMS + "status"),
    URIRef(_BIBO + "status"),
)
CHANGE_HISTORY_PREDICATES = (SKOS.changeNote, SKOS.historyNote, URIRef(_VANN + "changes"), OWL.priorVersion)
REVIEW_PREDICATES = (DCTERMS.dateAccepted, URIRef(_SCHEMA + "reviewedBy"), URIRef(_PAV + "curatedBy"))
OBSOLETE_TYPES = (OWL.DeprecatedClass, OWL.DeprecatedProperty)
REFERENCE_ANNOTATIONS = frozenset(
    {
        RDFS.label,
        RDFS.comment,
        RDFS.seeAlso,
        RDFS.isDefinedBy,
        OWL.deprecated,
        DCTERMS.description,
        DCTERMS.isReplacedBy,
        DCTERMS.replaces,
        SKOS.changeNote,
        SKOS.historyNote,
        URIRef(_OBO + "IAO_0100001"),
    }
)
DEFINING_PREDICATES = (
    RDFS.subClassOf,
    RDFS.subPropertyOf,
    RDFS.domain,
    RDFS.range,
    OWL.equivalentClass,
    OWL.equivalentProperty,
    OWL.disjointWith,
    OWL.inverseOf,
)
CORE_NAMESPACES = tuple(str(ns) for ns in (OWL, RDF, RDFS, XSD))

SPECS: tuple[RuleSpec, ...] = (
    RuleSpec(
        "GOV004",
        "GOV",
        "Ontology without a contact or maintainer",
        Severity.INFO,
        "Add a dcterms:publisher, dcat:contactPoint or foaf:maintainer so users know whom to contact.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.ONTOLOGY,
        "governance_metadata",
    ),
    RuleSpec(
        "GOV008",
        "GOV",
        "Deprecated term without a replacement or reason",
        Severity.WARNING,
        "Add dcterms:isReplacedBy or an obsolescence reason (rdfs:comment, skos:historyNote) to deprecated terms.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "governance_metadata",
    ),
    RuleSpec(
        "GOV009",
        "GOV",
        "Term without creator attribution",
        Severity.INFO,
        "Add dcterms:creator or dcterms:contributor to the terms that lack attribution.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "governance_metadata",
    ),
    RuleSpec(
        "GOV010",
        "GOV",
        "Term without creation or modification date",
        Severity.INFO,
        "Add dcterms:created or dcterms:modified to the terms that lack a date.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "governance_metadata",
    ),
    RuleSpec(
        "GOV011",
        "GOV",
        "Versioned ontology without change history",
        Severity.INFO,
        "Record changes with skos:changeNote, vann:changes or owl:priorVersion.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.ONTOLOGY,
        "governance_metadata",
    ),
    RuleSpec(
        "GOV012",
        "GOV",
        "Term without a status",
        Severity.INFO,
        "Add a status such as vs:term_status to the terms that lack one.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "governance_metadata",
    ),
    RuleSpec(
        "GOV013",
        "GOV",
        "Obsolete term still used in axioms",
        Severity.WARNING,
        "Replace references to owl:DeprecatedClass/owl:DeprecatedProperty terms or retire the referencing axiom.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "governance_metadata",
    ),
    RuleSpec(
        "GOV014",
        "GOV",
        "Term defined outside the base namespace",
        Severity.INFO,
        "Move the definition to the owning vocabulary or keep only an import stub for external terms.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "governance_metadata",
    ),
    RuleSpec(
        "GOV017",
        "GOV",
        "Versioned ontology without review or approval metadata",
        Severity.INFO,
        "Record review or approval with dcterms:dateAccepted, schema:reviewedBy or pav:curatedBy.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.ONTOLOGY,
        "governance_metadata",
    ),
)


def run(ctx: RuleContext) -> None:
    """Run the graph-local governance-metadata rules."""
    _contact(ctx)
    _deprecated_without_replacement(ctx)
    _coverage(ctx, "GOV009", ATTRIBUTION_PREDICATES, "creator or contributor attribution")
    _coverage(ctx, "GOV010", DATE_PREDICATES, "creation or modification date")
    _coverage(ctx, "GOV012", STATUS_PREDICATES, "status")
    _release_metadata(ctx)
    _obsolete_usage(ctx)
    _foreign_definitions(ctx)


def _has_any(ctx: RuleContext, subject: Node, predicates: tuple[Node, ...]) -> bool:
    return any((subject, p, None) in ctx.g for p in predicates)


def _is_deprecated(ctx: RuleContext, term: Node) -> bool:
    return (term, OWL.deprecated, Literal(True)) in ctx.g


def _local_terms(ctx: RuleContext) -> list[URIRef]:
    return sorted((t for t in ctx.terms if ctx.local(t)), key=str)


def _contact(ctx: RuleContext) -> None:
    for ont in sorted(ctx.ontologies, key=str):
        if not any(_has_any(ctx, node, CONTACT_PREDICATES) for node in describing_nodes(ctx.g, ont)):
            ctx.add("GOV004", ont, "Ontology names no contact, publisher or maintainer.")


def _deprecated_without_replacement(ctx: RuleContext) -> None:
    for term in _local_terms(ctx):
        if (
            _is_deprecated(ctx, term)
            and not _has_any(ctx, term, REPLACEMENT_PREDICATES)
            and not _has_any(ctx, term, REASON_PREDICATES)
        ):
            ctx.add("GOV008", term, "Deprecated term has neither a replacement nor an obsolescence reason.")


def _coverage(ctx: RuleContext, rule: str, predicates: tuple[Node, ...], what: str) -> None:
    """Flag live local terms missing ``predicates`` once at least half of all local terms have them."""
    terms = [t for t in _local_terms(ctx) if not _is_deprecated(ctx, t)]
    if len(terms) < MIN_CONSISTENCY_TERMS:
        return
    missing = [t for t in terms if not _has_any(ctx, t, predicates)]
    if MAJORITY_FACTOR * (len(terms) - len(missing)) < len(terms):
        return
    for term in missing:
        ctx.add(rule, term, f"Term has no {what}, though most local terms do.")


def _release_metadata(ctx: RuleContext) -> None:
    predicates = ctx.context.predicates
    has_history = any(p in predicates for p in CHANGE_HISTORY_PREDICATES)
    has_review = any(p in predicates for p in REVIEW_PREDICATES)
    for ont in sorted(ctx.ontologies, key=str):
        if not _has_any(ctx, ont, (OWL.versionIRI, OWL.versionInfo)):
            continue
        if not has_history:
            ctx.add("GOV011", ont, "Versioned ontology records no change history.")
        if not has_review:
            ctx.add("GOV017", ont, "Versioned ontology records no review or approval metadata.")


def _obsolete_usage(ctx: RuleContext) -> None:
    g = ctx.g
    types = ctx.context.subjects_by_type
    # owl:deprecated true terms are GOV001's; only the owl:Deprecated* typed remainder is reported here.
    obsolete = {
        t
        for type_ in OBSOLETE_TYPES
        for t in types.get(type_, frozenset())
        if isinstance(t, URIRef) and not _is_deprecated(ctx, t)
    }
    for term in sorted(obsolete, key=str):
        for s, p in g.subject_predicates(term):
            if p in REFERENCE_ANNOTATIONS or s == term or s in obsolete or _is_deprecated(ctx, s):
                continue
            ctx.add("GOV013", s, f"Obsolete term {term} appears as object of {p}.")
        for s, _o in g.subject_objects(term):
            if s not in obsolete and not _is_deprecated(ctx, s):
                ctx.add("GOV013", s, f"Obsolete property {term} used in assertion.")


def _foreign_definitions(ctx: RuleContext) -> None:
    base = ctx.policy.base
    if not base:
        return  # Without an explicit base the "own" namespace cannot be derived soundly.
    declared = {
        s
        for kind in KINDS
        for s in ctx.context.subjects_by_type.get(kind, frozenset())
        if isinstance(s, URIRef) and not ctx.local(s) and not str(s).startswith(CORE_NAMESPACES)
    }
    for term in sorted(declared, key=str):
        if _has_any(ctx, term, DEFINING_PREDICATES):
            ctx.add("GOV014", term, f"Term is defined with axioms outside the base namespace {base}.")
