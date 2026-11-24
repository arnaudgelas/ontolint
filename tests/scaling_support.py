"""The time of a step at two sizes, and the check that it grew like the input.

Shared by ``tests/test_scaling.py`` (single steps, in the normal suite) and ``tests/benchmarks`` (the whole
linter, in the weekly benchmark job of ``docs/ci-schedule.md``).  Multiplying the input by eight must cost well
under the sixty-four-fold time of a quadratic step, whatever the speed of the machine: the check is a ratio,
never a number of seconds.  The time is CPU time, alternated between the sizes, as a run beside other workers
is slowed by them as a whole and the larger input more.
"""

from __future__ import annotations

import time
from collections.abc import Callable

GROWTH = 8  # a wide step keeps linear and quadratic times apart when a busy machine inflates both
MAX_RATIO = GROWTH**2 / 2  # a quadratic step gives at least 64; a linear one 8, up to 24 when dicts outgrow the cache
ATTEMPTS = 5

Step = Callable[[], object]


def best_times(small: Step, large: Step, attempts: int = ATTEMPTS) -> tuple[float, float]:
    """The fastest of several runs of each step, alternating them so both see the same load on a busy machine."""
    best = [float("inf"), float("inf")]
    for _attempt in range(attempts):  # the fastest run discards scheduling noise from a loaded machine
        for side, step in enumerate((small, large)):
            started = time.process_time()
            step()
            best[side] = min(best[side], time.process_time() - started)
    return best[0], best[1]


def assert_grows_linearly(small: Step, large: Step, what: str, attempts: int = ATTEMPTS) -> None:
    """Fail when ``large`` (``GROWTH`` times the input of ``small``) costs ``MAX_RATIO`` times as much or more."""
    fast, slow = best_times(small, large, attempts)
    assert slow / fast < MAX_RATIO, f"{what}: {fast:.3f} s, then {GROWTH} times the input: {slow:.3f} s"
