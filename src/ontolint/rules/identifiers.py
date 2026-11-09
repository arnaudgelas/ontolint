"""Identifier hygiene rules: IRI001-IRI003."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import TYPE_CHECKING

from rdflib import Literal, URIRef
from rdflib.namespace import OWL

from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity
from ontolint.ownership import OBO_NAMESPACE

from .support import local_name, safe_urlsplit

if TYPE_CHECKING:
    from .runtime import RuleContext


SPECS: tuple[RuleSpec, ...] = (
    RuleSpec(
        "IRI001",
        "IRI",
        "Whitespace or non-absolute IRI",
        Severity.WARNING,
        "Use stable absolute IRIs; avoid whitespace in identifiers.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "identifiers",
    ),
    RuleSpec(
        "IRI002",
        "IRI",
        "Ontology IRI contains a file extension",
        Severity.WARNING,
        "Consider an extension-independent ontology identifier (policy-dependent).",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.ONTOLOGY,
        "identifiers",
    ),
    RuleSpec(
        "IRI003",
        "IRI",
        "Local-name collision across namespaces",
        Severity.INFO,
        "Check whether duplicate local identifiers across namespaces confuse users.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.VOCABULARY,
        "identifiers",
    ),
)


def _kinds(ctx: RuleContext, term: URIRef) -> tuple[str, ...]:
    kinds = tuple(kind for kind, group in (("class", ctx.classes), ("property", ctx.properties)) if term in group)
    return kinds or ("other",)


def run(ctx: RuleContext) -> None:
    """Check IRIs of ontologies and declared terms for syntax, extensions, and collisions."""
    names: defaultdict[tuple[str, str], set[URIRef]] = defaultdict(set)
    for u in ctx.terms | ctx.ontologies:
        s = str(u)
        pieces = safe_urlsplit(s)
        if any(character.isspace() for character in s) or not pieces.scheme:
            ctx.add("IRI001", u, "IRI contains whitespace or is not absolute.", confidence="certain")
        elif pieces.scheme.lower() in {"http", "https"} and not pieces.netloc:
            # "http:example.org/x" (one missing "//") parses as an absolute IRI but names no host.
            ctx.add(
                "IRI001",
                u,
                f"{pieces.scheme}: IRI has no '//' host, so it cannot be dereferenced.",
                confidence="certain",
            )
        if (
            u in ctx.ontologies
            and not s.startswith(OBO_NAMESPACE)
            and re.search(r"\.(owl|ttl|n3|rdf|rdfxml)$", pieces.path, flags=re.I)
        ):
            ctx.add("IRI002", u, "Ontology IRI contains a serialization file extension.")
        if u in ctx.terms and (u, OWL.deprecated, Literal(True)) not in ctx.g:
            # A class and a property sharing a name (``Agent`` / ``agent``) is ordinary vocabulary style.
            for kind in _kinds(ctx, u):
                names[(local_name(u).casefold(), kind)].add(u)
    for iris in names.values():
        # The set cannot contain two distinct IRIs with the same complete
        # namespace/local-name split, so cardinality alone is sufficient.
        if len(iris) > 1:
            ctx.add(
                "IRI003",
                sorted(map(str, iris))[0],
                "Local-name collision across IRIs: " + ", ".join(sorted(map(str, iris))[:5]),
            )
