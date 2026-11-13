"""Fuzz harness tests: regression replay, a fixed smoke run, and unit tests of the mutators and the shrinker.

``regressions/*.bin`` are minimised former crashers whose bug is fixed: they must keep passing.
``regressions/known_bugs/*.bin`` are crashers whose bug is still open: they are asserted to *still fail* (strict
xfail), so fixing a bug turns its replay into an unexpected pass that forces moving the file to ``regressions/``.
Set ``ONTOLINT_FUZZ=1`` for the longer (about one minute per target) run.
"""

# ruff: noqa: PLR2004

from __future__ import annotations

import contextlib
import os
import socket
import sys
import time
from collections.abc import Generator
from pathlib import Path

import pytest
from fuzz import fuzzer

from ontolint import cli
from ontolint.reporting import MARKDOWN_MAX_BYTES, RunReport, render_markdown

pytestmark = pytest.mark.slow

ORIGINAL_CONNECT = socket.socket.connect
KNOWN_BAD_SEEDS: frozenset[str] = (
    frozenset()
)  # seeds that trigger a still-open bug (none: cyclic contexts are rejected)
SMOKE_SEED = 20240607
SMOKE_ITERATIONS = 150


def _files(directory: Path) -> list[Path]:
    return sorted(directory.glob("*.bin")) if directory.is_dir() else []


def _known_bug_params() -> list[object]:
    reason = "known open bug: when it is fixed, move the file from regressions/known_bugs/ to regressions/"
    return [
        pytest.param(path, id=path.name, marks=pytest.mark.xfail(strict=True, reason=reason))
        for path in _files(fuzzer.KNOWN_BUGS_DIR)
    ]


@pytest.fixture
def runner() -> Generator[fuzzer.Runner]:
    with fuzzer.Runner(case_seconds=5.0) as instance:
        yield instance


@pytest.fixture(scope="module")
def corpus() -> fuzzer.Corpus:
    return fuzzer.load_corpus()


# ------------------------------------------------------------------------------------ (a) regressions


@pytest.mark.parametrize("path", _files(fuzzer.REGRESSIONS_DIR), ids=lambda p: p.name)
def test_regression_replays_cleanly(path: Path) -> None:
    failure = fuzzer.replay(path, case_seconds=5.0)
    assert failure is None, (
        f"{path.name}: {failure.kind if failure else ''} (sig {failure.signature if failure else ''})"
    )


@pytest.mark.parametrize("path", _known_bug_params())
def test_known_bug_still_fails(path: Path) -> None:
    assert fuzzer.replay(path, case_seconds=3.0) is None


def test_saved_case_names_are_replayable() -> None:
    for path in (*_files(fuzzer.REGRESSIONS_DIR), *_files(fuzzer.KNOWN_BUGS_DIR)):
        case = fuzzer.parse_case_path(path)
        assert case.target in fuzzer.TARGETS
        assert len(case.data) <= fuzzer.MAX_INPUT


# ---------------------------------------------------------------------------------------- (b) smoke


@pytest.mark.parametrize("target", fuzzer.TARGETS)
def test_smoke_fuzz_finds_no_new_crash(target: str, runner: fuzzer.Runner, corpus: fuzzer.Corpus) -> None:
    known = fuzzer.known_signatures(fuzzer.KNOWN_BUGS_DIR)
    stats, crashes = fuzzer.fuzz_target(
        target,
        seed=SMOKE_SEED,
        seconds=None,
        iterations=SMOKE_ITERATIONS,
        runner=runner,
        known=known,
        corpus=corpus,
        shrink_seconds=5.0,
    )
    assert stats.executions == SMOKE_ITERATIONS
    assert [(c.failure.kind, c.failure.signature, c.minimised.data[:200]) for c in crashes] == []


def test_every_seed_passes_every_target(runner: fuzzer.Runner, corpus: fuzzer.Corpus) -> None:
    for seed in corpus.rdf:
        if seed.name in KNOWN_BAD_SEEDS:
            continue
        for target, opt in (("loader", "-"), ("lint", "ont"), ("cli", "7")):
            case = fuzzer.Case(target, seed.ext, opt, seed.data)
            assert runner.run(case).failure is None, f"{seed.name} / {target}"
    for seed in corpus.config:
        assert runner.run(fuzzer.Case("config", ".json", "-", seed.data)).failure is None, seed.name


def test_corpus_covers_every_format(corpus: fuzzer.Corpus) -> None:
    extensions = {seed.ext for seed in corpus.rdf}
    assert {".ttl", ".nt", ".rdf", ".xml", ".jsonld", ".n3"} <= extensions
    assert len(corpus.config) >= 3
    names = " ".join(seed.name for seed in corpus.rdf)
    assert "entity" in names
    assert "remote_context" in names
    assert "shapes" in names
    assert all(0 < len(seed.data) <= fuzzer.MAX_INPUT for seed in (*corpus.rdf, *corpus.config))


def test_generated_cli_options_are_accepted_by_the_real_parser(runner: fuzzer.Runner) -> None:
    parser = cli.build_parser()
    mutant = runner.work.write("input.ttl", b"")
    seen: set[str] = set()
    for optseed in range(400):
        argv = fuzzer.build_cli_argv(optseed, runner.work, mutant)
        assert argv == fuzzer.build_cli_argv(optseed, runner.work, mutant)
        parser.parse_args(argv)
        seen.update(a for a in argv if a.startswith("--"))
    assert {"--select", "--ignore", "--profile", "--format", "--fail-on", "--base", "--language", "--shapes"} <= seen
    assert {"--depth-limit", "--max-triples", "--max-input-bytes", "--baseline", "--output"} <= seen


# The argv each saved CLI case replays, as 0.13 built it from its optseed (``WORK`` is the work directory): a
# change to the option builders that moved a draw would replay a saved crasher with other options, and so would
# no longer test what it was saved for.
SAVED_CLI_ARGV = {
    1954055657: [
        "--profile", "obo", "--base", "x" * 500, "--inheritance-limit", "9223372036854775808",
        "--output", "WORK/report.out", "WORK/input.ttl",
    ],
    2044887847: [
        "--profile", "ci", "--language", "FR", "--soup-limit", "-1", "--max-triples", "1",
        "--shapes", "WORK/input.ttl", "WORK/input.ttl",
    ],
    71506165: [
        "--ignore", "LEX011", "--format", "sarif", "--fail-on", "warning", "--inheritance-limit", "2",
        "--shapes", "WORK/shapes.ttl", "--baseline", "WORK/baseline.json", "WORK/input.ttl",
    ],
    602926872: [
        "--format", "text", "--fail-on", "never", "--base", "", "--depth-limit", "1000000000000000000000000000000",
        "--shapes", "WORK/input.ttl", "WORK/input.ttl",
    ],
    7: [
        "--select", "CLS014,DATA002,GOV004", "--ignore", "OBO", "--profile", "ci", "--format", "text",
        "--fail-on", "never", "--base", "http://example.org/", "--inheritance-limit",
        "1000000000000000000000000000000", "--max-triples", "5", "--shapes", "WORK/input.ttl",
        "--config", "WORK/config.json", "WORK/input.ttl",
    ],
}  # fmt: skip


def test_saved_cli_cases_keep_their_argv(runner: fuzzer.Runner) -> None:
    cases = [fuzzer.parse_case_path(path) for path in (*_files(fuzzer.REGRESSIONS_DIR), *_files(fuzzer.KNOWN_BUGS_DIR))]
    # Every saved CLI case is pinned, and so is the optseed test_every_seed_passes_every_target runs.
    assert {case.opt for case in cases if case.target == "cli"} | {"7"} <= {str(optseed) for optseed in SAVED_CLI_ARGV}
    mutant = runner.work.write("input.ttl", b"")
    work = f"{runner.work.root}{os.sep}"
    for optseed, expected in SAVED_CLI_ARGV.items():
        argv = fuzzer.build_cli_argv(optseed, runner.work, mutant)
        assert argv == [arg.replace("WORK/", work) for arg in expected], optseed


def test_smoke_run_is_deterministic(corpus: fuzzer.Corpus) -> None:
    def labels() -> dict[str, int]:
        with fuzzer.Runner(case_seconds=5.0) as run:
            stats, _ = fuzzer.fuzz_target(
                "loader", seed=5, seconds=None, iterations=60, runner=run, corpus=corpus, shrink_seconds=1.0
            )
        return dict(stats.labels)

    assert labels() == labels()


# -------------------------------------------------------------------------------- (c) mutators, shrinker


def test_mutator_is_deterministic_under_a_seed() -> None:
    seeds = [b"@prefix e: <http://e/> .\ne:a e:p 1 .\n", b'{"@context": {}}']
    a = fuzzer.Mutator(7, seeds)
    b = fuzzer.Mutator(7, seeds)
    c = fuzzer.Mutator(8, seeds)
    out_a = [a.mutate(seeds[0]) for _ in range(50)]
    assert out_a == [b.mutate(seeds[0]) for _ in range(50)]
    assert out_a != [c.mutate(seeds[0]) for _ in range(50)]
    gentle = [fuzzer.Mutator(3, seeds).mutate(seeds[0], gentle=True) for _ in range(5)]
    assert gentle == [fuzzer.Mutator(3, seeds).mutate(seeds[0], gentle=True) for _ in range(5)]


def test_mutator_respects_the_size_cap() -> None:
    cap = 4096
    mutator = fuzzer.Mutator(1, [b"a" * 100], max_size=cap)
    start = b"x" * cap
    for _ in range(300):
        assert len(mutator.mutate(start)) <= cap
        assert len(mutator.mutate(b"")) <= cap
    default = fuzzer.Mutator(2, [b"<a> <b> <c> .\n"])
    assert max(len(default.mutate(b"<a> <b> <c> .\n" * 5000)) for _ in range(60)) <= fuzzer.MAX_INPUT


def test_every_operator_returns_bytes_within_the_cap() -> None:
    mutator = fuzzer.Mutator(11, [b'<http://e/a> <http://e/p> "x" .\n'], max_size=2048)
    for data in (b"", b"a", b"<http://e/a> <http://e/p> <http://e/b> .\n" * 3, b"\xff\x00" * 40):
        for operator in (*mutator.operators, *mutator.gentle_operators):
            for _ in range(5):
                out = operator(data)
                assert isinstance(out, bytes)
                assert len(out) <= mutator.max_size * 2  # the cap is applied by mutate(); operators stay bounded


def test_operators_do_what_they_claim() -> None:
    m = fuzzer.Mutator(5, [b"<a> <b> <c> .\n"], max_size=1 << 16)
    assert len(m.token_insert(b"x" * 10)) > 10
    flipped = m.bit_flip(b"\x00" * 8)
    assert flipped != b"\x00" * 8 and len(flipped) == 8
    assert len(m.delete_chunk(b"abcdefgh")) < 8
    assert len(m.duplicate_chunk(b"abcdefgh")) > 8
    assert len(m.repeat_chunk(b"abc")) > 3
    cut = m.unterminate(b'<a> <b> "long literal" .')
    assert len(cut) < len(b'<a> <b> "long literal" .')
    assert m.term_swap(b"<a> <b>") in (b"<a> <b>", b"<b> <b>", b"<a> <a>")
    assert m.term_swap(b"nothing") == b"nothing"
    encodings = {m.reencode(b"<a> <b> <c> .") for _ in range(60)}
    assert any(e.startswith((b"\xff\xfe", b"\xfe\xff", b"\xef\xbb\xbf")) for e in encodings)
    assert any(b"\x00" in e for e in encodings)
    nested = m.deep_nest(b"")
    assert len(nested) >= 8
    assert any(len(m.long_literal(b"")) > 60 for _ in range(10))


def test_shrinker_reduces_a_toy_failure() -> None:
    data = b"aaaa" * 100 + b"X" + b"bbbb" * 50 + b"Y" + b"cccc" * 30

    def fails(candidate: bytes) -> bool:
        return b"X" in candidate and b"Y" in candidate and candidate.index(b"X") < candidate.index(b"Y")

    reduced = fuzzer.shrink(data, fails)
    assert reduced == b"XY"
    assert fuzzer.shrink(b"harmless", lambda _c: False) == b"harmless"
    assert fuzzer.shrink(b"", lambda _c: True) == b""


def test_shrinker_honours_its_budget() -> None:
    calls = 0

    def fails(_candidate: bytes) -> bool:
        nonlocal calls
        calls += 1
        return False

    fuzzer.shrink(b"z" * 5000, fails, max_runs=25)
    assert calls <= 25
    started = time.monotonic()

    def slow(_candidate: bytes) -> bool:
        time.sleep(0.01)
        return False

    fuzzer.shrink(b"z" * 5000, slow, seconds=0.2)
    assert time.monotonic() - started < 2


def test_minimise_keeps_the_failure_signature(runner: fuzzer.Runner, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(case: fuzzer.Case, work: fuzzer.Workdir) -> str:
        if b"BOOM" in case.data:
            raise KeyError("boom")
        return "ok"

    monkeypatch.setitem(fuzzer._RUNNERS, "loader", boom)
    case = fuzzer.Case("loader", ".ttl", "-", b"x" * 300 + b"BOOM" + b"y" * 300)
    failure = runner.run(case).failure
    assert failure is not None and failure.kind == "KeyError"
    assert fuzzer.minimise(runner, case, failure, seconds=10).data == b"BOOM"


# ------------------------------------------------------------------------ invariants are really checked


def test_unexpected_loader_exception_is_a_failure(runner: fuzzer.Runner, monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(*args: object, **kwargs: object) -> None:
        raise RecursionError("deep")

    monkeypatch.setattr(fuzzer, "load_graph", explode)
    outcome = runner.run(fuzzer.Case("loader", ".ttl", "-", b"<a> <b> <c> ."))
    assert outcome.failure is not None
    assert outcome.failure.kind == "RecursionError"
    assert outcome.failure.signature == runner.run(fuzzer.Case("loader", ".nt", "-", b"other")).failure.signature  # type: ignore[union-attr]


def test_documented_rejections_and_parse_errors_are_not_failures(runner: fuzzer.Runner) -> None:
    assert runner.run(fuzzer.Case("loader", ".ttl", "-", b"<a> <b> .")).failure is None
    assert (
        runner.run(fuzzer.Case("loader", ".rdf", "-", b'<!DOCTYPE x SYSTEM "http://127.0.0.1:9/">')).label
        == "rej:SEC010"
    )
    assert (
        runner.run(fuzzer.Case("loader", ".jsonld", "-", b'{"@context": "http://127.0.0.1:9/c"}')).label == "rej:SEC006"
    )
    assert runner.run(fuzzer.Case("loader", ".ttl", "b8", b"x" * 100)).label == "rej:SEC001"
    assert runner.run(fuzzer.Case("loader", ".ttl", "t2", b"<a> <b> <c>, <d>, <e>, <f> .")).label == "rej:SEC002"
    assert runner.run(fuzzer.Case("loader", ".ttl", "-", b"\x1f\x8bgzip")).label == "rej:SEC011"


def test_limits_that_are_ignored_are_detected(runner: fuzzer.Runner, monkeypatch: pytest.MonkeyPatch) -> None:
    from rdflib import Graph, Literal, URIRef  # noqa: PLC0415 -- only this test builds graphs

    def too_big(*args: object, **kwargs: object) -> Graph:
        g = Graph()
        for i in range(5):
            g.add((URIRef(f"http://e/{i}"), URIRef("http://e/p"), Literal(i)))
        return g

    monkeypatch.setattr(fuzzer, "load_graph", too_big)
    outcome = runner.run(fuzzer.Case("loader", ".ttl", "t2", b"<a> <b> <c> ."))
    assert outcome.failure is not None and outcome.failure.kind == "loader:triple-limit-ignored"
    outcome = runner.run(fuzzer.Case("loader", ".ttl", "b4", b"<a> <b> <c> ."))
    assert outcome.failure is not None and outcome.failure.kind == "loader:input-limit-ignored"


def test_network_use_outside_the_guard_is_a_failure(runner: fuzzer.Runner, monkeypatch: pytest.MonkeyPatch) -> None:
    def phone_home(case: fuzzer.Case, work: fuzzer.Workdir) -> str:
        with contextlib.suppress(OSError):
            socket.create_connection(("127.0.0.1", 9), timeout=0.1)
        return "ok"

    monkeypatch.setitem(fuzzer._RUNNERS, "loader", phone_home)
    outcome = runner.run(fuzzer.Case("loader", ".ttl", "-", b""))
    assert outcome.failure is not None and outcome.failure.kind == "network"


@pytest.mark.skipif(sys.platform == "win32", reason="the SIGALRM watchdog is POSIX only")
def test_watchdog_interrupts_a_hang(monkeypatch: pytest.MonkeyPatch) -> None:
    def spin(case: fuzzer.Case, work: fuzzer.Workdir) -> str:
        while True:
            with contextlib.suppress(Exception):  # the watchdog must not be swallowable by this
                sum(range(1000))

    monkeypatch.setitem(fuzzer._RUNNERS, "loader", spin)
    with fuzzer.Runner(case_seconds=0.3) as short:
        started = time.monotonic()
        outcome = short.run(fuzzer.Case("loader", ".ttl", "-", b""))
    assert outcome.failure is not None and outcome.failure.kind == "CaseTimeout"
    assert time.monotonic() - started < 5
    assert socket.socket.connect is ORIGINAL_CONNECT  # the socket patches were restored


def test_cli_contract_violations_are_detected(runner: fuzzer.Runner, monkeypatch: pytest.MonkeyPatch) -> None:
    case = fuzzer.Case("cli", ".ttl", "1", b"")
    monkeypatch.setattr(cli, "main", lambda argv=None: 7)
    outcome = runner.run(case)
    assert outcome.failure is not None and outcome.failure.kind == "cli:exit-code"

    def noisy(argv: object = None) -> int:
        print("Traceback (most recent call last):", file=sys.stderr)
        return 2

    monkeypatch.setattr(cli, "main", noisy)
    outcome = runner.run(case)
    assert outcome.failure is not None and outcome.failure.kind == "cli:traceback"


def test_cli_output_formats_are_validated(runner: fuzzer.Runner, monkeypatch: pytest.MonkeyPatch) -> None:
    work = runner.work

    def run_with(output: str, fmt: str = "sarif") -> str | None:
        monkeypatch.setattr(cli, "main", lambda argv=None: (print(output), 0)[1])
        try:
            fuzzer.check_cli(["--format", fmt, "x.ttl"], work)
        except fuzzer.InvariantViolation as exc:
            return exc.kind
        return None

    assert run_with("not json") == "cli:invalid-sarif"
    assert run_with('{"version": "2.1.0"}') == "cli:invalid-sarif"
    assert run_with('{"version": "2.1.0", "runs": []}') is None
    summary = render_markdown(RunReport(()), 0)
    assert run_with(summary, "markdown") is None
    assert run_with("not a summary", "markdown") == "cli:invalid-markdown"
    assert run_with(summary + "x" * MARKDOWN_MAX_BYTES, "markdown") == "cli:invalid-markdown"
    assert run_with(f"{summary}\n\nhttps://alice:Zq7@example.test/x", "markdown") == "cli:invalid-markdown"
    assert run_with("not json", "markdown") == "cli:invalid-markdown"  # a summary is not parsed as JSON
    assert run_with(summary, "text") is None


def test_config_target_accepts_only_value_errors(runner: fuzzer.Runner) -> None:
    for payload in (
        b"{",
        b"[]",
        b"null",
        b'{"depth_limit": "x"}',
        b'{"severity_overrides": {"A": "fatal"}}',
        b"[" * 5000,
    ):
        assert runner.run(fuzzer.Case("config", ".json", "-", payload)).failure is None, payload[:30]


def test_failure_signatures_depend_on_site_not_message() -> None:
    def raise_it(message: str) -> BaseException:
        try:
            raise KeyError(message)
        except KeyError as exc:
            return exc

    a = fuzzer.failure_from_exception("loader", raise_it("one"))
    b = fuzzer.failure_from_exception("loader", raise_it("two"))
    c = fuzzer.failure_from_exception("cli", raise_it("one"))
    assert a.signature == b.signature != c.signature
    assert a.kind == "KeyError"


def test_save_crash_and_replay_roundtrip(
    tmp_path: Path, runner: fuzzer.Runner, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(case: fuzzer.Case, work: fuzzer.Workdir) -> str:
        raise ValueError("boom")

    monkeypatch.setitem(fuzzer._RUNNERS, "loader", boom)
    case = fuzzer.Case("loader", ".jsonld", "t3", b"payload")
    failure = runner.run(case).failure
    assert failure is not None
    saved = fuzzer.save_crash(fuzzer.Crash(case, case, failure), tmp_path)
    assert saved.name == f"loader__jsonld__t3__{failure.signature}.bin"
    assert fuzzer.parse_case_path(saved) == case
    assert fuzzer.signature_of_path(saved) == failure.signature
    report = (tmp_path / "reports.txt").read_text(encoding="utf-8")
    assert f"sig={failure.signature}" in report and "target=loader" in report and report.count("\n") == 1
    assert fuzzer.replay(saved) is not None
    assert fuzzer.known_signatures(tmp_path) == {failure.signature}
    with pytest.raises(ValueError, match="not named"):
        fuzzer.parse_case_path(tmp_path / "bogus.bin")


def test_cli_entry_point(tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert fuzzer.main(["--iterations", "10", "--target", "config", "--seed", "3", "--out", str(out)]) == 0
    assert not out.exists() or not list(out.glob("*.bin"))


# ------------------------------------------------------------------------------------- longer, opt-in


@pytest.mark.skipif(os.environ.get("ONTOLINT_FUZZ") != "1", reason="set ONTOLINT_FUZZ=1 for the ~60 s per target run")
@pytest.mark.parametrize("target", fuzzer.TARGETS)
def test_long_fuzz(target: str, tmp_path: Path, runner: fuzzer.Runner) -> None:
    known = fuzzer.known_signatures(fuzzer.KNOWN_BUGS_DIR)
    _, crashes = fuzzer.fuzz_target(
        target,
        seed=int(os.environ.get("ONTOLINT_FUZZ_SEED", "1")),
        seconds=60.0,
        iterations=None,
        runner=runner,
        known=known,
        out=tmp_path,
        shrink_seconds=30.0,
    )
    assert [(c.failure.kind, c.failure.signature) for c in crashes] == []
