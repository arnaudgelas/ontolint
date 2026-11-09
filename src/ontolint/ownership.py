"""Which declared terms does the linted file own?

Term-level rules should judge the terms an ontology *defines*, not the vocabulary terms it merely
references (``rdfs:seeAlso`` targets, imported BFO/IAO/RO terms, ...).  :class:`Ownership` is the single
place that decides this, deterministically and without network access:

* with an explicit ``base`` the base decides (:func:`base_matches`);
* otherwise the owned namespaces are derived from the ``owl:Ontology`` IRIs of the file
  (:func:`derive_prefixes`);
* if that leaves no declared term owned, the namespace holding more than :data:`DOMINANT_PERCENT`
  percent of the declared terms is owned (a Protege placeholder IRI such as ``untitled-ontology-139``,
  or terms minted outside the ontology IRI); only without such a namespace is every declared
  non-built-in term owned (the historic behaviour), so a file never goes silent;
* if the derived namespaces own less than :data:`MINOR_OWNED_PERCENT` percent of the declared terms
  while one other namespace holds more than :data:`DOMINANT_PERCENT` percent of them, that dominant
  namespace is owned too (a vocabulary that embeds the SKOS core description next to its own concepts).

Built-in vocabularies (RDF, RDFS, OWL, XSD) are never owned.  Terms of well-known vocabularies
(:data:`WELL_KNOWN_NAMESPACES`: Dublin Core, SKOS, DCAT, ...) that the ontology IRIs do not own are left
out of the decision and are not owned, because OWL 2 DL makes a file declare the annotation properties it
borrows (``skos:definition a owl:AnnotationProperty``).  A well-known namespace holding more than
:data:`DOMINANT_PERCENT` percent of the declared terms is the vocabulary being linted and still decides,
and a file declaring nothing but borrowed terms keeps the historic behaviour.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from rdflib import URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

BUILTIN_NAMESPACES = (str(RDF), str(RDFS), str(OWL), str(XSD))
OBO_NAMESPACE = "http://purl.obolibrary.org/obo/"
# Vocabularies whose terms ontologies borrow, mostly as annotation properties.  Prefixes, not
# namespaces, for OBO: only the IAO, RO and BFO identifiers are borrowed everywhere.
WELL_KNOWN_NAMESPACES = (
    "http://purl.org/dc/terms/",
    "http://purl.org/dc/elements/1.1/",
    "http://www.w3.org/2004/02/skos/core#",
    "http://www.w3.org/2008/05/skos-xl#",
    "http://www.w3.org/ns/dcat#",
    "http://xmlns.com/foaf/0.1/",
    "http://www.w3.org/ns/prov#",
    "http://schema.org/",
    "https://schema.org/",
    "http://purl.org/vocab/vann/",
    "http://www.w3.org/2006/vcard/ns#",
    "http://creativecommons.org/ns#",
    "http://www.w3.org/ns/shacl#",
    "http://www.geneontology.org/formats/oboInOwl#",
    OBO_NAMESPACE + "IAO_",
    OBO_NAMESPACE + "RO_",
    OBO_NAMESPACE + "BFO_",
)
BOUNDARY_SUFFIXES = ("#", "/", "_")
# Derived ownership is widened to a dominant namespace when the ontology headers own *less than*
# ``MINOR_OWNED_PERCENT`` percent of the declared terms and one namespace holds *more than*
# ``DOMINANT_PERCENT`` percent of them.
MINOR_OWNED_PERCENT = 5
DOMINANT_PERCENT = 50
# File extensions an ontology IRI may carry (``…/automatce.ttl``), and ODK release suffixes
# (``…/automatce/automatce-full.ttl``); both are stripped when deriving the owned namespaces.
FILE_EXTENSIONS = (".owl", ".ttl", ".rdf", ".nt", ".n3", ".jsonld", ".json", ".ofn", ".omn", ".owx", ".obo")
RELEASE_SUFFIXES = ("-full", "-base", "-simple", "-merged", "-non-classified", "-basic", "-edit")


class OwnershipMode(Enum):
    """How ownership was decided for a run."""

    BASE = "base"
    DERIVED = "derived"
    ALL = "all"


def is_builtin(node: object) -> bool:
    """Return whether ``node`` is an RDF, RDFS, OWL or XSD vocabulary IRI."""
    return isinstance(node, URIRef) and str(node).startswith(BUILTIN_NAMESPACES)


def is_well_known(node: object) -> bool:
    """Return whether ``node`` is an IRI of a well-known vocabulary (:data:`WELL_KNOWN_NAMESPACES`)."""
    return isinstance(node, URIRef) and str(node).startswith(WELL_KNOWN_NAMESPACES)


def base_matches(base: str | None, node: object) -> bool:
    """Return whether ``node`` is a non-built-in IRI inside ``base`` (every such IRI when ``base`` is empty).

    A base ending in a letter or digit (``https://x.org/onto``) matches itself and ``base#...`` /
    ``base/...`` only, so it never swallows ``https://x.org/ontology``.  Any other base
    (``https://x.org/onto#``, ``https://x.org/onto/``, ``http://purl.obolibrary.org/obo/RO_``) is a
    plain prefix.
    """
    if not isinstance(node, URIRef) or is_builtin(node):
        return False
    if not base:
        return True
    iri = str(node)
    if base[-1].isalnum():
        return iri == base or iri.startswith((base + "#", base + "/"))
    return iri.startswith(base)


def derive_prefixes(ontologies: Iterable[URIRef]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return ``(exact, casefolded)`` namespace prefixes derived from ontology IRIs.

    Candidates per ontology IRI: the IRI itself; the IRI without a trailing ``#``/``/`` and without a
    file extension (:data:`FILE_EXTENSIONS`); for ``http://purl.obolibrary.org/obo/<name>.owl`` (or
    ``.../obo/<name>/<file>.owl``) the ID prefix ``http://purl.obolibrary.org/obo/<NAME>_``; and for any
    other IRI whose last segment is a file name, the ODK-style ID prefix ``<dir>/<NAME>_`` with the
    release suffix (:data:`RELEASE_SUFFIXES`) removed, so ``…/automatce/automatce-full.ttl`` owns
    ``…/automatce/AUTOMATCE_0000003``.  ID prefixes are matched case-insensitively.
    """
    exact: set[str] = set()
    folded: set[str] = set()
    for ontology in ontologies:
        iri = str(ontology)
        exact.add(iri)
        stripped = _strip_extension(iri.rstrip("#/"))
        if stripped:
            exact.add(stripped)
        if iri.startswith(OBO_NAMESPACE):
            name = _strip_extension(re.split(r"[/#]", iri[len(OBO_NAMESPACE) :])[0])
            if name:
                folded.add((OBO_NAMESPACE + name + "_").casefold())
        elif (id_prefix := _file_id_prefix(iri)) is not None:
            folded.add(id_prefix.casefold())
    return tuple(sorted(exact)), tuple(sorted(folded))


def _strip_extension(iri: str) -> str:
    """``iri`` without a trailing ontology file extension (``.owl``, ``.ttl``, ...)."""
    for extension in FILE_EXTENSIONS:
        if iri.endswith(extension):
            return iri.removesuffix(extension)
    return iri


def _file_id_prefix(iri: str) -> str | None:
    """``<dir>/<NAME>_`` for an IRI ending in a file name with an extension, as ODK names its releases."""
    if "#" in iri:
        return None
    directory, _slash, last = iri.rpartition("/")
    name = _strip_extension(last)
    if not directory or name == last or not name:
        return None
    for suffix in RELEASE_SUFFIXES:
        name = name.removesuffix(suffix)
    return f"{directory}/{name}_" if name else None


def namespace_of_iri(iri: str) -> str | None:
    """Return ``iri`` up to and including its last ``#`` or ``/`` (``None`` when it has neither)."""
    cut = max(iri.rfind("#"), iri.rfind("/"))
    return iri[: cut + 1] if cut >= 0 else None


def _prefix_matches(iri: str, prefix: str) -> bool:
    """Prefix match that, for prefixes not ending in ``#``, ``/`` or ``_``, requires a name boundary."""
    if not iri.startswith(prefix):
        return False
    return prefix.endswith(BOUNDARY_SUFFIXES) or len(iri) == len(prefix) or iri[len(prefix)] in BOUNDARY_SUFFIXES


def _dominant_namespace(terms: list[URIRef]) -> str | None:
    """Return the namespace holding more than :data:`DOMINANT_PERCENT` percent of ``terms``, if any."""
    counts = Counter(ns for term in terms if (ns := namespace_of_iri(str(term))) is not None)
    if not counts:
        return None
    # Ties cannot exceed 50%, so the order among equal counts never matters.
    namespace, count = counts.most_common(1)[0]
    return namespace if count * 100 > DOMINANT_PERCENT * len(terms) else None


@dataclass(frozen=True)
class Ownership:
    """Decides whether an IRI belongs to the linted ontology."""

    mode: OwnershipMode = OwnershipMode.ALL
    base: str | None = None
    prefixes: tuple[str, ...] = ()
    folded_prefixes: tuple[str, ...] = ()
    base_selected_nothing: bool = False
    dominant_namespace: str | None = None
    borrows_well_known: bool = False  # in ALL mode: well-known vocabulary terms are not owned

    @classmethod
    def for_terms(cls, base: str | None, ontologies: Iterable[URIRef], declared: Iterable[URIRef]) -> Ownership:
        """Choose ownership for a file with the given ``ontologies`` and declared terms."""
        declared_terms = [term for term in dict.fromkeys(declared) if not is_builtin(term)]
        if base is not None:
            nothing = bool(base) and bool(declared_terms) and not any(base_matches(base, t) for t in declared_terms)
            return cls(OwnershipMode.BASE, base, base_selected_nothing=nothing)
        exact, folded = derive_prefixes(ontologies)
        derived = cls(OwnershipMode.DERIVED, None, exact, folded)
        # Borrowed well-known terms do not decide, unless the file declares nothing else; a well-known
        # namespace that dominates the declarations is the vocabulary being linted (schema.org itself).
        overall = _dominant_namespace(declared_terms)
        own_kind = [
            term
            for term in declared_terms
            if derived.owns(term) or not is_well_known(term) or namespace_of_iri(str(term)) == overall
        ]
        borrows = bool(own_kind) and len(own_kind) < len(declared_terms)
        declared_terms = own_kind or declared_terms
        owned = sum(derived.owns(term) for term in declared_terms)
        dominant = _dominant_namespace(declared_terms)
        if not owned:
            if dominant is None:
                return cls(borrows_well_known=borrows)
            return cls(
                OwnershipMode.DERIVED, None, tuple(sorted({*exact, dominant})), folded, dominant_namespace=dominant
            )
        if owned * 100 < MINOR_OWNED_PERCENT * len(declared_terms) and dominant is not None:
            return cls(
                OwnershipMode.DERIVED, None, tuple(sorted({*exact, dominant})), folded, dominant_namespace=dominant
            )
        return derived

    def owns(self, node: object) -> bool:
        """Return whether ``node`` is an IRI owned by the linted ontology."""
        if not isinstance(node, URIRef):
            return False
        if self.mode is OwnershipMode.BASE:
            return base_matches(self.base, node)
        if is_builtin(node):
            return False
        if self.mode is OwnershipMode.ALL:
            return not (self.borrows_well_known and is_well_known(node))
        iri = str(node)
        return any(_prefix_matches(iri, p) for p in self.prefixes) or any(
            _prefix_matches(iri.casefold(), p) for p in self.folded_prefixes
        )
