"""Safe RDF input loader: no network, bounded size, no external entities, no compressed archives.

``Graph().parse(path)`` guesses the serialisation from the file extension and lets rdflib fetch remote
resources on its own (a JSON-LD ``@context`` given as a URL is downloaded over HTTP).  A linter run in CI
must never do that, so every input is read through :func:`load_graph`:

* the file is opened once, checked (regular file, not a symlink pointing outside the working directory,
  not a relative path escaping it) and read with a byte limit, so a swapped or endless file cannot
  exhaust memory;
* compressed input and RDF/XML whose DTD is external or can amplify (nested entities) are refused;
* parsing runs inside :func:`network_disabled`, which blocks sockets and name resolution and makes
  rdflib refuse every external JSON-LD context; ``owl:imports`` are never fetched;
* the number of triples is bounded while the graph is being built.

Problems are raised as :class:`LoadError`: :class:`InputRejected` carries the rule id (``SEC001`` ...) of a refusal,
:class:`ParseFailure` (also a ``ValueError``, reported as ``INPUT001``) wraps every failure of the RDF parser itself,
whatever internal exception type rdflib raised, so library callers only ever have to catch ``LoadError``.

Network blocking patches process-global state, so the guard is serialised by a lock and is meant
for one parse at a time (the CLI is single threaded).
"""

from __future__ import annotations

import codecs
import contextlib
import json
import os
import re
import socket
import stat
import threading
import warnings
from collections.abc import Generator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rdflib import Graph
from rdflib.plugins.shared.jsonld import context as jsonld_context
from rdflib.plugins.stores.memory import Memory
from rdflib.util import guess_format

from . import datasets, syntax, worker
from .datasets import EMPTY_INDEX, GraphIndex
from .models import SourceFacts
from .paths import InputFile
from .policy import Policy
from .redaction import withheld_parser_message
from .source_locations import SourceIndex, build_source_index

RDF_XML_FORMATS = frozenset({"xml", "application/rdf+xml"})
COMPRESSION_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\x1f\x8b", "gzip"),
    (b"BZh", "bzip2"),
    (b"\xfd7zXZ\x00", "xz"),
    (b"PK\x03\x04", "zip"),
    (b"\x28\xb5\x2f\xfd", "zstd"),
    (b"7z\xbc\xaf\x27\x1c", "7z"),
)


class LoadError(Exception):
    """Base of everything :func:`load_graph` raises on purpose (except ``OSError`` for unreadable files)."""


class InputRejected(LoadError):  # noqa: N818 -- a rejection, not an error condition of the program.
    """An input was refused or could not be read safely; ``rule_id`` is the SEC rule that describes why."""

    def __init__(self, rule_id: str, message: str) -> None:
        super().__init__(message)
        self.rule_id = rule_id
        self.message = message


class ParseFailure(LoadError, ValueError):
    """The RDF parser failed on the input (malformed text, encoding, hostile structure); reported as ``INPUT001``.

    ``cause_type`` names the parser's own exception (chained as ``__cause__``); ``detail`` is its message.
    """

    rule_id = "INPUT001"

    def __init__(self, cause_type: str, detail: str) -> None:
        super().__init__(f"{cause_type}: {detail}")
        self.cause_type = cause_type
        self.detail = detail


SPDX_SCAN_BYTES = 8192
"""How far into a file an ``SPDX-License-Identifier:`` comment is looked for (file headers only)."""


@dataclass(frozen=True)
class Module:
    """One file of an ``owl:imports`` closure: its report identity, the IRIs it declares, its source positions."""

    display: str
    uri: str
    declared: frozenset[str]
    """IRIs this file gives an ``rdf:type`` to: a finding about one of them belongs to this file."""
    source_index: SourceIndex
    directory: str = ""
    """The file's directory as a ``file:`` URI ending in ``/``: relative references resolve under it."""
    graph: Graph | None = None
    """The file's own triples (the root's too: without them, the input graph is the whole closure)."""
    graphs: GraphIndex = field(default=EMPTY_INDEX, compare=False)
    """The named graphs that state each of the file's triples (empty unless it is a dataset with one)."""


# gremlin: pardon[equivalent] nothing mutates a choice; frozen only guards against it
@dataclass(frozen=True)
class ImportChoice:
    """An ``owl:imports`` IRI the ``--import-dir`` options hold in several files, so the import took the first."""

    iri: str
    directories: tuple[str, ...]
    """The report paths of the ``--import-dir`` options holding ``iri``, in argument order."""
    candidates: tuple[tuple[Path, Path], ...]
    """Every file there that declares ``iri`` with its ``--import-dir``, by directory then path: the first is the
    one the import resolved to.  Only paths: a candidate the closure did not load is read only to compare it."""


# gremlin: pardon[equivalent] nothing mutates a shadow; frozen only guards against it
@dataclass(frozen=True)
class ImportShadow:
    """An ``owl:imports`` IRI a loaded file already declares, although it resolves to a file that was not loaded."""

    iri: str
    path: Path
    """The file the catalog (or an ``--import-dir``) names for ``iri``."""
    root: Path
    """The import root or ``--import-dir`` it lies in: the sandbox it is read in, if it is read to compare it."""


@dataclass(frozen=True)
class LoadedGraph:
    """A parsed graph plus the source locations recoverable from its input syntax."""

    graph: Graph
    source_index: SourceIndex
    # With --follow-imports: the owl:imports loaded from local files, and the ontology IRIs those files declare.
    resolved_imports: frozenset[str] = frozenset()
    imported_ontologies: frozenset[str] = frozenset()
    modules: tuple[Module, ...] = ()
    """With --follow-imports: the root file first, then every imported file in load order."""
    source: SourceFacts = SourceFacts()
    """What the file's text says that the graph does not keep (an SPDX licence comment, its prefixes)."""
    graphs: GraphIndex = field(default=EMPTY_INDEX, compare=False)
    """The named graphs that state each triple of the (root) file; empty unless it is a dataset with one."""
    choices: tuple[ImportChoice, ...] = ()
    """With ``--import-dir``: the imports of the closure that the import dirs held in several files."""
    shadowed: tuple[ImportShadow, ...] = ()
    """The imports of the closure served by a file already loaded that declares their IRI, in walk order."""


class NetworkAccessBlocked(Exception):  # noqa: N818 -- not an OSError on purpose: urllib must not wrap it.
    """Raised in place of any network operation while :func:`network_disabled` is active."""


class RemoteContextRefused(Exception):  # noqa: N818 -- see above.
    """Raised when a JSON-LD document references an external ``@context``."""


@dataclass
class NetworkAttempts:
    """What the guard blocked, so a swallowed exception cannot hide a network attempt."""

    network: list[str] = field(default_factory=list[str])
    contexts: list[str] = field(default_factory=list[str])


_LOCK = threading.RLock()


def _blocked(attempts: NetworkAttempts, what: str) -> NetworkAccessBlocked:
    attempts.network.append(what)
    return NetworkAccessBlocked(f"network access is disabled ({what})")


@contextlib.contextmanager
def network_disabled() -> Generator[NetworkAttempts]:
    """Block sockets, DNS and external JSON-LD contexts; originals are restored on exit (even on error)."""
    attempts = NetworkAttempts()

    def connect(self: socket.socket, address: Any, /) -> None:
        raise _blocked(attempts, f"connect {address!r}")

    def connect_ex(self: socket.socket, address: Any, /) -> int:
        raise _blocked(attempts, f"connect_ex {address!r}")

    def create_connection(address: Any, *args: Any, **kwargs: Any) -> socket.socket:
        raise _blocked(attempts, f"connect {address!r}")

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        raise _blocked(attempts, f"resolve {host!r}")

    def sendto(self: socket.socket, data: Any, *args: Any) -> int:
        raise _blocked(attempts, f"sendto {args[-1] if args else '?'!r}")

    def fetch_context(*args: Any, **kwargs: Any) -> Any:
        target = str(args[0]) if args else "?"
        attempts.contexts.append(target)
        raise RemoteContextRefused(f"external JSON-LD context {target!r} refused")

    with _LOCK, contextlib.ExitStack() as stack:
        patches: tuple[tuple[Any, str, Any], ...] = (
            (socket.socket, "connect", connect),
            (socket.socket, "connect_ex", connect_ex),
            (socket, "create_connection", create_connection),
            (socket, "getaddrinfo", getaddrinfo),
            # The C resolvers below do not go through ``socket.getaddrinfo``; UDP needs no ``connect``.
            (socket, "gethostbyname", getaddrinfo),
            (socket, "gethostbyname_ex", getaddrinfo),
            (socket, "gethostbyaddr", getaddrinfo),
            (socket.socket, "sendto", sendto),
            (jsonld_context, "source_to_json", fetch_context),
        )
        for owner, name, replacement in patches:
            original = getattr(owner, name)
            setattr(owner, name, replacement)
            stack.callback(setattr, owner, name, original)
        yield attempts


MAX_TERM_EXPANSION_DEPTH = 64
"""How many prefix expansions one JSON-LD term may chain; real contexts need a handful, cycles never end."""


@contextlib.contextmanager
def term_expansion_bounded(limit: int = MAX_TERM_EXPANSION_DEPTH) -> Generator[None]:
    """Make rdflib's JSON-LD term expansion fail fast on cyclic definitions instead of recursing ~1000 levels.

    ``{"a": "b:x", "b": "a:y"}`` makes ``Context._rec_expand`` recurse until the interpreter's own limit, which costs
    seconds on a long value.  Past ``limit`` nested calls a ``RecursionError`` is raised (the same failure, earlier);
    :func:`load_graph` reports it as :class:`ParseFailure`.  The interpreter's recursion limit is never changed.
    """
    original = jsonld_context.Context._rec_expand  # noqa: SLF001
    depth = 0

    def bounded(self: Any, source: Any, expr: Any, prev: Any = None) -> Any:
        nonlocal depth
        if depth >= limit:
            raise RecursionError(f"JSON-LD term expansion is nested more than {limit} levels")
        depth += 1
        try:
            return original(self, source, expr, prev)
        finally:
            depth -= 1

    with _LOCK:
        jsonld_context.Context._rec_expand = bounded  # type: ignore[method-assign]  # noqa: SLF001
        try:
            yield
        finally:
            jsonld_context.Context._rec_expand = original  # type: ignore[method-assign]  # noqa: SLF001


class _BoundedStore(Memory):
    """A store that stops the parser as soon as it holds more than ``limit`` distinct triples, in any context.

    Parsers add through ``Graph.add``, ``Graph.addN``, formulae and quoted graphs (N3), which all end in the store, so
    the bound lives here.  ``limit = None`` switches it off once loading is done.
    """

    def __init__(self, limit: int) -> None:
        super().__init__()
        self.limit: int | None = limit

    def _check(self) -> None:
        if self.limit is not None and len(self) > self.limit:
            raise InputRejected("SEC002", f"graph has more than {self.limit} triples (max_triples)")

    def add(self, triple: Any, context: Any, quoted: bool = False) -> None:  # noqa: D102 -- documented on the base.
        super().add(triple, context, quoted)
        self._check()

    def addN(self, quads: Any) -> None:  # noqa: D102, N802 -- documented on the base class.
        for s, p, o, c in quads:
            self.add((s, p, o), c)


_PROLOG_CODECS: tuple[tuple[bytes, str], ...] = (
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (b"<\0\0\0", "utf-32-le"),
    (b"\0\0\0<", "utf-32-be"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
    (b"<\0", "utf-16-le"),
    (b"\0<", "utf-16-be"),
)


def _decode_prolog(data: bytes) -> str:
    """Decode an XML document well enough to look for a DOCTYPE: BOM or ``<`` byte-pattern sniffing, else Latin-1.

    The UTF-32 BOM is tested before the UTF-16 one because UTF-32-LE starts with the UTF-16-LE BOM.
    """
    for prefix, codec in _PROLOG_CODECS:
        if data.startswith(prefix):
            return data.decode(codec, errors="replace")
    return data.decode("latin-1")


_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_DOCTYPE = re.compile(r"<!DOCTYPE", re.IGNORECASE)
_EXTERNAL_ID = re.compile(r"\b(?:SYSTEM|PUBLIC)\b", re.IGNORECASE)
_ENTITY = re.compile(r"<!ENTITY\s+(?:%\s+)?([^\s\"'>]+)\s+[\"']", re.IGNORECASE)
_REFERENCE = re.compile(r"[&%](?!(?:amp|lt|gt|quot|apos);)[A-Za-z_][^\s;&%]*;")


def _mask_quotes(text: str) -> str:
    """Blank out quoted text (keeping the quotes and every offset) so keywords inside values are ignored."""
    out: list[str] = []
    quote = ""
    for char in text:
        if quote:
            out.append(char if char == quote else " ")
            quote = "" if char == quote else quote
        else:
            out.append(char)
            quote = char if char in "\"'" else ""
    return "".join(out)


def _declaration_end(masked: str) -> int:
    depth = 0
    for i, char in enumerate(masked):
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
        elif char == ">" and depth <= 0:
            return i
    return len(masked)


def dtd_problem(data: bytes, max_expanded: int) -> str | None:
    """Describe why an RDF/XML document's DOCTYPE is unsafe, or return ``None`` when it is acceptable.

    Internal entities with plain values (``<!ENTITY owl "http://www.w3.org/2002/07/owl#">``, common in
    Protege output) stay allowed.  Refused: ``SYSTEM``/``PUBLIC`` identifiers (external DTD or entity),
    entities whose value references another entity (the "billion laughs" shape; expat's own guard
    needs hundreds of megabytes of output to react), and entity use that would expand the document
    beyond ``max_expanded`` characters.
    """
    text = _COMMENT.sub("", _decode_prolog(data))
    start = _DOCTYPE.search(text)
    if start is None:
        return None
    rest = text[start.end() :]
    masked = _mask_quotes(rest)
    end = _declaration_end(masked)
    if _EXTERNAL_ID.search(masked[:end]):
        return "declares an external DTD or entity (SYSTEM/PUBLIC)"
    expanded = 0
    for match in _ENTITY.finditer(masked[:end]):
        quote = rest[match.end() - 1]
        value = rest[match.end() : end].split(quote, 1)[0]
        if _REFERENCE.search(value):
            return f"declares entity {match.group(1)!r} that references another entity"
        expanded += len(value) * rest[end:].count(f"&{match.group(1)};")
    if expanded > max_expanded:
        return f"uses entities that expand to {expanded} characters, more than the limit of {max_expanded}"
    return None


def compression_of(data: bytes) -> str | None:
    """Name the compression format ``data`` starts with, or ``None`` for (probably) plain text."""
    for magic, name in COMPRESSION_MAGIC:
        if data.startswith(magic):
            return name
    return None


def _read_limited(item: InputFile, limit: int) -> bytes:
    """Open once, check it is a regular file within the size limit, and read at most ``limit`` bytes."""
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    fd = os.open(item.path, flags)  # OSError (missing file, permissions) is an ordinary INPUT001 for the caller
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise InputRejected("SEC009", f"{item.display} is not a regular file (device, pipe or socket)")
        if info.st_size > limit:
            raise InputRejected(
                "SEC001", f"{item.display} is {info.st_size} bytes, more than the limit of {limit} (max_input_bytes)"
            )
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise InputRejected("SEC001", f"{item.display} grew beyond the limit of {limit} bytes (max_input_bytes)")
    return data


def check_path(item: InputFile, root: Path) -> None:
    """Refuse a relative argument that climbs out of ``root`` or a symlink whose target lies outside it.

    A path that lies beneath ``root`` as written but reaches a file outside it through a symlinked directory
    (``linked/x.ttl`` with ``linked -> /elsewhere``) is refused too.  Absolute paths outside ``root`` are explicit
    user intent and are accepted; links that stay beneath ``root`` are fine.
    """
    if item.escapes_root:
        raise InputRejected("SEC009", f"{item.display} escapes the working directory through '..'")
    real_root = Path(os.path.realpath(root))
    target = Path(os.path.realpath(item.path))
    if target.is_relative_to(real_root):
        return
    if item.path.is_symlink():
        raise InputRejected("SEC009", f"{item.display} is a symlink to {target.as_posix()} outside the working dir")
    if item.path.is_relative_to(root):
        raise InputRejected(
            "SEC009",
            f"{item.display} goes through a symlinked directory to {target.as_posix()} outside the working dir",
        )


def _network_problem(display: str, attempts: NetworkAttempts) -> InputRejected | None:
    """Translate what the guard blocked into a SEC rejection (contexts first: they are the specific case)."""
    if attempts.contexts:
        return InputRejected(
            "SEC006", f"{display} references an external JSON-LD context {attempts.contexts[0]!r}; refused"
        )
    if attempts.network:
        return InputRejected(
            "SEC013", f"{display} tried to use the network ({attempts.network[0]}); the network is disabled"
        )
    return None


def _describe(failure: Exception) -> str:
    """The message of a parser failure; recursion and memory exhaustion get a readable one."""
    if isinstance(failure, RecursionError):
        return "input is nested too deeply (or defines cyclic JSON-LD terms) to be parsed"
    if isinstance(failure, MemoryError):
        return "input needs more memory than is available to be parsed"
    return str(failure)


DATASET_FORMATS = frozenset({"trig", "nquads", "json-ld"})
"""RDF dataset syntaxes (TriG, N-Quads and JSON-LD): their named graphs are merged into the one graph that is linted.

The names are the formats :func:`load_document` passes to the parser: ``guess_format`` and :func:`syntax.choose`
spell JSON-LD ``json-ld`` (for ``.jsonld``, ``.json-ld`` and ``.json`` alike, and when the content is sniffed).
"""


def _parse_bytes(data: bytes, fmt: str, public_id: str, display: str, max_triples: int) -> tuple[Graph, GraphIndex]:
    """Parse ``data`` under the network guard and the triple bound; shared by the in-process and worker paths.

    Returns the graph and, for a dataset syntax, the named graphs that state each of its triples.
    """
    store = _BoundedStore(max_triples)
    graph = Graph(store=store)
    failure: Exception | None = None
    with network_disabled() as attempts, term_expansion_bounded():
        try:
            with warnings.catch_warnings():
                # rdflib's JSON-LD parser builds a ConjunctiveGraph and warns about its own deprecation, and the
                # N3/N-Quads parsers touch the deprecated Dataset.default_context.
                warnings.filterwarnings("ignore", message="ConjunctiveGraph is deprecated", category=DeprecationWarning)
                warnings.filterwarnings(
                    "ignore", message="Dataset.default_context is deprecated", category=DeprecationWarning
                )
                graph.parse(data=data, format=fmt, publicID=public_id)
        except Exception as exc:  # noqa: BLE001 -- classified below; nothing but a LoadError leaves this function.
            failure = exc
    rejection = _network_problem(display, attempts)
    if rejection is not None:
        raise rejection from failure
    if isinstance(failure, LoadError):
        raise failure
    if failure is not None:
        raise ParseFailure(type(failure).__name__, withheld_parser_message(_describe(failure), data)) from failure
    index = EMPTY_INDEX
    if fmt in DATASET_FORMATS:
        # Record which graph states each triple first: once merged, the default graph holds them all.
        index = datasets.build_graph_index(store, graph.identifier, public_id)
        # The parser put each named graph in its own context; ``graph`` sees only the default one. An ontology
        # author means the whole file, so lint the union (adding a triple in another context adds no new one).
        for triple, _contexts in list(store.triples((None, None, None), None)):
            graph.add(triple)
    store.limit = None  # a plain graph: pySHACL and other consumers copy it and must not hit the bound
    if len(graph) > max_triples:  # pragma: no cover - the store bound fires first; defence in depth
        raise InputRejected("SEC002", f"graph has more than {max_triples} triples (max_triples)")
    return graph, index


def load_graph(item: InputFile, policy: Policy, root: Path | None = None) -> Graph:
    """Parse ``item`` safely; raises :class:`InputRejected` (refused) or :class:`ParseFailure` (parser error).

    With ``policy.max_parse_seconds`` set, the parse runs in a killable worker process (see :func:`_parse_in_worker`);
    otherwise (the default) it runs in this process.
    """
    loaded = load_document(item, policy, root)
    # Keep the established Graph-returning API while letting the CLI retain loader metadata.
    setattr(loaded.graph, "_ontolint_source_index", loaded.source_index)  # noqa: B010 -- Graph has no metadata slot.
    setattr(loaded.graph, "_ontolint_source_facts", loaded.source)  # noqa: B010 -- likewise.
    setattr(loaded.graph, "_ontolint_graph_index", loaded.graphs)  # noqa: B010 -- likewise.
    return loaded.graph


def loaded_graph(graph: Graph) -> LoadedGraph:
    """The :class:`LoadedGraph` for a graph returned by :func:`load_graph` (its metadata travels with it)."""
    facts = getattr(graph, "_ontolint_source_facts", None)
    index = getattr(graph, "_ontolint_graph_index", None)
    return LoadedGraph(
        graph,
        source_index(graph),
        source=facts if isinstance(facts, SourceFacts) else SourceFacts(),
        graphs=index if isinstance(index, GraphIndex) else EMPTY_INDEX,
    )


def source_index(graph: Graph) -> SourceIndex:
    """Return source metadata attached by :func:`load_graph`, or an empty index for an external graph."""
    value = getattr(graph, "_ontolint_source_index", None)
    return value if isinstance(value, SourceIndex) else SourceIndex({})


def load_document(item: InputFile, policy: Policy, root: Path | None = None) -> LoadedGraph:
    """Parse ``item`` and retain source positions where its RDF syntax supports them."""
    check_path(item, root if root is not None else Path.cwd())
    data = _read_limited(item, policy.max_input_bytes)
    kind = compression_of(data)
    if kind is not None:
        raise InputRejected("SEC011", f"{item.display} is {kind}-compressed; compressed input is refused")
    fmt = syntax.choose(guess_format(item.path.name) or "turtle", data)
    problem = dtd_problem(data, policy.max_input_bytes) if fmt in RDF_XML_FORMATS or fmt == "owl-xml" else None
    if problem is not None:
        raise InputRejected("SEC010", f"{item.display} {problem}")
    try:
        public_id = item.path.as_uri()
    except ValueError as exc:  # a relative path: reported like any other parser failure, as it always was
        raise ParseFailure(type(exc).__name__, str(exc)) from exc
    if fmt in syntax.NON_RDF_SYNTAXES:
        return _load_converted(item, data, fmt, public_id, policy)
    try:
        graph, index = _parse_document(data, fmt, public_id, item.display, policy)
    except ParseFailure as failure:
        line = syntax.html_start(data)
        if line is None:
            raise
        hint = f"; an HTML page starts at line {line} (a web page or server error saved in place of RDF?)"
        raise ParseFailure(failure.cause_type, failure.detail + hint) from failure
    return LoadedGraph(
        graph, build_source_index(data, fmt, public_id, graph), source=source_facts(data, fmt, graph), graphs=index
    )


def _load_converted(item: InputFile, data: bytes, fmt: str, public_id: str, policy: Policy) -> LoadedGraph:
    """Load a file in a non-RDF OWL syntax through ``policy.owl_converter``, or refuse it naming the way forward.

    The converted Turtle is parsed under the same limits as any input.  It has no source index: its lines
    are not the file's.
    """
    name = syntax.NON_RDF_SYNTAXES[fmt]
    if policy.owl_converter is None:
        raise ParseFailure(
            "UnsupportedSyntax",
            f"{item.display} is written in {name}, which ontolint cannot read; rerun with --convert-with-robot, "
            f"convert it to Turtle or RDF/XML first (for example `robot convert --input {item.path.name} --output "
            f"{item.path.stem}.ttl`), or lint a Turtle or RDF/XML release of the ontology",
        )
    try:
        turtle = policy.owl_converter(item.path, data, fmt)
    except Exception as exc:  # noqa: BLE001 -- any converter failure is this input's parse failure.
        raise ParseFailure("ConversionFailed", f"{item.display} is written in {name}; {exc}") from exc
    graph, _index = _parse_document(turtle, "turtle", public_id, item.display, policy)  # Turtle: no named graph
    return LoadedGraph(graph, SourceIndex({}), source=source_facts(data, "turtle", graph))


_DEFAULT_BINDINGS = frozenset((prefix, str(namespace)) for prefix, namespace in Graph().namespaces())
"""The prefixes RDFLib binds in every graph, whether or not a file declares them."""


def source_facts(data: bytes, fmt: str, graph: Graph) -> SourceFacts:
    """The SPDX licence comment and the prefix declarations of a parsed file."""
    spdx = re.search(rb"SPDX-License-Identifier:\s*([A-Za-z0-9.+-]+)", data[:SPDX_SCAN_BYTES])
    license_comment = spdx.group(1).decode("ascii") if spdx else None
    if syntax.family(fmt) == "json-ld":
        return SourceFacts(license_comment, ())  # a @context's terms are shared vocabulary, not declarations
    # A default binding counts only when the file spells its namespace out (a parse worker keeps no bindings).
    declared = tuple(
        sorted(
            (prefix, str(namespace))
            for prefix, namespace in graph.namespaces()
            if (prefix, str(namespace)) not in _DEFAULT_BINDINGS or str(namespace).encode("utf-8") in data
        )
    )
    return SourceFacts(license_comment, declared)


def _parse_document(data: bytes, fmt: str, public_id: str, display: str, policy: Policy) -> tuple[Graph, GraphIndex]:
    """Choose the in-process or time-bounded parsing path for one already-validated document."""
    if policy.max_parse_seconds is None:
        return _parse_bytes(data, fmt, public_id, display, policy.max_triples)
    job = _ParseJob(data, fmt, public_id, display, policy.max_triples)
    return _parse_in_worker(job, policy.max_parse_seconds)


# --- time budget: the parse runs in a worker process that can be killed (see :mod:`ontolint.worker`) -------------


def _encode_graph(graph: Graph, index: GraphIndex = EMPTY_INDEX) -> bytes:
    """The worker's reply: triples and prefixes, plus ``graphs`` only for a dataset with a named graph.

    Every other file's reply is the same as before the index existed.
    """
    triples = list(graph)
    document = worker.graph_document(graph, triples)
    if index.triples:
        document["graphs"] = datasets.encode_index(index, triples)
    return json.dumps(document, separators=(",", ":")).encode()


def _decode_document(payload: dict[str, Any]) -> tuple[Graph, GraphIndex]:
    """The graph and graph index of a worker reply; a reply without ``graphs`` has the empty index."""
    graph, triples = worker.decode_graph_document(payload)
    try:
        index = datasets.decode_index(payload.get("graphs"), triples)
    except ValueError as exc:
        raise ParseFailure("WorkerError", f"the parse worker sent a malformed graph index: {exc}") from exc
    return graph, index


# gremlin: pardon[equivalent] nothing mutates a job; frozen only guards against it
@dataclass(frozen=True)
class _ParseJob:
    """Everything the worker needs: the bytes (already checked by the parent), the format and the bounds."""

    data: bytes
    fmt: str
    public_id: str
    display: str
    max_triples: int

    def prepare(self) -> None:
        """Nothing to do: importing this module (to unpickle the job) already imported rdflib."""

    def run(self) -> bytes:
        """Parse and answer with the graph, or with the ``rejected`` or ``parse_failure`` it ran into."""
        try:
            return _encode_graph(*_parse_bytes(self.data, self.fmt, self.public_id, self.display, self.max_triples))
        except InputRejected as exc:
            return json.dumps({"rejected": [exc.rule_id, exc.message]}).encode()
        except ParseFailure as exc:
            return json.dumps({"parse_failure": [exc.cause_type, exc.detail]}).encode()
        except BaseException as exc:  # noqa: BLE001 -- the parent must always receive an answer it can map.
            detail = _describe(exc) if isinstance(exc, Exception) else ""
            return json.dumps({"parse_failure": [type(exc).__name__, detail]}).encode()


def _parse_in_worker(job: _ParseJob, seconds: float) -> tuple[Graph, GraphIndex]:
    """Parse in a bounded worker and give it ``seconds`` of wall-clock time from the moment it is ready.

    Interpreter start-up and the import of rdflib are excluded from the budget (they are the tool's cost, not the
    input's); the worker is terminated, then killed, when the budget is exhausted: :class:`InputRejected` ``SEC003``.
    """
    try:
        reply = worker.run_bounded(job, seconds, name="parse")
    except worker.WorkerTimeout:
        raise InputRejected(
            "SEC003", f"{job.display} was not parsed within the time budget of {seconds:g} seconds (max_parse_seconds)"
        ) from None
    except worker.WorkerGone as exc:
        raise ParseFailure("WorkerError", str(exc)) from None
    except worker.WorkerFailed as exc:
        raise ParseFailure(exc.cause_type, exc.detail) from None
    if "rejected" in reply:
        raise InputRejected(*reply["rejected"])
    if "parse_failure" in reply:
        raise ParseFailure(*reply["parse_failure"])
    graph, index = _decode_document(reply)
    if len(graph) > job.max_triples:  # pragma: no cover - the worker enforces it; defence in depth
        raise InputRejected("SEC002", f"graph has more than {job.max_triples} triples (max_triples)")
    return graph, index
