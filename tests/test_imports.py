"""Following owl:imports offline through an OASIS XML catalog (--follow-imports, --catalog).

The synthetic corpus in tests/fixtures/modular/ recreates a common modular layout: an umbrella with no
terms of its own, modules sharing one namespace, a diamond (the umbrella and core both import meta), a
cycle (meta imports the umbrella), a data module in a subdirectory mapped through a catalog group, a draft
module nobody imports, and one external import no catalog maps.
"""

from __future__ import annotations

import gzip
import json
import re
import shutil
import socket
from pathlib import Path

import pytest

from ontolint.cli import main
from ontolint.imports import CatalogError, index_directory, load_closure, read_catalog
from ontolint.loader import InputRejected, LoadedGraph, load_document
from ontolint.paths import resolve_inputs
from ontolint.policy import Policy

CORPUS = Path(__file__).parent / "fixtures" / "modular"
EXTERNAL = "https://external.example/vocabulary"
CORE = "https://example.test/onto/core#"
TOOL_FAILURE = 2


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    target = tmp_path / "modular"
    shutil.copytree(CORPUS, target)
    return target


def _report(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, dict[str, object], str]:
    code = main([*argv, "--format", "json", "--fail-on", "never"])
    captured = capsys.readouterr()
    return code, (json.loads(captured.out) if captured.out else {}), captured.err


def _findings(report: dict[str, object], rule: str) -> list[dict[str, str]]:
    return [f for f in report["findings"] if f["rule"] == rule]  # type: ignore[union-attr, index]


def _closure(umbrella: Path, policy: Policy | None = None, *, catalog: bool = True):  # noqa: ANN202
    policy = policy or Policy()
    item = resolve_inputs([str(umbrella)], umbrella.parent)[0]
    root = load_document(item, policy, umbrella.parent)
    found = read_catalog(umbrella.parent / "catalog-v001.xml", policy.max_input_bytes) if catalog else None
    return load_closure(LoadedGraph(root.graph, root.source_index), umbrella, policy, found)


# --- default behaviour is unchanged -------------------------------------------------------------


def test_without_the_flag_the_umbrella_is_linted_alone(corpus: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _code, report, _err = _report(capsys, str(corpus / "umbrella.ttl"))
    (note,) = _findings(report, "SEC007")
    assert "4 owl:imports were not followed" in note["message"]
    assert not _findings(report, "LEX002")  # the module terms are invisible


# --- following the closure ----------------------------------------------------------------------


@pytest.mark.parametrize("flag", ["--follow-imports", "--catalog"])
def test_the_closure_is_linted_and_only_the_unresolved_import_is_noted(
    corpus: Path, capsys: pytest.CaptureFixture[str], flag: str
) -> None:
    argv = [str(corpus / "umbrella.ttl"), flag]
    if flag == "--catalog":
        argv.append(str(corpus / "catalog-v001.xml"))
    code, report, err = _report(capsys, *argv)
    assert code == 0, err
    (note,) = _findings(report, "SEC007")
    assert note["message"] == f"1 owl:import was not followed: {EXTERNAL}."
    assert [f["focus"] for f in _findings(report, "LEX002")] == [f"{CORE}UndefinedThing"]
    assert not _findings(report, "ONT002")  # one header per module is expected, not a second ontology
    assert all("DraftOnly" not in f["focus"] for f in report["findings"])  # type: ignore[union-attr, index]


def test_a_diamond_loads_each_module_once_and_a_cycle_terminates(corpus: Path) -> None:
    closure = _closure(corpus / "umbrella.ttl")
    # Breadth first, in sorted IRI order; meta is reached three times (umbrella, core, data) and loaded once.
    assert [Path(name).name for name in closure.files] == ["core.ttl", "data.ttl", "meta.ttl"]
    assert closure.unresolved == {EXTERNAL}
    assert closure.resolved == {f"https://example.test/onto{suffix}" for suffix in ("", "/meta", "/core", "/data")}
    assert closure.imported_ontologies == {f"https://example.test/onto/{name}" for name in ("meta", "core", "data")}


def test_without_a_catalog_only_file_iris_resolve(corpus: Path) -> None:
    umbrella = corpus / "umbrella.ttl"
    text = umbrella.read_text(encoding="utf-8")
    umbrella.write_text(text.replace("<https://example.test/onto/meta>", f"<{(corpus / 'meta.ttl').as_uri()}>"))
    closure = _closure(umbrella, catalog=False)
    assert [Path(name).name for name in closure.files] == ["meta.ttl"]
    assert EXTERNAL in closure.unresolved


def test_a_rewrite_prefix_resolves_a_whole_namespace(corpus: Path) -> None:
    (corpus / "catalog-v001.xml").write_text(
        '<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">'
        '<rewriteURI uriStartString="https://example.test/onto/" rewritePrefix="./"/>'
        '<uri name="https://example.test/onto/core" uri="core.ttl"/>'
        '<uri name="https://example.test/onto/data" uri="generated/data.ttl"/></catalog>',
        encoding="utf-8",
    )
    (corpus / "meta").write_bytes((corpus / "meta.ttl").read_bytes())
    closure = _closure(corpus / "umbrella.ttl")
    assert {Path(name).name for name in closure.files} == {"meta", "core.ttl", "data.ttl"}


def test_the_network_is_never_used(corpus: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    assert EXTERNAL in _closure(corpus / "umbrella.ttl").unresolved


# --- sandbox --------------------------------------------------------------------------------------


def _catalog_pointing_at(corpus: Path, target: str) -> None:
    catalog = (corpus / "catalog-v001.xml").read_text(encoding="utf-8")
    (corpus / "catalog-v001.xml").write_text(catalog.replace('uri="meta.ttl"', f'uri="{target}"'), encoding="utf-8")


def test_a_catalog_entry_outside_the_import_root_is_refused(corpus: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (corpus.parent / "outside.ttl").write_bytes((corpus / "meta.ttl").read_bytes())
    _catalog_pointing_at(corpus, "../outside.ttl")
    code, _report_, err = _report(capsys, str(corpus / "umbrella.ttl"), "--follow-imports")
    assert code == TOOL_FAILURE
    assert err.startswith("SEC009: owl:imports https://example.test/onto/meta resolves to")
    assert "outside the import root" in err


def test_a_symlink_leaving_the_import_root_is_refused(corpus: Path) -> None:
    outside = corpus.parent / "outside.ttl"
    outside.write_bytes((corpus / "meta.ttl").read_bytes())
    (corpus / "link.ttl").symlink_to(outside)
    _catalog_pointing_at(corpus, "link.ttl")
    with pytest.raises(InputRejected, match="outside the import root") as error:
        _closure(corpus / "umbrella.ttl")
    assert error.value.rule_id == "SEC009"


def test_a_file_iri_outside_the_import_root_is_refused(corpus: Path) -> None:
    outside = corpus.parent / "outside.ttl"
    outside.write_bytes((corpus / "meta.ttl").read_bytes())
    umbrella = corpus / "umbrella.ttl"
    umbrella.write_text(
        umbrella.read_text(encoding="utf-8").replace(f"<{EXTERNAL}>", f"<{outside.as_uri()}>"), encoding="utf-8"
    )
    with pytest.raises(InputRejected, match="outside the import root"):
        _closure(umbrella)


# --- limits ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("policy", "message"),
    [
        (Policy(max_imported_files=1), "more than 1 files (max_imported_files)"),
        (Policy(max_import_depth=1), "deeper than 1 (max_import_depth)"),
        (Policy(max_triples=12), "more than 12 triples (max_triples)"),
    ],
    ids=["files", "depth", "triples"],
)
def test_the_closure_is_bounded(corpus: Path, policy: Policy, message: str) -> None:
    umbrella = corpus / "umbrella.ttl"
    # A chain for the depth case: the umbrella imports only core, which imports meta (depth 2).
    text = umbrella.read_text(encoding="utf-8")
    start, end = text.index("owl:imports"), text.index(" .", text.index("vocabulary"))
    umbrella.write_text(text[:start] + "owl:imports <https://example.test/onto/core>" + text[end:], encoding="utf-8")
    with pytest.raises(InputRejected, match=re.escape(message)) as error:
        _closure(umbrella, policy)
    assert error.value.rule_id == "SEC015"


def test_closure_limits_are_policy_keys(corpus: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = corpus / "policy.json"
    config.write_text(json.dumps({"policy_version": 1, "max_imported_files": 1}), encoding="utf-8")
    code, _report_, err = _report(capsys, str(corpus / "umbrella.ttl"), "--follow-imports", "--config", str(config))
    assert code == TOOL_FAILURE
    assert err.startswith("SEC015: the import closure has more than 1 files")
    with pytest.raises(ValueError, match="max_import_depth"):
        Policy.from_mapping({"max_import_depth": 0})


# --- broken catalogs and modules -----------------------------------------------------------------


def test_a_catalog_with_a_dtd_is_refused(corpus: Path, capsys: pytest.CaptureFixture[str]) -> None:
    catalog = corpus / "catalog-v001.xml"
    catalog.write_text(
        '<?xml version="1.0"?>\n<!DOCTYPE catalog SYSTEM "file:///etc/passwd">\n'
        '<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog"/>\n',
        encoding="utf-8",
    )
    code, _report_, err = _report(capsys, str(corpus / "umbrella.ttl"), "--catalog", str(catalog))
    assert code == TOOL_FAILURE
    assert err.startswith("SEC010: catalog ")


@pytest.mark.parametrize("text", ["<catalog", "<notacatalog/>"], ids=["malformed", "wrong-root"])
def test_a_catalog_that_is_not_a_catalog_is_a_configuration_error(
    corpus: Path, capsys: pytest.CaptureFixture[str], text: str
) -> None:
    catalog = corpus / "catalog-v001.xml"
    catalog.write_text(text, encoding="utf-8")
    code, _report_, err = _report(capsys, str(corpus / "umbrella.ttl"), "--catalog", str(catalog))
    assert code == TOOL_FAILURE
    assert err.startswith("TOOL001: configuration failed: CatalogError: ")
    with pytest.raises(CatalogError):
        read_catalog(catalog, 1000)


def test_a_catalog_entry_naming_a_missing_file_leaves_the_import_unresolved(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (corpus / "meta.ttl").unlink()  # SDC: the catalog still names files the repository no longer has
    code, report, err = _report(capsys, str(corpus / "umbrella.ttl"), "--follow-imports")
    assert code == 0
    assert "TOOL004: note: the catalog maps owl:imports https://example.test/onto/meta to " in err
    (note,) = _findings(report, "SEC007")
    assert "https://example.test/onto/meta" in note["message"]


def test_an_imported_module_still_passes_the_safe_loader(corpus: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (corpus / "core.ttl").write_text("this is not turtle", encoding="utf-8")
    code, _report_, err = _report(capsys, str(corpus / "umbrella.ttl"), "--follow-imports")
    assert code == TOOL_FAILURE
    assert err.startswith("INPUT001: RDF input parsing failed")


def test_a_file_iri_naming_another_host_does_not_resolve(corpus: Path) -> None:
    umbrella = corpus / "umbrella.ttl"
    remote = "file://remote.example" + (corpus / "meta.ttl").as_uri().removeprefix("file://")
    umbrella.write_text(umbrella.read_text(encoding="utf-8").replace(f"<{EXTERNAL}>", f"<{remote}>"), encoding="utf-8")
    assert remote in _closure(umbrella, catalog=False).unresolved


@pytest.mark.parametrize(
    "entry",
    [
        '<uri uri="meta.ttl"/>',  # no name
        '<uri name="https://example.test/onto/meta"/>',  # no target
        '<rewriteURI uriStartString="https://example.test/onto/"/>',  # no prefix
        '<rewriteURI rewritePrefix="./"/>',  # no start string
        '<system systemId="https://example.test/onto/meta" uri="meta.ttl"/>',  # not a URI entry
    ],
)
def test_incomplete_or_foreign_catalog_entries_are_ignored(corpus: Path, entry: str) -> None:
    (corpus / "catalog-v001.xml").write_text(
        f'<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">{entry}</catalog>', encoding="utf-8"
    )
    assert "https://example.test/onto/meta" in _closure(corpus / "umbrella.ttl").unresolved


def test_the_import_depth_limit_is_inclusive(corpus: Path) -> None:
    umbrella = corpus / "umbrella.ttl"
    text = umbrella.read_text(encoding="utf-8")
    start, end = text.index("owl:imports"), text.index(" .", text.index("vocabulary"))
    umbrella.write_text(text[:start] + "owl:imports <https://example.test/onto/core>" + text[end:], encoding="utf-8")
    closure = _closure(umbrella, Policy(max_import_depth=2))  # core is at depth 1, meta at depth 2
    assert [Path(name).name for name in closure.files] == ["core.ttl", "meta.ttl"]


# --- import root and per-module catalogs ---------------------------------------------------------


def _sibling_layout(root: Path) -> Path:
    """CCO's layout: the umbrella and its catalog in merged/, the modules in a sibling modules/."""
    (root / "merged").mkdir(parents=True)
    (root / "modules").mkdir()
    for name in ("meta.ttl", "core.ttl"):
        (root / "modules" / name).write_bytes((CORPUS / name).read_bytes())
    umbrella = root / "merged" / "umbrella.ttl"
    umbrella.write_text(
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
        "<https://example.test/onto> a owl:Ontology ; owl:imports <https://example.test/onto/core> .\n",
        encoding="utf-8",
    )
    (root / "merged" / "catalog-v001.xml").write_text(
        '<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">'
        '<uri name="https://example.test/onto/core" uri="../modules/core.ttl"/>'
        '<uri name="https://example.test/onto/meta" uri="../modules/meta.ttl"/></catalog>',
        encoding="utf-8",
    )
    return umbrella


def test_a_catalog_may_point_at_sibling_directories_of_the_repository(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    closure = _closure(_sibling_layout(tmp_path))
    assert [Path(name).name for name in closure.files] == ["core.ttl", "meta.ttl"]


def test_without_a_repository_siblings_need_an_explicit_import_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    umbrella = _sibling_layout(tmp_path)
    code, _report_, err = _report(capsys, str(umbrella), "--follow-imports")
    assert code == TOOL_FAILURE
    assert "SEC009" in err
    code, report, err = _report(capsys, str(umbrella), "--import-root", str(tmp_path))
    assert code == 0, err
    assert not _findings(report, "SEC007")


def test_the_repository_still_bounds_the_closure(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    (repository / ".git").mkdir(parents=True)
    umbrella = _sibling_layout(repository)
    (tmp_path / "outside.ttl").write_bytes((CORPUS / "meta.ttl").read_bytes())
    catalog = umbrella.parent / "catalog-v001.xml"
    catalog.write_text(catalog.read_text(encoding="utf-8").replace("../modules/meta.ttl", "../../outside.ttl"))
    with pytest.raises(InputRejected, match="outside the import root") as error:
        _closure(umbrella)
    assert error.value.rule_id == "SEC009"


def test_the_catalog_next_to_a_module_resolves_that_module_imports(tmp_path: Path) -> None:
    # EMMO keeps a catalog in each directory: core's own catalog is the only one that maps meta.
    (tmp_path / ".git").mkdir()
    umbrella = _sibling_layout(tmp_path)
    (tmp_path / "merged" / "catalog-v001.xml").write_text(
        '<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">'
        '<uri name="https://example.test/onto/core" uri="../modules/core.ttl"/></catalog>',
        encoding="utf-8",
    )
    (tmp_path / "modules" / "catalog-v001.xml").write_text(
        '<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">'
        '<uri name="https://example.test/onto/meta" uri="meta.ttl"/></catalog>',
        encoding="utf-8",
    )
    closure = _closure(umbrella)
    assert [Path(name).name for name in closure.files] == ["core.ttl", "meta.ttl"]
    assert "https://example.test/onto/meta" in closure.resolved


def test_an_import_naming_a_loaded_module_by_its_version_iri_needs_no_catalog_entry(corpus: Path) -> None:
    core = corpus / "core.ttl"
    core.write_text(
        core.read_text(encoding="utf-8").replace(
            "<https://example.test/onto/core> a owl:Ontology ;",
            "<https://example.test/onto/core> a owl:Ontology ; owl:versionIRI <https://example.test/onto/core/1.0> ;",
        ),
        encoding="utf-8",
    )
    data = corpus / "generated" / "data.ttl"
    data.write_text(
        data.read_text(encoding="utf-8").replace(
            "<https://example.test/onto/core>", "<https://example.test/onto/core/1.0>"
        ),
        encoding="utf-8",
    )
    closure = _closure(corpus / "umbrella.ttl")
    assert "https://example.test/onto/core/1.0" in closure.resolved
    assert closure.unresolved == {EXTERNAL}


# --- --import-dir ---------------------------------------------------------------------------------------


def _bfo_like(folder: Path) -> None:
    """A folder of downloaded imports, as robot mirror leaves it: files named unlike their IRIs."""
    folder.mkdir(parents=True)
    (folder / "upper.owl").write_text(  # Turtle under .owl, as published files often are
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
        "<https://upper.test/classes-only.owl> a owl:Ontology ;\n"
        "    owl:versionIRI <https://upper.test/2020/classes-only.owl> .\n"
        "<https://upper.test/U1> a owl:Class .\n",
        encoding="utf-8",
    )
    (folder / "notes.txt").write_text("not RDF", encoding="utf-8")
    (folder / "broken.ttl").write_text("this is not turtle", encoding="utf-8")


@pytest.mark.parametrize("iri", ["https://upper.test/classes-only.owl", "https://upper.test/2020/classes-only.owl"])
def test_an_import_dir_resolves_by_ontology_or_version_iri(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], iri: str
) -> None:
    _bfo_like(tmp_path / "mirror")
    ontology = tmp_path / "project" / "mfto.ttl"
    ontology.parent.mkdir()
    ontology.write_text(
        f"@prefix owl: <http://www.w3.org/2002/07/owl#> .\n<https://p.test/o> a owl:Ontology ; owl:imports <{iri}> .\n",
        encoding="utf-8",
    )
    code, report, err = _report(capsys, str(ontology), "--import-dir", str(tmp_path / "mirror"))
    assert code == 0, err
    assert not _findings(report, "SEC007")


def test_an_import_dir_is_bounded(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _bfo_like(tmp_path / "mirror")
    config = tmp_path / "policy.json"
    config.write_text(json.dumps({"policy_version": 1, "max_imported_files": 1}), encoding="utf-8")
    ontology = tmp_path / "o.ttl"
    ontology.write_text("<https://p.test/a> <https://p.test/b> <https://p.test/c> .\n", encoding="utf-8")
    code, _report_, err = _report(
        capsys, str(ontology), "--import-dir", str(tmp_path / "mirror"), "--config", str(config)
    )
    assert code == TOOL_FAILURE
    assert err.startswith("SEC015: --import-dir ")


def test_a_large_import_never_outweighs_the_root_file_own_terms(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # MFTO plus RO: the import declares more terms than the root, which must still be the one judged.
    mirror = tmp_path / "mirror"
    mirror.mkdir()
    (mirror / "relations.ttl").write_text(
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n<https://rel.test/core.owl> a owl:Ontology .\n"
        + "".join(f"<https://rel.test/R_{i}> a owl:ObjectProperty .\n" for i in range(30)),
        encoding="utf-8",
    )
    root = tmp_path / "root.ttl"
    root.write_text(
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
        "<https://p.test/untitled-ontology-1> a owl:Ontology ; owl:imports <https://rel.test/core.owl> .\n"
        + "".join(f"<https://p.test/mfto#C{i}> a owl:Class .\n" for i in range(3)),
        encoding="utf-8",
    )
    _code, report, err = _report(capsys, str(root), "--import-dir", str(mirror))
    lex001 = {f["focus"] for f in _findings(report, "LEX001")}
    assert lex001 == {f"https://p.test/mfto#C{i}" for i in range(3)}, err


# --- --import-dir: a file the safe loader refuses is named (TOOL010) -----------------------------------------

ONTOLOGY = "<{iri}> a <http://www.w3.org/2002/07/owl#Ontology> .\n"
SKIPPED = "is skipped, so no owl:imports resolves to it"
OASIS_CATALOG = (
    '<?xml version="1.0"?>\n<!DOCTYPE catalog PUBLIC "-//OASIS//DTD XML Catalogs V1.1//EN"'
    ' "http://www.oasis-open.org/committees/entity/release/1.1/catalog.dtd">\n'
    '<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog"/>\n'
)


def _refusing_mirror(folder: Path) -> int:
    """``m.ttl`` declares ``https://e.test/m``; ``big.ttl`` declares ``https://e.test/big``; return big's size."""
    folder.mkdir(parents=True)
    (folder / "m.ttl").write_text(ONTOLOGY.format(iri="https://e.test/m"), encoding="utf-8")
    big = ONTOLOGY.format(iri="https://e.test/big") + "# padding\n" * 40
    (folder / "big.ttl").write_text(big, encoding="utf-8")
    return len(big.encode())


def test_a_refused_import_dir_file_is_named_once_above_the_import_it_leaves_unresolved(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    size = _refusing_mirror(tmp_path / "mirror")
    config = tmp_path / "policy.json"
    config.write_text(json.dumps({"policy_version": 1, "max_input_bytes": 300}), encoding="utf-8")
    (tmp_path / "u.ttl").write_text(
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
        "<https://e.test/u> a owl:Ontology ; owl:imports <https://e.test/m>, <https://e.test/big> .\n",
        encoding="utf-8",
    )
    argv = ("u.ttl", "--import-dir", "mirror", "--config", "policy.json")
    code, report, err = _report(capsys, *argv)
    assert err == (
        f"TOOL010: warning: --import-dir mirror: mirror/big.ttl {SKIPPED}: "
        f"SEC001: mirror/big.ttl is {size} bytes, more than the limit of 300 (max_input_bytes)\n"
    )
    sec007 = " ".join(f["message"] for f in _findings(report, "SEC007"))
    assert "https://e.test/big" in sec007 and "https://e.test/m" not in sec007  # the line above explains it
    (tmp_path / "mirror" / "big.ttl").write_text("# not an ontology any more\n", encoding="utf-8")
    assert _report(capsys, *argv)[:2] == (code, report)  # the warning changes neither the exit code nor the report


def test_each_kind_of_refusal_is_recorded_in_path_order_and_the_folder_still_indexes(tmp_path: Path) -> None:
    mirror = tmp_path / "mirror"
    mirror.mkdir()
    (mirror / "zipped.ttl").write_bytes(gzip.compress(ONTOLOGY.format(iri="https://e.test/z").encode()))
    (mirror / "dtd.rdf").write_text(
        '<?xml version="1.0"?>\n<!DOCTYPE rdf:RDF [<!ENTITY e SYSTEM "file:///etc/passwd">]>\n'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"/>\n',
        encoding="utf-8",
    )
    (mirror / "good.ttl").write_text(ONTOLOGY.format(iri="https://e.test/good"), encoding="utf-8")
    (mirror / "many.nt").write_text(
        "".join(f"<https://e.test/s{i}> <https://e.test/p> <https://e.test/o> .\n" for i in range(5)), encoding="utf-8"
    )
    catalog = index_directory(mirror, Policy(max_triples=3))
    assert set(catalog.entries) == {"https://e.test/good"}
    display = {path.name: resolve_inputs([str(path)], Path.cwd())[0].display for path in mirror.iterdir()}
    assert catalog.refused == (
        f"{display['dtd.rdf']} {SKIPPED}: SEC010: {display['dtd.rdf']} declares an external DTD or entity "
        "(SYSTEM/PUBLIC)",
        f"{display['many.nt']} {SKIPPED}: SEC002: graph has more than 3 triples (max_triples)",
        f"{display['zipped.ttl']} {SKIPPED}: SEC011: {display['zipped.ttl']} is gzip-compressed; "
        "compressed input is refused",
    )


def test_a_file_that_does_not_parse_and_a_catalog_are_skipped_silently(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mirror = tmp_path / "mirror"
    mirror.mkdir()
    (mirror / "m.ttl").write_text(ONTOLOGY.format(iri="https://e.test/m"), encoding="utf-8")
    (mirror / "broken.ttl").write_text("this is not turtle", encoding="utf-8")
    (mirror / "notes.json").write_text('{"not": "json-ld"', encoding="utf-8")
    (mirror / "catalog-v001.xml").write_text(OASIS_CATALOG, encoding="utf-8")  # SEC010 as RDF, but a catalog
    catalog = index_directory(mirror, Policy())
    assert (set(catalog.entries), catalog.refused) == ({"https://e.test/m"}, ())
    (mirror / "other-catalog.xml").write_text(OASIS_CATALOG, encoding="utf-8")  # another name is not excused
    assert [line.split(": ")[1] for line in index_directory(mirror, Policy()).refused] == ["SEC010"]
    ontology = tmp_path / "o.ttl"
    ontology.write_text(ONTOLOGY.format(iri="https://e.test/o"), encoding="utf-8")
    (mirror / "other-catalog.xml").unlink()
    code, _report_, err = _report(capsys, str(ontology), "--import-dir", str(mirror))
    assert (code, err) == (0, "")


def test_a_clean_import_dir_prints_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _bfo_like(tmp_path / "mirror")
    ontology = tmp_path / "o.ttl"
    ontology.write_text(ONTOLOGY.format(iri="https://e.test/o"), encoding="utf-8")
    code, _report_, err = _report(capsys, str(ontology), "--import-dir", str(tmp_path / "mirror"))
    assert (code, err) == (0, "")


def test_a_folder_over_max_imported_files_is_sec015_and_names_no_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _refusing_mirror(tmp_path / "mirror")
    config = tmp_path / "policy.json"
    config.write_text(json.dumps({"max_input_bytes": 300, "max_imported_files": 1}), encoding="utf-8")
    (tmp_path / "o.ttl").write_text(ONTOLOGY.format(iri="https://e.test/o"), encoding="utf-8")
    code, _report_, err = _report(capsys, "o.ttl", "--import-dir", "mirror", "--config", "policy.json")
    assert (code, err) == (TOOL_FAILURE, "SEC015: --import-dir mirror holds more than 1 files (max_imported_files)\n")
