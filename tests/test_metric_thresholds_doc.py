"""docs/metric-thresholds.md lists every METRIC policy key with the default the Policy has."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ontolint.policy import METRIC_FIELDS, Policy
from ontolint.rules import metrics
from ontolint.rules.bounds import BUILT_IN

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


# --- every threshold has a rationale, evidence and an override (issue #163) -----------------------------------

MIN_RATIONALE = 40  # characters: a sentence, not a placeholder
ROW_CELLS = re.compile(r"^\| `(metric_\w+)` \|(.*)\|$", re.MULTILINE)
EVIDENCE_ROW = re.compile(
    r"^\| (METRIC\d{3}) \| `(metric_\w+)` \| \S+ \| (\d+) \| (\d+) \| (\d+) \| (\d+) \|.*\| (.+) \|$", re.MULTILINE
)


def _thresholds() -> dict[str, list[str]]:
    """The cells of each row of the Thresholds table after the key: rules, default, fires when, gate, why, notes."""
    table = PAGE.read_text(encoding="utf-8").split("## Thresholds")[1].split("## Evidence per threshold")[0]
    return {key: [c.strip() for c in rest.split(" | ")] for key, rest in ROW_CELLS.findall(table)}


def _evidence() -> dict[str, tuple[int, int, int, int, str]]:
    """The generated evidence rows by key: compared, flagged, fire labels, silent labels, status."""
    text = PAGE.read_text(encoding="utf-8").split("## Evidence per threshold")[1].split("## Measurements")[0]
    return {
        key: (int(compared), int(flagged), int(fire), int(silent), status)
        for _, key, compared, flagged, fire, silent, status in EVIDENCE_ROW.findall(text)
    }


@pytest.mark.parametrize("built_in", BUILT_IN, ids=lambda b: b.key)
def test_every_built_in_threshold_has_a_rationale_corpus_evidence_and_its_override_key(built_in: object) -> None:
    key = built_in.key  # type: ignore[attr-defined]
    cells = _thresholds()[key]
    rationale, notes = cells[-2], cells[-1]
    assert len(rationale) > MIN_RATIONALE, f"{key}: no rationale"
    assert notes, f"{key}: no corpus notes"
    compared, flagged, fire, silent, status = _evidence()[key]
    assert compared >= flagged and fire + silent <= compared, key
    assert status == "measured" or status.startswith("unmeasured: no label expects a"), key
    # The override key is the key itself: it is a METRIC policy field, validated and documented under "Overriding".
    assert key in METRIC_FIELDS


def test_the_corpus_notes_count_the_files_the_generated_table_flags() -> None:
    """The hand-written ``N fire`` of a row cannot drift from the recorded measurements."""
    evidence = _evidence()
    for key, cells in _thresholds().items():
        if key == "metric_min_sample":
            continue
        match = re.match(r"(\d+) fires?\b", cells[-1])
        assert match is not None, f"{key}: the corpus notes start with the number of files flagged"
        assert int(match.group(1)) == evidence[key][1], key


def test_a_rule_with_no_fire_label_says_unmeasured_and_no_row_claims_a_zero_rate() -> None:
    text = PAGE.read_text(encoding="utf-8")
    for key, (_, _, fire, _, status) in _evidence().items():
        assert (fire == 0) == status.startswith("unmeasured: no label expects a fire"), key
    assert not re.search(r"\b0\s?% false", text)
