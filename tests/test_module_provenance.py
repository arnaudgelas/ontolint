"""Modular stage 2: in an import closure, a finding points at the module that declares its focus."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from jsonschema.validators import validator_for

from ontolint import source_locations
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


def test_header_rules_judge_only_the_root_ontology(umbrella: Path, capsys: pytest.CaptureFixture[str]) -> None:
    findings = _json(capsys, umbrella)
    header_rules = {"ONT003", "ONT004", "ONT005", "ONT006", "GOV004"}
    foci = {(f["rule"], f["focus"], Path(f["path"]).name) for f in findings if f["rule"] in header_rules}
    assert foci
    assert {focus for _rule, focus, _path in foci} == {"https://example.test/onto"}  # modules inherit it
    assert {path for _rule, _focus, path in foci} == {"umbrella.ttl"}


def test_sarif_uses_the_module_artifact_and_region(umbrella: Path, capsys: pytest.CaptureFixture[str]) -> None:
    sarif = json.loads(_run(capsys, umbrella, "sarif"))
    (result,) = [r for r in sarif["runs"][0]["results"] if r["ruleId"] == "LEX002"]
    physical = result["locations"][0]["physicalLocation"]
    assert physical["artifactLocation"]["uri"].endswith("modular/core.ttl")
    assert physical["region"] == {"startLine": UNDEFINED_LINE, "startColumn": 1}
    notes = sarif["runs"][0]["invocations"][0]["toolExecutionNotifications"]
    assert not [n for n in notes if n["message"]["text"].startswith("Source regions are unavailable")]
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


def _policy(umbrella: Path, **keys: object) -> str:
    path = umbrella.parent / "policy.json"
    path.write_text(json.dumps({"policy_version": 1, **keys}), encoding="utf-8")
    return str(path)


def test_metric011_counts_only_imports_that_are_not_local_modules(
    umbrella: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _policy(umbrella, metric_max_imports=2)  # the umbrella has 4 imports; 3 resolve to modules
    main([str(umbrella), "--config", config, "--format", "json", "--fail-on", "never"])
    alone = json.loads(capsys.readouterr().out)["findings"]
    assert [f["message"] for f in alone if f["rule"] == "METRIC011"] == ["4 distinct owl:imports (threshold 2)."]
    closure = json.loads(_run(capsys, umbrella, "json", "--config", config))["findings"]
    assert not [f for f in closure if f["rule"] == "METRIC011"]


def test_a_vendored_vocabulary_in_the_closure_is_not_owned(umbrella: Path, capsys: pytest.CaptureFixture[str]) -> None:
    corpus = umbrella.parent
    (corpus / "vendor.ttl").write_text(
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
        "<https://vendor.example/v> a owl:Ontology .\n"
        "<https://vendor.example/v#Unlabelled> a owl:Class .\n",
        encoding="utf-8",
    )
    catalog = (corpus / "catalog-v001.xml").read_text(encoding="utf-8")
    entry = '<uri name="https://vendor.example/v" uri="vendor.ttl"/>'
    (corpus / "catalog-v001.xml").write_text(catalog.replace("</catalog>", f"  {entry}\n</catalog>"), encoding="utf-8")
    text = umbrella.read_text(encoding="utf-8")
    vendored = text.replace("<https://external.example/vocabulary> .", "<https://vendor.example/v> .")
    umbrella.write_text(vendored, encoding="utf-8")
    findings = _json(capsys, umbrella)
    assert not [f for f in findings if f["focus"].startswith("https://vendor.example/")]
    assert [f["focus"] for f in findings if f["rule"] == "LEX002"] == [UNDEFINED]  # project terms still judged


def test_a_module_locator_failure_is_reported_in_sarif(
    umbrella: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_args: object) -> dict[object, object]:
        raise RuntimeError("locator bug")

    monkeypatch.setattr(source_locations, "_locations", broken)
    sarif = json.loads(_run(capsys, umbrella, "sarif"))
    notes = [n["message"]["text"] for n in sarif["runs"][0]["invocations"][0]["toolExecutionNotifications"]]
    (note,) = [n for n in notes if n.startswith("Source regions are unavailable")]
    assert "umbrella.ttl: RuntimeError: locator bug" in note
    assert "core.ttl: RuntimeError: locator bug" in note
    report = json.loads(_run(capsys, umbrella, "json"))
    assert report["findings"]  # the run itself is unaffected
