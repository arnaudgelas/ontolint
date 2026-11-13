"""Source-position recovery for SARIF results."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from rdflib import Graph, URIRef
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


# --- JSON-LD written by a Java tool (issue #7): Jena's riot, see tests/fixtures/java_jsonld/README.md ----

JAVA_JSONLD = Path(__file__).parent / "fixtures" / "java_jsonld"
# Jackson's DefaultPrettyPrinter (Jena's JSON-LD 1.0 writer) puts a space before the colon; the 1.1 writer does not.
JAVA_LAYOUTS = {"pets.jsonld10.jsonld": '"@id" : ', "pets.jsonld11.jsonld": '"@id": '}
_FOCUS = re.compile(r"Focus: (\S+)\. Suggestion: ")


@pytest.mark.parametrize(("fixture", "separator"), JAVA_LAYOUTS.items(), ids=JAVA_LAYOUTS.keys())
def test_a_java_jsonld_fixture_keeps_its_writers_layout(fixture: str, separator: str) -> None:
    """The fixtures are worth keeping only as written: a reformatted copy no longer tests Jackson's layout."""
    text = (JAVA_JSONLD / fixture).read_text(encoding="utf-8")
    assert separator in text
    assert not any(other in text for other in set(JAVA_LAYOUTS.values()) - {separator})


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


@pytest.mark.parametrize("fixture", JAVA_LAYOUTS)
def test_a_java_jsonld_finding_has_a_region_at_its_focus(capsys: pytest.CaptureFixture[str], fixture: str) -> None:
    """The findings of the Turtle the file was exported from, each with a region that spells its focus."""
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
