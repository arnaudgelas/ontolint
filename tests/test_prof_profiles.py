"""``--shapes-from-profile``: the SHACL validator a W3C PROF profile names is used as ``--shapes``, offline.

The fixture copies FAIR-IMPACT MOD's layout: ``profile.ttl`` names ``prof:hasArtifact
<https://w3id.org/…/validator>`` with ``prof:hasRole role:validator``, and ``validator.ttl`` beside it
holds the shapes.  Its ontology IRI is the profile's, not the artifact's, as in MOD, so only the file
name links the two.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from rdflib import Graph

from ontolint.cli import main
from ontolint.imports import Catalog
from ontolint.prof import ProfileError, resolve_artifact, shapes_files, validator_artifacts

ARTIFACT = "https://example.test/profile/validator"
USAGE_ERROR = 2  # argparse's exit code
TOOL_FAILURE = 2

PREFIXES = """
@prefix dct: <http://purl.org/dc/terms/> .
@prefix prof: <http://www.w3.org/ns/dx/prof/> .
@prefix role: <http://www.w3.org/ns/dx/prof/role/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
"""


def _profile(*resources: str) -> str:
    body = " , ".join(f"[ a prof:ResourceDescriptor ; {r} ]" for r in resources)
    return PREFIXES + f"<https://example.test/profile> a prof:Profile ; prof:hasResource {body} ."


def _validator(artifact: str = ARTIFACT, standard: str = "<https://www.w3.org/TR/shacl/>") -> str:
    conforms = f"dct:conformsTo {standard} ; " if standard else ""
    return f"{conforms}prof:hasArtifact <{artifact}> ; prof:hasRole role:validator"


SHAPES = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix dct: <http://purl.org/dc/terms/> .
<https://example.test/profile> a owl:Ontology .
<https://example.test/profile/validator/shape> a sh:NodeShape ;
    sh:targetClass owl:Ontology ;
    sh:property [ sh:path dct:title ; sh:minCount 1 ] .
"""

ONTOLOGY = """
@prefix owl: <http://www.w3.org/2002/07/owl#> .
<https://example.test/onto> a owl:Ontology .
"""


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()  # the import root
    (tmp_path / "profile.ttl").write_text(_profile(_validator()), encoding="utf-8")
    (tmp_path / "validator.ttl").write_text(SHAPES, encoding="utf-8")
    (tmp_path / "onto.ttl").write_text(ONTOLOGY, encoding="utf-8")
    return tmp_path


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, dict[str, Any] | None, str]:
    code = main([*argv, "--format", "json", "--fail-on", "never", "--select", "SHACL001"])
    captured = capsys.readouterr()
    return code, json.loads(captured.out) if captured.out else None, captured.err


def _graph(text: str) -> Graph:
    return Graph().parse(data=text, format="turtle")


# --- which artifacts are validators --------------------------------------------------------------------


def test_a_validator_without_a_standard_or_conforming_to_shacl_is_shacl() -> None:
    graph = _graph(
        _profile(
            _validator("https://e.test/a", standard=""),
            _validator("https://e.test/b", standard="<http://www.w3.org/ns/shacl#>"),
            _validator("https://e.test/c", standard="<https://www.w3.org/TR/shacl/> , <https://e.test/house-style>"),
        )
    )
    found = validator_artifacts(graph)
    assert found.shacl == ("https://e.test/a", "https://e.test/b", "https://e.test/c")
    assert found.other == ()


def test_other_standards_other_roles_and_literal_artifacts_are_not_used() -> None:
    graph = _graph(
        _profile(
            _validator("https://e.test/shex", standard="<http://shex.io/shex-semantics/>"),
            "prof:hasArtifact <https://e.test/guide> ; prof:hasRole role:guidance",
            'prof:hasArtifact "https://e.test/literal" ; prof:hasRole role:validator',
        )
    )
    found = validator_artifacts(graph)
    assert found.shacl == ()
    assert found.other == ("https://e.test/shex",)


# --- resolving an artifact -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("artifact", "name"),
    [
        ("https://e.test/p/validator", "validator.ttl"),
        ("https://e.test/p/validator/", "validator.ttl"),
        ("https://e.test/p/validator.shacl.ttl", "validator.shacl.ttl"),
        ("https://e.test/p/rules", "rules.jsonld"),
    ],
)
def test_a_file_beside_the_profile_named_after_the_artifact(tmp_path: Path, artifact: str, name: str) -> None:
    (tmp_path / name).write_text("", encoding="utf-8")
    assert resolve_artifact(artifact, tmp_path / "profile.ttl", [], []) == tmp_path / name


def test_a_catalog_or_import_dir_without_the_artifact_falls_through(tmp_path: Path) -> None:
    (tmp_path / "validator.ttl").write_text("", encoding="utf-8")
    other = Catalog(tmp_path, {"https://e.test/other": tmp_path / "other.ttl"})
    found = resolve_artifact("https://e.test/p/validator", tmp_path / "profile.ttl", [other], [other])
    assert found == tmp_path / "validator.ttl"


@pytest.mark.parametrize("artifact", ["https://e.test/", "https://e.test/p/..", "urn:x"])
def test_an_artifact_without_a_usable_last_segment_resolves_to_nothing(tmp_path: Path, artifact: str) -> None:
    (tmp_path / "x.ttl").write_text("", encoding="utf-8")
    assert resolve_artifact(artifact, tmp_path / "profile.ttl", [], []) is None


def test_no_validator_and_an_unresolved_one_are_errors(tmp_path: Path) -> None:
    profile = tmp_path / "profile.ttl"
    with pytest.raises(ProfileError, match=r"names no SHACL validator \(prof:hasRole role:validator\) \(passed over"):
        shapes_files(profile, _graph(_profile(_validator(standard="<http://shex.io/shex-semantics/>"))), [], [])
    with pytest.raises(ProfileError, match="names no SHACL validator"):
        shapes_files(profile, _graph(PREFIXES), [], [])
    with pytest.raises(ProfileError, match="has no local copy: map it in catalog-v001.xml.*as validator.ttl"):
        shapes_files(profile, _graph(_profile(_validator())), [], [])


# --- end to end ----------------------------------------------------------------------------------------


def test_the_profile_gives_the_same_report_as_shapes(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    onto = str(project / "onto.ttl")
    _, direct, _ = _run(capsys, onto, "--shapes", str(project / "validator.ttl"))
    code, profiled, err = _run(capsys, onto, "--shapes-from-profile", str(project / "profile.ttl"))
    assert code == 0
    assert profiled == direct
    assert direct is not None
    assert [f["rule"] for f in direct["findings"]] == ["SHACL001"]
    assert f"TOOL007: note: {project / 'profile.ttl'} names validator {ARTIFACT}; using" in err


def test_a_catalog_beside_the_profile_maps_the_artifact(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (project / "shapes").mkdir()
    (project / "validator.ttl").rename(project / "shapes" / "dcat.ttl")
    (project / "catalog-v001.xml").write_text(
        '<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">'
        f'<uri name="{ARTIFACT}" uri="shapes/dcat.ttl"/></catalog>',
        encoding="utf-8",
    )
    _, document, err = _run(capsys, str(project / "onto.ttl"), "--shapes-from-profile", str(project / "profile.ttl"))
    assert document is not None
    assert len(document["findings"]) == 1
    assert "dcat.ttl as --shapes" in err


def test_an_import_dir_matches_the_artifact_by_ontology_iri(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mirror = project / "mirror"
    mirror.mkdir()
    (project / "validator.ttl").unlink()
    (mirror / "downloaded.ttl").write_text(SHAPES.replace("<https://example.test/profile> a", f"<{ARTIFACT}> a"))
    onto, profile = str(project / "onto.ttl"), str(project / "profile.ttl")
    _, document, _ = _run(capsys, onto, "--shapes-from-profile", profile, "--import-dir", str(mirror))
    assert document is not None
    assert len(document["findings"]) == 1


def test_a_validator_outside_the_import_root_is_refused(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    outside = project.parent / f"{project.name}-elsewhere.ttl"
    outside.write_text(SHAPES, encoding="utf-8")
    (project / "validator.ttl").unlink()
    (project / "catalog-v001.xml").write_text(
        '<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">'
        f'<uri name="{ARTIFACT}" uri="../{outside.name}"/></catalog>',
        encoding="utf-8",
    )
    code, document, err = _run(capsys, str(project / "onto.ttl"), "--shapes-from-profile", str(project / "profile.ttl"))
    assert (code, document) == (TOOL_FAILURE, None)
    assert f"SEC009: the validator {ARTIFACT} resolves to" in err
    assert "outside the import root" in err


def test_two_validators_are_merged(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    second = "https://example.test/profile/labels"
    (project / "profile.ttl").write_text(_profile(_validator(), _validator(second)), encoding="utf-8")
    (project / "labels.ttl").write_text(
        SHAPES.replace("validator/shape", "labels/shape").replace("dct:title", "dct:description"), encoding="utf-8"
    )
    _, document, err = _run(capsys, str(project / "onto.ttl"), "--shapes-from-profile", str(project / "profile.ttl"))
    assert document is not None
    assert len(document["findings"]) == 2  # noqa: PLR2004 -- one per validator
    assert err.count("TOOL007: note:") == 2  # noqa: PLR2004


def test_a_non_shacl_validator_is_passed_over_with_a_note(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    shex = "https://example.test/profile/shex"
    (project / "profile.ttl").write_text(
        _profile(_validator(), _validator(shex, standard="<http://shex.io/shex-semantics/>")), encoding="utf-8"
    )
    code, _, err = _run(capsys, str(project / "onto.ttl"), "--shapes-from-profile", str(project / "profile.ttl"))
    assert code == 0
    assert f"names validator {shex}, which is not SHACL; it is not used" in err


def test_a_profile_without_a_usable_validator_fails_the_run(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (project / "validator.ttl").unlink()
    code, document, err = _run(capsys, str(project / "onto.ttl"), "--shapes-from-profile", str(project / "profile.ttl"))
    assert (code, document) == (TOOL_FAILURE, None)
    assert err.startswith(f"TOOL001: --shapes-from-profile: the validator {ARTIFACT} of ")


@pytest.mark.parametrize("broken", ["profile.ttl", "validator.ttl"])
def test_a_parse_failure_names_the_file(project: Path, capsys: pytest.CaptureFixture[str], broken: str) -> None:
    # MOD's own files use prefixes they never declare (rdfs: in the profile, dcatnull: in the validator).
    (project / broken).write_text(PREFIXES.replace("@prefix rdfs", "#") + "<x> rdfs:label 'y' .", encoding="utf-8")
    code, _, err = _run(capsys, str(project / "onto.ttl"), "--shapes-from-profile", str(project / "profile.ttl"))
    assert code == TOOL_FAILURE
    assert f"INPUT001: RDF input parsing failed for {project / broken}: BadSyntax" in err


def test_shapes_and_a_profile_are_alternatives(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["x.ttl", "--shapes", "s.ttl", "--shapes-from-profile", "p.ttl"])
    assert raised.value.code == USAGE_ERROR
    assert "--shapes and --shapes-from-profile are alternatives" in capsys.readouterr().err
