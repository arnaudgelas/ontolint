"""IRI and namespace quality rules: IRI004-IRI006, IRI008-IRI014 and IRI016-IRI019, specified here.

IRI007 (dereferenceability) needs the network, so it stays proposed (issue #38).  IRI015 is implemented in
``iri_lexical_extras`` as a mixed-naming check (namespace hijacking would need ownership evidence).
Every rule here inspects only the asserted IRIs.

RFC 3986 is the URI generic syntax and RFC 3987 its extension to IRIs.  A *term* is an owned declared term (the
terms ``--base`` or the ontology IRIs select: ``ontolint.ownership``); a *local name* is the text after the last
``/`` or ``#`` of an IRI; its *namespace* is the rest.  Every rule reads the IRI as the graph holds it: a parser
has resolved a relative reference (RFC 3986 section 5) and ``--base`` selects terms, it does not resolve.  A focus
or message that holds an IRI with a userinfo (RFC 3986 3.2.1) prints it masked by ``ontolint.redaction``, so IRIs that
differ only in their userinfo give one finding.  The catalogue category of every rule here is heuristic; the
findings of IRI006, IRI009, IRI010, IRI012, IRI016, IRI017 and IRI018 (and IRI001) say certain: category and
confidence disagree, an open question.  The pinned cases, including every known gap, are in
``tests/test_iri_specification.py``; the per-rule fixtures in ``tests/rule_cases/iri_quality.py``.

* **IRI004.** Scope: the ontology, when the file has exactly one ``owl:Ontology`` IRI, that is absolute, not under
  ``http://purl.obolibrary.org/obo/``, and at least one term has a local name.  Fires when no term IRI starts with
  the ontology IRI minus its trailing ``#`` or ``/`` (a plain string prefix: ``o`` also covers ``ontology/A``).
  Convention: terms are minted under the ontology IRI.  Gap: a file extension, a query or a version is not
  removed from the ontology IRI, so ``o.owl`` with terms in ``o#`` is reported although ownership derives the namespace
  ``o#`` from it, and ``http`` terms under an ``https`` ontology are unrelated.  Info.
* **IRI005.** Scope: the vocabulary.  Fires once (focus ``(vocabulary)``) when terms with a local name include both
  an IRI with a ``#`` (hash-style) and one without (slash-style, a URN included).  An IRI that ends in
  a separator is not counted.  The ``#`` terms under ``http://purl.obolibrary.org/obo/`` are exempt in a file whose
  ontology IRI is an OBO one (subset annotations).  Convention: one style per vocabulary.  Info.
* **IRI006.** Scope: every term.  Fires, with certainty, when the IRI holds a ``?`` before its first ``#`` (so an
  empty query ``x?`` is reported).  RFC 3986 3.4 starts the query at the first ``?`` and ends it at ``#``; a ``?``
  inside a fragment (``#a?b``, allowed by 3.5) is no query and is not reported.  Ontology IRIs are IRI016's.
  Warning: a query is not a stable identifier.
* **IRI008.** Scope: the vocabulary.  Fires once when terms with a local name have both an ``http`` and an
  ``https`` scheme (compared lower-cased; other schemes ignored).  The same name under both schemes is two terms.
  Convention: one scheme per vocabulary.  Info.
* **IRI009.** Scope: every term (an ontology IRI is not read: gap).  Fires, with certainty, when the IRI holds one of
  the characters ``<``, ``>``, ``"``, ``{``, ``}``, ``|``, ``\\``, ``^`` or the backtick, which RFC 3986 2.2 and
  2.3 do not allow and RFC 3987 2.2 does not either.  Exclusions: the space, which is IRI001's,
  and non-ASCII characters (``ucschar`` is what an IRI allows).  Gap: a control character, a character outside
  ``ucschar`` and a ``%`` not followed by two hex digits (RFC 3986 2.1) are not reported by any rule.  Warning.
* **IRI010.** Scope: every term.  Fires, with certainty, when the local name is empty, that is when the IRI ends in
  ``#`` or ``/`` (``ns#``, ``ns/``, ``ns#A/``).  Gap: the IRI of an authority alone (``https://a.test``) has the host
  as its local name, and a URN's final colon is not read, since only ``/`` and ``#`` separate.
  Warning: a namespace names no term.
* **IRI011.** Scope: every term.  Fires when the local name holds ``%`` followed by two hex digits.  Escapes in
  the namespace, and a ``%`` that starts no escape, are not read.  Gap: an escape of an unreserved character
  (RFC 3986 2.3: ``%41`` is ``A``) is reported like any other.  Convention: a readable name.  Info.
* **IRI012.** Scope: every term.  Fires, with certainty, when the host (after any userinfo, so ``localhost@a.test`` is
  ``a.test``), lower-cased, is exactly ``localhost``, ``127.0.0.1`` or ``::1`` (an IPv6 literal in brackets, with or
  without a port).  Gap: RFC 6761 6.3 reserves ``localhost.`` and ``*.localhost``, ``127.0.0.0/8`` is all loopback and
  ``[0:0:0:0:0:0:0:1]`` is ``::1``; none is reported.  Warning: a loopback IRI cannot be resolved by another reader.
* **IRI013.** Scope: every term.  A path segment (the whole path is split on ``/``, a local name after the last
  ``/`` included, the fragment excluded) that is ``v`` and digits with optional dotted parts, dotted numbers, or
  ``yyyy-mm`` or ``yyyy-mm-dd`` (case-insensitive) is a version or a date.  One finding per namespace of such terms,
  focused on the namespace, naming the count and the first IRI.  A year alone and a loosely written date are not
  versions.  Gap: a version in the fragment is not read, and a local name such as ``1.0`` in a slash namespace is.
  Convention: ``owl:versionIRI`` carries versions (OWL 2 Structural Specification 3.1).  Info.
* **IRI014.** Scope: every term with a local name.  Fires when the local name starts or ends with ``_`` or ``-`` or
  holds ``__`` or ``--``.  The mixed ``_-``, ``.`` and ``:`` are not separators here.  Convention.  Info.
* **IRI016.** Scope: every ontology IRI.  Fires, with certainty, when ``urlsplit`` finds a non-empty query or
  fragment.  Boundary, accepted by design: an empty fragment (``o#``) is the usual hash-terminated ontology IRI.
  Gap: an empty query (``o?``) passes although RFC 3986 3.4 makes it a query and IRI006 reports it on a term.
  An ontology IRI is a document identifier (OWL 2 Structural Specification 3.1, with the version IRI).  Warning.
* **IRI017.** Scope: every ontology IRI.  Fires, with certainty, when it is also asserted as an ``owl:Class``,
  ``rdfs:Class``, an object, datatype or annotation property, ``rdf:Property``, a ``skos:Concept``,
  ``skos:ConceptScheme``, ``skos:Collection`` or ``owl:NamedIndividual``.  Exclusion: a term under the ontology IRI
  (``o#A``).  Convention: the ontology and its entities are distinct things.  Warning.
* **IRI018.** Scope: every ontology IRI of the file (the root, not an imported module).  Fires, with certainty, when
  the IRI ends in ``/untitled-ontology-<digits>`` with an optional ``/`` (message one), or starts with
  ``http://www.semanticweb.org/<user>/ontologies/`` (``https`` too; message two), Protege's defaults.  Gap: the
  match is case-sensitive although RFC 3986 3.2.2 makes the host case-insensitive, and a userinfo in the authority
  hides it.  Warning: the author does not control that namespace.
* **IRI019.** Scope: the vocabulary.  A declared prefix (the file's own declarations, else the graph's bindings that
  are not rdflib's defaults, one prefix per namespace) fires, once per prefix, focused on its namespace, when
  no IRI of the graph or datatype starts with the namespace and the namespace without a final ``#`` or
  ``/`` is no IRI of the graph.  Exclusions: the editor boilerplate namespaces (rdf, rdfs, owl, xsd, xml).  The
  namespace itself counts as a use.  Info: an unused declaration is a convention violation, harmless to a reader.
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
            subject=(),
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
    if "?" in iri.partition("#")[0]:  # RFC 3986 3.4: the query ends at "#"; a "?" in a fragment is not one
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
            subject=(),
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
        ctx.add(
            "IRI018",
            ontology,
            "Ontology IRI is Protege's untitled-ontology placeholder.",
            confidence="certain",
            subject=(),
        )
    elif PROTEGE_DEFAULT_BASE.match(str(ontology)):
        ctx.add(
            "IRI018",
            ontology,
            "Ontology IRI is under Protege's default http://www.semanticweb.org/<user>/ontologies/ base, "
            "which its authors do not control.",
            subject=(),
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
        ctx.add(
            "IRI019",
            URIRef(namespace),
            f"Prefix {prefix}: is declared for <{namespace}>, but no IRI uses it.",
            subject=(prefix,),
        )


def _ontology_namespace(ctx: RuleContext) -> None:
    ontologies = sorted(ctx.ontologies, key=str)
    terms = [term for term in ctx.terms if local_name(term)]
    if len(ontologies) != 1 or not terms or str(ontologies[0]).startswith(OBO_NAMESPACE):
        return
    root = str(ontologies[0]).rstrip("#/")
    if safe_urlsplit(root).scheme and not any(str(term).startswith(root) for term in terms):
        ctx.add("IRI004", ontologies[0], "No term IRI starts with the ontology IRI.")
