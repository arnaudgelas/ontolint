"""Source-position recovery for SARIF results."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from rdflib import Graph, URIRef
from rdflib.compare import isomorphic
from rdflib.term import Node
from timing_support import LINEAR_SCAN_SECONDS

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


@pytest.mark.parametrize("suffix", ["ttl", "trig"])
def test_the_scan_is_linear_on_a_long_word_outside_strings(tmp_path: Path, suffix: str) -> None:
    # A run of name characters with no ':' (here a 200 000-letter language tag) used to be retried as a prefixed
    # name at each of its letters: about 5 s at 50 000 letters, four times longer when it doubles.
    text = '@prefix ex: <https://example.test/> .\n{ ex:A ex:p "x"@' + "a" * 200_000 + " . ex:B a ex:A . }\n"
    if suffix == "ttl":
        text = text.replace("{ ", "").replace(" }", "")
    document = _document(tmp_path, f"a.{suffix}", text)
    started = time.perf_counter()
    locations = document.source_index.locations
    assert time.perf_counter() - started < LINEAR_SCAN_SECONDS
    column = text.split("\n")[1].index("ex:B") + 1
    assert locations[URIRef("https://example.test/B")] == Location(2, column)


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


# --- cases found by mutation testing of the scanner ------------------------------------------------


def test_a_node_named_in_a_comment_or_literal_is_located_at_its_statement(tmp_path: Path) -> None:
    text = (
        "@prefix ex: <https://example.test/> .\n"
        "# ex:A is declared below\n"
        'ex:Note ex:says "ex:A again" .\n'
        "ex:A a ex:K .\n"
    )
    locations = _document(tmp_path, "a.ttl", text).source_index.locations
    assert locations[URIRef("https://example.test/A")] == Location(4, 1)


def test_the_last_characters_of_a_comment_are_not_a_term(tmp_path: Path) -> None:
    text = "@prefix : <https://example.test/> .\n# see :A\n<https://example.test/x> :p :A .\n"
    locations = _document(tmp_path, "a.ttl", text).source_index.locations
    assert locations[URIRef("https://example.test/A")] == Location(3, len("<https://example.test/x> :p ") + 1)


def test_a_comment_at_the_very_end_of_the_file_ends_the_scan(tmp_path: Path) -> None:
    locations = _document(
        tmp_path, "a.ttl", "<https://example.test/A> a <https://example.test/K> . # end"
    ).source_index.locations
    assert locations[URIRef("https://example.test/K")] == Location(1, len("<https://example.test/A> a ") + 1)


def test_an_iri_ending_in_a_hash_does_not_start_a_comment(tmp_path: Path) -> None:
    locations = _document(
        tmp_path, "a.ttl", "<https://example.test/o#> a <https://example.test/K> .\n"
    ).source_index.locations
    assert locations[URIRef("https://example.test/K")] == Location(1, len("<https://example.test/o#> a ") + 1)


def test_rdfxml_keeps_the_first_reference_to_a_resource(tmp_path: Path) -> None:
    text = """<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:e="https://example.test/">
  <rdf:Description rdf:about="https://example.test/a"><e:p rdf:resource="https://example.test/b"/></rdf:Description>
  <rdf:Description rdf:about="https://example.test/b"/>
</rdf:RDF>
"""
    locations = _document(tmp_path, "a.rdf", text).source_index.locations
    assert locations[URIRef("https://example.test/b")].line == THIRD_LINE


def test_a_jsonld_term_without_an_iri_does_not_cost_the_regions(tmp_path: Path) -> None:
    text = (
        '{"@context": {"@vocab": "https://example.test/", "tags": {"@container": "@set"}},\n'
        ' "@id": "https://example.test/a", "@type": "' + OWL_CLASS + '"}'
    )
    index = _document(tmp_path, "a.jsonld", text).source_index
    assert index.locations[URIRef("https://example.test/a")] == Location(2, 9)
    assert index.problem is None


def test_a_locator_failure_is_logged_with_its_traceback(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def broken(*_args: object) -> dict[object, object]:
        raise RuntimeError("locator bug")

    monkeypatch.setattr(source_locations, "_locations", broken)
    with caplog.at_level("DEBUG", logger="ontolint.source_locations"):
        assert dict(source_locations.build_source_index(b"", "nt", "file:///a.nt", Graph()).locations) == {}
    assert [record.exc_info[0] if record.exc_info else None for record in caplog.records] == [RuntimeError]


@pytest.mark.parametrize(
    ("data", "fmt"),
    [
        (b"<a> <b> <c> .", "trix"),  # a format without a locator
        (b"\xff\xfe<a> <b> <c> .", "nt"),  # not UTF-8
        (b"<rdf:RDF", "xml"),  # malformed XML
        (b"{", "json-ld"),  # malformed JSON
    ],
)
def test_input_the_locator_cannot_read_gives_an_empty_index(data: bytes, fmt: str) -> None:
    index = source_locations.build_source_index(data, fmt, "file:///a", Graph())
    assert index.locations == {}
    assert index.problem is None


def test_a_jsonld_context_given_as_a_list_still_expands_compact_iris(tmp_path: Path) -> None:
    text = '{"@context": [{"ex": "https://example.test/"}],\n "@id": "ex:a", "@type": "' + OWL_CLASS + '"}'
    assert _document(tmp_path, "a.jsonld", text).source_index.locations[URIRef("https://example.test/a")] == Location(
        2, 9
    )


# Turtle and JSON-LD accept "s://]", but urllib.parse.urljoin raises ValueError on it (found by the region
# property test).
UNSPLITTABLE = "s://]"


@pytest.mark.parametrize(
    ("name", "text"),
    [
        (
            "a.ttl",
            f"<{UNSPLITTABLE}> a <https://example.test/K> .\n<https://example.test/a> a <https://example.test/K> .\n",
        ),
        (
            "a.jsonld",
            '[{"@id": "' + UNSPLITTABLE + '", "@type": "https://example.test/K"},\n'
            ' {"@id": "https://example.test/a", "@type": "https://example.test/K"}]',
        ),
    ],
    ids=["turtle", "json-ld"],  # RDFLib itself refuses this IRI in RDF/XML, so the locator never sees it
)
def test_an_iri_python_cannot_split_costs_only_its_own_region(tmp_path: Path, name: str, text: str) -> None:
    index = _document(tmp_path, name, text).source_index
    assert index.problem is None
    assert URIRef("https://example.test/a") in index.locations


# --- TriG (issue #6) ------------------------------------------------------------------------------

DATASETS = Path(__file__).parent / "fixtures" / "datasets"
EX = "https://example.test/"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
# Braces, "#" and "GRAPH" where they open nothing; ex:C is named in a comment and a string before its statement.
TRIG = (
    "# ex:C { ex:C a ex:K . }\n"
    "PREFIX ex: <https://example.test/>\n"
    "@prefix k: <https://example.test/k#> .\n"
    "ex:g1 {\n"
    '    ex:A a k:Class ; ex:note "a } { # GRAPH ex:C" .\n'
    "}\n"
    "GRAPH <https://example.test/g2> {\n"
    "    ex:A ex:p ex:B .  # ex:C }\n"
    "}\n"
    "{ ex:B ex:p ex:C }\n"
)


def test_trig_terms_are_located_inside_named_and_default_graph_blocks(tmp_path: Path) -> None:
    index = _document(tmp_path, "a.trig", TRIG).source_index
    assert index.problem is None
    # The graph labels ex:g1 and <g2> name no node of the merged graph; ``a`` is a keyword, not a term.
    assert dict(index.locations) == {
        URIRef(f"{EX}A"): Location(5, 5),  # the first of its two graphs
        URIRef(f"{EX}k#Class"): Location(5, 12),
        URIRef(f"{EX}note"): Location(5, 22),
        URIRef(f"{EX}p"): Location(8, 10),
        URIRef(f"{EX}B"): Location(8, 15),
        URIRef(f"{EX}C"): Location(10, 13),  # in the default-graph block
    }


@pytest.mark.parametrize(
    ("name", "text", "column"),
    [
        ("a.trig", f"<{EX}g> {{ <{EX}a> a <{EX}K> . }}\n<{EX}g> a <{EX}K> .\n", 1),
        ("a.nq", f"<{EX}a> <{RDF_TYPE}> <{EX}K> <{EX}g> .\n<{EX}g> <{RDF_TYPE}> <{EX}K> .\n", 101),
        ("a.jsonld", f'{{"@id": "{EX}g", "@type": "{EX}K", "@graph": [{{"@id": "{EX}a", "@type": "{EX}K"}}]}}\n', 9),
    ],
    ids=["trig", "nquads", "json-ld"],
)
def test_a_described_graph_name_is_located_at_its_first_occurrence_in_every_dataset_syntax(
    tmp_path: Path, name: str, text: str, column: int
) -> None:
    """A graph name that is also a node keeps its first lexical occurrence, its graph label, in each syntax."""
    index = _document(tmp_path, name, text).source_index
    assert index.locations[URIRef(f"{EX}g")] == Location(1, column)


def _turtle_twin(trig: str) -> str:
    """``trig`` with its graph-block lines blanked: its triples as Turtle, each on the same line and column.

    Only a line that opens a block (ends with ``{``) or closes one (is ``}``) is blanked, which fits both
    fixtures; a one-line block (``ex:g { ex:A a ex:K . }``) would leave a twin that is not Turtle.
    """
    lines = trig.splitlines(keepends=True)
    return "".join("\n" if line.rstrip().endswith("{") or line.strip() == "}" else line for line in lines)


def _regions(path: Path, capsys: pytest.CaptureFixture[str]) -> list[tuple[str, str, object]]:
    main([str(path), "--format", "sarif", "--fail-on", "never"])
    results = json.loads(capsys.readouterr().out)["runs"][0]["results"]
    return [(r["ruleId"], r["message"]["text"], r["locations"][0]["physicalLocation"].get("region")) for r in results]


@pytest.mark.parametrize("fixture", ["single_graph.trig", "one_term_two_graphs.trig"])
def test_a_trig_finding_has_the_region_of_its_turtle_twin(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], fixture: str
) -> None:
    trig = (DATASETS / fixture).read_text(encoding="utf-8")
    (tmp_path / "a.trig").write_text(trig, encoding="utf-8")
    twin = _turtle_twin(trig)
    assert len(Graph().parse(data=twin, format="turtle")) > 0  # the twin is Turtle, not a broken file
    (tmp_path / "a.ttl").write_text(twin, encoding="utf-8")
    regions = _regions(tmp_path / "a.trig", capsys)
    assert regions == _regions(tmp_path / "a.ttl", capsys)
    assert regions
    assert all(region is not None for _rule, _message, region in regions)


# --- Punctuation glued to a name (issue #61) ------------------------------------------------------

GLUE_HEADER = "@prefix ex: <https://example.test/> .\n"
B_IRI = f"{EX}B"


def _offset_location(text: str, offset: int) -> Location:
    line_start = text.rfind("\n", 0, offset) + 1
    return Location(text.count("\n", 0, offset) + 1, offset - line_start + 1)


def _glue_text(suffix: str, statements: str, header: str = GLUE_HEADER) -> str:
    """``statements`` as a Turtle/N3 file, or inside a TriG graph block."""
    return header + ("{\n" + statements + "\n}\n" if suffix == "trig" else statements)


# A statement whose only mention of ex:B / <.../B> is followed, with no space, by the punctuation under test.
GLUED_STATEMENTS = {
    ".": "ex:A ex:p {b}.\n",
    ";": "ex:A ex:p {b};\n    ex:q ex:C.\n",
    ",": "ex:A ex:p {b},\n    ex:C.\n",
}
SPELLINGS = ["ex:B", f"<{B_IRI}>"]


@pytest.mark.parametrize("suffix", ["ttl", "trig", "n3"])
@pytest.mark.parametrize("spelling", SPELLINGS, ids=["prefixed", "iri"])
@pytest.mark.parametrize("punctuation", sorted(GLUED_STATEMENTS))
def test_a_punctuation_glued_to_a_name_does_not_cost_its_region(
    tmp_path: Path, suffix: str, spelling: str, punctuation: str
) -> None:
    """Turtle's PN_LOCAL has no trailing ``.`` and no ``;`` or ``,``: the name ends before them (issue #61)."""
    text = _glue_text(suffix, GLUED_STATEMENTS[punctuation].format(b=spelling))
    index = _document(tmp_path, f"a.{suffix}", text).source_index
    assert index.problem is None
    assert index.locations[URIRef(B_IRI)] == _offset_location(text, text.index(spelling))


@pytest.mark.parametrize("suffix", ["ttl", "trig"])
@pytest.mark.parametrize(
    "statements",
    [
        "ex:A ex:p ex:B.",  # the end of the file (or of the block) right after the dot
        "ex:A ex:p ex:B.# the comment starts at once\n",
        "ex:A ex:p ex:B.\n",
        "ex:A ex:p ex:B;ex:q ex:C,ex:D.\n",  # nothing but punctuation between the names
    ],
    ids=["eof", "comment", "newline", "no-space"],
)
def test_glued_punctuation_is_no_part_of_a_name_whatever_follows_it(
    tmp_path: Path, suffix: str, statements: str
) -> None:
    text = _glue_text(suffix, statements)
    index = _document(tmp_path, f"a.{suffix}", text).source_index
    assert index.locations[URIRef(B_IRI)] == _offset_location(text, text.index("ex:B"))


@pytest.mark.parametrize(
    "tail", ["}\n", ".}\n", ";}\n", " }\n"], ids=["brace", "dot-brace", "semicolon-brace", "space"]
)
def test_a_trig_block_closed_straight_after_a_name_keeps_the_region(tmp_path: Path, tail: str) -> None:
    text = GLUE_HEADER + "ex:g {\n    ex:A ex:p ex:B" + tail
    index = _document(tmp_path, "a.trig", text).source_index
    assert index.locations[URIRef(B_IRI)] == Location(3, 15)


@pytest.mark.parametrize(
    "statement",
    ["ex:A ex:p ( ex:C ex:B).\n", "ex:A ex:p [ ex:q ex:B].\n", "ex:A ex:p ex:B#a comment\n    .\n"],
    ids=["paren", "bracket", "comment"],
)
def test_a_closing_bracket_or_comment_glued_to_a_name_is_no_part_of_it(tmp_path: Path, statement: str) -> None:
    # PN_LOCAL has none of ``)``, ``]`` and ``#`` unescaped either; the old pattern swallowed them all.
    text = GLUE_HEADER + statement
    index = _document(tmp_path, "a.ttl", text).source_index
    assert index.locations[URIRef(B_IRI)] == _offset_location(text, text.index("ex:B"))


@pytest.mark.parametrize(
    ("name", "local"),
    [
        ("ex:a.b", "a.b"),  # a dot inside a local name is part of it
        ("ex:a.b.c", "a.b.c"),
        ("ex:a:b.c", "a:b.c"),
        ("ex:a%2Eb", "a%2Eb"),  # a percent escape stays as spelled
        ("ex:a%2E", "a%2E"),  # ... also at the end of the name
        ("ex:a\\,b", "a,b"),  # an escaped , or ; is part of the name
        ("ex:a\\;b", "a;b"),
        ("ex:a\\.b", "a.b"),
        ("ex:a-", "a-"),
        ("ex:1.2", "1.2"),
    ],
)
@pytest.mark.parametrize("suffix", ["ttl", "trig"])
@pytest.mark.parametrize("punctuation", sorted(GLUED_STATEMENTS))
def test_a_local_name_keeps_its_inner_dots_and_escapes_before_glued_punctuation(
    tmp_path: Path, suffix: str, name: str, local: str, punctuation: str
) -> None:
    text = _glue_text(suffix, GLUED_STATEMENTS[punctuation].format(b=name))
    index = _document(tmp_path, f"a.{suffix}", text).source_index
    assert index.locations[URIRef(EX + local)] == _offset_location(text, text.index(name))


@pytest.mark.parametrize("punctuation", [".", ";", ","])
def test_an_empty_local_name_ends_before_the_punctuation_glued_to_it(tmp_path: Path, punctuation: str) -> None:
    # ``ex:.`` is the empty local name, then the end of the statement: the node is the namespace itself.
    statements = {".": "ex:A ex:p ex:.\n", ";": "ex:A ex:p ex:;\n    ex:q ex:C.\n", ",": "ex:A ex:p ex:,\n    ex:C.\n"}
    text = GLUE_HEADER + statements[punctuation]
    index = _document(tmp_path, "a.ttl", text).source_index
    assert index.locations[URIRef(EX)] == _offset_location(text, text.index("ex:" + punctuation))


@pytest.mark.parametrize("header", ["PREFIX ex: <https://example.test/>\n", "prefix ex: <https://example.test/>\n"])
def test_a_sparql_style_prefix_declaration_is_no_obstacle_to_a_glued_name(tmp_path: Path, header: str) -> None:
    text = header + "GRAPH ex:g { ex:A ex:p ex:B. }\n"
    index = _document(tmp_path, "a.trig", text).source_index
    assert index.locations[URIRef(B_IRI)] == _offset_location(text, text.index("ex:B"))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ex:a\\. .", {"a.": 1}),  # an escaped trailing dot belongs to the name; the next one ends it
        ("ex:a\\.. .", {"a.": 1}),
        ("ex:a..b .", {"a..b": 1}),  # a run of dots inside a name
        ("ex:a. ex:b.", {"a": 1, "b": 7}),
        ("ex:a.ex:b.", {"a.ex:b": 1}),  # a dot between two words is inner, whatever the words hold
        ("ex:a...", {"a": 1}),  # a run of dots after a name is no part of it
        ("ex:.a", {"": 1}),  # a local name cannot start with a dot
    ],
)
def test_the_local_name_follows_the_turtle_grammar_even_where_rdflib_is_lenient(
    text: str, expected: dict[str, int]
) -> None:
    nodes: set[Node] = {URIRef(EX + local) for local in [*expected, "other"]}
    found = source_locations._scan(text, "turtle", "", nodes, {"ex": EX})  # noqa: SLF001 -- no parse: some inputs are invalid
    assert found == {URIRef(EX + local): Location(1, column) for local, column in expected.items()}


def test_the_reproduction_of_issue_61_is_located_in_the_sarif_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "glued.ttl"
    path.write_text(
        "@prefix ex: <https://example.test/onto#> .\n"
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
        "ex:A a owl:Class ;\n"
        "    rdfs:subClassOf ex:B.\n",
        encoding="utf-8",
    )
    main([str(path), "--select", "OWL001", "--format", "sarif", "--fail-on", "never"])
    results = json.loads(capsys.readouterr().out)["runs"][0]["results"]
    regions = [r["locations"][0]["physicalLocation"].get("region") for r in results if "onto#B" in r["message"]["text"]]
    assert regions == [{"startLine": 5, "startColumn": 21}]


@pytest.mark.parametrize(
    "build",
    [
        lambda n: "ex:a" + "." * n + " .",  # a name, then a very long run of dots
        lambda n: "ex:" + "." * n + " .",  # an empty name, then the run
        lambda n: "ex:a" + ".a" * n + " .",  # many inner dots
        lambda n: "ex:a" + ".b." * n + " .",  # dot-name-dot, repeated
        lambda n: "ex:a." * n,  # many names, each glued to its dot
        lambda n: "ex:a" + "\\." * n + " .",  # escaped dots
        lambda n: "ex:a" + "..a" * n + " .",  # double dots inside the name
        lambda n: "ex:a" + "." * n + "\n" + "ex:" * n,  # the run, then many empty-name attempts
    ],
    ids=["trailing", "empty-name", "inner", "dot-name-dot", "many-names", "escaped", "double", "run-then-names"],
)
def test_the_scan_is_linear_on_long_runs_of_dots(build: Callable[[int], str]) -> None:
    # A name pattern that backtracked over the run for each of its dots would be quadratic on these inputs: minutes
    # at this size, against milliseconds when linear.
    text = build(200_000)
    started = time.perf_counter()
    nodes: set[Node] = {URIRef(EX + "a")}
    source_locations._scan(text, "turtle", "", nodes, {"ex": EX})  # noqa: SLF001
    assert time.perf_counter() - started < LINEAR_SCAN_SECONDS


# --- JSON-LD written by a Java tool (issue #7): Jena's riot, see tests/fixtures/java_jsonld/README.md ----

JAVA_JSONLD = Path(__file__).parent / "fixtures" / "java_jsonld"
# Jackson's DefaultPrettyPrinter (Jena's JSON-LD 1.0 writer) puts a space before the colon; the 1.1 writer does not.
JAVA_LAYOUTS = {"pets.jsonld10.jsonld": '"@id" : ', "pets.jsonld11.jsonld": '"@id": '}
_FOCUS = re.compile(r"Focus: (\S+)\. Suggestion: ")


# The committed bytes (.gitattributes checks them out with LF everywhere). A regeneration changes them, since
# both writers may order members and nodes differently on each run: update the digest with the files.
JAVA_DIGESTS = {
    "pets.jsonld10.jsonld": "015e37d13af4219297d73122c27811871657609082a7e1fefea9acc06fddd275",
    "pets.jsonld11.jsonld": "6f1d8ceb9db44a7d6a4405f0d33f9faf4dad90055c8f19a2331ac9dc5bfa5841",
}
# What each writer's layout looks like (the fixture README's table): indent unit, and Jackson's `[ {` / `}, {`.
JAVA_INDENTS = {"pets.jsonld10.jsonld": 2, "pets.jsonld11.jsonld": 4}


@pytest.mark.parametrize("fixture", JAVA_LAYOUTS)
def test_a_java_jsonld_fixture_is_the_committed_export(fixture: str) -> None:
    """The fixtures are worth keeping only as written: a reformatted copy no longer tests Jackson's layout."""
    assert hashlib.sha256((JAVA_JSONLD / fixture).read_bytes()).hexdigest() == JAVA_DIGESTS[fixture]


@pytest.mark.parametrize("fixture", JAVA_LAYOUTS)
def test_a_java_jsonld_fixture_has_its_writers_layout(fixture: str) -> None:
    """Checked on the layout, not the bytes, so that a regenerated file is held to what the README describes."""
    _assert_writers_layout(fixture, (JAVA_JSONLD / fixture).read_text(encoding="utf-8"))


def _assert_writers_layout(fixture: str, text: str) -> None:
    """The traits of ``fixture``'s writer that the README's table lists; not a full model of its printer."""
    separator, jackson = JAVA_LAYOUTS[fixture], fixture == "pets.jsonld10.jsonld"
    assert separator in text
    assert not any(other in text for other in set(JAVA_LAYOUTS.values()) - {separator})
    assert "\t" not in text  # indented with spaces only (a raw tab cannot occur inside a JSON string)
    assert list(json.loads(text)) == ["@graph", "@context"]  # both writers put the context last
    lines = text.splitlines()
    indents = {len(line) - len(line.lstrip(" ")) for line in lines}
    assert {indent % JAVA_INDENTS[fixture] for indent in indents} == {0}
    assert JAVA_INDENTS[fixture] in indents
    assert ("[ {" in text) is jackson
    assert any(line.strip() == "}, {" for line in lines) is jackson
    # The other writer's arrays: one value per line, never an object opened on the bracket's line.
    assert any(line.rstrip().endswith("[") for line in lines) is not jackson


@pytest.mark.parametrize("fixture", JAVA_LAYOUTS)
def test_a_java_jsonld_fixture_is_an_export_of_the_turtle_next_to_it(tmp_path: Path, fixture: str) -> None:
    text = (JAVA_JSONLD / fixture).read_text(encoding="utf-8")
    exported = _document(tmp_path, "a.jsonld", text).graph
    assert isomorphic(exported, Graph().parse(JAVA_JSONLD / "pets.ttl", format="turtle"))
    _graph_nodes_by_id(text)  # and each node is written once: a repeated node changes no graph, only the file


@pytest.mark.parametrize("fixture", JAVA_LAYOUTS)
def test_every_iri_subject_of_a_java_jsonld_file_is_located_at_an_id(tmp_path: Path, fixture: str) -> None:
    text = (JAVA_JSONLD / fixture).read_text(encoding="utf-8")
    document = _document(tmp_path, "a.jsonld", text)
    index = document.source_index
    assert index.problem is None
    assert {s for s in document.graph.subjects() if isinstance(s, URIRef)} <= set(index.locations)
    # A compact @id (the 1.1 writer's "xsd:nonNegativeInteger") names the node through the file's prefixes.
    prefixes = {k: v for k, v in json.loads(text)["@context"].items() if isinstance(v, str)}
    lines = text.split("\n")
    for node, location in index.locations.items():
        assert location.column is not None
        at = sum(len(line) + 1 for line in lines[: location.line - 1]) + location.column - 1
        assert text[:at].endswith(JAVA_LAYOUTS[fixture]), (node, location)
        prefix, _colon, local = json.JSONDecoder().raw_decode(text, at)[0].partition(":")
        assert prefixes.get(prefix, prefix + ":") + local == str(node), (node, location)


@pytest.mark.parametrize("cwd", [".", "tests"], ids=["from-root", "from-tests"])
@pytest.mark.parametrize("fixture", JAVA_LAYOUTS)
def test_a_java_jsonld_finding_has_a_region_at_its_focus(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, fixture: str, cwd: str
) -> None:
    """The findings of the Turtle the file was exported from, each with a region that spells its focus."""
    monkeypatch.chdir(Path(__file__).parent.parent / cwd)
    path = JAVA_JSONLD / fixture
    regions = _regions(path, capsys)
    turtle = _regions(JAVA_JSONLD / "pets.ttl", capsys)
    assert sorted(found[:2] for found in regions) == sorted(found[:2] for found in turtle)
    assert regions
    lines = path.read_text(encoding="utf-8").split("\n")
    for _rule, message, region in regions:
        assert isinstance(region, dict), message
        focus = _FOCUS.search(message)
        assert focus is not None, message
        spelled, _end = json.JSONDecoder().raw_decode(lines[region["startLine"] - 1], region["startColumn"] - 1)
        assert spelled == focus[1], (message, region)
    # A region is a start position only (no SARIF output has an end); it must sit in the file that was linted.
    main([str(path), "--format", "sarif", "--fail-on", "never"])
    results = json.loads(capsys.readouterr().out)["runs"][0]["results"]
    uris = {r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] for r in results}
    assert not any(Path(uri).is_absolute() for uri in uris), uris  # relative to the working directory...
    assert {(Path.cwd() / uri).resolve() for uri in uris} == {path.resolve()}  # ...and naming the linted file
    assert not any({"endLine", "endColumn"} & set(r["locations"][0]["physicalLocation"]["region"]) for r in results)


def _graph_nodes_by_id(text: str) -> dict[str, object]:
    """The export as data: its context, and its ``@graph`` nodes by ``@id``, each with its value arrays sorted.

    JSON-LD gives no order to a node's values, nor to the nodes of ``@graph``; only an ``@list`` is ordered.
    """
    data = json.loads(text)
    ids = [node["@id"] if isinstance(node, dict) else None for node in data["@graph"]]
    assert all(isinstance(node_id, str) for node_id in ids), ids  # a node without an @id would be dropped
    assert len(ids) == len(set(ids)), ids  # so would all but the last of two nodes with one @id
    return {"@context": data["@context"], **{node["@id"]: _unordered(node) for node in data["@graph"]}}


def _unordered(value: object, *, ordered: bool = False) -> object:
    if isinstance(value, dict):
        return {key: _unordered(item, ordered=key == "@list") for key, item in value.items()}
    if isinstance(value, list):
        items = [_unordered(item) for item in value]
        return items if ordered else sorted(items, key=lambda item: json.dumps(item, sort_keys=True))
    return value


def test_the_export_comparison_ignores_value_order_but_not_list_order() -> None:
    def export(labels: list[str], members: list[str]) -> str:
        node = {"@id": "x", "label": labels, "members": {"@list": members}}
        return json.dumps({"@graph": [node, {"@id": "y"}], "@context": {}})

    assert _graph_nodes_by_id(export(["a", "b"], ["m", "n"])) == _graph_nodes_by_id(export(["b", "a"], ["m", "n"]))
    assert _graph_nodes_by_id(export(["a", "b"], ["m", "n"])) != _graph_nodes_by_id(export(["a", "b"], ["n", "m"]))


# What riot runs, from the apache-jena-4.10.0.zip whose SHA-512 the fixture README gives: the SHA-256 of each
# file of lib/ and of log4j2.properties, one "path digest" line each, sorted. The test runs Java on exactly
# these files, as bin/riot would, so it does not depend on bin/riot or on CLASSPATH.
JENA_FILES_DIGEST = "b468c814526d32dfd6d98581aa8fcf4c9c9779017b1dfacaaff89fd9ec150f6d"
JENA_FILES_COUNT = 46
# Read by the JVM at start-up: each could add a class or an agent ahead of the verified jars.
JVM_ENVIRONMENT = ("CLASSPATH", "JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS")


def _jena_files(home: Path) -> list[Path]:
    files = [*sorted((home / "lib").iterdir()), home / "log4j2.properties"]
    listing = "".join(f"{f.relative_to(home).as_posix()} {hashlib.sha256(f.read_bytes()).hexdigest()}\n" for f in files)
    assert (len(files), hashlib.sha256(listing.encode()).hexdigest()) == (JENA_FILES_COUNT, JENA_FILES_DIGEST)
    return files


def _riot(home: Path, *args: str) -> str:
    """Run Jena's riot command on the verified jars only, with the JVM of JAVA_HOME or else of PATH."""
    *jars, logging = _jena_files(home)
    java = Path(os.environ["JAVA_HOME"]) / "bin" / "java" if "JAVA_HOME" in os.environ else shutil.which("java")
    assert java is not None, "no java on PATH and no JAVA_HOME"
    argv = [str(java), f"-Dlog4j.configurationFile={logging.as_uri()}", "-cp", os.pathsep.join(map(str, jars))]
    return subprocess.run(  # noqa: S603 -- the maintainer's own JVM, on jars whose digests were just checked
        [*argv, "riotcmd.riot", *args],
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
        env={key: value for key, value in os.environ.items() if key not in JVM_ENVIRONMENT},
    ).stdout


@pytest.mark.skipif("ONTOLINT_JENA_HOME" not in os.environ, reason="set ONTOLINT_JENA_HOME to an Apache Jena 4.10.0")
@pytest.mark.parametrize(
    ("fixture", "variant"), [("pets.jsonld10.jsonld", "JSONLD10"), ("pets.jsonld11.jsonld", "JSONLD")]
)
def test_a_java_jsonld_fixture_is_what_riot_writes_today(fixture: str, variant: str) -> None:
    """Corroborates the fixtures' origin: Jena 4.10.0's own jars, run now, write the fixture up to order.

    Neither writer reproduces its bytes (member and node order vary between runs), so the bytes are compared
    as data, and the layout by the same test as the committed file. The jars are the distribution's, checked
    file by file; the JVM is trusted, as the Python running the tests is. Not run in CI, which has no Java.
    """
    home = Path(os.environ["ONTOLINT_JENA_HOME"])
    assert _riot(home, "--version").strip() == "Apache Jena RIOT version 4.10.0"
    fresh = _riot(home, f"--formatted={variant}", str(JAVA_JSONLD / "pets.ttl"))
    assert _graph_nodes_by_id(fresh) == _graph_nodes_by_id((JAVA_JSONLD / fixture).read_text(encoding="utf-8"))
    _assert_writers_layout(fixture, fresh)
