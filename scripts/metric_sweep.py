"""Sweep the METRIC limits over the recorded corpus measurements, and count false positives and negatives (issue #8).

    uv run python scripts/metric_sweep.py render           # rewrite the generated part of the sweep page
    uv run python scripts/metric_sweep.py sweep            # print the sweep tables (no labels needed)
    uv run python scripts/metric_sweep.py calibrate        # FP/FN per rule and limit, and the recommended limit
    uv run python scripts/metric_sweep.py labels-sheet > sheet.csv    # a row per (file, rule) to fill in
    uv run python scripts/metric_sweep.py calibrate --labels sheet.csv    # the same, under the filled sheet
    uv run python scripts/metric_sweep.py fetch-candidates DIR     # download the candidate files by pin (network)
    uv run python scripts/metric_sweep.py measure-candidates DIR   # lint them, rewrite the candidate results and page

Nothing here fetches or lints: it reads ``docs/validation/metric-corpus-results.json`` (written by
``scripts/metric_corpus.py measure``) and the labels of ``docs/validation/metric-corpus.json``, so it is
offline, deterministic and exact (fractions, no floating-point comparison).

A rule's value on a file changes the flag only when a limit crosses it, so the sweep evaluates one limit per
observed value, plus the shipped default: between two consecutive observed values the counts do not move.
A rule fires strictly above (or, for METRIC006, METRIC009 and METRIC012, strictly below) its limit.

What this measures is the count of files flagged at each limit, and, under a label sheet, false positives and
negatives *conditioned on those labels*.  It does not measure whether a label is right.  A rule with no label
expecting a fire has no measurable recall: ``recommend`` then says so and proposes no limit, instead of
proposing the one that switches the rule off.  Every number is as good as the labels and no better.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

_spec = importlib.util.spec_from_file_location("metric_corpus", Path(__file__).with_name("metric_corpus.py"))
if _spec is None or _spec.loader is None:
    raise ImportError("scripts/metric_corpus.py cannot be loaded")
corpus = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("metric_corpus", corpus)
_spec.loader.exec_module(corpus)

ROOT: Path = corpus.ROOT
SWEEP_PAGE = ROOT / "docs" / "validation" / "metric-sweep.md"
SWEEP_MARKERS = ("<!-- metric_sweep.py: begin -->", "<!-- metric_sweep.py: end -->")
CANDIDATES = ROOT / "docs" / "validation" / "metric-candidates.json"
CANDIDATE_RESULTS = ROOT / "docs" / "validation" / "metric-candidates-results.json"
CANDIDATE_PAGE = ROOT / "docs" / "validation" / "metric-candidates.md"
CANDIDATE_MARKERS = ("<!-- metric_sweep.py: candidates begin -->", "<!-- metric_sweep.py: candidates end -->")
SHEET_COLUMNS = (
    "file",
    "rule",
    "value",
    "default_fires",
    "current_expect",
    "current_basis",
    "maintainer_expect",
    "maintainer_basis",
    "maintainer_reason",
)


@dataclass(frozen=True)
class Cell:
    """One limit of a rule's sweep: how many files it flags, and the confusion counts under the labels."""

    limit: Fraction
    flagged: int
    tp: int
    fp: int
    fn: int
    tn: int

    @property
    def errors(self) -> int:
        return self.fp + self.fn


def fires(rule: str, value: Fraction, limit: Fraction) -> bool:
    """Say whether ``rule`` fires on ``value`` at ``limit``, as the rule does (strictly)."""
    return bool(corpus.would_fire(rule, value, limit))


def limits_for(values: Mapping[str, Fraction], default: Fraction) -> list[Fraction]:
    """Return the limits worth evaluating: every observed value and the default, ascending."""
    return sorted({*values.values(), default})


def cell(entries: list[Any], rule: str, values: Mapping[str, Fraction], limit: Fraction, *, checked_only: bool) -> Cell:
    """Count the files flagged at ``limit``, and the true and false positives and negatives among labelled ones.

    A file with no value (below the sample gate, or with an empty population) cannot fire and is never counted
    against a label; a label that is ``unknown`` or ``unassessed``, or presumed when ``checked_only``, is skipped.
    """
    flagged = sum(fires(rule, value, limit) for value in values.values())
    counts = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for entry in entries:
        label = entry.label(rule)
        if entry.id not in values or label["expect"] not in corpus.COUNTED:
            continue
        if checked_only and label["basis"] != "checked":
            continue
        fired = fires(rule, values[entry.id], limit)
        if label["expect"] == "fire":
            counts["tp" if fired else "fn"] += 1
        else:
            counts["fp" if fired else "tn"] += 1
    return Cell(limit, flagged, **counts)


def sweep(
    entries: list[Any], rule: str, values: Mapping[str, Fraction], default: Fraction, *, checked_only: bool
) -> list[Cell]:
    """Return the cells of ``rule`` at every limit worth evaluating."""
    return [cell(entries, rule, values, limit, checked_only=checked_only) for limit in limits_for(values, default)]


def recommend(cells: list[Cell], default: Fraction) -> tuple[Fraction | None, str]:
    """Return the limit with the fewest errors, nearest the default (the lower on a tie), and why.

    ``None`` when the labels cannot support one: no label expects a fire (a limit that switches the rule off
    would win, which is not evidence), or none expects a silence (a limit that fires everywhere would).
    """
    base = cells[0]
    if base.tp + base.fn == 0:
        return None, "no label expects a fire: recall is not measured"
    if base.fp + base.tn == 0:
        return None, "no label expects a silence: precision is not measured"
    best = min(cells, key=lambda c: (c.errors, abs(c.limit - default), c.limit))
    at_default = next(c for c in cells if c.limit == default)
    if best.errors == at_default.errors:
        return default, f"the default is among the best ({at_default.errors} errors)"
    return best.limit, f"{best.errors} errors against {at_default.errors} at the default"


def _fmt(rule: str, value: Fraction) -> str:
    return str(int(value)) if value.denominator == 1 and rule == "METRIC011" else f"{float(value):.4f}"


def _collapse(cells: list[Cell], default: Fraction) -> list[Cell]:
    """Drop a cell whose counts equal the previous one's, unless it is the default or the first."""
    kept: list[Cell] = []
    for item in cells:
        same = kept and (item.flagged, item.tp, item.fp, item.fn) == (
            kept[-1].flagged,
            kept[-1].tp,
            kept[-1].fp,
            kept[-1].fn,
        )
        if not same or item.limit == default:
            kept.append(item)
    return kept


def _table(rule: str, cells: list[Cell], default: Fraction, *, labelled: bool) -> list[str]:
    sign = ">" if corpus.READINGS[rule].upper else "<"
    head = (
        f"| Limit (fires {sign}) | Flagged | TP | FP | FN | TN |" if labelled else f"| Limit (fires {sign}) | Flagged |"
    )
    lines = [head, "| --- " * (6 if labelled else 2) + "|"]
    for item in _collapse(cells, default):
        mark = " (default)" if item.limit == default else ""
        row = f"| {_fmt(rule, item.limit)}{mark} | {item.flagged} |"
        if labelled:
            row += f" {item.tp} | {item.fp} | {item.fn} | {item.tn} |"
        lines.append(row)
    return lines


def render_sweep(entries: list[Any], results: Mapping[str, Any], *, labelled: bool, checked_only: bool = False) -> str:
    """Return the sweep of every rule as Markdown; with ``labelled``, the confusion counts and a recommendation."""
    limits = corpus.default_limits()
    out: list[str] = []
    for rule in corpus.RULES:
        values = corpus.values_of(rule, results)
        out += [f"#### {rule}", ""]
        if not values:
            out += ["No file makes a comparison for this rule.", ""]
            continue
        cells = sweep(entries, rule, values, limits[rule], checked_only=checked_only)
        out += _table(rule, cells, limits[rule], labelled=labelled)
        if labelled:
            limit, why = recommend(cells, limits[rule])
            out += ["", f"Recommended limit: {'none' if limit is None else _fmt(rule, limit)} ({why})."]
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def labels_sheet(entries: list[Any], results: Mapping[str, Any]) -> str:
    """Return a CSV with one row per file and rule, the maintainer's columns blank, in a deterministic order."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(SHEET_COLUMNS)
    limits = corpus.default_limits()
    for rule in corpus.RULES:
        values = corpus.values_of(rule, results)
        for entry in sorted(entries, key=lambda e: e.id):
            label = entry.label(rule)
            value = values.get(entry.id)
            writer.writerow(
                [
                    entry.id,
                    rule,
                    "" if value is None else _fmt(rule, value),
                    "" if value is None else str(fires(rule, value, limits[rule])).lower(),
                    label["expect"],
                    label["basis"],
                    "",
                    "",
                    "",
                ]
            )
    return buffer.getvalue()


def apply_sheet(entries: list[Any], sheet: str) -> list[Any]:
    """Return ``entries`` with each filled maintainer row applied as that rule's label; blank rows change nothing.

    A filled row needs an expect, a basis and a reason; the result is validated as the manifest is.
    """
    by_id = {entry.id: {rule: dict(label) for rule, label in entry.labels.items()} for entry in entries}
    for row in csv.DictReader(io.StringIO(sheet)):
        expect = (row.get("maintainer_expect") or "").strip()
        if not expect:
            continue
        file, rule = row["file"], row["rule"]
        if file not in by_id or rule not in corpus.RULES:
            raise ValueError(f"the sheet names an unknown file or rule: {file} {rule}")
        by_id[file][rule] = {
            "expect": expect,
            "basis": (row.get("maintainer_basis") or "").strip(),
            "why": (row.get("maintainer_reason") or "").strip(),
        }
    updated = [corpus.Entry(e.id, e.url, e.sha256, by_id[e.id]) for e in entries]
    for entry in updated:
        corpus.validate(entry)
    return updated


def _block(text: str) -> str:
    return "\n".join(["", text.rstrip(), ""])


def render_page(entries: list[Any], results: Mapping[str, Any]) -> str:
    """Return the generated part of docs/validation/metric-sweep.md: the label-free sweep of every rule."""
    return _block(render_sweep(entries, results, labelled=False))


def write_page(text: str, page: Path = SWEEP_PAGE) -> None:
    corpus.write_page(text, page, *SWEEP_MARKERS)


def render_candidates(entries: list[Any], results: Mapping[str, Any]) -> str:
    """Return, per candidate and rule, the measured value (a star: the default flags it), or a dash if none."""
    limits = corpus.default_limits()
    values = {rule: corpus.values_of(rule, results) for rule in corpus.RULES}
    lines = [
        "| Candidate | " + " | ".join(r.removeprefix("METRIC") for r in corpus.RULES) + " |",
        "| --- " * (len(corpus.RULES) + 1) + "|",
    ]
    for entry in entries:
        cells = []
        for rule in corpus.RULES:
            value = values[rule].get(entry.id)
            flag = "*" if value is not None and fires(rule, value, limits[rule]) else ""
            cells.append("-" if value is None else format(float(value), ".4g") + flag)
        lines.append(f"| {entry.id} | " + " | ".join(cells) + " |")
    return _block("\n".join(lines))


def candidates(command: str, directory: Path | None) -> None:
    """Fetch the candidate files (network), or lint them and rewrite their results and page."""
    entries = corpus.load_manifest(CANDIDATES)
    if directory is None:
        raise SystemExit(f"{command} needs a directory")
    if command == "fetch-candidates":
        corpus.fetch(directory, entries)
        return
    document = corpus.measure(directory, entries)
    CANDIDATE_RESULTS.write_text(corpus._dump(document), encoding="utf-8")
    corpus.write_page(render_candidates(entries, document), CANDIDATE_PAGE, *CANDIDATE_MARKERS)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sweep METRIC limits over the recorded corpus measurements.")
    parser.add_argument(
        "command",
        choices=("render", "sweep", "calibrate", "labels-sheet", "fetch-candidates", "measure-candidates"),
    )
    parser.add_argument("directory", nargs="?", type=Path, help="where the candidate files are kept (not committed)")
    parser.add_argument("--labels", type=Path, help="a filled sheet from labels-sheet (calibrate only)")
    parser.add_argument("--checked-only", action="store_true", help="count only labels checked in the file")
    args = parser.parse_args(argv)
    if args.command.endswith("-candidates"):
        candidates(args.command, args.directory)
        return 0
    entries = corpus.load_manifest()
    results = json.loads(corpus.RESULTS.read_text(encoding="utf-8"))
    if args.command == "labels-sheet":
        sys.stdout.write(labels_sheet(entries, results))
    elif args.command == "render":
        write_page(render_page(entries, results))
    elif args.command == "sweep":
        sys.stdout.write(render_sweep(entries, results, labelled=False))
    else:
        if args.labels is not None:
            entries = apply_sheet(entries, args.labels.read_text(encoding="utf-8"))
        sys.stdout.write(render_sweep(entries, results, labelled=True, checked_only=args.checked_only))
    return 0


if __name__ == "__main__":
    sys.exit(main())
