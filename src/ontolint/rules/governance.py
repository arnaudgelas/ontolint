"""Governance rules for deprecation, equivalence targets, and imports: GOV001-GOV003."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rdflib import Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, RDFS

from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity

if TYPE_CHECKING:
    from .runtime import RuleContext


SPECS: tuple[RuleSpec, ...] = (
    RuleSpec(
        "GOV001",
        "GOV",
        "Reference to a deprecated term",
        Severity.WARNING,
        "Migrate non-annotation references to deprecated terms or justify them.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "governance",
    ),
    RuleSpec(
        "GOV002",
        "GOV",
        "Unpinned or invalid ontology import",
        Severity.INFO,
        "Pin or resolve imported ontology versions in an explicit import manifest.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.ONTOLOGY,
        "governance",
    ),
    RuleSpec(
        "GOV003",
        "GOV",
        "Undeclared local vocabulary term",
        Severity.WARNING,
        "Review references to local undeclared vocabulary terms.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "governance",
    ),
)


def run(ctx: RuleContext) -> None:
    """Run all governance rules."""
    _deprecated_usage(ctx)
    _equivalence_targets(ctx)
    _imports(ctx)


def _deprecated_usage(ctx: RuleContext) -> None:
    g = ctx.g
    for term in set(g.subjects(OWL.deprecated, Literal(True))):
        for s, p in g.subject_predicates(term):
            if p not in (RDFS.label, RDFS.comment, OWL.deprecated, DCTERMS.description):
                ctx.add("GOV001", s, f"Deprecated term {term} appears as object of {p}.")
        for s, _o in g.subject_objects(term):
            ctx.add("GOV001", s, f"Deprecated property {term} used in assertion.")


def _equivalence_targets(ctx: RuleContext) -> None:
    g = ctx.g
    for c in set(g.objects(None, OWL.equivalentClass)) | set(g.subjects(OWL.equivalentClass, None)):
        if isinstance(c, URIRef) and ctx.local(c) and c not in ctx.classes:
            ctx.add("GOV003", c, "Local URI used in owl:equivalentClass but not declared a class.")


def _imports(ctx: RuleContext) -> None:
    for ont in ctx.ontologies:
        for imported in set(ctx.g.objects(ont, OWL.imports)):
            if not isinstance(imported, URIRef):
                ctx.add("GOV002", ont, f"Non-IRI import target: {imported}.")
