"""Source-position recovery for SARIF results."""

from __future__ import annotations

from pathlib import Path

from rdflib import URIRef

from ontolint.loader import load_document
from ontolint.models import Finding
from ontolint.paths import resolve_inputs
from ontolint.policy import Policy

THIRD_LINE = 3
OTHER_COLUMN = 33


def _document(tmp_path: Path, name: str, text: str):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return load_document(resolve_inputs([name], tmp_path)[0], Policy(), tmp_path)


def test_turtle_source_index_ignores_comments_and_literals_and_resolves_prefixed_names(tmp_path: Path) -> None:
    document = _document(
        tmp_path,
        "a.ttl",
        '# ex:False\n@prefix ex: <https://example.test/> .\nex:Thing ex:p "ex:False" ; ex:q ex:Other .\n',
    )
    index = document.source_index.locations
    assert index[URIRef("https://example.test/Thing")].line == THIRD_LINE
    assert index[URIRef("https://example.test/Thing")].column == 1
    assert index[URIRef("https://example.test/Other")].line == THIRD_LINE
    assert index[URIRef("https://example.test/Other")].column == OTHER_COLUMN


def test_ntriples_iri_findings_receive_positions(tmp_path: Path) -> None:
    document = _document(tmp_path, "a.nt", "_:node <https://example.test/p> <https://example.test/o> .\n")
    finding = Finding("ONT001", "warning", "https://example.test/o", "message", "suggestion")
    locations = document.source_index.for_findings(document.graph, [finding])
    assert locations[finding].line == 1 and locations[finding].column == OTHER_COLUMN


def test_unsupported_syntax_omits_source_positions(tmp_path: Path) -> None:
    document = _document(
        tmp_path,
        "a.jsonld",
        '{"@context": {"p": "https://example.test/p"}, "@id": "https://example.test/a", "p": "x"}',
    )
    assert document.source_index.locations == {}
