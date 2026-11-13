"""No output channel repeats an IRI's userinfo: not a report, a baseline, stderr, a module or a graph name.

One ontology carries a userinfo in its ontology IRI, its term IRIs (through its namespace), its imports, an
annotation value used as a module name, a literal and every userinfo form: ``user:password``, a token sent
as the user name with a placeholder password (``x-oauth-basic``) or with none, a password holding ``@``
(which a URL parser reads up to the last ``@``) and a percent-encoded ``:``.  The command line runs over it
in every format and mode, and over datasets, shapes and inputs it refuses; no secret may appear anywhere.
Other inputs hold a scheme that follows a digit or a sign in its run of scheme characters
(``urn:x:1https://``, ``?next=-https://``), which a reader takes for an IRI.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from ontolint import main

PASSWORD = "Zq7Secret"  # noqa: S105 -- fake credentials the outputs must not repeat
TOKEN = "ghpTOKEN9xyz"  # noqa: S105 -- sent as the user name, with the placeholder password x-oauth-basic
BARE_TOKEN = "glpatTOKEN4abc"  # noqa: S105 -- sent as the user name, without a password
TAIL = "Zq8Tail"  # what follows the second "@" of a password that holds one
ENCODED = "Zq9Enc"  # after a percent-encoded ":", which is data, not the separator
SECRETS = (PASSWORD, TOKEN, BARE_TOKEN, TAIL, ENCODED)
ONTOLOGY = "https://****@example.test/onto"

ONTOLOGY_TTL = f"""@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix m: <https://example.test/meta#> .
@prefix ex: <https://alice:{PASSWORD}@example.test/onto#> .

<https://alice:{PASSWORD}@example.test/onto> a owl:Ontology ;
    owl:imports <https://bob:{PASSWORD}@example.test/imported> ,
        <https://{TOKEN}:x-oauth-basic@github.com/org/repo/raw/main/x.ttl> ,
        <https://{BARE_TOKEN}@gitlab.example/x.ttl> .

ex:Thing a owl:Class ; m:module <https://erin:{PASSWORD}@example.test/modules/core> .
ex:thing a owl:Class ; rdfs:label "thing" ; m:module "core" .
ex:Other a owl:Class ; rdfs:subClassOf ex:Thing ;
    rdfs:seeAlso <https://carl:pa@{TAIL}@example.test/x> , <https://dora%3A{ENCODED}@example.test/y> ;
    rdfs:comment "Mirror: https://alice:{PASSWORD}@example.test/mirror" ;
    rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:prop ] .
ex:prop a owl:ObjectProperty .
ex:Prop a owl:DatatypeProperty .
ex:item a ex:Thing .
"""
# The bob import maps to a file that does not exist: TOOL004 names the import on stderr.
CATALOG = f"""<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">
  <uri name="https://bob:{PASSWORD}@example.test/imported" uri="missing.ttl"/>
</catalog>
"""
SHAPES_TTL = f"""@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
<https://alice:{PASSWORD}@example.test/shapes#ThingShape> a sh:NodeShape ;
    sh:targetClass <https://alice:{PASSWORD}@example.test/onto#Thing> ;
    sh:property [ sh:path rdfs:label ; sh:minCount 1 ;
        sh:message "needs a label, see https://alice:{PASSWORD}@example.test/help" ] .
"""
GRAPH = f"https://carol:{PASSWORD}@example.test/graph1"
TRIG = f"""@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex: <https://alice:{PASSWORD}@example.test/onto#> .
<{GRAPH}> {{
  <https://alice:{PASSWORD}@example.test/onto> a owl:Ontology .
  ex:Thing a owl:Class .
  ex:Other a owl:Class ; rdfs:subClassOf ex:Thing .
}}
"""
NQUADS = (
    f"<https://alice:{PASSWORD}@example.test/onto> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> "
    f"<http://www.w3.org/2002/07/owl#Ontology> <{GRAPH}> .\n"
    f"<https://alice:{PASSWORD}@example.test/onto#Thing> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> "
    f"<http://www.w3.org/2002/07/owl#Class> <{GRAPH}> .\n"
)
# A syntax error just after a credentialed IRI: rdflib quotes the 60 bytes around it, starting mid-IRI.
BROKEN_TTL = (
    "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
    f"<https://alice:{PASSWORD}@example.test/onto#A> a owl:Class ; ; ] .\n"
)
# A scheme that follows a digit or a sign in its run of scheme characters: no URL parser reads one, but a reader
# does (#55).  Without an owl:Ontology every term is local, so the rules name each of them.
PREFIXED_TTL = f"""@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
<urn:x:1https://dave:{PASSWORD}@example.test/z#Thing> a owl:Class .
<https://example.test/r?next=-https://eve:{PASSWORD}@example.test/w#Other> a owl:Class ;
    rdfs:subClassOf <urn:x:1https://dave:{PASSWORD}@example.test/z#Thing> .
"""
PREFIXED_TRIG = f"""@prefix owl: <http://www.w3.org/2002/07/owl#> .
<urn:x:1https://carol:{PASSWORD}@example.test/graph1> {{
  <https://example.test/onto> a owl:Ontology .
  <https://example.test/onto#Thing> a owl:Class .
}}
"""
# The parser quotes the whole line, which starts with the scheme.
BROKEN_PREFIXED_TTL = (
    f"@prefix owl: <http://www.w3.org/2002/07/owl#> .\n<1https://alice:{PASSWORD}@example.test/A> a owl:Class ; ; ] .\n"
)
BROKEN_NT = f"<https://alice:{PASSWORD}@example.test/a> <http://x.test/p> <bad\n"
REMOTE_CONTEXT = f'{{"@context": "https://alice:{PASSWORD}@example.test/ctx.jsonld", "@id": "https://x.test/y"}}\n'
FORMATS = ("text", "json", "sarif")


@pytest.fixture
def run(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> Any:
    """Run the CLI in ``tmp_path`` (holding every input); return ``(exit code, stdout + stderr)``."""
    monkeypatch.chdir(tmp_path)
    for name, text in {
        "onto.ttl": ONTOLOGY_TTL,
        "shapes.ttl": SHAPES_TTL,
        "data.trig": TRIG,
        "data.nq": NQUADS,
        "broken.ttl": BROKEN_TTL,
        "prefixed.ttl": PREFIXED_TTL,
        "prefixed.trig": PREFIXED_TRIG,
        "broken-prefixed.ttl": BROKEN_PREFIXED_TTL,
        "broken.nt": BROKEN_NT,
        "remote.jsonld": REMOTE_CONTEXT,
    }.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    (tmp_path / "imports").mkdir()
    (tmp_path / "imports" / "onto.ttl").write_text(ONTOLOGY_TTL, encoding="utf-8")
    (tmp_path / "imports" / "catalog-v001.xml").write_text(CATALOG, encoding="utf-8")

    def _run(*argv: str) -> tuple[int, str]:
        code = main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out + captured.err

    return _run


def _leaks(text: str) -> list[str]:
    return [secret for secret in SECRETS if secret in text]


@pytest.mark.parametrize("output_format", FORMATS)
@pytest.mark.parametrize(
    "options",
    [
        (),
        ("--profile", "strict"),
        ("--module-by", "namespace"),
        ("--module-annotation", "m:module"),
        ("--shapes", "shapes.ttl"),
    ],
    ids=["default", "strict", "module-by", "module-annotation", "shapes"],
)
def test_no_report_repeats_a_userinfo(run: Any, output_format: str, options: tuple[str, ...]) -> None:
    code, out = run("onto.ttl", "--format", output_format, *options)
    assert code == 1, out
    assert _leaks(out) == []
    assert ONTOLOGY in out


@pytest.mark.parametrize("output_format", FORMATS)
@pytest.mark.parametrize("name", ["data.trig", "data.nq"])
def test_no_dataset_report_repeats_a_userinfo(run: Any, output_format: str, name: str) -> None:
    code, out = run(name, "--format", output_format, "--module-by", "namespace")
    assert code == 1, out
    assert _leaks(out) == []
    assert "https://****@example.test/graph1" in out


@pytest.mark.parametrize("output_format", FORMATS)
def test_an_import_closure_repeats_no_userinfo_on_stdout_or_stderr(run: Any, output_format: str) -> None:
    code, out = run("imports/onto.ttl", "--follow-imports", "--format", output_format)
    assert code == 1, out
    assert "TOOL004" in out
    assert _leaks(out) == []


def test_no_baseline_and_no_output_file_holds_a_userinfo(tmp_path: Path, run: Any) -> None:
    code, out = run("onto.ttl", "--write-baseline", "base.json", "--format", "sarif", "--output", "report.sarif")
    assert code == 1, out
    _code, again = run("onto.ttl", "--baseline", "base.json", "--format", "json")
    files = [(tmp_path / name).read_text(encoding="utf-8") for name in ("base.json", "report.sarif")]
    for text in (out, again, *files):
        assert _leaks(text) == []
    assert json.loads(again)["findings"] == []


@pytest.mark.parametrize("output_format", FORMATS)
def test_a_scheme_after_a_digit_or_a_sign_is_masked_in_every_output(
    tmp_path: Path, run: Any, output_format: str
) -> None:
    code, out = run("prefixed.ttl", "--format", output_format)
    assert code == 1, out
    assert _leaks(out) == []
    assert "urn:x:1https://****@example.test/z#Thing" in out
    assert "https://example.test/r?next=-https://****@example.test/w#Other" in out
    assert "SEC014" in out
    _code, out = run("prefixed.ttl", "--write-baseline", "base.json", "--format", output_format, "--output", "out")
    files = [(tmp_path / name).read_text(encoding="utf-8") for name in ("base.json", "out")]
    for text in (out, *files):
        assert _leaks(text) == []
    _code, out = run("prefixed.trig", "--format", output_format, "--module-by", "namespace")
    assert _leaks(out) == []
    assert "urn:x:1https://****@example.test/graph1" in out


@pytest.mark.parametrize("name", ["broken.ttl", "broken-prefixed.ttl", "broken.nt", "remote.jsonld"])
def test_a_refused_or_unparsable_input_repeats_no_userinfo_on_stderr(run: Any, name: str) -> None:
    code, out = run(name)
    assert code == 2, out  # noqa: PLR2004 -- a tool failure
    assert out.startswith(("INPUT001", "SEC006"))
    assert _leaks(out) == []


def test_iris_that_differ_only_in_their_userinfo_give_one_baseline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    documents = []
    for index, secret in enumerate(("first", "second")):
        folder = tmp_path / str(index)
        folder.mkdir()
        (folder / "onto.ttl").write_text(ONTOLOGY_TTL.replace(PASSWORD, secret), encoding="utf-8")
        monkeypatch.chdir(folder)
        assert main(["onto.ttl", "--write-baseline", "base.json"]) == 1
        documents.append((folder / "base.json").read_text(encoding="utf-8"))
    capsys.readouterr()
    assert documents[0] == documents[1]


def test_the_definition_hint_counts_credentialed_terms_and_masks_them(run: Any, tmp_path: Path) -> None:
    # TOOL005 looks up the terms of LEX002's masked foci: each stands for every term that masks to it.
    onto = f"https://alice:{PASSWORD}@example.test/onto"
    terms = "".join(
        f"<{onto}#C{i}> a owl:Class ; <https://bob:{PASSWORD}@v.test/termDefinition> 'Def {i}.'@en .\n"
        for i in range(12)
    )
    (tmp_path / "hint.ttl").write_text(
        f"@prefix owl: <http://www.w3.org/2002/07/owl#> .\n<{onto}> a owl:Ontology .\n{terms}", encoding="utf-8"
    )
    _code, out = run("hint.ttl", "--select", "LEX002", "--fail-on", "never")
    assert "TOOL005: note: 12 of the 12 terms LEX002 reports" in out
    assert "<https://****@v.test/termDefinition>" in out
    assert _leaks(out) == []


def test_a_credentialed_term_keeps_its_module_annotation(run: Any) -> None:
    code, out = run("onto.ttl", "--format", "json", "--module-annotation", "m:module", "--select", "SEC014")
    assert code == 1, out
    modules = {f["focus"]: f.get("modules") for f in json.loads(out)["findings"]}
    assert modules["https://****@example.test/onto#Thing"] == ["https://****@example.test/modules/core"]


def test_without_a_stderr_the_report_is_still_masked(
    run: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Under pythonw there is no stderr to wrap; the report is still masked and sys.stderr stays None.
    monkeypatch.setattr("sys.stderr", None)
    assert main(["onto.ttl", "--select", "SEC014"]) == 1
    assert sys.stderr is None
    assert _leaks(capsys.readouterr().out) == []


# A userinfo holding characters an IRI may not hold, which rdflib still reads: RDF/XML and JSON-LD take them as
# they stand, Turtle from a UCHAR escape (a brace, a caret, a space, a line break).  0.12.0 masked SEC014's
# focus for all of them, and every URL parser sends them as credentials.
ODD = ("OddSPACE", "OddBRACE", "OddPIPE", "OddCARET", "OddLINE", "OddJSON")
ODD_RDF = """<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:owl="http://www.w3.org/2002/07/owl#">
  <owl:Ontology rdf:about="https://alice:pw OddSPACE@example.test/onto"/>
  <owl:Class rdf:about="https://alice:pw{OddBRACE@example.test/onto#A"/>
  <owl:Class rdf:about="https://alice:pw|OddPIPE@example.test/onto#B"/>
</rdf:RDF>
"""
ODD_TTL = (
    "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
    "<https://alice:pw\\u005EOddCARET@example.test/onto> a owl:Ontology .\n"
    "<https://alice:pw\\u000AOddLINE@example.test/onto#A> a owl:Class .\n"
)
ODD_JSONLD = (
    '{"@id": "https://alice:pw{OddJSON@example.test/onto", "@type": "http://www.w3.org/2002/07/owl#Ontology"}\n'
)
# Messages that quote 60 characters of a value: a cut-off userinfo has no "@" left to be found by.
LONG = "LongSecret" + "x" * 70
TRUNCATED_TTL = f"""@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
<https://example.test/onto> a owl:Ontology .
<https://example.test/onto#C> a skos:Concept ; skos:prefLabel <https://alice:{LONG}@example.test/x> .
<https://example.test/onto#D> a skos:Concept ; skos:prefLabel "Mirror https://alice:{LONG}@example.test/x"@en .
<https://example.test/onto#E> a skos:Concept ; skos:prefLabel "Mirror https://alice:{LONG}@example.test/x"@en .
<https://example.test/onto#F> a skos:Concept ; skos:prefLabel "https://alice:{LONG}@example.test/y"@en ;
    skos:altLabel "https://alice:{LONG}@example.test/y"@en .
<https://example.test/onto#G> a skos:Concept ; skos:notation "https://alice:{LONG}@example.test/z" .
<https://example.test/onto#H> a skos:Concept ; skos:notation "https://alice:{LONG}@example.test/z" .
"""
# A shapes graph with an IRI pySHACL cannot serialise: SHACL001 fails and quotes it, cut at 80 characters.
UNSERIALISABLE_SHAPES = (
    f"@prefix sh: <http://www.w3.org/ns/shacl#> .\n<https://alice:{LONG}@example.test/a\\u0020b> a sh:NodeShape .\n"
)


def _odd_inputs(tmp_path: Path) -> None:
    for name, text in {
        "odd.rdf": ODD_RDF,
        "odd.ttl": ODD_TTL,
        "odd.jsonld": ODD_JSONLD,
        "long.ttl": TRUNCATED_TTL,
        "bad-shapes.ttl": UNSERIALISABLE_SHAPES,
    }.items():
        (tmp_path / name).write_text(text, encoding="utf-8")


@pytest.mark.parametrize("output_format", FORMATS)
def test_a_userinfo_with_characters_no_iri_may_hold_is_masked_and_reported(
    run: Any, tmp_path: Path, output_format: str
) -> None:
    _odd_inputs(tmp_path)
    code, out = run("odd.rdf", "odd.ttl", "odd.jsonld", "--format", output_format, "--profile", "strict")
    assert code == 1, out
    assert [secret for secret in ODD if secret in out] == []
    _code, sec014 = run("odd.rdf", "odd.ttl", "odd.jsonld", "--select", "SEC014")
    assert sec014.count("SEC014 https://****@example.test/onto") == 6, sec014  # noqa: PLR2004


@pytest.mark.parametrize("output_format", FORMATS)
def test_a_truncated_value_repeats_no_part_of_a_userinfo(run: Any, tmp_path: Path, output_format: str) -> None:
    _odd_inputs(tmp_path)
    code, out = run("long.ttl", "--format", output_format, "--profile", "strict")
    assert code == 1, out
    assert "SKOS013" in out
    assert "SKOS002" in out
    assert "LongSecret" not in out
    code, out = run("long.ttl", "--shapes", "bad-shapes.ttl", "--format", output_format)
    assert "SHACL001" in out
    assert "LongSecret" not in out


def test_a_digit_led_iri_resolved_as_relative_repeats_no_userinfo(run: Any, tmp_path: Path) -> None:
    # A scheme must start with a letter, so RDF/XML resolves "1https://..." against the document, which turns its
    # "//" into "/": the special scheme https still has an authority there (#55).
    (tmp_path / "digit.rdf").write_text(
        '<?xml version="1.0"?>\n'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:owl="http://www.w3.org/2002/07/owl#">\n'
        '  <owl:Ontology rdf:about="https://example.test/onto"/>\n'
        f'  <owl:Class rdf:about="1https://alice:{PASSWORD}@example.test/y"/>\n'
        "</rdf:RDF>\n",
        encoding="utf-8",
    )
    for output_format in FORMATS:
        _code, out = run("digit.rdf", "--format", output_format, "--profile", "strict")
        assert "example.test/y" in out, out
        assert _leaks(out) == []


def test_a_catalog_entry_for_a_credentialed_url_repeats_no_userinfo(run: Any, tmp_path: Path) -> None:
    # os.path.normpath turns "https://" into "https:/"; the git+https form is no URL a WHATWG parser reads either.
    (tmp_path / "imports" / "catalog-v001.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">\n'
        f'  <uri name="https://bob:{PASSWORD}@example.test/imported" uri="https://bob:{TAIL}@example.test/r.ttl"/>\n'
        f'  <rewriteURI uriStartString="https://{TOKEN}:x@github.com/" rewritePrefix="git+https://u:{ENCODED}@h/"/>\n'
        "</catalog>\n",
        encoding="utf-8",
    )
    code, out = run("imports/onto.ttl", "--follow-imports")
    assert code == 1, out
    assert "TOOL004" in out
    assert _leaks(out) == []


def test_a_bounded_worker_repeats_no_userinfo_on_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    # A parse or validation budget runs in a spawned worker, whose stderr is the process's own file descriptor:
    # rdflib's warning about an IRI it cannot serialise quotes the IRI there.
    monkeypatch.chdir(tmp_path)
    _odd_inputs(tmp_path)
    (tmp_path / "budget.json").write_text('{"max_parse_seconds": 60, "max_validation_seconds": 60}', encoding="utf-8")
    (tmp_path / "shapes.ttl").write_text(SHAPES_TTL, encoding="utf-8")
    assert main(["odd.rdf", "odd.jsonld", "--config", "budget.json", "--shapes", "shapes.ttl"]) == 1
    captured = capfd.readouterr()
    assert [secret for secret in ODD if secret in captured.out + captured.err] == []


def test_an_unexpected_exception_is_printed_masked(run: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object) -> str:
        raise ValueError(f"cannot render https://alice:{PASSWORD}@example.test/x")

    monkeypatch.setattr("ontolint.cli.render_report", fail)
    code, out = run("onto.ttl")
    assert code == 2, out  # noqa: PLR2004 -- a tool failure
    assert "ValueError: cannot render https://****@example.test/x" in out
    assert _leaks(out) == []
