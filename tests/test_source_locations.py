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
JSONLD_ID_COLUMN = 54
RDFXML_SUBJECT_COLUMN = 3
RDFXML_OBJECT_COLUMN = 55


def _document(tmp_path: Path, name: str, text: str, policy: Policy | None = None):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return load_document(resolve_inputs([name], tmp_path)[0], policy or Policy(), tmp_path)


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


def test_jsonld_explicit_id_receives_a_source_position(tmp_path: Path) -> None:
    document = _document(
        tmp_path,
        "a.jsonld",
        '{"@context": {"p": "https://example.test/p"}, "@id": "https://example.test/a", "p": "x"}',
    )
    location = document.source_index.locations[URIRef("https://example.test/a")]
    assert location.line == 1 and location.column == JSONLD_ID_COLUMN


def test_jsonld_compact_id_uses_its_local_context(tmp_path: Path) -> None:
    document = _document(
        tmp_path,
        "a.jsonld",
        '[{"@context":{"ex":"https://example.test/"},"@id":"ex:outer","@type":"ex:Class"},{"@context":{"ex":"https://nested.test/"},"@id":"ex:inner","@type":"ex:Class"}]',
    )
    locations = document.source_index.locations
    outer = locations[URIRef("https://example.test/outer")]
    inner = locations[URIRef("https://nested.test/inner")]
    assert outer.column is not None and outer.column > 0
    assert inner.column is not None and inner.column > 0


def test_jsonld_base_reverse_list_and_duplicate_ids_keep_only_real_graph_nodes(tmp_path: Path) -> None:
    document = _document(
        tmp_path,
        "a.jsonld",
        """{
  "@context":{"@base":"https://example.test/","ex":"https://example.test/"},
  "@id":"old", "@id":"root", "@type":"ex:Class",
  "@reverse":{"ex:p":{"@id":"reverse","@type":"ex:Class"}},
  "ex:p":{"@list":[{"@id":"listed","@type":"ex:Class"}]}
}""",
    )
    locations = document.source_index.locations
    assert URIRef("https://example.test/old") not in locations
    for iri in ("root", "reverse", "listed"):
        assert locations[URIRef(f"https://example.test/{iri}")].line > 0


def test_rdfxml_about_and_resource_receive_element_positions(tmp_path: Path) -> None:
    document = _document(
        tmp_path,
        "a.rdf",
        """<?xml version=\"1.0\"?>
<rdf:RDF xmlns:rdf=\"http://www.w3.org/1999/02/22-rdf-syntax-ns#\" xmlns:e=\"https://example.test/\">
  <rdf:Description rdf:about=\"https://example.test/a\"><e:p rdf:resource=\"https://example.test/b\"/></rdf:Description>
</rdf:RDF>
""",
    )
    locations = document.source_index.locations
    assert locations[URIRef("https://example.test/a")].line == THIRD_LINE
    assert locations[URIRef("https://example.test/a")].column == RDFXML_SUBJECT_COLUMN
    assert locations[URIRef("https://example.test/b")].line == THIRD_LINE
    assert locations[URIRef("https://example.test/b")].column == RDFXML_OBJECT_COLUMN


def test_rdfxml_unicode_and_crlf_locations_are_reported(tmp_path: Path) -> None:
    text = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>\r
<rdf:RDF xmlns:rdf=\"http://www.w3.org/1999/02/22-rdf-syntax-ns#\">\r
  <rdf:Description rdf:about=\"https://example.test/é😀\"/>\r
</rdf:RDF>\r
"""
    text = text.replace("<rdf:RDF ", '<rdf:RDF xmlns:e="https://example.test/" ', 1).replace(
        "rdf:Description", "e:Class", 1
    )
    document = _document(tmp_path, "a.rdf", text)
    location = document.source_index.locations[URIRef("https://example.test/é😀")]
    assert location.line == THIRD_LINE and location.column == RDFXML_SUBJECT_COLUMN


def test_source_locations_match_in_the_time_bounded_worker(tmp_path: Path) -> None:
    source = "@prefix ex: <https://example.test/> .\nex:A a ex:Class .\n"
    direct = _document(tmp_path, "direct.ttl", source)
    worker = _document(tmp_path, "worker.ttl", source, Policy(max_parse_seconds=5))
    assert dict(direct.source_index.locations) == dict(worker.source_index.locations)
