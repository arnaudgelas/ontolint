"""Baseline files: what ``--write-baseline`` records and what ``--baseline`` accepts (OPS002-OPS004)."""

from __future__ import annotations

from ontolint import baseline
from ontolint.models import Finding
from ontolint.reporting import FileReport


def _finding(focus: str, message: str = "message") -> Finding:
    return Finding("ONT001", "warning", focus, message, "fix")


def test_apply_returns_the_findings_it_removed_per_report() -> None:
    known, new = _finding("x"), _finding("y")
    reports = [FileReport("a.ttl", "a.ttl", (known, new)), FileReport("b.ttl", "b.ttl", (new,))]
    accepted = baseline.build([FileReport("a.ttl", "a.ttl", (known,)), FileReport("b.ttl", "b.ttl", ())])

    applied = baseline.apply(accepted, reports)

    assert [r.findings for r in applied.files] == [(new,), (new,)]
    assert applied.baselined == ((known,), ())
    assert applied.stale == ()


def test_dumps_then_loads_gives_the_same_baseline() -> None:
    accepted = baseline.build([FileReport("a.ttl", "a.ttl", (_finding("x"), _finding("y")))])

    assert baseline.loads(baseline.dumps(accepted)) == accepted
