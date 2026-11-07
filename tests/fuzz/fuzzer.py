"""Deterministic, seedable, dependency-free mutation fuzzer for ontolint's input-facing surface.

Run ``uv run python -m tests.fuzz.fuzzer --seconds 60 --seed 1 --target all --out fuzz-out``.

Targets (each has an invariant, see the ``_run_*`` functions):

* ``loader``: :func:`ontolint.loader.load_graph` on mutated bytes with every RDF extension.
* ``lint``:   parseable mutants through :class:`ontolint.linter.Linter` (``execute`` and ``run``).
* ``cli``:    :func:`ontolint.cli.main` with random option combinations built from the real parser.
* ``config``: :meth:`ontolint.policy.Policy.from_mapping` and ``--config`` with mutated JSON.

Design: a seed pool (corpus files, plus mutants that produced a rarely seen outcome label) is mutated by byte-
and structure-aware operators; every case runs in-process under a ``SIGALRM`` watchdog (a post-hoc check where
that is unavailable), a socket recorder and an input size cap.  A failing case is reduced by delta debugging
while its *signature* (target, failure kind and where it happened) persists, saved under ``--out`` and
deduplicated by signature.  The process exits non-zero when a signature that is not known is found.

A case is fully described by ``(target, ext, opt, data)`` and is stored as ``<target>__<ext>__<opt>__<sig>.bin``,
so any file under ``regressions/`` can be replayed without extra state.
"""

# ruff: noqa: PLR2004, S311

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import logging
import math
import random
import re
import signal
import socket
import sys
import tempfile
import time
import traceback
import warnings
from collections import Counter
from collections.abc import Callable, Generator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Any, Self
from xml.sax import SAXException

if sys.platform != "win32":
    import resource

from rdflib import Graph
from rdflib.exceptions import Error as RdflibError

from ontolint import cli
from ontolint.linter import Linter
from ontolint.loader import InputRejected, load_graph
from ontolint.models import ExecutionStatus
from ontolint.paths import resolve_inputs
from ontolint.policy import Policy
from ontolint.profiles import PROFILES
from ontolint.rules.registry import default_registry

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent / "fixtures"
CORPUS_DIR = HERE / "corpus"
REGRESSIONS_DIR = HERE / "regressions"
KNOWN_BUGS_DIR = REGRESSIONS_DIR / "known_bugs"

MAX_INPUT = 256 * 1024
TARGETS = ("loader", "lint", "cli", "config")
EXTENSIONS = (".ttl", ".nt", ".rdf", ".xml", ".jsonld", ".json", ".n3", "")
DEFAULT_CASE_SECONDS = 10.0

DICTIONARY: tuple[bytes, ...] = (
    b"<!DOCTYPE",
    b"<!DOCTYPE rdf:RDF [",
    b"<!ENTITY",
    b'<!ENTITY a "x">',
    b'<!ENTITY % p SYSTEM "http://127.0.0.1:9/p">',
    b'<!ENTITY b "&a;&a;&a;&a;">',
    b"]>",
    b"SYSTEM",
    b"PUBLIC",
    b'SYSTEM "file:///etc/passwd"',
    b"&a;",
    b"&b;",
    b"%p;",
    b"&#0;",
    b"&#x10FFFF;",
    b"<![CDATA[",
    b"]]>",
    b"<?xml version='1.0' encoding='UTF-16'?>",
    b"<?xml version='1.0' encoding='latin-1'?>",
    b"<rdf:RDF",
    b"</rdf:RDF>",
    b"<rdf:Description",
    b'rdf:about="',
    b'rdf:parseType="Literal"',
    b'rdf:parseType="Collection"',
    b'rdf:nodeID="',
    b'xml:base="',
    b'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"',
    b"@context",
    b'"@context": "http://127.0.0.1:9/ctx"',
    b'"@context": ["http://127.0.0.1:9/a", {}]',
    b'"@import": "http://127.0.0.1:9/i"',
    b'"@graph"',
    b'"@id"',
    b'"@type"',
    b'"@list"',
    b'"@set"',
    b'"@reverse"',
    b'"@included"',
    b'"@nest"',
    b'"@vocab"',
    b'"@base"',
    b'"@value"',
    b'"@language"',
    b'"@json"',
    b'"@protected"',
    b'"@container"',
    b"@prefix",
    b"@base",
    b"@keywords",
    b"@forAll",
    b"PREFIX",
    b"BASE",
    b"=>",
    b"^^",
    b"<<",
    b">>",
    b"a",
    b"http://127.0.0.1:9/",
    b"<http://127.0.0.1:9/>",
    b"file:///etc/passwd",
    b"http://www.w3.org/2002/07/owl#Class",
    b"http://www.w3.org/2000/01/rdf-schema#subClassOf",
    b"http://www.w3.org/2002/07/owl#imports",
    b"owl:Class",
    b"owl:Thing",
    b"owl:Nothing",
    b"owl:Restriction",
    b"owl:unionOf",
    b"owl:intersectionOf",
    b"owl:complementOf",
    b"owl:onProperty",
    b"owl:equivalentClass",
    b"owl:sameAs",
    b"owl:propertyChainAxiom",
    b"rdfs:subClassOf",
    b"rdfs:subPropertyOf",
    b"rdf:first",
    b"rdf:rest",
    b"rdf:nil",
    b"skos:broader",
    b"skos:narrower",
    b"sh:property",
    b"sh:path",
    b"sh:sparql",
    b"sh:or",
    b"sh:node",
    b"sh:targetClass",
    "\u202e".encode(),
    "\u200b\ufeff\u2028".encode(),
    "\U0001f600".encode(),
    b"\x00",
    b"\x00\x00\x00<",
    b"\xff\xfe",
    b"\xfe\xff",
    b"\xef\xbb\xbf",
    b"\xff\xfe\x00\x00",
    b"\xed\xa0\x80",
    b"\xc0\xaf",
    b"\\u0000",
    b"\\ud800",
    b"\\U0010FFFF",
    b'"""',
    b"'''",
    b'"',
    b"'",
    b"<",
    b">",
    b"[",
    b"]",
    b"(",
    b")",
    b"{",
    b"}",
    b"\\",
    b"#",
    b" .\n",
    b" ;\n",
    b" ,\n",
    b"\r\n",
    b"_:b0",
    b"_:",
    b"9" * 400,
    b"-1e999",
    b"NaN",
    b"1e-400",
    b"true",
    b"null",
    b'{"depth_limit": 1e999}',
    b'{"severity_overrides": {"A": "fatal"}}',
    b'{"max_triples": 0}',
    b'"base": 1',
    b'"languages": "en"',
    b'"ignored_rules": [1]',
    b"ontolint",
)

_NEST_UNITS: tuple[bytes, ...] = (
    b"[",
    b"(",
    b"[ <http://e/p> ",
    b"( [ <http://e/p> ",
    b"{",
    b'{"@graph":',
    b'[{"@id":',
    b'{"@list":[',
    b'{"@context":',
    b"<a>",
    b"<rdf:Description>",
    b"<a><b>",
    b'"""',
    b"<<",
    b"{ ",
    b"&a;",
)

_INTERESTING_BYTES = b"\x00\x01\x7f\x80\xff\"'<>[](){}\\#@^_:;,. \t\r\n&%!"

_TERM = re.compile(rb'<[^<>\s"]*>|"[^"\n]*"|[A-Za-z]*:[A-Za-z_0-9]+|_:\w+')
_QUOTE_POSITIONS = re.compile(rb"[\"'<\[(\{]")


class CaseTimeout(BaseException):  # noqa: N818 -- BaseException so no ``except Exception`` in the target swallows it.
    """Raised by the watchdog when a case exceeds its time limit."""


class InvariantViolation(Exception):  # noqa: N818 -- a failed check, not an error condition.
    """A target's own invariant failed (as opposed to an unexpected exception)."""

    def __init__(self, kind: str, detail: str = "") -> None:
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind
        self.detail = detail


# --------------------------------------------------------------------------------------- mutation engine


class Mutator:
    """Seeded byte- and structure-aware mutation operators; ``mutate`` never returns more than ``max_size`` bytes."""

    def __init__(self, seed: int | str, corpus: Sequence[bytes] = (), max_size: int = MAX_INPUT) -> None:
        self.rng = random.Random(seed)
        self.corpus = tuple(corpus)
        self.max_size = max_size
        self.operators: tuple[Callable[[bytes], bytes], ...] = (
            self.bit_flip,
            self.byte_set,
            self.insert_random,
            self.delete_chunk,
            self.duplicate_chunk,
            self.repeat_chunk,
            self.splice,
            self.crossover,
            self.token_insert,
            self.token_replace,
            self.token_insert,
            self.deep_nest,
            self.unterminate,
            self.long_literal,
            self.reencode,
            self.line_shuffle,
            self.term_swap,
            self.term_swap,
        )
        self.gentle_operators: tuple[Callable[[bytes], bytes], ...] = (
            self.term_swap,
            self.term_swap,
            self.term_swap,
            self.token_replace,
            self.token_insert,
            self.line_shuffle,
            self.duplicate_chunk,
            self.byte_set,
            self.long_literal,
            self.deep_nest,
        )

    def _pos(self, data: bytes) -> int:
        return self.rng.randrange(len(data) + 1)

    def _span(self, data: bytes, longest: int) -> tuple[int, int]:
        start = self.rng.randrange(len(data)) if data else 0
        return start, min(len(data), start + self.rng.randint(1, max(1, longest)))

    def mutate(self, data: bytes, *, gentle: bool = False) -> bytes:
        """Apply one to five random operators; ``gentle`` keeps to small edits that often still parse."""
        out = data[: self.max_size]
        operators = self.gentle_operators if gentle else self.operators
        for _ in range(self.rng.choice((1, 1, 2)) if gentle else self.rng.choice((1, 1, 2, 2, 3, 5))):
            out = self.rng.choice(operators)(out)[: self.max_size]
        return out

    def term_swap(self, data: bytes) -> bytes:
        """Replace one RDF term (IRI, literal, qname, blank node) by another one from the same document."""
        terms = _TERM.findall(data)
        if len(terms) < 2:
            return data
        victim = self.rng.choice(terms)
        at = data.find(victim)
        return data[:at] + self.rng.choice(terms) + data[at + len(victim) :]

    def bit_flip(self, data: bytes) -> bytes:
        if not data:
            return bytes([1 << self.rng.randrange(8)])
        buf = bytearray(data)
        for _ in range(self.rng.randint(1, 8)):
            buf[self.rng.randrange(len(buf))] ^= 1 << self.rng.randrange(8)
        return bytes(buf)

    def byte_set(self, data: bytes) -> bytes:
        if not data:
            return b"\x00"
        buf = bytearray(data)
        for _ in range(self.rng.randint(1, 6)):
            buf[self.rng.randrange(len(buf))] = self.rng.choice(_INTERESTING_BYTES)
        return bytes(buf)

    def insert_random(self, data: bytes) -> bytes:
        junk = bytes(self.rng.randrange(256) for _ in range(self.rng.randint(1, 32)))
        at = self._pos(data)
        return data[:at] + junk + data[at:]

    def delete_chunk(self, data: bytes) -> bytes:
        start, end = self._span(data, max(1, len(data) // self.rng.choice((2, 8, 64, 1024))))
        return data[:start] + data[end:]

    def duplicate_chunk(self, data: bytes) -> bytes:
        start, end = self._span(data, 256)
        chunk = data[start:end]
        return data[:end] + chunk * self.rng.randint(1, 4) + data[end:]

    def repeat_chunk(self, data: bytes) -> bytes:
        """Insert a (log-uniform) huge repetition of a short chunk or dictionary token."""
        chunk = self.rng.choice(DICTIONARY) if self.rng.random() < 0.5 else data[slice(*self._span(data, 16))]
        chunk = chunk or b"a"
        room = max(1, (self.max_size - len(data)) // len(chunk))
        count = min(room, int(math.exp(self.rng.uniform(0, math.log(room + 1)))))
        at = self._pos(data)
        return data[:at] + chunk * count + data[at:]

    def splice(self, data: bytes) -> bytes:
        if not self.corpus:
            return self.duplicate_chunk(data)
        other = self.rng.choice(self.corpus)
        piece = other[slice(*self._span(other, 512))]
        at = self._pos(data)
        overwrite = self.rng.random() < 0.3
        return data[:at] + piece + data[at + (len(piece) if overwrite else 0) :]

    def crossover(self, data: bytes) -> bytes:
        if not self.corpus:
            return data
        other = self.rng.choice(self.corpus)
        return data[: self._pos(data)] + other[self._pos(other) :]

    def token_insert(self, data: bytes) -> bytes:
        at = self._pos(data)
        return data[:at] + self.rng.choice(DICTIONARY) + data[at:]

    def token_replace(self, data: bytes) -> bytes:
        token = self.rng.choice(DICTIONARY)
        start, end = self._span(data, max(2, len(token)))
        return data[:start] + token + data[end:]

    def deep_nest(self, data: bytes) -> bytes:
        unit = self.rng.choice(_NEST_UNITS)
        count = min(self.max_size // (2 * len(unit)), int(math.exp(self.rng.uniform(math.log(8), math.log(120_000)))))
        closer = b"" if self.rng.random() < 0.5 else bytes(reversed(unit.translate(_CLOSERS))) * count
        at = self._pos(data)
        return data[:at] + unit * count + closer + data[at:]

    def unterminate(self, data: bytes) -> bytes:
        """Cut the input right after an opening quote/IRI/list/object character (or anywhere)."""
        spots = [m.end() for m in _QUOTE_POSITIONS.finditer(data)]
        if not spots or self.rng.random() < 0.2:
            return data[: self._pos(data)]
        return data[: self.rng.choice(spots)]

    def long_literal(self, data: bytes) -> bytes:
        opener, closer = self.rng.choice(((b'"', b'"'), (b"<", b">"), (b'"""', b'"""'), (b'"@', b""), (b"_:", b"")))
        body = self.rng.choice((b"a", b"\\u00e9", b"\xc3\xa9", b" ", b"\\", b"http://e/"))
        count = min(self.max_size // len(body) // 2, int(math.exp(self.rng.uniform(math.log(64), math.log(100_000)))))
        end = closer if self.rng.random() < 0.6 else b""
        at = self._pos(data)
        return data[:at] + opener + body * count + end + data[at:]

    def reencode(self, data: bytes) -> bytes:
        """Wrap the whole document in a BOM or re-encode it as UTF-16/32 (with or without BOM) or Latin-1."""
        text = data.decode("utf-8", errors="replace")
        kind = self.rng.choice(("bom8", "u16", "u16le", "u16be", "u32", "u32le", "u32be", "latin1", "half"))
        encoders: dict[str, Callable[[], bytes]] = {
            "bom8": lambda: b"\xef\xbb\xbf" + data,
            "u16": lambda: text.encode("utf-16", errors="replace"),
            "u16le": lambda: text.encode("utf-16-le", errors="replace"),
            "u16be": lambda: text.encode("utf-16-be", errors="replace"),
            "u32": lambda: text.encode("utf-32", errors="replace"),
            "u32le": lambda: text.encode("utf-32-le", errors="replace"),
            "u32be": lambda: text.encode("utf-32-be", errors="replace"),
            "latin1": lambda: text.encode("latin-1", errors="replace"),
            "half": lambda: data[: len(data) // 2] + text[len(text) // 2 :].encode("utf-16-le", errors="replace"),
        }
        return encoders[kind]()

    def line_shuffle(self, data: bytes) -> bytes:
        lines = data.split(b"\n")
        for _ in range(self.rng.randint(1, 4)):
            i, j = self.rng.randrange(len(lines)), self.rng.randrange(len(lines))
            action = self.rng.choice(("swap", "dup", "drop"))
            if action == "swap":
                lines[i], lines[j] = lines[j], lines[i]
            elif action == "dup":
                lines.insert(i, lines[j])
            elif len(lines) > 1:
                del lines[i]
        return b"\n".join(lines)


_CLOSERS = bytes.maketrans(b"[({<", b"])}>")


# ------------------------------------------------------------------------------------- cases and failures


@dataclass(frozen=True)
class Case:
    """One fuzz input: the target, the file extension, a target-specific option string and the bytes."""

    target: str
    ext: str
    opt: str
    data: bytes

    @property
    def stem(self) -> str:
        return f"{self.target}__{self.ext.lstrip('.') or 'none'}__{self.opt}"


@dataclass(frozen=True)
class Failure:
    """What went wrong, with the stable ``signature`` used for deduplication and shrinking."""

    kind: str
    detail: str
    key: str
    trace: str = field(default="", compare=False)

    @property
    def signature(self) -> str:
        return hashlib.sha1(self.key.encode(), usedforsecurity=False).hexdigest()[:10]


@dataclass(frozen=True)
class Outcome:
    """Result of one execution: a coarse label (for corpus feedback) and the failure, if any."""

    label: str
    failure: Failure | None = None


def case_filename(case: Case, signature: str) -> str:
    return f"{case.stem}__{signature}.bin"


def parse_case_path(path: Path) -> Case:
    """Rebuild a :class:`Case` from a saved ``<target>__<ext>__<opt>__<sig>.bin`` file."""
    parts = path.stem.split("__")
    if len(parts) < 3 or parts[0] not in TARGETS:
        raise ValueError(f"{path.name} is not named <target>__<ext>__<opt>__<signature>.bin")
    ext = "" if parts[1] == "none" else f".{parts[1]}"
    return Case(parts[0], ext, parts[2], path.read_bytes())


def signature_of_path(path: Path) -> str:
    return path.name.removesuffix(".bin").removesuffix(".orig").split("__")[-1]


_DEEP_KINDS = frozenset({"RecursionError", "MemoryError", "CaseTimeout"})


def _frames(exc: BaseException) -> list[str]:
    frames = list(traceback.extract_tb(exc.__traceback__))
    while frames and Path(frames[0].filename).name == "fuzzer.py":
        frames.pop(0)
    return [f"{Path(f.filename).name}:{f.name}" for f in frames]


def failure_from_exception(target: str, exc: BaseException) -> Failure:
    """Classify an exception; deep-stack kinds are keyed on the entry frames, others on the raising frame."""
    if isinstance(exc, InvariantViolation):
        return Failure(exc.kind, exc.detail, f"{target}|{exc.kind}", "".join(traceback.format_exception(exc)))
    kind = type(exc).__name__
    frames = _frames(exc)
    where = ">".join(frames[:3]) if kind in _DEEP_KINDS else (frames[-1] if frames else "")
    text = "".join(traceback.format_exception(exc, limit=-12))
    return Failure(kind, str(exc)[:300], f"{target}|{kind}|{where}", text)


# ----------------------------------------------------------------------------------------- safety nets


if sys.platform == "win32":

    @contextlib.contextmanager
    def deadline(seconds: float) -> Generator[None]:
        """No SIGALRM here: only an after-the-fact check (a hang cannot be interrupted)."""
        start = time.monotonic()
        yield
        if time.monotonic() - start > seconds:
            raise CaseTimeout(f"took {time.monotonic() - start:.1f}s (limit {seconds}s)")

else:

    @contextlib.contextmanager
    def deadline(seconds: float) -> Generator[None]:
        """Interrupt the running case with :class:`CaseTimeout` after ``seconds`` (main thread, POSIX)."""

        def fire(signum: int, frame: object) -> None:
            raise CaseTimeout(f"exceeded {seconds}s")

        previous = signal.signal(signal.SIGALRM, fire)
        signal.setitimer(signal.ITIMER_REAL, seconds)
        try:
            yield
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)


def limit_memory(megabytes: int) -> None:
    """Cap the address space on Linux (elsewhere RLIMIT_AS is unreliable); ``MemoryError`` then becomes a failure."""
    if megabytes > 0 and sys.platform == "linux":
        limit = megabytes * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


@contextlib.contextmanager
def record_network() -> Generator[list[str]]:
    """Refuse and record every socket operation that reaches the real socket layer.

    ontolint's own guard (installed inside ``load_graph``) shadows this one while it is active, so what lands
    here escaped it.  The originals are restored even when a watchdog interrupted an inner guard.
    """
    seen: list[str] = []

    def connect(self: socket.socket, address: Any, /) -> None:
        seen.append(f"connect {address!r}")
        raise ConnectionRefusedError(address)

    def connect_ex(self: socket.socket, address: Any, /) -> int:
        seen.append(f"connect_ex {address!r}")
        return 111

    def create_connection(address: Any, *args: Any, **kwargs: Any) -> socket.socket:
        seen.append(f"create_connection {address!r}")
        raise ConnectionRefusedError(address)

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        seen.append(f"getaddrinfo {host!r}")
        raise socket.gaierror(host)

    patches: tuple[tuple[Any, str, Any], ...] = (
        (socket.socket, "connect", connect),
        (socket.socket, "connect_ex", connect_ex),
        (socket, "create_connection", create_connection),
        (socket, "getaddrinfo", getaddrinfo),
    )
    originals = [(owner, name, getattr(owner, name)) for owner, name, _ in patches]
    for owner, name, replacement in patches:
        setattr(owner, name, replacement)
    try:
        yield seen
    finally:
        for owner, name, original in originals:
            setattr(owner, name, original)


# ------------------------------------------------------------------------------------------ the targets

DOCUMENTED_PARSE_ERRORS = (RdflibError, SyntaxError, ValueError, SAXException)
"""What an RDF parser may raise for malformed input (rdflib's ParserError/BadSyntax, expat/JSON/decoding errors)."""

CLEAN_ONTOLOGY = FIXTURES / "clean.ttl"
CLEAN_SHAPES = FIXTURES / "clean_shapes.ttl"
POLICY_FIXTURE = FIXTURES / "policy.json"
_BASELINE_STUB = b'{"fingerprints": ["deadbeef", "0123456789abcdef"]}\n'


class Workdir:
    """A reusable scratch directory (outside the repository) holding the files of the current case."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="ontolint-fuzz-")
        self.root = Path(self._tmp.name)

    def reset(self) -> None:
        for child in self.root.iterdir():
            child.unlink()

    def write(self, name: str, data: bytes) -> Path:
        path = self.root / name
        path.write_bytes(data)
        return path

    def close(self) -> None:
        self._tmp.cleanup()


def loader_policy(opt: str) -> Policy:
    """``-`` defaults, ``t<N>`` caps triples at N, ``b<N>`` caps the input at N bytes."""
    if opt[:1] == "t" and opt[1:].isdigit():
        return Policy(max_triples=max(1, int(opt[1:])))
    if opt[:1] == "b" and opt[1:].isdigit():
        return Policy(max_input_bytes=max(1, int(opt[1:])))
    return Policy()


def _load(path: Path, root: Path, policy: Policy) -> tuple[Graph | None, str]:
    """``load_graph`` with the loader's contract enforced: a Graph, InputRejected or a parse error; nothing else."""
    item = resolve_inputs([str(path)], root)[0]
    size = path.stat().st_size
    try:
        graph = load_graph(item, policy, root)
    except InputRejected as exc:
        if not exc.rule_id.startswith("SEC") or not exc.message:
            raise InvariantViolation("loader:bad-rejection", f"{exc.rule_id}: {exc.message}") from exc
        return None, f"rej:{exc.rule_id}"
    except DOCUMENTED_PARSE_ERRORS as exc:
        return None, f"err:{type(exc).__name__}"
    if size > policy.max_input_bytes:
        raise InvariantViolation("loader:input-limit-ignored", f"{size} > {policy.max_input_bytes}")
    if len(graph) > policy.max_triples:
        raise InvariantViolation("loader:triple-limit-ignored", f"{len(graph)} > {policy.max_triples}")
    return graph, "ok"


def _run_loader(case: Case, work: Workdir) -> str:
    path = work.write(f"input{case.ext}", case.data)
    return _load(path, work.root, loader_policy(case.opt))[1]


_SHAPES_ERRORS = frozenset({"ReportableRuntimeError", "ShapeLoadError", "ConstraintLoadError", "ValidationFailure"})
"""pySHACL's own refusals of malformed shapes: a reported FAILED execution, not a crash."""

_LINT_KWARGS: dict[str, dict[str, Any]] = {
    "ont": {},
    "shp": {},
    "ontb": {"base": "http://e/", "languages": ("en", "FR"), "depth_limit": 1, "inheritance_limit": 1},
}


def _family(rule_id: str) -> str:
    """``IRI016`` -> ``IRI``: one bug usually fails several rules of a family, which share a signature."""
    return rule_id.rstrip("0123456789")


def _run_lint(case: Case, work: Workdir) -> str:
    mutant = work.write(f"input{case.ext}", case.data)
    policy = Policy(max_triples=50_000)
    shapes: Graph | None = None
    if case.opt == "shp":
        ontology = work.write("ontology.ttl", CLEAN_ONTOLOGY.read_bytes())
        graph, label = _load(ontology, work.root, policy)
        shapes, label = _load(mutant, work.root, policy)
        if graph is None or shapes is None:
            return label
    else:
        graph, label = _load(mutant, work.root, policy)
        if graph is None:
            return label
    kwargs = _LINT_KWARGS.get(case.opt, {})
    first = Linter(graph, shapes, **kwargs).execute()
    for execution in first.with_status(ExecutionStatus.FAILED):
        error = execution.detail.split(":", 1)[0]
        if not (execution.rule_id == "SHACL001" and error in _SHAPES_ERRORS):
            raise InvariantViolation(f"lint:rule-failed:{_family(execution.rule_id)}:{error}", execution.detail[:300])
    if Linter(graph, shapes, **kwargs).execute() != first:
        raise InvariantViolation("lint:execute-nondeterministic")
    if Linter(graph, shapes, **kwargs).run() != Linter(graph, shapes, **kwargs).run():
        raise InvariantViolation("lint:run-nondeterministic")
    return f"lint-ok:{len(first.findings) > 0}"


@dataclass(frozen=True)
class _Options:
    """The ingredients the random option builders draw from."""

    work: Workdir
    mutant: Path


@dataclass(frozen=True)
class RuleTokens:
    ids: tuple[str, ...]
    families: tuple[str, ...]


_RULE_TOKENS: RuleTokens | None = None


def rule_tokens() -> RuleTokens:
    global _RULE_TOKENS  # noqa: PLW0603 -- lazily computed constant
    if _RULE_TOKENS is None:
        specs = default_registry().all()
        _RULE_TOKENS = RuleTokens(tuple(s.rule_id for s in specs), tuple(sorted({s.family for s in specs})))
    return _RULE_TOKENS


_BAD_INTS = (-1, 0, 1, 2, 3, 10, 100, 2**31, 2**63, 10**30)
_BASES = (
    "http://e/",
    "http://example.org/",
    "",
    "urn:x:",
    "http://127.0.0.1:9/",
    "\u202e",
    "x" * 500,
    "http://example.org/onto#",
)
_LANGS = ("en", "FR", "", "en-GB", "*", "\u202e")


def _selectors(rng: random.Random) -> str:
    tokens = rule_tokens()
    pool = [*tokens.ids, *tokens.families, "NOPE001", "", " ", "all", "lex,OWL", "ALL"]
    return ",".join(rng.choice(pool) for _ in range(rng.randint(1, 3)))


def _opt_shapes(rng: random.Random, o: _Options) -> list[str]:
    path = o.mutant if rng.random() < 0.4 else o.work.write("shapes.ttl", CLEAN_SHAPES.read_bytes())
    return ["--shapes", str(path)]


def _opt_config(rng: random.Random, o: _Options) -> list[str]:
    return ["--config", str(o.work.write("config.json", POLICY_FIXTURE.read_bytes()))]


def _opt_baseline(rng: random.Random, o: _Options) -> list[str]:
    stub = o.work.write("baseline.json", _BASELINE_STUB)
    pick = rng.choice(("read", "write", "both", "missing"))
    out: list[str] = []
    if pick in ("read", "both"):
        out += ["--baseline", str(stub)]
    if pick in ("write", "both"):
        out += ["--write-baseline", str(o.work.root / "written.json")]
    if pick == "missing":
        out += ["--baseline", str(o.work.root / "absent.json")]
    return out


_OPTION_BUILDERS: tuple[tuple[float, Callable[[random.Random, _Options], list[str]]], ...] = (
    (0.5, lambda r, o: ["--select", _selectors(r)]),
    (0.4, lambda r, o: ["--ignore", _selectors(r)]),
    (0.3, lambda r, o: ["--profile", r.choice(sorted(PROFILES))]),
    (0.6, lambda r, o: ["--format", r.choice(cli.FORMATS)]),
    (0.4, lambda r, o: ["--fail-on", r.choice(["error", "warning", "info", "never"])]),
    (0.4, lambda r, o: ["--base", r.choice(_BASES)]),
    (0.3, lambda r, o: ["--language", r.choice(_LANGS)]),
    (0.15, lambda r, o: ["--language", r.choice(_LANGS), "--language", r.choice(_LANGS)]),
    (0.3, lambda r, o: ["--depth-limit", str(r.choice(_BAD_INTS))]),
    (0.3, lambda r, o: ["--inheritance-limit", str(r.choice(_BAD_INTS))]),
    (0.3, lambda r, o: ["--soup-limit", str(r.choice(_BAD_INTS))]),
    (0.2, lambda r, o: ["--max-input-bytes", str(r.choice((1, 64, 512, 4096)))]),
    (0.2, lambda r, o: ["--max-triples", str(r.choice((1, 5, 20, 1000)))]),
    (0.3, _opt_shapes),
    (0.15, _opt_config),
    (0.15, _opt_baseline),
    (0.15, lambda r, o: ["--output", str(o.work.root / "report.out")]),
)


def build_cli_argv(optseed: int, work: Workdir, mutant: Path) -> list[str]:
    """Deterministic random option combination (from the real parser's options) for ``optseed``."""
    rng = random.Random(optseed)
    if rng.random() < 0.03:
        info = rng.choice(
            (["--list-rules"], ["--version"], ["--explain", rng.choice((*rule_tokens().ids, "NOPE", ""))])
        )
        return [*info, "--format", rng.choice(cli.FORMATS)]
    options = _Options(work, mutant)
    argv: list[str] = []
    for probability, build in _OPTION_BUILDERS:
        if rng.random() < probability:
            argv += build(rng, options)
    return [*argv, str(mutant)]


_INFO_FLAGS = frozenset({"--list-rules", "--explain", "--version"})
_TRACEBACK = "Traceback (most recent call last)"
_LINT_STAGE_FAILURE = re.compile(r"TOOL001: lint execution failed: (\w+)")
_BASELINE_ERRORS = frozenset({"FileNotFoundError"})  # a missing --baseline file is an ordinary tool failure
_RULE_FAILED = re.compile(r"TOOL001: rule (\w+) (failed|unsupported) for [^\n]*?: (\w+):")


def _invoke_cli(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main(argv)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 2
    return code, out.getvalue(), err.getvalue()


def _check_json_report(argv: list[str], code: int, out: str, work: Workdir) -> None:
    fmt = argv[argv.index("--format") + 1] if "--format" in argv else "text"
    if fmt == "text" or code not in (0, 1) or _INFO_FLAGS.intersection(argv):
        return
    text = Path(argv[argv.index("--output") + 1]).read_text(encoding="utf-8") if "--output" in argv else out
    try:
        document = json.loads(text)
    except ValueError as exc:
        raise InvariantViolation(f"cli:invalid-{fmt}", str(exc)[:100]) from exc
    if fmt == "sarif" and not (isinstance(document, dict) and "runs" in document and document.get("version")):
        raise InvariantViolation("cli:invalid-sarif", "missing version/runs")


def check_cli(argv: list[str], work: Workdir) -> str:
    """Run the CLI once and enforce its output contract; returns a coarse outcome label."""
    code, out, err = _invoke_cli(argv)
    if code not in (0, 1, 2):
        raise InvariantViolation("cli:exit-code", str(code))
    if _TRACEBACK in err or _TRACEBACK in out:
        raise InvariantViolation("cli:traceback", err[-200:])
    stage = _LINT_STAGE_FAILURE.search(err)
    if stage and not ("--baseline" in argv and stage.group(1) in _BASELINE_ERRORS):
        raise InvariantViolation(f"cli:lint-stage-failure:{stage.group(1)}", err[-300:])
    broken = next(
        (
            m
            for m in _RULE_FAILED.finditer(err)
            if not (m.group(1).startswith("SHACL") and m.group(3) in _SHAPES_ERRORS)
        ),
        None,
    )
    if broken:
        kind = f"cli:rule-{broken.group(2)}:{_family(broken.group(1))}:{broken.group(3)}"
        raise InvariantViolation(kind, err[-300:])
    _check_json_report(argv, code, out, work)
    return f"cli-exit{code}"


def _run_cli(case: Case, work: Workdir) -> str:
    mutant = work.write(f"input{case.ext}", case.data)
    argv = build_cli_argv(int(case.opt) if case.opt.isdigit() else 0, work, mutant)
    return check_cli(argv, work)


def _run_config(case: Case, work: Workdir) -> str:
    label = "config-nondict"
    try:
        document = json.loads(case.data)
    except RecursionError:
        document, label = None, "config-recursion"
    except ValueError:
        document, label = None, "config-badjson"
    if isinstance(document, dict):
        try:
            Policy.from_mapping(document)
            label = "config-ok"
        except ValueError:
            label = "config-rejected"
    config = work.write("config.json", case.data)
    ontology = work.write("small.ttl", CLEAN_ONTOLOGY.read_bytes())
    check_cli([str(ontology), "--config", str(config), "--format", "json"], work)
    return label


_RUNNERS: dict[str, Callable[[Case, Workdir], str]] = {
    "loader": _run_loader,
    "lint": _run_lint,
    "cli": _run_cli,
    "config": _run_config,
}


class Runner:
    """Executes cases in-process with the safety nets; reuse one instance for a whole run."""

    def __init__(self, case_seconds: float = DEFAULT_CASE_SECONDS) -> None:
        self.case_seconds = case_seconds
        self.work = Workdir()
        self._log_level = logging.root.manager.disable
        logging.disable(logging.CRITICAL)  # rdflib/pyshacl log warnings for every malformed term

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self.work.close()
        logging.disable(self._log_level)

    def run(self, case: Case) -> Outcome:
        """Run one case; never raises (except KeyboardInterrupt)."""
        self.work.reset()
        label = "?"
        try:
            with warnings.catch_warnings(), record_network() as network, deadline(self.case_seconds):
                warnings.simplefilter("ignore")
                label = _RUNNERS[case.target](case, self.work)
            if network:
                raise InvariantViolation("network", network[0])
        except CaseTimeout as exc:
            return Outcome("timeout", failure_from_exception(case.target, exc))
        except Exception as exc:  # noqa: BLE001 -- anything unexpected is the finding.
            return Outcome(f"crash:{type(exc).__name__}", failure_from_exception(case.target, exc))
        return Outcome(label)


# ------------------------------------------------------------------------------------------- shrinking


def shrink(
    data: bytes,
    still_fails: Callable[[bytes], bool],
    *,
    seconds: float = 60.0,
    max_runs: int = 3000,
) -> bytes:
    """Delta-debugging reducer: drop ever smaller chunks while ``still_fails`` stays true (bounded by time/runs)."""
    deadline_at = time.monotonic() + seconds
    runs = 0

    def budget() -> bool:
        return runs < max_runs and time.monotonic() < deadline_at

    chunk = max(1, len(data) // 2)
    while data and budget():
        progress = False
        start = 0
        while start < len(data) and budget():
            candidate = data[:start] + data[start + chunk :]
            runs += 1
            if candidate != data and still_fails(candidate):
                data, progress = candidate, True
            else:
                start += chunk
        if chunk == 1 and not progress:
            break
        chunk = chunk if chunk == 1 and progress else max(1, chunk // 2)
    return data


# ---------------------------------------------------------------------------------------------- driver


@dataclass(frozen=True)
class Seed:
    name: str
    ext: str
    data: bytes


@dataclass(frozen=True)
class Corpus:
    rdf: tuple[Seed, ...]
    config: tuple[Seed, ...]


def load_corpus(corpus_dir: Path = CORPUS_DIR, fixtures_dir: Path = FIXTURES) -> Corpus:
    """Seeds from ``tests/fuzz/corpus`` plus the shared fixtures (read in place, so they cannot go stale)."""
    rdf: list[Seed] = []
    config: list[Seed] = []
    for directory in (corpus_dir, fixtures_dir):
        for path in sorted(directory.iterdir()):
            if not path.is_file() or path.suffix not in EXTENSIONS or path.stat().st_size > MAX_INPUT:
                continue
            seed = Seed(path.name, path.suffix, path.read_bytes())
            is_config = path.suffix == ".json" and (path.name.startswith("config_") or path.name == "policy.json")
            (config if is_config else rdf).append(seed)
    return Corpus(tuple(rdf), tuple(config))


def known_signatures(*directories: Path) -> frozenset[str]:
    """Signatures of already tracked bugs (file names under ``known_bugs`` and any extra directory)."""
    return frozenset(signature_of_path(p) for d in directories if d.is_dir() for p in d.glob("*.bin"))


class CaseGenerator:
    """Produces the cases of one target from a seeded RNG and a feedback-driven pool of seeds."""

    def __init__(self, target: str, seed: int, corpus: Corpus) -> None:
        self.target = target
        self.rng = random.Random(f"{seed}:{target}:gen")
        seeds = corpus.config if target == "config" else corpus.rdf
        self.pool: list[tuple[bytes, str]] = [(s.data, s.ext) for s in seeds]
        self.shapes = [(s.data, s.ext) for s in corpus.rdf if "shapes" in s.name]
        self.mutator = Mutator(f"{seed}:{target}:mut", [d for d, _ in self.pool])
        self.label_counts: Counter[str] = Counter()

    def _option(self) -> str:
        rng = self.rng
        if self.target == "loader":
            return rng.choice(("-", "-", "-", "-", f"t{rng.randint(1, 50)}", f"b{rng.randint(32, 2000)}"))
        if self.target == "lint":
            return rng.choice(("ont", "ont", "shp", "ontb"))
        if self.target == "cli":
            return str(rng.getrandbits(32))
        return "-"

    def next_case(self) -> Case:
        opt = self._option()
        pool = self.shapes if opt == "shp" and self.shapes else self.pool
        data, ext = self.rng.choice(pool)
        if self.rng.random() < 0.05:
            data = self.rng.choice(self.pool)[0]
        gentle = self.target in ("lint", "cli") and self.rng.random() < 0.7
        mutant = self.mutator.mutate(data, gentle=gentle) if self.rng.random() < 0.97 else data
        if self.target == "config":
            ext = ".json"
        elif self.rng.random() < 0.25:
            ext = self.rng.choice(EXTENSIONS)
        return Case(self.target, ext, opt, mutant)

    def feedback(self, case: Case, label: str) -> None:
        """Keep mutants whose outcome label is still rare: a cheap stand-in for coverage guidance."""
        self.label_counts[label] += 1
        if self.label_counts[label] <= 20 and len(case.data) <= 64 * 1024:
            if len(self.pool) >= 300:
                self.pool[self.rng.randrange(len(self.pool))] = (case.data, case.ext)
            else:
                self.pool.append((case.data, case.ext))


@dataclass
class TargetStats:
    executions: int = 0
    seconds: float = 0.0
    duplicates: int = 0
    labels: Counter[str] = field(default_factory=Counter[str])

    @property
    def rate(self) -> float:
        return self.executions / self.seconds if self.seconds else 0.0


@dataclass(frozen=True)
class Crash:
    case: Case
    minimised: Case
    failure: Failure


def minimise(runner: Runner, case: Case, failure: Failure, seconds: float = 60.0) -> Case:
    """Shrink ``case.data`` while the same failure signature is reproduced."""

    def same(candidate: bytes) -> bool:
        again = runner.run(Case(case.target, case.ext, case.opt, candidate)).failure
        return again is not None and again.signature == failure.signature

    return Case(case.target, case.ext, case.opt, shrink(case.data, same, seconds=seconds))


def save_crash(crash: Crash, out: Path) -> Path:
    """Write the minimised ``<name>.bin`` (replayable), ``<name>.txt`` (report) and ``orig/<name>.orig.bin``."""
    out.mkdir(parents=True, exist_ok=True)
    sig = crash.failure.signature
    name = case_filename(crash.case, sig).removesuffix(".bin")
    if len(crash.case.data) <= 64 * 1024:  # the unminimised input stays in the (git-ignored) run directory only
        (out / "orig").mkdir(exist_ok=True)
        (out / "orig" / f"{name}.orig.bin").write_bytes(crash.case.data)
    minimal = out / f"{name}.bin"
    minimal.write_bytes(crash.minimised.data)
    line = (
        f"target={crash.case.target} exc={crash.failure.kind} sig={sig} ext={crash.case.ext or 'none'} "
        f"opt={crash.case.opt} orig={len(crash.case.data)}B min={len(crash.minimised.data)}B file={minimal.name}"
    )
    (out / f"{name}.txt").write_text(f"{line}\n\n{crash.failure.detail}\n\n{crash.failure.trace}", encoding="utf-8")
    with (out / "reports.txt").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return minimal


def fuzz_target(  # noqa: PLR0913 -- a run is described by this many independent knobs.
    target: str,
    *,
    seed: int,
    seconds: float | None,
    iterations: int | None,
    runner: Runner,
    known: frozenset[str] = frozenset(),
    out: Path | None = None,
    corpus: Corpus | None = None,
    shrink_seconds: float = 60.0,
    log: Callable[[str], None] = lambda _msg: None,
) -> tuple[TargetStats, list[Crash]]:
    """Fuzz one target for ``seconds`` and/or ``iterations`` (whichever ends first); returns new crashes."""
    generator = CaseGenerator(target, seed, corpus or load_corpus())
    stats, crashes = TargetStats(), []
    seen = set(known)
    start = time.monotonic()
    while True:
        if (iterations is not None and stats.executions >= iterations) or (
            seconds is not None and time.monotonic() - start >= seconds
        ):
            break
        case = generator.next_case()
        outcome = runner.run(case)
        stats.executions += 1
        stats.labels[outcome.label] += 1
        failure = outcome.failure
        if failure is None:
            generator.feedback(case, outcome.label)
            continue
        if failure.signature in seen:
            stats.duplicates += 1
            continue
        seen.add(failure.signature)
        log(f"[{target}] NEW {failure.kind} sig={failure.signature} size={len(case.data)}; shrinking")
        crash = Crash(case, minimise(runner, case, failure, shrink_seconds), failure)
        crashes.append(crash)
        if out is not None:
            log(f"[{target}] saved {save_crash(crash, out)} ({len(crash.minimised.data)} bytes)")
    stats.seconds = time.monotonic() - start
    return stats, crashes


def replay(path: Path, case_seconds: float = DEFAULT_CASE_SECONDS) -> Failure | None:
    """Replay one saved case file and return its failure (``None`` when the invariant holds)."""
    with Runner(case_seconds) as runner:
        return runner.run(parse_case_path(path)).failure


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="ontolint mutation fuzzer (deterministic for a given --seed)")
    ap.add_argument("--seconds", type=float, default=10.0, help="time budget PER TARGET (default 10)")
    ap.add_argument("--iterations", type=int, help="stop each target after N executions (in addition to --seconds)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--target", choices=(*TARGETS, "all"), default="all")
    ap.add_argument("--out", type=Path, default=Path("fuzz-out"), help="directory for crashers (default fuzz-out)")
    ap.add_argument("--case-seconds", type=float, default=DEFAULT_CASE_SECONDS, help="per-input time limit")
    ap.add_argument("--shrink-seconds", type=float, default=60.0, help="time budget to minimise each new crash")
    ap.add_argument("--memory-mb", type=int, default=0, help="address-space cap on Linux (0 = unlimited)")
    ap.add_argument("--replay", type=Path, help="replay one saved <target>__<ext>__<opt>__<sig>.bin and exit")
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; exit status 1 when a crash with a new signature was found."""
    args = build_parser().parse_args(argv)
    limit_memory(args.memory_mb)
    if args.replay is not None:
        failure = replay(args.replay, args.case_seconds)
        print(
            "OK: invariant holds"
            if failure is None
            else f"FAIL {failure.kind} sig={failure.signature}\n{failure.trace}"
        )
        return 0 if failure is None else 1
    known = known_signatures(KNOWN_BUGS_DIR, args.out)
    targets = TARGETS if args.target == "all" else (args.target,)
    new = 0
    total = 0

    def log(message: str) -> None:
        print(message, flush=True)

    with Runner(args.case_seconds) as runner:
        for target in targets:
            stats, crashes = fuzz_target(
                target,
                seed=args.seed,
                seconds=None if args.iterations is not None else args.seconds,
                iterations=args.iterations,
                runner=runner,
                known=known,
                out=args.out,
                shrink_seconds=args.shrink_seconds,
                log=log,
            )
            new += len(crashes)
            total += stats.executions
            top = ", ".join(f"{k}={v}" for k, v in stats.labels.most_common(6))
            log(
                f"[{target}] seed={args.seed} execs={stats.executions} {stats.rate:.1f}/s new_crashes={len(crashes)} "
                f"known_hits={stats.duplicates} outcomes: {top}"
            )
    log(f"total executions: {total}; new crashes: {new}")
    return 1 if new else 0


if __name__ == "__main__":
    sys.exit(main())
