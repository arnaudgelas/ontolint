"""Check the ``paths`` input of the mutation job before anything is installed (issue #151, PR #296).

The input is a comma-separated list of files and directories that narrows a manual mutation run.  pytest-gremlins
accepts any text there: a path that exists nowhere is not an error but "No gremlins found", it exits 0 after the
whole coverage pre-scan and writes no report, and the policy gate then fails with "Mutation report not found".  So each
item is checked here, from the repository root, and a bad one is named:

* it is written as ``src/ontolint/`` followed by plain path segments (letters, digits, ``_``, ``-``, ``.``), with no
  empty, ``.`` or ``..`` segment;
* it exists, is not a symbolic link, and is a directory or a ``.py`` file;
* it lies within the scope the project configures (``[tool.pytest-gremlins].paths`` of ``pyproject.toml``): a run
  narrowed to a module the policy does not cover would be judged by a gate and pardons written for another scope;
* there are at most :data:`MAX_ITEMS` items and the text is at most :data:`MAX_LENGTH` characters.

A narrowed run measures part of the scope, so it cannot be the ``blocking`` run.  The text is read from the environment
(``MUTATION_PATHS``, ``MUTATION_GATE_MODE``), never from the command line or interpolated into a script.
"""

from __future__ import annotations

import os
import re
import sys
import tomllib
from pathlib import Path

PREFIX = "src/ontolint/"
SEGMENT = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
MAX_ITEMS = 20
MAX_LENGTH = 500


def configured_scope(root: Path) -> list[str]:
    """The files and directories ``[tool.pytest-gremlins].paths`` names."""
    document = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return list(document["tool"]["pytest-gremlins"]["paths"])


def _within(item: str, scope: list[str]) -> bool:
    return any(item == entry or item.startswith(f"{entry}/") for entry in scope)


def problems(paths: str, mode: str, root: Path) -> list[str]:
    """The reasons ``paths`` cannot narrow a run in ``mode``; empty when it can."""
    if not paths:
        return []
    if mode == "blocking":
        return ["a run narrowed by paths measures part of the scope, so it cannot be blocking"]
    if len(paths) > MAX_LENGTH:
        return [f"paths is {len(paths)} characters long; at most {MAX_LENGTH}"]
    items = paths.split(",")
    if len(items) > MAX_ITEMS:
        return [f"paths has {len(items)} items; at most {MAX_ITEMS}"]
    scope = configured_scope(root)
    found: list[str] = []
    for item in items:
        segments = item.removeprefix(PREFIX).split("/")
        if not item.startswith(PREFIX) or not all(SEGMENT.fullmatch(s) and s not in {".", ".."} for s in segments):
            found.append(
                f"'{item}' is not a path of the form {PREFIX}NAME[/NAME...] "
                "(letters, digits, _ - . only; no empty, '.' or '..' segment)"
            )
            continue
        target = root / item
        if target.is_symlink() or not target.exists() or not target.resolve().is_relative_to(root.resolve()):
            found.append(f"'{item}' is not an existing file or directory (a symbolic link is refused)")
        elif not (target.is_dir() or (target.is_file() and item.endswith(".py"))):
            found.append(f"'{item}' is neither a directory nor a .py file")
        elif not _within(item, scope):
            found.append(
                f"'{item}' is outside the configured scope; it must be one of, or lie within: {', '.join(scope)}"
            )
    return found


def main() -> int:
    found = problems(os.environ.get("MUTATION_PATHS", ""), os.environ.get("MUTATION_GATE_MODE", ""), Path.cwd())
    for reason in found:
        sys.stdout.write(f"::error::{reason}\n")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
