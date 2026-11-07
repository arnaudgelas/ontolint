"""Enforce docs/mutation-policy.md against a pytest-gremlins JSON report.

pytest-gremlins reports scores but has no minimum-score option, so this script
computes the overall and per-operator scores with the library's own formula,
(zapped + timeout) / (total - pardoned), and compares them with the policy.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

OVERALL_MIN = 85.0
OPERATOR_MIN = {
    "comparison": 85.0,
    "arithmetic": 85.0,
    "boolean": 90.0,
    "boundary": 80.0,
    "return": 80.0,
}
KILLED = {"zapped", "timeout"}


def _score(killed: int, total: int, pardoned: int) -> float:
    effective = total - pardoned
    return 100.0 if effective <= 0 else 100.0 * killed / effective


def _collect(results: list[dict[str, object]]) -> tuple[dict[str, dict[str, int]], list[str]]:
    stats: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "killed": 0, "pardoned": 0})
    survivors: list[str] = []
    for r in results:
        s = stats[str(r["operator"])]
        s["total"] += 1
        if r["status"] == "pardoned":
            s["pardoned"] += 1
        elif r["status"] in KILLED:
            s["killed"] += 1
        else:  # survived or error: an unverified mutant is never counted as killed
            survivors.append(f"{r['file_path']}:{r['line_number']} [{r['operator']}] {r['status']}: {r['description']}")
    return stats, survivors


def _operator_failures(stats: dict[str, dict[str, int]]) -> list[str]:
    failures: list[str] = []
    for op, minimum in OPERATOR_MIN.items():
        s = stats.get(op)
        if s is None or s["total"] == 0:
            print(f"{op}: no mutants generated")
            continue
        value = _score(s["killed"], s["total"], s["pardoned"])
        print(f"{op}: {value:.1f}% of {s['total']} (minimum {minimum}%)")
        if value < minimum:
            failures.append(f"{op} score {value:.1f}% < {minimum}%")
    unexpected = set(stats) - set(OPERATOR_MIN)
    if unexpected:
        failures.append(f"operators outside policy: {sorted(unexpected)}")
    return failures


def _failures(stats: dict[str, dict[str, int]]) -> list[str]:
    failures: list[str] = []
    total = sum(s["total"] for s in stats.values())
    if total == 0:
        failures.append("no mutants were generated")
    overall = _score(sum(s["killed"] for s in stats.values()), total, sum(s["pardoned"] for s in stats.values()))
    print(f"overall: {overall:.1f}% (minimum {OVERALL_MIN}%)")
    if overall < OVERALL_MIN:
        failures.append(f"overall score {overall:.1f}% < {OVERALL_MIN}%")
    return failures + _operator_failures(stats)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("report", type=Path)
    ap.add_argument("--mode", choices=("blocking", "advisory"), default="advisory")
    args = ap.parse_args()
    if not args.report.is_file():
        print(f"::error::Mutation report not found: {args.report}")
        return 2
    stats, survivors = _collect(json.loads(args.report.read_text(encoding="utf-8"))["results"])
    failures = _failures(stats)
    if survivors:
        print("Surviving or errored mutants (triage per docs/mutation-policy.md):")
        print("\n".join(f"  {line}" for line in survivors))
    level = "error" if args.mode == "blocking" else "warning"
    for failure in failures:
        print(f"::{level}::mutation policy: {failure}")
    return 1 if failures and args.mode == "blocking" else 0


if __name__ == "__main__":
    sys.exit(main())
