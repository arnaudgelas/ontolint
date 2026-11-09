"""IRI019 and ONT003 read facts the loader takes from a file's text: prefix declarations, SPDX comments."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ontolint.cli import main

HEADER = (
    "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
    "@prefix ex: <https://example.test/onto#> .\n"
    "<https://example.test/onto> a owl:Ontology .\nex:A a owl:Class .\n"
)


def _iri019(tmp_path: Path, name: str, text: str, *options: str) -> list[str]:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    out = tmp_path / "report.json"
    main([str(path), "--select", "IRI019", "--format", "json", "--fail-on", "never", "--output", str(out), *options])
    return [f["focus"] for f in json.loads(out.read_text(encoding="utf-8"))["findings"]]


def test_an_unused_declared_prefix_is_reported(tmp_path: Path) -> None:
    text = "@prefix cco: <https://cco.test/ns#> .\n" + HEADER
    assert _iri019(tmp_path, "o.ttl", text) == ["https://cco.test/ns#"]


def test_an_unused_prefix_rdflib_also_binds_by_default_is_reported(tmp_path: Path) -> None:
    # dcat: is one of RDFLib's default bindings; the file declares it, so it counts.
    text = "@prefix dcat: <http://www.w3.org/ns/dcat#> .\n" + HEADER
    assert _iri019(tmp_path, "o.ttl", text) == ["http://www.w3.org/ns/dcat#"]


def test_rdflib_defaults_the_file_never_declares_are_not_reported(tmp_path: Path) -> None:
    assert _iri019(tmp_path, "o.ttl", HEADER) == []


def test_editor_boilerplate_prefixes_are_not_reported(tmp_path: Path) -> None:
    text = (
        "@prefix xml: <http://www.w3.org/XML/1998/namespace> .\n"
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n" + HEADER
    )
    assert _iri019(tmp_path, "o.ttl", text) == []


def test_rdf_xml_namespace_declarations_count(tmp_path: Path) -> None:
    text = """<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:frbr="http://purl.org/vocab/frbr/core#">
  <owl:Ontology rdf:about="https://example.test/onto"/>
</rdf:RDF>
"""
    assert _iri019(tmp_path, "o.rdf", text) == ["http://purl.org/vocab/frbr/core#"]


def test_a_json_ld_context_is_never_reported(tmp_path: Path) -> None:
    text = json.dumps(
        {
            "@context": {"ex": "https://example.test/onto#", "unused": "https://unused.test/"},
            "@id": "ex:A",
            "@type": "http://www.w3.org/2002/07/owl#Class",
        }
    )
    assert _iri019(tmp_path, "o.jsonld", text) == []


@pytest.mark.slow
def test_a_parse_worker_reports_the_same_prefixes(tmp_path: Path) -> None:
    # max_parse_seconds parses in a worker process, which sends its bindings back with the triples.
    policy = tmp_path / "policy.json"
    policy.write_text('{"max_parse_seconds": 30}', encoding="utf-8")
    text = "@prefix cco: <https://cco.test/ns#> .\n" + HEADER
    assert _iri019(tmp_path, "o.ttl", text, "--config", str(policy)) == ["https://cco.test/ns#"]
