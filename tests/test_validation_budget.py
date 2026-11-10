"""SHACL validation under a time budget (``max_validation_seconds`` / ``--max-validation-seconds``).

The regression is the TODO reproduction: a ``sh:sparql`` constraint joining four triple patterns on a few hundred
triples runs for minutes; with a budget the run ends at it, the report is written, SHACL001 is ``failed`` and the
exit code is 2, as for a ROBOT timeout.  Under a budget the findings, failures and reports are the in-process ones.
"""

# ruff: noqa: PLR2004, SLF001

from __future__ import annotations

import json
import math
import multiprocessing
import subprocess
import sys
import time
from dataclasses import fields
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis_strategies import budget, literals
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import RDF, XSD

from ontolint import engine, worker
from ontolint.adapters import shacl
from ontolint.adapters.shacl import ValidationTimeout, bounded_shacl_issues, shacl_issues
from ontolint.cli import build_parser, main
from ontolint.models import ExecutionStatus, Finding, plain_evidence
from ontolint.policy import Policy

GENEROUS = 120.0
FAILED = 2

PREFIXES = "@prefix sh: <http://www.w3.org/ns/shacl#> .\n@prefix ex: <http://example.org/> .\n"
SLOW_SHAPES = PREFIXES + (
    "ex:S a sh:NodeShape ; sh:targetClass ex:Thing ;\n"
    '  sh:sparql [ a sh:SPARQLConstraint ; sh:message "slow" ;\n'
    '    sh:select "SELECT $this WHERE { $this ?p ?o . ?a ?b ?c . ?d ?e ?f . ?g ?h ?i . FILTER(false) }" ] .\n'
)
SLOW_DATA = (
    "@prefix ex: <http://example.org/> .\n@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\nex:o a owl:Ontology .\n"
    + "".join(f'ex:i{i} a ex:Thing ; ex:p ex:i{i + 1} ; rdfs:label "i{i}"@en .\n' for i in range(100))
)


def timeout_detail(seconds: str) -> str:
    return (
        f"ValidationTimeout: SHACL validation did not finish within the time budget of {seconds} seconds"
        " (max_validation_seconds)"
    )


@pytest.fixture
def slow(tmp_path: Path) -> Path:
    (tmp_path / "data.ttl").write_text(SLOW_DATA, encoding="utf-8")
    (tmp_path / "shapes.ttl").write_text(SLOW_SHAPES, encoding="utf-8")
    return tmp_path


def _executions(report: dict[str, Any]) -> list[tuple[str, str, str | None]]:
    return [
        (file["path"], execution["status"], execution.get("detail"))
        for file in report["files"]
        for execution in file["executions"]
        if execution["rule"] == "SHACL001"
    ]


# --- the reproduction ---------------------------------------------------------------------------------------------


def test_the_reproduction_ends_at_its_budget_with_a_failed_execution_and_exit_2(slow: Path) -> None:
    """Run in a subprocess: without the budget this run does not end, and the subprocess timeout says so."""
    argv = ["data.ttl", "--shapes", "shapes.ttl", "--select", "SHACL001", "--format", "json"]
    argv += ["--max-parse-seconds", "2", "--max-validation-seconds", "0.5"]
    started = time.monotonic()
    done = subprocess.run(  # noqa: S603 -- this interpreter, fixed arguments
        [sys.executable, "-c", "import sys; from ontolint.cli import main; sys.exit(main(sys.argv[1:]))", *argv],
        cwd=slow,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert time.monotonic() - started < 60
    assert done.returncode == FAILED, done.stderr
    report = json.loads(done.stdout)
    assert _executions(report) == [("data.ttl", "failed", timeout_detail("0.5"))]
    assert report["findings"] == []
    assert f"TOOL001: rule SHACL001 failed for data.ttl: {timeout_detail('0.5')}" in done.stderr


def test_a_timeout_leaves_no_worker_and_is_a_failed_sarif_notification(
    slow: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = [str(slow / "data.ttl"), "--shapes", str(slow / "shapes.ttl"), "--select", "SHACL001"]
    assert main([*argv, "--format", "sarif", "--max-validation-seconds", "0.3"]) == FAILED
    assert multiprocessing.active_children() == []
    invocation = json.loads(capsys.readouterr().out)["runs"][0]["invocations"][0]
    assert invocation["executionSuccessful"] is False
    (note,) = [
        n for n in invocation["toolExecutionNotifications"] if n.get("associatedRule", {}).get("id") == "SHACL001"
    ]
    assert note["level"] == "error"
    assert note["message"]["text"] == f"Rule SHACL001 failed: {timeout_detail('0.3')}"


def test_each_file_gets_its_own_budget_and_its_own_tool001_line(slow: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (slow / "other.ttl").write_text(SLOW_DATA, encoding="utf-8")
    report_path = slow / "report.json"
    argv = [str(slow / "data.ttl"), str(slow / "other.ttl"), "--shapes", str(slow / "shapes.ttl")]
    argv += ["--select", "SHACL001", "--format", "json", "--output", str(report_path)]
    assert main([*argv, "--max-validation-seconds", "0.3"]) == FAILED
    err = capsys.readouterr().err
    assert err.count("TOOL001: rule SHACL001 failed for ") == 2
    statuses = [(status, detail) for _path, status, detail in _executions(json.loads(report_path.read_text()))]
    assert statuses == [("failed", timeout_detail("0.3"))] * 2


def test_shapes_from_a_prof_profile_are_bounded_too(slow: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (slow / ".git").mkdir()
    (slow / "validator.ttl").write_text(SLOW_SHAPES, encoding="utf-8")
    (slow / "profile.ttl").write_text(
        "@prefix prof: <http://www.w3.org/ns/dx/prof/> . @prefix role: <http://www.w3.org/ns/dx/prof/role/> .\n"
        "<https://example.test/profile> a prof:Profile ; prof:hasResource [ a prof:ResourceDescriptor ;\n"
        "  prof:hasArtifact <https://example.test/profile/validator> ; prof:hasRole role:validator ] .\n",
        encoding="utf-8",
    )
    argv = [str(slow / "data.ttl"), "--shapes-from-profile", str(slow / "profile.ttl"), "--select", "SHACL001"]
    assert main([*argv, "--format", "json", "--max-validation-seconds", "0.3"]) == FAILED
    assert [status for _path, status, _detail in _executions(json.loads(capsys.readouterr().out))] == ["failed"]


# --- the same results with and without a budget -------------------------------------------------------------------

SH = "@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <https://example.test/> .\n"
CASES = {
    "severities and blank nodes": (
        "@prefix ex: <https://example.test/> . ex:a a ex:K . [] a ex:K .",
        SH + "ex:S a sh:NodeShape ; sh:targetClass ex:K ;\n"
        "  sh:property [ sh:path ex:violation ; sh:minCount 1 ] ;\n"
        "  sh:property [ sh:path ex:warning ; sh:minCount 1 ; sh:severity sh:Warning ] ;\n"
        "  sh:property [ sh:path ex:info ; sh:minCount 1 ; sh:severity sh:Info ] ;\n"
        "  sh:property [ sh:path ex:custom ; sh:minCount 1 ; sh:severity ex:Blocker ] .\n",
    ),
    "ill-typed literal": (
        "@prefix ex: <https://example.test/> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
        'ex:a a ex:K ; ex:n "abc"^^xsd:integer, "1.5", "007"^^xsd:integer .',
        SH + "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
        "ex:S a sh:NodeShape ; sh:targetClass ex:K ; sh:property [ sh:path ex:n ; sh:datatype xsd:integer ] .\n",
    ),
    "rebound default prefix": (
        "@prefix schema: <https://example.test/s#> . schema:a a schema:K ; schema:p schema:b .",
        "@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix schema: <https://example.test/s#> .\n"
        "schema:S a sh:NodeShape ; sh:targetClass schema:K ; sh:property [ sh:path schema:p ; sh:class schema:C ] .\n",
    ),
    "non-ASCII literal and sh:node detail": (
        '@prefix ex: <https://example.test/> . ex:a a ex:K ; ex:addr [ ex:city "Zürich 日本"@de ] .',
        SH + "ex:S a sh:NodeShape ; sh:targetClass ex:K ; sh:property [ sh:path ex:addr ; sh:node ex:Addr ] .\n"
        "ex:Addr a sh:NodeShape ; sh:property [ sh:path ex:city ; sh:maxLength 3 ] .\n",
    ),
    "complex path": (
        "@prefix ex: <https://example.test/> . ex:a a ex:K . ex:b ex:p ex:a .",
        SH + "ex:S a sh:NodeShape ; sh:targetClass ex:K ;\n"
        "  sh:property [ sh:path ( [ sh:inversePath ex:p ] [ sh:zeroOrMorePath ex:q ] ) ; sh:minCount 2 ] .\n",
    ),
    "sparql constraint": (
        "@prefix ex: <https://example.test/> . ex:a a ex:K ; ex:p ex:a .",
        SH + "ex:S a sh:NodeShape ; sh:targetClass ex:K ;\n"
        '  sh:sparql [ sh:message "loops on {$this}" ; sh:select "SELECT $this WHERE { $this ex:p $this }" ;\n'
        '    sh:prefixes [ sh:declare [ sh:prefix "ex" ; sh:namespace "https://example.test/"^^'
        "<http://www.w3.org/2001/XMLSchema#anyURI> ] ] ] .\n",
    ),
}


def _graph(text: str) -> Graph:
    return Graph().parse(data=text, format="turtle")


def full(findings: list[Finding]) -> list[tuple[Any, ...]]:
    """Every field of each finding, the ones identity ignores included."""
    return [
        (f, f.details, f.related, f.subject, None if f.evidence is None else plain_evidence(f.evidence))
        for f in findings
    ]


@pytest.mark.parametrize("case", sorted(CASES))
def test_findings_are_identical_in_the_worker(case: str) -> None:
    data, shapes = CASES[case]
    in_process = shacl_issues(_graph(data), _graph(shapes))
    assert in_process
    assert full(bounded_shacl_issues(_graph(data), _graph(shapes), GENEROUS)) == full(in_process)


def test_background_filtering_is_identical_in_the_worker(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    corpus = Path(__file__).parent / "fixtures" / "modular"
    argv = [str(corpus / "examples" / "invalid.ttl"), "--shapes", str(corpus / "shapes.ttl"), "--follow-imports"]
    argv += ["--select", "SHACL001", "--format", "json"]
    outputs = []
    for extra in ([], ["--max-validation-seconds", "120"]):
        code = main([*argv, *extra])
        outputs.append((code, capsys.readouterr().out))
    assert outputs[0] == outputs[1]
    assert json.loads(outputs[0][1])["findings"]


@pytest.mark.parametrize("fmt", ["json", "sarif", "text"])
def test_reports_are_byte_identical_with_a_generous_budget(
    fmt: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data, shapes = CASES["severities and blank nodes"]
    (tmp_path / "data.ttl").write_text(data, encoding="utf-8")
    (tmp_path / "shapes.ttl").write_text(shapes, encoding="utf-8")
    argv = [str(tmp_path / "data.ttl"), "--shapes", str(tmp_path / "shapes.ttl"), "--format", fmt]
    plain = main(argv), capsys.readouterr()
    budgeted = main([*argv, "--max-validation-seconds", "120"]), capsys.readouterr()
    assert plain == budgeted


def test_without_shapes_a_budget_changes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "data.ttl").write_text(SLOW_DATA, encoding="utf-8")
    argv = [str(tmp_path / "data.ttl"), "--format", "json"]
    plain = main(argv), capsys.readouterr()
    budgeted = main([*argv, "--max-validation-seconds", "1"]), capsys.readouterr()
    assert plain == budgeted
    assert ("data.ttl", "skipped", "no SHACL shapes graph was supplied") in [
        (Path(path).name, status, detail) for path, status, detail in _executions(json.loads(plain[1].out))
    ]


# --- failures read the same ---------------------------------------------------------------------------------------

CYCLIC_SHAPES = SH + "ex:S a sh:NodeShape ; sh:in _:l . _:l rdf:first 1 ; rdf:rest _:l ."


def test_a_refused_shapes_graph_fails_alike_and_starts_no_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    shapes = _graph("@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n" + CYCLIC_SHAPES)

    def no_worker(*args: object, **kwargs: object) -> dict[str, Any]:
        raise AssertionError("a refused shapes graph must not start a worker")

    monkeypatch.setattr(shacl, "run_bounded", no_worker)
    details = []
    for policy in (Policy(), Policy(max_validation_seconds=GENEROUS)):
        (execution,) = engine.execute(engine.build_context(Graph(), shapes, policy), ["SHACL001"]).executions
        details.append((execution.status, execution.detail))
    assert (
        details
        == [(ExecutionStatus.FAILED, "ShapesRejected: shapes graph contains a cyclic rdf:list (rdf:rest loops back)")]
        * 2
    )


def test_a_pyshacl_failure_diagnosed_in_the_worker_reads_as_in_process() -> None:
    """The odd data IRI of ``test_shacl_precheck``: pySHACL fails only when it must name the node."""
    data = Graph()
    node = BNode()
    data.add((node, RDF.type, URIRef("https://example.test/K")))
    data.add((node, URIRef("https://example.test/x}y"), Literal(1)))
    shapes = _graph(SH + "ex:S a sh:NodeShape ; sh:targetClass ex:K ; sh:property [ sh:path ex:p ; sh:minCount 1 ] .")
    details = []
    for policy in (Policy(), Policy(max_validation_seconds=GENEROUS)):
        (execution,) = engine.execute(engine.build_context(data, shapes, policy), ["SHACL001"]).executions
        details.append((execution.status, execution.detail))
    assert details[0] == details[1]
    assert details[0][0] is ExecutionStatus.FAILED
    assert (details[0][1] or "").startswith("ShapesRejected: data graph contains an IRI that cannot be serialised")


def test_without_a_budget_no_worker_is_started(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_worker(*args: object, **kwargs: object) -> dict[str, Any]:
        raise AssertionError("no budget, no worker")

    monkeypatch.setattr(shacl, "run_bounded", no_worker)
    data, shapes = CASES["severities and blank nodes"]
    result = engine.execute(engine.build_context(_graph(data), _graph(shapes), Policy()), ["SHACL001"])
    assert [e.status for e in result.executions] == [ExecutionStatus.EXECUTED]
    assert result.findings


@pytest.mark.parametrize(
    ("raised", "detail"),
    [
        (worker.WorkerGone("the validation worker did not start"), "WorkerError: the validation worker did not start"),
        (
            worker.WorkerGone("the validation worker exited without a result (exit code 3)"),
            "WorkerError: the validation worker exited without a result (exit code 3)",
        ),
        (worker.WorkerFailed("MemoryError", ""), "MemoryError: "),
        (worker.WorkerTimeout("the validation worker did not answer"), timeout_detail("0.25")),
    ],
)
def test_worker_outcomes_become_the_execution_detail(
    monkeypatch: pytest.MonkeyPatch, raised: Exception, detail: str
) -> None:
    def outcome(*args: object, **kwargs: object) -> dict[str, Any]:
        raise raised

    monkeypatch.setattr(shacl, "run_bounded", outcome)
    data, shapes = CASES["severities and blank nodes"]
    ctx = engine.build_context(_graph(data), _graph(shapes), Policy(max_validation_seconds=0.25))
    (execution,) = engine.execute(ctx, ["SHACL001"]).executions
    assert (execution.status, execution.detail) == (ExecutionStatus.FAILED, detail)


def test_a_timeout_is_a_timeout_error() -> None:
    assert issubclass(ValidationTimeout, TimeoutError)


def test_the_worker_task_validates_under_the_network_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """The task runs ``shacl_issues``, guard included; a dialling validation is a ``worker_error`` reply."""
    import socket  # noqa: PLC0415
    from importlib.machinery import ModuleSpec  # noqa: PLC0415
    from types import ModuleType  # noqa: PLC0415

    def validate(*_args: object, **_kwargs: object) -> tuple[bool, Graph, None]:
        socket.create_connection(("127.0.0.1", 9))
        return True, Graph(), None  # pragma: no cover - the guard raises first

    stub = ModuleType("pyshacl")
    stub.__spec__ = ModuleSpec("pyshacl", None)
    stub.validate = validate  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pyshacl", stub)

    class Pipe:
        def __init__(self) -> None:
            self.sent: list[bytes] = []

        def send_bytes(self, data: bytes) -> None:
            self.sent.append(data)

        def close(self) -> None:
            pass

    pipe = Pipe()
    task = shacl._ValidationJob(worker.encode_graph(Graph()), worker.encode_graph(Graph()))
    worker._worker_main(pipe, task)
    assert pipe.sent[0] == b"ready"
    assert json.loads(pipe.sent[1]) == {
        "worker_error": [
            "RuntimeError",
            "SHACL validation tried to use the network (connect ('127.0.0.1', 9)); the network is disabled",
        ]
    }


# --- the finding codec --------------------------------------------------------------------------------------------

_text = st.text(max_size=12)
_evidence = st.recursive(
    st.dictionaries(_text, st.one_of(_text, st.lists(_text, max_size=3).map(tuple)), max_size=3),
    lambda inner: st.dictionaries(_text, st.lists(inner, min_size=1, max_size=2).map(tuple), max_size=2),
    max_leaves=6,
)


_findings = st.builds(
    Finding,
    rule=_text,
    severity=st.sampled_from(("error", "warning", "info")),
    focus=_text,
    message=_text,
    suggestion=_text,
    confidence=st.sampled_from(("certain", "heuristic")),
    details=st.none() | _text,
    related=st.lists(_text, max_size=3).map(tuple),
    evidence=st.none() | _evidence,
    subject=st.lists(_text, max_size=3).map(tuple),
)


@budget(0.5)
@given(finding=_findings)
def test_every_finding_field_survives_the_codec(finding: Finding) -> None:
    (decoded,) = shacl._findings_from_json(json.loads(json.dumps(shacl._findings_to_json([finding]))))
    assert [getattr(decoded, f.name) for f in fields(Finding)] == [getattr(finding, f.name) for f in fields(Finding)]
    assert type(decoded.related) is tuple
    assert type(decoded.subject) is tuple


_SHAPES_FOR_PROPERTY = _graph(
    SH + "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
    "ex:S a sh:NodeShape ; sh:targetClass ex:K ;\n"
    "  sh:property [ sh:path ex:v ; sh:datatype xsd:integer ; sh:maxCount 1 ] ;\n"
    "  sh:property [ sh:path ex:link ; sh:class ex:K ] .\n"
)


@st.composite
def _data_graphs(draw: st.DrawFn) -> Graph:
    graph = Graph()
    nodes: list[URIRef | BNode] = [URIRef(f"https://example.test/n{i}") for i in range(draw(st.integers(1, 3)))]
    nodes += [BNode() for _ in range(draw(st.integers(0, 2)))]
    for node in nodes:
        graph.add((node, RDF.type, URIRef("https://example.test/K")))
        for value in draw(st.lists(literals(), max_size=2)):
            graph.add((node, URIRef("https://example.test/v"), value))
        if draw(st.booleans()):
            graph.add((node, URIRef("https://example.test/link"), draw(st.sampled_from(nodes))))
    if draw(st.booleans()):
        graph.add((nodes[0], URIRef("https://example.test/v"), Literal("x", datatype=XSD.integer)))
    return graph


@budget(0.1, floor=10)
@given(data=_data_graphs())
def test_the_worker_task_answers_with_the_in_process_findings(data: Graph) -> None:
    """No process: the task's ``run`` on the encoded graphs equals ``shacl_issues`` on the originals."""
    task = shacl._ValidationJob(worker.encode_graph(data), worker.encode_graph(_SHAPES_FOR_PROPERTY))
    decoded = shacl._findings_from_json(json.loads(task.run())["findings"])
    assert full(decoded) == full(shacl_issues(data, _SHAPES_FOR_PROPERTY))


# --- policy and CLI -----------------------------------------------------------------------------------------------


def test_the_budget_is_off_by_default() -> None:
    assert Policy().max_validation_seconds is None
    assert Policy.from_mapping({}).max_validation_seconds is None
    assert Policy.from_mapping({"max_validation_seconds": None}).max_validation_seconds is None


@pytest.mark.parametrize("value", [0.25, 3, 86400])
def test_valid_budgets_are_stored_as_float(value: float) -> None:
    policy = Policy.from_mapping({"max_validation_seconds": value})
    assert policy.max_validation_seconds == value
    assert type(policy.max_validation_seconds) is float
    assert policy.unknown_keys == ()


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (0, "max_validation_seconds must be positive"),
        (-1, "max_validation_seconds must be positive"),
        (86400.5, "max_validation_seconds must be at most 86400"),
        (math.nan, "max_validation_seconds must be a finite number"),
        (math.inf, "max_validation_seconds must be a finite number"),
        (True, "max_validation_seconds must be a finite number"),
        ("5", "max_validation_seconds must be a finite number"),
    ],
)
def test_invalid_budgets_are_refused_naming_the_key(value: Any, message: str) -> None:
    with pytest.raises(ValueError, match=f"^{message}$"):
        Policy.from_mapping({"max_validation_seconds": value})
    with pytest.raises(ValueError, match=f"^{message}$"):
        Policy(max_validation_seconds=value)


def test_the_parse_budget_messages_are_unchanged() -> None:
    with pytest.raises(ValueError, match="^max_parse_seconds must be positive$"):
        Policy(max_parse_seconds=0)
    with pytest.raises(ValueError, match="^max_parse_seconds must be at most 86400$"):
        Policy(max_parse_seconds=86401)


def test_the_cli_option_defaults_to_none_and_parses_floats() -> None:
    assert build_parser().parse_args(["x.ttl"]).max_validation_seconds is None
    assert build_parser().parse_args(["x.ttl", "--max-validation-seconds", "0.25"]).max_validation_seconds == 0.25


@pytest.mark.parametrize("text", ["0", "-1", "nan", "inf", "x", "86401"])
def test_the_cli_option_refuses_bad_values(text: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["x.ttl", "--max-validation-seconds", text])
    assert "--max-validation-seconds" in capsys.readouterr().err


def test_the_cli_option_overrides_the_policy_file(slow: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = slow / "policy.json"
    config.write_text(json.dumps({"max_validation_seconds": 0.3}), encoding="utf-8")
    argv = [str(slow / "data.ttl"), "--shapes", str(slow / "shapes.ttl"), "--select", "SHACL001", "--format", "json"]
    assert main([*argv, "--config", str(config)]) == FAILED
    assert [detail for _p, _s, detail in _executions(json.loads(capsys.readouterr().out))] == [timeout_detail("0.3")]
    assert main([*argv, "--config", str(config), "--max-validation-seconds", "0.4"]) == FAILED
    assert [detail for _p, _s, detail in _executions(json.loads(capsys.readouterr().out))] == [timeout_detail("0.4")]
