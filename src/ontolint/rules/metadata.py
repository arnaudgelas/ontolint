"""Ontology-header rules: ONT001-ONT006."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rdflib.namespace import DCTERMS, OWL

from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity

from .support import DESCRIPTIONS, META_CREATOR, META_LICENSE

if TYPE_CHECKING:
    from .runtime import RuleContext


SPECS: tuple[RuleSpec, ...] = (
    RuleSpec(
        "ONT001",
        "ONT",
        "Missing ontology declaration",
        Severity.WARNING,
        "Declare a stable ontology IRI using rdf:type owl:Ontology.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.ONTOLOGY,
        "metadata",
    ),
    RuleSpec(
        "ONT002",
        "ONT",
        "Multiple ontology declarations",
        Severity.WARNING,
        "Prefer one primary owl:Ontology declaration per standalone ontology document.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.ONTOLOGY,
        "metadata",
    ),
    RuleSpec(
        "ONT003",
        "ONT",
        "Missing ontology license",
        Severity.WARNING,
        "Add dcterms:license (or an agreed equivalent) to the ontology.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.ONTOLOGY,
        "metadata",
    ),
    RuleSpec(
        "ONT004",
        "ONT",
        "Missing ontology version",
        Severity.INFO,
        "Add owl:versionIRI or owl:versionInfo according to your release policy.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.ONTOLOGY,
        "metadata",
    ),
    RuleSpec(
        "ONT005",
        "ONT",
        "Missing ontology creator or creation date",
        Severity.INFO,
        "Add creator and creation date provenance (e.g. dcterms:creator and dcterms:created).",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.ONTOLOGY,
        "metadata",
    ),
    RuleSpec(
        "ONT006",
        "ONT",
        "Missing ontology description",
        Severity.WARNING,
        "Describe the ontology with dcterms:description or rdfs:comment.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.ONTOLOGY,
        "metadata",
    ),
)


def run(ctx: RuleContext) -> None:
    """Check that ontology declarations carry identification and provenance metadata."""
    g = ctx.g
    if not ctx.ontologies:
        ctx.add("ONT001", "(ontology)", "Missing owl:Ontology declaration.", confidence="certain")
    if len(ctx.ontologies) > 1:
        ctx.add("ONT002", "(ontology)", f"{len(ctx.ontologies)} owl:Ontology declarations found.")
    for ont in sorted(ctx.ontologies, key=str):
        if not any((ont, p, None) in g for p in META_LICENSE):
            ctx.add("ONT003", ont, "Ontology has no license annotation.", confidence="certain")
        if not any((ont, p, None) in g for p in (OWL.versionIRI, OWL.versionInfo)):
            ctx.add("ONT004", ont, "No versionIRI/versionInfo.")
        if not any((ont, p, None) in g for p in META_CREATOR) or (ont, DCTERMS.created, None) not in g:
            ctx.add("ONT005", ont, "Missing creator or dcterms:created provenance.")
        if not any((ont, p, None) in g for p in DESCRIPTIONS):
            ctx.add("ONT006", ont, "Missing ontology description.")
