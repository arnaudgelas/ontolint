"""Backwards-compatible import surface for the original ``ontolint.ontolint`` module.

The implementation lives in :mod:`ontolint.engine`, :mod:`ontolint.rules`,
:mod:`ontolint.adapters`, :mod:`ontolint.reporting` and :mod:`ontolint.cli`.
"""

from __future__ import annotations

import subprocess  # noqa: F401 -- tests patch ``ontolint.ontolint.subprocess.run``.
import sys

from .adapters.robot import robot_profile_issues as _robot_profile_issues
from .adapters.shacl import shacl_issues as _shacl_issues
from .cli import main
from .linter import Linter
from .models import Finding
from .reporting import fingerprint
from .reporting import to_sarif as _sarif
from .rules.specs import FIXES, SEVERITY

__all__ = [
    "FIXES",
    "SEVERITY",
    "Finding",
    "Linter",
    "_robot_profile_issues",
    "_sarif",
    "_shacl_issues",
    "fingerprint",
    "main",
]

if __name__ == "__main__":
    sys.exit(main())
