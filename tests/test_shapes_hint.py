"""TOOL003: linting a file that is mostly SHACL shapes says, once, that it probably belongs in --shapes."""

from __future__ import annotations

from pathlib import Path

import pytest

from ontolint.cli import main

PREFIXES = (
    "@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
    "@prefix ex: <https://example.test/> .\n"
)
SHAPES = PREFIXES + (
    "ex:S a sh:NodeShape ; sh:targetClass ex:K ;\n"
    "  sh:property [ sh:path ex:p ; sh:minCount 1 ] , [ sh:path ex:q ; sh:maxCount 1 ] .\n"
    "ex:T a sh:NodeShape ; sh:targetClass ex:L .\n"
)
ONTOLOGY = PREFIXES + "ex:K a owl:Class . ex:L a owl:Class . ex:p a owl:ObjectProperty .\n"
ONTOLOGY_WITH_ONE_SHAPE = ONTOLOGY + "ex:S a sh:NodeShape ; sh:targetClass ex:K .\n"


def _stderr(tmp_path: Path, capsys: pytest.CaptureFixture[str], text: str) -> str:
    path = tmp_path / "input.ttl"
    path.write_text(text, encoding="utf-8")
    main([str(path), "--fail-on", "never", "--output", str(tmp_path / "report.txt")])
    return capsys.readouterr().err


def test_a_shapes_file_linted_as_an_ontology_gets_one_note(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    err = _stderr(tmp_path, capsys, SHAPES)
    assert err.count("TOOL003: note:") == 1
    assert "looks like a SHACL shapes graph (4 shapes, 0 declared terms)" in err
    assert "--shapes" in err


@pytest.mark.parametrize("text", [ONTOLOGY, ONTOLOGY_WITH_ONE_SHAPE], ids=["ontology", "ontology-with-a-shape"])
def test_an_ontology_gets_no_note(tmp_path: Path, capsys: pytest.CaptureFixture[str], text: str) -> None:
    assert "TOOL003" not in _stderr(tmp_path, capsys, text)


def test_the_note_does_not_change_the_exit_code(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "shapes.ttl"
    path.write_text(SHAPES, encoding="utf-8")
    assert main([str(path), "--select", "ONT001", "--fail-on", "never", "--output", str(tmp_path / "r")]) == 0
    capsys.readouterr()
