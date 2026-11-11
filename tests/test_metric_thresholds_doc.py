"""docs/metric-thresholds.md lists every METRIC policy key with the default the Policy has."""

from __future__ import annotations

import re
from pathlib import Path

from ontolint.policy import METRIC_FIELDS, Policy
from ontolint.rules import metrics

PAGE = Path(__file__).resolve().parent.parent / "docs" / "metric-thresholds.md"
ROW = re.compile(r"^\| `(metric_\w+)` \| ([^|]+) \| ([\d.]+) \|", re.MULTILINE)


def test_the_table_matches_the_policy_keys_and_defaults() -> None:
    rows = {key: (rules.strip(), default) for key, rules, default in ROW.findall(PAGE.read_text(encoding="utf-8"))}
    assert set(rows) == set(METRIC_FIELDS)
    for key, (_, default) in rows.items():
        assert float(default) == float(getattr(Policy(), key)), key


def test_every_metric_rule_appears_in_the_table() -> None:
    text = PAGE.read_text(encoding="utf-8")
    table = "\n".join(line for line in text.splitlines() if line.startswith("| `metric_"))
    assert all(spec.rule_id in table for spec in metrics.SPECS)
