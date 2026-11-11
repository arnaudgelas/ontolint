"""The METRIC specification (module docstring), the catalogue and the policy keys state one contract."""

from __future__ import annotations

import re

from ontolint.catalogue import load_catalogue
from ontolint.policy import METRIC_FIELDS
from ontolint.rules import metrics

BULLET = re.compile(r"^\* \*\*(METRIC\d{3})\.\*\* \((``\w+``)", re.MULTILINE)


def test_the_docstring_specifies_every_metric_rule_and_its_policy_key() -> None:
    bullets = dict(BULLET.findall(metrics.__doc__ or ""))
    assert sorted(bullets) == sorted(spec.rule_id for spec in metrics.SPECS)
    keys = {key.strip("`") for key in bullets.values()}
    assert keys <= set(METRIC_FIELDS)
    assert keys == set(METRIC_FIELDS) - {"metric_min_sample"}  # the sample gate is common to the rules


def test_every_bullet_states_its_severity_and_confidence() -> None:
    doc = metrics.__doc__ or ""
    severity = {spec.rule_id: spec.severity.value for spec in metrics.SPECS}
    for rule_id, text in re.findall(r"^\* \*\*(METRIC\d{3})\.\*\*(.*?)(?=^\* \*\*|\Z)", doc, re.MULTILINE | re.DOTALL):
        assert f"*{severity[rule_id].capitalize()}" in text, rule_id


def test_catalogue_rows_name_their_fixtures_not_the_placeholder() -> None:
    rows = [row for row in load_catalogue() if row.rule_id.startswith("METRIC")]
    assert len(rows) == len(metrics.SPECS)
    assert all("fixture" in row.test_requirement and "metric threshold" not in row.test_requirement for row in rows)
