"""The version-bump script edits the three version files and the changelog, and nothing else."""

# ruff: noqa: PLR2004, S603, S607

from __future__ import annotations

import importlib.util
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "bump_version.py"
spec = importlib.util.spec_from_file_location("bump_version", SCRIPT)
assert spec is not None
assert spec.loader is not None
bump = importlib.util.module_from_spec(spec)
sys.modules["bump_version"] = bump
spec.loader.exec_module(bump)

TODAY = date(2026, 11, 8)
PYPROJECT = '[project]\nname = "x"\nversion = "0.1.0"\n'
FALLBACK = 'FALLBACK_VERSION = "0.1.0"\n'


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
        cwd=root,
        check=True,
        capture_output=True,
    )


def _commit(root: Path, subject: str, body: str = "") -> None:
    _git(root, "commit", "--allow-empty", "-m", f"{subject}\n\n{body}" if body else subject)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "src/ontolint").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text(PYPROJECT)
    (tmp_path / "src/ontolint/_version.py").write_text(FALLBACK)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", ".")
    _commit(tmp_path, "feat: first thing")
    _git(tmp_path, "tag", "v0.1.0")
    _commit(tmp_path, "fix(loader): repair it")
    _commit(tmp_path, "docs: explain it")
    _commit(tmp_path, "test: cover it")
    _commit(tmp_path, "chore: release 0.1.0")
    _commit(tmp_path, "feat!: drop the old flag")
    _commit(tmp_path, "refactor: tidy", "BREAKING CHANGE: output moved")
    _commit(tmp_path, "not conventional")
    return tmp_path


@pytest.mark.parametrize(
    ("current", "request_", "expected"),
    [
        ((0, 1, 0), "patch", (0, 1, 1)),
        ((0, 1, 9), "minor", (0, 2, 0)),
        ((1, 2, 3), "major", (2, 0, 0)),
        ((0, 1, 0), "0.1.1", (0, 1, 1)),
        ((0, 1, 0), "3.0.0", (3, 0, 0)),
    ],
)
def test_next_version(current: tuple[int, int, int], request_: str, expected: tuple[int, int, int]) -> None:
    assert bump.next_version(current, request_) == expected


@pytest.mark.parametrize("bad", ["0.1.0", "0.0.9", "1.0", "1.0.0rc1", "v1.0.0", "", "1.0.0.0", "-1.0.0", "x"])
def test_next_version_rejects(bad: str) -> None:
    with pytest.raises(bump.BumpError):
        bump.next_version((0, 1, 0), bad)


def test_apply_edits_only_the_version_files_and_the_changelog(repo: Path) -> None:
    plan = bump.apply(repo, "minor", today=TODAY, lock=None)
    assert plan.new == (0, 2, 0)
    assert 'version = "0.2.0"' in (repo / "pyproject.toml").read_text()
    assert (repo / "src/ontolint/_version.py").read_text() == 'FALLBACK_VERSION = "0.2.0"\n'
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    assert sorted(line[3:] for line in status) == ["CHANGELOG.md", "pyproject.toml", "src/ontolint/_version.py"]
    head = subprocess.run(["git", "log", "-1", "--format=%s"], cwd=repo, capture_output=True, text=True, check=True)
    assert head.stdout.strip() == "not conventional"  # nothing was committed
    tags = subprocess.run(["git", "tag"], cwd=repo, capture_output=True, text=True, check=True).stdout.split()
    assert tags == ["v0.1.0"]


def test_changelog_groups_commits_since_the_previous_tag(repo: Path) -> None:
    text = bump.apply(repo, "minor", today=TODAY, lock=None).files[repo / "CHANGELOG.md"]
    new = text.split("## [0.1.0]")[0]
    assert "## [0.2.0] - 2026-11-08" in new
    assert "### Breaking changes" in new
    assert "- drop the old flag" in new
    assert "- tidy" in new  # BREAKING CHANGE trailer promotes a refactor
    assert "- **loader:** repair it" in new
    assert "### Documentation" in new
    assert "### Maintenance" in new
    assert "- not conventional" in new
    assert "release 0.1.0" not in new
    assert "first thing" not in new
    assert "## [0.1.0] - " in text
    assert "- first thing" in text.split("## [0.1.0]")[1]


def test_changelog_section_is_prepended_to_an_existing_file(repo: Path) -> None:
    (repo / "CHANGELOG.md").write_text("# Changelog\n\nintro\n\n## [0.1.0] - 2026-01-01\n\n- old\n")
    _git(repo, "add", ".")
    _commit(repo, "docs: add changelog")
    text = bump.apply(repo, "patch", today=TODAY, lock=None).files[repo / "CHANGELOG.md"]
    assert text.startswith("# Changelog\n\nintro\n\n## [0.1.1] - 2026-11-08")
    assert text.endswith("## [0.1.0] - 2026-01-01\n\n- old\n")


def test_existing_section_is_refused(repo: Path) -> None:
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n## [0.1.1] - 2026-01-01\n")
    _git(repo, "add", ".")
    _commit(repo, "docs: add changelog")
    with pytest.raises(bump.BumpError, match="already has a section"):
        bump.apply(repo, "patch", today=TODAY, lock=None)


def test_dry_run_writes_nothing(repo: Path) -> None:
    plan = bump.apply(repo, "patch", today=TODAY, dry_run=True, lock=None)
    assert plan.new == (0, 1, 1)
    assert (repo / "pyproject.toml").read_text() == PYPROJECT
    assert not (repo / "CHANGELOG.md").exists()


def test_no_changelog_leaves_it_alone(repo: Path) -> None:
    plan = bump.apply(repo, "patch", today=TODAY, changelog=False, lock=None)
    assert repo / "CHANGELOG.md" not in plan.files
    assert not (repo / "CHANGELOG.md").exists()


def test_dirty_tree_is_refused(repo: Path) -> None:
    (repo / "pyproject.toml").write_text(PYPROJECT + "\n# edited\n")
    with pytest.raises(bump.BumpError, match="uncommitted"):
        bump.apply(repo, "patch", today=TODAY, lock=None)


def test_untracked_files_do_not_block_a_bump(repo: Path) -> None:
    (repo / "scratch.txt").write_text("x")
    bump.apply(repo, "patch", today=TODAY, lock=None)


def test_disagreeing_version_files_are_refused(repo: Path) -> None:
    (repo / "src/ontolint/_version.py").write_text('FALLBACK_VERSION = "0.0.9"\n')
    _git(repo, "add", ".")
    _commit(repo, "chore: skew")
    with pytest.raises(bump.BumpError, match="make them equal"):
        bump.apply(repo, "patch", today=TODAY, lock=None)


@pytest.mark.parametrize("content", ["[project]\n", PYPROJECT + PYPROJECT])
def test_missing_or_repeated_version_line_is_refused(repo: Path, content: str) -> None:
    (repo / "pyproject.toml").write_text(content)
    _git(repo, "add", ".")
    _commit(repo, "chore: edit")
    with pytest.raises(bump.BumpError, match="exactly one version line"):
        bump.apply(repo, "patch", today=TODAY, lock=None)


def test_lock_hook_runs_after_the_files_are_written(repo: Path) -> None:
    seen: list[str] = []
    bump.apply(repo, "patch", today=TODAY, lock=lambda root: seen.append((root / "pyproject.toml").read_text()))
    assert len(seen) == 1
    assert 'version = "0.1.1"' in seen[0]


def test_no_tag_means_the_whole_history(tmp_path: Path) -> None:
    (tmp_path / "src/ontolint").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text(PYPROJECT)
    (tmp_path / "src/ontolint/_version.py").write_text(FALLBACK)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", ".")
    _commit(tmp_path, "feat: only thing")
    text = bump.apply(tmp_path, "patch", today=TODAY, lock=None).files[tmp_path / "CHANGELOG.md"]
    assert "- only thing" in text


def test_empty_range_says_so() -> None:
    assert "No notable changes." in bump.render_section((0, 1, 1), TODAY, [])


def test_the_real_repository_has_the_expected_version_lines() -> None:
    root = SCRIPT.parent.parent
    assert bump.read_version(root) == bump.parse_version(
        bump.PYPROJECT_LINE.findall((root / "pyproject.toml").read_text())[0]
    )
