"""Run the project's validation gate: the one command that decides whether a change is green.

    uv run python scripts/gate.py          # check only, as CI runs it
    uv run python scripts/gate.py --fix    # first apply ruff formatting and autofixes

CI (``.github/workflows/ci.yml``) calls this script and nothing else, so "green locally" and
"green in CI" mean the same thing.  The steps run in order and the gate stops at the first
failure.  ``pip-audit`` needs network access to the vulnerability database.
"""

# ruff: noqa: S603, S607 -- runs fixed developer tools from the project environment.

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

FIXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Format with Ruff", ("ruff", "format")),
    ("Autofix with Ruff", ("ruff", "check", "--fix")),
)

STEPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Check formatting", ("ruff", "format", "--check")),
    ("Lint with Ruff", ("ruff", "check")),
    ("Type check with Pyright", ("pyright",)),
    ("Type check with mypy", ("mypy",)),
    ("Type check with mypy for Windows", ("mypy", "--platform", "win32")),
    ("Run tests, warnings as errors", ("pytest", "-n", "auto", "-W", "error")),
    ("Audit dependencies", ("pip-audit",)),
    ("Build distributions", ("uv", "build")),
)


def _command(argv: tuple[str, ...]) -> list[str]:
    """Run project tools through ``uv run`` so they use the locked environment; ``uv`` runs as is."""
    return list(argv) if argv[0] == "uv" else ["uv", "run", *argv]


def run_step(title: str, argv: tuple[str, ...]) -> int:
    """Run one step, folded into a log group on GitHub Actions; return its exit status."""
    github = os.environ.get("GITHUB_ACTIONS") == "true"
    print(f"::group::{title}" if github else f"==> {title}", flush=True)
    started = time.monotonic()
    status = subprocess.run(_command(argv), check=False).returncode
    if github:
        print("::endgroup::", flush=True)
    outcome = "ok" if status == 0 else f"failed with exit status {status}"
    print(f"{title}: {outcome} ({time.monotonic() - started:.0f} s)", flush=True)
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the ontolint validation gate.")
    parser.add_argument("--fix", action="store_true", help="apply ruff formatting and autofixes first")
    args = parser.parse_args(argv)
    for title, step in (*FIXES, *STEPS) if args.fix else STEPS:
        status = run_step(title, step)
        if status != 0:
            return status
    print("Gate passed.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
