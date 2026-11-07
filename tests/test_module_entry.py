"""``python -m ontolint`` and the historical ``python -m ontolint.ontolint`` start without warnings."""

from __future__ import annotations

import subprocess
import sys

import pytest


@pytest.mark.parametrize("module", ["ontolint", "ontolint.ontolint"])
def test_module_entry_points_run_without_warnings(module: str) -> None:
    done = subprocess.run(  # noqa: S603 -- fixed interpreter and module names.
        [sys.executable, "-W", "error", "-m", module, "--version"], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.startswith("ontolint ")
    assert done.stderr == ""
