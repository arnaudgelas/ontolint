"""Opt-in timing of a run (``--timing``, issue #174).

All values are integer milliseconds, each duration rounded to the nearest millisecond (halves to even, as
:func:`round`) *after* a unit's readings are added, so a unit that runs for several files adds its exact durations.

* ``load_ms``: reading the inputs (the ontologies, the shapes graph, the pattern library), over every file of the run.
* ``units_ms``: the time of each unit that ran rules, failed or timed out included.  A unit is a rule module for the
  graph rules (``"owl"``, ``"shacl"`` ...: the rules of a module run together) and one adapter for each adapter rule
  (``"adapter:SHACL001"``).  Units never overlap, so their times can be added.
* ``rules_ms``: for each rule that ran, the time of its unit.  Rules of one module share their module's time, so these
  values must not be added up.  A rule that was skipped or unsupported did not run and is absent, never zero.
* ``total_ms``: the wall time from the start of the run to the end of the last rule; writing the report is excluded.

The clock is injected (default :func:`time.perf_counter`, monotonic), and nothing patches :mod:`time`.  The timing is
never part of a baseline, a fingerprint, a quality snapshot, a DQV file or the Markdown summary.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Generator, Iterable
from contextlib import contextmanager
from dataclasses import dataclass, field

type Clock = Callable[[], float]


@dataclass(frozen=True)
class Timing:
    """The timing of one run, in integer milliseconds (see the module docstring)."""

    total_ms: int
    load_ms: int
    units_ms: dict[str, int]
    rules_ms: dict[str, int]


def _ms(seconds: float) -> int:
    return round(seconds * 1000)


@dataclass
class Recorder:
    """Collects the durations of one run; every context manager records its time when the block raises too."""

    clock: Clock = time.perf_counter
    _start: float = field(init=False)
    _load: float = field(default=0.0, init=False)
    _units: dict[str, float] = field(default_factory=dict[str, float], init=False)
    _rules: dict[str, set[str]] = field(default_factory=dict[str, set[str]], init=False)

    def __post_init__(self) -> None:
        self._start = self.clock()

    @contextmanager
    def load(self) -> Generator[None]:
        began = self.clock()
        try:
            yield
        finally:
            self._load += self.clock() - began

    @contextmanager
    def unit(self, name: str, rules: Iterable[str]) -> Generator[None]:
        """Time a unit that runs ``rules``."""
        began = self.clock()
        try:
            yield
        finally:
            self._units[name] = self._units.get(name, 0.0) + self.clock() - began
            self._rules.setdefault(name, set()).update(rules)

    def finish(self) -> Timing:
        total = self.clock() - self._start
        rules = {rule: _ms(self._units[name]) for name, ids in self._rules.items() for rule in ids}
        return Timing(
            _ms(total),
            _ms(self._load),
            {name: _ms(seconds) for name, seconds in sorted(self._units.items())},
            dict(sorted(rules.items())),
        )


def to_dict(timing: Timing) -> dict[str, object]:
    """The ``timing`` object of the JSON report and the ``ontolintTiming`` property of the SARIF run."""
    return {
        "total_ms": timing.total_ms,
        "load_ms": timing.load_ms,
        "units_ms": dict(timing.units_ms),
        "rules_ms": dict(timing.rules_ms),
    }


def footer(timing: Timing, slowest: int = 3) -> str:
    """The last line of the text report."""
    top = sorted(timing.units_ms.items(), key=lambda item: (-item[1], item[0]))[:slowest]
    ranked = ", ".join(f"{name} {ms} ms" for name, ms in top) or "none"
    return f"Timing: total {timing.total_ms} ms; load {timing.load_ms} ms; slowest: {ranked}"
