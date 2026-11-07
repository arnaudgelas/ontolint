"""Tests for reporting, CLI execution, and optional validation adapters."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

import pytest
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SH, SKOS

from ontolint.ontolint import Finding, Linter, _robot_profile_issues, _sarif, _shacl_issues, fingerprint, main

EX = Namespace("https://example.test/")
TOOL_FAILURE_EXIT = 2
XSD_STRING = URIRef("http://www.w3.org/2001/XMLSchema#string")
XSD_INTEGER = URIRef("http://www.w3.org/2001/XMLSchema#integer")


def test_shacl_and_report_serializers_preserve_actionable_information() -> None:
    data, shapes = Graph(), Graph()
    data.add((EX.instance, RDF.type, EX.Target))
    shape = EX.Shape
    shapes.add((shape, RDF.type, SH.NodeShape))
    shapes.add((shape, SH.targetClass, EX.Target))
    shapes.add((shape, SH.property, EX.PropertyShape))
    shapes.add((EX.PropertyShape, SH.minCount, Literal(1)))
    shapes.add((EX.PropertyShape, SH.path, EX.required))

    findings = _shacl_issues(data, shapes)

    assert findings and findings[0].rule == "SHACL001"
    assert fingerprint(findings[0]) == fingerprint(findings[0])
    sarif = _sarif(findings)
    assert sarif["runs"][0]["results"][0]["ruleId"] == "SHACL001"


def test_findings_are_immutable_and_hashable_value_objects() -> None:
    finding = Finding("ONT001", "warning", "focus", "message", "fix")

    assert hash(finding)
    with pytest.raises(FrozenInstanceError):
        finding.rule = "ONT002"  # type: ignore[misc] -- verifies the frozen dataclass contract.


def test_shacl_conforming_graph_has_no_validation_findings() -> None:
    assert _shacl_issues(Graph(), Graph()) == []


def test_shacl_adapter_rejects_an_unexpected_report_type(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        sys.modules, "pyshacl", SimpleNamespace(validate=lambda *_args, **_kwargs: (False, object(), None))
    )

    with pytest.raises(RuntimeError, match="unexpected report type"):
        _shacl_issues(Graph(), Graph())


def test_shacl_adapter_uses_fixed_validation_options_and_fallback_message(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_validate(*_args: object, **kwargs: object) -> tuple[bool, Graph, None]:
        assert kwargs.pop("shacl_graph") is not None
        assert kwargs == {"inference": "none", "advanced": True, "meta_shacl": True, "abort_on_first": False}
        return False, Graph(), None

    monkeypatch.setitem(sys.modules, "pyshacl", SimpleNamespace(validate=fake_validate))

    findings = _shacl_issues(Graph(), Graph())

    assert findings[0].focus == "(shapes)"


def test_cli_writes_sarif_and_filters_a_baseline(tmp_path: Path) -> None:
    ontology = tmp_path / "ontology.ttl"
    report, baseline = tmp_path / "report.sarif", tmp_path / "baseline.json"
    ontology.write_text("@prefix ex: <https://example.test/> . ex:term a ex:Undeclared .", encoding="utf-8")

    assert (
        main(
            [
                str(ontology),
                "--format",
                "sarif",
                "--output",
                str(report),
                "--write-baseline",
                str(baseline),
                "--fail-on",
                "never",
            ]
        )
        == 0
    )
    assert json.loads(report.read_text(encoding="utf-8"))["version"] == "2.1.0"
    assert json.loads(baseline.read_text(encoding="utf-8"))["fingerprints"]
    assert main([str(ontology), "--baseline", str(baseline), "--fail-on", "error"]) == 0


def test_robot_adapter_returns_no_finding_on_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ontology = tmp_path / "ontology.owl"
    ontology.write_text("<rdf:RDF/>", encoding="utf-8")

    def fake_run(_command: list[str], **kwargs: object) -> SimpleNamespace:
        assert kwargs == {"capture_output": True, "text": True, "timeout": 1, "check": False}
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr("ontolint.ontolint.subprocess.run", fake_run)

    assert _robot_profile_issues(ontology, "EL", "robot:test", 1) == []


def test_fingerprint_is_stable_for_unicode_and_changes_with_finding_content() -> None:
    accented = Finding("ONT001", "warning", "café", "déjà vu", "fix")
    changed = Finding("ONT001", "warning", "café", "different", "fix")

    assert fingerprint(accented) == fingerprint(accented)
    assert fingerprint(accented) != fingerprint(changed)
    expected_payload = '["ONT001","café","déjà vu"]'.encode()
    assert fingerprint(accented) == hashlib.sha256(expected_payload).hexdigest()


def test_helpers_and_owl_edge_cases_have_safe_negative_outcomes() -> None:
    graph, shapes = Graph(), Graph()
    invalid_list = BNode()
    graph.add((invalid_list, RDF.first, EX.item))
    assert Linter.list_items(graph, invalid_list) is None
    assert Linter(Graph()).local(BNode()) is False
    assert Finding("ONT001", "warning", "focus", "message", "fix").to_dict()["rule"] == "ONT001"

    object_property, data_property = EX.object, EX.data
    graph.add((object_property, RDF.type, OWL.ObjectProperty))
    graph.add((data_property, RDF.type, OWL.DatatypeProperty))
    graph.add((object_property, OWL.inverseOf, data_property))
    graph.add((object_property, RDF.type, OWL.SymmetricProperty))
    graph.add((data_property, RDF.type, OWL.TransitiveProperty))
    graph.add((EX.subject, object_property, EX.resource))
    graph.add((EX.subject, data_property, Literal("literal")))
    graph.add((EX.disjoint, RDF.type, OWL.Class))
    graph.add((EX.domain, RDF.type, OWL.Class))
    graph.add((EX.disjoint, OWL.disjointWith, EX.domain))
    graph.add((object_property, RDFS.domain, EX.domain))
    graph.add((EX.subject, RDF.type, EX.disjoint))
    restriction = BNode()
    graph.add((restriction, OWL.allValuesFrom, EX.domain))
    graph.add((restriction, OWL.someValuesFrom, EX.domain))
    shapes.add((EX.clean_shape, RDF.type, SH.NodeShape))
    shapes.add((EX.clean_shape, RDFS.label, Literal("shape")))
    shapes.add((EX.clean_shape, RDFS.comment, Literal("comment")))

    rules = {finding.rule for finding in Linter(graph, shapes, base=str(EX)).run()}
    assert {"OWL008", "OWL009", "DATA002"} <= rules
    assert "OWL013" not in rules
    assert "OWL011" not in rules


def test_invalid_property_chain_and_datatype_exceptions_are_safe() -> None:
    graph = Graph()
    invalid_chain, property_chain = BNode(), EX.chain
    graph.add((invalid_chain, RDF.first, EX.member))
    graph.add((property_chain, OWL.propertyChainAxiom, invalid_chain))
    string_property, integer_property = EX.string_property, EX.integer_property
    graph.add((string_property, RDF.type, OWL.DatatypeProperty))
    graph.add((string_property, RDFS.range, XSD_STRING))
    graph.add((EX.subject, string_property, Literal("plain string")))
    graph.add((integer_property, RDF.type, OWL.DatatypeProperty))
    graph.add((integer_property, RDFS.range, XSD_INTEGER))
    graph.add((EX.subject, integer_property, Literal(1)))

    rules = {finding.rule for finding in Linter(graph).run()}

    assert "OWL010" not in rules
    assert "DATA001" not in rules


def test_undeclared_range_predicate_is_reported_only_when_local() -> None:
    graph = Graph()
    graph.add((EX.local_range, RDFS.range, EX.Target))
    graph.add((URIRef("https://external.example/range"), RDFS.range, EX.Target))

    rules = {finding.rule for finding in Linter(graph, base=str(EX)).run()}

    assert "OWL002" in rules


def test_declared_owl_entities_do_not_trigger_undeclared_or_missing_schema_rules() -> None:
    graph = Graph()
    first, second, object_property = EX.first, EX.second, EX.object_property
    for term in (first, second):
        graph.add((term, RDF.type, OWL.Class))
    graph.add((first, RDFS.subClassOf, second))
    graph.add((object_property, RDF.type, OWL.ObjectProperty))
    graph.add((object_property, RDFS.domain, first))
    graph.add((object_property, RDFS.range, second))
    graph.add((object_property, OWL.inverseOf, EX.inverse_property))
    graph.add((EX.inverse_property, RDF.type, OWL.ObjectProperty))
    graph.add((EX.inverse_property, RDFS.domain, second))
    graph.add((EX.inverse_property, RDFS.range, first))
    graph.add((EX.instance, object_property, EX.target))

    rules = {finding.rule for finding in Linter(graph, base=str(EX)).run()}

    assert not {"CLS001", "OWL001", "OWL002", "OWL005", "OWL006", "OWL008", "OWL009", "OWL015"} & rules


def test_skos_and_shape_happy_paths_do_not_emit_integrity_errors() -> None:
    graph, shapes = Graph(), Graph()
    concept = EX.clean_concept
    graph.add((concept, RDF.type, SKOS.Concept))
    graph.add((concept, SKOS.prefLabel, Literal("Clean", lang="en")))
    graph.add((concept, SKOS.inScheme, EX.scheme))
    shape = EX.clean_property_shape
    shapes.add((shape, RDF.type, SH.PropertyShape))
    shapes.add((shape, SH.name, Literal("name", lang="en")))
    shapes.add((shape, SH.description, Literal("description", lang="en")))
    shapes.add((shape, SH.minCount, Literal(1)))
    shapes.add((shape, SH.message, Literal("message", lang="en")))

    rules = {finding.rule for finding in Linter(graph, shapes, base=str(EX)).run()}
    assert not {"SKOS001", "SKOS002", "SKOS003", "SKOS004", "SKOS005", "SHQ001", "SHQ002", "SHQ003", "SHQ005"} & rules


def test_skos_nonliteral_preferred_label_does_not_count_as_a_label() -> None:
    graph = Graph()
    concept = EX.nonliteral_label
    graph.add((concept, RDF.type, SKOS.Concept))
    graph.add((concept, SKOS.prefLabel, EX.not_a_literal))
    graph.add((concept, SKOS.inScheme, EX.scheme))

    rules = {finding.rule for finding in Linter(graph).run()}

    assert "SKOS004" in rules


def test_skos_preferred_labels_in_distinct_languages_are_not_duplicates() -> None:
    graph = Graph()
    concept = EX.multilingual_concept
    graph.add((concept, RDF.type, SKOS.Concept))
    graph.add((concept, SKOS.prefLabel, Literal("Book", lang="en")))
    graph.add((concept, SKOS.prefLabel, Literal("Livre", lang="fr")))
    graph.add((concept, SKOS.inScheme, EX.scheme))

    rules = {finding.rule for finding in Linter(graph).run()}

    assert "SKOS001" not in rules


def test_shapes_require_each_node_shape_annotation_and_literal_language_values() -> None:
    graph, shapes = Graph(), Graph()
    target = EX.Target
    graph.add((EX.instance, RDF.type, target))

    missing_comment = EX.missing_comment
    shapes.add((missing_comment, RDF.type, SH.NodeShape))
    shapes.add((missing_comment, RDFS.label, Literal("shape")))
    shapes.add((missing_comment, SH.targetClass, target))

    uri_name = EX.uri_name
    shapes.add((uri_name, RDF.type, SH.PropertyShape))
    shapes.add((uri_name, SH.name, EX.not_a_literal))

    findings = {(finding.rule, finding.focus) for finding in Linter(graph, shapes).run()}

    assert ("SHQ004", str(missing_comment)) in findings
    assert ("SHQ005", str(uri_name)) not in findings
    assert ("SHQ006", str(target)) not in findings


def test_shape_annotations_in_distinct_languages_are_not_duplicates() -> None:
    shapes = Graph()
    shape = EX.multilingual_shape
    shapes.add((shape, RDF.type, SH.PropertyShape))
    shapes.add((shape, SH.name, Literal("name", lang="en")))
    shapes.add((shape, SH.name, Literal("nom", lang="fr")))

    rules = {finding.rule for finding in Linter(Graph(), shapes).run()}

    assert "SHQ005" not in rules


def test_shape_coverage_requires_a_target_for_instantiated_classes() -> None:
    graph, shapes = Graph(), Graph()
    covered, uncovered = EX.covered, EX.uncovered
    for term in (covered, uncovered):
        graph.add((term, RDF.type, OWL.Class))
        graph.add((EX[f"instance_{term.split('/')[-1]}"], RDF.type, term))
    shape = EX.covered_shape
    shapes.add((shape, RDF.type, SH.NodeShape))
    shapes.add((shape, SH.targetClass, covered))

    findings = {(finding.rule, finding.focus) for finding in Linter(graph, shapes).run()}

    assert ("SHQ006", str(covered)) not in findings
    assert ("SHQ006", str(uncovered)) in findings


def test_equivalent_classes_and_valid_rdf_list_cover_hierarchy_edges() -> None:
    graph = Graph()
    left, right, head = EX.Left, EX.Right, BNode()
    for term in (left, right):
        graph.add((term, RDF.type, OWL.Class))
        graph.add((term, RDFS.label, Literal("same")))
    graph.add((left, OWL.equivalentClass, right))
    graph.add((head, RDF.first, left))
    graph.add((head, RDF.rest, RDF.nil))

    assert Linter.list_items(graph, head) == [left]
    assert "CLS009" in {finding.rule for finding in Linter(graph).run()}


def test_equivalence_with_an_undeclared_term_is_not_duplicate_class_diagnostic() -> None:
    graph = Graph()
    graph.add((EX.declared, RDF.type, OWL.Class))
    graph.add((EX.declared, RDFS.label, Literal("same")))
    graph.add((EX.undeclared, RDFS.label, Literal("same")))
    graph.add((EX.declared, OWL.equivalentClass, EX.undeclared))

    rules = {finding.rule for finding in Linter(graph, base=str(EX)).run()}

    assert "CLS009" not in rules
    assert "GOV003" in rules


def test_external_equivalent_class_is_not_treated_as_an_undeclared_local_term() -> None:
    graph = Graph()
    graph.add((EX.declared, RDF.type, OWL.Class))
    graph.add((EX.declared, OWL.equivalentClass, URIRef("https://external.example/Unknown")))

    rules = {finding.rule for finding in Linter(graph, base=str(EX)).run()}

    assert "GOV003" not in rules


def test_inverse_with_only_one_datatype_property_is_invalid() -> None:
    graph = Graph()
    object_property, data_property = EX.only_object, EX.only_data
    graph.add((object_property, RDF.type, OWL.ObjectProperty))
    graph.add((data_property, RDF.type, OWL.DatatypeProperty))
    graph.add((object_property, OWL.inverseOf, data_property))

    rules = {finding.rule for finding in Linter(graph).run()}

    assert "OWL009" in rules


def test_shacl_report_uses_default_message_only_when_none_were_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    result = BNode()
    report = Graph()
    report.add((result, RDF.type, SH.ValidationResult))
    report.add((result, SH.focusNode, EX.focus))
    report.add((result, SH.sourceShape, EX.source))
    report.add((result, SH.resultMessage, Literal("first")))
    report.add((result, SH.resultMessage, Literal("second")))
    monkeypatch.setitem(
        sys.modules, "pyshacl", SimpleNamespace(validate=lambda *_args, **_kwargs: (False, report, None))
    )

    findings = _shacl_issues(Graph(), Graph())

    assert findings[0].message.startswith("first; second")


def test_cli_options_override_configured_base_and_languages(tmp_path: Path) -> None:
    ontology, config, report = tmp_path / "ontology.ttl", tmp_path / "config.json", tmp_path / "report.json"
    ontology.write_text(
        "@prefix ex: <https://example.test/> . ex:Term a <http://www.w3.org/2002/07/owl#Class> ; "
        '<http://www.w3.org/2000/01/rdf-schema#label> "term"@en ; '
        '<http://www.w3.org/2000/01/rdf-schema#comment> "definition" .',
        encoding="utf-8",
    )
    config.write_text(json.dumps({"base": str(EX), "languages": ["fr"]}), encoding="utf-8")

    assert (
        main(
            [
                str(ontology),
                "--config",
                str(config),
                "--base",
                "https://other.example/",
                "--language",
                "en",
                "--format",
                "json",
                "--output",
                str(report),
                "--fail-on",
                "never",
            ]
        )
        == 0
    )
    rules = {finding["rule"] for finding in json.loads(report.read_text(encoding="utf-8"))["findings"]}
    assert "LEX008" not in rules
    assert "LEX009" not in rules

    assert (
        main(
            [
                str(ontology),
                "--config",
                str(config),
                "--base",
                str(EX),
                "--language",
                "en",
                "--format",
                "json",
                "--output",
                str(report),
                "--fail-on",
                "never",
            ]
        )
        == 0
    )
    rules = {finding["rule"] for finding in json.loads(report.read_text(encoding="utf-8"))["findings"]}
    assert "LEX008" not in rules


def test_cli_json_text_and_input_failures(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ontology, output = tmp_path / "ontology.ttl", tmp_path / "report.json"
    ontology.write_text("@prefix ex: <https://example.test/> . ex:term a ex:Type .", encoding="utf-8")

    assert main([str(ontology), "--format", "json", "--output", str(output), "--fail-on", "never"]) == 0
    assert "findings" in json.loads(output.read_text(encoding="utf-8"))
    assert main([str(ontology), "--format", "text", "--fail-on", "never"]) == 0
    assert "Ontology linter:" in capsys.readouterr().out
    bad = tmp_path / "bad.ttl"
    bad.write_text("this is not turtle", encoding="utf-8")
    assert main([str(bad)]) == TOOL_FAILURE_EXIT
    assert capsys.readouterr().err.startswith("INPUT001:")


def test_fingerprint_survives_a_lone_surrogate_deterministically() -> None:
    finding = Finding("ONT001", "warning", "x", "bad \ud800 text", "fix")
    payload = '["ONT001","x","bad \ud800 text"]'.encode("utf-8", errors="surrogatepass")

    assert fingerprint(finding) == hashlib.sha256(payload).hexdigest()
    assert fingerprint(finding, "a.ttl") != fingerprint(finding)
