"""Vocabulary constants and small graph helpers shared by rule families."""

from __future__ import annotations

import re
from collections.abc import Set
from typing import cast

from rdflib import Graph, URIRef
from rdflib.namespace import DC, DCTERMS, RDF, RDFS, SKOS
from rdflib.term import Identifier, Node

DESCRIPTIONS = (RDFS.comment, SKOS.definition, DCTERMS.description, DC.description)
LABELS = (RDFS.label, SKOS.prefLabel)
META_LICENSE = (DCTERMS.license, URIRef("http://creativecommons.org/ns#license"))
META_CREATOR = (DCTERMS.creator, DC.creator, URIRef("http://www.w3.org/ns/prov#wasAttributedTo"))
MINIMUM_STYLE_SAMPLE_SIZE = 4
MINIMUM_SINGLE_CHILD_CHAIN_LENGTH = 3


def is_local(base: str | None, node: object) -> bool:
    """Return whether ``node`` is an IRI inside the configured base namespace."""
    if not isinstance(node, URIRef):
        return False
    if not base:
        return True
    iri = str(node)
    return (
        iri.startswith(base) if base.endswith(("#", "/")) else (iri == base or iri.startswith((base + "#", base + "/")))
    )


def local_name(iri: URIRef) -> str:
    """Return the fragment or last path segment of an IRI."""
    return re.split(r"[/#]", str(iri))[-1]


def directed_edges(g: Graph, predicate: Identifier, allowed: Set[URIRef]) -> set[tuple[URIRef, URIRef]]:
    """Return asserted ``predicate`` edges whose endpoints are both in ``allowed``."""
    return {
        (cast("URIRef", s), cast("URIRef", o)) for s, o in g.subject_objects(predicate) if s in allowed and o in allowed
    }


def list_items(g: Graph, head: Node, *, limit: int = 500) -> list[Node] | None:
    """Return the members of a well-formed RDF list, or ``None`` if it is invalid."""
    items: list[Node] = []
    seen: set[Node] = set()
    while head != RDF.nil and head not in seen and len(items) < limit:
        seen.add(head)
        firsts, rests = list(g.objects(head, RDF.first)), list(g.objects(head, RDF.rest))
        if len(firsts) != 1 or len(rests) != 1:
            return None  # Invalid lists are Meta-SHACL / OWL structural checks.
        items.append(firsts[0])
        head = rests[0]
    return items if head == RDF.nil else None
