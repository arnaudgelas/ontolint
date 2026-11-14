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
from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, SH

from ontolint import cli
from ontolint.cli import main
from ontolint.loader import load_graph
from ontolint.paths import resolve_inputs
from ontolint.policy import Policy
from ontolint.rules.support import stable_blank_id

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
    library, background = cli._shapes_closure(item, shapes, Policy(), cli.ImportOptions())  # noqa: SLF001
    assert library is None
    assert background is not None
    core = "https://example.test/onto/core#"
    assert (URIRef(core + "Authoritative"), RDF.type, URIRef(core + "Status")) in background
    assert not set(background.subjects(RDF.type, SH.NodeShape))
    shapes.remove((None, OWL.imports, None))
    assert cli._shapes_closure(item, shapes, Policy(), cli.ImportOptions()) == (None, None)  # noqa: SLF001


# --- what the background may hide, and what imported shape libraries add -------------------------------------

ONTO = """@prefix owl: <http://www.w3.org/2002/07/owl#> .
<https://ex.test/onto> a owl:Ontology .
<https://ex.test/knows> a owl:ObjectProperty .
<https://ex.test/x> <https://ex.test/knows> <https://ex.test/onlyInOntology> .
"""
OBJECT_SHAPES = """@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
<https://ex.test/shapes> a owl:Ontology ; owl:imports <https://ex.test/onto> .
<https://ex.test/S> a sh:NodeShape ; sh:targetObjectsOf <https://ex.test/knows> ;
    sh:property [ sh:path <https://ex.test/code> ; sh:minCount 1 ] .
"""
LIBRARY = """@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
<https://ex.test/lib> a owl:Ontology .
<https://ex.test/L> a sh:NodeShape ; sh:targetSubjectsOf <https://ex.test/knows> ;
    sh:property [ sh:path <https://ex.test/name> ; sh:minCount 1 ] .
<https://ex.test/Typed> a owl:Class .
"""
CATALOG = (
    '<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">'
    '<uri name="https://ex.test/onto" uri="onto.ttl"/><uri name="https://ex.test/lib" uri="lib.ttl"/></catalog>'
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    for name, text in {
        "onto.ttl": ONTO,
        "lib.ttl": LIBRARY,
        "shapes.ttl": OBJECT_SHAPES,
        "catalog-v001.xml": CATALOG,
        "data.ttl": "<https://ex.test/a> <https://ex.test/knows> <https://ex.test/b> .\n",
        "uses-lib.ttl": "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
        "<https://ex.test/shapes2> a owl:Ontology ; owl:imports <https://ex.test/lib> .\n",
    }.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    return tmp_path


def test_an_object_only_focus_of_the_data_survives_the_background(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # ex:b is only ever an object in the data; ex:onlyInOntology violates too, but only the background has it.
    _, without, _ = _shacl(capsys, project / "data.ttl", project / "shapes.ttl", "--fail-on", "never")
    _, with_background, _ = _shacl(
        capsys, project / "data.ttl", project / "shapes.ttl", "--follow-imports", "--fail-on", "never"
    )
    assert [f["focus"] for f in without] == ["https://ex.test/b"]
    assert [f["focus"] for f in with_background] == ["https://ex.test/b"]


def test_shapes_imported_by_the_shapes_file_are_validated(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, findings, err = _shacl(capsys, project / "data.ttl", project / "uses-lib.ttl", "--follow-imports")
    assert code == 1
    assert [f["focus"] for f in findings] == ["https://ex.test/a"]
    assert "Less than 1 values on <https://ex.test/a>-><https://ex.test/name>" in findings[0]["message"]
    assert "TOOL009: note: " in err
    assert "uses-lib.ttl imports shapes from " in err


def test_a_library_with_other_triples_is_shapes_and_background(project: Path) -> None:
    item = resolve_inputs([str(project / "uses-lib.ttl")], project)[0]
    shapes = load_graph(item, Policy())
    library, background = cli._shapes_closure(item, shapes, Policy(), cli.ImportOptions())  # noqa: SLF001
    assert library is not None
    assert background is not None
    typed = (URIRef("https://ex.test/Typed"), RDF.type, OWL.Class)
    assert typed in library
    assert typed in background
    assert set(library.subjects(RDF.type, SH.NodeShape)) == {URIRef("https://ex.test/L")}
    assert not set(background.subjects(RDF.type, SH.NodeShape))
    assert not set(background.subjects(SH.path, None))  # the inline property shape stays with its shape


def test_evidence_names_data_values_in_the_merged_graph_and_keeps_the_filter(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Both ex:a (data) and ex:x (background only) know a blank node; only ex:a's result is kept, and its blank
    # value has the same content-stable name with the ontology merged in as without it.
    (project / "onto.ttl").write_text(ONTO + "<https://ex.test/x> <https://ex.test/knows> [] .\n", encoding="utf-8")
    shapes = OBJECT_SHAPES.replace("sh:targetObjectsOf", "sh:targetSubjectsOf").replace(
        "sh:path <https://ex.test/code> ; sh:minCount 1", "sh:path <https://ex.test/knows> ; sh:nodeKind sh:IRI"
    )
    (project / "shapes.ttl").write_text(shapes, encoding="utf-8")
    (project / "data.ttl").write_text("<https://ex.test/a> <https://ex.test/knows> [ <https://ex.test/n> 1 ] .\n")
    _, without, _ = _shacl(capsys, project / "data.ttl", project / "shapes.ttl", "--fail-on", "never")
    _, merged, _ = _shacl(
        capsys, project / "data.ttl", project / "shapes.ttl", "--follow-imports", "--fail-on", "never"
    )
    assert [f["focus"] for f in merged] == [f["focus"] for f in without] == ["https://ex.test/a"]
    assert merged[0]["evidence"]["value"].startswith("_:")
    assert merged[0]["evidence"] == without[0]["evidence"]
    assert merged[0]["evidence"]["sourceConstraintComponent"] == str(SH.NodeKindConstraintComponent)


# --- a violation reached from the background, caused in the linted file (issue #9) ---------------------------

PREFIXES = "@prefix ex: <https://ex.test/> . @prefix sh: <http://www.w3.org/ns/shacl#> .\n"
PREFIXES += "@prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
NAMED = "ex:N sh:property [ sh:path ex:name ; sh:minCount 1 ] ."
"""A node shape the linted node fails: it has no ex:name."""


def _background_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], data: str, background: str, shapes: str, *extra: str
) -> tuple[int, list[Any]]:
    """Lint ``data`` against ``shapes``, which import an ontology holding ``background`` (``--follow-imports``)."""
    (tmp_path / ".git").mkdir(exist_ok=True)
    (tmp_path / "catalog-v001.xml").write_text(
        '<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">'
        '<uri name="https://ex.test/onto" uri="onto.ttl"/></catalog>',
        encoding="utf-8",
    )
    (tmp_path / "onto.ttl").write_text(f"{PREFIXES}<https://ex.test/onto> a owl:Ontology .\n{background}\n")
    (tmp_path / "shapes.ttl").write_text(
        f"{PREFIXES}<https://ex.test/shapes> a owl:Ontology ; owl:imports <https://ex.test/onto> .\n"
        f"ex:S a sh:NodeShape ; sh:targetClass ex:T ; {shapes}\n"
    )
    (tmp_path / "data.ttl").write_text(f"{PREFIXES}{data}\n")
    code, findings, err = _shacl(capsys, tmp_path / "data.ttl", tmp_path / "shapes.ttl", "--follow-imports", *extra)
    assert code in {0, 1}, err
    return code, findings


def _nested_foci(finding: dict[str, Any]) -> list[str]:
    """The focus of each result nested in ``finding``'s evidence, depth first."""
    foci, stack = [], list(reversed(finding["evidence"].get("detail", [])))
    while stack:
        detail = stack.pop()
        foci.append(detail["focusNode"])
        stack.extend(reversed(detail.get("detail", [])))
    return foci


@pytest.mark.parametrize("budget", [[], ["--max-validation-seconds", "120"]])
def test_a_violation_reached_from_the_background_is_kept_for_its_linted_cause(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], budget: list[str]
) -> None:
    """SHACL reports the violation on the background node; its nested cause is the linted file's node."""
    code, findings = _background_run(
        tmp_path,
        capsys,
        "ex:b a ex:Person .",
        "ex:bg a ex:T ; ex:knows ex:b .",
        f"sh:property [ sh:path ex:knows ; sh:node ex:N ] . {NAMED}",
        *budget,
    )
    assert [f["focus"] for f in findings] == ["https://ex.test/bg"]
    assert _nested_foci(findings[0]) == ["https://ex.test/b"]
    assert code == 1


def test_a_cause_nested_deeper_than_one_level_keeps_the_violation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """bg -> c (background only) -> b (linted): the value of the background node is not the linted node."""
    shapes = "sh:property [ sh:path ex:knows ; sh:node ex:N1 ] . "
    shapes += f"ex:N1 sh:property [ sh:path ex:knows ; sh:node ex:N ] . {NAMED}"
    code, findings = _background_run(
        tmp_path, capsys, "ex:b a ex:Person .", "ex:bg a ex:T ; ex:knows ex:c . ex:c ex:knows ex:b .", shapes
    )
    assert [f["focus"] for f in findings] == ["https://ex.test/bg"]
    assert _nested_foci(findings[0]) == ["https://ex.test/c", "https://ex.test/b"]
    assert code == 1


def test_a_violation_whose_causes_the_linted_file_never_mentions_is_dropped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, findings = _background_run(
        tmp_path,
        capsys,
        "ex:z a ex:Person .",
        "ex:bg a ex:T ; ex:knows ex:b .",
        f"sh:property [ sh:path ex:knows ; sh:node ex:N ] . {NAMED}",
    )
    assert (code, findings) == (0, [])


# ex:c is the linted file's, but never a focus: the sequence path reaches the linted value from ex:bg.
ADDRESS = "sh:property [ sh:path ( ex:knows ex:addr ) ; sh:node ex:Addr ] . "
ADDRESS += "ex:Addr sh:property [ sh:path ex:city ; sh:minCount 1 ] ."


def test_a_blank_cause_is_compared_by_its_identity_in_the_merged_graph(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    background = "ex:bg a ex:T ; ex:knows ex:c ."
    data = 'ex:c ex:addr [ ex:zip "1" ] .'
    code, findings = _background_run(tmp_path, capsys, data, background, ADDRESS)
    merged = Graph().parse(data=PREFIXES + data, format="turtle") + Graph().parse(
        data=PREFIXES + background, format="turtle"
    )
    (blank,) = merged.objects(URIRef("https://ex.test/c"), URIRef("https://ex.test/addr"))
    assert [f["focus"] for f in findings] == ["https://ex.test/bg"]
    assert _nested_foci(findings[0]) == [stable_blank_id(merged, blank)]
    assert code == 1


def test_a_cause_with_userinfo_is_compared_masked(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, findings = _background_run(
        tmp_path, capsys, "ex:c ex:addr <https://u:pw@h.test/b> .", "ex:bg a ex:T ; ex:knows ex:c .", ADDRESS
    )
    assert [f["focus"] for f in findings] == ["https://ex.test/bg"]
    assert _nested_foci(findings[0]) == ["https://****@h.test/b"]
    assert code == 1


def test_a_literal_cause_is_compared_in_its_ntriples_spelling(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shapes = "sh:property [ sh:path ( ex:knows ex:age ) ; sh:node ex:Int ] . ex:Int sh:datatype xsd:integer ."
    code, findings = _background_run(tmp_path, capsys, 'ex:c ex:age "x" .', "ex:bg a ex:T ; ex:knows ex:c .", shapes)
    assert [f["focus"] for f in findings] == ["https://ex.test/bg"]
    assert _nested_foci(findings[0]) == ['"x"']
    assert code == 1


def test_a_literal_cause_with_userinfo_is_compared_masked(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The evidence masks the userinfo of a literal's N-Triples spelling, so the linted literal is masked too."""
    shapes = "sh:property [ sh:path ( ex:knows ex:age ) ; sh:node ex:Int ] . ex:Int sh:datatype xsd:integer ."
    data = 'ex:c ex:age "https://u:pw@h.test/x" .'
    code, findings = _background_run(tmp_path, capsys, data, "ex:bg a ex:T ; ex:knows ex:c .", shapes)
    assert [f["focus"] for f in findings] == ["https://ex.test/bg"]
    assert _nested_foci(findings[0]) == ['"https://****@h.test/x"']
    assert code == 1
