"""The validation gate script is the single definition of "green", for CI and developers alike."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
PYRIGHT_FAILURE = 3
SCRIPT = ROOT / "scripts" / "gate.py"
spec = importlib.util.spec_from_file_location("gate", SCRIPT)
assert spec is not None
assert spec.loader is not None
gate = importlib.util.module_from_spec(spec)
sys.modules["gate"] = gate
spec.loader.exec_module(gate)


def _commands(steps: tuple[tuple[str, tuple[str, ...]], ...]) -> list[str]:
    return [" ".join(argv) for _title, argv in steps]


def test_the_gate_runs_every_required_check_in_check_only_mode() -> None:
    assert _commands(gate.STEPS) == [
        "ruff format --check",
        "ruff check",
        "pyright",
        "mypy",
        "mypy --platform win32",
        "pytest -n auto -W error",
        "pip-audit",
        "uv build",
    ]


def test_fix_mode_only_adds_autofixes_before_the_same_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    ran: list[str] = []
    monkeypatch.setattr(gate, "run_step", lambda _title, argv: ran.append(" ".join(argv)) or 0)
    assert gate.main(["--fix"]) == 0
    assert ran == ["ruff format", "ruff check --fix", *_commands(gate.STEPS)]


def test_the_gate_stops_at_the_first_failing_step(monkeypatch: pytest.MonkeyPatch) -> None:
    ran: list[str] = []

    def run_step(_title: str, argv: tuple[str, ...]) -> int:
        ran.append(" ".join(argv))
        return PYRIGHT_FAILURE if argv == ("pyright",) else 0

    monkeypatch.setattr(gate, "run_step", run_step)
    assert gate.main([]) == PYRIGHT_FAILURE
    assert ran == ["ruff format --check", "ruff check", "pyright"]


def test_tools_run_in_the_locked_environment_except_uv_itself() -> None:
    assert gate._command(("mypy", "--platform", "win32")) == ["uv", "run", "mypy", "--platform", "win32"]
    assert gate._command(("uv", "build")) == ["uv", "build"]


def test_ci_and_the_contributor_docs_use_the_gate_script() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "run: uv run python scripts/gate.py\n" in workflow
    for tool in ("pytest", "mypy", "pyright", "ruff", "pip-audit"):
        assert f"uv run {tool}" not in workflow, f"ci.yml runs {tool} outside the gate"
    assert "scripts/gate.py" in (ROOT / "docs" / "adding-rules.md").read_text(encoding="utf-8")
    assert "scripts/gate.py" in (ROOT / "README.md").read_text(encoding="utf-8")
