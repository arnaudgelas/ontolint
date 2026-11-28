"""The mutation job has the time it measured, takes a narrowed target safely, and always uploads (#151, #71)."""

# ruff: noqa: PLR2004

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

WORKFLOW = (Path(__file__).parent.parent / ".github" / "workflows" / "validation.yml").read_text(encoding="utf-8")
JOB = WORKFLOW[WORKFLOW.index("\n  mutation:") :]
STEP = re.compile(r"- name: Check the mutation targets\n\s+run: \|\n(?P<script>(?:\s{10}.*\n)+)")
TIMEOUT_MINUTES = int(re.search(r"timeout-minutes: (\d+)", JOB)[1])  # type: ignore[index]
# Run 46122669870 (3104 mutants): a 15 minute coverage pre-scan, 95 minutes of mutants, then about 9 minutes with no
# output. It was cut at 120 minutes, so a run needs 120 minutes at least, and the count of mutants only grows.
MEASURED_MINUTES = 120
HEADROOM = 1.5


def _script() -> str:
    match = STEP.search(JOB)
    assert match, "validation.yml has no 'Check the mutation targets' step in the mutation job"
    return match["script"]


def _check(paths: str, mode: str = "advisory") -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- the fixed script of the workflow, a test value in the environment
        ["bash", "-c", _script()],  # noqa: S607
        env={"MUTATION_PATHS": paths, "MUTATION_GATE_MODE": mode, "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_job_timeout_leaves_headroom_over_the_measured_run() -> None:
    assert TIMEOUT_MINUTES >= MEASURED_MINUTES * HEADROOM


def test_the_dispatch_takes_a_paths_input_that_defaults_to_the_whole_scope() -> None:
    inputs = WORKFLOW[WORKFLOW.index("  workflow_dispatch:") : WORKFLOW.index("  pull_request:")]
    assert re.search(r"\n      paths:\n(?:        .*\n)*?        default: \"\"", inputs)


@pytest.mark.parametrize(
    "paths",
    ["", "src/ontolint/imports.py", "src/ontolint/imports.py,src/ontolint/worker.py", "src/ontolint/rules"],
)
def test_no_paths_or_paths_under_the_package_are_accepted(paths: str) -> None:
    assert _check(paths).returncode == 0


@pytest.mark.parametrize(
    "paths",
    [
        "src/ontolint/../../etc",
        "/etc/passwd",
        "tests",
        "src/ontolint/a.py,",
        ",src/ontolint/a.py",
        "src/ontolint/a.py,,src/ontolint/b.py",
        "src/ontolint/a.py b.py",
        "src/ontolint/$(id).py",
        "src/ontolint/a.py;rm -rf x",
        "src/ontolint/a.py\nsrc/ontolint/b.py",
        "--gremlin-targets=x",
    ],
)
def test_other_paths_are_refused_with_a_reason(paths: str) -> None:
    result = _check(paths)
    assert result.returncode != 0
    assert "::error::" in result.stdout + result.stderr


def test_a_narrowed_run_cannot_be_blocking() -> None:
    assert _check("src/ontolint/imports.py", "blocking").returncode != 0
    assert _check("", "blocking").returncode == 0


def test_the_check_runs_before_the_checkout_and_the_input_reaches_the_shell_only_by_environment() -> None:
    assert JOB.index("Check the mutation targets") < JOB.index("Check out repository")
    assert WORKFLOW.count("inputs.paths") == 1  # the env line below; no script interpolates it
    assert "MUTATION_PATHS: ${{ inputs.paths }}" in JOB


def test_the_narrowed_targets_are_passed_to_gremlins() -> None:
    assert '--gremlin-targets="$MUTATION_PATHS"' in JOB


def test_the_reports_are_uploaded_whatever_the_outcome() -> None:
    upload = JOB[JOB.index("- name: Upload mutation reports") :]
    assert re.match(r"- name: Upload mutation reports\n\s+if: always\(\)", upload)
