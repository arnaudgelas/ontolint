"""Integrity tests for the implementation and planning rule catalogue."""

from __future__ import annotations

import csv
from pathlib import Path
from types import SimpleNamespace

import pytest

from ontolint.ontolint import SEVERITY, _robot_profile_issues

ROBOT_REPORT = (
    "OWL 2 DL Profile Report: Ontology and imports closure NOT in profile. The following violations are present:\n"
    "Use of undeclared class: <http://e/C> [SubClassOf(<http://e/A> <http://e/C>)]"
)

CATALOGUE = Path(__file__).parents[1] / "data" / "rule_catalogue.csv"
CATALOGUE_RULE_COUNT = 304


def test_catalogue_covers_all_registered_rules_and_has_unique_identifiers() -> None:
    """Keep the machine-readable roadmap aligned with executable diagnostics."""
    with CATALOGUE.open(encoding="utf-8", newline="") as file:
        rules = list(csv.DictReader(file))

    identifiers = [rule["rule_id"] for rule in rules]
    implemented = {rule["rule_id"] for rule in rules if rule["status"] == "implemented"}
    assert len(rules) == CATALOGUE_RULE_COUNT
    assert len(identifiers) == len(set(identifiers))
    assert implemented == set(SEVERITY)
    assert all(rule["backend"] and rule["test_requirement"] for rule in rules)


def test_robot_adapter_uses_an_isolated_container_and_translates_violations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Python adapter owns command construction and converts ROBOT output."""
    ontology = tmp_path / "example.owl"
    ontology.write_text("<rdf:RDF/>", encoding="utf-8")

    def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        output_mount = next(value for value in command if value.endswith(":/output"))
        Path(output_mount.removesuffix(":/output"), "profile.txt").write_text(ROBOT_REPORT, encoding="utf-8")
        assert "--network" in command and command[command.index("--network") + 1] == "none"
        assert "--cap-drop" in command and "ALL" in command
        assert "--security-opt" in command and "no-new-privileges" in command
        assert "validate-profile" in command
        return SimpleNamespace(returncode=1, stderr="", stdout="")

    monkeypatch.setattr("ontolint.ontolint.subprocess.run", fake_run)

    findings = _robot_profile_issues(ontology, "DL", "ontolint-robot:1.9.11", 30)

    assert [(finding.rule, finding.severity, finding.confidence) for finding in findings] == [
        ("SEM001", "error", "certain")
    ]
    assert "Use of undeclared class: http://e/C (1)" in findings[0].message
