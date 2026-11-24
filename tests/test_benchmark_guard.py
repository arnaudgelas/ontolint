"""The benchmarks are skipped without ``ONTOLINT_BENCH=1`` and collected by ``-m benchmark`` (issue #164).

A benchmark that nothing runs is no evidence, and one that silently never runs looks like one that passes.  These tests
run pytest on ``tests/benchmarks`` in a child process, as the weekly job does, and check both halves: without the
variable every benchmark is skipped with its reason, and ``-m benchmark`` selects every test of the directory (the
marker is on the whole module), so ``benchmarks.yml`` cannot select nothing and pass.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
BENCHMARKS = ROOT / "tests" / "benchmarks" / "test_linter_benchmarks.py"
SWITCH = "ONTOLINT_BENCH"


def _pytest(*arguments: str, switch: str | None) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != SWITCH}
    if switch is not None:
        env[SWITCH] = switch
    return subprocess.run(  # noqa: S603 -- our own interpreter and fixed arguments
        [sys.executable, "-m", "pytest", "--no-cov", "-p", "no:randomly", "-p", "no:cacheprovider", *arguments],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
        check=False,
        timeout=120,
    )


def _declared() -> list[str]:
    tree = ast.parse(BENCHMARKS.read_text(encoding="utf-8"))
    return sorted(n.name for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_"))


def test_the_marker_selects_every_benchmark_whether_or_not_the_switch_is_set() -> None:
    declared = _declared()
    assert declared  # a scan that found nothing would make the comparison below pass for nothing

    for switch in (None, "1"):
        done = _pytest("-m", "benchmark", "--collect-only", "-q", "tests/benchmarks", switch=switch)

        assert done.returncode == 0, done.stdout + done.stderr
        collected = {re.split(r"[:\[]", line.split("::")[1])[0] for line in done.stdout.splitlines() if "::" in line}
        assert collected == set(declared), switch


def test_without_the_switch_every_benchmark_is_skipped_and_says_why() -> None:
    done = _pytest("-m", "benchmark", "-q", "-rs", "tests/benchmarks", switch=None)

    assert done.returncode == 0, done.stdout + done.stderr
    assert "passed" not in done.stdout
    assert "failed" not in done.stdout
    assert "set ONTOLINT_BENCH=1 to run benchmarks" in done.stdout
    assert re.search(r"\b\d+ skipped\b", done.stdout)


def test_with_the_switch_a_benchmark_runs() -> None:
    done = _pytest("-q", "tests/benchmarks", "-k", "test_deep_chain_within_budget", switch="1")

    assert done.returncode == 0, done.stdout + done.stderr
    assert "1 passed" in done.stdout
