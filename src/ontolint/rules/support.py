"""Vocabulary constants and small graph helpers shared by rule families."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Set
from typing import cast
from urllib.parse import SplitResult, urlsplit

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import DC, DCTERMS, RDF, RDFS, SKOS
from rdflib.term import Identifier, Node

from ontolint.ownership import base_matches

OBO = "http://purl.obolibrary.org/obo/"
PROV = "http://www.w3.org/ns/prov#"
# Definition-like annotations: OBO "definition" (IAO_0000115) and "elucidation" (IAO_0000600), PROV-O
# ``prov:definition``.  ``skos:scopeNote`` is deliberately not a definition.
DESCRIPTIONS = (
    RDFS.comment,
    SKOS.definition,
    DCTERMS.description,
    DC.description,
    URIRef(OBO + "IAO_0000115"),
    URIRef(OBO + "IAO_0000600"),
    URIRef(PROV + "definition"),
    # Common Core Ontologies 1.x define every term with their own annotation (CCO 2 uses skos:definition).
    URIRef("http://www.ontologyrepository.com/CommonCoreOntologies/definition"),
)
LABELS = (RDFS.label, SKOS.prefLabel)
META_LICENSE = (DCTERMS.license, URIRef("http://creativecommons.org/ns#license"))
META_CREATOR = (DCTERMS.creator, DC.creator, URIRef("http://www.w3.org/ns/prov#wasAttributedTo"))
MINIMUM_STYLE_SAMPLE_SIZE = 4
MINIMUM_SINGLE_CHILD_CHAIN_LENGTH = 3


def is_local(base: str | None, node: object) -> bool:
    """Return whether ``node`` is an IRI inside the configured base namespace (plain prefix match)."""
    return base_matches(base, node)


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


def safe_urlsplit(iri: str) -> SplitResult:
    """Split ``iri`` like :func:`urllib.parse.urlsplit`, but return an empty split for an unparsable IRI.

    ``urlsplit`` raises :class:`ValueError` for IRIs such as ``s://]`` (invalid bracketed host); rules must
    treat those as "no scheme, host, path, query or fragment" rather than crash.
    """
    try:
        return urlsplit(iri)
    except ValueError:
        return SplitResult("", "", "", "", "")


# Blank nodes are followed upwards (restriction -> class, list node -> list owner) at most this far.
OWNER_DEPTH = 8
# ... and downwards at most this far when computing a blank node's content digest.
DIGEST_DEPTH = 6
STABLE_ID_LENGTH = 12


def owning_term(g: Graph, node: Node) -> Node:
    """Return the named term a blank node (restriction, expression, list cell) belongs to, else ``node``.

    Walks upwards through incoming triples, preferring the first IRI subject found in sorted order, so
    the answer is deterministic; ``rdf:rest``/``rdf:first`` hops climb to the list head.
    """
    if not isinstance(node, BNode):
        return node
    seen: set[Node] = set()
    frontier: list[Node] = [node]
    for _ in range(OWNER_DEPTH):
        parents = sorted(
            {s for n in frontier for s in g.subjects(None, n) if s not in seen},
            key=str,
        )
        if not parents:
            return node
        named = [s for s in parents if isinstance(s, URIRef)]
        if named:
            return named[0]
        seen.update(frontier)
        frontier = parents
    return node


def _content_digest(g: Graph, node: Node, depth: int, path: frozenset[Node]) -> str:
    """Label-free description of ``node``: IRIs and literals verbatim, blank nodes by their own content."""
    if isinstance(node, Literal):
        return "L" + node.n3()
    if not isinstance(node, BNode):
        return "I" + str(node)
    if node in path or depth <= 0:
        return "B"
    inner = path | {node}
    edges = sorted(f"{p}>{_content_digest(g, o, depth - 1, inner)}" for p, o in g.predicate_objects(node))
    return "B(" + ";".join(edges) + ")"


def stable_blank_id(g: Graph, node: Node) -> str:
    """Return a ``_:``-prefixed identity of ``node`` that depends on content and place, never on its label.

    The identity hashes the nearest named owner (see :func:`owning_term`), the predicates through which the
    node is referenced and the blank node's own reachable content, so the same file always yields the
    same identity however the parser labelled its blank nodes.
    """
    owner = owning_term(g, node)
    owner_text = "" if owner == node else str(owner)
    incoming = sorted({str(p) for _s, p in g.subject_predicates(node)})
    payload = "\x00".join([owner_text, ",".join(incoming), _content_digest(g, node, DIGEST_DEPTH, frozenset())])
    return "_:" + hashlib.sha256(payload.encode("utf-8", "surrogatepass")).hexdigest()[:STABLE_ID_LENGTH]


def relative_reference(iri: str, bases: tuple[str, ...]) -> str | None:
    """``iri`` as the relative reference it was written as, when it resolved under one of ``bases``.

    A relative IRI (``<model/X.ttl>``) parsed from a local file becomes ``file:///…/model/X.ttl``: an
    artefact of where the file was read, which must neither be reported as an unsafe ``file:`` IRI nor
    printed with the reader's local path.
    """
    for base in bases:
        if iri.startswith(base):
            return iri[len(base) :]
    return None


def display_iri(iri: str, bases: tuple[str, ...]) -> str:
    """``iri`` for a message: relative to the linted file when it came from a relative reference."""
    relative = relative_reference(iri, bases)
    return iri if relative is None else relative


ONTOLOGY_IRI = URIRef("http://www.w3.org/2002/07/owl#ontologyIRI")


def describing_nodes(g: Graph, ontology: Node) -> list[Node]:
    """``ontology`` and every node that names it with ``owl:ontologyIRI`` and so carries its metadata.

    A metadata vocabulary may describe an ontology on a separate node (MOD puts its title, licence and
    creators on ``<https://w3id.org/mod#>``, which says ``owl:ontologyIRI <https://w3id.org/mod>``).
    """
    return [ontology, *sorted(g.subjects(ONTOLOGY_IRI, ontology), key=str)]


SHAPES_BLANK_NODE = "(blank node)"


def shape_term(node: Node) -> Node | str:
    """``node`` of a shapes graph as a finding subject: a blank node there has no stable identity, so it is a key.

    A finding's blank nodes are named by their content in the data graph (:func:`stable_blank_id`), which
    a shapes-graph node is not part of.
    """
    return SHAPES_BLANK_NODE if isinstance(node, BNode) else node


_NT_ESCAPES = str.maketrans({"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r"})
"""What N-Triples escapes in a quoted string (``Literal.n3()`` would write a multi-line value as a long string)."""


def ntriples_literal(literal: Literal) -> str:
    """``literal`` as an N-Triples term on one line: quoted, then ``@lang`` or ``^^<datatype>`` when it has one."""
    quoted = f'"{str(literal).translate(_NT_ESCAPES)}"'
    if literal.language:
        return f"{quoted}@{literal.language}"
    return f"{quoted}^^<{literal.datatype}>" if literal.datatype else quoted


def term_text(node: Node) -> str:
    """``node`` for a message: an IRI bare, a blank node as ``_:label``, a literal by :func:`ntriples_literal`.

    The literal is rdflib's ``n3()`` for every value without a line break; a line break is escaped where ``n3()``
    would triple-quote the value, so a message stays on one line.  ``RuleContext`` rewrites ``_:label`` to the
    blank node's stable identity.  Never a Python repr.
    """
    if isinstance(node, Literal):
        return ntriples_literal(node)
    return f"_:{node}" if isinstance(node, BNode) else str(node)


# An authority's userinfo, after ``scheme://`` and before the first ``@`` of the authority (RFC 3986 3.2.1).
_USERINFO = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*://([^/?#@]*)@")
PASSWORD_MASK = "****"  # noqa: S105 -- what replaces a password, not one


def _credentials(iri: str) -> tuple[re.Match[str], str] | None:
    """The userinfo match and user of an IRI whose userinfo has a non-empty part after its first ``:``."""
    match = _USERINFO.match(iri)
    if match is None:
        return None
    user, separator, password = match.group(1).partition(":")
    return (match, user) if separator and password else None


def password_user(iri: str) -> str | None:
    """The user name of ``iri`` when its authority embeds a password (``https://user:pw@...``), else ``None``."""
    found = _credentials(iri)
    return None if found is None else found[1]


def redact_password(iri: str) -> str:
    """``iri`` with everything after the first ``:`` of its userinfo replaced by :data:`PASSWORD_MASK`.

    RFC 3986 section 3.2.1 says not to render that data.  The user, host, port, path, query and fragment are
    kept, and ``*`` is a userinfo sub-delimiter, so the result is still an IRI; an IRI without a password is
    returned unchanged, so the function is idempotent.
    """
    found = _credentials(iri)
    if found is None:
        return iri
    match, user = found
    return f"{iri[: match.start(1)]}{user}:{PASSWORD_MASK}{iri[match.end(1) :]}"
