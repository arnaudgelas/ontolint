"""``--write-quality-snapshot``, ``--quality-baseline`` and ``--compare-quality`` (``docs/quality.md``).

The two uses of the snapshot are one comparison: a committed baseline is the old side of a run, a trend is two
files.  New output is opt-in: without the flags, a run's report is what it was.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ontolint import main
from ontolint.quality import SnapshotError, dumps, loads

FIXTURES = Path(__file__).parent / "fixtures"
BEFORE, AFTER = str(FIXTURES / "quality" / "before.ttl"), str(FIXTURES / "quality" / "after.ttl")
KITCHEN = str(FIXTURES / "kitchen_sink.ttl")
Q = "https://example.test/q#"
USAGE, TOOL_FAILURE = 2, 2
COVERAGE = "class_definition_coverage"
FIXTURE_SPLIT = {"regressed": 1, "diluted": 3, "removed": 2, "improved": 1, "added_good": 0}

Run = Any


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Run:
    def _run(*argv: str) -> tuple[int, str, str]:
        code = main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return _run


@pytest.fixture
def snapshots(run: Run, tmp_path: Path) -> tuple[Path, Path]:
    """The snapshots of the fixture pair, written by the CLI."""
    old, new = tmp_path / "old.json", tmp_path / "new.json"
    assert run(BEFORE, "--write-quality-snapshot", str(old))[0] == 0
    assert run(AFTER, "--write-quality-snapshot", str(new))[0] == 0
    return old, new


def result(report: dict[str, Any], measurement_id: str) -> dict[str, Any]:
    return next(m for m in report["measurements"] if m["id"] == measurement_id)  # type: ignore[no-any-return]


# --- --write-quality-snapshot ----------------------------------------------------------------------------------


def test_a_run_writes_its_snapshot_and_a_snapshot_round_trips(snapshots: tuple[Path, Path]) -> None:
    old, _ = snapshots
    text = old.read_text(encoding="utf-8")
    snapshot = loads(text)
    assert dumps(snapshot) == text
    defined = next(e for e in snapshot.entries if e.measurement.id == COVERAGE)
    assert defined.coverage is not None
    assert defined.coverage.numerator == tuple(f"{Q}{n}" for n in "ABC")
    assert defined.coverage.denominator == tuple(f"{Q}{n}" for n in "ABCDE")


def test_the_snapshot_does_not_change_the_report_or_the_exit_code(run: Run, tmp_path: Path) -> None:
    plain = run(KITCHEN, "--format", "json")
    with_snapshot = run(KITCHEN, "--format", "json", "--write-quality-snapshot", str(tmp_path / "s.json"))
    assert with_snapshot == plain


def test_the_snapshot_is_written_whatever_the_exit_code(run: Run, tmp_path: Path) -> None:
    target = tmp_path / "s.json"
    code = run(KITCHEN, "--write-quality-snapshot", str(target))[0]
    assert code == 1 and loads(target.read_text(encoding="utf-8"))


def test_the_snapshot_is_the_same_file_whichever_format_the_run_reports(run: Run, tmp_path: Path) -> None:
    texts = []
    for fmt in ("text", "json", "sarif", "markdown"):
        target = tmp_path / f"{fmt}.json"
        run(BEFORE, "--format", fmt, "--write-quality-snapshot", str(target))
        texts.append(target.read_text(encoding="utf-8"))
    assert len(set(texts)) == 1


def test_a_snapshot_is_of_one_file(run: Run, tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exit_:
        run(BEFORE, AFTER, "--write-quality-snapshot", str(tmp_path / "s.json"))
    assert exit_.value.code == USAGE
    assert not (tmp_path / "s.json").exists()


def test_the_snapshot_follows_the_policy_options(run: Run, tmp_path: Path) -> None:
    target = tmp_path / "s.json"
    run(BEFORE, "--base", "https://example.test/q#", "--write-quality-snapshot", str(target))
    assert json.loads(target.read_text(encoding="utf-8"))["policy"]["base"] == "https://example.test/q#"


def test_a_snapshot_that_cannot_be_written_is_a_tool_failure(run: Run, tmp_path: Path) -> None:
    code, _out, err = run(BEFORE, "--write-quality-snapshot", str(tmp_path / "missing" / "s.json"))
    assert code == TOOL_FAILURE and err.startswith("TOOL001: quality snapshot output failed")


# --- --compare-quality ------------------------------------------------------------------------------------------


def test_a_fixture_pair_with_a_regression_a_dilution_and_a_removal_is_classified(
    run: Run, snapshots: tuple[Path, Path]
) -> None:
    code, out, err = run("--compare-quality", *map(str, snapshots), "--format", "json")
    assert (code, err) == (0, "")
    report = json.loads(out)
    assert report["format"] == "ontolint-quality-comparison" and report["version"] == 1
    m = result(report, COVERAGE)
    assert m["status"] == "compared"
    assert {k: m["coverage"][k] for k in FIXTURE_SPLIT} == FIXTURE_SPLIT
    assert m["coverage"]["terms"] == {
        "regressed": [Q + "B"],
        "diluted": [Q + n for n in "FGH"],
        "removed": [Q + "C", Q + "E"],
        "improved": [Q + "D"],
        "added_good": [],
    }
    assert (m["before"], m["after"], m["delta"]) == (
        {"numerator": 3, "denominator": 5},
        {"numerator": 2, "denominator": 6},
        "-0.2667",
    )


def test_a_snapshot_compared_with_itself_changes_nothing(run: Run, snapshots: tuple[Path, Path]) -> None:
    old, _ = snapshots
    report = json.loads(run("--compare-quality", str(old), str(old), "--format", "json")[1])
    for m in report["measurements"]:
        if m["id"] == "shacl_class_target_coverage":  # not taken, by either snapshot: nothing to compare
            assert m["status"] == "not_comparable"
            continue
        assert m["status"] == "compared", m
        if "coverage" in m:
            assert not any(m["coverage"][k] for k in FIXTURE_SPLIT)
        if m["kind"] != "histogram":
            assert m["delta"] in ("0.0000", 0, None)


def test_the_text_report_says_the_split_and_the_rename_limit(run: Run, snapshots: tuple[Path, Path]) -> None:
    code, out, _err = run("--compare-quality", *map(str, snapshots))
    assert code == 0
    assert (
        f"{COVERAGE}: 3/5 -> 2/6 (delta -0.2667)\n  regressed 1, diluted 3, removed 2, improved 1, added good 0\n"
        in out
    )
    assert "renamed term counts as one removal and one new term" in out
    assert out.startswith("16 measurement(s): 15 compared, 1 not comparable")


def test_the_markdown_report_shows_the_split(run: Run, snapshots: tuple[Path, Path]) -> None:
    code, out, _err = run("--compare-quality", *map(str, snapshots), "--format", "markdown")
    assert code == 0
    assert "### Quality comparison" in out
    assert (
        "- ` class_definition_coverage `: 3/5 -> 2/6, delta -0.2667; regressed 1, diluted 3, removed 2, improved 1, "
        "new and fine 0" in out
    )
    assert "- ` shacl_class_target_coverage `: not comparable: ` not taken in the old snapshot: no SHACL" in out


def test_an_incompatible_pair_is_refused_measurement_by_measurement(
    run: Run, snapshots: tuple[Path, Path], tmp_path: Path
) -> None:
    old, new = snapshots
    document = json.loads(new.read_text(encoding="utf-8"))
    bumped = next(m for m in document["measurements"] if m["id"] == COVERAGE)
    bumped["definition_version"] = 2
    other = next(m for m in document["measurements"] if m["id"] == "class_label_coverage")
    other["population"] = "owned_things"
    edited = tmp_path / "edited.json"
    edited.write_text(json.dumps(document), encoding="utf-8")
    code, out, _err = run("--compare-quality", str(old), str(edited), "--format", "json")
    assert code == 0
    report = json.loads(out)
    assert result(report, COVERAGE) == {
        "id": COVERAGE,
        "status": "not_comparable",
        "reasons": ["definition version 1 -> 2"],
    }
    assert result(report, "class_label_coverage")["reasons"] == ["population owned_classes -> owned_things"]
    others = [m for m in report["measurements"] if m["id"] not in (COVERAGE, "class_label_coverage")]
    assert all(m["status"] == "compared" for m in others if m["id"] != "shacl_class_target_coverage")


def test_a_different_policy_refuses_every_measurement(run: Run, tmp_path: Path) -> None:
    old, new = tmp_path / "old.json", tmp_path / "new.json"
    run(BEFORE, "--write-quality-snapshot", str(old))
    run(BEFORE, "--base", "https://example.test/q#", "--write-quality-snapshot", str(new))
    report = json.loads(run("--compare-quality", str(old), str(new), "--format", "json")[1])
    assert {m["status"] for m in report["measurements"]} == {"not_comparable"}
    assert all("policy differs: base" in m["reasons"] for m in report["measurements"])


def test_the_comparison_goes_to_output_when_asked(run: Run, snapshots: tuple[Path, Path], tmp_path: Path) -> None:
    target = tmp_path / "trend.json"
    code, out, _err = run("--compare-quality", *map(str, snapshots), "--format", "json", "--output", str(target))
    assert code == 0 and out == ""
    assert json.loads(target.read_text(encoding="utf-8"))["format"] == "ontolint-quality-comparison"


@pytest.mark.parametrize(
    "argv",
    [
        ("--compare-quality", "only-one.json"),
        ("--compare-quality", "a.json", "b.json", BEFORE),
        ("--compare-quality", "a.json", "b.json", "--format", "sarif"),
        ("--compare-quality", "a.json", "b.json", "--write-quality-snapshot", "s.json"),
        ("--compare-quality", "a.json", "b.json", "--quality-baseline", "c.json"),
    ],
)
def test_a_trend_takes_two_snapshots_and_nothing_to_lint(run: Run, argv: tuple[str, ...]) -> None:
    with pytest.raises(SystemExit) as exit_:
        run(*argv)
    assert exit_.value.code == USAGE


def test_an_unusable_snapshot_is_a_tool_failure_that_names_the_file(
    run: Run, snapshots: tuple[Path, Path], tmp_path: Path
) -> None:
    old, _ = snapshots
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    code, out, err = run("--compare-quality", str(old), str(broken))
    assert (code, out) == (TOOL_FAILURE, "")
    assert err.startswith(f"TOOL001: quality snapshot {broken} cannot be used: not JSON")
    code, _out, err = run("--compare-quality", str(tmp_path / "gone.json"), str(old))
    assert code == TOOL_FAILURE and "gone.json cannot be used" in err


def test_a_snapshot_of_a_later_version_is_refused_with_its_version(
    run: Run, snapshots: tuple[Path, Path], tmp_path: Path
) -> None:
    later = tmp_path / "later.json"
    later.write_text(
        json.dumps({**json.loads(snapshots[0].read_text(encoding="utf-8")), "version": 2}), encoding="utf-8"
    )
    code, _out, err = run("--compare-quality", str(later), str(snapshots[0]))
    assert code == TOOL_FAILURE and "snapshot version 2 is not supported (this ontolint reads version 1)" in err


def test_a_snapshot_that_is_not_utf_8_is_refused_and_not_a_crash(run: Run, tmp_path: Path) -> None:
    binary = tmp_path / "binary.json"
    binary.write_bytes(b"\xff\xfe\x00")
    code, _out, err = run("--compare-quality", str(binary), str(binary))
    assert code == TOOL_FAILURE and "cannot be used" in err


# --- --quality-baseline -----------------------------------------------------------------------------------------


def test_a_run_is_compared_with_the_committed_baseline_in_json(run: Run, snapshots: tuple[Path, Path]) -> None:
    old, _ = snapshots
    code, out, _err = run(AFTER, "--format", "json", "--quality-baseline", str(old))
    report = json.loads(out)
    assert code == run(AFTER, "--format", "json")[0]
    comparison = report.pop("quality_comparison")
    assert {k: result(comparison, COVERAGE)["coverage"][k] for k in FIXTURE_SPLIT} == FIXTURE_SPLIT
    assert report == json.loads(run(AFTER, "--format", "json")[1])  # nothing else moved


def test_the_run_against_a_baseline_equals_the_trend_of_its_snapshot(run: Run, snapshots: tuple[Path, Path]) -> None:
    old, new = snapshots
    trend = json.loads(run("--compare-quality", str(old), str(new), "--format", "json")[1])
    assert json.loads(run(AFTER, "--format", "json", "--quality-baseline", str(old))[1])["quality_comparison"] == trend


def test_the_markdown_summary_shows_the_split_against_the_baseline(run: Run, snapshots: tuple[Path, Path]) -> None:
    old, _ = snapshots
    code, out, _err = run(AFTER, "--format", "markdown", "--quality-baseline", str(old))
    assert code == 0
    assert "### Quality against the baseline" in out
    assert "- ` class_definition_coverage `: 3/5 -> 2/6, delta -0.2667; regressed 1, diluted 3, removed 2" in out


def test_a_run_without_the_flag_has_no_quality_section(run: Run) -> None:
    assert "quality" not in run(AFTER, "--format", "markdown")[1].lower()
    assert "quality_comparison" not in json.loads(run(AFTER, "--format", "json")[1])


def test_the_comparison_never_changes_the_exit_code(run: Run, snapshots: tuple[Path, Path]) -> None:
    old, _ = snapshots
    plain = run(AFTER, "--format", "json")[0]
    assert run(AFTER, "--format", "json", "--quality-baseline", str(old))[0] == plain
    assert run(AFTER, "--format", "json", "--quality-baseline", str(old), "--fail-on", "never")[0] == 0


@pytest.mark.parametrize("fmt", ["text", "sarif"])
def test_a_quality_baseline_needs_a_format_that_can_show_it(run: Run, snapshots: tuple[Path, Path], fmt: str) -> None:
    with pytest.raises(SystemExit) as exit_:
        run(AFTER, "--format", fmt, "--quality-baseline", str(snapshots[0]))
    assert exit_.value.code == USAGE


def test_a_baseline_is_for_one_file(run: Run, snapshots: tuple[Path, Path]) -> None:
    with pytest.raises(SystemExit) as exit_:
        run(BEFORE, AFTER, "--format", "json", "--quality-baseline", str(snapshots[0]))
    assert exit_.value.code == USAGE


def test_an_unusable_quality_baseline_fails_before_the_ontology_is_read(run: Run, tmp_path: Path) -> None:
    code, out, err = run(AFTER, "--format", "json", "--quality-baseline", str(tmp_path / "gone.json"))
    assert code == TOOL_FAILURE and out == "" and "gone.json cannot be used" in err


def test_the_two_flags_work_together(run: Run, snapshots: tuple[Path, Path], tmp_path: Path) -> None:
    target = tmp_path / "again.json"
    code, out, _err = run(
        AFTER, "--format", "json", "--quality-baseline", str(snapshots[0]), "--write-quality-snapshot", str(target)
    )
    assert code == 0 and "quality_comparison" in json.loads(out)
    assert target.read_text(encoding="utf-8") == snapshots[1].read_text(encoding="utf-8")


def test_the_snapshot_loader_error_is_a_value_error() -> None:
    assert issubclass(SnapshotError, ValueError)
