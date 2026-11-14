"""Baseline files: record the findings of one run and accept them in a later one (OPS002-OPS004).

A baseline file (version 2) holds:

* ``fingerprints``: the version 1 hash of every finding (:func:`ontolint.reporting.fingerprint`: rule, focus
  and message, plus the report path in a multi-file run), exactly as ontolint 0.10 wrote and read it;
* ``files``: the report paths of the run that wrote it;
* ``identities``: per report path, the message-independent identity of each finding
  (:func:`ontolint.reporting.identity`: rule, focus and subject), mapped to its version 1 hash.

A finding is accepted when its identity is recorded for its report path (for any path when both the baseline
and the run have exactly one file, so a one-file baseline keeps following a renamed file, as version 1 does), or
when its version 1 hash is recorded.  Rewording a message therefore keeps a finding accepted, and a one-file
baseline applies to that file in a multi-file run (and the reverse).  An identity shared by two findings of one
report means a rule's subject is incomplete: such findings are recorded and matched by version 1 only.

A version 1 hash that the file pairs with an identity accepts a finding only in place of an entry of that hash
whose identity no finding of the run holds (shared identities included), each such entry once, in report order
(issue #10).  So a finding whose subject a later release refines stays accepted, but a new problem whose message
equals an accepted one's (a second bad value of one SHACL shape on one node) is reported while the accepted one
is still found.  A hash the file pairs with no identity (a version 1 file, or findings that shared an identity)
accepts every finding with it, as in version 1, and so does a finding whose identity is shared in its report.
Its limits:

* a problem fixed and another with its message introduced in one change: the second takes the freed entry, as in
  version 1;
* findings that shared an identity when the file was written, and that become unique (a later release tells them
  apart, or all but one of them is fixed), reopen once when their hash is also paired with a unique finding: the
  file never recorded their identity, and the unique finding holds the hash's only entry;
* when a refined finding and a new one with its message coincide, report order decides which one is reported.

A finding of a rule that compares the files of a run (``roaming``: ONT007, ONT008) is reported on one of
the files it names, which another file of the run can displace (a copy added that sorts first).  Its identity
is therefore also accepted under another report path, when it is unambiguous: the run reports it once, and the
baseline records it under one path.  This is decided for every finding before any version 1 hash is spent, so the
result does not depend on the order of the reports, and the entry it takes is stale or not exactly as before.

A recorded entry (a version 1 hash and its identity) is stale when neither matched a finding of the run.
``fingerprints`` stays the list of entries: an identity whose version 1 hash is not listed is ignored, so
deleting a line from that list still withdraws the finding's acceptance, and ontolint 0.10, which reads
only that list, gives the version 1 results.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, NamedTuple

from .models import Finding
from .reporting import FileReport, fingerprint, identity

BASELINE_VERSION = 2
_HASH = re.compile(r"[0-9a-f]{64}")


class BaselineError(ValueError):
    """A baseline file this version cannot read: not JSON, a section of the wrong shape, or identities of a path
    missing from ``files``."""


@dataclass(frozen=True)
class Baseline:
    """The accepted findings of an earlier run."""

    fingerprints: frozenset[str] = frozenset()
    """The version 1 hash of every accepted finding."""
    files: tuple[str, ...] = ()
    """The report paths of the run that wrote the baseline, sorted; ``()`` for a version 1 file."""
    identities: Mapping[str, Mapping[str, str]] = field(default_factory=dict[str, Mapping[str, str]])
    """Per report path, each accepted finding's identity mapped to its version 1 hash."""


class Applied(NamedTuple):
    """What applying a baseline to the reports of a run gives."""

    files: list[FileReport]
    """Each report without its baselined findings, in the order given."""
    stale: tuple[str, ...]
    """The version 1 hashes of the recorded entries that matched no finding of the run, sorted."""
    baselined: tuple[tuple[Finding, ...], ...]
    """For each report, in the same order, the findings the baseline removed."""


def _v1(finding: Finding, report: FileReport, multi: bool) -> str:
    return fingerprint(finding, report.path if multi else None)


def _unique(report: FileReport) -> list[tuple[Finding, str, bool]]:
    """Each finding of ``report`` with its identity, and whether no other finding of the report shares it."""
    ids = [identity(f) for f in report.findings]
    counts = Counter(ids)
    # gremlin: pardon[equivalent] ids is built from report.findings, so the lengths always match
    pairs = zip(report.findings, ids, strict=True)
    return [(f, i, counts[i] == 1) for f, i in pairs]


def build(reports: Sequence[FileReport]) -> Baseline:
    """The baseline that accepts every finding of ``reports`` (the reports of one run)."""
    multi = len(reports) > 1
    fingerprints: set[str] = set()
    identities: dict[str, dict[str, str]] = {}
    for report in reports:
        for finding, ident, unique in _unique(report):
            fingerprints.add(_v1(finding, report, multi))
            if unique:
                identities.setdefault(report.path, {})[ident] = _v1(finding, report, multi)
    return Baseline(frozenset(fingerprints), tuple(sorted({r.path for r in reports})), identities)


def dumps(baseline: Baseline) -> str:
    """The baseline file's text: indented JSON, every list and map sorted, with a trailing newline."""
    document = {
        "version": BASELINE_VERSION,
        "files": list(baseline.files),
        "fingerprints": sorted(baseline.fingerprints),
        "identities": {path: dict(sorted(baseline.identities[path].items())) for path in sorted(baseline.identities)},
    }
    return json.dumps(document, indent=2) + "\n"


def _strings(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise BaselineError(f"{name} must be a list of strings")
    return value


def _pairs(path: str, value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or not all(
        isinstance(v, str) and _HASH.fullmatch(k) and _HASH.fullmatch(v) for k, v in value.items()
    ):
        raise BaselineError(f"identities[{path!r}] must map 64-digit hex identities to fingerprints")
    return value


def loads(text: str) -> Baseline:
    """Read a baseline file of any version; sections this version does not know are ignored."""
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BaselineError(f"not JSON: {exc}") from None
    if not isinstance(document, dict):
        raise BaselineError("a baseline is a JSON object")
    version = document.get("version", 1)
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise BaselineError("version must be a positive integer")
    fingerprints = frozenset(_strings(document.get("fingerprints", []), "fingerprints"))
    files = tuple(_strings(document.get("files", []), "files"))
    raw = document.get("identities", {})
    if not isinstance(raw, dict):
        raise BaselineError("identities must map report paths to identities")
    if unlisted := sorted(set(raw) - set(files)):
        raise BaselineError(f"identities name report paths missing from files: {unlisted!r}")
    identities = {
        path: {ident: v1 for ident, v1 in _pairs(path, pairs).items() if v1 in fingerprints}
        for path, pairs in raw.items()
    }
    return Baseline(fingerprints, files, identities)


type _Entry = tuple[str | None, str]
"""A recorded entry's report path (``None`` when the run is path-free) and identity."""


@dataclass
class _Matcher:
    """A baseline indexed for the reports of one run, and what pass 1 of :func:`apply` learns about the run.

    Not frozen: pass 1 adds to ``held`` and ``seen``, and a ``frozen=True`` would only give the mutation run a decorator
    mutant that it cannot execute in time (``docs/mutation-pardons.md``)."""

    baseline: Baseline
    path_free: bool
    roamers: Counter[str]
    """How many findings of a roaming rule the run reports with each identity."""
    held: set[_Entry]
    """Every (place, identity) a finding of the run holds, shared or not, and the entries roaming findings take."""
    everywhere: dict[str, str] = field(default_factory=dict[str, str])
    recorded: dict[str, list[str]] = field(default_factory=dict[str, list[str]])
    """Identity -> the report paths the baseline records it under."""
    entries: dict[str, list[_Entry]] = field(default_factory=dict[str, list[_Entry]])
    """Version 1 hash -> the entries the file pairs it with."""
    seen: set[_Entry] = field(default_factory=set[_Entry])
    """For staleness only, as before: the (place, identity) of each unique finding, and the entry a roaming finding
    takes when its version 1 hash is not recorded."""

    @classmethod
    def of(cls, baseline: Baseline, reports: Sequence[FileReport], roaming: frozenset[str]) -> _Matcher:
        path_free = len(baseline.files) == 1 and len(reports) == 1
        roamers = Counter(identity(f) for report in reports for f in report.findings if f.rule in roaming)
        held = {(None if path_free else r.path, identity(f)) for r in reports for f in r.findings}
        matcher = cls(baseline, path_free, roamers, held)
        for path, pairs in baseline.identities.items():
            for ident, v1 in pairs.items():
                matcher.everywhere[ident] = v1
                matcher.recorded.setdefault(ident, []).append(path)
                matcher.entries.setdefault(v1, []).append((matcher.place(path), ident))
        return matcher

    def place(self, path: str) -> str | None:
        return None if self.path_free else path

    def verdict(self, path: str, v1: str, ident: str, unique: bool) -> bool | None:
        """Whether the baseline accepts a finding; ``None`` when only an entry no finding holds can accept it."""
        candidates = self.everywhere if self.path_free else self.baseline.identities.get(path, {})
        if unique and ident in candidates:
            return True
        recorded = v1 in self.baseline.fingerprints
        if recorded and not (unique and v1 in self.entries):
            return True  # a hash paired with no identity, or a shared identity: version 1, as before
        elsewhere = self.recorded.get(ident, [])
        if not self.path_free and self.roamers[ident] == 1 and len(elsewhere) == 1:
            self.held.add((elsewhere[0], ident))
            if not recorded:
                self.seen.add((elsewhere[0], ident))
            return True
        return None if recorded else False

    def spare(self) -> Counter[str]:
        """For each paired version 1 hash, how many of its entries no finding of the run holds."""
        return Counter({v1: sum(e not in self.held for e in entries) for v1, entries in self.entries.items()})


def apply(baseline: Baseline, reports: Sequence[FileReport], roaming: frozenset[str] = frozenset()) -> Applied:
    """Remove the findings ``baseline`` accepts from ``reports`` (the reports of one run).

    A finding of a ``roaming`` rule may be accepted under another report path than its own (see above).
    """
    multi = len(reports) > 1
    matcher = _Matcher.of(baseline, reports, roaming)
    path_free, seen = matcher.path_free, matcher.seen
    current: set[str] = set()  # version 1 hashes of the run
    verdicts: list[list[bool | None]] = []
    pending: list[tuple[list[bool | None], int, str]] = []  # (verdicts of a report, index, version 1 hash)
    for report in reports:
        row: list[bool | None] = []
        for finding, ident, unique in _unique(report):
            v1 = _v1(finding, report, multi)
            current.add(v1)
            if unique:
                seen.add((matcher.place(report.path), ident))
            verdict = matcher.verdict(report.path, v1, ident, unique)
            if verdict is None:
                pending.append((row, len(row), v1))
            row.append(verdict)
        verdicts.append(row)
    spare = matcher.spare()  # after every roaming finding has taken its entry
    for row, index, v1 in pending:
        row[index] = spare[v1] > 0
        spare[v1] -= 1
    files = [
        replace(r, findings=tuple(f for i, f in enumerate(r.findings) if not verdicts[n][i]))
        for n, r in enumerate(reports)
    ]
    removed = [tuple(f for i, f in enumerate(r.findings) if verdicts[n][i]) for n, r in enumerate(reports)]
    paired = {v1 for pairs in baseline.identities.values() for v1 in pairs.values()}
    stale = {v1 for v1 in baseline.fingerprints - paired if v1 not in current}
    for path, pairs in baseline.identities.items():
        place = None if path_free else path
        stale |= {v1 for ident, v1 in pairs.items() if v1 not in current and (place, ident) not in seen}
    return Applied(files, tuple(sorted(stale)), tuple(removed))
