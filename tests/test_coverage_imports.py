"""Catalog read failures and import closures where several IRIs name one file."""

from __future__ import annotations

from pathlib import Path

import pytest

from ontolint.imports import CatalogError, load_closure, read_catalog
from ontolint.loader import LoadedGraph, load_document
from ontolint.paths import resolve_inputs
from ontolint.policy import Policy

TTL = "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n<https://t.test/{name}> a owl:Ontology {imports}.\n"


def test_an_unreadable_catalog_is_a_catalog_error_naming_the_file(tmp_path: Path) -> None:
    missing = tmp_path / "catalog-v001.xml"

    with pytest.raises(CatalogError) as info:
        read_catalog(missing, 10_000)

    assert str(info.value).startswith(f"cannot read the catalog {missing}: ")
    assert isinstance(info.value.__cause__, OSError)


def test_two_iris_for_one_file_load_it_once(tmp_path: Path) -> None:
    (tmp_path / "root.ttl").write_text(
        TTL.format(name="root", imports="; owl:imports <https://t.test/one>, <https://t.test/two> "), encoding="utf-8"
    )
    (tmp_path / "shared.ttl").write_text(TTL.format(name="shared", imports=""), encoding="utf-8")
    (tmp_path / "catalog-v001.xml").write_text(
        '<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">'
        '<uri name="https://t.test/one" uri="shared.ttl"/><uri name="https://t.test/two" uri="shared.ttl"/>'
        "</catalog>",
        encoding="utf-8",
    )
    policy = Policy()
    item = resolve_inputs([str(tmp_path / "root.ttl")], tmp_path)[0]
    root = load_document(item, policy, tmp_path)
    catalog = read_catalog(tmp_path / "catalog-v001.xml", policy.max_input_bytes)

    closure = load_closure(LoadedGraph(root.graph, root.source_index), tmp_path / "root.ttl", policy, catalog)

    assert len(closure.files) == 1
    assert closure.files[0].endswith("shared.ttl")
    assert closure.resolved >= {"https://t.test/one", "https://t.test/two"}
