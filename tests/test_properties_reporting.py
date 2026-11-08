"""Properties of reporting: fingerprints, ordering, baselines, JSON/SARIF output and exit codes."""

from __future__ import annotations

import json
import random
import re
import tempfile
from argparse import Namespace
from dataclasses import replace
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis_strategies import RULE_IDS, budget, roundtrip_triple_lists
from hypothesis_strategies import build_graph as build

from ontolint.cli import _apply_baselines, main
from ontolint.engine import sort_findings
from ontolint.models import ExecutionStatus, Finding, RuleExecution
from ontolint.reporting import (
    FAIL_THRESHOLDS,
    SARIF_LEVELS,
    SEVERITY_ORDER,
    FileReport,
    RunReport,
    exit_code,
    fingerprint,
    render_report,
    run_exit_code,
    to_json,
    to_sarif,
    to_sarif_report,
)
from ontolint.rules.registry import default_registry

pytestmark = pytest.mark.slow

REGISTRY = default_registry()
KEEP_RATIO = 0.7
severities = st.sampled_from(SEVERITY_ORDER)
texts = st.one_of(st.text(max_size=30), st.sampled_from(("", chr(0x202E), "\x00", "x" * 300, "a\nb", '"quoted"', "💥")))
findings = st.builds(
    Finding,
    rule=st.sampled_from(RULE_IDS + ("ZZZ999",)),
    severity=severities,
    focus=texts,
    message=texts,
    suggestion=texts,
    confidence=st.sampled_from(("certain", "heuristic")),
)
finding_lists = st.lists(findings, max_size=8)
executions = st.builds(
    lambda rule, status: RuleExecution(rule, status, "" if status is ExecutionStatus.EXECUTED else "because"),
    st.sampled_from(RULE_IDS),
    st.sampled_from(list(ExecutionStatus)),
)


def identity(f: Finding) -> tuple[str, str, str]:
    return f.rule, f.focus, f.message


# --- fingerprints ------------------------------------------------------------------------------------


@budget(1)
@given(findings, st.one_of(st.none(), texts))
def test_fingerprint_is_a_stable_sha256_of_rule_focus_message_only(f: Finding, path: str | None) -> None:
    """INVARIANT: a fingerprint is a 64-hex digest, repeatable, and independent of severity, fix and confidence."""
    digest = fingerprint(f, path)

    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert digest == fingerprint(replace(f), path)
    other = replace(f, severity="info" if f.severity != "info" else "error", suggestion="x", confidence="certain")
    assert fingerprint(other, path) == digest


@budget(1)
@given(findings, findings, st.one_of(st.none(), texts))
def test_fingerprints_distinguish_distinct_identities(a: Finding, b: Finding, path: str | None) -> None:
    """INVARIANT: findings with different (rule, focus, message) never share a fingerprint; equal ones always do."""
    assert (fingerprint(a, path) == fingerprint(b, path)) == (identity(a) == identity(b))


@budget(1)
@given(findings, texts)
def test_fingerprint_with_a_path_differs_from_the_single_file_form(f: Finding, path: str) -> None:
    """INVARIANT: multi-file fingerprints include the path, so they differ from the path-less ones."""
    assert fingerprint(f, path) != fingerprint(f)
    assert fingerprint(f, path) != fingerprint(f, path + "x")


@budget(1)
@given(finding_lists, st.randoms(use_true_random=False))
def test_fingerprint_set_is_independent_of_finding_order(items: list[Finding], rnd: random.Random) -> None:
    """INVARIANT: the baseline fingerprint set does not depend on the order of the findings."""
    shuffled = list(items)
    rnd.shuffle(shuffled)

    assert {fingerprint(f) for f in items} == {fingerprint(f) for f in shuffled}


# --- sorting -----------------------------------------------------------------------------------------


@budget(1)
@given(finding_lists, st.randoms(use_true_random=False))
def test_sort_findings_orders_by_severity_rule_focus_message(items: list[Finding], rnd: random.Random) -> None:
    """INVARIANT: sort_findings is a permutation, idempotent, ordered by the documented key and input-order blind."""
    shuffled = list(items)
    rnd.shuffle(shuffled)

    result = sort_findings(list(items))

    key = [(SEVERITY_ORDER.index(f.severity), f.rule, f.focus, f.message) for f in result]
    assert key == sorted(key)
    assert sorted(map(repr, result)) == sorted(map(repr, items))
    assert sort_findings(list(result)) == result
    assert [identity(f) for f in sort_findings(shuffled)] == [identity(f) for f in result]


# --- baselines ---------------------------------------------------------------------------------------


def _baseline_args(baseline: Path | None = None, write: Path | None = None) -> Namespace:
    return Namespace(baseline=str(baseline) if baseline else None, write_baseline=str(write) if write else None)


@budget(0.5)
@given(finding_lists, st.randoms(use_true_random=False), st.booleans())
def test_baseline_removes_exactly_the_baselined_findings(items: list[Finding], rnd: random.Random, multi: bool) -> None:
    """INVARIANT: applying a baseline removes exactly the findings whose fingerprints it holds."""
    paths = ("a.ttl", "b.ttl") if multi else ("a.ttl",)
    reports = [FileReport(p, p, tuple(i for i in items if rnd.random() < KEEP_RATIO)) for p in paths]
    known = [replace(r, findings=r.findings[: len(r.findings) // 2]) for r in reports]
    with tempfile.TemporaryDirectory() as folder:
        baseline = Path(folder) / "baseline.json"
        _apply_baselines(known, _baseline_args(write=baseline))
        kept, _stale = _apply_baselines(reports, _baseline_args(baseline=baseline))

    prints = {fingerprint(f, r.path if multi else None) for r in known for f in r.findings}
    for before, after in zip(reports, kept, strict=True):
        expected = tuple(f for f in before.findings if fingerprint(f, before.path if multi else None) not in prints)
        assert after.findings == expected


@budget(0.3)
@given(roundtrip_triple_lists(), st.sampled_from((None, "obo")), st.sampled_from(("error", "warning", "info")))
def test_baseline_round_trip_through_the_cli_leaves_no_findings(
    triples: list, profile: str | None, fail_on: str
) -> None:
    """INVARIANT: ``--write-baseline`` then ``--baseline`` on the same file reports no findings and exits 0."""
    graph = build(triples)
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        source, baseline, out = root / "o.ttl", root / "baseline.json", root / "out.json"
        graph.serialize(source, format="turtle")
        extra = ["--profile", profile] if profile else []
        first = main([str(source), "--write-baseline", str(baseline), "--output", str(out), "--format", "json", *extra])
        findings_before = json.loads(out.read_text(encoding="utf-8"))["findings"]
        second = main(
            [
                str(source),
                "--baseline",
                str(baseline),
                "--output",
                str(out),
                "--format",
                "json",
                "--fail-on",
                fail_on,
                *extra,
            ]
        )
        document = json.loads(out.read_text(encoding="utf-8"))

    assert first in (0, 1)
    assert first == 0 or findings_before
    assert second == 0
    assert document["findings"] == []


def test_baseline_matches_findings_about_blank_nodes_across_runs() -> None:
    """A baseline written from one run must silence the same finding on a re-parse of the unchanged file."""
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        source, baseline, out = root / "o.ttl", root / "baseline.json", root / "out.json"
        source.write_text("@prefix owl: <http://www.w3.org/2002/07/owl#> .\n[] owl:unionOf () .\n", encoding="utf-8")
        main([str(source), "--write-baseline", str(baseline), "--output", str(out), "--format", "json"])
        code = main([str(source), "--baseline", str(baseline), "--output", str(out), "--format", "json"])
        remaining = json.loads(out.read_text(encoding="utf-8"))["findings"]

    assert not [f for f in remaining if f["rule"] == "OWL031"]
    assert code in (0, 1)


# --- JSON and SARIF ----------------------------------------------------------------------------------


@st.composite
def run_reports(draw: st.DrawFn) -> RunReport:
    count = draw(st.integers(1, 3))
    files = tuple(
        FileReport(
            f"dir/file{i}.ttl",
            f"dir/file{i}.ttl",
            tuple(draw(finding_lists)),
            tuple(draw(st.lists(executions, max_size=4))),
        )
        for i in range(count)
    )
    specs = tuple(REGISTRY.get(r) for r in sorted(draw(st.sets(st.sampled_from(RULE_IDS), max_size=6))))
    overrides = draw(st.dictionaries(st.sampled_from(RULE_IDS), severities, max_size=3))
    return RunReport(files, specs, overrides)


@budget(1)
@given(run_reports())
def test_json_report_is_valid_json_with_the_required_keys(report: RunReport) -> None:
    """INVARIANT: the JSON report parses, round-trips and carries schema, summary, findings, rules, executions."""
    text = render_report(report, "json")

    document = json.loads(text)
    assert document == to_json(report)
    assert {"schema_version", "summary", "findings", "execution_summary", "rules", "files"} <= set(document)
    assert len(document["findings"]) == len(report.findings)
    assert sum(document["summary"].values()) == len(report.findings)
    assert set(document["execution_summary"]) == {s.value for s in ExecutionStatus}
    assert {"rule", "severity", "focus", "message", "suggestion", "confidence", "path"} <= set(
        document["findings"][0]
        if document["findings"]
        else {"rule", "severity", "focus", "message", "suggestion", "confidence", "path"}
    )
    assert [r["id"] for r in document["rules"]] == [s.rule_id for s in report.rules]


@budget(1)
@given(run_reports(), st.one_of(st.none(), st.integers(0, 2)))
def test_sarif_report_is_valid_json_with_the_required_keys(report: RunReport, status: int | None) -> None:
    """INVARIANT: SARIF parses and has version, driver, one result per finding and consistent rule indexes."""
    document = json.loads(render_report(report, "sarif", status))

    assert document["version"] == "2.1.0"
    (run,) = document["runs"]
    assert run["tool"]["driver"]["name"] == "ontolint"
    assert len(run["results"]) == len(report.findings)
    rules = run["tool"]["driver"]["rules"]
    assert [r["id"] for r in rules] == [s.rule_id for s in report.rules]
    for result, finding in zip(run["results"], report.findings, strict=True):
        assert result["ruleId"] == finding.rule
        assert result["level"] == SARIF_LEVELS[finding.severity]
        assert result["message"]["text"]
        assert result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
        if "ruleIndex" in result:
            assert rules[result["ruleIndex"]]["id"] == finding.rule
    (invocation,) = run["invocations"]
    non_executed = [x for r in report.files for x in r.executions if x.status is not ExecutionStatus.EXECUTED]
    assert len(invocation["toolExecutionNotifications"]) == len(non_executed)
    assert invocation["executionSuccessful"] == (not report.broken)
    assert ("exitCode" in invocation) == (status is not None)
    assert document == to_sarif_report(report, status)


@budget(1)
@given(finding_lists)
def test_bare_findings_sarif_and_text_render_for_any_findings(items: list[Finding]) -> None:
    """INVARIANT: SARIF for bare findings and the text report never fail and mention every finding."""
    sarif = json.loads(json.dumps(to_sarif(items)))
    text = render_report(RunReport((FileReport("a", "a", tuple(items)),)), "text")

    assert len(sarif["runs"][0]["results"]) == len(items)
    assert text.startswith(f"Ontology linter: {len(items)} finding(s)")
    assert all(f.rule in text for f in items)


# --- exit codes --------------------------------------------------------------------------------------


@budget(1)
@given(finding_lists, finding_lists)
def test_exit_code_is_monotone_in_threshold_and_in_findings(items: list[Finding], more: list[Finding]) -> None:
    """INVARIANT: never <= error <= warning <= info; adding findings never lowers the code; empty input is 0."""
    codes = [exit_code(items, level) for level in ("never", "error", "warning", "info")]

    assert codes == sorted(codes)
    assert codes[0] == 0
    assert exit_code([], "info") == 0
    for level in FAIL_THRESHOLDS:
        assert exit_code([*items, *more], level) >= exit_code(items, level)
        threshold = FAIL_THRESHOLDS[level]
        assert exit_code(items, level) == int(any(SEVERITY_ORDER.index(f.severity) <= threshold for f in items))


@budget(1)
@given(run_reports(), st.sampled_from(sorted(FAIL_THRESHOLDS)))
def test_run_exit_code_is_two_for_broken_rules_else_the_findings_code(report: RunReport, fail_on: str) -> None:
    """INVARIANT: a failed or unsupported rule forces 2; otherwise the code is exit_code over all findings."""
    code = run_exit_code(report, fail_on)

    assert code == (2 if report.broken else exit_code(report.findings, fail_on))
    assert code in (0, 1, 2)
