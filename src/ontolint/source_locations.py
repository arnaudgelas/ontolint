"""Best-effort source positions for RDF terms retained by RDFLib parsing.

RDFLib graphs deliberately contain semantic nodes, not their lexical source positions. This
module recovers positions from Turtle/N3, N-Triples/N-Quads and RDF/XML syntax, and from explicit
JSON-LD ``@id`` values. Nodes with no unambiguous source construct simply have no SARIF region.
"""

from __future__ import annotations

import bisect
import contextlib
import io
import json
import logging
import re
from collections.abc import Callable, Mapping, Sequence
from urllib.parse import urljoin
from xml.sax import SAXException, handler, make_parser
from xml.sax.xmlreader import AttributesNSImpl

from rdflib import BNode, Graph, URIRef
from rdflib.term import Node

from .models import Finding
from .reporting import Location
from .rules.support import redact_password, stable_blank_id

_TEXT_FORMATS = frozenset({"turtle", "n3", "nt", "nquads"})
_XML_FORMATS = frozenset({"xml", "application/rdf+xml"})
_JSON_FORMATS = frozenset({"json-ld", "application/ld+json"})
_PREFIXED_NAME = re.compile(r"(?P<prefix>[A-Za-z][A-Za-z0-9_-]*|):(?P<local>(?:\\.|[^\s<>\"{}|^`\\])*)")
_BNODE = re.compile(r"_:(?P<label>[A-Za-z][A-Za-z0-9_-]*)")
# Turtle/N3 directives declare namespaces; the IRIs they mention are not statements about a node.
_DIRECTIVE = re.compile(r"(?:@prefix|(?i:prefix))\s+[^\s:<>]*:\s*<[^>]*>\s*\.?|(?:@base|(?i:base))\s+<[^>]*>\s*\.?")
_RDF_ABOUT = "http://www.w3.org/1999/02/22-rdf-syntax-ns#about"
_RDF_ID = "http://www.w3.org/1999/02/22-rdf-syntax-ns#ID"
_RDF_RESOURCE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#resource"
_XML_BASE = "http://www.w3.org/XML/1998/namespacebase"
_LOG = logging.getLogger(__name__)


class SourceIndex:
    """The first lexical occurrence of each parsed RDF node in a supported source document.

    The positions are computed on first access to :attr:`locations`, so a run that never renders
    SARIF never pays for them.  A locator error costs only the positions: :attr:`locations` is then
    empty and :attr:`problem` says why.
    """

    def __init__(
        self,
        locations: Mapping[Node, Location] | None = None,
        *,
        build: Callable[[], Mapping[Node, Location]] | None = None,
    ) -> None:
        self._locations = locations
        self._build = build
        self._problem: str | None = None

    @property
    def locations(self) -> Mapping[Node, Location]:
        if self._locations is None:
            try:
                self._locations = self._build() if self._build is not None else {}
            except Exception as exc:  # noqa: BLE001 -- a locator bug costs SARIF regions, never the run.
                _LOG.debug("source locations unavailable", exc_info=True)
                self._problem = f"{type(exc).__name__}: {exc}"
                self._locations = {}
            self._build = None
        return self._locations

    @property
    def problem(self) -> str | None:
        """Why the positions could not be computed, or ``None``; resolves :attr:`locations` first."""
        _ = self.locations
        return self._problem

    def for_findings(self, graph: Graph, findings: Sequence[Finding]) -> dict[Finding, Location]:
        """Return locations keyed by finding, including stable identities used for blank-node focuses.

        An IRI with a password is also keyed by its masked spelling (SEC014's focus), at its first occurrence;
        an IRI that is itself spelled with the mask keeps its own position.
        """
        by_focus = {str(node): location for node, location in self.locations.items()}
        by_focus.update(
            {
                stable_blank_id(graph, node): location
                for node, location in self.locations.items()
                if isinstance(node, BNode)
            }
        )
        for node, location in self.locations.items():
            if isinstance(node, URIRef):
                by_focus.setdefault(redact_password(str(node)), location)
        return {finding: by_focus[finding.focus] for finding in findings if finding.focus in by_focus}


def build_source_index(data: bytes, fmt: str, public_id: str, graph: Graph) -> SourceIndex:
    """Index term starts in ``data`` when ``fmt`` is supported, otherwise return no locations.

    Columns are one-based Unicode code points.  The SARIF renderer declares that unit explicitly.
    Parsing has already succeeded, so a token is retained only when it resolves to a node in ``graph``.
    Locations are auxiliary: the parse has already succeeded, so a locator error must never fail the
    lint (see :class:`SourceIndex`).  Nothing is computed until the positions are first read.
    """
    return SourceIndex(build=lambda: _locations(data, fmt, public_id, graph))


def _locations(data: bytes, fmt: str, public_id: str, graph: Graph) -> dict[Node, Location]:
    if fmt in _XML_FORMATS:
        return _xml_locations(data, public_id, graph)
    if fmt in _JSON_FORMATS:
        return _jsonld_locations(data, public_id, graph)
    if fmt not in _TEXT_FORMATS:
        return {}
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return {}
    graph_nodes = {node for triple in graph for node in triple}
    prefixes = {prefix or "": str(namespace) for prefix, namespace in graph.namespaces()}
    return _scan(text, fmt, public_id, graph_nodes, prefixes)


class _Lines:
    """Turn character offsets into one-based line and column numbers, in logarithmic time."""

    def __init__(self, text: str) -> None:
        self.starts = [0, *(match.end() for match in re.finditer("\n", text))]

    def location(self, index: int) -> Location:
        line = bisect.bisect_right(self.starts, index)
        return Location(line, index - self.starts[line - 1] + 1)


def _scan(
    text: str, fmt: str, public_id: str, graph_nodes: set[Node], prefixes: Mapping[str, str]
) -> dict[Node, Location]:
    """Walk a supported RDF lexical stream, recording only terms that the parsed graph contains."""
    locations: dict[Node, Location] = {}
    lines = _Lines(text)
    index = 0
    while index < len(text):
        skipped = _skip_ignored(text, index)
        if skipped is not None:
            index = skipped
            continue
        if fmt in {"turtle", "n3"} and (directive := _directive_end(text, index)) is not None:
            index = directive
            continue
        char = text[index]
        if char == "<":
            # gremlin: pardon[equivalent] starting one character earlier only rescans the "<" itself
            end = _iri_end(text, index + 1)
            if end is None:
                break
            node = _resolve_iri(public_id, text[index + 1 : end])
            if node is not None:
                _record(locations, graph_nodes, node, lines, index)
            index = end + 1
        elif (match := _BNODE.match(text, index)) is not None:
            _record(locations, graph_nodes, BNode(match["label"]), lines, index)
            index = match.end()
        elif fmt in {"turtle", "n3"} and (match := _PREFIXED_NAME.match(text, index)) is not None:
            namespace = prefixes.get(match["prefix"])
            if namespace is not None:
                _record(locations, graph_nodes, URIRef(namespace + _unescape_local(match["local"])), lines, index)
            index = match.end()
        else:
            index += 1
    return locations


def _skip_ignored(text: str, index: int) -> int | None:
    """Return the index after a comment or a string literal, if one starts here.

    Whitespace needs no case: no token starts with it, so the scan simply steps over it.
    """
    char = text[index]
    if char == "#":
        return (text.find("\n", index) + 1) or len(text)  # find() gives -1 for a comment at the very end
    if char in {"'", '"'}:
        return _skip_string(text, index)
    return None


def _directive_end(text: str, index: int) -> int | None:
    """Return the index after a ``@prefix``/``PREFIX``/``@base``/``BASE`` directive starting here.

    The scan only reaches ``index`` at a token boundary (names, IRIs, strings and comments are
    consumed whole), so a keyword here cannot be the tail of a longer word.
    """
    match = _DIRECTIVE.match(text, index)
    return match.end() if match else None


def _record(locations: dict[Node, Location], graph_nodes: set[Node], node: Node, lines: _Lines, index: int) -> None:
    if node in graph_nodes and node not in locations:
        locations[node] = lines.location(index)


def _join(base: str, reference: str) -> str | None:
    """Resolve ``reference`` against ``base``, or ``None`` when Python cannot split it.

    RDF accepts IRIs such as ``s://]`` that :func:`urllib.parse.urljoin` rejects with ``ValueError``; such
    an IRI must cost only its own region, never every region of the file.
    """
    try:
        return urljoin(base, reference)
    except ValueError:
        return None


def _resolve_iri(public_id: str, value: str) -> URIRef | None:
    """Resolve a lexical IRI reference without making a successful RDF parse fail during indexing."""
    joined = _join(public_id, value)
    return None if joined is None else URIRef(joined)


def _iri_end(text: str, index: int) -> int | None:
    # gremlin: pardon[equivalent] the parse succeeded, so a ">" always ends the IRI before the text does
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
    # gremlin: pardon[equivalent] the parse succeeded, so the closing quote comes before the end of the text
    while index < len(text):
        if text[index] == "\\":
            index += 2
        elif text.startswith(marker, index):
            return index + len(marker)
        else:
            index += 1
    # gremlin: pardon[equivalent] the parse succeeded, so every string is closed and this is unreachable
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
        if (xml_base := values.get(_XML_BASE)) and (joined := _join(self.base, xml_base)) is not None:
            self.base = joined
        references = [values.get(attr) for attr in (_RDF_ABOUT, _RDF_RESOURCE)]  # "" is the base IRI
        if value := values.get(_RDF_ID):
            references.append(f"#{value}")
        for reference in references:
            if reference is not None and (node := _resolve_iri(self.base, reference)) is not None:
                self._record(node)

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
    except SAXException:  # A successful RDFLib parse remains authoritative if the auxiliary scan disagrees.
        return {}
    return collector.locations


def _jsonld_locations(data: bytes, public_id: str, graph: Graph) -> dict[Node, Location]:
    """Map explicit JSON-LD ``@id`` strings, including local compact-IRI contexts, to graph nodes."""
    try:
        text = data.decode("utf-8-sig")
        document = json.loads(text, object_pairs_hook=_Pairs)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    locations: dict[Node, Location] = {}
    graph_nodes = {node for triple in graph for node in triple}
    lines = _Lines(text)
    for value, offset in _json_id_values(text, document, public_id):
        node = _resolve_iri(public_id, value)
        if node is not None:
            _record(locations, graph_nodes, node, lines, offset)
    return locations


class _Pairs(list[tuple[str, object]]):
    """A decoded JSON object kept as its ordered key/value pairs, duplicate keys included.

    The text walk below visits every member in source order; a ``dict`` would keep only the last of
    duplicate keys and so pair the first occurrence's text with the last occurrence's value.
    """


def _plain(value: object) -> object:
    """Convert :class:`_Pairs` back to ``dict`` (last duplicate wins, as ``json.loads`` does)."""
    if isinstance(value, _Pairs):
        return {key: _plain(child) for key, child in value}
    if isinstance(value, list):
        return [_plain(child) for child in value]
    return value


def _json_id_values(text: str, document: object, public_id: str) -> list[tuple[str, int]]:  # noqa: C901 -- mirrors JSON nesting.
    """Return physical offsets of explicit ``@id`` values after simple local-context expansion.

    ``document`` must be ``text`` decoded with ``object_pairs_hook=_Pairs``, so that the walk and
    the decoded tree agree member by member.  Any disagreement raises :class:`ValueError`.
    """
    found: list[tuple[str, int]] = []
    decoder = json.JSONDecoder()

    def whitespace(index: int) -> int:
        while index < len(text) and text[index] in " \t\n\r":
            index += 1
        return index

    def expect(index: int, char: str) -> int:
        if text[index : index + 1] != char:
            raise ValueError(f"expected {char!r} at offset {index}")
        return whitespace(index + 1)

    def value(index: int, current: object, base: str, terms: Mapping[str, str], context: bool = False) -> int:
        """Walk one JSON value; inside a ``@context`` (``context``) an ``@id`` names a term, not a node."""
        index = whitespace(index)
        if isinstance(current, _Pairs):
            contexts = [child for key, child in current if key == "@context"]
            if contexts:
                base, terms = _json_context(_plain(contexts[-1]), base, terms)
            index = expect(index, "{")
            for position, (key, child) in enumerate(current):
                if position:
                    index = expect(index, ",")
                _key, index = decoder.raw_decode(text, index)
                index = expect(whitespace(index), ":")
                start = index
                index = whitespace(value(index, child, base, terms, context or key == "@context"))
                if key == "@id" and isinstance(child, str) and not context:
                    expanded = _expand_jsonld_id(child, base, terms)
                    if expanded is not None:
                        found.append((expanded, start))
            return expect(index, "}")
        if isinstance(current, list):
            index = expect(index, "[")
            for position, child in enumerate(current):
                if position:
                    index = expect(index, ",")
                index = whitespace(value(index, child, base, terms, context))
            return expect(index, "]")
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
        if isinstance(entry.get("@base"), str) and (joined := _join(base, entry["@base"])) is not None:
            base = joined
        for name, definition in entry.items():
            value = definition.get("@id") if isinstance(definition, dict) else definition
            if not name.startswith("@") and isinstance(value, str):
                expanded = _expand_jsonld_id(value, base, terms)
                if expanded is not None:
                    terms[name] = expanded
    return base, terms


def _expand_jsonld_id(value: str, base: str, terms: Mapping[str, str]) -> str | None:
    """Expand an explicit compact IRI without inventing a mapping for an unknown term (``None``: unresolvable)."""
    prefix, separator, local = value.partition(":")
    if separator and prefix in terms:
        return terms[prefix] + local
    return _join(base, value)
