"""``--pattern-library DIR``: lint an index ontology against the pattern ontologies under ``DIR``.

The fixture copies MODL's layout: ``lib/index.ttl`` describes patterns as individuals of its own
``Pattern`` class (and categories of a ``Category`` class), each pattern is ``lib/<name>/<name>.ttl``
with an ontology IRI in another namespace, and pattern headers name related patterns by IRI literals.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from ontolint.cli import main
from ontolint.library import load_library
from ontolint.models import LibraryMember
from ontolint.policy import Policy
from ontolint.rules.library import library_namespace, normalise_name

TOOL_FAILURE = 2
DOMAIN = "https://example.test/domain/lib/"
INDEX_NS = "https://example.test/purl/lib#"

INDEX = f"""
@prefix : <{INDEX_NS}> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
<https://example.test/purl/lib> a owl:Ontology .
:Pattern a owl:Class .
:Category a owl:Class .
:Events a owl:NamedIndividual , :Category .
:AgentRole a owl:NamedIndividual , :Pattern .
:Event a owl:NamedIndividual , :Pattern ; rdfs:isDefinedBy <{DOMAIN}event> .
:Ghost a owl:NamedIndividual , :Pattern .
"""


def _pattern(iri: str, name: str, *related: str) -> str:
    refs = "".join(f' ; opla-core:hasRelatedPattern "{r}"^^rdfs:Literal' for r in related)
    return f"""
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix opla-core: <http://ontologydesignpatterns.org/opla-core#> .
<{iri}> a owl:Ontology ; opla-core:hasPatternName "{name}" ; rdfs:comment "draft"{refs} .
<{iri}#Thing> a owl:Class ; rdfs:label "thing" .
"""


@pytest.fixture
def library(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    lib = tmp_path / "lib"
    for directory, iri, name, related in (
        ("agent-role", DOMAIN + "agentrole", "Agent Role", (DOMAIN + "agent", DOMAIN + "event")),
        ("event", DOMAIN + "event", "Event Pattern", ()),
        ("place", DOMAIN + "place", "Place", ()),
    ):
        (lib / directory).mkdir(parents=True)
        (lib / directory / f"{directory}.ttl").write_text(_pattern(iri, name, *related), encoding="utf-8")
    (lib / "index.ttl").write_text(INDEX, encoding="utf-8")
    (lib / "README.md").write_text("not RDF", encoding="utf-8")
    return lib


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, dict[str, Any] | None, str]:
    code = main([*argv, "--format", "json", "--fail-on", "never", "--select", "LIB"])
    captured = capsys.readouterr()
    return code, json.loads(captured.out) if captured.out else None, captured.err


def _findings(document: dict[str, Any] | None) -> list[tuple[str, str, str]]:
    assert document is not None
    return [(f["rule"], f["focus"], Path(f["path"]).name) for f in document["findings"]]


def test_the_index_and_its_members_are_compared(library: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, document, err = _run(capsys, str(library / "index.ttl"), "--pattern-library", str(library))
    assert code == 0
    assert _findings(document) == [
        ("LIB001", INDEX_NS + "AgentRole", "index.ttl"),
        ("LIB001", INDEX_NS + "Ghost", "index.ttl"),
        ("LIB002", DOMAIN + "place", "place.ttl"),
        ("LIB003", DOMAIN + "agentrole", "agent-role.ttl"),
    ]
    assert document is not None
    messages = {f["focus"]: f["message"] for f in document["findings"]}
    assert messages[INDEX_NS + "AgentRole"] == (
        f"Index entry names no pattern ontology by IRI; <{DOMAIN}agentrole> has its name: link them "
        f"(for example rdfs:isDefinedBy <{DOMAIN}agentrole>)."
    )
    assert messages[DOMAIN + "agentrole"] == (
        f"The header names <{DOMAIN}agent> (hasRelatedPattern), which no pattern ontology of the library declares."
    )
    assert "TOOL008" not in err  # README.md is not an RDF file; the index is not a member


def test_member_findings_point_at_the_member_file_in_sarif(library: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main([str(library / "index.ttl"), "--pattern-library", str(library), "--format", "sarif", "--select", "LIB002"])
    sarif = json.loads(capsys.readouterr().out)
    (result,) = sarif["runs"][0]["results"]
    physical = result["locations"][0]["physicalLocation"]
    assert physical["artifactLocation"]["uri"].endswith("lib/place/place.ttl")
    assert "region" not in physical


def test_an_unparseable_member_is_skipped_and_absence_is_hedged(
    library: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (library / "broken").mkdir()
    (library / "broken" / "broken.ttl").write_text('<x> <y> "unterminated .', encoding="utf-8")
    _, document, err = _run(capsys, str(library / "index.ttl"), "--pattern-library", str(library))
    assert "TOOL008: warning: " in err
    assert "broken.ttl in the pattern library is skipped: " in err
    assert document is not None
    messages = {(f["rule"], f["focus"]): f["message"] for f in document["findings"]}
    caveat = " Some files of the library did not parse (TOOL008), so it may be in one of them."
    assert messages[("LIB001", INDEX_NS + "Ghost")].endswith(caveat)
    assert messages[("LIB003", DOMAIN + "agentrole")].endswith(caveat)
    assert not messages[("LIB001", INDEX_NS + "AgentRole")].endswith(caveat)  # it has a same-named member
    assert not messages[("LIB002", DOMAIN + "place")].endswith(caveat)


def test_without_the_option_the_rules_are_skipped(library: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, document, _ = _run(capsys, str(library / "index.ttl"))
    assert code == 0
    assert document is not None
    assert document["findings"] == []
    executions = {x["rule"]: x for x in document["files"][0]["executions"]}
    assert executions["LIB001"] == {
        "rule": "LIB001",
        "status": "skipped",
        "detail": "no pattern library was supplied (--pattern-library)",
    }


def test_a_missing_directory_is_a_tool_failure(library: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, document, err = _run(capsys, str(library / "index.ttl"), "--pattern-library", str(library / "nope"))
    assert (code, document) == (TOOL_FAILURE, None)
    assert err.strip() == f"TOOL001: --pattern-library {library / 'nope'} is not a directory"


def test_exactly_max_imported_files_is_accepted(
    library: Path, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    config = tmp_path / "policy.json"
    config.write_text(json.dumps({"max_imported_files": 3}), encoding="utf-8")  # the three patterns
    code, _, err = _run(capsys, str(library / "index.ttl"), "--pattern-library", str(library), "--config", str(config))
    assert code == 0
    assert "SEC015" not in err


def test_too_many_files_is_refused(library: Path, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    config = tmp_path / "policy.json"
    config.write_text(json.dumps({"max_imported_files": 2}), encoding="utf-8")
    code, _, err = _run(capsys, str(library / "index.ttl"), "--pattern-library", str(library), "--config", str(config))
    assert code == TOOL_FAILURE
    assert "SEC015: --pattern-library" in err
    assert "holds more than 2 files" in err


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_a_member_outside_the_import_root_is_refused(
    library: Path, capsys: pytest.CaptureFixture[str], tmp_path_factory: pytest.TempPathFactory
) -> None:
    outside = tmp_path_factory.mktemp("outside") / "elsewhere.ttl"
    outside.write_text(_pattern(DOMAIN + "elsewhere", "Elsewhere"), encoding="utf-8")
    (library / "link.ttl").symlink_to(outside)
    code, _, err = _run(capsys, str(library / "index.ttl"), "--pattern-library", str(library))
    assert code == TOOL_FAILURE
    assert err.startswith("SEC009")


def test_the_loader_reads_names_references_and_identities(library: Path) -> None:
    loaded = load_library(library, Policy(), library.parent, exclude=[library / "index.ttl"])
    by_iri = {m.ontology: m for m in loaded.members}
    assert sorted(by_iri) == [DOMAIN + "agentrole", DOMAIN + "event", DOMAIN + "place"]
    agent = by_iri[DOMAIN + "agentrole"]
    assert agent.names == ("Agent Role",)
    assert agent.identities == frozenset({DOMAIN + "agentrole"})
    related = "http://ontologydesignpatterns.org/opla-core#hasRelatedPattern"
    assert agent.references == ((related, DOMAIN + "agent"), (related, DOMAIN + "event"))
    assert Path(agent.display).name == "agent-role.ttl"
    assert loaded.unreadable == ()


@pytest.mark.parametrize(
    ("a", "b"),
    [("AgentRole", "Agent Role"), ("DataTransformationPattern", "Data Transformation"), ("Event", "event pattern")],
)
def test_names_compare_without_case_punctuation_or_a_pattern_suffix(a: str, b: str) -> None:
    assert normalise_name(a) == normalise_name(b)


def test_a_name_that_is_only_pattern_stays_a_name() -> None:
    assert normalise_name("Pattern") == "pattern"
    assert normalise_name("--") == ""


@pytest.mark.parametrize(
    ("iris", "namespace"),
    [
        ((DOMAIN + "a", DOMAIN + "b"), DOMAIN),
        ((DOMAIN + "agent", DOMAIN + "agentrole"), DOMAIN),  # a common prefix inside a name is cut back
        (("https://example.test/a", "https://example.test/b"), None),  # only the host in common
        ((DOMAIN + "a",), None),
        (("urn:a:x", "urn:a:y"), None),
    ],
)
def test_the_library_namespace(iris: tuple[str, ...], namespace: str | None) -> None:
    members = [LibraryMember("f", "u", iri, frozenset({iri})) for iri in iris]
    assert library_namespace(members) == namespace
