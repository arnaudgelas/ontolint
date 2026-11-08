"""Following owl:imports offline through an OASIS XML catalog (--follow-imports, --catalog).

The synthetic corpus in tests/fixtures/modular/ recreates a common modular layout: an umbrella with no
terms of its own, modules sharing one namespace, a diamond (the umbrella and core both import meta), a
cycle (meta imports the umbrella), a data module in a subdirectory mapped through a catalog group, a draft
module nobody imports, and one external import no catalog maps.
"""

from __future__ import annotations

import json
import re
import shutil
import socket
from pathlib import Path

import pytest

from ontolint.cli import main
from ontolint.imports import CatalogError, load_closure, read_catalog
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


def test_a_catalog_entry_naming_a_missing_file_is_an_input_error(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (corpus / "meta.ttl").unlink()
    code, _report_, err = _report(capsys, str(corpus / "umbrella.ttl"), "--follow-imports")
    assert code == TOOL_FAILURE
    assert err.startswith("INPUT001: ")


def test_an_imported_module_still_passes_the_safe_loader(corpus: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (corpus / "core.ttl").write_text("this is not turtle", encoding="utf-8")
    code, _report_, err = _report(capsys, str(corpus / "umbrella.ttl"), "--follow-imports")
    assert code == TOOL_FAILURE
    assert err.startswith("INPUT001: RDF input parsing failed")
