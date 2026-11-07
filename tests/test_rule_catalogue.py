"""Integrity tests for the implementation and planning rule catalogue."""

from __future__ import annotations

import csv
from pathlib import Path

from ontolint.ontolint import SEVERITY

CATALOGUE = Path(__file__).parents[1] / "data" / "rule_catalogue.csv"
CATALOGUE_RULE_COUNT = 329


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
