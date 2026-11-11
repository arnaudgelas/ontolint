"""Modules inside one file: group findings by an annotation of their term or by its namespace.

Some ontologies keep their modules in one file instead of splitting them over ``owl:imports``.  MOMo
marks each term with the module it is native to (``opla:isNativeTo "Container"``); a merged release
keeps one namespace per source ontology (``…/behaviour#``, ``…/bill-of-material#``).  With
``--module-annotation PREDICATE`` a finding belongs to the modules its term names with that
predicate; with ``--module-by namespace`` to its term's namespace.  A finding about several terms
(an ``IRI003`` local-name or ``LEX004`` label collision, through :attr:`Finding.related`) belongs to
the modules of all of them, which is how a collision *between* modules shows.

Grouping is presentation only: it never adds, removes or rewords a finding, so fingerprints and
baselines are the same with and without it.  A finding whose focus is not an IRI (``(ontology)``, a
blank node) or whose term carries no module annotation belongs to no module.

A finding's terms hold no userinfo (:mod:`ontolint.redaction`), so neither do module names: a namespace is
taken from the masked term, and an annotation value is masked too.  A masked term is looked up under every
IRI of the graph that masks to it, so a credentialed term keeps its modules.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence

from rdflib import Graph, Literal, URIRef

from .models import Finding
from .ownership import namespace_of_iri
from .policy import MODULE_BY_VALUES
from .redaction import redact_userinfo

MODULE_BY = MODULE_BY_VALUES
"""The values ``--module-by`` accepts."""

_IRI_FOCUS = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:\S+")
_CURIE = re.compile(r"(?P<prefix>[A-Za-z_][\w.-]*)?:(?P<name>\S*)")


class UnresolvedModulePredicate(ValueError):
    """The ``--module-annotation`` CURIE uses a prefix the linted file does not declare."""


def resolve_predicate(text: str, prefixes: Iterable[tuple[str, str]]) -> URIRef:
    """The predicate ``text`` names: ``<IRI>``, an IRI with ``//`` or ``urn:``, or ``prefix:name``.

    ``prefixes`` are ``(prefix, namespace)`` pairs; a later pair for the same prefix wins.
    """
    if text.startswith("<") and text.endswith(">"):
        return URIRef(text[1:-1])
    if "://" in text or text.startswith("urn:"):
        return URIRef(text)
    match = _CURIE.fullmatch(text)
    namespace = dict(prefixes).get(match.group("prefix") or "") if match else None
    if match is None or namespace is None:
        raise UnresolvedModulePredicate(text)
    return URIRef(namespace + match.group("name"))


def _module_names(graph: Graph, term: str, predicate: URIRef | None, carriers: Mapping[str, list[URIRef]]) -> list[str]:
    if not _IRI_FOCUS.fullmatch(term):  # "(ontology)", and blank nodes ("_:" starts with no scheme)
        return []
    if predicate is None:
        namespace = namespace_of_iri(term)
        return [namespace] if namespace else []
    return [
        redact_userinfo(str(value))
        for node in carriers.get(term, ())
        for value in graph.objects(node, predicate)
        if isinstance(value, Literal | URIRef)
    ]


def _carriers(graph: Graph, predicate: URIRef | None) -> dict[str, list[URIRef]]:
    """The IRIs that carry ``predicate``, keyed by their masked spelling (a finding's term)."""
    carriers: dict[str, list[URIRef]] = {}
    if predicate is not None:
        for node in sorted({s for s in graph.subjects(predicate, None) if isinstance(s, URIRef)}):
            carriers.setdefault(redact_userinfo(str(node)), []).append(node)
    return carriers


def finding_modules(
    graph: Graph, findings: Sequence[Finding], predicate: URIRef | None
) -> dict[Finding, tuple[str, ...]]:
    """The modules of each finding that has one: by ``predicate``, or by namespace when it is ``None``."""
    carriers = _carriers(graph, predicate)
    modules: dict[Finding, tuple[str, ...]] = {}
    for finding in findings:
        names = {
            name
            for term in (finding.focus, *finding.related)
            for name in _module_names(graph, term, predicate, carriers)
        }
        if names:
            modules[finding] = tuple(sorted(names))
    return modules


def module_summary(modules: Mapping[Finding, tuple[str, ...]]) -> dict[str, dict[str, int]]:
    """Per module, its findings counted by severity; a finding in several modules counts in each."""
    summary: dict[str, dict[str, int]] = {}
    for finding, names in modules.items():
        for name in names:
            counts = summary.setdefault(name, {})
            counts[finding.severity] = counts.get(finding.severity, 0) + 1
    return dict(sorted(summary.items()))
