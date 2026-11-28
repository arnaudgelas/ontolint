"""The ``paths`` input of the mutation job names something that can be mutated (issue #151, PR #296).

pytest-gremlins treats a target that exists nowhere as "No gremlins found": it exits 0 after the whole coverage
pre-scan and writes no report, so the policy gate then fails with "Mutation report not found".  The check of
``.github/scripts/mutation_targets.py`` refuses such a target, and the others it cannot run, before anything is
installed.
"""

# ruff: noqa: PLR2004

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).parent.parent
SCRIPT = REPO / ".github" / "scripts" / "mutation_targets.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("mutation_targets", SCRIPT)
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository whose configured scope is a.py and the directory pkg; b.py is a module outside it."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest-gremlins]\npaths = ["src/ontolint/a.py", "src/ontolint/pkg"]\n', encoding="utf-8"
    )
    package = tmp_path / "src" / "ontolint"
    (package / "pkg" / "sub").mkdir(parents=True)
    for name in ("a.py", "b.py", "pkg/m.py", "pkg/sub/n.py", "pkg/data.txt"):
        (package / name).write_text("x = 1\n", encoding="utf-8")
    return tmp_path


def _run(repo: Path, paths: str, mode: str = "advisory") -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- the checked-in script, a test value in the environment
        [sys.executable, "-I", str(SCRIPT)],
        cwd=repo,
        env={"MUTATION_PATHS": paths, "MUTATION_GATE_MODE": mode, "PATH": os.environ.get("PATH", "")},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "paths",
    [
        "",
        "src/ontolint/a.py",  # a file of the scope
        "src/ontolint/pkg",  # a directory of the scope
        "src/ontolint/pkg/m.py",  # a file within a directory of the scope
        "src/ontolint/pkg/sub",  # a directory within it
        "src/ontolint/a.py,src/ontolint/pkg/m.py",
    ],
)
def test_a_target_that_exists_within_the_scope_is_accepted(repo: Path, paths: str) -> None:
    result = _run(repo, paths)
    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize(
    ("paths", "named"),
    [
        ("src/ontolint/does-not-exist", "src/ontolint/does-not-exist"),  # the case of PR #296: valid text, no such path
        ("src/ontolint/a.py,src/ontolint/pkg/gone.py", "src/ontolint/pkg/gone.py"),  # the bad item is the one named
        ("src/ontolint/pkg/data.txt", "src/ontolint/pkg/data.txt"),  # exists, is not Python
        ("src/ontolint/b.py", "src/ontolint/b.py"),  # exists, outside the configured scope
        ("src/ontolint/.", "src/ontolint/."),  # the whole package: outside the scope as a whole
        ("src/ontolint/pkg/", "src/ontolint/pkg/"),  # an empty segment
        ("src/ontolint/pkg/../b.py", "src/ontolint/pkg/../b.py"),  # a traversal
        ("src/ontolint/a.py,", ""),  # an empty item
        ("/etc/passwd", "/etc/passwd"),
        ("tests", "tests"),
        ("src/ontolint/a.py b.py", "src/ontolint/a.py b.py"),
        ("src/ontolint/$(id).py", "src/ontolint/$(id).py"),
        ("src/ontolint/a.py;rm -rf x", "src/ontolint/a.py;rm -rf x"),
        ("src/ontolint/a.py\nsrc/ontolint/pkg", "src/ontolint/a.py\nsrc/ontolint/pkg"),
        ("--gremlin-targets=x", "--gremlin-targets=x"),
        ("src/ontolint/-x.py", "src/ontolint/-x.py"),  # a segment may not start like an option
    ],
)
def test_any_other_target_is_refused_naming_the_item(repo: Path, paths: str, named: str) -> None:
    result = _run(repo, paths)
    assert result.returncode == 1
    assert result.stdout.startswith("::error::")
    assert f"'{named}'" in result.stdout


def test_a_symbolic_link_is_refused(repo: Path) -> None:
    link = repo / "src" / "ontolint" / "pkg" / "link.py"
    try:
        link.symlink_to(repo / "src" / "ontolint" / "b.py")
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are not available")
    assert _run(repo, "src/ontolint/pkg/link.py").returncode == 1


def test_the_number_and_the_length_of_the_items_are_bounded(repo: Path) -> None:
    many = ",".join(["src/ontolint/a.py"] * 21)
    assert _run(repo, many).returncode == 1
    assert _run(repo, ",".join(["src/ontolint/a.py"] * 20)).returncode == 0
    assert _run(repo, "src/ontolint/pkg/" + "a" * 500).returncode == 1


def test_a_narrowed_run_cannot_be_blocking(repo: Path) -> None:
    assert _run(repo, "src/ontolint/a.py", "blocking").returncode == 1
    assert _run(repo, "", "blocking").returncode == 0


def test_the_scope_of_this_repository_exists_and_is_accepted() -> None:
    """Every module the mutation job covers can be named, and none is refused as out of scope."""
    module = _load()
    scope = module.configured_scope(REPO)
    assert scope
    assert module.problems(",".join(scope[:20]), "advisory", REPO) == []
    assert module.problems("src/ontolint/exit_reasons.py", "advisory", REPO) != []  # the real scope omits it


# The real command on a real tiny project: a unit test of the check cannot say what pytest-gremlins does with it.
TINY = textwrap.dedent(
    """\
    [tool.pytest.ini_options]
    pythonpath = ["src"]
    [tool.pytest-gremlins]
    paths = ["src/tiny"]
    """
)


@pytest.fixture
def tiny(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text(TINY, encoding="utf-8")
    (tmp_path / "src" / "tiny").mkdir(parents=True)
    (tmp_path / "src" / "tiny" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "src" / "tiny" / "mod.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_mod.py").write_text(
        "from tiny.mod import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n", encoding="utf-8"
    )
    return tmp_path


def _gremlins(project: Path, target: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- this interpreter's pytest, on a project of this test
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:randomly",
            "-p",
            "no:cacheprovider",
            "--gremlins",
            "--no-cov",
            "--gremlin-report=json",
            f"--gremlin-targets={target}",
        ],  # fmt: skip
        cwd=project,
        env={**os.environ, "PYTHONPATH": ""},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.slow
def test_an_accepted_target_writes_the_report_the_gate_reads(tiny: Path) -> None:
    result = _gremlins(tiny, "src/tiny/mod.py")
    report = tiny / "coverage" / "gremlins" / "gremlins.json"
    assert result.returncode == 0, result.stdout + result.stderr
    assert report.is_file(), result.stdout
    assert json.loads(report.read_text(encoding="utf-8"))


@pytest.mark.slow
def test_a_target_that_exists_nowhere_writes_no_report_which_is_why_it_is_refused_first(tiny: Path) -> None:
    """The behaviour of pytest-gremlins the check stands on; if it changes, read the check again."""
    result = _gremlins(tiny, "src/tiny/does-not-exist")
    assert result.returncode == 0
    assert "No gremlins found" in result.stdout
    assert not (tiny / "coverage" / "gremlins" / "gremlins.json").exists()
