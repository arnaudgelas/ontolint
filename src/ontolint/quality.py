"""Quality snapshots and their comparison: one file format, two uses (``docs/quality.md``).

A *snapshot* is the measurement vector of one run (:mod:`ontolint.rules.measurements`) with, for every coverage
measure, the sorted IRIs of its numerator and denominator, and the policy that shaped the populations.  A
*quality baseline* is a snapshot committed to the repository (the accepted values); a *trend* is the comparison of
two snapshot files.  ontolint reads no git history: CI keeps the snapshots.  This is not ``--baseline``, which
suppresses findings by fingerprint (:mod:`ontolint.baseline`).

The file (``SNAPSHOT_VERSION`` 1) is JSON, deterministic (no timestamp, no path, no tool version) and strict:
:func:`loads` refuses anything it does not know, so a reader never guesses::

    {"format": "ontolint-quality-snapshot", "version": 1,
     "policy": {"base": null, "extra_label_predicates": [], "extra_definition_predicates": [], "imports": []},
     "measurements": [<a published measurement>, + for a coverage measure:
                      "better": "higher" | "lower", "numerator_terms": [...], "denominator_terms": [...]]}

A change to the format increments the version, and a reader refuses a version it does not read.

A coverage measure compares term by term, so a coverage change splits into counts that aggregates cannot give:
terms that got worse (``regressed``), new terms that are worse (``diluted``), ``removed`` terms, terms that got
better (``improved``) and new terms that are fine (``added_good``).  What is "worse" is the measure's ``better``:
for ``higher`` a term is fine when it is in the numerator, for ``lower`` when it is not.  A measurement whose
definition version, kind, population, numerator reading or policy differs between the two snapshots, or that one
of them could not take, is reported as not comparable with its reasons, one measurement at a time, and never
diffed.  A rename is one removal and one new term (there is no rename detection).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal
from fractions import Fraction
from typing import Any, cast

from .models import Measurement, MeasurementKind
from .redaction import redact_userinfo
from .rules import measurements as engine
from .rules.measurements import Absent, TermRatio
from .rules.runtime import RuleContext

SNAPSHOT_FORMAT = "ontolint-quality-snapshot"
SNAPSHOT_VERSION = 1
COMPARISON_FORMAT = "ontolint-quality-comparison"
COMPARISON_VERSION = 1
BETTER = ("higher", "lower")
CHANGES = ("regressed", "diluted", "removed", "improved", "added_good")
"""The parts of a coverage change, in the order a report lists them."""
RENAME_NOTE = (
    "A renamed term counts as one removal and one new term: ontolint has no rename detection (the COMP rules "
    "will add it)."
)
_DELTA_PLACES = Decimal("0.0001")


class SnapshotError(ValueError):
    """A snapshot this version cannot use: not JSON, an unknown version, or a shape the format does not allow."""


def _refuse(condition: object, message: str) -> None:
    if not condition:
        raise SnapshotError(message)


# --- the model -------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Shaping:
    """The policy that shaped the populations: everything besides the graph a measurement's value depends on.

    These are ``--base``, ``extra_label_predicates``, ``extra_definition_predicates`` and the IRIs of the
    imports the run resolved to files (the import closure).  Two snapshots with another shaping are not
    comparable: a different ``base`` is a different owned population.
    """

    base: str | None = None
    extra_label_predicates: tuple[str, ...] = ()
    extra_definition_predicates: tuple[str, ...] = ()
    imports: tuple[str, ...] = ()

    def differing(self, other: Shaping) -> tuple[str, ...]:
        """The names of the fields that differ, in field order."""
        return tuple(name for name in _SHAPING_FIELDS if getattr(self, name) != getattr(other, name))

    def to_dict(self) -> dict[str, Any]:
        return {name: list(v) if isinstance(v := getattr(self, name), tuple) else v for name in _SHAPING_FIELDS}


_SHAPING_FIELDS = tuple(Shaping.__dataclass_fields__)


@dataclass(frozen=True)
class Coverage:
    """The terms behind a coverage measure: both sets sorted, each IRI once, the numerator within the denominator."""

    better: str
    numerator: tuple[str, ...]
    denominator: tuple[str, ...]

    def __post_init__(self) -> None:
        _refuse(self.better in BETTER, f"a coverage measure is better higher or lower, not {self.better!r}")
        for name, iris in (("numerator", self.numerator), ("denominator", self.denominator)):
            _refuse(
                all(isinstance(i, str) for i in iris) and all(a < b for a, b in zip(iris, iris[1:], strict=False)),
                f"the {name} terms are IRIs, sorted, each once",
            )
        _refuse(set(self.numerator) <= set(self.denominator), "the numerator terms are among the denominator terms")

    def fine(self, term: str) -> bool:
        """Whether ``term`` (of the denominator) is in the good state: in the numerator if ``higher``, else not."""
        return (term in self.numerator) == (self.better == "higher")


@dataclass(frozen=True)
class Entry:
    """One measurement of a snapshot: the published record and, for a coverage measure, its terms."""

    measurement: Measurement
    coverage: Coverage | None = None

    def __post_init__(self) -> None:
        if self.coverage is None:
            return
        m = self.measurement
        _refuse(
            m.kind is MeasurementKind.RATIO and m.reason is None and m.by_namespace is None,
            f"{m.id}: only a ratio that was taken has term sets",
        )
        _refuse(
            (m.numerator, m.denominator) == (len(self.coverage.numerator), len(self.coverage.denominator)),
            f"{m.id}: the counts are those of the term sets",
        )


@dataclass(frozen=True)
class Snapshot:
    """The measurement vector of one run, with its term sets and the policy that shaped it."""

    shaping: Shaping
    entries: tuple[Entry, ...]

    def __post_init__(self) -> None:
        ids = [e.measurement.id for e in self.entries]
        _refuse(len(set(ids)) == len(ids), "a measurement appears once in a snapshot")


# --- taking a snapshot ------------------------------------------------------------------------------------------


def _masked(iris: frozenset[Any]) -> tuple[str, ...]:
    """``iris`` as sorted text, each userinfo masked and the IRIs that mask to one text counted once."""
    return tuple(sorted({redact_userinfo(str(i)) for i in iris}))


def build(ctx: RuleContext) -> Snapshot:
    """The snapshot of ``ctx``: every measurement of the catalogue, in its order, as it stood after the rules ran.

    A coverage measure (one with ``better``) keeps the sorted, masked IRIs of its numerator and denominator, and
    its counts are theirs: two IRIs that differ only in their userinfo are one term here, as they are one finding.
    Raises :class:`SnapshotError` if a coverage measure's numerator is not within its denominator.
    """
    policy = ctx.policy
    shaping = Shaping(
        None if policy.base is None else redact_userinfo(policy.base),
        tuple(sorted(map(redact_userinfo, policy.extra_label_predicates))),
        tuple(sorted(map(redact_userinfo, policy.extra_definition_predicates))),
        tuple(sorted(map(redact_userinfo, policy.resolved_imports))),
    )
    entries: list[Entry] = []
    for spec, value in engine.taken(ctx):
        if spec.better is None or isinstance(value, Absent):
            entries.append(Entry(engine.record(spec, value)))
            continue
        if not isinstance(value, TermRatio):
            raise SnapshotError(f"{spec.id} is a coverage measure of terms")
        coverage = Coverage(spec.better, _masked(value.numerator), _masked(value.denominator))
        record = Measurement(
            spec.id,
            spec.version,
            spec.kind,
            spec.population,
            numerator=len(coverage.numerator),
            denominator=len(coverage.denominator),
        )
        entries.append(Entry(record, coverage))
    return Snapshot(shaping, tuple(entries))


# --- the file ---------------------------------------------------------------------------------------------------


def _entry_dict(entry: Entry) -> dict[str, Any]:
    data = entry.measurement.to_dict()
    if entry.coverage is not None:
        data["better"] = entry.coverage.better
        data["numerator_terms"] = list(entry.coverage.numerator)
        data["denominator_terms"] = list(entry.coverage.denominator)
    return data


def to_dict(snapshot: Snapshot) -> dict[str, Any]:
    """The JSON-ready snapshot document."""
    return {
        "format": SNAPSHOT_FORMAT,
        "version": SNAPSHOT_VERSION,
        "policy": snapshot.shaping.to_dict(),
        "measurements": [_entry_dict(e) for e in snapshot.entries],
    }


def dumps(snapshot: Snapshot) -> str:
    """The snapshot file's text: UTF-8 JSON, two-space indent, one IRI per line, a final newline."""
    return json.dumps(to_dict(snapshot), indent=2, ensure_ascii=False) + "\n"


_IDENTITY = {"id", "definition_version", "kind", "population"}
_VALUES = {
    MeasurementKind.RATIO: {"numerator", "denominator", "by_namespace"},
    MeasurementKind.COUNT: {"value"},
    MeasurementKind.HISTOGRAM: {"buckets"},
}
_COVERAGE_KEYS = {"better", "numerator_terms", "denominator_terms"}


def _dict(raw: object, what: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise SnapshotError(f"{what} is a JSON object")
    return cast("dict[str, Any]", raw)


def _object(raw: object, keys: set[str], what: str) -> dict[str, Any]:
    """``raw`` as an object with exactly the keys ``keys``."""
    found = _dict(raw, what)
    _refuse(set(found) == keys, f"{what} has the keys {sorted(keys)}, not {sorted(found)}")
    return found


def _list(raw: object, what: str) -> list[Any]:
    if not isinstance(raw, list):
        raise SnapshotError(f"{what} is a JSON array")
    return raw


def _pairs(raw: object, first: str, what: str) -> tuple[tuple[Any, Any], ...]:
    return tuple((o[first], o["count"]) for o in (_object(x, {first, "count"}, what) for x in _list(raw, what)))


def _measurement(raw: object) -> Measurement:
    raw = _dict(raw, "a measurement")
    try:
        kind = MeasurementKind(str(raw.get("kind")))
    except ValueError:
        raise SnapshotError(
            f"a measurement has a kind of {[k.value for k in MeasurementKind]}, not {raw.get('kind')!r}"
        ) from None
    allowed = _IDENTITY | _VALUES[kind] | {"reason"} | _COVERAGE_KEYS
    _refuse(not set(raw) - allowed, f"a measurement of kind {kind.value} has no key {sorted(set(raw) - allowed)}")
    fields: dict[str, Any] = {k: raw[k] for k in _IDENTITY - {"kind"} if k in raw}
    _refuse(_IDENTITY - {"kind"} <= set(fields), "a measurement has an id, a definition_version and a population")
    for key in ("numerator", "denominator", "value", "reason"):
        if key in raw:
            fields[key] = raw[key]
    if "buckets" in raw:
        fields["buckets"] = _pairs(raw["buckets"], "value", "a bucket")
    if "by_namespace" in raw:
        fields["by_namespace"] = _pairs(raw["by_namespace"], "namespace", "a namespace count")
    _refuse(fields.get("reason") is None or isinstance(fields["reason"], str), "a reason is text")
    try:
        return Measurement(kind=kind, **fields)
    except (TypeError, ValueError) as exc:
        raise SnapshotError(str(exc)) from exc


def _entry(raw: object) -> Entry:
    measurement = _measurement(raw)
    raw = _dict(raw, "a measurement")
    given = _COVERAGE_KEYS & set(raw)
    if not given:
        return Entry(measurement)
    _refuse(given == _COVERAGE_KEYS, f"{measurement.id}: better and both term sets go together")
    terms = [tuple(_list(raw[k], f"{measurement.id}: {k}")) for k in ("numerator_terms", "denominator_terms")]
    return Entry(measurement, Coverage(raw["better"], terms[0], terms[1]))


def _shaping(raw: object) -> Shaping:
    given = _object(raw, set(_SHAPING_FIELDS), "the policy")
    _refuse(given["base"] is None or isinstance(given["base"], str), "the policy base is text or null")
    lists = {name: tuple(_list(given[name], f"the policy {name}")) for name in _SHAPING_FIELDS if name != "base"}
    _refuse(all(isinstance(i, str) for items in lists.values() for i in items), "the policy lists hold text")
    return Shaping(given["base"], **lists)


def from_dict(document: object) -> Snapshot:
    """The snapshot of a decoded JSON document; raises :class:`SnapshotError` for anything else."""
    top = _object(document, {"format", "version", "policy", "measurements"}, "a snapshot")
    _refuse(top["format"] == SNAPSHOT_FORMAT, f"not a quality snapshot: its format is {top['format']!r}")
    version = top["version"]
    _refuse(
        isinstance(version, int) and not isinstance(version, bool) and version == SNAPSHOT_VERSION,
        f"snapshot version {version!r} is not supported (this ontolint reads version {SNAPSHOT_VERSION})",
    )
    return Snapshot(_shaping(top["policy"]), tuple(_entry(e) for e in _list(top["measurements"], "the measurements")))


def loads(text: str) -> Snapshot:
    """The snapshot a file's text holds; raises :class:`SnapshotError`, never anything else, for an unusable one."""
    try:
        document = json.loads(text)
    except ValueError as exc:  # JSONDecodeError, and the recursion limit's RecursionError is not one: see below
        raise SnapshotError(f"not JSON: {exc}") from exc
    except RecursionError as exc:
        raise SnapshotError("not a quality snapshot: nested too deeply") from exc
    return from_dict(document)


# --- the comparison ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Change:
    """How a coverage measure changed, term by term (:data:`CHANGES`); every list is sorted."""

    better: str
    regressed: tuple[str, ...]
    diluted: tuple[str, ...]
    removed: tuple[str, ...]
    improved: tuple[str, ...]
    added_good: tuple[str, ...]

    def terms(self, name: str) -> tuple[str, ...]:
        """The terms of one part of the change; ``name`` is one of :data:`CHANGES`."""
        _refuse(name in CHANGES, f"a coverage change has the parts {CHANGES}")
        return getattr(self, name)  # type: ignore[no-any-return]

    def counts(self) -> dict[str, int]:
        return {name: len(self.terms(name)) for name in CHANGES}

    def to_dict(self) -> dict[str, Any]:
        return {
            "better": self.better,
            **self.counts(),
            "terms": {name: list(self.terms(name)) for name in CHANGES},
        }


@dataclass(frozen=True)
class Result:
    """One measurement of the comparison: compared (no reason) or not comparable (reasons, and nothing else)."""

    id: str
    reasons: tuple[str, ...] = ()
    before: Measurement | None = None
    after: Measurement | None = None
    delta: str | int | None = None
    """A ratio's change as a signed decimal text with four places (exact, never a float), ``None`` when a
    population is empty; a count's difference; ``None`` for a histogram."""
    change: Change | None = None
    changed: bool | None = None
    """For a histogram, whether its buckets differ."""


@dataclass(frozen=True)
class Comparison:
    """The comparison of two snapshots: one :class:`Result` per measurement of either, and the notes."""

    results: tuple[Result, ...]
    notes: tuple[str, ...] = field(default=(RENAME_NOTE,))

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": COMPARISON_FORMAT,
            "version": COMPARISON_VERSION,
            "notes": list(self.notes),
            "measurements": [_result_dict(r) for r in self.results],
        }


def _values(m: Measurement) -> dict[str, Any]:
    data = m.to_dict()
    return {k: v for k, v in data.items() if k not in _IDENTITY}


def _result_dict(result: Result) -> dict[str, Any]:
    if result.before is None or result.after is None:  # only a compared result has both sides
        return {"id": result.id, "status": "not_comparable", "reasons": list(result.reasons)}
    data: dict[str, Any] = {
        "id": result.id,
        "status": "compared",
        "definition_version": result.before.definition_version,
        "kind": result.before.kind.value,
        "population": result.before.population,
        "before": _values(result.before),
        "after": _values(result.after),
    }
    if result.before.kind is not MeasurementKind.HISTOGRAM:
        data["delta"] = result.delta
    else:
        data["changed"] = result.changed
    if result.change is not None:
        data["coverage"] = result.change.to_dict()
    return data


def _ratio_delta(old: Measurement, new: Measurement) -> str | None:
    if not (old.denominator and new.denominator):
        return None
    exact = Fraction(new.numerator or 0, new.denominator) - Fraction(old.numerator or 0, old.denominator)
    rounded = (Decimal(exact.numerator) / Decimal(exact.denominator)).quantize(_DELTA_PLACES, ROUND_HALF_EVEN)
    return "0.0000" if rounded == 0 else f"{rounded:+.4f}"


def _split(old: Coverage, new: Coverage) -> Change:
    kept = set(old.denominator) & set(new.denominator)
    added = set(new.denominator) - set(old.denominator)
    return Change(
        old.better,
        regressed=tuple(sorted(t for t in kept if old.fine(t) and not new.fine(t))),
        diluted=tuple(sorted(t for t in added if not new.fine(t))),
        removed=tuple(sorted(set(old.denominator) - set(new.denominator))),
        improved=tuple(sorted(t for t in kept if not old.fine(t) and new.fine(t))),
        added_good=tuple(sorted(t for t in added if new.fine(t))),
    )


def _reasons(old: Entry, new: Entry, policy: tuple[str, ...]) -> tuple[str, ...]:
    reasons: list[str] = []
    if policy:
        reasons.append(f"policy differs: {', '.join(policy)}")
    for side, entry in (("old", old), ("new", new)):
        if entry.measurement.reason is not None:
            reasons.append(f"not taken in the {side} snapshot: {entry.measurement.reason}")
    if reasons and (old.measurement.reason is not None or new.measurement.reason is not None):
        return tuple(reasons)
    a, b = old.measurement, new.measurement
    if a.definition_version != b.definition_version:
        reasons.append(f"definition version {a.definition_version} -> {b.definition_version}")
    if a.kind is not b.kind:
        reasons.append(f"kind {a.kind.value} -> {b.kind.value}")
    if a.population != b.population:
        reasons.append(f"population {a.population} -> {b.population}")
    if (old.coverage is None) != (new.coverage is None):
        reasons.append(f"term sets are in the {'old' if old.coverage else 'new'} snapshot only")
    elif old.coverage and new.coverage and old.coverage.better != new.coverage.better:
        reasons.append(f"numerator reading {old.coverage.better} -> {new.coverage.better}")
    return tuple(reasons)


def _compare_entries(old: Entry, new: Entry, policy: tuple[str, ...]) -> Result:
    a, b = old.measurement, new.measurement
    if reasons := _reasons(old, new, policy):
        return Result(a.id, reasons)
    if a.kind is MeasurementKind.COUNT:
        return Result(a.id, (), a, b, (b.value or 0) - (a.value or 0))
    if a.kind is MeasurementKind.HISTOGRAM:
        return Result(a.id, (), a, b, changed=a.buckets != b.buckets)
    change = _split(old.coverage, new.coverage) if old.coverage and new.coverage else None
    return Result(a.id, (), a, b, _ratio_delta(a, b), change)


def compare(old: Snapshot, new: Snapshot) -> Comparison:
    """Compare ``new`` with ``old``, measurement by measurement: those of ``old`` in its order, then new ones.

    A measurement that cannot be compared (:func:`_reasons`) is a :class:`Result` with its reasons and no
    values; the others are compared whatever happened to their neighbours.
    """
    policy = old.shaping.differing(new.shaping)
    news = {e.measurement.id: e for e in new.entries}
    olds = {e.measurement.id for e in old.entries}
    results = [
        _compare_entries(e, news[e.measurement.id], policy)
        if e.measurement.id in news
        else Result(e.measurement.id, ("measured in the old snapshot only",))
        for e in old.entries
    ]
    results += [Result(i, ("measured in the new snapshot only",)) for i in news if i not in olds]
    return Comparison(tuple(results))


def render_text(comparison: Comparison) -> str:
    """The comparison for a terminal: a line per measurement, its split below it, then the notes."""
    refused = sum(1 for r in comparison.results if r.reasons)
    total = len(comparison.results)
    lines = [f"{total} measurement(s): {total - refused} compared, {refused} not comparable"]
    for r in comparison.results:
        if r.before is None or r.after is None:  # only a compared result has both sides
            lines.append(f"{r.id}: not comparable: {'; '.join(r.reasons)}")
            continue
        lines.append(f"{r.id}: {show(r.before)} -> {show(r.after)}{_delta_text(r)}")
        if r.change is not None:
            counts = r.change.counts()
            lines.append("  " + ", ".join(f"{name.replace('_', ' ')} {counts[name]}" for name in CHANGES))
    lines += ["", *(f"Note: {note}" for note in comparison.notes)]
    return "\n".join(lines)


def show(m: Measurement) -> str:
    if m.kind is MeasurementKind.RATIO:
        return f"{m.numerator}/{m.denominator}"
    if m.kind is MeasurementKind.COUNT:
        return str(m.value)
    return "{" + ", ".join(f"{v}: {n}" for v, n in m.buckets) + "}"


def _delta_text(r: Result) -> str:
    if r.changed is not None:
        return " (changed)" if r.changed else " (unchanged)"
    return f" (delta {r.delta})" if r.delta is not None else " (no delta: an empty population)"
