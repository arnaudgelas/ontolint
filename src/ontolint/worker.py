"""A bounded worker process: run one task in a ``spawn`` interpreter and stop it when its time is up.

A pure-Python computation (a parse, a SHACL validation, a SPARQL query) cannot be interrupted safely in this
process: a thread cannot be killed, and a signal timer (SIGALRM) exists on POSIX main threads only and collides with
any watchdog the embedding program already uses.  A worker started with the ``spawn`` method works the same on
Linux, macOS and Windows, shares no state with the parent (so a task's network guard and patched modules are applied
freshly in the worker) and can always be terminated.  The worker only ever returns plain data (one JSON object),
never pickles, so a compromised task cannot make the parent execute anything while decoding the result.

:func:`run_bounded` is the one lifecycle: start the worker, wait for it to be ready (interpreter start-up and the
task's imports are the tool's cost, not the input's, so they are bounded by :data:`WORKER_START_TIMEOUT`, not by the
budget), then give it ``seconds`` of wall-clock time to answer, and always terminate, then kill, and reap it.  A task
maps its own errors to JSON; each caller maps :class:`WorkerTimeout`, :class:`WorkerGone` and
:class:`WorkerFailed` to its own messages.  The JSON graph codec (:func:`encode_graph`, :func:`decode_graph`) lets a
task hand graphs across.
"""

from __future__ import annotations

import json
import logging
import multiprocessing
import sys
from collections.abc import Sequence
from typing import Any, Protocol, TextIO, cast

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.term import Node

from .redaction import RedactingStream

WORKER_START_TIMEOUT = 120.0
"""Seconds to wait for the worker interpreter to start (imports); not part of the caller's budget."""
_WORKER_GRACE = 2.0

type Triple = tuple[Node, Node, Node]
_Term = list[Any]


class WorkerTask(Protocol):
    """One job for :func:`run_bounded`; it must be picklable (a module-level dataclass of plain data)."""

    def prepare(self) -> None:
        """Do the input-independent set-up (heavy imports); runs before the worker reports ready."""

    def run(self) -> bytes:
        """Do the work and return one JSON object, mapping the task's own errors into it."""
        ...  # pragma: no cover - a protocol


class WorkerTimeout(Exception):  # noqa: N818 -- an outcome, like TimeoutError
    """The worker did not answer within its budget; it was stopped."""


class WorkerGone(Exception):  # noqa: N818 -- an outcome: the worker went away
    """The worker never became ready, or exited without an answer."""


class WorkerFailed(Exception):  # noqa: N818 -- an outcome: the task raised in the worker
    """The task raised an exception the task itself did not map; ``cause_type`` names its class."""

    def __init__(self, cause_type: str, detail: str) -> None:
        super().__init__(f"{cause_type}: {detail}")
        self.cause_type = cause_type
        self.detail = detail


def _worker_main(connection: Any, task: WorkerTask, rdflib_level: int | None = None) -> None:
    """Entry point of the worker: prepare, announce readiness, run the task, send one JSON object, exit.

    A ``spawn`` worker starts with the process's own stderr and default logging, so it takes the parent's level
    for rdflib's logger and masks what it writes to stderr (:mod:`ontolint.redaction`): rdflib's warning about an
    IRI it cannot serialise quotes the IRI.
    """
    if rdflib_level is not None:
        logging.getLogger("rdflib").setLevel(rdflib_level)
    stderr = sys.stderr
    redacting = None if stderr is None else RedactingStream(stderr)  # None under pythonw
    if redacting is not None:
        sys.stderr = cast("TextIO", redacting)
    try:
        _serve(connection, task)
    finally:
        if redacting is not None:
            redacting.drain()
        sys.stderr = stderr


def _serve(connection: Any, task: WorkerTask) -> None:
    task.prepare()
    connection.send_bytes(b"ready")
    try:
        reply = task.run()
    except BaseException as exc:  # noqa: BLE001 -- the parent must always receive an answer.
        detail = str(exc) if isinstance(exc, Exception) else ""
        reply = json.dumps({"worker_error": [type(exc).__name__, detail]}).encode()
    connection.send_bytes(reply)
    connection.close()


def run_bounded(task: WorkerTask, seconds: float, *, name: str) -> dict[str, Any]:
    """Run ``task`` in a ``spawn`` worker, give it ``seconds`` from the moment it is ready, return its JSON object.

    Raises :class:`WorkerTimeout` when the budget is exhausted, :class:`WorkerGone` (``"the <name> worker ..."``)
    when the worker never starts or exits without an answer, and :class:`WorkerFailed` when the task raised.
    """
    context = multiprocessing.get_context("spawn")
    # gremlin: pardon[equivalent] the parent only reads and the worker only writes; duplex adds no behaviour
    receiver, sender = context.Pipe(duplex=False)
    # gremlin: pardon[equivalent] the worker is always stopped in `finally`, so daemon only matters if the parent dies
    rdflib_level = logging.getLogger("rdflib").level
    process = context.Process(target=_worker_main, args=(sender, task, rdflib_level), daemon=True)
    process.start()
    sender.close()  # the parent only reads: EOF on the pipe means the worker is gone
    try:
        if not _ready(receiver, WORKER_START_TIMEOUT):
            raise WorkerGone(f"the {name} worker did not start")
        if not receiver.poll(seconds):
            raise WorkerTimeout(f"the {name} worker did not answer within {seconds:g} seconds")
        try:
            raw = receiver.recv_bytes()
        except (EOFError, OSError):
            raise WorkerGone(_worker_death(process, name)) from None
    finally:
        receiver.close()
        _stop(process)
    reply = _json_object(raw, name)
    if "worker_error" in reply:
        cause_type, detail = reply["worker_error"]
        raise WorkerFailed(str(cause_type), str(detail))
    return reply


def _json_object(raw: bytes, name: str) -> dict[str, Any]:
    try:
        reply = json.loads(raw)
    except ValueError:
        reply = None
    if not isinstance(reply, dict):
        raise WorkerGone(f"the {name} worker sent a reply that is not a JSON object")
    return reply


def _stop(process: Any) -> None:
    """Terminate, then kill, the worker and reap it; safe to call on a worker that already exited."""
    if process.is_alive():
        process.terminate()
        process.join(_WORKER_GRACE)
    if process.is_alive():
        process.kill()
    process.join()
    process.close()


def _ready(receiver: Any, timeout: float) -> bool:
    try:
        return bool(receiver.poll(timeout)) and receiver.recv_bytes() == b"ready"
    except (EOFError, OSError):
        # gremlin: pardon[equivalent] None and False are both falsy for the only caller, `if not _ready(...)`
        return False


def _worker_death(process: Any, name: str) -> str:
    process.join(_WORKER_GRACE)
    return f"the {name} worker exited without a result (exit code {process.exitcode})"


# --- the graph codec: triples and prefixes as JSON ---------------------------------------------------------------


def encode_term(term: Node) -> _Term:
    """One RDF term as JSON: ``["u", iri]``, ``["b", label]`` or ``["l", lexical form, language, datatype]``."""
    if isinstance(term, Literal):
        return ["l", str(term), term.language, None if term.datatype is None else str(term.datatype)]
    return ["b" if isinstance(term, BNode) else "u", str(term)]


def decode_term(raw: _Term) -> Node:
    """The term :func:`encode_term` wrote; a literal keeps its lexical form exactly (no normalisation)."""
    kind = raw[0]
    if kind == "u":
        return URIRef(raw[1])
    if kind == "b":
        return BNode(raw[1])
    return Literal(raw[1], lang=raw[2], datatype=None if raw[3] is None else URIRef(raw[3]), normalize=False)


def graph_document(graph: Graph, triples: Sequence[Triple]) -> dict[str, Any]:
    """``triples`` (all of ``graph``'s, in the order a caller indexes them by) and ``graph``'s prefixes, as JSON."""
    return {
        "triples": [[encode_term(t) for t in triple] for triple in triples],
        "namespaces": [[prefix, str(uri)] for prefix, uri in graph.namespaces()],
    }


def encode_graph(graph: Graph) -> bytes:
    """``graph`` as one compact JSON object (see :func:`graph_document`)."""
    return json.dumps(graph_document(graph, list(graph)), separators=(",", ":")).encode()


def decode_graph_document(payload: dict[str, Any]) -> tuple[Graph, list[Triple]]:
    """The graph of a :func:`graph_document`, with its triples in payload order; its prefixes replace the defaults."""
    graph = Graph()
    for prefix, uri in payload["namespaces"]:
        graph.bind(prefix, URIRef(uri), override=True, replace=True)
    triples: list[Triple] = [(decode_term(s), decode_term(p), decode_term(o)) for s, p, o in payload["triples"]]
    graph.addN((s, p, o, graph) for s, p, o in triples)
    return graph, triples


def decode_graph(payload: dict[str, Any]) -> Graph:
    """The graph of a :func:`graph_document`."""
    return decode_graph_document(payload)[0]
