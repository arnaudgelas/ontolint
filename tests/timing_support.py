"""The time limit of the tests that pin a scan to linear time.

Each such test guards a fix for quadratic or exponential backtracking, whose input is sized so that the old
code takes far longer than the limit. The limit is generous because a GitHub runner under coverage is about
five times slower than a laptop: 0.2 s locally reached 1.09 s there, which failed the 0.13.0 release run at
the former 1 s limit.
"""

from __future__ import annotations

LINEAR_SCAN_SECONDS = 10
