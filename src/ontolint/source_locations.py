"""Best-effort source positions for RDF terms retained by RDFLib parsing.

RDFLib graphs deliberately contain semantic nodes, not their lexical source positions. This
module recovers positions from Turtle/N3, N-Triples/N-Quads and RDF/XML syntax, and from explicit
JSON-LD ``@id`` values. Nodes with no unambiguous source construct simply have no SARIF region.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import urljoin
from xml.sax import handler, make_parser
from xml.sax.xmlreader import AttributesNSImpl

from rdflib import BNode, Graph, URIRef
from rdflib.term import Node

from .models import Finding
from .reporting import Location
from .rules.support import stable_blank_id

_TEXT_FORMATS = frozenset({"turtle", "n3", "nt", "nquads"})
_XML_FORMATS = frozenset({"xml", "application/rdf+xml"})
_JSON_FORMATS = frozenset({"json-ld", "application/ld+json"})
_PREFIXED_NAME = re.compile(r"(?P<prefix>[A-Za-z][A-Za-z0-9_-]*|):(?P<local>(?:\\.|[^\s<>\"{}|^`\\])*)")
_BNODE = re.compile(r"_:(?P<label>[A-Za-z][A-Za-z0-9_-]*)")
_RDF_ABOUT = "http://www.w3.org/1999/02/22-rdf-syntax-ns#about"
_RDF_ID = "http://www.w3.org/1999/02/22-rdf-syntax-ns#ID"
_RDF_RESOURCE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#resource"
_XML_BASE = "http://www.w3.org/XML/1998/namespacebase"


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
    if fmt in _XML_FORMATS:
        return SourceIndex(_xml_locations(data, public_id, graph))
    if fmt in _JSON_FORMATS:
        return SourceIndex(_jsonld_locations(data, public_id, graph))
    if fmt not in _TEXT_FORMATS:
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


class _RDFXMLLocator(handler.ContentHandler):
    """Collect RDF/XML resource positions from SAX events without changing the RDF parser's semantics."""

    def __init__(self, public_id: str, graph_nodes: set[Node]) -> None:
        self.base = public_id
        self.bases: list[str] = []
        self.graph_nodes = graph_nodes
        self.locations: dict[Node, Location] = {}

    def setDocumentLocator(self, locator: object) -> None:  # noqa: N802 -- SAX callback spelling.
        self.locator = locator

    def startElementNS(  # noqa: N802 -- SAX callback spelling.
        self, name: tuple[str | None, str], qname: str | None, attrs: AttributesNSImpl
    ) -> None:
        values = {f"{key[0] or ''}{key[1]}": value for key, value in attrs.items()}
        self.bases.append(self.base)
        if xml_base := values.get(_XML_BASE):
            self.base = urljoin(self.base, xml_base)
        for attr in (_RDF_ABOUT, _RDF_RESOURCE):
            if value := values.get(attr):
                self._record(URIRef(urljoin(self.base, value)))
        if value := values.get(_RDF_ID):
            self._record(URIRef(urljoin(self.base, f"#{value}")))

    def endElementNS(self, name: tuple[str | None, str], qname: str | None) -> None:  # noqa: N802 -- SAX callback spelling.
        self.base = self.bases.pop()

    def _record(self, node: Node) -> None:
        if node in self.graph_nodes and node not in self.locations:
            self.locations[node] = Location(self.locator.getLineNumber(), self.locator.getColumnNumber() + 1)  # type: ignore[attr-defined]


def _xml_locations(data: bytes, public_id: str, graph: Graph) -> dict[Node, Location]:
    """Collect element-start positions for RDF/XML IRIs with a non-resolving SAX parser."""
    try:
        parser = make_parser()  # noqa: S317 -- DTD/entity preflight runs before this non-resolving auxiliary scan.
        parser.setFeature(handler.feature_namespaces, True)
        for feature in (handler.feature_external_ges, handler.feature_external_pes):
            with contextlib.suppress(NotImplementedError, ValueError):
                parser.setFeature(feature, False)
        collector = _RDFXMLLocator(public_id, {node for triple in graph for node in triple})
        parser.setContentHandler(collector)
        parser.parse(io.BytesIO(data))
    except Exception:  # A successful RDFLib parse remains authoritative if the auxiliary locator disagrees.
        return {}
    return collector.locations


def _jsonld_locations(data: bytes, public_id: str, graph: Graph) -> dict[Node, Location]:
    """Map explicit JSON-LD ``@id`` strings, including local compact-IRI contexts, to graph nodes."""
    try:
        text = data.decode("utf-8-sig")
        document = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    locations: dict[Node, Location] = {}
    graph_nodes = {node for triple in graph for node in triple}
    for value, offset in _json_id_values(text, document, public_id):
        node = _resolve_iri(public_id, value)
        if node is not None:
            _record(locations, graph_nodes, node, text, offset)
    return locations


def _json_id_values(  # noqa: C901 -- mirrors JSON's recursive shape.
    text: str, document: object, public_id: str
) -> list[tuple[str, int]]:
    """Return physical offsets of explicit ``@id`` values after simple local-context expansion."""
    found: list[tuple[str, int]] = []
    decoder = json.JSONDecoder()

    def whitespace(index: int) -> int:
        while index < len(text) and text[index].isspace():
            index += 1
        return index

    def value(index: int, current: object, base: str, terms: Mapping[str, str]) -> int:
        index = whitespace(index)
        if isinstance(current, dict):
            base, terms = _json_context(current.get("@context"), base, terms)
            index += 1
            while text[index] != "}":
                index = whitespace(index)
                raw_key, index = decoder.raw_decode(text, index)
                index = whitespace(index + 1)
                child = current.get(raw_key)
                start = index
                index = value(index, child, base, terms)
                raw_child, _end = decoder.raw_decode(text, start)
                if raw_key == "@id" and isinstance(raw_child, str):
                    found.append((_expand_jsonld_id(raw_child, base, terms), start))
                index = whitespace(index)
                if text[index] == ",":
                    index += 1
                else:
                    break
            return index + 1
        if isinstance(current, list):
            index += 1
            for child in current:
                index = value(index, child, base, terms)
                index = whitespace(index)
                if text[index] == ",":
                    index += 1
            return index + 1
        _unused, index = decoder.raw_decode(text, index)
        return index

    value(0, document, public_id, {})
    return found


def _json_context(raw: object, base: str, inherited: Mapping[str, str]) -> tuple[str, dict[str, str]]:
    """Apply the location-relevant part of a local JSON-LD context (base and compact-IRI prefixes)."""
    terms = dict(inherited)
    entries = raw if isinstance(raw, list) else [raw]
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if isinstance(entry.get("@base"), str):
            base = urljoin(base, entry["@base"])
        for name, definition in entry.items():
            value = definition.get("@id") if isinstance(definition, dict) else definition
            if not name.startswith("@") and isinstance(value, str):
                terms[name] = _expand_jsonld_id(value, base, terms)
    return base, terms


def _expand_jsonld_id(value: str, base: str, terms: Mapping[str, str]) -> str:
    """Expand an explicit compact IRI without inventing a mapping for an unknown term."""
    prefix, separator, local = value.partition(":")
    if separator and prefix in terms:
        return terms[prefix] + local
    return urljoin(base, value)
