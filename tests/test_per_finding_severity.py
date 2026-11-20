"""``RuleContext.add(severity=...)``: a rule with two gravities reports each finding at its own severity.

Issue #63 (``docs/severity-decisions.md``, D2).  The registered severity is the rule's default; a finding may report
another one.  No rule needs this in this commit; SHQ011 and SHQ015 do next, and test the whole path through the CLI.
These tests pin the contract that stays true for any rule that uses it:

* without ``severity=`` nothing changes, with it the finding reports it, an unknown severity is refused;
* the identity and the fingerprint do not contain the severity, so a baseline never tells two of them apart;
* JSON and SARIF carry each finding's own severity and level, and the rule's registered one as its default;
* ``--fail-on`` follows the findings, not the rule.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import pytest
from rule_harness import PREFIXES, graph

from ontolint import Linter
from ontolint.models import Finding
from ontolint.reporting import (
    FileReport,
    RunReport,
    exit_code,
    fingerprint,
    identity,
    to_json,
    to_sarif_report,
)
from ontolint.rules.runtime import RuleContext
from ontolint.rules.specs import RULE_SPECS

RULE = "OWL009"  # registered at error
DEFAULT = "error"
OTHER = "info"


def _context() -> RuleContext:
    return Linter(graph(PREFIXES + "ex:a a owl:Class .")).rule_context


def test_without_severity_the_finding_has_the_registered_one() -> None:
    ctx = _context()
    ctx.add(RULE, "https://example.test/a", "plain.", subject=())
    assert [f.severity for f in ctx.findings] == [DEFAULT]


def test_with_severity_the_finding_reports_it_and_nothing_else_changes() -> None:
    ctx = _context()
    ctx.add(RULE, "https://example.test/a", "plain.", confidence="certain", subject=("x",))
    ctx.add(RULE, "https://example.test/a", "lower.", confidence="certain", subject=("x",), severity=OTHER)
    plain, lower = ctx.findings
    assert (plain.severity, lower.severity) == (DEFAULT, OTHER)
    assert replace(lower, severity=DEFAULT, message=plain.message) == plain


@pytest.mark.parametrize("bad", ["fatal", "ERROR", "", "Warning"])
def test_an_unknown_severity_is_refused_and_records_nothing(bad: str) -> None:
    ctx = _context()
    with pytest.raises(ValueError, match="severity must be one of"):
        ctx.add(RULE, "https://example.test/a", "plain.", subject=(), severity=bad)
    assert ctx.findings == []


def test_one_focus_and_message_is_one_finding_the_first_calls() -> None:
    ctx = _context()
    ctx.add(RULE, "https://example.test/a", "same.", subject=("x",), severity="warning")
    ctx.add(RULE, "https://example.test/a", "same.", subject=("x",), severity="info")
    assert [f.severity for f in ctx.findings] == ["warning"]


def _pair() -> tuple[Finding, Finding]:
    ctx = _context()
    ctx.add(RULE, "https://example.test/a", "one.", confidence="certain", subject=("s",))
    ctx.add(RULE, "https://example.test/b", "two.", confidence="certain", subject=("s",), severity=OTHER)
    first, second = ctx.findings
    return first, second


def test_the_identity_and_the_fingerprint_do_not_contain_the_severity() -> None:
    finding, _ = _pair()
    other = replace(finding, severity=OTHER)
    assert identity(finding) == identity(other)
    assert fingerprint(finding) == fingerprint(other)


def _run_report() -> RunReport:
    findings = _pair()
    rules = tuple(spec for spec in RULE_SPECS if spec.rule_id == RULE)
    return RunReport((FileReport("a.ttl", "file:///a.ttl", findings),), rules)


def test_json_carries_each_findings_severity_and_the_rules_default() -> None:
    document: dict[str, Any] = to_json(_run_report())
    assert [f["severity"] for f in document["findings"]] == [DEFAULT, OTHER]
    assert document["summary"] == {DEFAULT: 1, OTHER: 1}
    (rule,) = [r for r in document["rules"] if r["id"] == RULE]
    assert (rule["severity"], rule["default_severity"]) == (DEFAULT, DEFAULT)


def test_sarif_carries_each_findings_level_and_the_rules_default_level() -> None:
    sarif = to_sarif_report(_run_report())
    run = sarif["runs"][0]
    assert [r["level"] for r in run["results"]] == ["error", "note"]
    (rule,) = [r for r in run["tool"]["driver"]["rules"] if r["id"] == RULE]
    assert rule["defaultConfiguration"]["level"] == "error"
    json.dumps(sarif)


@pytest.mark.parametrize(("fail_on", "expected"), [("error", 1), ("warning", 1), ("info", 1), ("never", 0)])
def test_fail_on_follows_the_findings(fail_on: str, expected: int) -> None:
    assert exit_code(_pair(), fail_on) == expected


def test_a_rule_whose_findings_are_all_lower_does_not_fail_a_stricter_gate() -> None:
    _, lower = _pair()
    assert exit_code((lower,), "error") == 0
    assert exit_code((lower,), "info") == 1
