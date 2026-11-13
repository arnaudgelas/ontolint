"""Mutation survivors in older code that issue #19 took over: the TOOL005 hint, module grouping, catalogs."""

from __future__ import annotations

from pathlib import Path

import pytest
from rdflib import Graph

from ontolint import cli
from ontolint.cli import DEFINITION_HINT_MINIMUM, main
from ontolint.imports import index_directory, read_catalog
from ontolint.loader import LoadedGraph
from ontolint.paths import resolve_inputs
from ontolint.policy import Policy
from ontolint.source_locations import SourceIndex

PREFIXES = """@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix ex: <https://example.test/onto#> .
<https://example.test/onto> a owl:Ontology .
"""
CATALOG_NS = "urn:oasis:names:tc:entity:xmlns:xml:catalog"


def _hint(tmp_path: Path, capsys: pytest.CaptureFixture[str], with_predicate: int, without: int, *rules: str) -> str:
    """The TOOL005 lines for terms without a definition, ``with_predicate`` of them carrying ``ex:termDefinition``."""
    terms = [f"ex:D{i} a owl:Class ; ex:termDefinition 'Def {i}.'@en .\n" for i in range(with_predicate)]
    terms += [f"ex:N{i} a owl:Class .\n" for i in range(without)]
    path = tmp_path / "o.ttl"
    path.write_text(PREFIXES + "".join(terms), encoding="utf-8")
    main([str(path), "--select", ",".join(("LEX002", *rules)), "--fail-on", "never", "--output", str(tmp_path / "r")])
    return "\n".join(line for line in capsys.readouterr().err.splitlines() if line.startswith("TOOL005"))


def test_the_hint_needs_exactly_the_minimum_of_lex002_terms(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert f"{DEFINITION_HINT_MINIMUM} of the {DEFINITION_HINT_MINIMUM} terms" in _hint(
        tmp_path, capsys, DEFINITION_HINT_MINIMUM, 0
    )
    assert _hint(tmp_path, capsys, DEFINITION_HINT_MINIMUM - 1, 0) == ""


def test_only_lex002_findings_count_towards_the_minimum(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # LEX001 reports the same terms (no label): they must not lift nine LEX002 terms over the minimum.
    assert _hint(tmp_path, capsys, DEFINITION_HINT_MINIMUM - 1, 0, "LEX001") == ""


def test_the_predicate_must_be_on_at_least_half_of_the_terms(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert "5 of the 10 terms" in _hint(tmp_path, capsys, 5, 5)
    assert _hint(tmp_path, capsys, 4, 6) == ""


def test_no_pattern_library_means_no_member_origins() -> None:
    assert cli._library_origins(None, []) == {}


def test_an_unused_module_annotation_groups_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    item = resolve_inputs([str(tmp_path / "o.ttl")], tmp_path)[0]
    loaded = LoadedGraph(Graph(), SourceIndex({}))
    policy = Policy(module_annotation="<https://example.test/inModule>")
    # Not grouped: _lint_file then gives no finding a module.
    assert cli._module_grouping(item, loaded, policy) is None
    assert "TOOL006: note: no term in" in capsys.readouterr().err


@pytest.mark.parametrize(
    "child",
    [
        '<uri name="https://example.test/x"/>',
        '<uri uri="x.ttl"/>',
        '<rewriteURI uriStartString="https://example.test/"/>',
        '<rewriteURI rewritePrefix="mirror/"/>',
    ],
)
def test_a_catalog_entry_without_both_attributes_is_ignored(tmp_path: Path, child: str) -> None:
    path = tmp_path / "catalog-v001.xml"
    path.write_text(f'<catalog xmlns="{CATALOG_NS}">{child}</catalog>', encoding="utf-8")
    catalog = read_catalog(path, Policy().max_input_bytes)
    assert (catalog.entries, catalog.rewrites) == ({}, ())


def test_an_iri_one_file_declares_is_not_a_duplicate(tmp_path: Path) -> None:
    (tmp_path / "a.ttl").write_text(PREFIXES, encoding="utf-8")
    catalog = index_directory(tmp_path, Policy())
    assert catalog.entries == {"https://example.test/onto": (tmp_path / "a.ttl").resolve()}
    assert dict(catalog.duplicates) == {}
