"""Named graphs of an RDF dataset: which graphs of a TriG, N-Quads or JSON-LD file state each triple.

ontolint lints a dataset as the union of its graphs (see :data:`ontolint.loader.DATASET_FORMATS`), so the
linted graph no longer says where a triple was written.  The loader records it in a :class:`GraphIndex`
before merging: for every triple, the sorted names of the graphs that state it.  A triple stated in two
graphs belongs to both.

A file with no triple outside its default graph (every Turtle, N-Triples or RDF/XML file, and a dataset
that uses only the default graph) gets the empty index, so nothing about graphs reaches its reports.

Graph names never depend on where or how the file was read:

* the default graph is :data:`DEFAULT_GRAPH`;
* an IRI is itself, except a ``file:`` one, such as a relative reference resolved against the file
  (``<rel> { }``, ``<../g> { }``, ``<#g> { }``): that is the reference relative to the file (``rel``,
  ``../g``, ``#g``), never a ``file:`` IRI holding the reader's local path;
* a blank node has a fresh parser label on every parse, so it is named by its content instead:
  ``_:`` and the start of the SHA-256 of its triples, written with every blank node as ``_:``.  Two
  blank graphs with the same triples share the name.

An empty named graph states no triple and so has no name anywhere.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, cast

from rdflib import BNode
from rdflib.graph import DATASET_DEFAULT_GRAPH_ID
from rdflib.store import Store
from rdflib.term import Identifier, Node

from .rules.support import STABLE_ID_LENGTH

DEFAULT_GRAPH = "(default graph)"
"""The name of a dataset's default graph (parenthesised like ``(ontology)``, so no IRI can collide with it)."""

Triple = tuple[Node, Node, Node]


@dataclass(frozen=True)
class GraphIndex:
    """Which graphs of an RDF dataset state each triple; empty for a file with only a default graph."""

    triples: Mapping[Triple, tuple[str, ...]] = field(default_factory=dict[Triple, tuple[str, ...]])
    """The sorted names of the graphs stating each triple."""

    @property
    def names(self) -> tuple[str, ...]:
        """Every graph that states a triple, sorted (:data:`DEFAULT_GRAPH` first)."""
        return tuple(sorted({name for names in self.triples.values() for name in names}))


EMPTY_INDEX = GraphIndex()
"""The index of a file with only a default graph."""


def _is_default(identifier: Node, default: Node) -> bool:
    # Parsing into a plain Graph puts the default graph's triples in that graph's own context; a Dataset uses
    # rdflib's fixed identifier, which an rdflib upgrade could make the parsers use instead.
    return identifier in (default, DATASET_DEFAULT_GRAPH_ID)


def relative_reference(iri: str, base: str) -> str | None:
    """The relative reference that resolves against ``base`` to the ``file:`` IRI ``iri``, else ``None``.

    ``None`` unless both are ``file:`` IRIs on the same host, and for a path holding a dot segment, which
    resolution removes, or an empty segment (``//``), which resolvers disagree on.  A reference into
    ``base``'s own document is only its query or fragment (``#frag``); one above its directory starts
    with ``../``.
    """
    prefix = "file://"
    if not (iri.startswith(prefix) and base.startswith(prefix)):
        return None
    host, slash, rest = iri[len(prefix) :].partition("/")
    base_host, _, base_rest = base[len(prefix) :].partition("/")
    if host != base_host or not slash:
        return None
    end = min((at for at in (rest.find("?"), rest.find("#")) if at >= 0), default=len(rest))
    segments, suffix = rest[:end].split("/"), rest[end:]
    if "." in segments or ".." in segments or "" in segments[:-1]:
        return None
    base_segments = base_rest.split("?")[0].split("#")[0].split("/")
    if segments == base_segments and suffix:
        return suffix
    directory = base_segments[:-1]
    common = 0
    for ours, theirs in zip(directory, segments[:-1], strict=False):
        if ours != theirs:
            break
        common += 1
    ups, tail = len(directory) - common, segments[common:]
    reference = "../" * ups + "/".join(tail)
    if not ups and (not reference or ":" in tail[0]):
        reference = "./" + reference  # neither "" nor "a:b" would read as a relative path
    return reference + suffix


def graph_name(identifier: Node, triples: Sequence[Triple], base: str) -> str:
    """The reported name of the named graph ``identifier``, which states ``triples``, in the file ``base``.

    ``base`` is the file's ``file:`` URI, which its relative references resolved against.
    """
    if isinstance(identifier, BNode):
        lines = sorted(
            " ".join("_:" if isinstance(t, BNode) else cast(Identifier, t).n3() for t in triple) for triple in triples
        )
        digest = hashlib.sha256("\n".join(lines).encode("utf-8", "surrogatepass")).hexdigest()
        return "_:" + digest[:STABLE_ID_LENGTH]
    text = str(identifier)
    return relative_reference(text, base) or text


def build_graph_index(store: Store, default: Node, base: str) -> GraphIndex:
    """Index the graphs of a freshly parsed dataset; ``default`` is the identifier of its default graph.

    ``base`` is the file's ``file:`` URI (see :func:`graph_name`).

    Must run before the named graphs are merged into the default one.  Returns :data:`EMPTY_INDEX` when no
    named graph holds a triple.
    """
    members: dict[Node, list[Triple]] = {}
    for triple, contexts in store.triples((None, None, None), None):
        for context in contexts:
            identifier = default if context is None else context.identifier
            members.setdefault(identifier, []).append(triple)
    if all(_is_default(identifier, default) for identifier in members):
        return EMPTY_INDEX
    names = {
        identifier: DEFAULT_GRAPH if _is_default(identifier, default) else graph_name(identifier, triples, base)
        for identifier, triples in members.items()
    }
    stated: dict[Triple, set[str]] = {}
    for identifier, triples in members.items():
        for triple in triples:
            stated.setdefault(triple, set()).add(names[identifier])
    shared: dict[frozenset[str], tuple[str, ...]] = {}  # one tuple per combination of graphs, not per triple
    return GraphIndex({t: shared.setdefault(frozenset(n), tuple(sorted(n))) for t, n in stated.items()})


# --- the parse worker's reply ---------------------------------------------------------------------------------


def encode_index(index: GraphIndex, triples: Sequence[Triple]) -> dict[str, Any]:
    """``index`` as plain JSON data: the graph names, then per triple of ``triples`` (in order) their positions."""
    names = index.names
    position = {name: i for i, name in enumerate(names)}
    return {"names": list(names), "of": [[position[n] for n in index.triples.get(t, ())] for t in triples]}


def decode_index(payload: object, triples: Sequence[Triple]) -> GraphIndex:
    """The index :func:`encode_index` encoded over ``triples`` (``None``: a file with no named graph).

    Raises ``ValueError`` when ``payload`` does not have the encoded shape.
    """
    if payload is None:
        return EMPTY_INDEX
    if not isinstance(payload, dict):
        raise ValueError("the graph index is not an object")
    document = cast(dict[str, object], payload)
    names, of = document.get("names"), document.get("of")
    if not isinstance(names, list) or not all(isinstance(name, str) for name in cast(list[object], names)):
        raise ValueError("the graph names are not a list of strings")
    if not isinstance(of, list) or len(cast(list[object], of)) != len(triples):
        raise ValueError("the graph index does not list every triple")
    known = cast(list[str], names)
    shared: dict[tuple[int, ...], tuple[str, ...]] = {}
    index: dict[Triple, tuple[str, ...]] = {}
    # gremlin: pardon[equivalent] the lengths were compared above, so strict never fires
    for triple, positions in zip(triples, cast(list[object], of), strict=True):
        if not isinstance(positions, list):
            raise ValueError("a triple's graphs are not a list")
        key = tuple(cast(list[object], positions))
        if not all(isinstance(p, int) and 0 <= p < len(known) for p in key):
            raise ValueError("a triple names a graph that is not listed")
        if key:
            index[triple] = shared.setdefault(
                cast(tuple[int, ...], key), tuple(known[p] for p in cast(tuple[int, ...], key))
            )
    return GraphIndex(index)
