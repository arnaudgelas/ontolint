"""Behavioural pins for the CLI, engine, linter, reporting, builtin-registry and ROBOT adapter modules."""

from __future__ import annotations

import argparse
import dataclasses
import json
import subprocess
import types
from pathlib import Path
from typing import Any

import pytest
from rdflib import URIRef

from ontolint import cli, engine
from ontolint.adapters import robot as robot_adapter
from ontolint.linter import Linter
from ontolint.models import ExecutionStatus, Finding, RuleBackend, RuleExecution, RuleScope, RuleSpec, Severity
from ontolint.paths import InputFile
from ontolint.policy import Policy
from ontolint.reporting import FileReport, Location, RunReport, exit_code, fingerprint, identity, render_report
from ontolint.rules import builtin

ROBOT_REPORT = (
    "OWL 2 DL Profile Report: Ontology and imports closure NOT in profile. The following violations are present:\n"
    "Use of undeclared class: <http://e/C> [SubClassOf(<http://e/A> <http://e/C>)]"
)


def _finding(severity: str = "warning", rule: str = "ONT001") -> Finding:
    return Finding(rule, severity, "focus", "message", "fix")


def _spec(rule_id: str = "X001", backend: RuleBackend = RuleBackend.RDFLIB, module: str = "mod") -> RuleSpec:
    return RuleSpec(rule_id, "fam", "title", Severity.WARNING, "sugg", "cat", backend, RuleScope.ONTOLOGY, module)


# --- frozen dataclasses -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("instance", "field"),
    [
        (engine.RobotRequest(Path("a.ttl"), "EL"), "profile"),
        (Location(1), "line"),
        (FileReport("a", "a", ()), "path"),
        (RunReport(()), "files"),
        (cli.RunPlan(None, None, {}, None, None), "overrides"),  # type: ignore[arg-type]
    ],
)
def test_value_objects_are_frozen(instance: Any, field: str) -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(instance, field, "changed")


# --- cli ----------------------------------------------------------------------------------------


def _baseline_args(tmp_path: Path) -> argparse.Namespace:
    return argparse.Namespace(write_baseline=str(tmp_path / "b.json"), baseline=None)


def test_single_file_baseline_uses_path_free_fingerprints(tmp_path: Path) -> None:
    finding = _finding()
    report = FileReport("a.ttl", "a.ttl", (finding,))
    cli._apply_baselines([report], _baseline_args(tmp_path))  # noqa: SLF001
    written = json.loads((tmp_path / "b.json").read_text(encoding="utf-8"))
    assert written == {
        "version": 2,
        "files": ["a.ttl"],
        "fingerprints": [fingerprint(finding)],
        "identities": {"a.ttl": {identity(finding): fingerprint(finding)}},
    }


def test_two_file_baseline_uses_path_scoped_fingerprints(tmp_path: Path) -> None:
    finding = _finding()
    reports = [FileReport("a.ttl", "a.ttl", (finding,)), FileReport("b.ttl", "b.ttl", (finding,))]
    cli._apply_baselines(reports, _baseline_args(tmp_path))  # noqa: SLF001
    written = json.loads((tmp_path / "b.json").read_text(encoding="utf-8"))
    assert written == {
        "version": 2,
        "files": ["a.ttl", "b.ttl"],
        "fingerprints": sorted([fingerprint(finding, "a.ttl"), fingerprint(finding, "b.ttl")]),
        "identities": {
            "a.ttl": {identity(finding): fingerprint(finding, "a.ttl")},
            "b.ttl": {identity(finding): fingerprint(finding, "b.ttl")},
        },
    }


def test_a_baseline_reports_the_findings_it_accepted_per_file(tmp_path: Path) -> None:
    finding, other = _finding(), _finding("error", "ONT002")
    reports = [FileReport("a.ttl", "a.ttl", (finding,)), FileReport("b.ttl", "b.ttl", (other,))]
    assert cli._apply_baselines(reports, _baseline_args(tmp_path)) == (reports, None, None)  # noqa: SLF001
    cli._apply_baselines([reports[0], FileReport("b.ttl", "b.ttl", ())], _baseline_args(tmp_path))  # noqa: SLF001
    applying = argparse.Namespace(write_baseline=None, baseline=str(tmp_path / "b.json"))
    files, stale, baselined = cli._apply_baselines(reports, applying)  # noqa: SLF001
    assert [f.findings for f in files] == [(), (other,)]
    assert stale == ()
    assert baselined == ((finding,), ())


def test_the_run_report_carries_the_findings_the_baseline_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.ttl").write_text("<https://example.test/a> a <http://www.w3.org/2002/07/owl#Class> .\n")
    reports: list[RunReport] = []
    monkeypatch.setattr(cli, "render_report", lambda report, *_args: reports.append(report) or "")
    cli.main(["a.ttl", "--write-baseline", "b.json"])
    cli.main(["a.ttl", "--baseline", "b.json"])
    capsys.readouterr()
    without, applied = reports
    assert without.baselined is None
    assert applied.baselined is not None
    assert len(applied.baselined) == 1
    assert applied.baselined[0] == without.files[0].findings != ()
    assert applied.files[0].findings == ()


def _bad_ttl(tmp_path: Path, name: str) -> InputFile:
    path = tmp_path / name
    path.write_text("this is not turtle", encoding="utf-8")
    return InputFile(path, name, name)


def test_parse_error_names_file_only_for_multiple_inputs(tmp_path: Path) -> None:
    one = _bad_ttl(tmp_path, "one.ttl")
    two = _bad_ttl(tmp_path, "two.ttl")
    _, single = cli._parse_inputs([one])  # noqa: SLF001
    assert single[0].startswith("INPUT001: RDF input parsing failed: ")
    _, pair = cli._parse_inputs([one, two])  # noqa: SLF001
    assert pair[0].startswith("INPUT001: RDF input parsing failed for one.ttl: ")
    assert pair[1].startswith("INPUT001: RDF input parsing failed for two.ttl: ")


def test_lint_requires_one_graph_per_input(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ttl = tmp_path / "a.ttl"
    ttl.write_text("@prefix ex: <http://e/> . ex:a ex:b ex:c .", encoding="utf-8")
    monkeypatch.setattr(cli, "_parse_inputs", lambda inputs, imports=None: ([], []))
    args = cli.build_parser().parse_args([str(ttl)])
    with pytest.raises(ValueError, match="argument"):
        cli._lint(args, ["configuration"])  # noqa: SLF001


# --- engine -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("backend", "expected"),
    [(RuleBackend.PYSHACL, "shacl"), (RuleBackend.ROBOT_DOCKER, "robot")],
)
def test_run_adapter_dispatches_on_backend(
    monkeypatch: pytest.MonkeyPatch, backend: RuleBackend, expected: str
) -> None:
    monkeypatch.setattr(engine, "shacl_issues", lambda *_: [_finding(rule="SHACL")])
    monkeypatch.setattr(engine, "robot_profile_issues", lambda *_: [_finding(rule="ROBOT")])
    ctx = types.SimpleNamespace(g=object(), shapes=object(), shacl_background=None, policy=Policy())
    robot = engine.RobotRequest(Path("a.ttl"), "EL")
    execution, found = engine._run_adapter(_spec(backend=backend), ctx, robot)  # type: ignore[arg-type]  # noqa: SLF001
    assert execution.status is ExecutionStatus.EXECUTED
    assert [f.rule for f in found] == [expected.upper()]


# --- linter -------------------------------------------------------------------------------------


def test_linter_local_name_returns_the_fragment() -> None:
    assert Linter.local_name(URIRef("http://example.org/ns#Thing")) == "Thing"
    assert Linter.local_name(URIRef("http://example.org/ns/Other")) == "Other"


# --- reporting ----------------------------------------------------------------------------------


def _broken_file(path: str) -> FileReport:
    return FileReport(path, path, (), (RuleExecution("SEM001", ExecutionStatus.FAILED, "boom"),))


def test_text_executions_are_path_prefixed_only_for_multiple_files() -> None:
    single = render_report(RunReport((_broken_file("a.ttl"),)), "text")
    assert "a.ttl: Rule execution" not in single
    assert single.splitlines()[-2].startswith("Rule execution")
    pair = render_report(RunReport((_broken_file("a.ttl"), _broken_file("b.ttl"))), "text")
    assert "a.ttl: Rule execution" in pair
    assert "b.ttl: Rule execution" in pair


@pytest.mark.parametrize("fail_on", ["error", "warning", "info", "never"])
@pytest.mark.parametrize("severity", ["error", "warning", "info"])
def test_exit_code_threshold_matrix(fail_on: str, severity: str) -> None:
    order = {"error": 0, "warning": 1, "info": 2}
    expected = int(fail_on != "never" and order[severity] <= order[fail_on])
    assert exit_code([_finding(severity)], fail_on) == expected
    assert exit_code([], fail_on) == 0


# --- rules.builtin ------------------------------------------------------------------------------


def _module(**attrs: object) -> types.ModuleType:
    module = types.ModuleType("fake")
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


def test_as_rule_module_requires_both_specs_tuple_and_callable_run() -> None:
    with pytest.raises(TypeError):
        builtin.as_rule_module(_module(SPECS=[], run=lambda ctx: None))
    with pytest.raises(TypeError):
        builtin.as_rule_module(_module(SPECS=(), run=None))
    with pytest.raises(TypeError):
        builtin.as_rule_module(_module(SPECS=(), run=42))
    with pytest.raises(TypeError):
        builtin.as_rule_module(_module())
    builtin.as_rule_module(_module(SPECS=(), run=lambda ctx: None))


@pytest.mark.parametrize(
    "bad",
    [
        _spec("E001", RuleBackend.PYSHACL, module="mod"),  # module set, non-graph backend
        _spec("E002", RuleBackend.RDFLIB, module=""),  # no module, graph backend
        _spec("E003", RuleBackend.RDFLIB, module="mod"),  # both wrong
    ],
)
def test_validate_modules_flags_malformed_external_specs(monkeypatch: pytest.MonkeyPatch, bad: RuleSpec) -> None:
    monkeypatch.setattr(builtin, "EXTERNAL_SPECS", (bad,))
    problems = builtin.validate_modules(())
    assert problems == [f"{bad.rule_id}: external specs need module='' and a non-graph backend"]


def test_validate_modules_accepts_well_formed_external_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(builtin, "EXTERNAL_SPECS", (_spec("E004", RuleBackend.PYSHACL, module=""),))
    assert builtin.validate_modules(()) == []


# --- adapters.robot -----------------------------------------------------------------------------


def test_robot_subprocess_is_not_checked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ttl = tmp_path / "a.ttl"
    ttl.write_text("", encoding="utf-8")
    seen: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.update(kwargs)
        if kwargs.get("check"):
            raise subprocess.CalledProcessError(1, command)
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr=ROBOT_REPORT,
        )

    monkeypatch.setattr(robot_adapter.subprocess, "run", fake_run)
    findings = robot_adapter.robot_profile_issues(ttl, "EL", "img", 5)
    assert seen == {"capture_output": True, "text": True, "timeout": 5, "check": False}
    assert [f.rule for f in findings] == ["SEM001"]
    assert "Use of undeclared class" in findings[0].message


def test_robot_container_runs_as_the_calling_user(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # The output directory is a private 0700 temporary directory: the image's own user cannot write to it.
    ttl = tmp_path / "a.ttl"
    ttl.write_text("", encoding="utf-8")
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(robot_adapter.os, "getuid", lambda: 1001, raising=False)
    monkeypatch.setattr(robot_adapter.os, "getgid", lambda: 121, raising=False)
    monkeypatch.setattr(robot_adapter.subprocess, "run", fake_run)
    assert robot_adapter.robot_profile_issues(ttl, "EL", "img", 5) == []
    command = commands[0]
    assert command[command.index("--user") + 1] == "1001:121"
    assert command.index("--user") < command.index("img")  # a Docker option, not a ROBOT argument


def test_robot_container_user_is_omitted_without_posix_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(robot_adapter.sys, "platform", "win32")
    assert robot_adapter._host_user() == []  # noqa: SLF001
