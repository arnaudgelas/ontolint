"""The severity and confidence decisions of issue #63 (``docs/severity-decisions.md``), pinned one row at a time.

Every row of ``DECISIONS`` is a rule, the severity and the finding confidence that the decision record chose, and a
fixture with exactly one finding of that rule.  A corpus cannot discriminate these changes (the one file that carries
the findings already fails for another reason), so each row is tested on its own fixture:

* the registered severity and the confidence of the finding are the decided ones;
* ``--fail-on`` decides the exit code from that severity (an error fails ``--fail-on error``, a warning only
  ``--fail-on warning``);
* ``severity_overrides`` restores the old severity, so the escape hatch that the upgrade notes promise works;
* the baseline identity does not contain the severity: a baseline written while the rule had its old severity still
  matches.

Rows of the other families are added by the pull requests that ship their decisions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple

import pytest

from ontolint.cli import main
from ontolint.rules.specs import RULE_SPECS

PREFIXES = (
    "@prefix ex: <https://example.test/> .\n"
    "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
    "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n"
)


class Decision(NamedTuple):
    """One decided row: the severity and confidence now, the severity before, and a one-finding fixture."""

    rule: str
    severity: str
    confidence: str
    old_severity: str
    body: str


DECISIONS = (
    Decision("OWL009", "error", "certain", "warning", "ex:d a owl:DatatypeProperty, owl:SymmetricProperty ."),
    Decision(
        "OWL010",
        "warning",
        "certain",
        "info",
        "ex:p a owl:ObjectProperty ; owl:propertyChainAxiom ( ex:q ) . ex:q a owl:ObjectProperty .",
    ),
    Decision("OWL013", "error", "certain", "warning", 'ex:o a owl:ObjectProperty . ex:a ex:o "text" .'),
    Decision("OWL014", "error", "certain", "warning", "ex:d a owl:DatatypeProperty . ex:a ex:d ex:b ."),
    Decision(
        "OWL023",
        "warning",
        "certain",
        "warning",
        "ex:p a owl:ObjectProperty ; owl:inverseOf ex:q, ex:r . "
        "ex:q a owl:ObjectProperty . ex:r a owl:ObjectProperty .",
    ),
    Decision(
        "OWL032",
        "warning",
        "certain",
        "info",
        "ex:C a owl:Class ; owl:unionOf ( ex:D ) . ex:D a owl:Class .",
    ),
    Decision("OWL041", "error", "certain", "error", "ex:A a owl:Class ; owl:complementOf ex:A ."),
    Decision("OWL045", "error", "certain", "warning", "[] a owl:AllDifferent ; owl:distinctMembers ( ex:a ) ."),
)

RANK = {"info": 1, "warning": 2, "error": 3}
IDS = [d.rule for d in DECISIONS]


def _source(tmp_path: Path, decision: Decision) -> Path:
    source = tmp_path / f"{decision.rule}.ttl"
    source.write_text(PREFIXES + decision.body + "\n", encoding="utf-8")
    return source


def _run(
    capsys: pytest.CaptureFixture[str], source: Path, rule: str, *extra: str, fail_on: str = "never"
) -> tuple[int, dict[str, object]]:
    code = main([str(source), "--select", rule, "--format", "json", "--fail-on", fail_on, *extra])
    return code, json.loads(capsys.readouterr().out)


def _findings(report: dict[str, object], rule: str) -> list[dict[str, object]]:
    findings = report["findings"]
    assert isinstance(findings, list)
    return [f for f in findings if f["rule"] == rule]


@pytest.mark.parametrize("decision", DECISIONS, ids=IDS)
def test_registered_severity_is_the_decided_one(decision: Decision) -> None:
    spec = next(s for s in RULE_SPECS if s.rule_id == decision.rule)
    assert spec.severity.value == decision.severity


@pytest.mark.parametrize("decision", DECISIONS, ids=IDS)
def test_fixture_has_one_finding_with_the_decided_severity_and_confidence(
    decision: Decision, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, report = _run(capsys, _source(tmp_path, decision), decision.rule)
    (finding,) = _findings(report, decision.rule)
    assert (finding["severity"], finding["confidence"]) == (decision.severity, decision.confidence)


@pytest.mark.parametrize("decision", DECISIONS, ids=IDS)
@pytest.mark.parametrize("fail_on", ["info", "warning", "error"])
def test_fail_on_follows_the_decided_severity(
    decision: Decision, fail_on: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _ = _run(capsys, _source(tmp_path, decision), decision.rule, fail_on=fail_on)
    assert code == (1 if RANK[decision.severity] >= RANK[fail_on] else 0)


@pytest.mark.parametrize("decision", [d for d in DECISIONS if d.old_severity != d.severity], ids=lambda d: d.rule)
def test_severity_overrides_restore_the_old_exit_code(
    decision: Decision, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"severity_overrides": {decision.rule: decision.old_severity}}), encoding="utf-8")
    source = _source(tmp_path, decision)
    for fail_on in ("info", "warning", "error"):
        code, report = _run(capsys, source, decision.rule, "--config", str(policy), fail_on=fail_on)
        assert _findings(report, decision.rule)[0]["severity"] == decision.old_severity
        assert code == (1 if RANK[decision.old_severity] >= RANK[fail_on] else 0)


@pytest.mark.parametrize("decision", [d for d in DECISIONS if d.old_severity != d.severity], ids=lambda d: d.rule)
def test_a_baseline_written_with_the_old_severity_still_matches(
    decision: Decision, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Severity is not part of a finding's identity (``RuleContext.add``): this guards that it never becomes one."""
    source = _source(tmp_path, decision)
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"severity_overrides": {decision.rule: decision.old_severity}}), encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    main(
        [str(source), "--select", decision.rule, "--config", str(policy), "--write-baseline", str(baseline)]
        + ["--fail-on", "never", "--output", str(tmp_path / "ignored")]
    )
    capsys.readouterr()
    assert json.loads(baseline.read_text(encoding="utf-8"))["fingerprints"]
    code, report = _run(capsys, source, decision.rule, "--baseline", str(baseline), fail_on="info")
    assert code == 0
    assert _findings(report, decision.rule) == []
