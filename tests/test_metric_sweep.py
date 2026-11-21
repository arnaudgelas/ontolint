"""The limit sweep and the false-positive calculator (scripts/metric_sweep.py, docs/validation/metric-sweep.md).

Offline: a synthetic set of values and labels, and the recorded results for the committed page.
"""

from __future__ import annotations

import importlib.util
import json
import re
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


def _candidates() -> dict[str, Any]:
    return json.loads(metric_sweep.CANDIDATES.read_text(encoding="utf-8"))


def test_every_candidate_is_pinned_licensed_and_unlabelled() -> None:
    entries = corpus.load_manifest(metric_sweep.CANDIDATES)  # refuses an unpinned or unlicensed entry
    assert {e.id for e in entries} == {item["id"] for item in _candidates()["entries"]}
    for entry in entries:
        assert all(entry.label(rule)["expect"] == "unassessed" for rule in corpus.RULES)  # the label column is blank
    for item in _candidates()["entries"]:
        assert item["licence_source"].strip()
        assert set(item["suggested"]) == {"*"}  # a suggestion, kept apart from the labels
        assert item["suggested"]["*"]["source"].startswith("http")


def test_no_candidate_is_pinned_by_a_document_that_can_change() -> None:
    """Issue #152: a candidate comes from a commit of its repository or an Internet Archive snapshot, never live."""
    archive = re.compile(r"https://web\.archive\.org/web/\d{14}id_/https?://\S+")
    for item in _candidates()["entries"]:
        by_commit = item["commit"] is not None and f"/{item['commit']}/" in item["url"]
        assert by_commit or archive.fullmatch(item["url"]), item["id"]


def test_the_candidate_results_and_page_match_the_manifest() -> None:
    entries = corpus.load_manifest(metric_sweep.CANDIDATES)
    results = json.loads(metric_sweep.CANDIDATE_RESULTS.read_text(encoding="utf-8"))
    assert set(results["results"]) == {e.id for e in entries} == set(results["vectors"])
    shown = corpus.generated_part(metric_sweep.CANDIDATE_PAGE, *metric_sweep.CANDIDATE_MARKERS)
    assert shown == metric_sweep.render_candidates(entries, results).strip("\n")


def test_a_candidate_table_marks_the_flagged_and_the_empty() -> None:
    entries = _entries({"a": ("unassessed", "none")})
    vector = {
        name: {"definition_version": 1, "numerator": 0, "denominator": 20}
        for name in {r.measurement for r in corpus.READINGS.values()}
        | {r.gate for r in corpus.READINGS.values() if r.gate}
    }
    vector["unresolved_imports"] = {"definition_version": 1, "value": 12}
    vector["class_label_coverage"] = {"definition_version": 1, "numerator": 0, "denominator": 5}  # below the gate
    row = metric_sweep.render_candidates(entries, {"vectors": {"a": vector}}).splitlines()[-1].split("|")
    cells = [c.strip() for c in row[2:-1]]
    assert cells[0] == "-"  # METRIC001: under the sample gate
    assert cells[10] == "12*"  # METRIC011: above 10


# --- the evidence per shipped limit (issue #163) --------------------------------------------------------------------


def test_a_rule_with_no_fire_label_is_unmeasured_and_never_a_zero_rate() -> None:
    item = metric_sweep.Evidence("METRIC001", "metric_max_unlabelled_ratio", F(1, 2), 4, 0, 0, 4, 0, 0, 0, 4)
    assert item.status.startswith("unmeasured: no label expects a fire")
    assert item.recall == "unmeasured"
    assert item.precision == "n/a"
    assert "%" not in f"{item.status}{item.recall}{item.precision}"


def test_a_rule_with_no_silent_label_is_unmeasured_for_precision() -> None:
    item = metric_sweep.Evidence("METRIC001", "metric_max_unlabelled_ratio", F(1, 2), 2, 2, 2, 0, 2, 0, 0, 0)
    assert item.status.startswith("unmeasured: no label expects a silence")
    assert (item.recall, item.precision) == ("2/2", "2/2")


def test_a_rule_with_both_labels_is_measured_and_its_counts_are_fractions_of_counts() -> None:
    item = metric_sweep.Evidence("METRIC001", "metric_max_unlabelled_ratio", F(1, 2), 5, 2, 2, 3, 1, 1, 1, 2)
    assert (item.status, item.recall, item.precision) == ("measured", "1/2", "1/2")


def test_the_evidence_follows_the_recorded_labels_and_values() -> None:
    entries, results = _recorded()
    limits = corpus.default_limits()
    for item in metric_sweep.evidence(entries, results):
        values = corpus.values_of(item.rule, results)
        assert item.compared == len(values) and item.default == limits[item.rule]
        assert item.flagged == sum(metric_sweep.fires(item.rule, v, limits[item.rule]) for v in values.values())
        assert item.tp + item.fn == item.fire_labels and item.fp + item.tn == item.silent_labels
        assert (
            (item.fire_labels == 0) == (item.recall == "unmeasured") == item.status.startswith("unmeasured: no label")
        )


def test_every_rule_has_one_row_of_evidence_in_rule_order() -> None:
    entries, results = _recorded()
    assert [e.rule for e in metric_sweep.evidence(entries, results)] == list(corpus.RULES)


def test_approving_a_fire_label_makes_a_rule_measured() -> None:
    entries, results = _recorded()
    sheet = metric_sweep.labels_sheet(entries, results).splitlines()
    header, *rows = sheet
    columns = header.split(",")
    row = next(r for r in rows if r.startswith(f"{entries[0].id},METRIC004,"))
    fields = row.split(",")
    fields[columns.index("maintainer_expect")] = "fire"
    fields[columns.index("maintainer_basis")] = "checked"
    fields[columns.index("maintainer_reason")] = "flat catalogue"
    filled = "\n".join([header, ",".join(fields)])
    approved = metric_sweep.apply_sheet(entries, filled)
    before = next(e for e in metric_sweep.evidence(entries, results) if e.rule == "METRIC004")
    after = next(e for e in metric_sweep.evidence(approved, results) if e.rule == "METRIC004")
    value_known = entries[0].id in corpus.values_of("METRIC004", results)
    assert before.status.startswith("unmeasured")
    assert (after.fire_labels - before.fire_labels) == int(value_known)


def test_the_sweep_the_calibration_and_the_sheet_are_byte_identical_between_two_runs(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The calibration is deterministic: nothing depends on the clock, a hash seed or an iteration order."""
    for command in ("sweep", "calibrate", "labels-sheet"):
        outputs = []
        for _ in range(2):
            assert metric_sweep.main([command]) == 0
            outputs.append(capsys.readouterr().out)
        assert outputs[0] == outputs[1] and outputs[0], command
    entries, results = _recorded()
    assert metric_sweep.render_evidence(entries, results) == metric_sweep.render_evidence(entries, results)


def test_the_committed_evidence_table_is_what_the_script_generates() -> None:
    entries, results = _recorded()
    generated = corpus.generated_part(metric_sweep.THRESHOLDS_PAGE, *metric_sweep.EVIDENCE_MARKERS)
    assert generated == metric_sweep.render_evidence(entries, results).strip("\n")
