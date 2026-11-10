"""Governance rules for deprecation, equivalence targets, and imports: GOV001-GOV003."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rdflib import URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS
from rdflib.term import Node

from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity

from .owl import is_deprecated, owned_checker, owning_term
from .support import OBO, relative_reference

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

OBO_IN_OWL = "http://www.geneontology.org/formats/oboInOwl#"
# Predicates through which a deprecated term is legitimately *mentioned*: axiom annotation plumbing,
# replacement / consider pointers and other annotation-style links.
ANNOTATION_REFERENCES = frozenset(
    {
        OWL.annotatedSource,
        OWL.annotatedTarget,
        OWL.annotatedProperty,
        URIRef(OBO_IN_OWL + "consider"),
        URIRef(OBO_IN_OWL + "replaced_by"),
        URIRef(OBO + "IAO_0100001"),  # "term replaced by"
        DCTERMS.isReplacedBy,
        DCTERMS.replaces,
        URIRef("http://schema.org/supersededBy"),
        URIRef("https://schema.org/supersededBy"),
        RDFS.seeAlso,
        RDFS.isDefinedBy,
    }
)
_LIST_PLUMBING = (RDF.first, RDF.rest)
_LIST_DEPTH = 64


def run(ctx: RuleContext) -> None:
    """Run all governance rules."""
    _deprecated_usage(ctx)
    _equivalence_targets(ctx)
    _imports(ctx)


def _list_owners(ctx: RuleContext, cell: Node) -> set[tuple[Node, URIRef]]:
    """Return the ``(subject, predicate)`` pairs whose RDF list contains ``cell``."""
    g = ctx.g
    owners: set[tuple[Node, URIRef]] = set()
    seen: set[Node] = set()
    frontier: set[Node] = {cell}
    for _ in range(_LIST_DEPTH):
        if not frontier:
            break
        seen |= frontier
        nxt: set[Node] = set()
        for node in frontier:
            for s, p in g.subject_predicates(node):
                if p == RDF.rest and s not in seen:
                    nxt.add(s)
                elif p != RDF.rest and isinstance(p, URIRef) and p != RDF.first:
                    owners.add((s, p))
        frontier = nxt
    return owners


def _deprecated_usage(ctx: RuleContext) -> None:
    g = ctx.g
    deprecated = {t for t in set(g.subjects(OWL.deprecated, None)) if is_deprecated(g, t)}
    for term in sorted(deprecated, key=str):
        for s, p in sorted(g.subject_predicates(term), key=lambda t: (str(t[0]), str(t[1]))):
            if p in (RDFS.label, RDFS.comment, OWL.deprecated, DCTERMS.description) or p in ANNOTATION_REFERENCES:
                continue
            if p in _LIST_PLUMBING:
                for owner, owner_predicate in sorted(_list_owners(ctx, s), key=str):
                    focus = owning_term(g, owner)
                    if owner_predicate not in ANNOTATION_REFERENCES and not _foreign(ctx, focus):
                        ctx.add(
                            "GOV001",
                            focus,
                            f"Deprecated term {term} appears in a list of {owner_predicate}.",
                            subject=(term, "list", owner_predicate),
                        )
                continue
            if not _foreign(ctx, focus := owning_term(g, s)):
                ctx.add(
                    "GOV001", focus, f"Deprecated term {term} appears as object of {p}.", subject=(term, "object", p)
                )
        for s, _o in g.subject_objects(term):
            if not _foreign(ctx, s):
                ctx.add("GOV001", s, f"Deprecated property {term} used in assertion.", subject=(term, "predicate"))


def _foreign(ctx: RuleContext, node: object) -> bool:
    """Whether ``node`` is an IRI of a vocabulary the linted ontology only imports or merges in."""
    return isinstance(node, URIRef) and not ctx.local(node)


def _equivalence_targets(ctx: RuleContext) -> None:
    g = ctx.g
    owned = owned_checker(ctx)
    for c in set(g.objects(None, OWL.equivalentClass)) | set(g.subjects(OWL.equivalentClass, None)):
        if isinstance(c, URIRef) and owned(c) and c not in ctx.classes and (c, RDF.type, None) not in g:
            ctx.add("GOV003", c, "Local URI used in owl:equivalentClass but not declared a class.")


def _imports(ctx: RuleContext) -> None:
    bases = ctx.policy.document_bases
    for ont in ctx.ontologies:
        relative: list[str] = []
        for imported in set(ctx.g.objects(ont, OWL.imports)):
            if not isinstance(imported, URIRef):
                ctx.add("GOV002", ont, f"Non-IRI import target: {imported}.", subject=(imported,))
            elif (reference := relative_reference(str(imported), bases)) is not None:
                relative.append(reference)
        if relative:
            shown = ", ".join(sorted(relative)[:RELATIVE_IMPORTS_SHOWN])
            more = (
                f" and {len(relative) - RELATIVE_IMPORTS_SHOWN} more" if len(relative) > RELATIVE_IMPORTS_SHOWN else ""
            )
            ctx.add(
                "GOV002",
                ont,
                f"{len(relative)} owl:imports use relative references ({shown}{more}), which resolve differently "
                "depending on where the file is read; import absolute IRIs and map them with a catalog.",
                confidence="certain",
                subject=(),
            )


RELATIVE_IMPORTS_SHOWN = 5
"""How many relative import references the GOV002 note names before summarising the rest."""
