"""The fuzz workflow refuses a time budget its jobs cannot honour, and the fuzzer's oracle knows every refusal (#284, #285)."""

# ruff: noqa: PLR2004

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from ontolint.adapters import shacl
from ontolint.models import ExecutionStatus, RuleExecution
from fuzz import fuzzer

WORKFLOW = (Path(__file__).parent.parent / ".github" / "workflows" / "fuzz.yml").read_text(encoding="utf-8")
STEP = re.compile(r"- name: Check the time budget\n\s+run: \|\n(?P<script>(?:\s{10}.*\n)+)")
TIMEOUT_MINUTES = int(re.search(r"timeout-minutes: (\d+)", WORKFLOW)[1])  # type: ignore[index]
MAX_SECONDS = 1800
OVERHEAD_SECONDS = 600  # checkout, dependencies, shrinking a crasher, the upload


def _script() -> str:
    match = STEP.search(WORKFLOW)
    assert match, "fuzz.yml has no 'Check the time budget' step"
    return match["script"]


def _check(seconds: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- the fixed script of the workflow, a test value in the environment
        ["bash", "-c", _script()],  # noqa: S607
        env={"FUZZ_SECONDS": seconds, "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("seconds", ["1", "600", str(MAX_SECONDS)])
def test_a_budget_that_fits_the_job_is_accepted(seconds: str) -> None:
    assert _check(seconds).returncode == 0


@pytest.mark.parametrize("seconds", ["6000", str(MAX_SECONDS + 1), "0", "", "-5", "10m", "1.5", "99999999999999999999"])
def test_a_budget_that_does_not_fit_or_is_not_a_number_is_refused_with_a_reason(seconds: str) -> None:
    result = _check(seconds)
    assert result.returncode != 0
    assert "::error::" in result.stdout + result.stderr


def test_the_check_runs_before_anything_is_installed_or_fuzzed() -> None:
    assert WORKFLOW.index("Check the time budget") < WORKFLOW.index("Check out repository")


def test_the_largest_accepted_budget_fits_the_job_timeout() -> None:
    assert str(MAX_SECONDS) in _script()
    assert MAX_SECONDS + OVERHEAD_SECONDS <= TIMEOUT_MINUTES * 60


# --- the oracle (#284) ---------------------------------------------------------------------------------------------


def _summaries() -> list[str]:
    names = sorted(n for n in dir(shacl) if n.endswith("_SUMMARY"))
    return [*(getattr(shacl, n) for n in names), shacl.ShapesNotWellFormed.summary]


def test_there_is_a_summary_constant_to_check() -> None:
    assert len(_summaries()) >= 5


@pytest.mark.parametrize("summary", _summaries())
def test_the_fuzzer_takes_each_shapes_refusal_summary_for_a_reported_refusal(summary: str) -> None:
    assert summary in shacl.SHAPES_REFUSAL_SUMMARIES
    assert fuzzer.is_shapes_refusal(RuleExecution("SHACL001", ExecutionStatus.FAILED, summary))


def test_a_failure_of_another_rule_or_an_unknown_detail_is_not_a_refusal() -> None:
    assert not fuzzer.is_shapes_refusal(RuleExecution("SHQ001", ExecutionStatus.FAILED, shacl.NODE_SHAPE_PATH_SUMMARY))
    assert not fuzzer.is_shapes_refusal(RuleExecution("SHACL001", ExecutionStatus.FAILED, "KeyError: 'x'"))
