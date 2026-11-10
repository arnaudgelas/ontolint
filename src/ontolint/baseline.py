"""Baseline files: record the findings of one run and accept them in a later one (OPS002/OPS004).

``--write-baseline`` records a fingerprint (:func:`ontolint.reporting.fingerprint`) for every finding of
the run; ``--baseline`` removes the findings whose fingerprint the file holds, and names the recorded
fingerprints that matched no finding of the run (stale, OPS003).  One-file runs hash findings without
their path, multi-file runs with it.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import NamedTuple

from .models import Finding
from .reporting import FileReport, fingerprint


@dataclass(frozen=True)
class Baseline:
    """The accepted findings of an earlier run."""

    fingerprints: frozenset[str] = frozenset()


class Applied(NamedTuple):
    """What applying a baseline to the reports of a run gives."""

    files: list[FileReport]
    """Each report without its baselined findings, in the order given."""
    stale: tuple[str, ...]
    """The recorded fingerprints that matched no finding of the run, sorted."""
    baselined: tuple[tuple[Finding, ...], ...]
    """For each report, in the same order, the findings the baseline removed."""


def _fingerprints(report: FileReport, multi: bool) -> set[str]:
    return {fingerprint(f, report.path if multi else None) for f in report.findings}


def build(reports: Sequence[FileReport]) -> Baseline:
    """The baseline that accepts every finding of ``reports`` (the reports of one run)."""
    multi = len(reports) > 1
    return Baseline(frozenset().union(*(_fingerprints(r, multi) for r in reports)))


def dumps(baseline: Baseline) -> str:
    """The baseline file's text: sorted, indented JSON with a trailing newline."""
    return json.dumps({"fingerprints": sorted(baseline.fingerprints)}, indent=2) + "\n"


def loads(text: str) -> Baseline:
    """Read a baseline file written by :func:`dumps` (or by an earlier release)."""
    return Baseline(frozenset(json.loads(text).get("fingerprints", [])))


def apply(baseline: Baseline, reports: Sequence[FileReport]) -> Applied:
    """Remove the findings ``baseline`` accepts from ``reports`` (the reports of one run)."""
    multi = len(reports) > 1
    prior = baseline.fingerprints
    current = set().union(*(_fingerprints(r, multi) for r in reports))
    files: list[FileReport] = []
    removed: list[tuple[Finding, ...]] = []
    for report in reports:
        accepted = [fingerprint(f, report.path if multi else None) in prior for f in report.findings]
        files.append(
            replace(report, findings=tuple(f for f, a in zip(report.findings, accepted, strict=True) if not a))
        )
        removed.append(tuple(f for f, a in zip(report.findings, accepted, strict=True) if a))
    return Applied(files, tuple(sorted(prior - current)), tuple(removed))
