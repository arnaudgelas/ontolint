"""Best-effort source regions for RDF terms retained by RDFLib parsing.

RDFLib graphs deliberately contain semantic nodes, not their lexical source positions. This
module recovers positions from Turtle/N3/TriG, N-Triples/N-Quads and RDF/XML syntax, and from explicit
JSON-LD ``@id`` values. Nodes with no unambiguous source construct simply have no SARIF region.

A node gets the first place its source spells it, whichever graph of a dataset that is: a term stated in
two graphs is located in the first, and a graph name that is also a node is located at its graph label
when that comes first (a TriG ``<g> {``, an N-Quads fourth term, a JSON-LD ``@id`` beside ``@graph``).
"""

from __future__ import annotations

import bisect
import contextlib
import io
import json
import logging
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any
from urllib.parse import urljoin
from xml.sax import SAXException, handler, make_parser
from xml.sax.xmlreader import AttributesNSImpl

from rdflib import BNode, Graph, URIRef
from rdflib.term import Node

from .models import Finding
from .redaction import redact_userinfo
from .reporting import Location
from .rules.support import stable_blank_id

_TEXT_FORMATS = frozenset({"turtle", "n3", "trig", "nt", "nquads"})
# Turtle and its supersets have prefixed names and directives; N-Triples and N-Quads spell every IRI in full.
# TriG adds only graph blocks to Turtle: ``{`` and ``}`` start no term and the ``GRAPH`` keyword is no prefixed
# name (it has no ``:``), so the scan steps over them, as it does over the braces of N3 formulae.
_PREFIXED_FORMATS = frozenset({"turtle", "n3", "trig"})
_XML_FORMATS = frozenset({"xml", "application/rdf+xml"})
_JSON_FORMATS = frozenset({"json-ld", "application/ld+json"})
# A local name (Turtle's PN_LOCAL) is runs of name characters and ``\``-escapes joined by runs of dots, so it never
# ends with a dot: ``ex:B.`` is ``ex:B`` and the end of the statement.  A name character is anything but whitespace
# and the characters that end a name unescaped (``;`` ``,`` the brackets, ``#``, ``{}``...: RDFLib's own set), so
# ``ex:B;``, ``ex:B,``, ``ex:B)``, ``ex:B}`` and ``ex:B#comment`` end at ``B``.  Each dot run is committed to its
# name character or given up whole, so the match is linear however many dots a run holds.
_LOCAL_UNIT = r"(?:\\.|[^\s<>\"{}|^`\\;,()\[\]#!~=@'&*+?/$.])"
_PREFIXED_NAME = re.compile(
    rf"(?P<prefix>[A-Za-z][A-Za-z0-9_-]*|):(?P<local>(?:{_LOCAL_UNIT}++(?:\.++{_LOCAL_UNIT}++)*+)?)"
)
_BNODE = re.compile(r"_:(?P<label>[A-Za-z][A-Za-z0-9_-]*)")
_NAME_RUN = re.compile(r"[A-Za-z0-9_-]+")
# Turtle/N3/TriG directives declare namespaces; the IRIs they mention are not statements about a node.
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
                self._problem = redact_userinfo(f"{type(exc).__name__}: {exc}")
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

        An IRI with a userinfo is also keyed by its masked spelling (what a finding holds), at its first occurrence;
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
                by_focus.setdefault(redact_userinfo(str(node)), location)
        return {finding: by_focus[finding.focus] for finding in findings if finding.focus in by_focus}


def build_source_index(data: bytes, fmt: str, public_id: str, graph: Graph) -> SourceIndex:
    """Index the regions of terms in ``data`` when ``fmt`` is supported, otherwise return no locations.

    A region is the term's first spelling: its start, and its exclusive end when that is as certain as the start.
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

    def span(self, index: int, end: int | None) -> Location:
        """The region of the token at ``index`` that ends at ``end`` (exclusive); no end if ``end`` is ``None``."""
        start = self.location(index)
        if end is None:
            return start
        stop = self.location(end)
        return Location(start.line, start.column, stop.line, stop.column)


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
        if fmt in _PREFIXED_FORMATS and (directive := _directive_end(text, index)) is not None:
            index = directive
            continue
        char = text[index]
        if char == "<":
            end = _iri_end(text, index + 1)
            if end is None:
                break
            node = _resolve_iri(public_id, text[index + 1 : end])
            if node is not None:
                _record(locations, graph_nodes, node, lines, (index, end + 1))
            index = end + 1
        elif (match := _BNODE.match(text, index)) is not None:
            # A label may go on past what the pattern reads (inner dots, non-ASCII letters): then its end is unknown.
            stop = match.end() if _bnode_ends(text, match.end()) else None
            _record(locations, graph_nodes, BNode(match["label"]), lines, (index, stop))
            index = match.end()
        elif fmt in _PREFIXED_FORMATS and (match := _PREFIXED_NAME.match(text, index)) is not None:
            namespace = prefixes.get(match["prefix"])
            if namespace is not None:
                node = URIRef(namespace + _unescape_local(match["local"]))
                _record(locations, graph_nodes, node, lines, (index, match.end()))
            index = match.end()
        else:
            index = _past_non_term(text, index)
    return locations


def _past_non_term(text: str, index: int) -> int:
    """Return the index after the character at ``index``, or after the run of name characters it starts.

    No term starts inside such a run: a prefixed name or blank node starting in it would have matched at its
    first character.  Skipping it whole keeps the scan linear on a long word, such as a language tag, that the
    prefixed-name pattern would otherwise retry at each of its letters.
    """
    match = _NAME_RUN.match(text, index)
    return index + 1 if match is None else match.end()


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


# What may follow a blank-node label for it to end there: the end of the text, a space, a delimiter, or a dot
# that ends the statement.  Anything else (a letter, a digit, ``.b``) may be part of a label the pattern cut short.
_BNODE_END = re.compile(r"(?=$|[\s;,()\[\]{}<>#\"']|\.(?:$|[\s#}\])<]))")


def _bnode_ends(text: str, end: int) -> bool:
    """Whether the blank-node label read up to ``end`` certainly ends there."""
    return _BNODE_END.match(text, end) is not None


def _record(
    locations: dict[Node, Location],
    graph_nodes: set[Node],
    node: Node,
    lines: _Lines,
    at: tuple[int, int | None],
) -> None:
    """Record ``node`` at ``at``, the offset of its token and the offset after it (``None``: its end is unknown)."""
    if node in graph_nodes and node not in locations:
        locations[node] = lines.span(*at)


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


# The end of a start tag: the first ``>`` outside a quoted attribute value (a value may hold a ``>``).
_TAG_END = re.compile(rb"""(?:[^>"']|"[^"]*"|'[^']*')*+>""")
_XML_BREAK = re.compile(rb"\r\n|\r|\n")
_XML_ENCODING = re.compile(rb"""\A(?:\xef\xbb\xbf)?<\?xml[^>]*?\sencoding\s*=\s*["']([^"']+)["']""")


def _tag_end(data: bytes, start: int) -> int | None:
    """The byte offset after the start tag that begins at ``start``, or ``None`` if it has no end."""
    match = _TAG_END.match(data, start + 1)
    return None if match is None else match.end()


def _utf8_compatible(data: bytes) -> bool:
    """Whether byte offsets of ``data`` can be turned into code-point columns (UTF-8 or ASCII, as declared)."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff", b"\x00<", b"<\x00")):
        return False
    declared = _XML_ENCODING.match(data)
    return declared is None or declared[1].lower() in {b"utf-8", b"utf8", b"us-ascii", b"ascii"}


class _ByteCursor:
    """Turn increasing byte offsets of a UTF-8 document into XML line and column numbers, in linear time overall.

    An XML parser counts a line break as ``\\n``, ``\\r\\n`` or a lone ``\\r``, and a column in code points.  The
    cursor remembers the last position it answered and counts only the bytes since, so it cannot go backwards.
    """

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 3 if data.startswith(b"\xef\xbb\xbf") else 0  # a parser does not count the byte order mark
        self.line = 1
        self.column = 1

    def move(self, offset: int) -> tuple[int, int] | None:
        """The one-based line and column of byte ``offset`` (a character boundary), or ``None`` if it is behind."""
        if offset < self.offset:
            return None
        end = self.data.rfind(b"\n", self.offset, offset)
        end_cr = self.data.rfind(b"\r", self.offset, offset)
        last = max(end, end_cr)
        if last >= 0:
            self.line += sum(1 for _ in _XML_BREAK.finditer(self.data, self.offset, offset))
            self.offset = last + 1
            self.column = 1
        self.column += len(self.data[self.offset : offset].decode("utf-8"))
        self.offset = offset
        return self.line, self.column


class _RDFXMLLocator(handler.ContentHandler):
    """Collect RDF/XML resource positions from SAX events without changing the RDF parser's semantics."""

    def __init__(self, public_id: str, graph_nodes: set[Node], data: bytes = b"") -> None:
        self.base = public_id
        self.bases: list[str] = []
        self.graph_nodes = graph_nodes
        self.locations: dict[Node, Location] = {}
        self.data = data
        self.cursor = _ByteCursor(data) if _utf8_compatible(data) else None
        self.parser: Any = None

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
            line, column = self.locator.getLineNumber(), self.locator.getColumnNumber() + 1  # type: ignore[attr-defined]
            end = self._tag_end(line, column)
            self.locations[node] = Location(line, column, *end) if end is not None else Location(line, column)

    def _tag_end(self, line: int, column: int) -> tuple[int, int] | None:
        """Where the start tag being read ends, as (line, column) one past its ``>``; ``None`` unless that is certain.

        The parser's own start position is the check: the tag is trusted only when the bytes at the parser's byte
        offset begin a tag and count to the same line and column the parser reports.
        """
        if self.cursor is None:
            return None
        try:
            start = self.parser._parser.CurrentByteIndex  # noqa: SLF001 -- pyexpat's offset
        except AttributeError:
            return None
        stop = _tag_end(self.data, start) if self.data[start : start + 1] == b"<" else None
        if stop is None or self.cursor.move(start) != (line, column):
            return None
        return self.cursor.move(stop)


def _xml_locations(data: bytes, public_id: str, graph: Graph) -> dict[Node, Location]:
    """Collect element-start positions for RDF/XML IRIs with a non-resolving SAX parser."""
    try:
        parser = make_parser()  # noqa: S317 -- DTD/entity preflight runs before this non-resolving auxiliary scan.
        parser.setFeature(handler.feature_namespaces, True)
        for feature in (handler.feature_external_ges, handler.feature_external_pes):
            with contextlib.suppress(NotImplementedError, ValueError):
                parser.setFeature(feature, False)
        collector = _RDFXMLLocator(public_id, {node for triple in graph for node in triple}, data)
        collector.parser = parser
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
    for value, offset, end in _json_id_values(text, document, public_id):
        node = _resolve_iri(public_id, value)
        if node is not None:
            _record(locations, graph_nodes, node, lines, (offset, end))
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


def _json_id_values(text: str, document: object, public_id: str) -> list[tuple[str, int, int]]:  # noqa: C901 -- mirrors JSON nesting.
    """Return the physical span (start offset, offset after the closing quote) of each explicit ``@id`` value.

    The values are expanded by the simple local-context rules.

    ``document`` must be ``text`` decoded with ``object_pairs_hook=_Pairs``, so that the walk and
    the decoded tree agree member by member.  Any disagreement raises :class:`ValueError`.
    """
    found: list[tuple[str, int, int]] = []
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
                stop = value(index, child, base, terms, context or key == "@context")
                index = whitespace(stop)
                if key == "@id" and isinstance(child, str) and not context:
                    expanded = _expand_jsonld_id(child, base, terms)
                    if expanded is not None:
                        found.append((expanded, start, stop))
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
