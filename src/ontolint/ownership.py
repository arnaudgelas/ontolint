"""Which declared terms does the linted file own?

Term-level rules should judge the terms an ontology *defines*, not the vocabulary terms it merely
references (``rdfs:seeAlso`` targets, imported BFO/IAO/RO terms, ...).  :class:`Ownership` is the single
place that decides this, deterministically and without network access:

* with an explicit ``base`` the base decides (:func:`base_matches`);
* otherwise the owned namespaces are derived from the ``owl:Ontology`` IRIs of the file
  (:func:`derive_prefixes`);
* if that leaves no declared term owned, every declared non-built-in term is owned (the historic
  behaviour), so a file whose ontology IRI differs from its term namespace never goes silent.

Built-in vocabularies (RDF, RDFS, OWL, XSD) are never owned.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from rdflib import URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

BUILTIN_NAMESPACES = (str(RDF), str(RDFS), str(OWL), str(XSD))
OBO_NAMESPACE = "http://purl.obolibrary.org/obo/"
BOUNDARY_SUFFIXES = ("#", "/", "_")


class OwnershipMode(Enum):
    """How ownership was decided for a run."""

    BASE = "base"
    DERIVED = "derived"
    ALL = "all"


def is_builtin(node: object) -> bool:
    """Return whether ``node`` is an RDF, RDFS, OWL or XSD vocabulary IRI."""
    return isinstance(node, URIRef) and str(node).startswith(BUILTIN_NAMESPACES)


def base_matches(base: str | None, node: object) -> bool:
    """Return whether ``node`` is an IRI inside ``base`` (every IRI when ``base`` is empty).

    A base ending in a letter or digit (``https://x.org/onto``) matches itself and ``base#...`` /
    ``base/...`` only, so it never swallows ``https://x.org/ontology``.  Any other base
    (``https://x.org/onto#``, ``https://x.org/onto/``, ``http://purl.obolibrary.org/obo/RO_``) is a
    plain prefix.
    """
    if not isinstance(node, URIRef):
        return False
    if not base:
        return True
    iri = str(node)
    if base[-1].isalnum():
        return iri == base or iri.startswith((base + "#", base + "/"))
    return iri.startswith(base)


def derive_prefixes(ontologies: Iterable[URIRef]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return ``(exact, casefolded)`` namespace prefixes derived from ontology IRIs.

    Candidates per ontology IRI: the IRI itself, the IRI without a trailing ``#``/``/`` and without
    ``.owl``, and for ``http://purl.obolibrary.org/obo/<name>.owl`` (or ``.../obo/<name>/<file>.owl``) the ID prefix
    ``http://purl.obolibrary.org/obo/<NAME>_`` (matched case-insensitively).
    """
    exact: set[str] = set()
    folded: set[str] = set()
    for ontology in ontologies:
        iri = str(ontology)
        exact.add(iri)
        stripped = iri.rstrip("#/").removesuffix(".owl")
        if stripped:
            exact.add(stripped)
        if iri.startswith(OBO_NAMESPACE):
            name = re.split(r"[/#]", iri[len(OBO_NAMESPACE) :])[0].removesuffix(".owl")
            if name:
                folded.add((OBO_NAMESPACE + name + "_").casefold())
    return tuple(sorted(exact)), tuple(sorted(folded))


def _prefix_matches(iri: str, prefix: str) -> bool:
    """Prefix match that, for prefixes not ending in ``#``, ``/`` or ``_``, requires a name boundary."""
    if not iri.startswith(prefix):
        return False
    return prefix.endswith(BOUNDARY_SUFFIXES) or len(iri) == len(prefix) or iri[len(prefix)] in BOUNDARY_SUFFIXES


@dataclass(frozen=True)
class Ownership:
    """Decides whether an IRI belongs to the linted ontology."""

    mode: OwnershipMode = OwnershipMode.ALL
    base: str | None = None
    prefixes: tuple[str, ...] = ()
    folded_prefixes: tuple[str, ...] = ()
    base_selected_nothing: bool = False

    @classmethod
    def for_terms(cls, base: str | None, ontologies: Iterable[URIRef], declared: Iterable[URIRef]) -> Ownership:
        """Choose ownership for a file with the given ``ontologies`` and declared terms."""
        declared_terms = [term for term in declared if not is_builtin(term)]
        if base is not None:
            nothing = bool(base) and bool(declared_terms) and not any(base_matches(base, t) for t in declared_terms)
            return cls(OwnershipMode.BASE, base, base_selected_nothing=nothing)
        exact, folded = derive_prefixes(ontologies)
        derived = cls(OwnershipMode.DERIVED, None, exact, folded)
        if any(derived.owns(term) for term in declared_terms):
            return derived
        return cls()

    def owns(self, node: object) -> bool:
        """Return whether ``node`` is an IRI owned by the linted ontology."""
        if not isinstance(node, URIRef):
            return False
        if self.mode is OwnershipMode.BASE:
            return base_matches(self.base, node)
        if is_builtin(node):
            return False
        if self.mode is OwnershipMode.ALL:
            return True
        iri = str(node)
        return any(_prefix_matches(iri, p) for p in self.prefixes) or any(
            _prefix_matches(iri.casefold(), p) for p in self.folded_prefixes
        )
