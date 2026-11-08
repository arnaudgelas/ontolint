"""Source-position recovery for SARIF results."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from rdflib import Graph, URIRef

from ontolint import source_locations
from ontolint.cli import main
from ontolint.loader import load_document
from ontolint.models import Finding
from ontolint.paths import resolve_inputs
from ontolint.policy import Policy
from ontolint.reporting import Location

THIRD_LINE = 3
FOURTH_LINE = 4
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


OWL_CLASS = "http://www.w3.org/2002/07/owl#Class"

# Valid JSON-LD that RDFLib parses but that 0.4.0's locator walked out of step with (exit 2).
JSONLD_LOCATOR_REGRESSIONS = {
    "space-before-colon": '{"@id" : "https://example.test/a", "@type" : "' + OWL_CLASS + '"}',
    "spaced-empty-object": '{"@context": { }, "@id": "https://example.test/a", "@type": "' + OWL_CLASS + '"}',
    "spaced-empty-array": '{"@id": "https://example.test/a", "@type": "'
    + OWL_CLASS
    + '", "https://example.test/p": [ ]}',
    "duplicate-key-of-another-type": (
        '{"@id": "https://example.test/a", "@type": "' + OWL_CLASS + '", '
        '"https://example.test/p": "y", "https://example.test/p": {"@id": "https://example.test/b"}}'
    ),
}


@pytest.mark.parametrize("text", JSONLD_LOCATOR_REGRESSIONS.values(), ids=JSONLD_LOCATOR_REGRESSIONS.keys())
def test_jsonld_layout_never_breaks_the_locator(tmp_path: Path, text: str) -> None:
    document = _document(tmp_path, "a.jsonld", text)
    location = document.source_index.locations[URIRef("https://example.test/a")]
    assert location.column is not None
    assert text[location.column - 1 :].startswith('"https://example.test/a"')


@pytest.mark.parametrize("text", JSONLD_LOCATOR_REGRESSIONS.values(), ids=JSONLD_LOCATOR_REGRESSIONS.keys())
def test_jsonld_layout_never_fails_the_run(tmp_path: Path, text: str, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "a.jsonld"
    path.write_text(text, encoding="utf-8")
    assert main([str(path), "--format", "sarif", "--fail-on", "never"]) == 0
    assert "INPUT001" not in capsys.readouterr().err


def test_a_locator_failure_costs_only_the_regions(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*_args: object) -> dict[object, object]:
        raise RuntimeError("locator bug")

    monkeypatch.setattr(source_locations, "_locations", broken)
    index = source_locations.build_source_index(b"<a> <b> <c> .", "nt", "file:///a.nt", Graph())
    assert dict(index.locations) == {}
    assert index.problem == "RuntimeError: locator bug"


def test_the_json_walk_rejects_a_tree_that_does_not_match_its_text() -> None:
    with pytest.raises(ValueError, match="expected"):
        source_locations._json_id_values("[1]", source_locations._Pairs(), "file:///a.jsonld")


_JSON_WHITESPACE = st.text(alphabet=" \t\n\r", max_size=3)


@settings(max_examples=60, deadline=None)
@given(st.lists(_JSON_WHITESPACE, min_size=24, max_size=24))
def test_jsonld_whitespace_anywhere_keeps_the_location(
    tmp_path_factory: pytest.TempPathFactory, gaps: list[str]
) -> None:
    tokens = [
        "{",
        '"@context"',
        ":",
        "{",
        '"ex"',
        ":",
        '"https://example.test/"',
        "}",
        ",",
        '"@id"',
        ":",
        '"ex:a"',
        ",",
        '"@type"',
        ":",
        json.dumps(OWL_CLASS),
        ",",
        '"ex:p"',
        ":",
        "[",
        "{",
        "}",
        "]",
        "}",
    ]
    text = "".join(gap + token for gap, token in zip(gaps, tokens, strict=True))
    document = _document(tmp_path_factory.mktemp("ws"), "a.jsonld", text)
    location = document.source_index.locations[URIRef("https://example.test/a")]
    assert location.column is not None
    line_start = sum(len(line) + 1 for line in text.split("\n")[: location.line - 1])
    assert text[line_start + location.column - 1 :].startswith('"ex:a"')


ONTOLOGY_TTL = "<https://example.test/o> a <http://www.w3.org/2002/07/owl#Ontology> .\n"


@pytest.mark.parametrize(
    "header",
    [
        "@prefix ex: <https://example.test/o> .\n",
        "PREFIX ex: <https://example.test/o>\n",
        "prefix ex: <https://example.test/o>\n",
        "@base <https://example.test/o> .\n",
        "BASE <https://example.test/o>\n",
    ],
)
def test_turtle_directives_are_never_a_location(tmp_path: Path, header: str) -> None:
    document = _document(tmp_path, "a.ttl", header + ONTOLOGY_TTL)
    assert document.source_index.locations[URIRef("https://example.test/o")] == Location(2, 1)


def test_a_prefixed_name_spelled_like_a_directive_keyword_is_still_located(tmp_path: Path) -> None:
    text = "@prefix base: <https://example.test/> .\nbase:A a base:B .\n"
    locations = _document(tmp_path, "a.ttl", text).source_index.locations
    assert locations[URIRef("https://example.test/A")] == Location(2, 1)


def test_a_jsonld_context_term_definition_is_never_a_location(tmp_path: Path) -> None:
    text = (
        '{"@context": {"o": {"@id": "https://example.test/o"}},\n'
        ' "@id": "https://example.test/o", "@type": "http://www.w3.org/2002/07/owl#Ontology"}'
    )
    location = _document(tmp_path, "a.jsonld", text).source_index.locations[URIRef("https://example.test/o")]
    assert location == Location(2, 9)


def test_rdfxml_empty_about_locates_the_ontology_at_its_base(tmp_path: Path) -> None:
    text = """<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:owl="http://www.w3.org/2002/07/owl#" xml:base="https://example.test/o">
  <owl:Ontology rdf:about=""/>
</rdf:RDF>
"""
    location = _document(tmp_path, "a.rdf", text).source_index.locations[URIRef("https://example.test/o")]
    assert location.line == FOURTH_LINE


def test_line_numbers_are_exact_across_many_lines(tmp_path: Path) -> None:
    body = "".join(f"<https://example.test/c{i}> a <https://example.test/K> .\n" for i in range(500))
    locations = _document(tmp_path, "a.ttl", body).source_index.locations
    assert locations[URIRef("https://example.test/c0")] == Location(1, 1)
    assert locations[URIRef("https://example.test/c499")] == Location(500, 1)
    assert locations[URIRef("https://example.test/K")] == Location(1, len("<https://example.test/c0> a ") + 1)


def test_the_index_is_computed_only_when_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    real = source_locations._locations

    def counting(*args: object) -> object:
        calls.append("built")
        return real(*args)  # type: ignore[arg-type]

    monkeypatch.setattr(source_locations, "_locations", counting)
    document = _document(tmp_path, "a.ttl", ONTOLOGY_TTL)
    assert calls == []
    assert document.source_index.locations
    assert document.source_index.locations
    assert calls == ["built"]


def test_only_sarif_output_computes_locations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(source_locations, "_locations", lambda *_args: calls.append("built") or {})
    path = tmp_path / "a.ttl"
    path.write_text(ONTOLOGY_TTL, encoding="utf-8")
    for output in ("text", "json"):
        main([str(path), "--format", output, "--fail-on", "never"])
    assert calls == []
    main([str(path), "--format", "sarif", "--fail-on", "never"])
    capsys.readouterr()
    assert calls == ["built"]


def test_sarif_says_when_regions_are_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken(*_args: object) -> dict[object, object]:
        raise RuntimeError("locator bug")

    monkeypatch.setattr(source_locations, "_locations", broken)
    path = tmp_path / "a.ttl"
    path.write_text(ONTOLOGY_TTL, encoding="utf-8")
    assert main([str(path), "--format", "sarif", "--fail-on", "never"]) == 0
    sarif = json.loads(capsys.readouterr().out)
    notes = [n["message"]["text"] for n in sarif["runs"][0]["invocations"][0]["toolExecutionNotifications"]]
    assert "Source regions are unavailable for this file: RuntimeError: locator bug" in notes
    assert all("region" not in r["locations"][0]["physicalLocation"] for r in sarif["runs"][0]["results"])
