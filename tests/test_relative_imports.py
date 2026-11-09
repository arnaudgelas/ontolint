"""Relative owl:imports (the IDS Information Model pattern): reported once, never as local file paths."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ontolint.cli import main

HEADER = (
    "@prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix ids: <https://ids.test/core/> .\n"
    "ids: a owl:Ontology ;\n"
    "    owl:imports <model/A.ttl> , <model/B.ttl> .\n"
)
MODULE = (
    "@prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix ids: <https://ids.test/core/> .\nids:{0} a owl:Class .\n"
)


def _project(root: Path) -> Path:
    (root / "model").mkdir(parents=True)
    (root / "model" / "A.ttl").write_text(MODULE.format("A"), encoding="utf-8")
    (root / "model" / "B.ttl").write_text(MODULE.format("B"), encoding="utf-8")
    header = root / "Ontology.ttl"
    header.write_text(HEADER, encoding="utf-8")
    return header


def _findings(capsys: pytest.CaptureFixture[str], header: Path, *extra: str) -> list[tuple[str, str, str]]:
    main([str(header), "--format", "json", "--fail-on", "never", *extra])
    findings = json.loads(capsys.readouterr().out)["findings"]
    return sorted((f["rule"], f["focus"], f["message"]) for f in findings)


def test_relative_imports_are_not_unsafe_file_iris(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    findings = _findings(capsys, _project(tmp_path))
    assert not [f for f in findings if f[0] == "SEC008"]
    assert [f[2] for f in findings if f[0] == "GOV002"] == [
        "2 owl:imports use relative references (model/A.ttl, model/B.ttl), which resolve differently depending "
        "on where the file is read; import absolute IRIs and map them with a catalog."
    ]
    (note,) = [f[2] for f in findings if f[0] == "SEC007"]
    assert note == "2 owl:imports were not followed: model/A.ttl, model/B.ttl."


def test_two_checkouts_give_the_same_findings(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    first = _findings(capsys, _project(tmp_path / "one"))
    second = _findings(capsys, _project(tmp_path / "elsewhere" / "two"))
    assert first == second
    assert all(str(tmp_path) not in message for _rule, _focus, message in first)


def test_relative_imports_resolve_with_follow_imports(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    findings = _findings(capsys, _project(tmp_path), "--follow-imports")
    assert not [f for f in findings if f[0] in {"SEC007", "SEC008"}]
    assert {f[1] for f in findings if f[0] == "LEX001"} == {"https://ids.test/core/A", "https://ids.test/core/B"}


def test_a_real_file_iri_elsewhere_is_still_unsafe(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    header = _project(tmp_path / "project")
    header.write_text(HEADER + "ids: owl:imports <file:///etc/passwd> .\n", encoding="utf-8")
    assert [f[1] for f in _findings(capsys, header) if f[0] == "SEC008"] == ["file:///etc/passwd"]
