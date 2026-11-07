"""CLI discovery, selection, profile, multi-file, report-metadata and platform-path contracts."""

from __future__ import annotations

import hashlib
import json
import tomllib
from collections.abc import Callable
from importlib import metadata
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import pytest

from ontolint import main
from ontolint._version import FALLBACK_VERSION, package_version
from ontolint.catalogue import implemented_rows, planned_rows
from ontolint.github import escape_data, escape_property
from ontolint.models import ExecutionStatus, Finding, Requirement, RuleExecution
from ontolint.paths import artifact_uri, display_path, resolve_inputs
from ontolint.profiles import PROFILES
from ontolint.reporting import (
    FileReport,
    Location,
    RunReport,
    fingerprint,
    render_report,
    run_exit_code,
    to_sarif,
    to_sarif_report,
)
from ontolint.rules.registry import UnknownSelectorError, default_registry
from ontolint.rules.specs import RULE_SPECS
from ontolint.selection import SelectorSyntaxError, resolve_selection, split_selectors, unknown_selector_help

ROOT = Path(__file__).parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
KITCHEN, CLEAN = str(FIXTURES / "kitchen_sink.ttl"), str(FIXTURES / "clean.ttl")
SHAPES = str(FIXTURES / "kitchen_shapes.ttl")
TOOL_FAILURE = 2
FAILING_INPUTS = ("broken.ttl", "missing.ttl")
# SHACL001, SEM001 and every SHQ rule need an optional input (shapes graph / OWL-profile request).
SKIPPED_WITHOUT_OPTIONAL_INPUTS = sum(spec.requires is not Requirement.NONE for spec in RULE_SPECS)
Run = Callable[..., tuple[int, str, str]]


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> Run:
    monkeypatch.chdir(FIXTURES)

    def _run(*argv: str) -> tuple[int, str, str]:
        code = main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return _run


def _json(run: Run, *argv: str) -> tuple[int, dict[str, Any]]:
    code, out, _ = run(*argv, "--format", "json")
    return code, json.loads(out)


def _statuses(document: dict[str, Any], file_index: int = 0) -> dict[str, tuple[str, str]]:
    return {x["rule"]: (x["status"], x["detail"]) for x in document["files"][file_index]["executions"]}


# --- version, listing, explain -----------------------------------------------------------------


def test_version_matches_project_metadata(run: Run) -> None:
    code, out, _ = run("--version")
    assert (code, out) == (0, f"ontolint {package_version()}\n")
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == FALLBACK_VERSION


def test_version_falls_back_when_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(_: str) -> str:
        raise metadata.PackageNotFoundError

    monkeypatch.setattr("ontolint._version.metadata.version", missing)
    assert package_version() == FALLBACK_VERSION


def test_list_rules_json_separates_implemented_from_proposed(run: Run) -> None:
    code, out, _ = run("--list-rules", "--format", "json")
    document = json.loads(out)
    rows = document["rules"]
    assert code == 0 and document["schema_version"] == 1
    implemented = [r for r in rows if r["selectable"]]
    proposed = [r for r in rows if not r["selectable"]]
    assert len(implemented) == len(implemented_rows())
    assert len(proposed) == len(planned_rows())
    assert {r["status"] for r in implemented} == {"implemented"}
    assert {r["status"] for r in proposed} == {"proposed"}
    assert all(r["severity"] and r["scope"] and r["backend"] and r["category"] for r in implemented)
    assert all(r["severity"] is None and r["scope"] is None for r in proposed)
    assert "executed" not in out and "skipped" not in out


def test_list_rules_text_is_a_table_with_status_column(run: Run) -> None:
    code, out, _ = run("--list-rules")
    lines = out.splitlines()
    assert code == 0
    assert lines[0].split() == ["ID", "FAMILY", "SEVERITY", "CATEGORY", "BACKEND", "SCOPE", "STATUS"]
    assert any(line.startswith("SHACL001") and "pyshacl" in line and "implemented" in line for line in lines)
    assert any(line.split()[-1] == "proposed" for line in lines[1:-1])
    assert "proposed rules cannot be selected or run" in lines[-1]


def test_explain_implemented_rule_text_and_json(run: Run) -> None:
    code, out, _ = run("--explain", "shq001")
    assert code == 0
    for expected in ("SHQ001:", "Catalogue status", "implemented", "Requires", "shapes", "Test requirement", "Backend"):
        assert expected in out
    _, document = _json(run, "--explain", "SHQ001")
    spec = default_registry().get("SHQ001")
    assert document["rule"]["suggestion"] == spec.suggestion
    assert document["rule"]["requires"] == "shapes" and document["rule"]["selectable"] is True


def test_explain_proposed_rule_says_it_cannot_run(run: Run) -> None:
    proposed = planned_rows()[0]
    code, out, _ = run("--explain", proposed.rule_id)
    assert code == 0
    assert "proposed only" in out and "proposed" in out
    _, document = _json(run, "--explain", proposed.rule_id)
    assert document["rule"]["selectable"] is False and document["rule"]["suggestion"] is None


def test_explain_unknown_rule_exits_2(run: Run) -> None:
    code, out, err = run("--explain", "NOPE999")
    assert (code, out) == (TOOL_FAILURE, "")
    assert err.startswith("TOOL001:") and "NOPE999" in err and "--list-rules" in err


# --- selectors ---------------------------------------------------------------------------------


def test_split_selectors_flattens_normalises_and_dedupes() -> None:
    assert split_selectors(["ont, iri", "ONT001", "ont"]) == ("ONT", "IRI", "ONT001")
    assert split_selectors([]) == ()
    for bad in ("", "ONT,", ",ONT", "ONT,,IRI", " "):
        with pytest.raises(SelectorSyntaxError):
            split_selectors([bad])


def test_select_runs_only_matching_rules_and_ignore_wins(run: Run) -> None:
    _, document = _json(run, KITCHEN, "--select", "ONT,iri", "--select", "LEX001", "--ignore", "ONT001")
    statuses = _statuses(document)
    assert {rule[:3] for rule in statuses} == {"ONT", "IRI", "LEX"}
    assert statuses["ONT001"][0] == "skipped" and "ignored" in statuses["ONT001"][1]
    assert statuses["ONT002"][0] == "executed" and statuses["LEX001"][0] == "executed"
    assert "LEX002" not in statuses  # deselected rules are absent, not "passed"
    assert {f["rule"] for f in document["findings"]} <= {r for r, (s, _) in statuses.items() if s == "executed"}


def test_ignore_family_removes_its_findings_and_is_visible_in_text(run: Run) -> None:
    code, out, _ = run(KITCHEN, "--ignore", "ONT", "--fail-on", "never")
    assert code == 0
    assert "ONT001" in out.split("Rule execution:")[1]  # shown as SKIPPED with its reason
    assert " ONT001 " not in out.split("Rule execution:")[0]
    assert "[SKIPPED    ] ONT001: ignored by --ignore or profile" in out


def test_policy_ignored_rules_union_with_cli_ignore(run: Run, tmp_path: Path) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"ignored_rules": ["ONT004"]}), encoding="utf-8")
    _, document = _json(run, KITCHEN, "--config", str(policy), "--ignore", "ONT001")
    statuses = _statuses(document)
    assert statuses["ONT004"] == ("skipped", "ignored by policy")
    assert statuses["ONT001"][0] == "skipped" and "--ignore" in statuses["ONT001"][1]
    assert statuses["ONT002"][0] == "executed"
    # An ignore always beats a select, wherever the ignore came from.
    _, document = _json(run, KITCHEN, "--config", str(policy), "--select", "ONT004,ONT002")
    assert _statuses(document) == {"ONT002": ("executed", ""), "ONT004": ("skipped", "ignored by policy")}
    assert "ONT004" not in {f["rule"] for f in document["findings"]}


def test_unknown_selectors_are_tool_failures(run: Run) -> None:
    code, out, err = run(KITCHEN, "--select", "ONT,NOPE999")
    assert (code, out) == (TOOL_FAILURE, "")
    assert err.startswith("TOOL001: configuration failed: UnknownSelectorError") and "NOPE999" in err
    code, _, err = run(KITCHEN, "--ignore", "TYPO")
    assert code == TOOL_FAILURE and "TYPO" in err
    code, _, err = run(KITCHEN, "--select", "ONT,")
    assert code == TOOL_FAILURE and "empty rule selector" in err


def test_selecting_a_proposed_rule_explains_why_it_is_unknown(run: Run) -> None:
    proposed = planned_rows()[0].rule_id
    code, _, err = run(KITCHEN, "--select", proposed)
    assert code == TOOL_FAILURE and "proposed rules and are not implemented" in err
    assert "proposed" not in unknown_selector_help(UnknownSelectorError(["TYPO"]), frozenset({proposed}))


def test_selecting_only_cli_rules_runs_nothing_and_reports_no_executions(run: Run) -> None:
    code, document = _json(run, KITCHEN, "--select", "INPUT001")
    assert code == 0 and document["findings"] == [] and document["files"][0]["executions"] == []


# --- profiles ----------------------------------------------------------------------------------


def test_profiles_are_valid_pure_data() -> None:
    registry = default_registry()
    assert set(PROFILES) == {"minimal", "recommended", "ci", "strict", "obo", "fair"}
    for profile in PROFILES.values():
        assert profile.description and profile.fail_on in {"error", "warning", "info", "never"}
        registry.select(profile.select or ())  # strict: raises on a typo
        for rule, severity in profile.severity_overrides:
            assert rule in registry and severity in {"error", "warning", "info"}


def test_profile_minimal_selects_its_families(run: Run) -> None:
    _, document = _json(run, KITCHEN, "--profile", "minimal")
    assert {rule.rstrip("0123456789") for rule in _statuses(document)} == {"ONT", "IRI", "DATA", "SKOS", "SHACL", "SEM"}


def test_explicit_select_replaces_the_profile_selection(run: Run) -> None:
    _, document = _json(run, KITCHEN, "--profile", "minimal", "--select", "LEX")
    assert {rule[:3] for rule in _statuses(document)} == {"LEX"}


def test_profile_recommended_equals_no_profile(run: Run) -> None:
    assert run(KITCHEN, "--format", "json") == run(KITCHEN, "--format", "json", "--profile", "recommended")


def test_profile_severity_override_and_policy_precedence(run: Run, tmp_path: Path) -> None:
    _, document = _json(run, KITCHEN, "--profile", "strict", "--select", "ONT003")
    assert {f["severity"] for f in document["findings"] if f["rule"] == "ONT003"} == {"error"}
    assert document["rules"][0]["severity"] == "error" and document["rules"][0]["default_severity"] == "warning"
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"severity_overrides": {"ONT003": "info"}}), encoding="utf-8")
    _, document = _json(run, KITCHEN, "--profile", "strict", "--select", "ONT003", "--config", str(policy))
    assert {f["severity"] for f in document["findings"]} == {"info"}


def test_fail_on_precedence_cli_then_profile_then_error(run: Run) -> None:
    only_info = ("--select", "ONT004")  # info-level finding on the kitchen sink
    assert run(KITCHEN, *only_info)[0] == 0
    assert run(KITCHEN, *only_info, "--profile", "recommended")[0] == 0
    assert run(KITCHEN, *only_info, "--profile", "strict")[0] == 1
    assert run(KITCHEN, *only_info, "--profile", "strict", "--fail-on", "never")[0] == 0
    assert run(CLEAN, "--profile", "ci")[0] == 0


# --- multi-file --------------------------------------------------------------------------------


def test_single_file_fingerprint_is_unchanged_and_path_distinguishes_files() -> None:
    finding = Finding("ONT001", "warning", "focus", "message", "fix")
    legacy = '["ONT001","focus","message"]'
    assert fingerprint(finding) == hashlib.sha256(legacy.encode()).hexdigest()
    assert fingerprint(finding, "a.ttl") != fingerprint(finding, "b.ttl") != fingerprint(finding)


def test_multi_file_reports_are_per_file_sorted_and_deduplicated(run: Run) -> None:
    code, document = _json(run, KITCHEN, CLEAN, "clean.ttl", "./clean.ttl", "../fixtures/kitchen_sink.ttl")
    assert code == 1
    assert [f["path"] for f in document["files"]] == ["clean.ttl", "kitchen_sink.ttl"]
    assert {f["path"] for f in document["findings"]} == {"kitchen_sink.ttl"}
    reversed_code, reversed_document = _json(run, CLEAN, KITCHEN)
    assert (reversed_code, reversed_document) == (code, document)


def test_multi_file_baseline_keeps_identical_findings_in_two_files_distinct(run: Run, tmp_path: Path) -> None:
    twin = tmp_path / "twin.ttl"
    twin.write_text(Path(KITCHEN).read_text(encoding="utf-8"), encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    args = (KITCHEN, str(twin), "--fail-on", "never")
    assert run(*args, "--write-baseline", str(baseline))[0] == 0
    fingerprints = json.loads(baseline.read_text(encoding="utf-8"))["fingerprints"]
    _, single = _json(run, KITCHEN)
    assert len(fingerprints) == 2 * len(single["findings"])
    code, document = _json(run, *args, "--baseline", str(baseline))
    assert code == 0 and document["findings"] == []
    # A baseline from the single-file run does not hide the same findings once a second file joins.
    single_baseline = tmp_path / "single.json"
    run(KITCHEN, "--write-baseline", str(single_baseline))
    _, document = _json(run, KITCHEN, str(twin), "--baseline", str(single_baseline))
    assert document["findings"]


def test_multi_file_text_has_sections(run: Run) -> None:
    code, out, _ = run(KITCHEN, CLEAN)
    assert code == 1
    assert out.splitlines()[0].endswith("in 2 file(s)")
    assert "== clean.ttl: 0 finding(s)" in out and "== kitchen_sink.ttl:" in out


def test_one_unparsable_file_fails_the_run_and_every_failure_is_reported(run: Run) -> None:
    code, out, err = run(KITCHEN, *FAILING_INPUTS)
    assert (code, out) == (TOOL_FAILURE, "")
    lines = [line for line in err.splitlines() if line.startswith("INPUT001:")]
    assert len(lines) == len(FAILING_INPUTS) and all("RDF input parsing failed for " in line for line in lines)
    assert "broken.ttl" in lines[0] and "missing.ttl" in lines[1]


def test_directories_are_rejected_not_walked(run: Run) -> None:
    code, out, err = run(str(FIXTURES))
    assert (code, out) == (TOOL_FAILURE, "")
    assert err.startswith("INPUT001: RDF input parsing failed: IsADirectoryError") and "shell globbing" in err


def test_missing_ontology_argument_is_a_usage_error(run: Run) -> None:
    with pytest.raises(SystemExit) as info:
        run("--format", "json")
    assert info.value.code == TOOL_FAILURE


def test_resolve_inputs_dedupes_aliases_and_sorts(tmp_path: Path) -> None:
    (tmp_path / "b.ttl").write_text("", encoding="utf-8")
    (tmp_path / "a.ttl").write_text("", encoding="utf-8")
    (tmp_path / "link.ttl").symlink_to(tmp_path / "a.ttl")
    raw = ["b.ttl", "link.ttl", "./a.ttl", "a.ttl", "missing.ttl", "missing.ttl"]
    inputs = resolve_inputs(raw, tmp_path)
    assert [x.display for x in inputs] == ["a.ttl", "b.ttl", "missing.ttl"]
    assert [x.display for x in resolve_inputs(raw[::-1], tmp_path)] == ["a.ttl", "b.ttl", "missing.ttl"]
    assert all(x.path.is_absolute() for x in inputs)
    assert [x.display for x in resolve_inputs([str(tmp_path / "sub" / ".." / "b.ttl")], tmp_path)] == ["b.ttl"]


# --- platform paths ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "root", "display", "uri"),
    [
        (
            PureWindowsPath(r"C:\work\repo\onto\a b.ttl"),
            PureWindowsPath("C:/work/repo"),
            "onto/a b.ttl",
            "onto/a%20b.ttl",
        ),
        (PureWindowsPath(r"c:\WORK\Repo\a.ttl"), PureWindowsPath(r"C:\work\repo"), "a.ttl", "a.ttl"),
        (
            PureWindowsPath(r"D:\other\a.ttl"),
            PureWindowsPath(r"C:\work\repo"),
            "D:/other/a.ttl",
            "file:///D:/other/a.ttl",
        ),
        (
            PureWindowsPath(r"\\srv\share\a.ttl"),
            PureWindowsPath(r"C:\work"),
            "//srv/share/a.ttl",
            "file://srv/share/a.ttl",
        ),
        (PureWindowsPath(r"sub\a.ttl"), PureWindowsPath(r"C:\work"), "sub/a.ttl", "sub/a.ttl"),
        (PurePosixPath("/repo/onto/a.ttl"), PurePosixPath("/repo"), "onto/a.ttl", "onto/a.ttl"),
        (PurePosixPath("/elsewhere/é.ttl"), PurePosixPath("/repo"), "/elsewhere/é.ttl", "file:///elsewhere/%C3%A9.ttl"),
        (PurePosixPath("/repo/Repo/a.ttl"), PurePosixPath("/REPO"), "/repo/Repo/a.ttl", "file:///repo/Repo/a.ttl"),
    ],
)
def test_report_paths_are_posix_style_on_every_platform(
    path: PurePosixPath | PureWindowsPath, root: PurePosixPath | PureWindowsPath, display: str, uri: str
) -> None:
    assert display_path(path, root) == display
    assert artifact_uri(path, root) == uri
    assert "\\" not in display and "\\" not in uri


# --- report metadata, execution status and exit codes -----------------------------------------


def test_json_schema_rules_and_execution_status(run: Run) -> None:
    code, document = _json(run, KITCHEN)
    assert code == 1 and document["schema_version"] == 1
    assert {"summary", "findings", "rules", "files", "execution_summary"} <= document.keys()
    rule = next(r for r in document["rules"] if r["id"] == "ONT001")
    assert {
        "title",
        "severity",
        "default_severity",
        "category",
        "backend",
        "scope",
        "requires",
        "suggestion",
    } <= rule.keys()
    statuses = _statuses(document)
    assert statuses["SHACL001"] == ("skipped", "no SHACL shapes graph was supplied")
    assert statuses["SEM001"][0] == "skipped" and statuses["ONT001"] == ("executed", "")
    assert (
        document["execution_summary"]["skipped"] == SKIPPED_WITHOUT_OPTIONAL_INPUTS
        and document["execution_summary"]["failed"] == 0
    )
    assert all(f["path"] == "kitchen_sink.ttl" for f in document["findings"])


def test_sarif_carries_rule_metadata_locations_and_invocation(run: Run) -> None:
    code, out, _ = run(KITCHEN, "--format", "sarif")
    sarif = json.loads(out)
    (sarif_run,) = sarif["runs"]
    driver = sarif_run["tool"]["driver"]
    rules = {r["id"]: r for r in driver["rules"]}
    ont001 = rules["ONT001"]
    assert ont001["name"] == "ONT001" and ont001["shortDescription"]["text"] and ont001["fullDescription"]["text"]
    assert ont001["help"]["text"] and ont001["defaultConfiguration"]["level"] == "warning"
    assert set(ont001["properties"]) == {"category", "backend", "scope"}
    assert driver["version"] == package_version()
    for result in sarif_run["results"]:
        assert result["locations"] == [{"physicalLocation": {"artifactLocation": {"uri": "kitchen_sink.ttl"}}}]
        assert driver["rules"][result["ruleIndex"]]["id"] == result["ruleId"]
    (invocation,) = sarif_run["invocations"]
    assert invocation["executionSuccessful"] is True and invocation["exitCode"] == code
    skipped = {n["associatedRule"]["id"]: n for n in invocation["toolExecutionNotifications"]}
    assert skipped["SHACL001"]["level"] == "note" and "no SHACL shapes graph" in skipped["SHACL001"]["message"]["text"]
    assert invocation["properties"]["executionSummary"]["executed"] > 0


def test_sarif_without_paths_omits_nothing_required() -> None:
    sarif = to_sarif([Finding("ONT001", "warning", "f", "m", "s"), Finding("ZZZ999", "info", "f", "m", "s")])
    results = sarif["runs"][0]["results"]
    assert [r["ruleId"] for r in results] == ["ONT001", "ZZZ999"]
    assert "ruleIndex" in results[0] and "ruleIndex" not in results[1]
    assert [r["id"] for r in sarif["runs"][0]["tool"]["driver"]["rules"]] == ["ONT001"]


def test_sarif_region_is_emitted_only_when_a_location_is_supplied() -> None:
    finding = Finding("ONT001", "warning", "f", "m", "s")
    other = Finding("ONT002", "warning", "f", "m", "s")
    third = Finding("ONT003", "warning", "f", "m", "s")
    locations = {finding: Location(3, 7), other: Location(9)}
    report = RunReport((FileReport("a.ttl", "a.ttl", (finding, other, third), (), locations),))
    regions = [
        r["locations"][0]["physicalLocation"].get("region") for r in to_sarif_report(report)["runs"][0]["results"]
    ]
    assert regions == [{"startLine": 3, "startColumn": 7}, {"startLine": 9}, None]


def _robot_report(status: ExecutionStatus) -> RunReport:
    execution = RuleExecution("SEM001", status, "because")
    return RunReport((FileReport("a.ttl", "a.ttl", (), (execution,)),))


@pytest.mark.parametrize(
    ("status", "level", "successful", "exit_status"),
    [
        (ExecutionStatus.FAILED, "error", False, 2),
        (ExecutionStatus.UNSUPPORTED, "warning", False, 2),
        (ExecutionStatus.SKIPPED, "note", True, 0),
        (ExecutionStatus.EXECUTED, None, True, 0),
    ],
)
def test_non_executed_rules_are_never_a_clean_pass(
    status: ExecutionStatus, level: str | None, successful: bool, exit_status: int
) -> None:
    report = _robot_report(status)
    assert run_exit_code(report, "error") == exit_status
    assert run_exit_code(report, "never") == exit_status
    invocation = to_sarif_report(report)["runs"][0]["invocations"][0]
    assert invocation["executionSuccessful"] is successful
    levels = [n["level"] for n in invocation["toolExecutionNotifications"]]
    assert levels == ([level] if level else [])
    text = render_report(report, "text")
    assert ("SEM001" in text) == (status is not ExecutionStatus.EXECUTED and status is not ExecutionStatus.SKIPPED)


def test_unsupported_backend_exits_2_but_still_reports(
    run: Run, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("ontolint.engine.shutil.which", lambda _: None)
    code, out, err = run(KITCHEN, "--owl-profile", "EL", "--format", "json", "--fail-on", "never")
    document = json.loads(out)
    assert code == TOOL_FAILURE and _statuses(document)["SEM001"][0] == "unsupported"
    assert document["execution_summary"]["unsupported"] == 1
    assert err.startswith("TOOL001: rule SEM001 unsupported for kitchen_sink.ttl: the docker executable")


def test_failed_adapter_exits_2_and_is_reported(run: Run, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ontolint.engine.shutil.which", lambda _: "docker")

    def boom(*_: Any, **__: Any) -> Any:
        raise OSError("docker daemon unreachable")

    monkeypatch.setattr("ontolint.ontolint.subprocess.run", boom)
    code, out, err = run(KITCHEN, "--owl-profile", "EL", "--format", "sarif")
    invocation = json.loads(out)["runs"][0]["invocations"][0]
    assert (
        code == TOOL_FAILURE and invocation["executionSuccessful"] is False and invocation["exitCode"] == TOOL_FAILURE
    )
    assert any(
        n["level"] == "error" and "docker daemon unreachable" in n["message"]["text"]
        for n in invocation["toolExecutionNotifications"]
    )
    assert "SEM001 failed" in err


def test_shapes_run_marks_shape_rules_executed(run: Run) -> None:
    _, document = _json(run, KITCHEN, "--shapes", SHAPES)
    statuses = _statuses(document)
    assert statuses["SHACL001"][0] == "executed" and statuses["SHQ001"][0] == "executed"


# --- GitHub workflow-command escaping ----------------------------------------------------------


def test_workflow_command_escaping() -> None:
    assert escape_data("100%\r\nnext: a, b") == "100%25%0D%0Anext: a, b"
    assert escape_property("C:\\a,b\nc%") == "C%3A\\a%2Cb%0Ac%25"
    assert escape_data("%0A") == "%250A"  # already-escaped text is escaped again, never trusted


def test_selection_composition_is_pure() -> None:
    registry = default_registry()
    selection = resolve_selection(registry, PROFILES["minimal"], (), ("ONT001",))
    assert "ONT001" in {s.rule_id for s in selection.ignored}
    assert "ONT001" not in {s.rule_id for s in selection.run}
    assert all(s.backend.value != "cli" for s in selection.run + selection.ignored)
