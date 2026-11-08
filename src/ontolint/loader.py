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
import multiprocessing
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

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.plugins.shared.jsonld import context as jsonld_context
from rdflib.plugins.stores.memory import Memory
from rdflib.term import Node
from rdflib.util import guess_format

from .paths import InputFile
from .policy import Policy
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


@dataclass(frozen=True)
class LoadedGraph:
    """A parsed graph plus the source locations recoverable from its input syntax."""

    graph: Graph
    source_index: SourceIndex


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

    Absolute paths are explicit user intent and are accepted; links that stay beneath ``root`` are fine.
    """
    if item.escapes_root:
        raise InputRejected("SEC009", f"{item.display} escapes the working directory through '..'")
    if item.path.is_symlink():
        target = Path(os.path.realpath(item.path))
        if not target.is_relative_to(Path(os.path.realpath(root))):
            raise InputRejected("SEC009", f"{item.display} is a symlink to {target.as_posix()} outside the working dir")


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


def _parse_bytes(data: bytes, fmt: str, public_id: str, display: str, max_triples: int) -> Graph:
    """Parse ``data`` under the network guard and the triple bound; shared by the in-process and worker paths."""
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
        raise ParseFailure(type(failure).__name__, _describe(failure)) from failure
    store.limit = None  # a plain graph: pySHACL and other consumers copy it and must not hit the bound
    if len(graph) > max_triples:  # pragma: no cover - the store bound fires first; defence in depth
        raise InputRejected("SEC002", f"graph has more than {max_triples} triples (max_triples)")
    return graph


def load_graph(item: InputFile, policy: Policy, root: Path | None = None) -> Graph:
    """Parse ``item`` safely; raises :class:`InputRejected` (refused) or :class:`ParseFailure` (parser error).

    With ``policy.max_parse_seconds`` set, the parse runs in a killable worker process (see :func:`_parse_in_worker`);
    otherwise (the default) it runs in this process.
    """
    loaded = load_document(item, policy, root)
    # Keep the established Graph-returning API while letting the CLI retain loader metadata.
    setattr(loaded.graph, "_ontolint_source_index", loaded.source_index)  # noqa: B010 -- Graph has no metadata slot.
    return loaded.graph


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
    fmt = guess_format(item.path.name) or "turtle"
    problem = dtd_problem(data, policy.max_input_bytes) if fmt in RDF_XML_FORMATS else None
    if problem is not None:
        raise InputRejected("SEC010", f"{item.display} {problem}")
    try:
        public_id = item.path.as_uri()
    except ValueError as exc:  # a relative path: reported like any other parser failure, as it always was
        raise ParseFailure(type(exc).__name__, str(exc)) from exc
    graph = _parse_document(data, fmt, public_id, item.display, policy)
    return LoadedGraph(graph, build_source_index(data, fmt, public_id, graph))


def _parse_document(data: bytes, fmt: str, public_id: str, display: str, policy: Policy) -> Graph:
    """Choose the in-process or time-bounded parsing path for one already-validated document."""
    if policy.max_parse_seconds is None:
        return _parse_bytes(data, fmt, public_id, display, policy.max_triples)
    job = _ParseJob(data, fmt, public_id, display, policy.max_triples)
    return _parse_in_worker(job, policy.max_parse_seconds)


# --- time budget: the parse runs in a worker process that can be killed -----------------------------------------
#
# A pure-Python parse cannot be interrupted safely in this process: a thread cannot be killed, and a signal timer
# (SIGALRM) exists on POSIX main threads only and collides with any watchdog the embedding program already uses.
# A worker started with the ``spawn`` method works the same on Linux, macOS and Windows, shares no state with the
# parent (so the network guard and the patched parser modules are applied freshly in the worker) and can always be
# terminated.  The worker only ever returns plain data (JSON text), never pickles, so a compromised parser cannot
# make the parent execute anything while decoding the result.

WORKER_START_TIMEOUT = 120.0
"""Seconds to wait for the worker interpreter to start (imports); not part of the user's parse budget."""
_WORKER_GRACE = 2.0

_Term = list[Any]


def _encode_term(term: Node) -> _Term:
    if isinstance(term, Literal):
        return ["l", str(term), term.language, None if term.datatype is None else str(term.datatype)]
    return ["b" if isinstance(term, BNode) else "u", str(term)]


def _decode_term(raw: _Term) -> Node:
    kind = raw[0]
    if kind == "u":
        return URIRef(raw[1])
    if kind == "b":
        return BNode(raw[1])
    return Literal(raw[1], lang=raw[2], datatype=None if raw[3] is None else URIRef(raw[3]), normalize=False)


def _encode_graph(graph: Graph) -> bytes:
    triples = [[_encode_term(t) for t in triple] for triple in graph]
    namespaces = [[prefix, str(uri)] for prefix, uri in graph.namespaces()]
    return json.dumps({"triples": triples, "namespaces": namespaces}, separators=(",", ":")).encode()


def _decode_graph(payload: dict[str, Any]) -> Graph:
    graph = Graph()
    for prefix, uri in payload["namespaces"]:
        graph.bind(prefix, URIRef(uri), override=True, replace=True)
    graph.addN((_decode_term(s), _decode_term(p), _decode_term(o), graph) for s, p, o in payload["triples"])
    return graph


# gremlin: pardon[equivalent] nothing mutates a job; frozen only guards against it
@dataclass(frozen=True)
class _ParseJob:
    """Everything the worker needs: the bytes (already checked by the parent), the format and the bounds."""

    data: bytes
    fmt: str
    public_id: str
    display: str
    max_triples: int


def _worker_main(connection: Any, job: _ParseJob) -> None:
    """Entry point of the worker: announce readiness, parse, send one JSON document, exit."""
    connection.send_bytes(b"ready")
    try:
        reply = _encode_graph(_parse_bytes(job.data, job.fmt, job.public_id, job.display, job.max_triples))
    except InputRejected as exc:
        reply = json.dumps({"rejected": [exc.rule_id, exc.message]}).encode()
    except ParseFailure as exc:
        reply = json.dumps({"parse_failure": [exc.cause_type, exc.detail]}).encode()
    except BaseException as exc:  # noqa: BLE001 -- the parent must always receive an answer.
        detail = _describe(exc) if isinstance(exc, Exception) else ""
        reply = json.dumps({"parse_failure": [type(exc).__name__, detail]}).encode()
    connection.send_bytes(reply)
    connection.close()


def _stop(process: Any) -> None:
    """Terminate, then kill, the worker and reap it; safe to call on a worker that already exited."""
    if process.is_alive():
        process.terminate()
        process.join(_WORKER_GRACE)
    if process.is_alive():
        process.kill()
    process.join()
    process.close()


def _parse_in_worker(job: _ParseJob, seconds: float) -> Graph:
    """Parse in a ``spawn`` worker and give it ``seconds`` of wall-clock time from the moment it is ready.

    Interpreter start-up and the import of rdflib are excluded from the budget (they are the tool's cost, not the
    input's); the worker is terminated, then killed, when the budget is exhausted: :class:`InputRejected` ``SEC003``.
    """
    context = multiprocessing.get_context("spawn")
    # gremlin: pardon[equivalent] the parent only reads and the worker only writes; duplex adds no behaviour
    receiver, sender = context.Pipe(duplex=False)
    # gremlin: pardon[equivalent] the worker is always stopped in `finally`, so daemon only matters if the parent dies
    process = context.Process(target=_worker_main, args=(sender, job), daemon=True)
    process.start()
    sender.close()  # the parent only reads: EOF on the pipe means the worker is gone
    try:
        if not _ready(receiver, WORKER_START_TIMEOUT):
            raise ParseFailure("WorkerError", "the parse worker did not start")
        if not receiver.poll(seconds):
            raise InputRejected(
                "SEC003",
                f"{job.display} was not parsed within the time budget of {seconds:g} seconds (max_parse_seconds)",
            )
        try:
            reply = json.loads(receiver.recv_bytes())
        except (EOFError, OSError):
            raise ParseFailure("WorkerError", _worker_death(process)) from None
    finally:
        receiver.close()
        _stop(process)
    if "rejected" in reply:
        raise InputRejected(*reply["rejected"])
    if "parse_failure" in reply:
        raise ParseFailure(*reply["parse_failure"])
    graph = _decode_graph(reply)
    if len(graph) > job.max_triples:  # pragma: no cover - the worker enforces it; defence in depth
        raise InputRejected("SEC002", f"graph has more than {job.max_triples} triples (max_triples)")
    return graph


def _ready(receiver: Any, timeout: float) -> bool:
    try:
        return bool(receiver.poll(timeout)) and receiver.recv_bytes() == b"ready"
    except (EOFError, OSError):
        # gremlin: pardon[equivalent] None and False are both falsy for the only caller, `if not _ready(...)`
        return False


def _worker_death(process: Any) -> str:
    process.join(_WORKER_GRACE)
    return f"the parse worker exited without a result (exit code {process.exitcode})"
