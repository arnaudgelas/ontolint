"""Syntax sniffing: the content picks the parser when it clearly contradicts the file extension."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from ontolint.cli import main
from ontolint.syntax import choose, html_start, sniff

TURTLE = b"@prefix owl: <http://www.w3.org/2002/07/owl#> .\n<https://e.test/o> a owl:Ontology .\n"
RDFXML = (
    b'<?xml version="1.0"?>\n<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
    b'xmlns:owl="http://www.w3.org/2002/07/owl#"><owl:Ontology rdf:about="https://e.test/o"/></rdf:RDF>\n'
)
JSONLD = b'{"@id": "https://e.test/o", "@type": "http://www.w3.org/2002/07/owl#Ontology"}'
OWLXML = b'<?xml version="1.0"?>\n<Ontology xmlns="http://www.w3.org/2002/07/owl#" ontologyIRI="https://e.test/o"/>\n'
FUNCTIONAL = b"Prefix(:=<https://e.test/o#>)\nOntology(<https://e.test/o>\nImport(<https://e.test/x>)\n)\n"
MANCHESTER = b"Prefix: : <https://e.test/o#>\nOntology: <https://e.test/o>\nClass: A\n"


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (TURTLE, "turtle"),
        (b"# a comment\n\n<https://e.test/a> <https://e.test/p> <https://e.test/b> .\n", "turtle"),
        (b"PREFIX ex: <https://e.test/>\nex:a ex:p ex:b .\n", "turtle"),
        (b"[ a <https://e.test/K> ] .\n", "turtle"),  # a Turtle blank node, not a JSON array
        (b"\n[] a <https://e.test/K> .\n\n", "turtle"),  # an anonymous blank node, as RDFLib writes one
        (b"[ ] <https://e.test/p> <https://e.test/o> .\n", "turtle"),
        (RDFXML, "xml"),
        (b'<!DOCTYPE rdf:RDF [<!ENTITY ex "https://e.test/">]>\n' + RDFXML.split(b"\n", 1)[1], "xml"),
        (JSONLD, "json-ld"),
        (b'[ {"@id": "https://e.test/o"} ]', "json-ld"),
        (b"\xef\xbb\xbf" + JSONLD, "json-ld"),  # with a byte-order mark
        (b"[]", "json-ld"),  # an empty JSON-LD document
        (b"[ ]\n", "json-ld"),
        (b'{\n  "@context": {"ex": "https://e.test/"}\n}', "json-ld"),
        (b"{}", "json-ld"),  # an empty JSON object; a .trig or .n3 extension still reads it as a graph block
        (b"{ }", "json-ld"),
        (b"{ <https://e.test/a> a <https://e.test/K> . }\n", "trig"),  # the TriG default graph, as RDFLib writes it
        (b"{ _:b a <https://e.test/K> . }", "trig"),
        (b"{ [ a <https://e.test/K> ] . }", "trig"),
        (b"{ ex:a a ex:K . }", "trig"),
        (b"{ :a a :K . }", "trig"),  # the empty prefix
        (b"{\n  # a comment\n  <https://e.test/a> a <https://e.test/K> .\n}", "trig"),
        (b"{ # empty\n}", "trig"),  # JSON has no comments
        (b"{ 42 }", None),
        (OWLXML, "owl-xml"),
        (FUNCTIONAL, "owl-functional"),
        (MANCHESTER, "owl-manchester"),
        (b'<?xml version="1.0"?><html><body>Error 500</body></html>', None),  # XML, but not RDF
        (b"plain words", None),
    ],
)
def test_sniff_recognises_each_syntax(data: bytes, expected: str | None) -> None:
    assert sniff(data) == expected


def test_sniff_is_linear_on_a_run_of_hashes_after_a_brace() -> None:
    # CodeQL py/redos: a ``{`` followed by many ``#`` and no newline backtracked exponentially in the graph-block
    # pattern (about 40 ms at 20 ``#``, four times longer for every two more).
    data = b"{" + b"#" * 5000
    started = time.perf_counter()
    assert sniff(data) is None
    assert time.perf_counter() - started < 1


def test_choose_keeps_the_extension_within_the_text_family() -> None:
    assert choose("nt", b"<https://e.test/a> <https://e.test/p> <https://e.test/b> .\n") == "nt"
    assert choose("turtle", RDFXML) == "xml"
    assert choose("xml", TURTLE) == "turtle"
    assert choose("xml", b"unknown") == "xml"


@pytest.mark.parametrize(
    ("extension_format", "data", "expected"),
    [
        ("trig", b"{}", "trig"),  # an empty JSON-LD object and an empty TriG default graph: the extension decides
        ("n3", b"{ }\n", "n3"),
        ("json-ld", b"{}", "json-ld"),
        ("turtle", b"{}", "json-ld"),  # Turtle has no graph blocks, so only JSON-LD reads it
        ("trig", b"{ <https://e.test/a> a <https://e.test/K> . }", "trig"),
        ("xml", b"{ <https://e.test/a> a <https://e.test/K> . }", "trig"),
        ("trig", JSONLD, "json-ld"),  # a quoted key cannot open a graph block, so the content still wins
    ],
)
def test_choose_keeps_the_extension_when_the_content_reads_in_its_syntax(
    extension_format: str, data: bytes, expected: str
) -> None:
    assert choose(extension_format, data) == expected


def _lint(tmp_path: Path, name: str, data: bytes, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    path = tmp_path / name
    path.write_bytes(data)
    code = main([str(path), "--select", "ONT001", "--fail-on", "never", "--output", str(tmp_path / "report.txt")])
    return code, capsys.readouterr().err


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("modl.owl", TURTLE),
        ("a.ttl", RDFXML),
        ("a.rdf", JSONLD),
        ("anon.ttl", b"[] a <https://e.test/K> .\n"),
        ("default.trig", b"{ <https://e.test/o> a <http://www.w3.org/2002/07/owl#Ontology> . }\n"),
        ("empty.trig", b"{}\n"),
    ],
)
def test_a_mismatched_extension_still_parses(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str, data: bytes
) -> None:
    assert _lint(tmp_path, name, data, capsys) == (0, "")


@pytest.mark.parametrize(
    ("data", "syntax"),
    [(FUNCTIONAL, "OWL Functional Syntax"), (MANCHESTER, "OWL Manchester Syntax"), (OWLXML, "OWL/XML")],
)
def test_a_non_rdf_owl_syntax_is_named_with_a_way_forward(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], data: bytes, syntax: str
) -> None:
    code, err = _lint(tmp_path, "edit.owl", data, capsys)
    assert code == 2  # noqa: PLR2004
    assert err.startswith("INPUT001: RDF input parsing failed: UnsupportedSyntax: ")
    assert f"is written in {syntax}" in err
    assert "robot convert --input edit.owl --output edit.ttl" in err


def test_rdf_xml_under_a_turtle_name_still_gets_the_dtd_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    hostile = (
        b'<?xml version="1.0"?>\n<!DOCTYPE rdf:RDF [<!ENTITY x SYSTEM "file:///etc/passwd">]>\n'
        + RDFXML.split(b"\n", 1)[1]
    )
    code, err = _lint(tmp_path, "innocent.ttl", hostile, capsys)
    assert code == 2  # noqa: PLR2004
    assert err.startswith("SEC010: ")


def test_an_html_page_inside_turtle_is_pointed_at(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    page = b"<html>\n<head><title>Error 500 </title></head>\n<body>oops</body>\n</html>\n"
    code, err = _lint(tmp_path, "kb.ttl", TURTLE + b"\n" + page, capsys)
    assert code == 2  # noqa: PLR2004
    assert "an HTML page starts at line 4 (a web page or server error saved in place of RDF?)" in err
    assert html_start(TURTLE) is None
