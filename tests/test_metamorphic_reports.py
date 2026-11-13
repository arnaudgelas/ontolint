"""Metamorphic relation: the report formats are views of one result, so they must describe the same findings.

One input is linted with ``--format json``, ``--format sarif`` and the default text format.  The JSON
``findings`` are the reference; the SARIF ``results`` must hold the same rule, the SARIF level of the same severity
and the same focus and message, and the text output the same count and the same severity, rule and focus per line.
The Markdown summary, which lists only the first findings, must count the same findings per severity.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

import pytest
from hypothesis import assume, given
from hypothesis_strategies import budget, roundtrip_triple_lists
from hypothesis_strategies import build_graph as build
from metamorphic_support import cli, serialisable, workdir

from ontolint.reporting import MARKDOWN_SHOWN, SARIF_LEVELS, SEVERITY_ORDER

pytestmark = pytest.mark.slow

FINDING_LINE = re.compile(r"^\[(ERROR|WARNING|INFO) *\] (\S+) (\S+): ", re.MULTILINE)
COUNT_LINE = re.compile(r"^Ontology linter: (\d+) finding\(s\)$", re.MULTILINE)
COUNT_ROW = re.compile(r"^\| (error|warning|info|total) \| (\d+) \|$", re.MULTILINE)
SUMMARY_LINE = re.compile(r"^- \*\*(error|warning|info)\*\* ` (\w+) ` ", re.MULTILINE)


@budget(0.5)
@given(roundtrip_triple_lists())
def test_json_sarif_and_text_reports_describe_the_same_findings(triples: list) -> None:
    """RELATION (report consistency): JSON findings, SARIF results and text lines are the same multiset of
    (rule, severity or its SARIF level, focus), SARIF carries each finding's message, focus and suggestion, and
    the text count, the JSON summary and the SARIF result count agree; the exit code does not depend on the format."""
    graph = build(serialisable(triples))
    assume(len(graph))

    with workdir() as root:
        (root / "g.ttl").write_text(graph.serialize(format="turtle"), encoding="utf-8")
        code, json_text = cli("g.ttl", fmt="json")
        sarif_code, sarif_text = cli("g.ttl", fmt="sarif")
        text_code, text = cli("g.ttl", fmt="text")

    document: dict[str, Any] = json.loads(json_text)
    results: list[dict[str, Any]] = json.loads(sarif_text)["runs"][0]["results"]
    findings: list[dict[str, Any]] = document["findings"]
    assume(findings)  # No finding, nothing to compare.
    assert code == sarif_code == text_code

    sarif_rules = json.loads(sarif_text)["runs"][0]["tool"]["driver"]["rules"]
    assert all(sarif_rules[r["ruleIndex"]]["id"] == r["ruleId"] for r in results)
    expected_sarif = Counter(
        (f["rule"], SARIF_LEVELS[f["severity"]], f"{f['message']} Focus: {f['focus']}. Suggestion: {f['suggestion']}")
        for f in findings
    )
    assert Counter((r["ruleId"], r["level"], r["message"]["text"]) for r in results) == expected_sarif

    expected_text = Counter((f["severity"].upper(), f["rule"], f["focus"]) for f in findings)
    assert Counter(FINDING_LINE.findall(text)) == expected_text
    counts = Counter(f["severity"] for f in findings)
    assert document["summary"] == dict(counts)
    assert [int(n) for n in COUNT_LINE.findall(text)] == [len(findings)]
    assert len(results) == len(findings)


@budget(0.3)
@given(roundtrip_triple_lists())
def test_the_markdown_summary_counts_the_findings_of_the_json_report(triples: list) -> None:
    """RELATION (summary consistency): the summary counts the JSON findings per severity, lists the first
    MARKDOWN_SHOWN of them with their rules, most severe first and otherwise in report order, and exits alike."""
    graph = build(serialisable(triples))
    assume(len(graph))

    with workdir() as root:
        (root / "g.ttl").write_text(graph.serialize(format="turtle"), encoding="utf-8")
        code, json_text = cli("g.ttl", fmt="json")
        markdown_code, markdown = cli("g.ttl", fmt="markdown")

    findings: list[dict[str, Any]] = json.loads(json_text)["findings"]
    counts = Counter(f["severity"] for f in findings)
    assert markdown_code == code
    expected = {**{s: counts[s] for s in SEVERITY_ORDER}, "total": len(findings)}
    assert {s: int(n) for s, n in COUNT_ROW.findall(markdown)} == expected
    ranked = sorted(findings, key=lambda f: SEVERITY_ORDER.index(f["severity"]))
    assert SUMMARY_LINE.findall(markdown) == [(f["severity"], f["rule"]) for f in ranked[:MARKDOWN_SHOWN]]
