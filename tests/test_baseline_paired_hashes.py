"""A version 1 hash that a version 2 baseline pairs with an identity accepts a finding only in place of a missing one.

Specification (issue #10, README "Policy and baselines"): a baseline entry is a version 1 hash (rule, focus and
message, plus the path in a multi-file run) and, when its finding's identity (rule, focus and subject) was not shared
within its report, that identity.  ``--baseline`` accepts a finding when:

1. its identity is unique in its report and recorded for its report path (any path when the baseline and the run
   each have one file);
2. its version 1 hash is recorded and either the file pairs that hash with no identity (a version 1 file, or
   findings that shared an identity when it was written) or the finding's identity is shared within its report:
   those match by version 1 only, as before;
3. it is a finding of a roaming rule (ONT007, ONT008) whose identity the run reports once and the baseline records
   under exactly one other path; this is decided for every finding before any version 1 allowance is spent, and the
   entry it takes counts as held;
4. otherwise, its version 1 hash is paired: it is accepted only while that hash has an entry whose identity no
   finding of the run holds (shared identities included, and the entries rule 3 took), each such entry once, the
   pending findings served in report order.

So a finding whose subject a later release refines stays accepted (it takes its own, now missing, entry), but a new
finding that repeats an accepted one's message is reported while the accepted one is still found: a second bad value
of one SHACL shape on one node, which pySHACL often words identically, was hidden before, even under
``--fail-on-stale-baseline``.  Stale entries are computed exactly as before.

Limits, each pinned below: a value replaced by another with the same message stays accepted, as in 0.10 (S3); findings
that shared an identity when the file was written and that become unique, because a later release tells them apart or
because all but one of them is fixed, reopen once when their hash is also paired with a unique finding (M1); which of
a refined finding and a new one is reported follows report order (S6); a new finding that shares an identity with
another stays matched by version 1 (D1).

Assertions compare identities or subjects, never findings: ``Finding`` equality ignores the subject.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis_strategies import budget
from test_baseline_identity import _version_1_apply
from test_shacl_evidence import INTEGER_AGE, PREFIXES

from ontolint import baseline, main
from ontolint.baseline import Applied, Baseline
from ontolint.models import Finding
from ontolint.reporting import FileReport, fingerprint, identity

ROAMING = frozenset({"ONT007", "ONT008"})


def _f(
    subject: str | None, message: str = "m", *, rule: str = "SHACL001", focus: str = "a", fix: str = "fix"
) -> Finding:
    """A finding with the subject ``(subject,)`` (``()`` for ``None``)."""
    return Finding(rule, "error", focus, message, fix, subject=() if subject is None else (subject,))


def _refined(finding: Finding) -> Finding:
    """``finding`` as a later release might report it: one more subject part, the same message."""
    return replace(finding, subject=(*finding.subject, "refined"))


def _report(path: str, *findings: Finding) -> FileReport:
    return FileReport(path, path, findings)


def _written(*reports: FileReport) -> Baseline:
    """The baseline ``--write-baseline`` writes for ``reports``, read back."""
    return baseline.loads(baseline.dumps(baseline.build(list(reports))))


def _ids(findings: Sequence[Finding]) -> list[str]:
    return [identity(f) for f in findings]


def _kept(applied: Applied) -> list[list[str]]:
    """The identities each report keeps (the new findings), in order."""
    return [_ids(r.findings) for r in applied.files]


def _apply(accepted: Baseline, *reports: FileReport, roaming: frozenset[str] = frozenset()) -> Applied:
    return baseline.apply(accepted, list(reports), roaming)


X, Y, Z = _f("x"), _f("y"), _f("z")


# --- a new finding with an accepted one's message ---------------------------------------------------------


def test_a_second_finding_with_the_message_of_an_accepted_one_is_reported() -> None:
    """S1: accepted ``x``; the run finds ``x`` and ``y`` with one message."""
    applied = _apply(_written(_report("d.ttl", X)), _report("d.ttl", X, Y))
    assert _kept(applied) == [_ids([Y])]
    assert [_ids(r) for r in applied.baselined] == [_ids([X])]
    assert applied.stale == ()


def test_every_new_finding_with_that_message_is_reported() -> None:
    """S2."""
    applied = _apply(_written(_report("d.ttl", X)), _report("d.ttl", X, Y, Z))
    assert _kept(applied) == [_ids([Y, Z])]
    assert applied.stale == ()


def test_a_reworded_accepted_finding_does_not_free_its_message_for_a_new_one() -> None:
    """``x`` is reworded (accepted by identity) and ``y`` takes its old message: ``x``'s entry is still held."""
    applied = _apply(_written(_report("d.ttl", X)), _report("d.ttl", replace(X, message="m2"), Y))
    assert _kept(applied) == [_ids([Y])]
    assert [_ids(r) for r in applied.baselined] == [_ids([X])]
    assert applied.stale == ()


def test_an_accepted_finding_reported_twice_still_holds_its_entry() -> None:
    """The accepted ``x`` now shares its identity (a ``sh:node`` reached from two parents): it is matched by version 1,
    and its entry counts as held although no unique finding holds it, so ``y`` is reported."""
    twice = replace(X, suggestion="other fix")
    applied = _apply(_written(_report("d.ttl", X)), _report("d.ttl", X, twice, Y))
    assert _kept(applied) == [_ids([Y])]
    assert [_ids(r) for r in applied.baselined] == [_ids([X, twice])]
    assert applied.stale == ()


def test_a_renamed_file_of_a_one_file_baseline_is_matched_the_same_way() -> None:
    applied = _apply(_written(_report("d.ttl", X)), _report("e.ttl", X, Y))
    assert _kept(applied) == [_ids([Y])]
    assert applied.stale == ()


def test_in_a_multi_file_run_each_report_path_has_its_own_entries() -> None:
    c = _f(None, focus="c")
    accepted = _written(_report("a.ttl", X), _report("b.ttl", c))
    applied = _apply(accepted, _report("a.ttl", X, Y), _report("b.ttl", c))
    assert _kept(applied) == [_ids([Y]), []]
    assert applied.stale == ()


def test_each_missing_entry_accepts_one_finding() -> None:
    """``x`` and ``y`` (one message) are both refined, and ``z`` is new: two entries are missing, so two of the three
    are accepted, the first two in report order."""
    applied = _apply(_written(_report("d.ttl", X, Y)), _report("d.ttl", _refined(X), _refined(Y), Z))
    assert _kept(applied) == [_ids([Z])]
    assert applied.stale == ()


# --- what stays accepted ---------------------------------------------------------------------------------


def test_a_refined_subject_with_the_same_message_stays_accepted() -> None:
    """S4: a later release adds a subject part, so the identity changes but the version 1 hash does not."""
    applied = _apply(_written(_report("d.ttl", X)), _report("d.ttl", _refined(X)))
    assert _kept(applied) == [[]]
    assert applied.stale == ()


def test_two_refined_findings_of_one_message_both_stay_accepted() -> None:
    """S5."""
    applied = _apply(_written(_report("d.ttl", X, Y)), _report("d.ttl", _refined(X), _refined(Y)))
    assert _kept(applied) == [[]]
    assert applied.stale == ()


def test_a_value_replaced_by_another_with_the_same_message_stays_accepted() -> None:
    """S3, a limit: ``x`` is fixed and ``y`` introduced in one change; ``y`` takes the freed entry, as in 0.10."""
    applied = _apply(_written(_report("d.ttl", X)), _report("d.ttl", Y))
    assert _kept(applied) == [[]]
    assert applied.stale == ()


def test_a_version_1_file_accepts_every_finding_of_a_recorded_hash() -> None:
    """S8: a 0.10.x file pairs no hash with an identity."""
    accepted = baseline.loads(json.dumps({"fingerprints": [fingerprint(X)]}))
    applied = _apply(accepted, _report("d.ttl", X, Y))
    assert _kept(applied) == [[]]
    assert applied.stale == ()


def test_a_hash_missing_from_fingerprints_accepts_nothing_by_version_1() -> None:
    """``fingerprints`` stays the list of entries, also for a ``Baseline`` built in memory, which :func:`loads` has not
    filtered: an identity whose hash is not listed gives that hash no allowance, as in 0.13.1, so ``y`` is reported
    although no finding holds ``x``'s identity."""
    accepted = Baseline(frozenset(), ("d.ttl",), {"d.ttl": {identity(X): fingerprint(X)}})
    applied = _apply(accepted, _report("d.ttl", Y))
    assert _kept(applied) == _kept(_lenient_apply(accepted, [_report("d.ttl", Y)], frozenset())) == [_ids([Y])]


def test_new_findings_that_share_an_identity_stay_matched_by_version_1() -> None:
    """D1, a limit: the two ``y`` share an identity (an incomplete subject), so they are matched by version 1 only."""
    applied = _apply(_written(_report("d.ttl", X)), _report("d.ttl", X, Y, replace(Y, suggestion="other fix")))
    assert _kept(applied) == [[]]
    assert applied.stale == ()


# --- limits ----------------------------------------------------------------------------------------------


def test_findings_that_shared_an_identity_reopen_once_when_refined_apart() -> None:
    """M1, a limit: two findings shared an identity when the file was written, and a unique finding has their message,
    so the hash is paired; a release that tells the two apart reports them (once: the next baseline records them)."""
    ambiguous = _f("k"), _f("k", fix="other fix")
    unique = _f("u")
    accepted = _written(_report("d.ttl", *ambiguous, unique))
    assert list(accepted.identities["d.ttl"]) == [identity(unique)]
    p, q = replace(ambiguous[0], subject=("k", "p")), replace(ambiguous[1], subject=("k", "q"))
    applied = _apply(accepted, _report("d.ttl", p, q, unique))
    assert _kept(applied) == [_ids([p, q])]
    assert applied.stale == ()
    rewritten = _apply(_written(_report("d.ttl", p, q, unique)), _report("d.ttl", p, q, unique))
    assert _kept(rewritten) == [[]]


def test_a_finding_whose_shared_identity_becomes_unique_by_a_fix_reopens_once() -> None:
    """M1 by a fix: ``k`` and ``k'`` shared an identity, so only their hash was recorded, and ``u`` has their message,
    so the hash is paired; ``k'`` is fixed (a second ``sh:node`` parent removed), and ``k``, now unique, has an
    identity the file never recorded and only ``u``'s held entry for its hash: reported once, where 0.13.1 accepted
    it, and accepted by the next baseline."""
    ambiguous = _f("k"), _f("k", fix="other fix")
    unique = _f("u")
    accepted = _written(_report("d.ttl", *ambiguous, unique))
    run = _report("d.ttl", ambiguous[0], unique)
    applied = _apply(accepted, run)
    assert _kept(applied) == [_ids(ambiguous[:1])]
    assert applied.stale == ()
    assert _kept(_lenient_apply(accepted, [run], frozenset())) == [[]]
    assert _kept(_apply(_written(run), run)) == [[]]


@pytest.mark.parametrize("refined_first", [True, False])
def test_report_order_decides_which_of_a_refined_and_a_new_finding_is_reported(refined_first: bool) -> None:
    """S6, a limit: ``x`` is refined and ``y`` is new, one entry is missing, and the first in report order takes it."""
    order = (_refined(X), Y) if refined_first else (Y, _refined(X))
    applied = _apply(_written(_report("d.ttl", X)), _report("d.ttl", *order))
    assert _kept(applied) == [_ids(order[1:])]
    assert applied.stale == ()


def test_an_entry_of_a_shared_hash_is_not_stale_while_its_hash_is_found() -> None:
    """S7: ``x`` and ``y`` have one message and ``x`` is fixed; ``x``'s entry is not stale (unchanged formula)."""
    applied = _apply(_written(_report("d.ttl", X, Y)), _report("d.ttl", Y))
    assert _kept(applied) == [[]]
    assert applied.stale == ()


# --- roaming findings (ONT007, ONT008) -------------------------------------------------------------------


def _roamer(subject: str) -> Finding:
    return _f(subject, rule="ONT007", focus="https://example.test/o")


def test_a_displaced_roaming_finding_is_accepted_and_its_old_entry_is_stale_as_before() -> None:
    """``f`` moved from ``q.ttl`` to ``p.ttl``, where ``g`` has its message: accepted by roaming.  Its old entry stays
    stale, as before this rule (its hash is found on ``p.ttl`` only), a known false stale left to a later decision."""
    g, f = _roamer("g"), _roamer("f")
    accepted = _written(_report("p.ttl", g), _report("q.ttl", f))
    applied = _apply(accepted, _report("p.ttl", g, f), _report("q.ttl"), roaming=ROAMING)
    assert _kept(applied) == [[], []]
    assert applied.stale == (fingerprint(f, "q.ttl"),)


@pytest.mark.parametrize("reverse", [False, True])
def test_the_entry_a_roaming_finding_takes_cannot_accept_another(reverse: bool) -> None:
    """``f`` moved from ``q.ttl`` to ``p.ttl`` and a new ``h`` on ``q.ttl`` has ``f``'s message: ``f`` takes its entry
    by roaming whatever the report order, so ``h`` is reported."""
    k, f, h = _f(None, rule="SEC014", focus="k"), _roamer("f"), _roamer("h")
    accepted = _written(_report("p.ttl", k), _report("q.ttl", f))
    reports = [_report("p.ttl", k, f), _report("q.ttl", h)]
    applied = _apply(accepted, *(reversed(reports) if reverse else reports), roaming=ROAMING)
    assert {r.path: _ids(r.findings) for r in applied.files} == {"p.ttl": [], "q.ttl": _ids([h])}
    assert applied.stale == ()


# --- the command line ------------------------------------------------------------------------------------

COLOUR = PREFIXES + "ex:ColourShape a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:Colour .\n"
COLOUR += 'ex:Colour sh:path ex:colour ; sh:in ( "red" "green" ) ; sh:message "Unknown colour" .'


@pytest.fixture
def lint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Write ``shapes`` and the data, then run the CLI on them with ``--select SHACL001`` and return the exit code and
    the JSON report."""
    monkeypatch.chdir(tmp_path)

    def invoke(shapes: str, data: str, *argv: str) -> tuple[int, dict[str, Any]]:
        Path("s.ttl").write_text(shapes, encoding="utf-8")
        Path("d.ttl").write_text(PREFIXES + data, encoding="utf-8")
        args = ["d.ttl", "--shapes", "s.ttl", "--select", "SHACL001", "--format", "json", "--output", "o.json"]
        code = main([*args, *argv])
        return code, json.loads(Path("o.json").read_text(encoding="utf-8"))

    return invoke


STRICT = ("--baseline", "b.json", "--fail-on", "info", "--fail-on-stale-baseline")


def test_new_bad_values_of_an_accepted_shape_and_node_fail_the_run(lint: Any) -> None:
    """The issue #10 reproduction: ``sh:datatype`` words every bad value alike, so ``"y"`` and ``"z"`` were hidden by
    ``"x"``'s entry, and the run exited 0 with nothing new and nothing stale."""
    code, written = lint(INTEGER_AGE, 'ex:a a ex:T ; ex:age "x" .', "--write-baseline", "b.json", "--fail-on", "never")
    assert code == 0
    assert len(written["findings"]) == 1
    code, document = lint(INTEGER_AGE, 'ex:a a ex:T ; ex:age "x", "y", "z" .', *STRICT)
    values = [f["evidence"]["value"] for f in document["findings"]]
    assert (code, values, document["baseline"]) == (1, ['"y"', '"z"'], {"stale_fingerprints": []})


def test_a_shape_message_no_longer_hides_a_new_value(lint: Any) -> None:
    """With ``sh:message``, every result of the shape has one message, whatever its value."""
    _code, written = lint(
        COLOUR, 'ex:a a ex:T ; ex:colour "blue" .', "--write-baseline", "b.json", "--fail-on", "never"
    )
    code, document = lint(COLOUR, 'ex:a a ex:T ; ex:colour "blue", "pink" .', *STRICT)
    found = [(f["message"], f["evidence"]["value"]) for f in document["findings"]]
    assert (code, found, document["baseline"]) == (
        1,
        [(written["findings"][0]["message"], '"pink"')],
        {"stale_fingerprints": []},
    )


# --- properties ------------------------------------------------------------------------------------------

PATHS = ("a.ttl", "b.ttl")
findings = st.builds(
    Finding,
    rule=st.sampled_from(["SHACL001", "ONT007"]),
    severity=st.just("error"),
    focus=st.sampled_from(["a", "b"]),
    message=st.sampled_from(["m", "n"]),
    suggestion=st.sampled_from(["fix", "other fix"]),
    subject=st.sampled_from([(), ("x",), ("y",), ("z",)]),
)


@st.composite
def runs(draw: st.DrawFn) -> list[FileReport]:
    """The reports of one run: one or two files, each with up to five findings."""
    paths = PATHS[: draw(st.integers(1, 2))]
    return [_report(path, *draw(st.lists(findings, max_size=5))) for path in paths]


def _reworded(finding: Finding) -> Finding:
    return replace(finding, message="n" if finding.message == "m" else "m")


@st.composite
def histories(draw: st.DrawFn) -> tuple[list[FileReport], list[FileReport]]:
    """A written run and a later one, whose findings are often the written ones: kept, moved to the other file,
    refined or reworded."""
    old = draw(runs())
    known = [f for r in old for f in r.findings]
    later = findings
    if known:
        known_findings = st.sampled_from(known)
        later = st.one_of(findings, known_findings, known_findings.map(_refined), known_findings.map(_reworded))
    paths = PATHS[: draw(st.integers(1, 2))]
    return old, [_report(path, *draw(st.lists(later, max_size=5))) for path in paths]


def _lenient_apply(accepted: Baseline, reports: Sequence[FileReport], roaming: frozenset[str]) -> Applied:
    """``baseline.apply`` as ontolint 0.13.1 released it (``src/`` did not change from ``v0.13.1`` to ``e6938c6``): any
    recorded version 1 hash accepted any finding.  The oracle of the never-more-lenient property."""
    multi = len(reports) > 1
    path_free = len(accepted.files) == 1 and len(reports) == 1
    everywhere = {i: v for pairs in accepted.identities.values() for i, v in pairs.items()}
    recorded: dict[str, list[str]] = {}
    for path, pairs in accepted.identities.items():
        for ident in pairs:
            recorded.setdefault(ident, []).append(path)
    roamers = Counter(identity(f) for r in reports for f in r.findings if f.rule in roaming)
    current: set[str] = set()
    seen: set[tuple[str | None, str]] = set()
    files: list[FileReport] = []
    for report in reports:
        candidates = everywhere if path_free else accepted.identities.get(report.path, {})
        counts = Counter(identity(f) for f in report.findings)
        kept: list[Finding] = []
        for finding in report.findings:
            ident, v1 = identity(finding), fingerprint(finding, report.path if multi else None)
            current.add(v1)
            if counts[ident] == 1:
                seen.add((None if path_free else report.path, ident))
            ok = v1 in accepted.fingerprints or (counts[ident] == 1 and ident in candidates)
            if not (ok or path_free) and roamers[ident] == 1 and len(elsewhere := recorded.get(ident, [])) == 1:
                ok = True
                seen.add((elsewhere[0], ident))
            if not ok:
                kept.append(finding)
        files.append(replace(report, findings=tuple(kept)))
    paired = {v for pairs in accepted.identities.values() for v in pairs.values()}
    stale = {v for v in accepted.fingerprints - paired if v not in current}
    for path, pairs in accepted.identities.items():
        place = None if path_free else path
        stale |= {v for i, v in pairs.items() if v not in current and (place, i) not in seen}
    return Applied(files, tuple(sorted(stale)), ())


def _fresh(finding: Finding, index: int) -> Finding:
    """``finding`` with a subject no generated finding has."""
    return replace(finding, subject=(f"new {index}",))


@pytest.mark.slow
@budget(0.5)
@given(runs(), st.data())
def test_new_findings_with_paired_hashes_are_all_reported(old: list[FileReport], data: st.DataObject) -> None:
    """P1: the run repeats the written one and adds findings with fresh identities whose hashes the file pairs with a
    unique identity: exactly those are reported."""
    accepted = _written(*old)
    multi = len(old) > 1
    reports: list[FileReport] = []
    added: list[list[str]] = []
    for report in old:
        pairs = accepted.identities.get(report.path, {})
        sources = [f for f in report.findings if identity(f) in pairs]
        drawn = data.draw(st.lists(st.sampled_from(sources), max_size=4)) if sources else []
        extra = [_fresh(f, len(added) * 10 + i) for i, f in enumerate(drawn)]
        assert all(fingerprint(f, report.path if multi else None) in pairs.values() for f in extra)
        added.append(_ids(extra))
        reports.append(replace(report, findings=(*report.findings, *extra)))
    applied = _apply(accepted, *reports, roaming=ROAMING)
    assert [Counter(k) for k in _kept(applied)] == [Counter(a) for a in added]
    assert applied.stale == ()


@pytest.mark.slow
@budget(0.5)
@given(runs())
def test_a_run_whose_subjects_are_all_refined_stays_accepted(old: list[FileReport]) -> None:
    """P2: every identity class gets one more subject part, the messages stay: nothing new, nothing stale."""
    refined = [replace(r, findings=tuple(map(_refined, r.findings))) for r in old]
    applied = _apply(_written(*old), *refined, roaming=ROAMING)
    assert _kept(applied) == [[] for _ in old]
    assert applied.stale == ()


@pytest.mark.slow
@budget(0.5)
@given(histories())
def test_a_version_1_file_gives_the_version_1_results(history: tuple[list[FileReport], list[FileReport]]) -> None:
    """P3: a file with ``fingerprints`` only is applied as ontolint 0.10.2 applied it."""
    old, new = history
    text = json.dumps({"fingerprints": sorted(baseline.build(old).fingerprints)})
    applied = _apply(baseline.loads(text), *new, roaming=ROAMING)
    kept, stale = _version_1_apply(text, new)
    assert _kept(applied) == [_ids(k) for k in kept]
    assert applied.stale == stale


def _new_hashes(applied: Applied, multi: bool) -> Counter[tuple[str, str]]:
    return Counter((r.path, fingerprint(f, r.path if multi else None)) for r in applied.files for f in r.findings)


@pytest.mark.slow
@budget(0.5)
@given(histories(), st.randoms(use_true_random=False))
def test_the_order_of_reports_and_findings_changes_neither_counts_nor_stale_entries(
    history: tuple[list[FileReport], list[FileReport]], rng: random.Random
) -> None:
    """P4: which of two findings with one hash is reported may follow report order (S6), but how many are not."""
    old, new = history
    accepted = _written(*old)
    shuffled = [replace(r, findings=tuple(rng.sample(r.findings, len(r.findings)))) for r in reversed(new)]
    first = _apply(accepted, *new, roaming=ROAMING)
    second = _apply(accepted, *shuffled, roaming=ROAMING)
    assert _new_hashes(first, len(new) > 1) == _new_hashes(second, len(new) > 1)
    assert first.stale == second.stale


@pytest.mark.slow
@budget(2.0)
@given(histories())
def test_never_more_lenient_than_0_13_and_stale_entries_unchanged(
    history: tuple[list[FileReport], list[FileReport]],
) -> None:
    """P5: every finding 0.13.1 reported is still reported, and the stale entries are exactly 0.13.1's."""
    old, new = history
    accepted = _written(*old)
    applied = _apply(accepted, *new, roaming=ROAMING)
    before = _lenient_apply(accepted, new, ROAMING)
    for now, then in zip(_kept(applied), _kept(before), strict=True):
        assert not Counter(then) - Counter(now)
    assert applied.stale == before.stale
