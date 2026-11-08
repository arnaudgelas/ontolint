"""Validate emitted reports against the vendored OASIS SARIF 2.1 schema."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema.validators import validator_for

from ontolint.models import Finding
from ontolint.reporting import FileReport, Location, RunReport, to_sarif_report

SCHEMA = Path(__file__).parent / "schemas" / "sarif-schema-2.1.0.json"


def test_sarif_matches_the_official_21_schema() -> None:
    finding = Finding("ONT001", "warning", "https://example.test/A", "Missing label.", "Add a label.")
    report = RunReport((FileReport("ontology.ttl", "ontology.ttl", (finding,), locations={finding: Location(2, 1)}),))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = validator_for(schema)
    validator.check_schema(schema)
    validator(schema).validate(to_sarif_report(report))
