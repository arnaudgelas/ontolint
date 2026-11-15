"""The end of a SARIF region (issue #68): it spans the token its start points at, in every syntax.

A region is the focus's first spelling: an IRI, a prefixed name or a blank-node label in the text syntaxes, a JSON
string in JSON-LD, the start tag of the element that names it in RDF/XML.  Its end is exclusive (one past the last
character, SARIF 2.1.0 section 3.30.9) and counts like its start, in Unicode code points (``columnKind``), a tab
as one.  An end that cannot be determined with the start's confidence is left out and the start is kept.
"""

from __future__ import annotations

import io
import json
import re
import time
from pathlib import Path

import pytest
from rdflib import RDF, BNode, Graph, URIRef
from rdflib.term import Node
from timing_support import LINEAR_SCAN_SECONDS

from ontolint import source_locations
from ontolint.cli import main
from ontolint.loader import load_document
from ontolint.models import Finding
from ontolint.paths import resolve_inputs
from ontolint.policy import Policy
from ontolint.reporting import FileReport, Location, Origin, RunReport, to_sarif_report

EX = "https://example.test/"
RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
LF = re.compile(r"\n")
XML_BREAK = re.compile(r"\r\n|\r|\n")  # what an XML parser counts as a line break


def _position(text: str, offset: int, breaks: re.Pattern[str] = LF) -> tuple[int, int]:
    """One-based line and column, in code points, of ``offset``: computed apart from the locator on purpose."""
    line, start = 1, 0
    for match in breaks.finditer(text, 0, offset):
        if match.end() <= offset:
            line, start = line + 1, match.end()
    return line, offset - start + 1


def _span(text: str, token: str, *, breaks: re.Pattern[str] = LF, after: int = 0) -> Location:
    """The region the first ``token`` at or after ``after`` should get: its start, and the end one past it."""
    offset = text.index(token, after)
    return Location(*_position(text, offset, breaks), *_position(text, offset + len(token), breaks))


def _locations(tmp_path: Path, name: str, text: str | bytes) -> dict[Node, Location]:
    path = tmp_path / name
    path.write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))
    document = load_document(resolve_inputs([name], tmp_path)[0], Policy(), tmp_path)
    assert document.source_index.problem is None
    return dict(document.source_index.locations)


# --- the Location value ---------------------------------------------------------------------------


def test_a_location_has_no_end_unless_it_is_given_one() -> None:
    location = Location(3, 7)
    assert (location.end_line, location.end_column) == (None, None)
    assert (Location(3, 7, 4, 2).end_line, Location(3, 7, 4, 2).end_column) == (4, 2)


@pytest.mark.parametrize(
    "arguments",
    [(3, 7, 3, None), (3, 7, None, 9), (3, None, 3, 9), (3, None, None, 9)],
    ids=["no-end-column", "no-end-line", "no-start-column", "end-column-only"],
)
def test_a_location_with_half_an_end_is_refused(arguments: tuple[int, int | None, int | None, int | None]) -> None:
    with pytest.raises(ValueError, match="end"):
        Location(*arguments)


@pytest.mark.parametrize("end", [(3, 7), (3, 6), (2, 99)], ids=["empty", "before", "earlier-line"])
def test_a_location_whose_end_is_not_after_its_start_is_refused(end: tuple[int, int]) -> None:
    with pytest.raises(ValueError, match="after"):
        Location(3, 7, *end)


def test_a_one_column_region_is_the_shortest() -> None:
    assert Location(3, 7, 3, 8).end_column == 8  # noqa: PLR2004
    assert Location(3, 7, 4, 1).end_line == 4  # noqa: PLR2004 -- an end at the first column of a later line


# --- SARIF rendering ------------------------------------------------------------------------------

FINDING = Finding("ONT001", "warning", f"{EX}a", "message", "suggestion")


def _region(location: Location | None) -> object:
    report = RunReport(
        (FileReport("a.ttl", "file:///a.ttl", (FINDING,), locations={FINDING: location} if location else {}),)
    )
    result = to_sarif_report(report)["runs"][0]["results"][0]
    return result["locations"][0]["physicalLocation"].get("region")


def test_sarif_writes_the_end_of_a_region_beside_its_start() -> None:
    assert _region(Location(3, 7, 4, 2)) == {"startLine": 3, "startColumn": 7, "endLine": 4, "endColumn": 2}


def test_sarif_writes_the_end_on_the_start_line_too() -> None:
    assert _region(Location(3, 7, 3, 12)) == {"startLine": 3, "startColumn": 7, "endLine": 3, "endColumn": 12}


def test_sarif_keeps_a_start_without_an_end_as_it_was() -> None:
    assert _region(Location(3, 7)) == {"startLine": 3, "startColumn": 7}
    assert _region(Location(3)) == {"startLine": 3}
    assert _region(None) is None


def test_sarif_related_locations_carry_the_end_too() -> None:
    other = Origin("b.ttl", "file:///b.ttl")
    file = FileReport(
        "a.ttl",
        "file:///a.ttl",
        (FINDING,),
        locations={FINDING: Location(1, 1, 1, 5)},
        others={FINDING: ((other, Location(2, 3, 2, 9)),)},
    )
    result = to_sarif_report(RunReport((file,)))["runs"][0]["results"][0]
    assert result["relatedLocations"][0]["physicalLocation"]["region"] == {
        "startLine": 2,
        "startColumn": 3,
        "endLine": 2,
        "endColumn": 9,
    }


# --- Turtle, N3 and TriG --------------------------------------------------------------------------

# CRLF, a tab, a non-BMP character, a glued dot and an IRI that no prefix shortens: the end of a name is the
# start's column plus the name's length in code points, whatever else the line holds.
TURTLE_BODY = (
    "ex:A a ex:K ;\r\n"
    "\tex:p <https://example.test/é😀> ,\r\n"
    "\t\tex:B. # ex:C\r\n"
    "<https://example.test/long/iri#frag> a ex:K ; ex:q ex:D;ex:r ex:E.\r\n"
)
TURTLE_TOKENS = {
    "A": "ex:A",
    "K": "ex:K",
    "p": "ex:p",
    "é😀": "<https://example.test/é😀>",
    "B": "ex:B",
    "long/iri#frag": "<https://example.test/long/iri#frag>",
    "q": "ex:q",
    "D": "ex:D",
    "r": "ex:r",
    "E": "ex:E",
}


@pytest.mark.parametrize("suffix", ["ttl", "n3", "trig"])
def test_a_turtle_family_region_spans_its_token(tmp_path: Path, suffix: str) -> None:
    header = f"@prefix ex: <{EX}> .\r\n"
    text = header + ("{\r\n" + TURTLE_BODY + "}\r\n" if suffix == "trig" else TURTLE_BODY)
    found = _locations(tmp_path, f"a.{suffix}", text)
    for local, token in TURTLE_TOKENS.items():
        assert found[URIRef(EX + local)] == _span(text, token), local


def test_a_turtle_region_ends_where_the_name_ends_not_where_the_statement_does(tmp_path: Path) -> None:
    text = f"@prefix ex: <{EX}> .\nex:A ex:p ex:B.\n"
    found = _locations(tmp_path, "a.ttl", text)
    assert found[URIRef(EX + "B")] == Location(2, 11, 2, 15)  # ex:B, not ex:B.
    assert found[URIRef(EX + "A")] == Location(2, 1, 2, 5)


def test_a_turtle_region_ending_at_the_end_of_the_file_has_its_end_after_the_last_character(tmp_path: Path) -> None:
    text = f"@prefix ex: <{EX}> .\nex:A ex:p ex:B."  # no final newline
    found = _locations(tmp_path, "a.ttl", text)
    assert found[URIRef(EX + "B")] == Location(2, 11, 2, 15)


def test_a_turtle_name_that_closes_a_line_ends_before_the_line_break(tmp_path: Path) -> None:
    text = f"@prefix ex: <{EX}> .\r\nex:A ex:p ex:B\r\n."
    found = _locations(tmp_path, "a.ttl", text)
    assert found[URIRef(EX + "B")] == Location(2, 11, 2, 15)  # the CR is not part of the name nor of the region


def test_a_turtle_directive_gives_no_region_and_so_no_end(tmp_path: Path) -> None:
    text = f"@prefix ex: <{EX}> .\n<{EX}o> a <http://www.w3.org/2002/07/owl#Ontology> .\n"
    assert _locations(tmp_path, "a.ttl", text)[URIRef(EX + "o")] == Location(2, 1, 2, len(f"<{EX}o>") + 1)


def test_a_term_of_a_graph_block_ends_at_its_token_in_trig(tmp_path: Path) -> None:
    text = f"@prefix ex: <{EX}> .\nex:g {{ ex:A ex:p <{EX}B> }}\n"
    found = _locations(tmp_path, "a.trig", text)
    assert found[URIRef(EX + "B")] == _span(text, f"<{EX}B>")
    assert found[URIRef(EX + "A")] == Location(2, 8, 2, 12)


# --- N-Triples and N-Quads ------------------------------------------------------------------------

NT_BODY = f"<{EX}a> <{EX}p> <{EX}é😀> .\r\n\t<{EX}b>\t<{EX}p>\t<{EX}a>\t.\n"


def test_an_ntriples_region_spans_its_iri(tmp_path: Path) -> None:
    found = _locations(tmp_path, "a.nt", NT_BODY)
    assert found[URIRef(EX + "a")] == _span(NT_BODY, f"<{EX}a>")
    assert found[URIRef(EX + "é😀")] == _span(NT_BODY, f"<{EX}é😀>")
    assert found[URIRef(EX + "b")] == _span(NT_BODY, f"<{EX}b>")
    assert found[URIRef(EX + "p")] == _span(NT_BODY, f"<{EX}p>")


def test_an_nquads_region_spans_its_iri_and_its_graph_label(tmp_path: Path) -> None:
    text = f"<{EX}a> <{EX}p> <{EX}é😀> <{EX}g> .\n<{EX}g> <{EX}q> <{EX}a> .\n"
    found = _locations(tmp_path, "a.nq", text)
    assert found[URIRef(EX + "g")] == _span(text, f"<{EX}g>")  # at the fourth term of the first quad
    assert found[URIRef(EX + "é😀")] == _span(text, f"<{EX}é😀>")


def test_a_blank_node_label_region_spans_the_label() -> None:
    text = f"\t_:b1 <{EX}p> <{EX}o> .\n<{EX}o> <{EX}q> _:b1 .\n"
    found = source_locations._scan(text, "nt", "", {BNode("b1")}, {})  # noqa: SLF001 -- RDFLib relabels blank nodes
    assert found[BNode("b1")] == Location(1, 2, 1, 6)


@pytest.mark.parametrize(
    ("after", "ends"),
    [
        (" .", True),
        (".\n", True),  # the end of the statement
        ("\t.", True),
        (";", True),
        (")", True),
        ("]", True),
        ("é .", False),  # a label may go on with any non-ASCII letter, which the pattern stops at
        (".b .", False),  # ... and with an inner dot
        ("· .", False),
        (".é .", False),
    ],
)
def test_a_blank_node_label_gets_an_end_only_where_the_label_cannot_go_on(after: str, ends: bool) -> None:
    text = "_:b1" + after
    end = len("_:b1")
    assert (source_locations._bnode_ends(text, end)) is ends  # noqa: SLF001


def test_a_blank_node_label_that_may_go_on_keeps_its_start_and_loses_its_end() -> None:
    text = f"_:b1é <{EX}p> <{EX}o> .\n"
    found = source_locations._scan(text, "nt", "", {BNode("b1"), URIRef(EX + "o")}, {})  # noqa: SLF001 -- no parse
    assert found[BNode("b1")] == Location(1, 1)
    assert found[URIRef(EX + "o")] == _span(text, f"<{EX}o>")


# --- RDF/XML --------------------------------------------------------------------------------------

XML_HEAD = f'<?xml version="1.0" encoding="UTF-8"?>\r\n<rdf:RDF xmlns:rdf="{RDF_NS}" xmlns:e="{EX}">\r\n'
XML_BODY = (
    f'\t<rdf:Description rdf:about="{EX}é😀"\r\n\t    e:q="a&gt;b > c"\n'
    f'\t   ><e:p rdf:resource="{EX}b"/></rdf:Description>\r\n'
    f'\t<e:K rdf:about="{EX}k"/>\r\n'
    f"\t<e:K\r\trdf:about='{EX}lone-cr'\r\r>\r</e:K>\r\n"
)
XML_TAIL = "</rdf:RDF>\r\n"
XML_TAGS = {
    "é😀": f'<rdf:Description rdf:about="{EX}é😀"\r\n\t    e:q="a&gt;b > c"\n\t   >',  # a ``>`` in a value is no end
    "b": f'<e:p rdf:resource="{EX}b"/>',
    "k": f'<e:K rdf:about="{EX}k"/>',
    "lone-cr": f"<e:K\r\trdf:about='{EX}lone-cr'\r\r>",  # a CR alone is a line break to an XML parser
}


def test_an_rdfxml_region_spans_the_start_tag_of_its_element(tmp_path: Path) -> None:
    text = XML_HEAD + XML_BODY + XML_TAIL
    found = _locations(tmp_path, "a.rdf", text)
    for local, tag in XML_TAGS.items():
        assert found[URIRef(EX + local)] == _span(text, tag, breaks=XML_BREAK), local


def test_an_rdfxml_region_spans_a_start_tag_over_several_lines() -> None:
    text = (
        XML_HEAD
        + f'  <rdf:Description\n      rdf:about="{EX}a"\n      >\n    <e:p>x</e:p>\n  </rdf:Description>\n'
        + XML_TAIL
    )
    found = _xml(text)
    assert found[URIRef(EX + "a")] == Location(3, 3, 5, 8)


def _xml(text: str | bytes) -> dict[Node, Location]:
    data = text if isinstance(text, bytes) else text.encode("utf-8")
    graph = Graph().parse(source=io.BytesIO(data), format="xml", publicID="file:///a.rdf")
    return dict(source_locations.build_source_index(data, "xml", "file:///a.rdf", graph).locations)


def test_an_rdfxml_region_in_a_file_with_a_byte_order_mark_counts_like_one_without() -> None:
    text = XML_HEAD + XML_BODY + XML_TAIL
    assert _xml(b"\xef\xbb\xbf" + text.encode("utf-8")) == _xml(text)


def test_an_rdfxml_region_on_a_very_long_line_ends_after_its_tag() -> None:
    text = XML_HEAD.replace("\r\n", "") + "".join(f'<e:K rdf:about="{EX}k{i}"/>' for i in range(30)) + XML_TAIL
    found = _xml(text)
    start = text.index(f'<e:K rdf:about="{EX}k17"/>')
    assert found[URIRef(EX + "k17")] == Location(1, start + 1, 1, start + 1 + len(f'<e:K rdf:about="{EX}k17"/>'))


@pytest.mark.parametrize(
    "prolog",
    ['<?xml version="1.0" encoding="ISO-8859-1"?>', '<?xml version="1.0" encoding="iso-8859-15"?>'],
)
def test_an_rdfxml_region_in_another_encoding_keeps_its_start_and_has_no_end(prolog: str) -> None:
    text = f'{prolog}\n<rdf:RDF xmlns:rdf="{RDF_NS}" xmlns:e="{EX}">\n <e:K rdf:about="{EX}k"/>\n</rdf:RDF>\n'
    data = text.replace("\n", "\n").encode("latin-1")
    location = _xml(data)[URIRef(EX + "k")]
    assert (location.line, location.column) == (3, 2)
    assert (location.end_line, location.end_column) == (None, None)


def test_an_rdfxml_region_in_utf_16_keeps_its_start_and_has_no_end() -> None:
    text = (
        f'<?xml version="1.0" encoding="UTF-16"?>\n<rdf:RDF xmlns:rdf="{RDF_NS}" xmlns:e="{EX}">\n'
        f' <e:K rdf:about="{EX}k"/>\n</rdf:RDF>\n'
    )
    location = _xml(b"\xff\xfe" + text.encode("utf-16-le"))[URIRef(EX + "k")]
    assert location.end_line is None and location.end_column is None
    assert location.line == 3  # noqa: PLR2004


def test_an_rdfxml_tag_end_is_the_first_unquoted_close() -> None:
    data = b"<a x='>' y=\">\" z='\"'>rest>"
    assert source_locations._tag_end(data, 0) == len(b"<a x='>' y=\">\" z='\"'>")  # noqa: SLF001
    assert source_locations._tag_end(b"<a x='>", 0) is None  # noqa: SLF001 -- an unterminated tag has no end
    assert source_locations._tag_end(b'<a x="b>', 0) is None  # noqa: SLF001


def test_the_byte_cursor_only_moves_forward() -> None:
    cursor = source_locations._ByteCursor(b"ab\ncd\r\nef\rgh")  # noqa: SLF001
    assert cursor.move(1) == (1, 2)
    assert cursor.move(4) == (2, 2)
    assert cursor.move(7) == (3, 1)  # after CRLF
    assert cursor.move(10) == (4, 1)  # after a lone CR
    assert cursor.move(11) == (4, 2)
    assert cursor.move(3) is None  # backwards: not answered
    assert cursor.move(11) == (4, 2)  # and the cursor is where it was


def test_the_byte_cursor_counts_code_points_not_bytes() -> None:
    cursor = source_locations._ByteCursor("é😀<b>".encode())  # noqa: SLF001
    assert cursor.move(len("é😀".encode())) == (1, 3)  # one-based: two characters before it


# --- JSON-LD --------------------------------------------------------------------------------------

JSON_TEXT = (
    '{"@context": {"ex": "https://example.test/"},\r\n'
    ' "@graph": [\r\n'
    '\t{"@id": "ex:a" , "@type": "ex:K"},{"@id":"https://example.test/\\ud83d\\ude00x","@type":"ex:K"},\n'
    '   {"@id" :\t"https://example.test/é😀","@type":"ex:K"}, {"@id": "https://example.test/slash\\/q","@type":"ex:K"}]}\n'
)
JSON_TOKENS = {
    "a": '"ex:a"',
    "😀x": '"https://example.test/\\ud83d\\ude00x"',  # six source characters for one
    "é😀": '"https://example.test/é😀"',  # one character, outside the BMP: two UTF-16 code units
    "slash/q": '"https://example.test/slash\\/q"',
}


def test_a_jsonld_region_spans_its_string(tmp_path: Path) -> None:
    found = _locations(tmp_path, "a.jsonld", JSON_TEXT)
    for local, token in JSON_TOKENS.items():
        assert found[URIRef(EX + local)] == _span(JSON_TEXT, token), local


def test_a_jsonld_region_ends_in_code_points_like_its_start(tmp_path: Path) -> None:
    text = '{"@id": "https://example.test/😀😀", "@type": "https://example.test/K"}'
    found = _locations(tmp_path, "a.jsonld", text)
    assert found[URIRef(EX + "😀😀")] == Location(1, 9, 1, 9 + len('"https://example.test/😀😀"'))


def test_a_jsonld_region_ends_before_the_whitespace_that_follows_the_string(tmp_path: Path) -> None:
    text = '{"@id": "https://example.test/a"\n\t\r\n , "@type": "https://example.test/K"}'
    found = _locations(tmp_path, "a.jsonld", text)
    assert found[URIRef(EX + "a")] == Location(1, 9, 1, 9 + len('"https://example.test/a"'))


def test_a_jsonld_value_that_is_not_a_string_gets_no_region_at_all(tmp_path: Path) -> None:
    text = '{"@id": "https://example.test/a", "https://example.test/p": {"@id": "https://example.test/b"}}'
    found = _locations(tmp_path, "a.jsonld", text)
    assert found[URIRef(EX + "b")] == _span(text, '"https://example.test/b"')


# --- the command line -----------------------------------------------------------------------------

OWL = "http://www.w3.org/2002/07/owl#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
# ``ex:a`` is a class with a superclass ``ex:missing`` that no triple declares: OWL001 is about the superclass.
NT_FILE = f"<{EX}a> <{RDF_NS}type> <{OWL}Class> .\n<{EX}a> <{RDFS}subClassOf> <{EX}missing> .\n"
TURTLE_FILE = f"@prefix ex: <{EX}> .\nex:a a <{OWL}Class> ;\n\t<{RDFS}subClassOf> ex:missing.\n"
TRIG_FILE = f"@prefix ex: <{EX}> .\nex:g {{ ex:a a <{OWL}Class> ;\n\t<{RDFS}subClassOf> ex:missing. }}\n"
RDFXML_FILE = (
    f'<?xml version="1.0"?>\n<rdf:RDF xmlns:rdf="{RDF_NS}" xmlns:owl="{OWL}" xmlns:rdfs="{RDFS}">\n'
    f'  <owl:Class rdf:about="{EX}a">\n    <rdfs:subClassOf rdf:resource="{EX}missing"/>\n  </owl:Class>\n</rdf:RDF>\n'
)
JSONLD_FILE = json.dumps(
    {"@id": EX + "a", "@type": OWL + "Class", RDFS + "subClassOf": {"@id": EX + "missing"}}, indent=2
)


def _sarif_regions(path: Path, capsys: pytest.CaptureFixture[str], *extra: str) -> list[tuple[str, dict[str, int]]]:
    main([str(path), "--format", "sarif", "--fail-on", "never", *extra])
    results = json.loads(capsys.readouterr().out)["runs"][0]["results"]
    return [(r["message"]["text"], r["locations"][0]["physicalLocation"]["region"]) for r in results]


@pytest.mark.parametrize(
    ("name", "text", "token"),
    [
        ("a.nt", NT_FILE, f"<{EX}missing>"),
        ("a.nq", NT_FILE.replace(" .\n", " <https://g.test/> .\n"), f"<{EX}missing>"),
        ("a.ttl", TURTLE_FILE, "ex:missing"),
        ("a.n3", TURTLE_FILE, "ex:missing"),
        ("a.trig", TRIG_FILE, "ex:missing"),
        ("a.rdf", RDFXML_FILE, f'<rdfs:subClassOf rdf:resource="{EX}missing"/>'),
        ("a.jsonld", JSONLD_FILE, f'"{EX}missing"'),
    ],
    ids=["nt", "nquads", "turtle", "n3", "trig", "rdfxml", "jsonld"],
)
def test_a_sarif_finding_carries_the_end_of_its_focus_in_every_syntax(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str, text: str, token: str
) -> None:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    found = _sarif_regions(path, capsys, "--select", "OWL001")
    regions = [region for message, region in found if f"Focus: {EX}missing." in message]
    expected = _span(text, token)
    assert regions == [
        {
            "startLine": expected.line,
            "startColumn": expected.column,
            "endLine": expected.end_line,
            "endColumn": expected.end_column,
        }
    ]


def test_a_text_report_is_unchanged_by_the_end(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "a.nt"
    path.write_text(NT_FILE, encoding="utf-8")
    main([str(path), "--fail-on", "never", "--select", "OWL001"])
    assert "endLine" not in capsys.readouterr().out


# --- linear time ----------------------------------------------------------------------------------


def test_finding_the_ends_of_a_long_xml_line_is_linear() -> None:
    # One 5 MB line: an end found by counting from the start of the line for each element would be quadratic.
    count = 30_000
    text = XML_HEAD.replace("\r\n", "") + "".join(f'<e:K rdf:about="{EX}k{i}"/>' for i in range(count)) + XML_TAIL
    graph = Graph().parse(data=text, format="xml", publicID="file:///a.rdf")
    started = time.perf_counter()
    found = source_locations.build_source_index(text.encode(), "xml", "file:///a.rdf", graph).locations
    assert time.perf_counter() - started < LINEAR_SCAN_SECONDS
    last = URIRef(f"{EX}k{count - 1}")
    assert found[last] == Location(
        1, len(text) - len(XML_TAIL) - len(f'<e:K rdf:about="{EX}k{count - 1}"/>') + 1, 1, len(text) - len(XML_TAIL) + 1
    )


def test_finding_the_ends_in_a_long_turtle_file_is_linear() -> None:
    body = "".join(f"ex:s{i} ex:p ex:o{i}, <{EX}n{i}> ; ex:q _:b{i} .\n" for i in range(30_000))
    text = f"@prefix ex: <{EX}> .\n" + body
    nodes: set[Node] = {URIRef(f"{EX}{name}{i}") for i in range(30_000) for name in ("s", "o", "n")}
    started = time.perf_counter()
    found = source_locations._scan(text, "turtle", "", nodes, {"ex": EX})  # noqa: SLF001
    assert time.perf_counter() - started < LINEAR_SCAN_SECONDS
    assert found[URIRef(f"{EX}n29999")].end_column is not None


def test_finding_the_ends_in_a_long_jsonld_file_is_linear(tmp_path: Path) -> None:
    text = json.dumps([{"@id": f"{EX}n{i}", "@type": f"{EX}K"} for i in range(30_000)])
    graph = Graph()  # built by hand: RDFLib's JSON-LD parser warns of a deprecated class
    for i in range(30_000):
        graph.add((URIRef(f"{EX}n{i}"), RDF.type, URIRef(f"{EX}K")))
    started = time.perf_counter()
    found = source_locations.build_source_index(text.encode(), "json-ld", "file:///a.jsonld", graph).locations
    assert time.perf_counter() - started < LINEAR_SCAN_SECONDS
    assert found[URIRef(f"{EX}n29999")].end_column is not None


# --- the guards of the RDF/XML end, one at a time (found by mutation testing) -----------------------


@pytest.mark.parametrize(
    ("data", "usable"),
    [
        (b'<?xml version="1.0"?><a/>', True),
        (b'<?xml version="1.0" encoding="UTF-8"?><a/>', True),
        (b"<?xml version='1.0' encoding='us-ascii'?><a/>", True),
        (b'\xef\xbb\xbf<?xml version="1.0" encoding="utf-8"?><a/>', True),
        (b'<?xml version="1.0" encoding="ISO-8859-1"?><a/>', False),
        (b"\xff\xfe<\x00a\x00/\x00>\x00", False),
        (b"\xfe\xff\x00<\x00a", False),
        (b"<\x00a\x00", False),
        (b"\x00<\x00a", False),
    ],
)
def test_only_utf8_and_ascii_documents_get_an_end(data: bytes, usable: bool) -> None:
    assert source_locations._utf8_compatible(data) is usable  # noqa: SLF001


def test_the_byte_cursor_counts_a_break_at_the_very_first_byte() -> None:
    cursor = source_locations._ByteCursor(b"\nab")  # noqa: SLF001
    assert cursor.move(1) == (2, 1)
    assert cursor.move(3) == (2, 3)


class _Parser:
    def __init__(self, index: int) -> None:
        self._parser = type("Expat", (), {"CurrentByteIndex": index})()


def _locator(data: bytes, index: int | None) -> source_locations._RDFXMLLocator:  # noqa: SLF001
    locator = source_locations._RDFXMLLocator("", set(), data)  # noqa: SLF001
    locator.parser = None if index is None else _Parser(index)
    return locator


def test_an_xml_end_is_given_when_the_bytes_and_the_parser_agree() -> None:
    assert _locator(b"<a>\n <b x='1'/>", 5)._tag_end(2, 2) == (2, 12)  # noqa: SLF001


def test_an_xml_end_is_refused_when_the_parser_position_disagrees() -> None:
    assert _locator(b"<a>\n <b x='1'/>", 5)._tag_end(2, 3) is None  # noqa: SLF001
    assert _locator(b"<a>\n <b x='1'/>", 5)._tag_end(1, 2) is None  # noqa: SLF001


def test_an_xml_end_is_refused_when_the_offset_is_not_a_tag() -> None:
    assert _locator(b"<a>\n x", 5)._tag_end(2, 2) is None  # noqa: SLF001 -- the position agrees, the byte is no tag


def test_an_xml_end_is_refused_when_the_tag_never_ends() -> None:
    assert _locator(b"<a x='1", 0)._tag_end(1, 1) is None  # noqa: SLF001


def test_an_xml_end_is_refused_without_a_parser_offset_or_a_usable_encoding() -> None:
    assert _locator(b"<a/>", None)._tag_end(1, 1) is None  # noqa: SLF001
    assert _locator(b'<?xml version="1.0" encoding="latin-1"?><a/>', 0)._tag_end(1, 1) is None  # noqa: SLF001
