"""Identifier hygiene rules: IRI001-IRI003, specified here.

RFC 3986 is the URI generic syntax and RFC 3987 its extension to IRIs.  The rules read the IRIs the graph holds:
every parser resolves a relative reference against the document (RFC 3986 section 5) before a rule runs, and
``--base`` (``Linter(base=...)``) is an ownership prefix that selects the terms judged, never a resolution base.
They inspect the declared terms the file owns and the ``owl:Ontology`` IRIs, and nothing leaves the process.  A
focus or message that holds an IRI with a userinfo prints it masked (``ontolint.redaction``).  The pinned cases,
including every known gap, are in ``tests/test_iri_specification.py``.

* **IRI001.** Scope: every owned declared term and every ontology IRI.  Fires with certainty when the IRI text holds a
  character for which ``str.isspace`` is true, or when ``urlsplit`` finds no scheme ("IRI contains whitespace or
  is not absolute."), and, as a second message, when the scheme is ``http`` or ``https`` (any case) and the
  authority is empty (``http:example.org/x``, ``http:///x``: "has no '//' host").  RFC 3986 4.3 makes an
  absolute IRI begin with a scheme (3.1: a letter first) and RFC 3987 2.2 excludes the space.  Exclusions: any other
  scheme (``urn:``, ``file:///x``).  Gap: an empty host with a port (``http://:80/x``) is not reported because the
  authority is not empty.  Warning, because such an IRI is a different identifier from the one the author meant
  once a tool resolves or serialises it; certain, because the condition is a syntax test (the catalogue category
  is heuristic: confidence and category disagree, an open question).  Fixtures: ``tests/rule_cases/identifiers.py``.
* **IRI002.** Scope: every ontology IRI except those under ``http://purl.obolibrary.org/obo/``.  Fires when the
  path (not the query or fragment) ends in ``.owl``, ``.ttl``, ``.n3``, ``.rdf`` or ``.rdfxml``, in any case.
  Convention, not a standard: an ontology IRI names the ontology, not a serialisation of it.  Gap: ``.jsonld``,
  ``.json``, ``.nt``, ``.obo``, ``.ofn``, ``.omn`` and ``.owx`` (which ownership strips) are not read.
  Warning at heuristic confidence, as the suggestion says the choice is policy-dependent.  Fixtures:
  ``tests/rule_cases/identifiers.py`` and ``tests/test_precision_lex_iri.py``.
* **IRI003.** Scope: the owned declared terms that are not ``owl:deprecated true``.  Groups them by the case-folded
  local name (the text after the last ``/`` or ``#``) and by kind (``class``, ``property`` or ``other``: a term of
  two kinds is in two groups); one finding per group with two or more IRIs, focused on the smallest IRI, naming
  at most five.  A class and a property, or a class and a concept, that share a name are ordinary style and are
  not reported.  Ontology IRIs are not read.  Gap: the title says across namespaces, but two names that differ only
  in case in one namespace are reported, and so are two empty local names.  Info at heuristic confidence:
  a convention that duplicate names confuse readers, no standard.  Fixtures: ``tests/rule_cases/identifiers.py`` and
  ``tests/test_precision_lex_iri.py``.
"""

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
            ctx.add("IRI001", u, "IRI contains whitespace or is not absolute.", confidence="certain", subject=())
        elif pieces.scheme.lower() in {"http", "https"} and not pieces.netloc:
            # "http:example.org/x" (one missing "//") parses as an absolute IRI but names no host.
            ctx.add(
                "IRI001",
                u,
                f"{pieces.scheme}: IRI has no '//' host, so it cannot be dereferenced.",
                confidence="certain",
                subject=(),
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
    for (name, kind), iris in names.items():
        # The set cannot contain two distinct IRIs with the same complete
        # namespace/local-name split, so cardinality alone is sufficient.
        if len(iris) > 1:
            ctx.add(
                "IRI003",
                sorted(map(str, iris))[0],
                "Local-name collision across IRIs: " + ", ".join(sorted(map(str, iris))[:5]),
                related=iris,
                subject=(name, kind),
            )
