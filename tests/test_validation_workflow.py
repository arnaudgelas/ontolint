"""The mutation job has the time it measured, takes a narrowed target safely, and always uploads (#151, #71)."""

# ruff: noqa: PLR2004

from __future__ import annotations

import re
from pathlib import Path

WORKFLOW = (Path(__file__).parent.parent / ".github" / "workflows" / "validation.yml").read_text(encoding="utf-8")
JOB = WORKFLOW[WORKFLOW.index("\n  mutation:") :]
TIMEOUT_MINUTES = int(re.search(r"timeout-minutes: (\d+)", JOB)[1])  # type: ignore[index]
# Run 46122669870 (3104 mutants): a 15 minute coverage pre-scan, 95 minutes of mutants, then about 9 minutes with no
# output. It was cut at 120 minutes, so a run needs 120 minutes at least, and the count of mutants only grows.
MEASURED_MINUTES = 120
HEADROOM = 1.5


def test_the_job_timeout_leaves_headroom_over_the_measured_run() -> None:
    assert TIMEOUT_MINUTES >= MEASURED_MINUTES * HEADROOM


def test_the_dispatch_takes_a_paths_input_that_defaults_to_the_whole_scope() -> None:
    inputs = WORKFLOW[WORKFLOW.index("  workflow_dispatch:") : WORKFLOW.index("  pull_request:")]
    assert re.search(r"\n      paths:\n(?:        .*\n)*?        default: \"\"", inputs)


def test_the_targets_are_checked_after_the_checkout_and_before_anything_is_installed() -> None:
    check = JOB.index("- name: Check the mutation targets")
    assert JOB.index("- name: Check out repository") < check < JOB.index("- name: Set up uv")
    assert "run: python3 .github/scripts/mutation_targets.py" in JOB[check : JOB.index("- name: Set up uv")]


def test_the_paths_input_reaches_the_script_and_the_command_only_by_the_environment() -> None:
    assert WORKFLOW.count("inputs.paths") == 1  # the env line below; no script interpolates it
    assert "MUTATION_PATHS: ${{ inputs.paths }}" in JOB


def test_the_narrowed_targets_are_passed_to_gremlins() -> None:
    assert '--gremlin-targets="$MUTATION_PATHS"' in JOB


def test_the_reports_are_uploaded_whatever_the_outcome() -> None:
    upload = JOB[JOB.index("- name: Upload mutation reports") :]
    assert re.match(r"- name: Upload mutation reports\n\s+if: always\(\)", upload)
