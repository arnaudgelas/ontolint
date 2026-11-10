"""--convert-with-robot: OWL Functional, Manchester and OWL/XML files read through a ROBOT conversion to Turtle.

Every test but the last replaces ``subprocess.run``; the last converts real files with the ROBOT image and runs
only when ``ONTOLINT_ROBOT_IMAGE`` names one (the Validation workflow sets it).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from functools import partial
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pytest
from rdflib import OWL, RDF, URIRef

from ontolint.adapters import robot
from ontolint.adapters.robot import ConversionFailed, robot_convert
from ontolint.cli import main
from ontolint.loader import InputRejected, ParseFailure, load_document
from ontolint.paths import resolve_inputs
from ontolint.policy import Policy

FUNCTIONAL = (
    b"Prefix(:=<https://e.test/o#>)\nOntology(<https://e.test/o>\n"
    b"Import(<https://e.test/part>)\nDeclaration(Class(:A))\n)\n"
)
MANCHESTER = b"Prefix: : <https://e.test/part#>\nOntology: <https://e.test/part>\nClass: B\n"
OWLXML = (
    b'<?xml version="1.0"?>\n<Ontology xmlns="http://www.w3.org/2002/07/owl#" ontologyIRI="https://e.test/x">'
    b"<Import>https://e.test/y</Import></Ontology>\n"
)
TURTLE_OF_FUNCTIONAL = (
    b"<https://e.test/o> a <http://www.w3.org/2002/07/owl#Ontology> ;\n"
    b"  <http://www.w3.org/2002/07/owl#imports> <https://e.test/part> .\n"
    b"<https://e.test/o#A> a <http://www.w3.org/2002/07/owl#Class> .\n"
)


class FakeDocker:
    """Stands in for ``subprocess.run``: records each command and the catalog, then writes or fails."""

    def __init__(self, *results: tuple[int, str], output: bytes = TURTLE_OF_FUNCTIONAL) -> None:
        self.results = list(results) or [(0, "")]
        self.output = output
        self.commands: list[list[str]] = []
        self.catalogs: list[str] = []
        self.kwargs: list[dict[str, Any]] = []

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        self.kwargs.append(kwargs)
        directory = Path(next(value for value in command if value.endswith(":/output")).removesuffix(":/output"))
        self.catalogs.append((directory / "catalog.xml").read_text(encoding="utf-8"))
        code, stderr = self.results.pop(0)
        if code == 0:
            (directory / "converted.ttl").write_bytes(self.output)
        return subprocess.CompletedProcess(command, code, stdout="", stderr=stderr)


@pytest.fixture
def docker(monkeypatch: pytest.MonkeyPatch) -> FakeDocker:
    fake = FakeDocker()
    monkeypatch.setattr(robot.shutil, "which", lambda _name: "/usr/bin/docker")
    monkeypatch.setattr(robot.subprocess, "run", fake)
    return fake


def _file(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


# --- the adapter ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "syntax", "input_format"),
    [(FUNCTIONAL, "owl-functional", "ofn"), (MANCHESTER, "owl-manchester", "omn"), (OWLXML, "owl-xml", "owx")],
)
def test_the_container_reads_only_the_file_with_its_syntax_named(
    tmp_path: Path, docker: FakeDocker, data: bytes, syntax: str, input_format: str
) -> None:
    source = _file(tmp_path, "edit.owl", data)
    assert robot_convert(source, data, syntax, "img", 30) == TURTLE_OF_FUNCTIONAL
    command = docker.commands[0]
    assert command[command.index("--network") + 1] == "none"
    assert "--cap-drop" in command and "no-new-privileges" in command
    assert f"{source.resolve()}:/input/edit.owl:ro" in command  # the file, not its directory
    assert command[command.index("--input-format") + 1] == input_format  # never left to OWL API's guesses
    assert command[command.index("img") + 1 :][:3] == ["convert", "--catalog", "/output/catalog.xml"]
    assert command[-4:] == ["--format", "ttl", "--output", "/output/converted.ttl"]
    # ROBOT's exit code is read, not raised; its output is text, captured for the failure message.
    assert docker.kwargs == [{"capture_output": True, "text": True, "timeout": 30, "check": False}]


@pytest.mark.parametrize(
    ("data", "syntax", "iri"),
    [(FUNCTIONAL, "owl-functional", "https://e.test/part"), (OWLXML, "owl-xml", "https://e.test/y")],
)
def test_each_declared_import_is_answered_by_a_stub(
    tmp_path: Path, docker: FakeDocker, data: bytes, syntax: str, iri: str
) -> None:
    robot_convert(_file(tmp_path, "a.owl", data), data, syntax, "img", 30)
    assert f'<uri name="{iri}" uri="stub-0.owl"/>' in docker.catalogs[0]


def test_manchester_imports_are_stubbed_and_iris_are_escaped(tmp_path: Path, docker: FakeDocker) -> None:
    data = b'Ontology: <https://e.test/m>\nImport: <https://e.test/a?x=1&y="2">\nImport: <https://e.test/b>\n'
    robot_convert(_file(tmp_path, "m.omn", data), data, "owl-manchester", "img", 30)
    entries = ElementTree.fromstring(docker.catalogs[0])  # noqa: S314 -- the catalog this test's code wrote.
    assert [(entry.get("name"), entry.get("uri")) for entry in entries] == [
        ('https://e.test/a?x=1&y="2"', "stub-0.owl"),
        ("https://e.test/b", "stub-1.owl"),
    ]


def test_an_import_the_pattern_missed_is_stubbed_on_a_retry(tmp_path: Path, docker: FakeDocker) -> None:
    data = b"Prefix(ex:=<https://e.test/>)\nOntology(<https://e.test/o>\nImport(ex:part)\n)\n"
    missed = "UnloadableImportException: Could not load imported ontology: <https://e.test/part> Cause: e.test"
    docker.results = [(1, missed), (0, "")]
    assert robot_convert(_file(tmp_path, "a.ofn", data), data, "owl-functional", "img", 30) == TURTLE_OF_FUNCTIONAL
    assert "https://e.test/part" not in docker.catalogs[0]
    assert '<uri name="https://e.test/part" uri="stub-0.owl"/>' in docker.catalogs[1]


def test_retries_stop_when_the_same_import_fails_again(tmp_path: Path, docker: FakeDocker) -> None:
    failure = "Could not load imported ontology: <https://e.test/part> Cause: broken stub"
    docker.results = [(1, failure)]
    with pytest.raises(ConversionFailed, match="ROBOT could not convert it to Turtle: Could not load imported"):
        robot_convert(_file(tmp_path, "a.owl", FUNCTIONAL), FUNCTIONAL, "owl-functional", "img", 30)
    assert len(docker.commands) == 1


def test_retries_are_bounded(tmp_path: Path, docker: FakeDocker) -> None:
    docker.results = [(1, f"Could not load imported ontology: <https://e.test/{n}>") for n in range(10)]
    with pytest.raises(ConversionFailed, match="after stubbing 5 imports"):
        robot_convert(_file(tmp_path, "a.owl", FUNCTIONAL), FUNCTIONAL, "owl-functional", "img", 30)
    assert len(docker.commands) == robot.CONVERSION_ATTEMPTS


def test_a_manchester_failure_explains_the_missing_declarations(tmp_path: Path, docker: FakeDocker) -> None:
    docker.results = [(1, "INVALID ONTOLOGY FILE FORMAT ERROR Could not load a valid ontology\nUse -vvv")]
    with pytest.raises(ConversionFailed) as caught:
        robot_convert(_file(tmp_path, "m.omn", MANCHESTER), MANCHESTER, "owl-manchester", "img", 30)
    assert str(caught.value) == (
        "ROBOT could not convert it to Turtle: INVALID ONTOLOGY FILE FORMAT ERROR Could not load a valid ontology; "
        "ontolint converts each file without its imports, so a Manchester Syntax file must declare every class "
        "and property it uses"
    )
    docker.results = [(1, "")]
    with pytest.raises(
        ConversionFailed, match=r"^ROBOT could not convert it to Turtle: ROBOT failed without output\.$"
    ):
        robot_convert(_file(tmp_path, "a.owl", FUNCTIONAL), FUNCTIONAL, "owl-functional", "img", 30)


def test_a_slow_conversion_names_the_timeout_option(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def slow(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(robot.shutil, "which", lambda _name: "/usr/bin/docker")
    monkeypatch.setattr(robot.subprocess, "run", slow)
    with pytest.raises(ConversionFailed, match=r"within 7 s \(--robot-timeout\)"):
        robot_convert(_file(tmp_path, "a.owl", FUNCTIONAL), FUNCTIONAL, "owl-functional", "img", 7)


def test_without_docker_nothing_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(robot.shutil, "which", lambda _name: None)
    monkeypatch.setattr(robot.subprocess, "run", pytest.fail)
    with pytest.raises(ConversionFailed, match="docker executable was not found on PATH"):
        robot_convert(_file(tmp_path, "a.owl", FUNCTIONAL), FUNCTIONAL, "owl-functional", "img", 30)


# --- the loader -------------------------------------------------------------------------------------------------


def _load(path: Path, converter: Any) -> Any:
    return load_document(resolve_inputs([str(path)], path.parent)[0], Policy(owl_converter=converter), path.parent)


def test_the_loader_parses_the_converted_turtle(tmp_path: Path) -> None:
    calls: list[tuple[Path, bytes, str]] = []

    def convert(path: Path, data: bytes, syntax: str) -> bytes:
        calls.append((path, data, syntax))
        return TURTLE_OF_FUNCTIONAL

    data = b"# SPDX-License-Identifier: CC-BY-4.0\n" + FUNCTIONAL
    path = _file(tmp_path, "edit.owl", data)
    loaded = _load(path, convert)
    assert calls == [(path, data, "owl-functional")]
    assert (URIRef("https://e.test/o"), OWL.imports, URIRef("https://e.test/part")) in loaded.graph
    assert loaded.source.comment_license == "CC-BY-4.0"  # read from the file, not from the conversion
    assert loaded.source_index.locations == {}  # the converted text's lines are not the file's


def test_a_converter_failure_is_the_files_parse_failure(tmp_path: Path) -> None:
    def broken(_path: Path, _data: bytes, _syntax: str) -> bytes:
        raise ConversionFailed("ROBOT could not convert it to Turtle: boom")

    with pytest.raises(ParseFailure) as caught:
        _load(_file(tmp_path, "m.omn", MANCHESTER), broken)
    assert caught.value.cause_type == "ConversionFailed"
    assert (
        caught.value.detail == "m.omn is written in OWL Manchester Syntax; ROBOT could not convert it to Turtle: boom"
    )


def test_owl_xml_with_an_external_entity_is_refused_before_any_conversion(tmp_path: Path) -> None:
    hostile = OWLXML.replace(
        b"<Ontology", b'<!DOCTYPE Ontology [<!ENTITY x SYSTEM "file:///etc/passwd">]>\n<Ontology', 1
    )
    with pytest.raises(InputRejected) as caught:
        _load(_file(tmp_path, "x.owx", hostile), pytest.fail)
    assert caught.value.rule_id == "SEC010"


def test_a_policy_file_cannot_set_the_converter() -> None:
    policy = Policy.from_mapping({"owl_converter": "rm -rf /"})
    assert policy.owl_converter is None
    assert policy.unknown_keys == ("owl_converter",)


# --- the command line -------------------------------------------------------------------------------------------


def test_the_flag_lints_a_closure_of_converted_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    edit = _file(tmp_path, "edit.owl", FUNCTIONAL)
    _file(tmp_path, "part.omn", MANCHESTER)
    _file(
        tmp_path,
        "catalog-v001.xml",
        b'<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">'
        b'<uri name="https://e.test/part" uri="part.omn"/></catalog>',
    )
    part_turtle = b"<https://e.test/part> a <http://www.w3.org/2002/07/owl#Ontology> .\n"
    seen: list[tuple[str, str, int]] = []

    def convert(path: Path, _data: bytes, syntax: str, image: str, timeout: int) -> bytes:
        seen.append((path.name, syntax, timeout))
        assert image == "custom:1"
        return TURTLE_OF_FUNCTIONAL if path.name == "edit.owl" else part_turtle

    monkeypatch.setattr("ontolint.cli.robot_convert", convert)
    report = tmp_path / "report.json"
    argv = [str(edit), "--follow-imports", "--convert-with-robot", "--robot-image", "custom:1", "--robot-timeout", "9"]
    assert main([*argv, "--select", "SEC007", "--format", "json", "--output", str(report)]) == 0
    assert seen == [("edit.owl", "owl-functional", 9), ("part.omn", "owl-manchester", 9)]
    assert '"findings": []' in report.read_text(encoding="utf-8")  # the import resolved: no SEC007


def test_without_the_flag_the_message_names_it(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    edit = _file(tmp_path, "edit.owl", FUNCTIONAL)
    assert main([str(edit), "--output", str(tmp_path / "r.txt")]) == 2  # noqa: PLR2004
    assert "which ontolint cannot read; rerun with --convert-with-robot, convert it" in capsys.readouterr().err


# --- the real image ---------------------------------------------------------------------------------------------

IMAGE = os.environ.get("ONTOLINT_ROBOT_IMAGE")


@pytest.mark.skipif(not IMAGE or shutil.which("docker") is None, reason="set ONTOLINT_ROBOT_IMAGE to a ROBOT image")
def test_the_robot_image_converts_each_syntax_without_its_imports(tmp_path: Path) -> None:
    assert IMAGE is not None
    convert = partial(robot_convert, image=IMAGE, timeout=300)
    for name, data in (("o.ofn", FUNCTIONAL), ("m.omn", MANCHESTER), ("x.owx", OWLXML)):
        graph = _load(_file(tmp_path, name, data), convert).graph
        ontologies = set(graph.subjects(RDF.type, OWL.Ontology))
        assert len(ontologies) == 1, name  # no stub leaked into the output
        assert str(next(iter(ontologies))).startswith("https://e.test/"), name  # never OWL API's OBO fallback
    assert (URIRef("https://e.test/o"), OWL.imports, URIRef("https://e.test/part")) in _load(
        tmp_path / "o.ofn", convert
    ).graph
    undeclared = b"Prefix: : <https://e.test/m#>\nOntology: <https://e.test/m>\nClass: A\n  SubClassOf: p some A\n"
    with pytest.raises(ParseFailure, match="must declare every class and property it uses"):
        _load(_file(tmp_path, "bad.omn", undeclared), convert)
