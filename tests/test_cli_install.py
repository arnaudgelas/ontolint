"""Installing the package gives a working ``ontolint`` command."""

from __future__ import annotations

import tomllib
from importlib import metadata
from pathlib import Path

import pytest

import ontolint

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_console_script_is_declared_and_points_at_the_cli() -> None:
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    assert project["scripts"] == {"ontolint": "ontolint:main"}
    (entry,) = metadata.entry_points(group="console_scripts", name="ontolint")
    assert entry.value == "ontolint:main"
    assert entry.load() is ontolint.main


def test_version_flag_reports_the_installed_distribution_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert ontolint.main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"ontolint {metadata.version('ontolint')}"


def test_package_metadata_helps_users_find_the_project() -> None:
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    assert {"Homepage", "Source", "Issues"} <= set(project["urls"])
    assert all(url.startswith("https://github.com/arnaudgelas/ontolint") for url in project["urls"].values())
    assert "Programming Language :: Python :: 3.13" in project["classifiers"]
    assert "Typing :: Typed" in project["classifiers"]
    assert project["license"] == "Apache-2.0"


def test_the_notice_names_the_author_and_ships_with_the_licence() -> None:
    # Apache-2.0 section 4(d): a NOTICE file travels with every redistribution, so the wheel carries it.
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    assert project["license-files"] == ["LICENSE", "NOTICE"]
    notice = (PYPROJECT.parent / "NOTICE").read_text(encoding="utf-8").splitlines()
    (author,) = project["authors"]
    assert notice[:2] == ["ontolint", f"Copyright 2026 {author['name']}"]
    # The build backend's own reading of license-files (an editable install carries no licence files to list).
    assert metadata.metadata("ontolint").get_all("License-File") == ["LICENSE", "NOTICE"]
