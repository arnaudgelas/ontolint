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

Problems are raised as :class:`InputRejected` carrying the rule id (``SEC001`` ...) so the CLI can report
them like ``INPUT001``.  Network blocking patches process-global state, so the guard is serialised by a
lock and is meant for one parse at a time (the CLI is single threaded).
"""

from __future__ import annotations

import codecs
import contextlib
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
from rdflib.util import guess_format

from .paths import InputFile
from .policy import Policy

RDF_XML_FORMATS = frozenset({"xml", "application/rdf+xml"})
COMPRESSION_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\x1f\x8b", "gzip"),
    (b"BZh", "bzip2"),
    (b"\xfd7zXZ\x00", "xz"),
    (b"PK\x03\x04", "zip"),
    (b"\x28\xb5\x2f\xfd", "zstd"),
    (b"7z\xbc\xaf\x27\x1c", "7z"),
)


class InputRejected(Exception):  # noqa: N818 -- a rejection, not an error condition of the program.
    """An input was refused or could not be read safely; ``rule_id`` is the SEC rule that describes why."""

    def __init__(self, rule_id: str, message: str) -> None:
        super().__init__(message)
        self.rule_id = rule_id
        self.message = message


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


class _BoundedGraph(Graph):
    """A graph that stops the parser as soon as it holds more than ``limit`` triples."""

    def __init__(self, limit: int) -> None:
        super().__init__()
        self._limit = limit
        self._adds = 0

    def add(self, triple: Any) -> Any:  # noqa: D102 -- documented on the base class.
        self._adds += 1
        # gremlin: pardon[equivalent] fewer than limit adds cannot reach len >= limit, so >= and > agree here
        if self._adds > self._limit and len(self) >= self._limit and triple not in self:
            raise InputRejected("SEC002", f"graph has more than {self._limit} triples (max_triples)")
        return super().add(triple)


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
        close = rest.find(quote, match.end())
        value = rest[match.end() : close if close >= 0 else end]
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


def _network_problem(item: InputFile, attempts: NetworkAttempts) -> InputRejected | None:
    """Translate what the guard blocked into a SEC rejection (contexts first: they are the specific case)."""
    if attempts.contexts:
        return InputRejected(
            "SEC006", f"{item.display} references an external JSON-LD context {attempts.contexts[0]!r}; refused"
        )
    if attempts.network:
        return InputRejected(
            "SEC013", f"{item.display} tried to use the network ({attempts.network[0]}); the network is disabled"
        )
    return None


def load_graph(item: InputFile, policy: Policy, root: Path | None = None) -> Graph:
    """Parse ``item`` safely; raises :class:`InputRejected` for refused input and parser errors otherwise."""
    check_path(item, root if root is not None else Path.cwd())
    data = _read_limited(item, policy.max_input_bytes)
    kind = compression_of(data)
    if kind is not None:
        raise InputRejected("SEC011", f"{item.display} is {kind}-compressed; compressed input is refused")
    fmt = guess_format(item.path.name) or "turtle"
    problem = dtd_problem(data, policy.max_input_bytes) if fmt in RDF_XML_FORMATS else None
    if problem is not None:
        raise InputRejected("SEC010", f"{item.display} {problem}")
    graph = _BoundedGraph(policy.max_triples)
    failure: Exception | None = None
    with network_disabled() as attempts:
        try:
            with warnings.catch_warnings():
                # rdflib's JSON-LD parser builds a ConjunctiveGraph and warns about its own deprecation.
                warnings.filterwarnings("ignore", message="ConjunctiveGraph is deprecated", category=DeprecationWarning)
                graph.parse(data=data, format=fmt, publicID=item.path.as_uri())
        except Exception as exc:  # noqa: BLE001 -- classified below; unknown failures are re-raised.
            failure = exc
    rejection = _network_problem(item, attempts)
    if rejection is not None:
        raise rejection from failure
    if isinstance(failure, InputRejected):
        raise failure
    if failure is not None:
        raise failure
    return graph
