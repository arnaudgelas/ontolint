"""SEC003: the parse time budget (``max_parse_seconds`` / ``--max-parse-seconds``) and its worker process."""

# ruff: noqa: PLR2004, SLF001

from __future__ import annotations

import contextlib
import io
import json
import math
import multiprocessing
import os
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.compare import isomorphic
from rdflib.namespace import XSD

from ontolint import loader, main
from ontolint.cli import build_parser
from ontolint.loader import InputRejected, ParseFailure, load_graph
from ontolint.paths import InputFile, resolve_inputs
from ontolint.policy import MAX_PARSE_SECONDS, Policy

TTL = "@prefix e: <http://e/> .\ne:a e:p 1, 2, 3 .\n"
BUDGET = 0.05
GENEROUS = 120.0


@pytest.fixture(scope="module")
def big_ttl(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """About 125k triples: seconds of pure-Python parsing, so a 50 ms budget can never be met."""
    folder = tmp_path_factory.mktemp("big")
    lines = ["@prefix e: <http://e/> ."]
    lines += [f'e:s{i} e:p "v{i}" ; e:q e:o{i % 50} ; e:r {i} ; e:t [ e:u "x" ] .' for i in range(25000)]
    (folder / "big.ttl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return folder


def load(folder: Path, name: str, data: str | bytes, policy: Policy) -> Graph:
    path = folder / name
    path.write_bytes(data if isinstance(data, bytes) else data.encode())
    return load_graph(resolve_inputs([name], folder)[0], policy, folder)


# --- Policy and CLI ----------------------------------------------------------------------------------


def test_budget_is_off_by_default() -> None:
    assert Policy().max_parse_seconds is None
    assert Policy.from_mapping({}).max_parse_seconds is None
    assert Policy.from_mapping({"max_parse_seconds": None}).max_parse_seconds is None


@pytest.mark.parametrize("value", [0.001, 0.5, 1, 30, MAX_PARSE_SECONDS])
def test_valid_budgets_are_accepted_and_stored_as_float(value: float) -> None:
    assert Policy(max_parse_seconds=value).max_parse_seconds == value
    stored = Policy.from_mapping({"max_parse_seconds": value}).max_parse_seconds
    assert stored == float(value)
    assert isinstance(stored, float)


@pytest.mark.parametrize(
    "value",
    [True, False, 0, 0.0, -1, -0.5, math.nan, math.inf, -math.inf, 1e9, MAX_PARSE_SECONDS + 1, 10**400, "5", [1], {}],
)
def test_invalid_budgets_raise_value_error_only(value: Any) -> None:
    with pytest.raises(ValueError, match="max_parse_seconds"):
        Policy(max_parse_seconds=value)
    with pytest.raises(ValueError, match="max_parse_seconds"):
        Policy.from_mapping({"max_parse_seconds": value})


def test_validation_messages() -> None:
    with pytest.raises(ValueError, match="^max_parse_seconds must be positive$"):
        Policy(max_parse_seconds=0)
    with pytest.raises(ValueError, match="^max_parse_seconds must be at most 86400$"):
        Policy(max_parse_seconds=86401)
    with pytest.raises(ValueError, match="^max_parse_seconds must be a finite number$"):
        Policy(max_parse_seconds=math.nan)


def parse_option(*argv: str) -> float | None:
    return build_parser().parse_args(["a.ttl", *argv]).max_parse_seconds


def test_cli_option_defaults_to_none_and_parses_floats() -> None:
    assert parse_option() is None
    assert parse_option("--max-parse-seconds", "0.25") == 0.25
    assert parse_option("--max-parse-seconds", "3") == 3.0


@pytest.mark.parametrize("text", ["0", "-1", "nan", "inf", "x", "", "86401", "1e9"])
def test_cli_option_rejects_non_positive_non_finite_and_huge(text: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        parse_option("--max-parse-seconds", text)
    assert info.value.code == 2
    assert "--max-parse-seconds" in capsys.readouterr().err


def test_cli_option_overrides_the_policy_file(tmp_path: Path) -> None:
    from ontolint.cli import _policy  # noqa: PLC0415

    config = Policy(max_parse_seconds=5.0)
    args = build_parser().parse_args(["a.ttl"])
    assert _policy(args, config, frozenset()).max_parse_seconds == 5.0
    args = build_parser().parse_args(["a.ttl", "--max-parse-seconds", "7"])
    assert _policy(args, config, frozenset()).max_parse_seconds == 7.0


# --- term encoding -----------------------------------------------------------------------------------


def test_graph_survives_the_wire_format_exactly() -> None:
    graph = Graph()
    graph.bind("ex", "http://e/")
    node = BNode("keepme")
    graph.add((URIRef("http://e/a"), URIRef("http://e/p"), node))
    graph.add((node, URIRef("http://e/q"), Literal("hola", lang="es")))
    graph.add((node, URIRef("http://e/q"), Literal("abc", datatype=XSD.integer)))  # ill-typed, kept verbatim
    graph.add((node, URIRef("http://e/q"), Literal("007", datatype=XSD.integer)))
    graph.add((node, URIRef("http://e/q"), Literal("plain")))
    decoded = loader._decode_graph(json.loads(loader._encode_graph(graph)))
    assert set(decoded) == set(graph)
    assert {str(t.datatype) for _, _, t in decoded if isinstance(t, Literal) and t.datatype} == {str(XSD.integer)}
    assert Literal("007", datatype=XSD.integer) in {o for _, _, o in decoded}
    assert dict(decoded.namespaces())["ex"] == URIRef("http://e/")


# --- the worker --------------------------------------------------------------------------------------


def test_parse_within_the_budget_equals_the_in_process_parse(tmp_path: Path) -> None:
    direct = load(tmp_path, "a.ttl", TTL, Policy())
    budgeted = load(tmp_path, "a.ttl", TTL, Policy(max_parse_seconds=GENEROUS))
    assert isomorphic(direct, budgeted)
    assert len(budgeted) == 3


def test_exceeding_the_budget_is_sec003_with_an_exact_message(big_ttl: Path) -> None:
    started = time.monotonic()
    with pytest.raises(InputRejected) as info:
        load(big_ttl, "big.ttl", (big_ttl / "big.ttl").read_bytes(), Policy(max_parse_seconds=BUDGET))
    assert info.value.rule_id == "SEC003"
    assert info.value.message == "big.ttl was not parsed within the time budget of 0.05 seconds (max_parse_seconds)"
    assert time.monotonic() - started < 60  # killed long before the ~2 s the parse would have needed


def test_the_same_input_parses_when_the_budget_is_generous(big_ttl: Path) -> None:
    graph = load(big_ttl, "big.ttl", (big_ttl / "big.ttl").read_bytes(), Policy(max_parse_seconds=GENEROUS))
    assert len(graph) == 125000


def test_cli_reports_sec003_on_stderr_and_exits_2(big_ttl: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with contextlib.chdir(big_ttl):
        code = main(["big.ttl", "--select", "ONT001", "--max-parse-seconds", str(BUDGET)])
    assert code == 2
    assert capsys.readouterr().err == (
        "SEC003: big.ttl was not parsed within the time budget of 0.05 seconds (max_parse_seconds)\n"
    )


def test_cli_without_the_option_never_starts_a_worker(tmp_path: Path) -> None:
    (tmp_path / "a.ttl").write_text(TTL, encoding="utf-8")
    with (
        contextlib.chdir(tmp_path),
        mock.patch.object(multiprocessing, "get_context", side_effect=AssertionError("worker used")),
        contextlib.redirect_stdout(io.StringIO()),
    ):
        assert main(["a.ttl", "--select", "ONT001"]) in {0, 1}


def test_config_file_budget_reaches_the_loader(big_ttl: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (big_ttl / "cfg.json").write_text(json.dumps({"max_parse_seconds": BUDGET}), encoding="utf-8")
    with contextlib.chdir(big_ttl):
        code = main(["big.ttl", "--select", "ONT001", "--config", "cfg.json"])
    assert code == 2
    assert capsys.readouterr().err.startswith("SEC003: ")


# --- limits and guards hold inside the worker --------------------------------------------------------


def test_triple_limit_is_enforced_in_the_worker(tmp_path: Path) -> None:
    with pytest.raises(InputRejected) as info:
        load(tmp_path, "a.ttl", TTL, Policy(max_triples=2, max_parse_seconds=GENEROUS))
    assert (info.value.rule_id, info.value.message) == ("SEC002", "graph has more than 2 triples (max_triples)")
    assert len(load(tmp_path, "a.ttl", TTL, Policy(max_triples=3, max_parse_seconds=GENEROUS))) == 3


def test_size_limit_and_compression_are_checked_before_any_worker_starts(tmp_path: Path) -> None:
    with mock.patch.object(multiprocessing, "get_context", side_effect=AssertionError("worker used")):
        with pytest.raises(InputRejected) as info:
            load(tmp_path, "a.ttl", TTL, Policy(max_input_bytes=5, max_parse_seconds=GENEROUS))
        assert info.value.rule_id == "SEC001"
        with pytest.raises(InputRejected) as info:
            load(tmp_path, "a.ttl", b"\x1f\x8bxx", Policy(max_parse_seconds=GENEROUS))
        assert info.value.rule_id == "SEC011"


def test_remote_jsonld_context_is_refused_in_the_worker(tmp_path: Path) -> None:
    remote = '{"@context": "http://127.0.0.1:9/ctx.jsonld", "@id": "http://e/a", "http://e/p": "x"}'
    with pytest.raises(InputRejected) as info:
        load(tmp_path, "r.jsonld", remote, Policy(max_parse_seconds=GENEROUS))
    assert info.value.rule_id == "SEC006"
    assert info.value.message == (
        "r.jsonld references an external JSON-LD context 'http://127.0.0.1:9/ctx.jsonld'; refused"
    )


def test_parser_failure_in_the_worker_is_a_parse_failure(tmp_path: Path) -> None:
    with pytest.raises(ParseFailure) as info:
        load(tmp_path, "bad.ttl", "this is not turtle", Policy(max_parse_seconds=GENEROUS))
    assert info.value.rule_id == "INPUT001"
    assert info.value.cause_type
    assert info.value.detail


def test_worker_dialling_out_is_sec013() -> None:
    """Run the worker body in this process with a parser that dials out: the guard and mapping are the shared ones."""
    sent: list[bytes] = []

    class Pipe:
        def send_bytes(self, data: bytes) -> None:
            sent.append(data)

        def close(self) -> None:
            pass

    def dial(self: Graph, *args: object, **kwargs: object) -> None:
        import socket  # noqa: PLC0415

        socket.create_connection(("127.0.0.1", 9))

    with mock.patch.object(Graph, "parse", dial):
        loader._worker_main(Pipe(), loader._ParseJob(b"x", "turtle", "file:///x.ttl", "x.ttl", 10))
    assert sent[0] == b"ready"
    assert json.loads(sent[1]) == {
        "rejected": ["SEC013", "x.ttl tried to use the network (connect ('127.0.0.1', 9)); the network is disabled"]
    }


def test_worker_always_answers_even_on_unexpected_errors() -> None:
    sent: list[bytes] = []

    class Pipe:
        def send_bytes(self, data: bytes) -> None:
            sent.append(data)

        def close(self) -> None:
            pass

    with mock.patch.object(loader, "_parse_bytes", side_effect=KeyboardInterrupt()):
        loader._worker_main(Pipe(), loader._ParseJob(b"x", "turtle", "file:///x.ttl", "x.ttl", 10))
    assert json.loads(sent[1]) == {"parse_failure": ["KeyboardInterrupt", ""]}


# --- worker lifecycle: hangs, deaths, orphans --------------------------------------------------------


def hang_worker(connection: Any, *args: Any) -> None:
    """Stand-in for an endless parse: announce readiness, then never answer."""
    connection.send_bytes(b"ready")
    time.sleep(600)


def die_after_ready(connection: Any, *args: Any) -> None:
    connection.send_bytes(b"ready")
    os._exit(3)


def die_before_ready(connection: Any, *args: Any) -> None:
    os._exit(1)


def silent_before_ready(connection: Any, *args: Any) -> None:
    time.sleep(600)


@pytest.fixture
def started_pids(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[int]]:
    """Record the pid of every worker the loader starts, to check afterwards that none survives."""
    pids: list[int] = []
    real_stop = loader._stop

    def recording_stop(process: Any) -> None:
        pids.append(process.pid)
        real_stop(process)

    monkeypatch.setattr(loader, "_stop", recording_stop)
    yield pids


def pid_exists(pid: int) -> bool:
    if sys.platform == "win32":  # pragma: no cover - os.kill(pid, 0) means CTRL_C_EVENT there
        return any(child.pid == pid for child in multiprocessing.active_children())
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_hanging_worker_is_killed_at_the_budget_and_leaves_no_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, started_pids: list[int]
) -> None:
    monkeypatch.setattr(loader, "_worker_main", hang_worker)
    started = time.monotonic()
    with pytest.raises(InputRejected) as info:
        load(tmp_path, "a.ttl", TTL, Policy(max_parse_seconds=0.3))
    assert info.value.rule_id == "SEC003"
    assert info.value.message == "a.ttl was not parsed within the time budget of 0.3 seconds (max_parse_seconds)"
    assert time.monotonic() - started < 60
    (pid,) = started_pids
    assert not pid_exists(pid)
    assert multiprocessing.active_children() == []


def test_worker_that_dies_without_a_result_is_a_parse_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, started_pids: list[int]
) -> None:
    monkeypatch.setattr(loader, "_worker_main", die_after_ready)
    with pytest.raises(ParseFailure) as info:
        load(tmp_path, "a.ttl", TTL, Policy(max_parse_seconds=GENEROUS))
    assert (info.value.cause_type, info.value.detail) == (
        "WorkerError",
        "the parse worker exited without a result (exit code 3)",
    )
    assert not pid_exists(started_pids[0])


def test_worker_that_never_starts_is_a_parse_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(loader, "_worker_main", die_before_ready)
    with pytest.raises(ParseFailure) as info:
        load(tmp_path, "a.ttl", TTL, Policy(max_parse_seconds=GENEROUS))
    assert (info.value.cause_type, info.value.detail) == ("WorkerError", "the parse worker did not start")


def test_slow_worker_start_is_not_counted_against_the_budget_but_has_its_own_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, started_pids: list[int]
) -> None:
    monkeypatch.setattr(loader, "_worker_main", silent_before_ready)
    monkeypatch.setattr(loader, "WORKER_START_TIMEOUT", 0.3)
    with pytest.raises(ParseFailure, match="did not start"):
        load(tmp_path, "a.ttl", TTL, Policy(max_parse_seconds=GENEROUS))
    assert not pid_exists(started_pids[0])


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
    loader._stop(polite)
    assert polite.calls == ["terminate", "join(2.0)", "join(None)", "close"]
    stubborn = FakeProcess(survives_terminate=True)
    loader._stop(stubborn)
    assert stubborn.calls == ["terminate", "join(2.0)", "kill", "join(None)", "close"]
    gone = FakeProcess(survives_terminate=False)
    gone.alive = False
    loader._stop(gone)
    assert gone.calls == ["join(None)", "close"]


def test_relative_input_path_is_a_parse_failure_with_and_without_a_budget(tmp_path: Path) -> None:
    (tmp_path / "a.ttl").write_text(TTL, encoding="utf-8")
    item = InputFile(Path("a.ttl"), "a.ttl", "a.ttl")
    for policy in (Policy(), Policy(max_parse_seconds=GENEROUS)):
        with contextlib.chdir(tmp_path), pytest.raises(ParseFailure) as info:
            load_graph(item, policy, tmp_path)
        assert info.value.cause_type == "ValueError"
