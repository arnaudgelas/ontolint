"""Every `gremlin: pardon` pragma is live, in scope, covers one mutant and is listed in docs/mutation-pardons.md.

A pragma pardons every mutant on its target line, not only the one its justification is about, so a pragma
over a line with several mutants hides the others from the run. Code inserted between a standalone pragma
and its line moves the pardon to the new line. Neither shows in a run that passes, so these checks read the
source the way pytest-gremlins does (its own instrumentation, with the operators of `pyproject.toml`).
"""

from __future__ import annotations

import importlib
import re
import tomllib
from pathlib import Path

from pytest_gremlins.instrumentation.gremlin import Gremlin
from pytest_gremlins.instrumentation.transformer import get_default_registry, transform_source
from test_mutation_pardon_audit import FROZEN

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "src"
AUDIT = ROOT / "docs" / "mutation-pardons.md"
PRAGMA = re.compile(r"#\s*gremlin:\s*pardon\[")
ROW = re.compile(r"^\| `(?P<module>[^`]+)` \| `(?P<code>(?:[^`]|``)+)` \| (?P<mutant>[^|]+) \|")


def _config() -> dict[str, list[str]]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["pytest-gremlins"]


def _scope() -> set[Path]:
    files: set[Path] = set()
    for entry in _config()["paths"]:
        path = ROOT / entry
        files.update(path.rglob("*.py") if path.is_dir() else [path])
    return files


def _gremlins(path: Path) -> list[Gremlin]:
    operators = get_default_registry().get_all(enabled=_config()["operators"])
    gremlins, _ = transform_source(path.read_text(), str(path), operators)
    return gremlins


def _pragma_files() -> list[Path]:
    return sorted(p for p in SOURCE.rglob("*.py") if PRAGMA.search(p.read_text()))


def _code(lines: list[str], number: int) -> str:
    """The pardoned line, stripped; a decorator is named with the line it decorates, which tells them apart."""
    code = lines[number - 1].strip()
    return f"{code} {lines[number].strip()}" if code.startswith("@") else code


def _pardoned() -> dict[tuple[str, str], list[str]]:
    """``(module, pardoned code) -> descriptions of the mutants it pardons``, for every pragma in scope."""
    found: dict[tuple[str, str], list[str]] = {}
    for path in sorted(_scope() & set(_pragma_files())):
        lines = path.read_text().splitlines()
        for gremlin in _gremlins(path):
            if gremlin.pardoned:
                key = (path.relative_to(ROOT).as_posix(), _code(lines, gremlin.line_number))
                found.setdefault(key, []).append(f"{gremlin.operator_name}: {gremlin.description}")
    return found


def _audited() -> dict[tuple[str, str], list[str]]:
    rows: dict[tuple[str, str], list[str]] = {}
    for line in AUDIT.read_text().splitlines():
        if match := ROW.match(line):
            key = (match["module"], match["code"].replace("``", "`"))
            rows.setdefault(key, []).append(match["mutant"].strip())
    return rows


def test_every_pragma_is_in_the_mutation_scope() -> None:
    # A pragma outside `paths` pardons nothing today and would pardon without review once its module enters.
    outside = [p.relative_to(ROOT).as_posix() for p in _pragma_files() if p not in _scope()]
    assert outside == []


def test_every_pragma_pardons_a_mutant() -> None:
    dead: list[str] = []
    for path in sorted(_scope() & set(_pragma_files())):
        mutated = {g.line_number for g in _gremlins(path)}
        lines = path.read_text().splitlines()
        for number, line in enumerate(lines, start=1):
            if PRAGMA.search(line):
                target = number + 1 if line.lstrip().startswith("#") else number
                if target not in mutated:
                    dead.append(f"{path.relative_to(ROOT).as_posix()}:{number}")
    assert dead == []


def test_every_pragma_pardons_exactly_one_mutant() -> None:
    # Put the equivalent expression on a line of its own, so the other mutants of the statement still run.
    crowded = {key: mutants for key, mutants in _pardoned().items() if len(mutants) != 1}
    assert crowded == {}


def test_the_audit_lists_exactly_the_active_pardons() -> None:
    # A new pragma, or an edit to a pardoned line, needs a reviewed row in docs/mutation-pardons.md.
    assert _audited() == _pardoned()


REASON = re.compile(r"#\s*gremlin:\s*pardon\[(?P<reason>[^\]]*)\]")


def _pragmas() -> list[tuple[Path, int, str]]:
    """``(file, line number, reason)`` of every pragma in the mutation scope."""
    return [
        (path, number, match["reason"])
        for path in sorted(_scope() & set(_pragma_files()))
        for number, line in enumerate(path.read_text().splitlines(), start=1)
        if (match := REASON.search(line))
    ]


def test_every_pragma_has_a_reason_the_policy_allows() -> None:
    # docs/mutation-policy.md, survivor triage item 3.
    assert sorted({reason for _, _, reason in _pragmas()} - {"equivalent", "untestable"}) == []


def test_every_untestable_pardon_is_a_frozen_dataclass_the_normal_suite_kills() -> None:
    """The policy allows `untestable` only on a frozen decorator whose mutant a normal-suite test kills (#71)."""
    unbacked: list[str] = []
    for path, number, reason in _pragmas():
        if reason != "untestable":
            continue
        lines = path.read_text().splitlines()
        decorator, header = lines[number].strip(), lines[number + 1].strip()
        name = re.fullmatch(r"class (\w+)[(:].*", header)
        module = importlib.import_module(".".join(path.relative_to(SOURCE).with_suffix("").parts))
        if decorator != "@dataclass(frozen=True)" or name is None or getattr(module, name[1], None) not in FROZEN:
            unbacked.append(f"{path.relative_to(ROOT).as_posix()}:{number}")
    assert unbacked == []
