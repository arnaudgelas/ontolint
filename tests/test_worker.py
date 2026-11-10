"""The bounded worker (:mod:`ontolint.worker`): lifecycle, budget, replies and the JSON graph codec.

The tasks are stubs, so these cases prove the lifecycle for any task (the parse, the SHACL validation and a
future SPARQL query); ``test_parse_budget.py`` and ``test_validation_budget.py`` check how each caller maps it.
"""

# ruff: noqa: PLR2004, SLF001

from __future__ import annotations

import json
import multiprocessing
import os
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import XSD

from ontolint import worker
from ontolint.worker import WorkerFailed, WorkerGone, WorkerTimeout, run_bounded

GENEROUS = 120.0


@dataclass(frozen=True)
class EchoTask:
    """Answers with what it was given."""

    text: str

    def prepare(self) -> None:
        pass

    def run(self) -> bytes:
        return json.dumps({"echo": self.text}).encode()


@dataclass(frozen=True)
class HangTask:
    """Stand-in for an endless computation: ready, then never answers."""

    def prepare(self) -> None:
        pass

    def run(self) -> bytes:
        time.sleep(600)
        return b"{}"  # pragma: no cover - killed first


@dataclass(frozen=True)
class ExitTask:
    """Exits with ``code`` after ready (``before_ready``: while preparing)."""

    code: int
    before_ready: bool = False

    def prepare(self) -> None:
        if self.before_ready:
            os._exit(self.code)

    def run(self) -> bytes:
        os._exit(self.code)


@dataclass(frozen=True)
class SlowStartTask:
    """Never becomes ready."""

    def prepare(self) -> None:
        time.sleep(600)

    def run(self) -> bytes:  # pragma: no cover - never reached
        return b"{}"


@dataclass(frozen=True)
class RaiseTask:
    """Raises ``ValueError("bad input")``, or ``KeyboardInterrupt`` with ``interrupt``."""

    interrupt: bool = False

    def prepare(self) -> None:
        pass

    def run(self) -> bytes:
        if self.interrupt:
            raise KeyboardInterrupt
        raise ValueError("bad input")


@dataclass(frozen=True)
class RawTask:
    """Answers with ``raw`` as is."""

    raw: bytes

    def prepare(self) -> None:
        pass

    def run(self) -> bytes:
        return self.raw


class Pipe:
    """The worker's end of the pipe, in this process."""

    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.closed = False

    def send_bytes(self, data: bytes) -> None:
        self.sent.append(data)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def started_pids(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[int]]:
    """Record the pid of every worker that is stopped, to check afterwards that none survives."""
    pids: list[int] = []
    real_stop = worker._stop

    def recording_stop(process: Any) -> None:
        pids.append(process.pid)
        real_stop(process)

    monkeypatch.setattr(worker, "_stop", recording_stop)
    yield pids


def pid_exists(pid: int) -> bool:
    if sys.platform == "win32":  # pragma: no cover - os.kill(pid, 0) means CTRL_C_EVENT there
        return any(child.pid == pid for child in multiprocessing.active_children())
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


# --- the lifecycle, in a real worker process ----------------------------------------------------------------------


def test_a_task_answers_with_its_json_object(started_pids: list[int]) -> None:
    assert run_bounded(EchoTask("héllo"), GENEROUS, name="echo") == {"echo": "héllo"}
    (pid,) = started_pids
    assert not pid_exists(pid)
    assert multiprocessing.active_children() == []


def test_a_hanging_task_is_killed_at_the_budget_and_leaves_no_process(started_pids: list[int]) -> None:
    started = time.monotonic()
    with pytest.raises(WorkerTimeout, match=r"^the x worker did not answer within 0\.3 seconds$"):
        run_bounded(HangTask(), 0.3, name="x")
    assert time.monotonic() - started < 60
    (pid,) = started_pids
    assert not pid_exists(pid)
    assert multiprocessing.active_children() == []


def test_a_task_that_dies_after_ready_is_gone_with_its_exit_code(started_pids: list[int]) -> None:
    with pytest.raises(WorkerGone) as info:
        run_bounded(ExitTask(3), GENEROUS, name="validation")
    assert str(info.value) == "the validation worker exited without a result (exit code 3)"
    assert not pid_exists(started_pids[0])


def test_a_task_that_dies_before_ready_did_not_start() -> None:
    with pytest.raises(WorkerGone) as info:
        run_bounded(ExitTask(1, before_ready=True), GENEROUS, name="validation")
    assert str(info.value) == "the validation worker did not start"


def test_slow_start_is_not_counted_against_the_budget_but_has_its_own_limit(
    monkeypatch: pytest.MonkeyPatch, started_pids: list[int]
) -> None:
    monkeypatch.setattr(worker, "WORKER_START_TIMEOUT", 0.3)
    with pytest.raises(WorkerGone, match=r"^the x worker did not start$"):
        run_bounded(SlowStartTask(), GENEROUS, name="x")
    assert not pid_exists(started_pids[0])


def test_a_task_that_raises_is_a_worker_failure_naming_the_exception() -> None:
    with pytest.raises(WorkerFailed) as info:
        run_bounded(RaiseTask(), GENEROUS, name="x")
    assert (info.value.cause_type, info.value.detail) == ("ValueError", "bad input")
    assert str(info.value) == "ValueError: bad input"


@pytest.mark.parametrize("raw", [b"not json", b"[1, 2]", b'"text"'])
def test_a_reply_that_is_not_a_json_object_is_gone(raw: bytes) -> None:
    with pytest.raises(WorkerGone, match=r"^the x worker sent a reply that is not a JSON object$"):
        run_bounded(RawTask(raw), GENEROUS, name="x")


# --- the worker's entry point, in this process --------------------------------------------------------------------


def test_worker_main_prepares_then_announces_ready_then_answers_once() -> None:
    pipe = Pipe()
    worker._worker_main(pipe, EchoTask("a"))
    assert pipe.sent == [b"ready", b'{"echo": "a"}']
    assert pipe.closed


def test_worker_main_always_answers_even_on_an_interrupt() -> None:
    pipe = Pipe()
    worker._worker_main(pipe, RaiseTask(interrupt=True))
    assert pipe.sent[0] == b"ready"
    assert json.loads(pipe.sent[1]) == {"worker_error": ["KeyboardInterrupt", ""]}
    pipe = Pipe()
    worker._worker_main(pipe, RaiseTask())
    assert json.loads(pipe.sent[1]) == {"worker_error": ["ValueError", "bad input"]}


class FakeProcess:
    """A worker that ignores SIGTERM: only ``kill`` ends it."""

    def __init__(self, survives_terminate: bool) -> None:
        self.survives_terminate = survives_terminate
        self.alive = True
        self.calls: list[str] = []

    def is_alive(self) -> bool:
        return self.alive

    def terminate(self) -> None:
        self.calls.append("terminate")
        self.alive = self.survives_terminate

    def kill(self) -> None:
        self.calls.append("kill")
        self.alive = False

    def join(self, timeout: float | None = None) -> None:
        self.calls.append(f"join({timeout})")

    def close(self) -> None:
        self.calls.append("close")


def test_stop_terminates_first_and_kills_only_a_worker_that_survives() -> None:
    polite = FakeProcess(survives_terminate=False)
    worker._stop(polite)
    assert polite.calls == ["terminate", "join(2.0)", "join(None)", "close"]
    stubborn = FakeProcess(survives_terminate=True)
    worker._stop(stubborn)
    assert stubborn.calls == ["terminate", "join(2.0)", "kill", "join(None)", "close"]
    gone = FakeProcess(survives_terminate=False)
    gone.alive = False
    worker._stop(gone)
    assert gone.calls == ["join(None)", "close"]


# --- the graph codec ----------------------------------------------------------------------------------------------


def test_graph_survives_the_wire_format_exactly() -> None:
    graph = Graph()
    graph.bind("ex", "http://e/")
    node = BNode("keepme")
    graph.add((URIRef("http://e/a"), URIRef("http://e/p"), node))
    graph.add((node, URIRef("http://e/q"), Literal("hola", lang="es")))
    graph.add((node, URIRef("http://e/q"), Literal("abc", datatype=XSD.integer)))  # ill-typed, kept verbatim
    graph.add((node, URIRef("http://e/q"), Literal("007", datatype=XSD.integer)))
    graph.add((node, URIRef("http://e/q"), Literal("plain")))
    decoded = worker.decode_graph(json.loads(worker.encode_graph(graph)))
    assert set(decoded) == set(graph)
    assert {str(t.datatype) for _, _, t in decoded if isinstance(t, Literal) and t.datatype} == {str(XSD.integer)}
    assert Literal("007", datatype=XSD.integer) in {o for _, _, o in decoded}
    assert dict(decoded.namespaces())["ex"] == URIRef("http://e/")


def test_decoded_triples_keep_the_payload_order() -> None:
    triples = [(URIRef(f"http://e/{n}"), URIRef("http://e/p"), Literal(n)) for n in "cab"]
    graph = Graph()
    for triple in triples:
        graph.add(triple)
    payload = worker.graph_document(graph, triples)
    decoded, order = worker.decode_graph_document(json.loads(json.dumps(payload)))
    assert order == triples
    assert set(decoded) == set(triples)
