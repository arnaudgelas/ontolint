"""Modular stage 2: in an import closure, a finding points at the module that declares its focus."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from jsonschema.validators import validator_for

from ontolint.cli import main

CORPUS = Path(__file__).parent / "fixtures" / "modular"
SCHEMA = Path(__file__).parent / "schemas" / "sarif-schema-2.1.0.json"
UNDEFINED = "https://example.test/onto/core#UndefinedThing"
UNDEFINED_LINE = 13  # "ex:UndefinedThing a owl:Class ;" in core.ttl


@pytest.fixture
def umbrella(tmp_path: Path) -> Path:
    shutil.copytree(CORPUS, tmp_path / "modular")
    return tmp_path / "modular" / "umbrella.ttl"


def _run(capsys: pytest.CaptureFixture[str], umbrella: Path, fmt: str, *extra: str) -> str:
    main([str(umbrella), "--follow-imports", "--format", fmt, "--fail-on", "never", *extra])
    return capsys.readouterr().out


def _json(capsys: pytest.CaptureFixture[str], umbrella: Path) -> list[dict[str, Any]]:
    return json.loads(_run(capsys, umbrella, "json"))["findings"]


def test_json_names_the_declaring_module(umbrella: Path, capsys: pytest.CaptureFixture[str]) -> None:
    findings = _json(capsys, umbrella)
    (lex002,) = [f for f in findings if f["rule"] == "LEX002"]
    assert lex002["focus"] == UNDEFINED
    assert Path(lex002["path"]).name == "core.ttl"


def test_each_module_header_finding_points_at_its_own_module(
    umbrella: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = {f["focus"]: Path(f["path"]).name for f in _json(capsys, umbrella) if f["rule"] == "ONT003"}
    assert paths == {
        "https://example.test/onto": "umbrella.ttl",
        "https://example.test/onto/meta": "meta.ttl",
        "https://example.test/onto/core": "core.ttl",
        "https://example.test/onto/data": "data.ttl",
    }


def test_sarif_uses_the_module_artifact_and_region(umbrella: Path, capsys: pytest.CaptureFixture[str]) -> None:
    sarif = json.loads(_run(capsys, umbrella, "sarif"))
    (result,) = [r for r in sarif["runs"][0]["results"] if r["ruleId"] == "LEX002"]
    physical = result["locations"][0]["physicalLocation"]
    assert physical["artifactLocation"]["uri"].endswith("modular/core.ttl")
    assert physical["region"] == {"startLine": UNDEFINED_LINE, "startColumn": 1}
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator_for(schema)(schema).validate(sarif)


def test_text_says_which_module_a_finding_is_in(umbrella: Path, capsys: pytest.CaptureFixture[str]) -> None:
    text = _run(capsys, umbrella, "text")
    block = text[text.index(f"LEX002 {UNDEFINED}") :].split("\n[", 1)[0]
    assert block.rstrip().endswith("core.ttl")
    assert "    In: " in block
    root_block = text[text.index("ONT003 https://example.test/onto:") :].split("\n[", 1)[0]
    assert "In:" not in root_block  # the root's own findings keep the historical layout


def test_a_baseline_of_a_closure_keeps_matching(umbrella: Path, capsys: pytest.CaptureFixture[str]) -> None:
    baseline = umbrella.parent / "baseline.json"
    _run(capsys, umbrella, "text", "--write-baseline", str(baseline))
    report = json.loads(_run(capsys, umbrella, "json", "--baseline", str(baseline)))
    assert report["findings"] == []
    assert report["baseline"]["stale_fingerprints"] == []


def test_without_follow_imports_nothing_is_attributed(umbrella: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main([str(umbrella), "--format", "json", "--fail-on", "never"])
    findings = json.loads(capsys.readouterr().out)["findings"]
    assert {Path(f["path"]).name for f in findings} == {"umbrella.ttl"}
