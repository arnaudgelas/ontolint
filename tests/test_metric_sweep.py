"""The limit sweep and the false-positive calculator (scripts/metric_sweep.py, docs/validation/metric-sweep.md).

Offline: a synthetic set of values and labels, and the recorded results for the committed page.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("metric_sweep", ROOT / "scripts" / "metric_sweep.py")
assert spec is not None
assert spec.loader is not None
metric_sweep = importlib.util.module_from_spec(spec)
sys.modules["metric_sweep"] = metric_sweep
spec.loader.exec_module(metric_sweep)
corpus = metric_sweep.corpus

F = Fraction


def _entries(labels: dict[str, tuple[str, str]]) -> list[Any]:
    return [
        corpus.Entry(name, "", "", {"*": {"expect": expect, "basis": basis, "why": "x"}})
        for name, (expect, basis) in labels.items()
    ]


# A rule that fires above its limit: 0.1 and 0.3 are silent (the second only presumed), 0.6 and 0.9 are fire, and
# one labelled file has no value at all.
VALUES = {"a": F(1, 10), "b": F(3, 10), "c": F(6, 10), "d": F(9, 10)}
LABELS = {
    "a": ("silent", "checked"),
    "b": ("silent", "presumed"),
    "c": ("fire", "checked"),
    "d": ("fire", "checked"),
    "gated": ("fire", "checked"),
}


def _recorded() -> tuple[list[Any], dict[str, Any]]:
    return corpus.load_manifest(), json.loads(corpus.RESULTS.read_text(encoding="utf-8"))


def test_a_sweep_evaluates_each_observed_value_and_the_default() -> None:
    cells = metric_sweep.sweep(_entries(LABELS), "METRIC001", VALUES, F(1, 2), checked_only=False)
    assert [c.limit for c in cells] == [F(1, 10), F(3, 10), F(1, 2), F(6, 10), F(9, 10)]
    assert [c.flagged for c in cells] == [3, 2, 2, 1, 0]


def test_the_comparison_is_strict_and_a_lower_limit_fires_below() -> None:
    assert not metric_sweep.fires("METRIC001", F(1, 2), F(1, 2))
    assert metric_sweep.fires("METRIC001", F(51, 100), F(1, 2))
    assert not metric_sweep.fires("METRIC009", F(1, 2), F(1, 2))
    assert metric_sweep.fires("METRIC009", F(49, 100), F(1, 2))


def test_the_confusion_counts_follow_the_labels_and_skip_what_has_no_value() -> None:
    entries = _entries(LABELS)
    at_default = metric_sweep.cell(entries, "METRIC001", VALUES, F(1, 2), checked_only=False)
    assert (at_default.tp, at_default.fp, at_default.fn, at_default.tn) == (2, 0, 0, 2)  # "gated" has no value
    low = metric_sweep.cell(entries, "METRIC001", VALUES, F(1, 5), checked_only=False)
    assert (low.fp, low.fn, low.errors) == (1, 0, 1)  # b, silent, is flagged
    high = metric_sweep.cell(entries, "METRIC001", VALUES, F(3, 4), checked_only=False)
    assert (high.fp, high.fn) == (0, 1)  # c, fire, is missed
    checked = metric_sweep.cell(entries, "METRIC001", VALUES, F(1, 5), checked_only=True)
    assert (checked.fp, checked.tn) == (0, 1)  # the presumed silent label is ignored


def test_unknown_and_unassessed_labels_are_never_counted() -> None:
    labels = {"a": ("unknown", "checked"), "b": ("unassessed", "none"), "c": ("fire", "checked")}
    c = metric_sweep.cell(_entries(labels), "METRIC001", VALUES, F(0), checked_only=False)
    assert (c.tp, c.fp, c.fn, c.tn) == (1, 0, 0, 0)
    assert c.flagged == len(VALUES)  # flagged counts every file with a value, labelled or not


def test_the_recommendation_is_the_fewest_errors_nearest_the_default() -> None:
    entries = _entries(LABELS)
    cells = metric_sweep.sweep(entries, "METRIC001", VALUES, F(1, 2), checked_only=False)
    assert metric_sweep.recommend(cells, F(1, 2)) == (F(1, 2), "the default is among the best (0 errors)")
    moved = metric_sweep.sweep(entries, "METRIC001", VALUES, F(9, 10), checked_only=False)
    assert metric_sweep.recommend(moved, F(9, 10)) == (F(3, 10), "0 errors against 2 at the default")


def test_a_recommendation_needs_a_label_on_each_side() -> None:
    only_silent = _entries({"a": ("silent", "checked"), "c": ("silent", "checked")})
    cells = metric_sweep.sweep(only_silent, "METRIC001", VALUES, F(1, 2), checked_only=False)
    assert metric_sweep.recommend(cells, F(1, 2)) == (None, "no label expects a fire: recall is not measured")
    only_fire = _entries({"c": ("fire", "checked"), "d": ("fire", "checked")})
    cells = metric_sweep.sweep(only_fire, "METRIC001", VALUES, F(1, 2), checked_only=False)
    assert metric_sweep.recommend(cells, F(1, 2)) == (None, "no label expects a silence: precision is not measured")


def test_a_lower_limit_rule_is_swept_the_other_way() -> None:
    values = {"a": F(1, 10), "b": F(9, 10)}
    entries = _entries({"a": ("fire", "checked"), "b": ("silent", "checked")})
    cells = metric_sweep.sweep(entries, "METRIC009", values, F(1, 2), checked_only=False)
    assert {c.limit: (c.flagged, c.fp, c.fn) for c in cells} == {
        F(1, 10): (0, 0, 1),
        F(1, 2): (1, 0, 0),
        F(9, 10): (1, 0, 0),
    }


def test_the_sweep_text_collapses_rows_that_change_nothing() -> None:
    entries = _entries(LABELS)
    assert "No file makes a comparison" in metric_sweep.render_sweep(entries, {"vectors": {}}, labelled=False)
    values = {"a": F(1, 10), "b": F(1, 10), "c": F(9, 10)}
    cells = metric_sweep.sweep(entries, "METRIC001", values, F(1, 2), checked_only=False)
    kept = metric_sweep._collapse(cells, F(1, 2))
    assert [c.limit for c in kept] == [F(1, 10), F(1, 2), F(9, 10)]  # the default stays, though its row repeats


SHEET_HEAD = ",".join(metric_sweep.SHEET_COLUMNS)


def test_a_filled_sheet_replaces_exactly_the_labels_it_fills() -> None:
    entries = _entries(LABELS)
    sheet = (
        f"{SHEET_HEAD}\n"
        "b,METRIC001,0.3,false,silent,presumed,fire,checked,seen poor\n"
        "c,METRIC001,0.6,true,fire,checked,,,\n"
    )
    updated = metric_sweep.apply_sheet(entries, sheet)
    assert updated[1].label("METRIC001") == {"expect": "fire", "basis": "checked", "why": "seen poor"}
    assert updated[1].label("METRIC002") == entries[1].label("METRIC002")  # other rules keep the '*' label
    assert updated[2].labels == entries[2].labels  # a blank row changes nothing


@pytest.mark.parametrize(
    "row",
    [
        "zzz,METRIC001,,,,,fire,checked,x",  # unknown file
        "b,METRIC099,,,,,fire,checked,x",  # unknown rule
        "b,METRIC001,,,,,maybe,checked,x",  # not an expectation
        "b,METRIC001,,,,,fire,presumed,x",  # a positive must be checked
        "b,METRIC001,,,,,fire,checked,",  # no reason
    ],
)
def test_a_bad_sheet_row_is_refused(row: str) -> None:
    with pytest.raises(ValueError, match=r"."):
        metric_sweep.apply_sheet(_entries(LABELS), f"{SHEET_HEAD}\n{row}\n")


def test_the_label_sheet_is_deterministic_and_has_blank_maintainer_columns() -> None:
    entries, results = _recorded()
    sheet = metric_sweep.labels_sheet(entries, results)
    assert sheet == metric_sweep.labels_sheet(list(reversed(entries)), results)
    rows = sheet.splitlines()
    assert rows[0] == SHEET_HEAD
    assert len(rows) == 1 + len(entries) * len(corpus.RULES)
    assert all(row.endswith(",,,") for row in rows[1:])
    # An untouched sheet applies as a no-op.
    assert [e.labels for e in metric_sweep.apply_sheet(entries, sheet)] == [e.labels for e in entries]


def test_the_committed_sweep_page_is_what_the_script_generates() -> None:
    entries, results = _recorded()
    page = ROOT / "docs" / "validation" / "metric-sweep.md"
    expected = metric_sweep.render_page(entries, results).strip("\n")
    assert corpus.generated_part(page, *metric_sweep.SWEEP_MARKERS) == expected


def test_the_sweep_flags_at_the_default_what_the_recorded_run_flagged() -> None:
    entries, results = _recorded()
    limits = corpus.default_limits()
    for rule in corpus.RULES:
        values = corpus.values_of(rule, results)
        cells = metric_sweep.sweep(entries, rule, values, limits[rule], checked_only=False)
        flagged = next(c.flagged for c in cells if c.limit == limits[rule])
        assert flagged == sum(results["results"][e.id][rule]["fires"] for e in entries)
