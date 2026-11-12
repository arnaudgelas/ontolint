"""ONT007 and ONT008: one ontology or version IRI declared by several files, or by several graphs of one file.

The fixtures in tests/fixtures/duplicates/ hold one case per place the rules look: the inputs of one run
(``inputs/``), an import closure (``closure/``, and its mirror image ``shadow/``), one ``--import-dir``
(``importdir/``) and the named graphs of a dataset (``dataset/``).  Each test copies the fixtures into a
temporary working directory, so report paths are short and the same on every machine.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest
from jsonschema.validators import validator_for
from rdflib import Graph

from ontolint import cli, declarations, imports
from ontolint.cli import main
from ontolint.datasets import content_of, same_content
from ontolint.loader import ImportChoice, LoadedGraph, Module
from ontolint.paths import resolve_inputs
from ontolint.policy import Policy
from ontolint.source_locations import build_source_index

FIXTURES = Path(__file__).parent / "fixtures" / "duplicates"
SCHEMA = Path(__file__).parent / "schemas" / "sarif-schema-2.1.0.json"
PIZZA = "https://example.test/pizza"
PIZZA_1 = "https://example.test/pizza/1.0"
PASTA_1 = "https://example.test/pasta/1.0"
FOOD = "https://example.test/kitchen/food"
TOOLS = "https://example.test/kitchen/tools"
UNITS = "https://example.test/units"
MENU = "https://example.test/menu"
RULES = ("ONT007", "ONT008")
VERSION_LINE = 7  # where inputs/release.ttl and inputs/working.ttl give the pizza ontology its version IRI


@pytest.fixture
def work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A copy of the fixtures, which is also the working directory."""
    target = tmp_path / "duplicates"
    shutil.copytree(FIXTURES, target)
    monkeypatch.chdir(target)
    return target


def run(capsys: pytest.CaptureFixture[str], *argv: str, fmt: str = "json") -> tuple[int, Any, str]:
    code = main([*argv, "--format", fmt])
    captured = capsys.readouterr()
    return code, (json.loads(captured.out) if fmt != "text" else captured.out), captured.err


def found(report: dict[str, Any]) -> list[tuple[str, str, str, str, str]]:
    """``(rule, severity, focus, path, message)`` of every ONT007 and ONT008 finding, in report order."""
    return [
        (f["rule"], f["severity"], f["focus"], f["path"], f["message"])
        for f in report["findings"]
        if f["rule"] in RULES
    ]


# --- the inputs of one run -------------------------------------------------------------------------------------


def test_a_working_copy_under_the_release_version_iri_is_one_warning(
    work: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, report, _err = run(capsys, "inputs/working.ttl", "inputs/release.ttl")
    assert code == 0  # a warning does not fail the default --fail-on error
    # One fact, one finding: both claim to be release 1.0 of the pizza ontology, so the version IRI says it all.
    assert found(report) == [
        (
            "ONT007",
            "warning",
            PIZZA_1,
            "inputs/release.ttl",
            "Version IRI declared by 2 input files whose content differs: inputs/release.ttl, inputs/working.ttl.",
        ),
    ]


def test_an_identical_copy_is_a_note_whatever_its_syntax(work: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _code, report, _err = run(capsys, "inputs/release.ttl", "inputs/release-copy.ttl")
    assert found(report) == [
        (
            "ONT008",
            "info",
            PIZZA_1,
            "inputs/release-copy.ttl",
            "Version IRI declared by 2 input files with identical content: inputs/release-copy.ttl, "
            "inputs/release.ttl.",
        )
    ]


def test_a_version_iri_shared_by_two_ontologies_with_different_content(
    work: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _code, report, _err = run(capsys, "inputs/pasta.ttl", "inputs/sauce.ttl")
    assert found(report) == [
        (
            "ONT007",
            "warning",
            PASTA_1,
            "inputs/pasta.ttl",
            "Version IRI declared by 2 input files whose content differs: inputs/pasta.ttl, inputs/sauce.ttl.",
        )
    ]


def test_three_files_one_of_them_a_copy_are_one_finding(work: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _code, report, _err = run(capsys, "inputs/release.ttl", "inputs/release-copy.ttl", "inputs/working.ttl")
    members = "inputs/release-copy.ttl, inputs/release.ttl, inputs/working.ttl"
    assert [(rule, focus, message) for rule, _s, focus, _p, message in found(report)] == [
        ("ONT007", PIZZA_1, f"Version IRI declared by 3 input files whose content differs: {members}."),
    ]


def test_the_edit_file_and_its_release_are_two_versions_of_one_ontology(
    work: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An ODK repository lints ``x-edit.owl`` (no version IRI) next to the release ``x.owl`` (a dated one): two
    versions of one ontology series, which OWL 2 lets coexist, so nothing is reported."""
    _code, report, _err = run(capsys, "inputs/pizza-edit.ttl", "inputs/release.ttl")
    assert found(report) == []
    two = (work / "inputs/release.ttl").read_text(encoding="utf-8").replace("pizza/1.0", "pizza/2.0")
    (work / "inputs/release-2.ttl").write_text(two + "<https://example.test/pizza#Crust> a owl:Class .\n")
    _code, report, _err = run(capsys, "inputs/release.ttl", "inputs/release-2.ttl")
    assert found(report) == []


def test_two_unversioned_documents_of_one_ontology_are_a_warning(
    work: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    edit = (work / "inputs/pizza-edit.ttl").read_text(encoding="utf-8")
    (work / "inputs/pizza-edit-old.ttl").write_text(edit.replace('"topping"@en', '"garnish"@en'))
    _code, report, _err = run(capsys, "inputs/pizza-edit.ttl", "inputs/pizza-edit-old.ttl", "inputs/release.ttl")
    assert found(report) == [
        (
            "ONT007",
            "warning",
            PIZZA,
            "inputs/pizza-edit-old.ttl",
            "Ontology IRI declared by 2 input files whose content differs: inputs/pizza-edit-old.ttl, "
            "inputs/pizza-edit.ttl.",
        )
    ]


def test_distinct_ontologies_and_a_single_file_give_nothing(work: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _code, together, _err = run(capsys, "inputs/pasta.ttl", "inputs/release.ttl")
    assert found(together) == []
    _code, alone, _err = run(capsys, "inputs/release.ttl")
    assert found(alone) == []
    assert {x["rule"]: x["status"] for x in alone["files"][0]["executions"] if x["rule"] in RULES} == {
        "ONT007": "executed",
        "ONT008": "executed",
    }


def test_the_argument_order_changes_nothing(work: Path, capsys: pytest.CaptureFixture[str]) -> None:
    forward = run(capsys, "inputs/release.ttl", "inputs/working.ttl", "inputs/release-copy.ttl")
    backward = run(capsys, "inputs/release-copy.ttl", "inputs/working.ttl", "inputs/release.ttl")
    assert found(forward[1])
    assert forward == backward


def _sarif_files(result: dict[str, Any]) -> tuple[list[str], list[str]]:
    """The artifact URIs of a SARIF result's locations and of its related locations."""
    return [loc["physicalLocation"]["artifactLocation"]["uri"] for loc in result["locations"]], [
        loc["physicalLocation"]["artifactLocation"]["uri"] for loc in result.get("relatedLocations", [])
    ]


def test_sarif_gives_one_location_and_relates_the_other_files(work: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Removing one copy fixes the finding, so SARIF 2.1.0 (3.27.12) allows one location: the others are related."""
    _code, sarif, _err = run(capsys, "inputs/release.ttl", "inputs/working.ttl", fmt="sarif")
    (result,) = [r for r in sarif["runs"][0]["results"] if r["ruleId"] == "ONT007"]
    assert _sarif_files(result) == (["inputs/release.ttl"], ["inputs/working.ttl"])
    (location,) = result["locations"]
    (related,) = result["relatedLocations"]
    lines = [where["physicalLocation"]["region"]["startLine"] for where in (location, related)]
    assert lines == [VERSION_LINE, VERSION_LINE]  # the owl:versionIRI of each file
    assert (related["id"], related["message"]["text"]) == (1, "Also declared here.")
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator_for(schema)(schema).validate(sarif)


def test_sarif_relates_every_import_dir_candidate(work: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _code, sarif, _err = run(capsys, "importdir/root.ttl", "--import-dir", "importdir/mirror", fmt="sarif")
    (result,) = [r for r in sarif["runs"][0]["results"] if r["ruleId"] == "ONT007"]
    assert _sarif_files(result) == (["importdir/mirror/units-2024.ttl"], ["importdir/mirror/units-2025.ttl"])


def test_the_text_report_names_both_files(work: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _code, text, _err = run(capsys, "inputs/release.ttl", "inputs/working.ttl", fmt="text")
    assert (
        f"[WARNING] ONT007 {PIZZA_1}: Version IRI declared by 2 input files whose content differs: "
        "inputs/release.ttl, inputs/working.ttl." in text
    )


def test_selection_gating_and_baselines_apply(work: Path, capsys: pytest.CaptureFixture[str]) -> None:
    files = ("inputs/release.ttl", "inputs/working.ttl")
    code, _report, _err = run(capsys, *files, "--fail-on", "warning", "--select", "ONT007")
    assert code == 1
    _code, ignored, _err = run(capsys, *files, "--ignore", "ONT007")
    assert found(ignored) == []
    code, _report, _err = run(capsys, *files, "--write-baseline", "baseline.json", "--fail-on", "warning")
    assert code == 1
    code, baselined, _err = run(capsys, *files, "--baseline", "baseline.json", "--fail-on", "warning")
    assert (code, found(baselined)) == (0, [])


# --- an import closure -----------------------------------------------------------------------------------------


def test_two_modules_of_a_closure_with_one_ontology_iri(work: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _code, report, _err = run(capsys, "closure/root.ttl", "--follow-imports")
    assert found(report) == [
        (
            "ONT007",
            "warning",
            FOOD,
            "closure/food.ttl",
            "Ontology IRI declared by 2 files of the import closure whose content differs: closure/food.ttl, "
            "closure/tools.ttl.",
        )
    ]


def test_the_mirror_image_closure_names_the_module_it_did_not_load(
    work: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``food.ttl`` is imported first and claims the tools IRI, so the import of tools loads nothing: OWL tools
    do not read an ontology again under an IRI the closure has.  Which module vanishes depends on the order of
    the imports, so the file the catalog names is compared all the same."""
    _code, report, _err = run(capsys, "shadow/root.ttl", "--follow-imports")
    assert found(report) == [
        (
            "ONT007",
            "warning",
            TOOLS,
            "shadow/food.ttl",
            "Ontology IRI declared by 2 files of the import closure whose content differs: shadow/food.ttl, "
            f"shadow/tools.ttl; owl:imports <{TOOLS}> resolves to shadow/tools.ttl but did not load it, since a "
            "loaded file already declares that IRI.",
        )
    ]
    assert "Knife" not in json.dumps(report)  # the loading itself is unchanged


def test_a_module_loaded_under_another_iri_is_not_called_unloaded(
    work: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    catalog = (work / "shadow/catalog-v001.xml").read_text(encoding="utf-8")
    entry = '<uri name="https://example.test/kitchen/tools" uri="tools.ttl"/>'
    (work / "shadow/catalog-v001.xml").write_text(
        catalog.replace(entry, entry + '<uri name="https://example.test/kitchen/zknives" uri="tools.ttl"/>')
    )
    root = (work / "shadow/root.ttl").read_text(encoding="utf-8")
    (work / "shadow/root.ttl").write_text(
        root.replace("kitchen/food> .", "kitchen/food> , <https://example.test/kitchen/zknives> .")
    )
    _code, report, _err = run(capsys, "shadow/root.ttl", "--follow-imports")
    assert [message for *_rest, message in found(report)] == [
        "Ontology IRI declared by 2 files of the import closure whose content differs: shadow/food.ttl, "
        "shadow/tools.ttl."
    ]
    assert "Knife" in json.dumps(report)


def test_a_closure_reports_the_ontology_iri_and_names_a_file_once(
    work: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Both modules give the tools IRI one version IRI, and the root imports both IRIs: in a closure the shared
    ontology IRI says it, so the version IRI is not reported again, and the file not loaded is named once."""
    version = "https://example.test/kitchen/tools/1.0"
    for name in ("food.ttl", "tools.ttl"):
        text = (work / "shadow" / name).read_text(encoding="utf-8")
        (work / "shadow" / name).write_text(
            text.replace("tools> a owl:Ontology .", f"tools> a owl:Ontology ; owl:versionIRI <{version}> .")
        )
    catalog = (work / "shadow/catalog-v001.xml").read_text(encoding="utf-8")
    entry = '<uri name="https://example.test/kitchen/tools" uri="tools.ttl"/>'
    (work / "shadow/catalog-v001.xml").write_text(
        catalog.replace(entry, entry + f'<uri name="{version}" uri="tools.ttl"/>')
    )
    root = (work / "shadow/root.ttl").read_text(encoding="utf-8")
    (work / "shadow/root.ttl").write_text(root.replace("kitchen/food> .", f"kitchen/food> , <{version}> ."))
    _code, report, _err = run(capsys, "shadow/root.ttl", "--follow-imports")
    assert [(focus, message.count("did not load")) for _r, _s, focus, _p, message in found(report)] == [(TOOLS, 1)]


def test_a_file_outside_the_import_root_named_for_a_loaded_iri_is_left_alone(
    work: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The import is served by the loaded file, as before, so a catalog entry it never follows cannot fail the run."""
    (work / "outside").mkdir()
    shutil.move(work / "shadow/tools.ttl", work / "outside/tools.ttl")
    catalog = (work / "shadow/catalog-v001.xml").read_text(encoding="utf-8")
    (work / "shadow/catalog-v001.xml").write_text(catalog.replace('uri="tools.ttl"', 'uri="../outside/tools.ttl"'))
    code, report, err = run(capsys, "shadow/root.ttl", "--follow-imports", "--import-root", "shadow")
    assert (code, err, found(report)) == (0, "", [])


def test_a_closure_and_the_inputs_report_one_pair_once(work: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _code, report, _err = run(capsys, "closure/root.ttl", "closure/food.ttl", "closure/tools.ttl", "--follow-imports")
    assert [(rule, focus, path) for rule, _s, focus, path, _m in found(report)] == [
        ("ONT007", FOOD, "closure/food.ttl")
    ]
    assert "files of the import closure" in found(report)[0][4]


def test_without_following_imports_the_closure_is_not_checked(work: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _code, report, _err = run(capsys, "closure/root.ttl")
    assert found(report) == []


# --- one --import-dir ------------------------------------------------------------------------------------------


def test_an_import_dir_with_two_candidates_names_both_and_the_one_it_chose(
    work: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _code, report, _err = run(capsys, "importdir/root.ttl", "--import-dir", "importdir/mirror")
    assert found(report) == [
        (
            "ONT007",
            "warning",
            UNITS,
            "importdir/mirror/units-2024.ttl",
            "owl:imports <https://example.test/units> matches 2 files in --import-dir importdir/mirror whose "
            "content differs: importdir/mirror/units-2024.ttl, importdir/mirror/units-2025.ttl; it resolved to "
            "importdir/mirror/units-2024.ttl, the first in path order.",
        )
    ]


def test_an_import_dir_holding_an_identical_copy_is_a_note(work: Path, capsys: pytest.CaptureFixture[str]) -> None:
    shutil.copy(work / "importdir/mirror/units-2024.ttl", work / "importdir/mirror/units-copy.ttl")
    (work / "importdir/mirror/units-2025.ttl").unlink()
    _code, report, _err = run(capsys, "importdir/root.ttl", "--import-dir", "importdir/mirror")
    assert [(rule, severity) for rule, severity, *_ in found(report)] == [("ONT008", "info")]


def test_one_file_reached_through_two_import_dir_options_is_one_candidate(
    work: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A repeated option, a directory inside another, and a hard link in another directory: still one file."""
    (work / "importdir/mirror/units-2025.ttl").unlink()
    (work / "other").mkdir()
    os.link(work / "importdir/mirror/units-2024.ttl", work / "other/units-linked.ttl")
    for dirs in (("importdir/mirror", "importdir/mirror"), ("importdir", "importdir/mirror"), ("importdir", "other")):
        options = [arg for d in dirs for arg in ("--import-dir", d)]
        _code, report, _err = run(capsys, "importdir/root.ttl", *options, "--fail-on", "info")
        assert found(report) == [], dirs


def _second(work: Path) -> None:
    """Another ontology that imports the units, next to ``importdir/root.ttl``."""
    root = (work / "importdir/root.ttl").read_text(encoding="utf-8")
    (work / "importdir/second.ttl").write_text(root.replace("example.test/recipes", "example.test/menus"))


def test_two_inputs_importing_one_iri_from_an_import_dir_give_one_finding(
    work: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _second(work)
    _code, report, _err = run(capsys, "importdir/root.ttl", "importdir/second.ttl", "--import-dir", "importdir/mirror")
    assert [(rule, focus, path) for rule, _s, focus, path, _m in found(report)] == [
        ("ONT007", UNITS, "importdir/mirror/units-2024.ttl")
    ]


def test_copies_in_two_import_dirs_are_named_with_both_dirs(work: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (work / "other").mkdir()
    shutil.move(work / "importdir/mirror/units-2025.ttl", work / "other/units-2025.ttl")
    args = ("importdir/root.ttl", "--import-dir", "other", "--import-dir", "importdir/mirror")
    _code, report, _err = run(capsys, *args)
    assert [message for *_rest, message in found(report)] == [
        f"owl:imports <{UNITS}> matches 2 files in --import-dir other, importdir/mirror whose content differs: "
        "other/units-2025.ttl, importdir/mirror/units-2024.ttl; it resolved to other/units-2025.ttl, the first "
        "in argument and path order."
    ]


@pytest.mark.skipif(os.name == "nt", reason="symbolic links need a privilege on Windows")
def test_a_latest_symlink_in_an_import_dir_is_one_file(work: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (work / "importdir/mirror/units-2025.ttl").unlink()
    (work / "importdir/mirror/units-latest.ttl").symlink_to("units-2024.ttl")
    _code, report, _err = run(capsys, "importdir/root.ttl", "--import-dir", "importdir/mirror")
    assert found(report) == []


def test_an_import_dir_reads_each_file_once_and_unused_copies_never_again(
    work: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Indexing reads every file once; a candidate is read again only when an import resolves to its IRI, once."""
    for number in range(3):  # three IRIs held twice, which nothing imports
        for copy in ("a", "b"):
            (work / f"importdir/mirror/spare{number}-{copy}.ttl").write_text(
                f"<https://example.test/spare{number}> a <http://www.w3.org/2002/07/owl#Ontology> .\n"
                f"<https://example.test/spare{number}#{copy}> a <http://www.w3.org/2002/07/owl#Class> .\n"
            )
    _second(work)
    reads: list[str] = []
    real = imports.load_document

    def counting(item: Any, *args: Any) -> Any:
        reads.append(item.display)
        return real(item, *args)

    monkeypatch.setattr(imports, "load_document", counting)
    monkeypatch.setattr(declarations, "load_document", counting)
    _code, report, _err = run(capsys, "importdir/root.ttl", "importdir/second.ttl", "--import-dir", "importdir/mirror")
    assert len(found(report)) == 1
    mirror = sorted(name for name in reads if name.startswith("importdir/mirror/"))
    assert mirror == sorted(
        [str(p.relative_to(work).as_posix()) for p in (work / "importdir/mirror").iterdir()]
        + ["importdir/mirror/units-2024.ttl", "importdir/mirror/units-2024.ttl"]  # each closure loads its import
        + ["importdir/mirror/units-2025.ttl"]  # the other candidate, read once to compare it
    )


def test_only_documents_that_share_an_iri_are_compared(
    work: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    compared: list[int] = []
    real = declarations.content_of

    def counting(triples: Any) -> Any:
        compared.append(len(list(triples)))
        return real(triples)

    monkeypatch.setattr(declarations, "content_of", counting)
    run(capsys, "inputs/pasta.ttl", "inputs/release.ttl", "importdir/root.ttl", "--follow-imports")
    assert compared == []
    run(capsys, "inputs/release.ttl", "inputs/working.ttl", "inputs/pasta.ttl")
    assert len(compared) == 2  # noqa: PLR2004 -- release.ttl and working.ttl, once each


def test_nothing_is_compared_when_neither_rule_runs(
    work: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*_args: object) -> None:
        raise AssertionError("shared_identities ran although ONT007 and ONT008 do not")

    monkeypatch.setattr(cli, "shared_identities", refuse)
    code, _report, _err = run(capsys, "importdir/root.ttl", "--import-dir", "importdir/mirror", "--select", "LEX")
    assert code == 0
    code, _report, _err = run(capsys, "inputs/release.ttl", "inputs/working.ttl", "--ignore", "ONT007,ONT008")
    assert code == 0


def test_an_unused_duplicate_in_an_import_dir_is_not_reported(work: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _code, report, _err = run(capsys, "inputs/pasta.ttl", "--import-dir", "importdir/mirror")
    assert found(report) == []


# --- baselines -------------------------------------------------------------------------------------------------


def test_the_baseline_identity_holds_no_path(work: Path, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    """A committed baseline keeps accepting the finding from another checkout, another working directory, and
    with another copy in the mirror: the identity is the rule, the IRI, the place and the kind."""
    project = work / "importdir"
    os.chdir(project)
    code, _report, _err = run(capsys, "root.ttl", "--import-dir", "../importdir/mirror", "--write-baseline", "b.json")
    assert code == 0
    gate = ("--fail-on", "warning")
    moved = tmp_path / "elsewhere" / "checkout"
    shutil.copytree(work, moved)
    os.chdir(moved / "importdir")
    assert run(capsys, "root.ttl", "--import-dir", "../importdir/mirror", "--baseline", "b.json", *gate)[0] == 0
    os.chdir(moved)
    args = ("importdir/root.ttl", "--import-dir", "importdir/mirror", "--baseline", "importdir/b.json", *gate)
    assert run(capsys, *args)[0] == 0
    shutil.copy(moved / "importdir/mirror/units-2025.ttl", moved / "importdir/mirror/units-2026.ttl")
    code, report, _err = run(capsys, *args)
    assert (code, found(report)) == (0, [])


def test_a_baseline_follows_the_finding_to_a_copy_that_sorts_first(
    work: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The finding is reported on its first file; adding a copy before it, or renaming that file, moves it
    to another report path, and the baseline still accepts it (once in the run, under one recorded path)."""
    os.chdir(work / "inputs")
    gate = ("--select", "ONT007,ONT008", "--fail-on", "warning")
    assert run(capsys, "release.ttl", "working.ttl", "--write-baseline", "b.json", *gate)[0] == 1
    shutil.copy("release.ttl", "a-copy.ttl")
    code, report, _err = run(capsys, "a-copy.ttl", "release.ttl", "working.ttl", "--baseline", "b.json", *gate)
    assert (code, found(report)) == (0, [])
    shutil.move("release.ttl", "z-release.ttl")
    code, report, _err = run(capsys, "a-copy.ttl", "z-release.ttl", "working.ttl", "--baseline", "b.json", *gate)
    assert (code, found(report)) == (0, [])


def test_a_baseline_entry_reported_twice_in_a_run_follows_only_its_own_path(
    work: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two datasets whose graphs both repeat one header: one identity, reported on each file.  The entry
    recorded for one file keeps accepting it there and never accepts the other's; recorded for both, it
    accepts neither on a third file."""
    header = f"<{MENU}> a <http://www.w3.org/2002/07/owl#Ontology>"
    label = "<http://www.w3.org/2000/01/rdf-schema#label>"
    for name in ("one", "two", "three"):
        (work / f"{name}.trig").write_text(
            f'<https://g.test/{name}/a> {{ {header} ; {label} "a" . }}\n'
            f'<https://g.test/{name}/b> {{ {header} ; {label} "b" . }}\n'
        )
    gate = ("--select", "ONT007,ONT008")
    run(capsys, "one.trig", "--write-baseline", "b.json", *gate)
    _code, report, _err = run(capsys, "one.trig", "two.trig", "--baseline", "b.json", *gate)
    assert [path for _r, _s, _f, path, message in found(report) if " graphs of " in message] == ["two.trig"]
    run(capsys, "one.trig", "two.trig", "--write-baseline", "both.json", *gate)
    _code, report, _err = run(capsys, "three.trig", "--baseline", "both.json", *gate)
    assert [path for _r, _s, _f, path, _m in found(report)] == ["three.trig"]


# --- the named graphs of a dataset -----------------------------------------------------------------------------


def test_two_graphs_of_a_dataset_with_one_ontology_iri(work: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _code, report, _err = run(capsys, "dataset/two-headers.trig")
    assert found(report) == [
        (
            "ONT007",
            "warning",
            MENU,
            "dataset/two-headers.trig",
            "Ontology IRI declared by 2 graphs of dataset/two-headers.trig whose content differs: "
            "https://example.test/menu/draft, https://example.test/menu/published.",
        )
    ]
    [finding] = [f for f in report["findings"] if f["rule"] == "ONT007"]
    assert finding["graphs"] == ["https://example.test/menu/draft", "https://example.test/menu/published"]


def test_one_header_in_the_default_graph_is_not_a_duplicate(work: Path, capsys: pytest.CaptureFixture[str]) -> None:
    shutil.copy(Path(__file__).parent / "fixtures" / "datasets" / "one_term_two_graphs.trig", work)
    _code, report, _err = run(capsys, "one_term_two_graphs.trig")
    assert found(report) == []


def test_two_graphs_with_the_same_header_and_nothing_else_are_a_note(
    work: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    header = "<https://example.test/menu> a <http://www.w3.org/2002/07/owl#Ontology> ."
    (work / "copies.trig").write_text(f"<https://g.test/a> {{ {header} }}\n<https://g.test/b> {{ {header} }}\n")
    _code, report, _err = run(capsys, "copies.trig")
    assert [(rule, message) for rule, _s, _f, _p, message in found(report)] == [
        (
            "ONT008",
            "Ontology IRI declared by 2 graphs of copies.trig with identical content: https://g.test/a, https://g.test/b.",
        )
    ]


def test_identical_blank_node_graphs_are_one_graph(work: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A blank graph is named by its content (:mod:`ontolint.datasets`), so two with the same triples are one
    graph of the index, and no document of their own: the limit is deliberate, and this test marks it."""
    header = "<https://example.test/menu> a <http://www.w3.org/2002/07/owl#Ontology> ."
    (work / "blank.trig").write_text(f"_:a {{ {header} }}\n_:b {{ {header} }}\n")
    _code, report, _err = run(capsys, "blank.trig")
    assert found(report) == []


def test_a_dataset_of_a_closure_names_its_own_graphs(work: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The root declares the IRI too, so it owns the focus; the finding on the dataset's graphs still moves to
    the dataset and names the graphs there."""
    owl = "<http://www.w3.org/2002/07/owl#Ontology>"
    (work / "lib").mkdir()
    (work / "root.ttl").write_text(
        f"<{MENU}> a {owl} ; <http://www.w3.org/2002/07/owl#imports> <https://example.test/data> .\n"
    )
    (work / "lib/data.trig").write_text(
        f"{{ <https://example.test/data> a {owl} . }}\n"
        f'<https://g.test/a> {{ <{MENU}> a {owl} ; <http://www.w3.org/2000/01/rdf-schema#label> "a" . }}\n'
        f'<https://g.test/b> {{ <{MENU}> a {owl} ; <http://www.w3.org/2000/01/rdf-schema#label> "b" . }}\n'
    )
    _code, report, _err = run(capsys, "root.ttl", "--import-dir", "lib")
    placed = [(f["path"], f.get("graphs")) for f in report["findings"] if f["rule"] in RULES]
    assert placed == [("root.ttl", None), ("lib/data.trig", ["https://g.test/a", "https://g.test/b"])]


# --- what "the same content" means -----------------------------------------------------------------------------

TURTLE = """@prefix owl: <http://www.w3.org/2002/07/owl#> .
<https://example.test/o> a owl:Ontology ; owl:imports <module.ttl> .
<https://example.test/C> owl:equivalentClass [ owl:unionOf ( <https://example.test/A> <https://example.test/B> ) ] .
"""


def _same(*graphs: Graph) -> bool:
    return same_content([content_of(graph) for graph in graphs], lambda: graphs)


def test_the_same_content_is_the_same_rdf_graph(tmp_path: Path) -> None:
    first = Graph().parse(data=TURTLE, format="turtle", publicID=(tmp_path / "x" / "o.ttl").as_uri())
    relabelled = Graph().parse(data=first.serialize(format="nt"), format="nt")  # new blank-node labels
    assert _same(first, relabelled)
    moved = Graph().parse(data=TURTLE, format="turtle", publicID=(tmp_path / "y" / "o.ttl").as_uri())
    assert not _same(first, moved)  # the relative import names another file: another graph
    spelled = Graph().parse(
        data=TURTLE.replace("<module.ttl>", "<../x/module.ttl>"),
        format="turtle",
        publicID=(tmp_path / "y" / "o.ttl").as_uri(),
    )
    assert _same(first, spelled)  # the same triples, written relative to another folder
    changed = Graph().parse(data=TURTLE.replace("<https://example.test/B>", "<https://example.test/D>"), format="ttl")
    assert not _same(changed, Graph().parse(data=TURTLE, format="turtle"))


def _branches(*branches: tuple[str, str], depth: int = 16) -> Graph:
    """Blank-node branches under one class, each a label and a chain deeper than a stable identity looks."""
    texts = []
    for label, leaf in branches:
        text = f'"{leaf}"'
        for _level in range(depth):
            text = f"[ <https://example.test/p> {text} ]"
        texts.append(f'[ <https://example.test/t> "{label}" ; <https://example.test/p> {text} ]')
    return Graph().parse(data=f"<https://example.test/C> <https://example.test/q> {' , '.join(texts)} .", format="ttl")


def test_blank_nodes_alike_to_the_depth_of_their_identity_are_compared_as_graphs() -> None:
    one = _branches(("x", "a"), ("y", "b"))
    swapped = _branches(("x", "b"), ("y", "a"))  # the leaves change branch: another graph
    assert not content_of(one).exact  # the middle of the two chains shares stable identities
    assert content_of(swapped).digest == content_of(one).digest  # so the digest alone cannot tell them apart
    assert not _same(one, swapped)
    assert _same(one, _branches(("y", "b"), ("x", "a")))  # isomorphic: the branches only listed in another order


def test_a_candidate_gone_since_it_was_indexed_is_compared_as_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The import dir is indexed before parsing; a candidate removed meanwhile cannot be the same content."""
    monkeypatch.chdir(tmp_path)
    mirror = tmp_path / "mirror"
    mirror.mkdir()
    chosen = mirror / "a.ttl"
    chosen.write_text("<https://example.test/u> a <http://www.w3.org/2002/07/owl#Ontology> .\n")
    (item,) = resolve_inputs([str(chosen)], tmp_path)
    graph = Graph().parse(chosen)
    index = build_source_index(b"", "nt", item.uri, graph)
    loaded = LoadedGraph(
        graph,
        index,
        modules=(Module(item.display, item.uri, frozenset(), index, "", graph),),
        choices=(ImportChoice("https://example.test/u", ("mirror",), ((chosen, mirror), (mirror / "b.ttl", mirror))),),
    )
    ((shared,),) = declarations.shared_identities([item], [loaded], Policy())
    assert (shared.identity.identical, shared.identity.members) == (False, ("mirror/a.ttl", "mirror/b.ttl"))
    assert shared.places[1].source_index is None
