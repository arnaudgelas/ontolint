"""Modular stage 4: SHACL validates instance data together with the ontology its shapes import.

The corpus shapes require a document's ex:status to be an ex:Status. The valid example's status value
is typed ex:Status only in the ontology (meta.ttl), so without the ontology as background it reports a
false violation.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from rdflib import URIRef
from rdflib.namespace import OWL, RDF, SH

from ontolint import cli
from ontolint.cli import main
from ontolint.loader import load_graph
from ontolint.paths import resolve_inputs
from ontolint.policy import Policy

CORPUS = Path(__file__).parent / "fixtures" / "modular"


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    shutil.copytree(CORPUS, tmp_path / "modular")
    return tmp_path / "modular"


def _shacl(capsys: pytest.CaptureFixture[str], data: Path, shapes: Path, *extra: str) -> tuple[int, list[Any], str]:
    code = main([str(data), "--shapes", str(shapes), "--select", "SHACL001", "--format", "json", *extra])
    captured = capsys.readouterr()
    return code, json.loads(captured.out)["findings"] if captured.out else [], captured.err


def test_valid_data_reports_a_false_violation_without_the_ontology(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, findings, _err = _shacl(capsys, corpus / "examples" / "valid.ttl", corpus / "shapes.ttl")
    assert code == 1
    assert ["does not have class" in f["message"] for f in findings] == [True]


@pytest.mark.parametrize("how", [["--follow-imports"], ["--catalog", "catalog-v001.xml"]])
def test_valid_data_conforms_with_the_ontology_as_background(
    corpus: Path, capsys: pytest.CaptureFixture[str], how: list[str]
) -> None:
    extra = [str(corpus / part) if part.endswith(".xml") else part for part in how]
    code, findings, err = _shacl(capsys, corpus / "examples" / "valid.ttl", corpus / "shapes.ttl", *extra)
    assert (code, findings) == (0, []), err


def test_invalid_data_still_fails_with_the_ontology(corpus: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, findings, _err = _shacl(
        capsys, corpus / "examples" / "invalid.ttl", corpus / "shapes.ttl", "--follow-imports"
    )
    assert code == 1
    assert [f["focus"] for f in findings] == ["https://example.test/data/d2"]


def test_the_background_is_never_judged_by_term_rules(corpus: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = corpus / "examples" / "valid.ttl"
    main([str(data), "--shapes", str(corpus / "shapes.ttl"), "--follow-imports", "--format", "json"])
    findings = json.loads(capsys.readouterr().out)["findings"]
    assert all(Path(f["path"]).name == "valid.ttl" for f in findings)
    assert not [f for f in findings if f["focus"].startswith("https://example.test/onto/core#Undefined")]


def test_shapes_without_imports_add_no_background(corpus: Path, capsys: pytest.CaptureFixture[str]) -> None:
    shapes = corpus / "shapes.ttl"
    shapes.write_text(shapes.read_text(encoding="utf-8").replace(" ; owl:imports <https://example.test/onto>", ""))
    code, findings, _err = _shacl(capsys, corpus / "examples" / "valid.ttl", shapes, "--follow-imports")
    assert code == 1
    assert len(findings) == 1


def test_the_background_holds_the_ontology_but_not_the_shapes(corpus: Path) -> None:
    item = resolve_inputs([str(corpus / "shapes.ttl")], corpus)[0]
    shapes = load_graph(item, Policy())
    background = cli._shapes_background(item, shapes, Policy(), cli.ImportOptions())  # noqa: SLF001
    assert background is not None
    core = "https://example.test/onto/core#"
    assert (URIRef(core + "Authoritative"), RDF.type, URIRef(core + "Status")) in background
    assert not set(background.subjects(RDF.type, SH.NodeShape))
    shapes.remove((None, OWL.imports, None))
    assert cli._shapes_background(item, shapes, Policy(), cli.ImportOptions()) is None  # noqa: SLF001
