"""IRI and namespace quality rules: IRI004-IRI006, IRI008-IRI014 and IRI016-IRI019.

IRI007 (dereferenceability) needs the network, so it stays proposed.  IRI015 is implemented in
``iri_lexical_extras`` as a mixed-naming check (namespace hijacking would need ownership evidence).
Every rule here inspects only the asserted IRIs.
"""

from __future__ import annotations

import bisect
import re
from typing import TYPE_CHECKING

from rdflib import Graph, Literal, URIRef

from ontolint.context import KINDS
from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity
from ontolint.ownership import OBO_NAMESPACE

from .support import local_name, safe_urlsplit

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
    _spec(
        "IRI018",
        "Placeholder ontology IRI",
        Severity.WARNING,
        "Give the ontology a permanent IRI under a namespace you control, such as a w3id.org or purl.org PURL.",
        RuleScope.ONTOLOGY,
    ),
    _spec(
        "IRI019",
        "Declared prefix that no IRI uses",
        Severity.INFO,
        "Remove the prefix declaration, or import the vocabulary it was declared for.",
        RuleScope.VOCABULARY,
    ),
)

# Protege's default ontology IRI: http://www.semanticweb.org/<user>/ontologies/<yyyy>/<m>/untitled-ontology-<n>.
PROTEGE_UNTITLED = re.compile(r"/untitled-ontology-\d+/?$")
PROTEGE_DEFAULT_BASE = re.compile(r"^https?://www\.semanticweb\.org/[^/]+/ontologies/")
# Prefixes editors write into every file (Protege: rdf, rdfs, owl, xsd and xml), used or not: never reported.
BOILERPLATE_NAMESPACES = frozenset(
    {
        "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "http://www.w3.org/2000/01/rdf-schema#",
        "http://www.w3.org/2002/07/owl#",
        "http://www.w3.org/2001/XMLSchema#",
        "http://www.w3.org/XML/1998/namespace",
    }
)


def run(ctx: RuleContext) -> None:
    """Run every IRI-quality rule over declared terms and ontologies."""
    versioned: dict[str, list[str]] = {}
    for term in sorted(ctx.terms, key=str):
        _term_checks(ctx, term, versioned)
    for namespace, iris in sorted(versioned.items()):
        ctx.add(
            "IRI013",
            namespace,
            f"{len(iris)} term IRIs in this namespace embed a version or date segment (e.g. {iris[0]}).",
        )
    _namespace_mix(ctx)
    for ontology in sorted(ctx.ontologies, key=str):
        _ontology_checks(ctx, ontology)
    _ontology_namespace(ctx)
    _unused_prefixes(ctx)


def _term_checks(ctx: RuleContext, term: URIRef, versioned: dict[str, list[str]]) -> None:
    iri = str(term)
    pieces = safe_urlsplit(iri)
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
        versioned.setdefault(iri[: len(iri) - len(name)], []).append(iri)
    if name and (name[0] in "_-" or name[-1] in "_-" or REPEATED_SEPARATOR.search(name)):
        ctx.add("IRI014", term, "Local name has a leading, trailing or repeated separator.")


def _namespace_mix(ctx: RuleContext) -> None:
    obo_ontology = any(str(ontology).startswith(OBO_NAMESPACE) for ontology in ctx.ontologies)
    named = [str(term) for term in ctx.terms if local_name(term)]
    # ``http://purl.obolibrary.org/obo/<name>#term`` (slim/subset annotations) next to ``obo/NAME_0000001`` is
    # standard OBO PURL practice.
    hashed = sorted(iri for iri in named if "#" in iri and not (obo_ontology and iri.startswith(OBO_NAMESPACE)))
    slashed = sorted(iri for iri in named if "#" not in iri)
    if hashed and slashed:
        ctx.add(
            "IRI005",
            "(vocabulary)",
            f"{len(hashed)} hash-style and {len(slashed)} slash-style term IRIs, e.g. {hashed[0]} and {slashed[0]}.",
        )
    schemes = {safe_urlsplit(iri).scheme.lower() for iri in named}
    if {"http", "https"} <= schemes:
        ctx.add("IRI008", "(vocabulary)", "Terms mix http and https IRIs.")


def _ontology_checks(ctx: RuleContext, ontology: URIRef) -> None:
    pieces = safe_urlsplit(str(ontology))
    if pieces.query or pieces.fragment:
        ctx.add("IRI016", ontology, "Ontology IRI contains a query string or fragment.", confidence="certain")
    if ctx.context.types_by_subject.get(ontology, frozenset()) & set(KINDS):
        ctx.add("IRI017", ontology, "Ontology IRI is also declared as a term.", confidence="certain")
    if PROTEGE_UNTITLED.search(str(ontology)):
        ctx.add("IRI018", ontology, "Ontology IRI is Protege's untitled-ontology placeholder.", confidence="certain")
    elif PROTEGE_DEFAULT_BASE.match(str(ontology)):
        ctx.add(
            "IRI018",
            ontology,
            "Ontology IRI is under Protege's default http://www.semanticweb.org/<user>/ontologies/ base, "
            "which its authors do not control.",
        )


def _declared_prefixes(ctx: RuleContext) -> tuple[tuple[str, str], ...]:
    """The file's own prefix declarations, or, for a graph ontolint did not read, its non-default bindings."""
    declared = ctx.policy.source.declared_prefixes
    if declared is not None:
        return declared
    defaults = {(prefix, str(namespace)) for prefix, namespace in Graph().namespaces()}
    return tuple(sorted((p, str(n)) for p, n in ctx.g.namespaces() if (p, str(n)) not in defaults))


def _unused_prefixes(ctx: RuleContext) -> None:
    declared = _declared_prefixes(ctx)
    if not declared:
        return
    iris = {str(n) for triple in ctx.g for n in triple if isinstance(n, URIRef)}
    iris |= {str(o.datatype) for o in ctx.g.objects() if isinstance(o, Literal) and o.datatype is not None}
    used = sorted(iris)
    for prefix, namespace in declared:
        if namespace in BOILERPLATE_NAMESPACES:
            continue
        at = bisect.bisect_left(used, namespace)
        if at < len(used) and used[at].startswith(namespace):
            continue  # some IRI is in the namespace (or is the namespace itself)
        if namespace.rstrip("#/") in iris:
            continue  # the namespace names the ontology (<https://x.test/o> for o: <https://x.test/o#>)
        ctx.add("IRI019", URIRef(namespace), f"Prefix {prefix}: is declared for <{namespace}>, but no IRI uses it.")


def _ontology_namespace(ctx: RuleContext) -> None:
    ontologies = sorted(ctx.ontologies, key=str)
    terms = [term for term in ctx.terms if local_name(term)]
    if len(ontologies) != 1 or not terms or str(ontologies[0]).startswith(OBO_NAMESPACE):
        return
    root = str(ontologies[0]).rstrip("#/")
    if safe_urlsplit(root).scheme and not any(str(term).startswith(root) for term in terms):
        ctx.add("IRI004", ontologies[0], "No term IRI starts with the ontology IRI.")
