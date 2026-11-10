"""Baseline files: record the findings of one run and accept them in a later one (OPS002-OPS004).

A baseline file (version 2) holds:

* ``fingerprints``: the version 1 hash of every finding (:func:`ontolint.reporting.fingerprint`: rule, focus
  and message, plus the report path in a multi-file run), exactly as ontolint 0.10 wrote and read it;
* ``files``: the report paths of the run that wrote it;
* ``identities``: per report path, the message-independent identity of each finding
  (:func:`ontolint.reporting.identity`: rule, focus and subject), mapped to its version 1 hash.

A finding is accepted when its version 1 hash is recorded, or when its identity is recorded for its report
path; for any path when both the baseline and the run have exactly one file, so a one-file baseline keeps
following a renamed file, as version 1 does.  Rewording a message therefore keeps a finding accepted, and a
one-file baseline applies to that file in a multi-file run (and the reverse).  An identity shared by two
findings of one report means a rule's subject is incomplete: such findings are recorded and matched by
version 1 only, so a missing subject never hides a new problem.

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
    return [(f, i, counts[i] == 1) for f, i in zip(report.findings, ids, strict=True)]


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


def apply(baseline: Baseline, reports: Sequence[FileReport]) -> Applied:
    """Remove the findings ``baseline`` accepts from ``reports`` (the reports of one run)."""
    multi = len(reports) > 1
    path_free = len(baseline.files) == 1 and len(reports) == 1
    everywhere = {ident: v1 for pairs in baseline.identities.values() for ident, v1 in pairs.items()}
    current: set[str] = set()  # version 1 hashes of the run
    seen: set[tuple[str | None, str]] = set()  # (report path, or None when path-free; identity), unambiguous only
    files: list[FileReport] = []
    removed: list[tuple[Finding, ...]] = []
    for report in reports:
        candidates = everywhere if path_free else baseline.identities.get(report.path, {})
        kept: list[Finding] = []
        dropped: list[Finding] = []
        for finding, ident, unique in _unique(report):
            v1 = _v1(finding, report, multi)
            current.add(v1)
            if unique:
                seen.add((None if path_free else report.path, ident))
            accepted = v1 in baseline.fingerprints or (unique and ident in candidates)
            (dropped if accepted else kept).append(finding)
        files.append(replace(report, findings=tuple(kept)))
        removed.append(tuple(dropped))
    paired = {v1 for pairs in baseline.identities.values() for v1 in pairs.values()}
    stale = {v1 for v1 in baseline.fingerprints - paired if v1 not in current}
    for path, pairs in baseline.identities.items():
        place = None if path_free else path
        stale |= {v1 for ident, v1 in pairs.items() if v1 not in current and (place, ident) not in seen}
    return Applied(files, tuple(sorted(stale)), tuple(removed))
