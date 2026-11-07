"""IRI and namespace quality rules: IRI004-IRI006, IRI008-IRI014, IRI016 and IRI017.

IRI007 (dereferenceability) needs the network and IRI015 (namespace hijacking) needs ownership
evidence, so both stay proposed.  Every rule here inspects only the asserted IRIs.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from rdflib import URIRef

from ontolint.context import KINDS
from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity

from .support import local_name

if TYPE_CHECKING:
    from .runtime import RuleContext

ILLEGAL_IRI_CHARACTERS = frozenset('<>"{}|\\^`')
PRIVATE_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
VERSION_SEGMENT = re.compile(r"^(?:v\d+(?:\.\d+)*|\d+\.\d+(?:\.\d+)*|\d{4}-\d{2}(?:-\d{2})?)$", re.IGNORECASE)
PERCENT_ESCAPE = re.compile(r"%[0-9A-Fa-f]{2}")
REPEATED_SEPARATOR = re.compile(r"(?:_{2,}|-{2,})")


def _spec(rule_id: str, title: str, severity: Severity, suggestion: str, scope: RuleScope) -> RuleSpec:
    return RuleSpec(rule_id, "IRI", title, severity, suggestion, "heuristic", RuleBackend.RDFLIB, scope, "iri_quality")


SPECS: tuple[RuleSpec, ...] = (
    _spec(
        "IRI004",
        "Term namespaces unrelated to the ontology IRI",
        Severity.INFO,
        "Mint term IRIs under the ontology IRI, or document why the namespace differs.",
        RuleScope.ONTOLOGY,
    ),
    _spec(
        "IRI005",
        "Mixed hash and slash term namespaces",
        Severity.INFO,
        "Use one namespace style (hash or slash) for the terms of a vocabulary.",
        RuleScope.VOCABULARY,
    ),
    _spec(
        "IRI006",
        "Term IRI contains a query string",
        Severity.WARNING,
        "Avoid '?query' parts in term IRIs; they are not stable identifiers.",
        RuleScope.TERM,
    ),
    _spec(
        "IRI008",
        "Mixed http and https term IRIs",
        Severity.INFO,
        "Use a single URI scheme for the terms of one vocabulary.",
        RuleScope.VOCABULARY,
    ),
    _spec(
        "IRI009",
        "IRI contains characters that are not allowed",
        Severity.WARNING,
        'Remove or percent-encode characters such as < > " { } | \\ ^ and backtick.',
        RuleScope.TERM,
    ),
    _spec(
        "IRI010",
        "Term IRI has an empty local name",
        Severity.WARNING,
        "Give the term a local name; an IRI ending in '#' or '/' names a namespace.",
        RuleScope.TERM,
    ),
    _spec(
        "IRI011",
        "Percent-encoded characters in a term local name",
        Severity.INFO,
        "Prefer readable local names without percent escapes.",
        RuleScope.TERM,
    ),
    _spec(
        "IRI012",
        "Term IRI uses a loopback host",
        Severity.WARNING,
        "Publish terms under a resolvable, persistent host instead of localhost.",
        RuleScope.TERM,
    ),
    _spec(
        "IRI013",
        "Version or date embedded in a term IRI",
        Severity.INFO,
        "Keep term IRIs persistent; put versions in owl:versionIRI instead.",
        RuleScope.TERM,
    ),
    _spec(
        "IRI014",
        "Leading, trailing or repeated separators in a local name",
        Severity.INFO,
        "Avoid leading/trailing or doubled '_' and '-' in local names.",
        RuleScope.TERM,
    ),
    _spec(
        "IRI016",
        "Ontology IRI has a query string or fragment",
        Severity.WARNING,
        "Use an ontology IRI without '?query' or '#fragment' parts.",
        RuleScope.ONTOLOGY,
    ),
    _spec(
        "IRI017",
        "Ontology IRI also used as a term",
        Severity.WARNING,
        "Do not reuse the ontology IRI as a class, property, concept or individual.",
        RuleScope.ONTOLOGY,
    ),
)


def run(ctx: RuleContext) -> None:
    """Run every IRI-quality rule over declared terms and ontologies."""
    for term in sorted(ctx.terms, key=str):
        _term_checks(ctx, term)
    _namespace_mix(ctx)
    for ontology in sorted(ctx.ontologies, key=str):
        _ontology_checks(ctx, ontology)
    _ontology_namespace(ctx)


def _term_checks(ctx: RuleContext, term: URIRef) -> None:
    iri = str(term)
    pieces = urlsplit(iri)
    name = local_name(term)
    if pieces.query or "?" in iri:
        ctx.add("IRI006", term, "Term IRI contains a query string.", confidence="certain")
    if ILLEGAL_IRI_CHARACTERS & set(iri):
        ctx.add("IRI009", term, "IRI contains characters that are not allowed in IRIs.", confidence="certain")
    if not name:
        ctx.add("IRI010", term, "Term IRI ends in a namespace separator and has no local name.", confidence="certain")
    if PERCENT_ESCAPE.search(name):
        ctx.add("IRI011", term, "Local name contains percent-encoded characters.")
    if (pieces.hostname or "").lower() in PRIVATE_HOSTS:
        ctx.add("IRI012", term, "Term IRI uses a loopback host.", confidence="certain")
    if any(VERSION_SEGMENT.match(segment) for segment in pieces.path.split("/")):
        ctx.add("IRI013", term, "Term IRI path embeds a version or date segment.")
    if name and (name[0] in "_-" or name[-1] in "_-" or REPEATED_SEPARATOR.search(name)):
        ctx.add("IRI014", term, "Local name has a leading, trailing or repeated separator.")


def _namespace_mix(ctx: RuleContext) -> None:
    named = [str(term) for term in ctx.terms if local_name(term)]
    hashed = sorted(iri for iri in named if "#" in iri)
    slashed = sorted(iri for iri in named if "#" not in iri)
    if hashed and slashed:
        ctx.add(
            "IRI005",
            "(vocabulary)",
            f"{len(hashed)} hash-style and {len(slashed)} slash-style term IRIs, e.g. {hashed[0]} and {slashed[0]}.",
        )
    schemes = {urlsplit(iri).scheme.lower() for iri in named}
    if {"http", "https"} <= schemes:
        ctx.add("IRI008", "(vocabulary)", "Terms mix http and https IRIs.")


def _ontology_checks(ctx: RuleContext, ontology: URIRef) -> None:
    pieces = urlsplit(str(ontology))
    if pieces.query or pieces.fragment:
        ctx.add("IRI016", ontology, "Ontology IRI contains a query string or fragment.", confidence="certain")
    if ctx.context.types_by_subject.get(ontology, frozenset()) & set(KINDS):
        ctx.add("IRI017", ontology, "Ontology IRI is also declared as a term.", confidence="certain")


def _ontology_namespace(ctx: RuleContext) -> None:
    ontologies = sorted(ctx.ontologies, key=str)
    terms = [term for term in ctx.terms if local_name(term)]
    if len(ontologies) != 1 or not terms:
        return
    root = str(ontologies[0]).rstrip("#/")
    if urlsplit(root).scheme and not any(str(term).startswith(root) for term in terms):
        ctx.add("IRI004", ontologies[0], "No term IRI starts with the ontology IRI.")
