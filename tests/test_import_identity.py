"""ONT009: a catalog entry whose file does not declare the imported IRI (issue #60).

Each test writes a tiny closure into ``tmp_path`` (a root, the files a catalog maps its imports to, and the
catalog) and reads the report of ``ontolint --follow-imports``.  The file is still loaded as the import: the rule
adds a finding, it never changes the closure.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ontolint.cli import main
from ontolint.models import ImportMismatch
from ontolint.rules.import_identity import MAX_LISTED, message

PREFIXES = "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
ROOT_IRI = "https://example.test/root"
LIB = "https://example.test/lib"
OTHER = "https://example.test/other"
LIB_1 = "https://example.test/lib/1.0"
MODS = "https://example.test/mods/"
MESSAGE_BOUND = 1500


def write(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(PREFIXES + body if name.endswith(".ttl") else body, encoding="utf-8")
    return path


def catalog(directory: Path, *entries: tuple[str, str], rewrite: bool = False) -> None:
    element = "rewriteURI" if rewrite else "uri"
    keys = ("uriStartString", "rewritePrefix") if rewrite else ("name", "uri")
    rows = "".join(f'  <{element} {keys[0]}="{iri}" {keys[1]}="{target}"/>\n' for iri, target in entries)
    write(
        directory,
        "catalog-v001.xml",
        f'<?xml version="1.0"?>\n<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">\n{rows}</catalog>\n',
    )


def root(directory: Path, *imports: str) -> Path:
    targets = " , ".join(f"<{iri}>" for iri in imports)
    return write(directory, "root.ttl", f"<{ROOT_IRI}> a owl:Ontology ; owl:imports {targets} .\n")


def lint(capsys: pytest.CaptureFixture[str], path: Path, *extra: str) -> tuple[int, dict[str, Any], str]:
    code = main([str(path), "--follow-imports", "--format", "json", *extra])
    captured = capsys.readouterr()
    return code, (json.loads(captured.out) if captured.out else {}), captured.err


def found(report: dict[str, Any], rule: str = "ONT009") -> list[dict[str, Any]]:
    return [f for f in report["findings"] if f["rule"] == rule]


def mapped(tmp_path: Path, body: str, name: str = "wrong.ttl", iri: str = LIB) -> Path:
    """A root importing ``iri``, which the catalog maps to ``name`` holding ``body``."""
    write(tmp_path, name, body)
    catalog(tmp_path, (iri, name))
    return root(tmp_path, iri)


def reported(capsys: pytest.CaptureFixture[str], path: Path) -> list[dict[str, Any]]:
    return found(lint(capsys, path, "--fail-on", "never")[1])


# --- the issue's reproduction ---------------------------------------------------------------------


def test_the_issue_reproduction_reports_the_mismatch_once_and_still_loads_the_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    start = mapped(tmp_path, f"<{OTHER}> a owl:Ontology .\n<{OTHER}#Z> a owl:Class .\n")
    code, report, _err = lint(capsys, start, "--fail-on", "never")
    assert code == 0
    (finding,) = found(report)
    assert finding["severity"] == "warning"
    assert finding["focus"] == LIB
    assert finding["path"].endswith("root.ttl")
    assert finding["message"] == (
        f"owl:imports <{LIB}> is loaded from {tmp_path / 'wrong.ttl'}, which declares ontology <{OTHER}>, not <{LIB}>."
    )
    assert [f["focus"] for f in found(report, "CLS001")] == [f"{OTHER}#Z"]  # loaded as before: findings do not move
    assert not found(report, "SEC007")


def test_the_finding_fails_a_run_at_warning_and_can_be_ignored(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    start = mapped(tmp_path, f"<{OTHER}> a owl:Ontology .\n")
    assert lint(capsys, start, "--select", "ONT009", "--fail-on", "warning")[0] == 1
    code, report, _err = lint(capsys, start, "--select", "ONT009", "--ignore", "ONT009", "--fail-on", "warning")
    assert (code, found(report)) == (0, [])


def test_without_following_imports_nothing_is_loaded_and_nothing_is_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    start = mapped(tmp_path, f"<{OTHER}> a owl:Ontology .\n")
    main([str(start), "--format", "json", "--fail-on", "never"])
    assert not found(json.loads(capsys.readouterr().out))


# --- what counts as declaring the imported IRI ----------------------------------------------------


def test_a_file_declaring_the_imported_ontology_iri_is_clean(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert not reported(capsys, mapped(tmp_path, f"<{LIB}> a owl:Ontology .\n"))


def test_a_file_whose_version_iri_is_the_imported_iri_is_clean(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert not reported(capsys, mapped(tmp_path, f"<{LIB}> a owl:Ontology ; owl:versionIRI <{LIB_1}> .\n", iri=LIB_1))


def test_an_odk_edit_file_and_its_release_are_each_clean_under_their_own_iri(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tmp_path, "lib-edit.ttl", f"<{LIB}> a owl:Ontology .\n")
    write(tmp_path, "lib-release.ttl", f"<{LIB}> a owl:Ontology ; owl:versionIRI <{LIB_1}> .\n")
    catalog(tmp_path, (LIB, "lib-edit.ttl"))
    assert not reported(capsys, root(tmp_path, LIB))
    catalog(tmp_path, (LIB, "lib-release.ttl"))  # the release imported by its ontology IRI
    assert not reported(capsys, root(tmp_path, LIB))
    catalog(tmp_path, (LIB_1, "lib-release.ttl"))  # and by its version IRI
    assert not reported(capsys, root(tmp_path, LIB_1))


def test_a_version_iri_mapped_to_another_release_of_the_series_is_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    older = "https://example.test/lib/0.9"
    start = mapped(tmp_path, f"<{LIB}> a owl:Ontology ; owl:versionIRI <{LIB_1}> .\n", iri=older)
    (finding,) = reported(capsys, start)
    assert finding["focus"] == older
    assert finding["message"].endswith(f"which declares ontology <{LIB}> (version <{LIB_1}>), not <{older}>.")


def test_a_file_declaring_several_ontologies_is_clean_when_one_is_the_imported_iri(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert not reported(capsys, mapped(tmp_path, f"<{OTHER}> a owl:Ontology .\n<{LIB}> a owl:Ontology .\n"))


def test_a_file_declaring_several_ontologies_none_of_them_the_imported_iri_names_them_all(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = f"<{OTHER}/b> a owl:Ontology .\n<{OTHER}/a> a owl:Ontology ; owl:versionIRI <{OTHER}/a/1> .\n"
    (finding,) = reported(capsys, mapped(tmp_path, body))
    assert finding["message"].endswith(
        f"which declares ontologies <{OTHER}/a> (version <{OTHER}/a/1>), <{OTHER}/b>, not <{LIB}>."
    )


def test_a_file_with_no_ontology_header_is_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (finding,) = reported(capsys, mapped(tmp_path, f"<{LIB}#A> a owl:Class .\n"))
    assert finding["message"] == (
        f"owl:imports <{LIB}> is loaded from {tmp_path / 'wrong.ttl'}, which declares no ontology, not <{LIB}>."
    )


def test_a_file_whose_only_ontology_is_a_blank_node_is_reported_as_declaring_none(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (finding,) = reported(capsys, mapped(tmp_path, "[] a owl:Ontology .\n"))
    assert "which declares no ontology," in finding["message"]
    assert "_:" not in finding["message"]


def test_a_literal_version_is_not_an_identity(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (finding,) = reported(capsys, mapped(tmp_path, f'<{OTHER}> a owl:Ontology ; owl:versionIRI "{LIB}" .\n'))
    assert "(version" not in finding["message"]


# --- where the check applies ----------------------------------------------------------------------


def test_a_file_iri_import_names_a_document_not_an_ontology_and_is_clean(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = write(tmp_path, "lib.ttl", f"<{OTHER}> a owl:Ontology .\n")
    assert not reported(capsys, root(tmp_path, target.resolve().as_uri()))


def test_a_rewrite_prefix_is_checked_like_an_entry(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(tmp_path, "mods/a.ttl", f"<{MODS}a.ttl> a owl:Ontology .\n")
    write(tmp_path, "mods/b.ttl", f"<{MODS}other.ttl> a owl:Ontology .\n")
    catalog(tmp_path, (MODS, "mods/"), rewrite=True)
    (finding,) = reported(capsys, root(tmp_path, f"{MODS}a.ttl", f"{MODS}b.ttl"))
    assert finding["focus"] == f"{MODS}b.ttl"


def test_a_catalog_next_to_an_imported_file_is_checked_for_the_imports_of_that_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    deep = "https://example.test/deep"
    write(tmp_path, "sub/lib.ttl", f"<{LIB}> a owl:Ontology ; owl:imports <{deep}> .\n")
    write(tmp_path, "sub/wrong.ttl", f"<{OTHER}> a owl:Ontology .\n")
    catalog(tmp_path / "sub", (deep, "wrong.ttl"))
    catalog(tmp_path, (LIB, "sub/lib.ttl"))
    (finding,) = reported(capsys, root(tmp_path, LIB))
    assert finding["focus"] == deep
    assert finding["path"].endswith("lib.ttl")  # the file that holds the owl:imports
    assert str(tmp_path / "sub" / "wrong.ttl") in finding["message"]


def test_two_imports_mapped_to_one_file_are_each_checked(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(tmp_path, "lib.ttl", f"<{LIB}> a owl:Ontology .\n")
    alias = "https://example.test/alias"
    catalog(tmp_path, (LIB, "lib.ttl"), (alias, "lib.ttl"))
    (finding,) = reported(capsys, root(tmp_path, LIB, alias))
    assert finding["focus"] == alias


def test_an_import_of_the_root_by_its_own_iri_is_clean(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert not reported(capsys, root(tmp_path, ROOT_IRI))


def test_an_import_mapped_to_the_root_file_under_another_iri_is_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    catalog(tmp_path, (LIB, "root.ttl"))
    (finding,) = reported(capsys, root(tmp_path, LIB))
    assert f"declares ontology <{ROOT_IRI}>, not <{LIB}>" in finding["message"]


def test_a_missing_file_stays_a_tool_note_and_is_not_reported_as_a_mismatch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    catalog(tmp_path, (LIB, "absent.ttl"))
    _code, report, err = lint(capsys, root(tmp_path, LIB), "--fail-on", "never")
    assert not found(report)
    assert "TOOL004" in err
    assert found(report, "SEC007")


def test_an_import_dir_file_matches_by_construction(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(tmp_path, "mirror/lib.ttl", f"<{LIB}> a owl:Ontology .\n")
    start = root(tmp_path, LIB)
    main([str(start), "--import-dir", str(tmp_path / "mirror"), "--format", "json", "--fail-on", "never"])
    assert not found(json.loads(capsys.readouterr().out))


# --- the message stays bounded and the finding keeps its identity --------------------------------


def test_a_file_declaring_many_ontologies_is_listed_with_a_bound(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = "".join(f"<{OTHER}/{n:04d}> a owl:Ontology .\n" for n in range(500))
    (finding,) = reported(capsys, mapped(tmp_path, body))
    assert " and 490 more" in finding["message"]
    assert len(finding["message"]) < MESSAGE_BOUND


def test_a_baseline_keeps_accepting_the_finding_when_the_file_or_its_ontology_changes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    start = mapped(tmp_path, f"<{OTHER}> a owl:Ontology .\n", name="one.ttl")
    accepted = tmp_path / "baseline.json"
    main([str(start), "--follow-imports", "--select", "ONT009", "--write-baseline", str(accepted)])
    capsys.readouterr()
    write(tmp_path, "two.ttl", f"<{OTHER}/2> a owl:Ontology .\n")
    catalog(tmp_path, (LIB, "two.ttl"))
    code, report, _err = lint(capsys, start, "--select", "ONT009", "--baseline", str(accepted), "--fail-on", "warning")
    assert (code, found(report)) == (0, [])
    write(tmp_path, "three.ttl", f"<{LIB}> a owl:Ontology .\n")  # fixed: the baseline entry is now stale
    catalog(tmp_path, (LIB, "three.ttl"))
    assert not reported(capsys, start)


def test_a_file_whose_ontology_has_many_versions_is_listed_with_a_bound(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = f"<{OTHER}> a owl:Ontology" + "".join(f" ; owl:versionIRI <{OTHER}/{n:03d}>" for n in range(40)) + " .\n"
    (finding,) = reported(capsys, mapped(tmp_path, body))
    assert "(versions <https://example.test/other/000>" in finding["message"]
    assert " and 30 more)" in finding["message"]


@pytest.mark.parametrize("count", [MAX_LISTED, MAX_LISTED + 1])
def test_the_message_names_every_ontology_up_to_the_bound_and_counts_the_rest(count: int) -> None:
    names = tuple((f"{OTHER}/{n:02d}", ()) for n in range(count))
    text = message(ImportMismatch(LIB, "w.ttl", names))
    assert (" more" in text) == (count > MAX_LISTED)
    assert text.count("<https://example.test/other/") == min(count, MAX_LISTED)
    if count > MAX_LISTED:
        assert "and 1 more, not" in text


@pytest.mark.parametrize("count", [MAX_LISTED, MAX_LISTED + 1])
def test_the_message_names_every_version_up_to_the_bound_and_counts_the_rest(count: int) -> None:
    versions = tuple(f"{OTHER}/v{n:02d}" for n in range(count))
    text = message(ImportMismatch(LIB, "w.ttl", ((OTHER, versions),)))
    assert (" more" in text) == (count > MAX_LISTED)
    assert text.count("/v") == min(count, MAX_LISTED)


def test_a_credential_in_an_imported_iri_is_masked_in_the_finding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (finding,) = reported(capsys, mapped(tmp_path, "<https://alice:s3cret@example.test/other> a owl:Ontology .\n"))
    assert "s3cret" not in json.dumps(finding)
    assert "https://****@example.test/other" in finding["message"]
