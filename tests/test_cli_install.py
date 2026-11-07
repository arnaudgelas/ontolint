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
