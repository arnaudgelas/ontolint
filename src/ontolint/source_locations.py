"""Best-effort source positions for RDF terms retained by RDFLib parsing.

RDFLib graphs deliberately contain semantic nodes, not their lexical source positions.  This
module recovers positions only for syntaxes whose lexical forms can be identified safely after
parsing: Turtle/N3 and N-Triples/N-Quads.  It never guesses for RDF/XML or JSON-LD; callers then
simply omit the SARIF region.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import urljoin

from rdflib import BNode, Graph, URIRef
from rdflib.term import Node

from .models import Finding
from .reporting import Location
from .rules.support import stable_blank_id

_SUPPORTED_FORMATS = frozenset({"turtle", "n3", "nt", "nquads"})
_PREFIXED_NAME = re.compile(r"(?P<prefix>[A-Za-z][A-Za-z0-9_-]*|):(?P<local>(?:\\.|[^\s<>\"{}|^`\\])*)")
_BNODE = re.compile(r"_:(?P<label>[A-Za-z][A-Za-z0-9_-]*)")


@dataclass(frozen=True)
class SourceIndex:
    """The first lexical occurrence of each parsed RDF node in a supported source document."""

    locations: Mapping[Node, Location]

    def for_findings(self, graph: Graph, findings: Sequence[Finding]) -> dict[Finding, Location]:
        """Return locations keyed by finding, including stable identities used for blank-node focuses."""
        by_focus = {str(node): location for node, location in self.locations.items()}
        by_focus.update(
            {
                stable_blank_id(graph, node): location
                for node, location in self.locations.items()
                if isinstance(node, BNode)
            }
        )
        return {finding: by_focus[finding.focus] for finding in findings if finding.focus in by_focus}


def build_source_index(data: bytes, fmt: str, public_id: str, graph: Graph) -> SourceIndex:
    """Index term starts in ``data`` when ``fmt`` is supported, otherwise return no locations.

    Columns are one-based Unicode code points.  The SARIF renderer declares that unit explicitly.
    Parsing has already succeeded, so a token is retained only when it resolves to a node in ``graph``.
    """
    if fmt not in _SUPPORTED_FORMATS:
        return SourceIndex({})
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return SourceIndex({})
    graph_nodes = {node for triple in graph for node in triple}
    prefixes = {prefix or "": str(namespace) for prefix, namespace in graph.namespaces()}
    return SourceIndex(_scan(text, fmt, public_id, graph_nodes, prefixes))


def _scan(
    text: str, fmt: str, public_id: str, graph_nodes: set[Node], prefixes: Mapping[str, str]
) -> dict[Node, Location]:
    """Walk a supported RDF lexical stream, recording only terms that the parsed graph contains."""
    locations: dict[Node, Location] = {}
    index = 0
    while index < len(text):
        skipped = _skip_ignored(text, index)
        if skipped is not None:
            index = skipped
            continue
        char = text[index]
        if char == "<":
            end = _iri_end(text, index + 1)
            if end is None:
                break
            node = _resolve_iri(public_id, text[index + 1 : end])
            if node is not None:
                _record(locations, graph_nodes, node, text, index)
            index = end + 1
        elif (match := _BNODE.match(text, index)) is not None:
            _record(locations, graph_nodes, BNode(match["label"]), text, index)
            index = match.end()
        elif fmt in {"turtle", "n3"} and (match := _PREFIXED_NAME.match(text, index)) is not None:
            namespace = prefixes.get(match["prefix"])
            if namespace is not None:
                _record(locations, graph_nodes, URIRef(namespace + _unescape_local(match["local"])), text, index)
            index = match.end()
        else:
            index += 1
    return locations


def _skip_ignored(text: str, index: int) -> int | None:
    """Return the index after whitespace, a comment or a string literal, if one starts here."""
    char = text[index]
    if char.isspace():
        return index + 1
    if char == "#":
        newline = text.find("\n", index)
        return len(text) if newline < 0 else newline + 1
    if char in {"'", '"'}:
        return _skip_string(text, index)
    return None


def _record(locations: dict[Node, Location], graph_nodes: set[Node], node: Node, text: str, index: int) -> None:
    if node in graph_nodes and node not in locations:
        line = text.count("\n", 0, index) + 1
        previous_newline = text.rfind("\n", 0, index)
        locations[node] = Location(line, index - previous_newline)


def _resolve_iri(public_id: str, value: str) -> URIRef | None:
    """Resolve a lexical IRI reference without making a successful RDF parse fail during indexing."""
    try:
        return URIRef(urljoin(public_id, value))
    except ValueError:
        return None


def _iri_end(text: str, index: int) -> int | None:
    while index < len(text):
        if text[index] == "\\":
            index += 2
        elif text[index] == ">":
            return index
        else:
            index += 1
    return None


def _skip_string(text: str, index: int) -> int:
    quote = text[index]
    triple = text.startswith(quote * 3, index)
    marker = quote * (3 if triple else 1)
    index += len(marker)
    while index < len(text):
        if text[index] == "\\":
            index += 2
        elif text.startswith(marker, index):
            return index + len(marker)
        else:
            index += 1
    return len(text)


def _unescape_local(value: str) -> str:
    """Decode the Turtle punctuation escapes that can occur in a prefixed-name local part."""
    return re.sub(r"\\(.)", r"\1", value)
