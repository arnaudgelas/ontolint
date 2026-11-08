"""SHACL001 keeps pySHACL's result severity and names blank shapes and focus nodes stably."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rdflib import Graph

from ontolint import Linter
from ontolint.cli import main

DATA = "@prefix ex: <https://example.test/> . ex:a a ex:K . [] a ex:K ."
SHAPES = """@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <https://example.test/> .
ex:S a sh:NodeShape ; sh:targetClass ex:K ;
  sh:property [ sh:path ex:violation ; sh:minCount 1 ] ;
  sh:property [ sh:path ex:warning ; sh:minCount 1 ; sh:severity sh:Warning ] ;
  sh:property [ sh:path ex:info ; sh:minCount 1 ; sh:severity sh:Info ] ;
  sh:property [ sh:path ex:custom ; sh:minCount 1 ; sh:severity ex:Blocker ] .
"""
WARNING_ONLY = """@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <https://example.test/> .
ex:S a sh:NodeShape ; sh:targetClass ex:K ; sh:property [ sh:path ex:p ; sh:minCount 1 ; sh:severity sh:Warning ] .
"""


def _shacl(data: str, shapes: str) -> list[tuple[str, str, str]]:
    result = Linter(Graph().parse(data=data, format="turtle"), Graph().parse(data=shapes, format="turtle")).execute(
        ["SHACL001"]
    )
    return sorted((f.severity, f.focus, f.message) for f in result.findings)


def test_each_shacl_severity_keeps_its_level() -> None:
    by_path = {message.split("->")[1].split(" ")[0]: severity for severity, _focus, message in _shacl(DATA, SHAPES)}
    assert by_path == {"ex:violation": "error", "ex:warning": "warning", "ex:info": "info", "ex:custom": "error"}


def test_a_custom_severity_is_named_in_the_message() -> None:
    custom = [message for _severity, _focus, message in _shacl(DATA, SHAPES) if "ex:custom" in message]
    assert custom
    assert all("(severity https://example.test/Blocker)" in message for message in custom)


def test_blank_shapes_and_focus_nodes_have_the_same_names_on_every_parse() -> None:
    first, second = _shacl(DATA, SHAPES), _shacl(DATA, SHAPES)
    assert first == second
    assert all("[shape: _:" in message for _severity, _focus, message in first)
    assert {focus for _severity, focus, _message in first if not focus.startswith("https://")} == {
        focus for _severity, focus, _message in first if focus.startswith("_:")
    }


def _files(tmp_path: Path, shapes: str) -> tuple[str, str]:
    data_file, shapes_file = tmp_path / "data.ttl", tmp_path / "shapes.ttl"
    data_file.write_text(DATA, encoding="utf-8")
    shapes_file.write_text(shapes, encoding="utf-8")
    return str(data_file), str(shapes_file)


def test_warnings_only_data_passes_the_default_gate(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data, shapes = _files(tmp_path, WARNING_ONLY)
    base = [data, "--shapes", shapes, "--select", "SHACL001", "--format", "json"]
    assert main(base) == 0
    findings = json.loads(capsys.readouterr().out)["findings"]
    assert {f["severity"] for f in findings} == {"warning"}
    assert main([*base, "--fail-on", "warning"]) == 1
    capsys.readouterr()


def test_a_baseline_suppresses_every_shacl_finding_on_the_next_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data, shapes = _files(tmp_path, SHAPES)
    baseline = tmp_path / "baseline.json"
    common = [data, "--shapes", shapes, "--select", "SHACL001", "--fail-on", "never"]
    main([*common, "--write-baseline", str(baseline), "--output", str(tmp_path / "first.txt")])
    main([*common, "--baseline", str(baseline), "--format", "json"])
    report = json.loads(capsys.readouterr().out)
    assert report["findings"] == []
    assert report["baseline"]["stale_fingerprints"] == []
