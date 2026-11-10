"""Modules inside one file: ``--module-annotation`` (MOMo's ``opla:isNativeTo``) and ``--module-by namespace``.

The fixtures copy the two real layouts: a MOMo schema that marks each term with the module it is native
to (the food-traceability schema), and a merged release keeping one namespace per source ontology
(Tractus-X ``ontology.ttl``), with a local-name and a label collision between two of them.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from jsonschema.validators import validator_for
from rdflib import Graph, Literal, URIRef

from ontolint.cli import main
from ontolint.models import Finding
from ontolint.modules import UnresolvedModulePredicate, finding_modules, module_summary, resolve_predicate
from ontolint.policy import Policy

SCHEMA = Path(__file__).parent / "schemas" / "sarif-schema-2.1.0.json"
FOOD = "http://example.test/food#"
USAGE_ERROR = 2  # argparse's exit code

MOMO = f"""
@prefix : <{FOOD}> .
@prefix opla: <http://ontologydesignpatterns.org/opla#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
<http://example.test/food> a owl:Ontology .
:Container a owl:Class ; opla:isNativeTo "Container" .
:hasCapacity a owl:ObjectProperty ; rdfs:label "has capacity" ; opla:isNativeTo "Container" .
:Event a owl:Class ; rdfs:label "Event" ; opla:isNativeTo "Event" .
:Shared a owl:Class ; rdfs:label "Shared" ; opla:isNativeTo "Container", "Event" .
:Loose a owl:Class .
"""

MERGED = """
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix b: <https://example.test/ontology/behaviour#> .
@prefix m: <https://example.test/ontology/bill-of-material#> .
<https://example.test/ontology> a owl:Ontology .
b:component a owl:ObjectProperty ; rdfs:label "component"@en .
m:component a owl:ObjectProperty ; rdfs:label "part"@en .
b:Recipient a owl:Class ; rdfs:label "Party"@en .
m:Supplier a owl:Class ; rdfs:label "Party"@en .
m:Lonely a owl:Class .
"""


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = main([*argv, "--fail-on", "never"])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _json(capsys: pytest.CaptureFixture[str], *argv: str) -> dict[str, Any]:
    return json.loads(_run(capsys, *argv, "--format", "json")[1])


# --- resolving the predicate ---------------------------------------------------------------------------


def test_a_curie_resolves_through_the_files_prefixes() -> None:
    prefixes = [("opla", "http://ontologydesignpatterns.org/opla#")]
    assert resolve_predicate("opla:isNativeTo", prefixes) == URIRef("http://ontologydesignpatterns.org/opla#isNativeTo")
    assert resolve_predicate(":x", [("", "http://example.test/#")]) == URIRef("http://example.test/#x")


def test_iris_are_taken_as_they_are() -> None:
    assert resolve_predicate("<urn:x:p>", []) == URIRef("urn:x:p")
    assert resolve_predicate("http://example.test/p", []) == URIRef("http://example.test/p")
    assert resolve_predicate("urn:x:p", []) == URIRef("urn:x:p")


def test_a_later_declaration_of_a_prefix_wins() -> None:
    prefixes = [("ex", "http://rdflib.default/"), ("ex", "http://the.file/")]
    assert resolve_predicate("ex:p", prefixes) == URIRef("http://the.file/p")


@pytest.mark.parametrize("text", ["nope:p", "isNativeTo", "a b:c", "<opla:isNativeTo", "<opla"])
def test_an_undeclared_prefix_or_a_bare_name_is_refused(text: str) -> None:
    with pytest.raises(UnresolvedModulePredicate):
        resolve_predicate(text, [("opla", "http://ontologydesignpatterns.org/opla#")])


# --- placing findings in modules -----------------------------------------------------------------------


def _finding(focus: str, *related: str, severity: str = "warning") -> Finding:
    return Finding("X001", severity, focus, "m", "s", related=related)


def test_by_namespace_a_finding_belongs_to_its_terms_namespaces() -> None:
    graph = Graph()
    one, collision = _finding("https://e.test/a#T"), _finding("https://e.test/a#T", "https://e.test/b#T")
    modules = finding_modules(graph, [one, collision, _finding("(ontology)"), _finding("_:abc")], None)
    assert modules == {one: ("https://e.test/a#",), collision: ("https://e.test/a#", "https://e.test/b#")}


def test_by_annotation_literals_and_iris_name_modules() -> None:
    graph = Graph()
    p = URIRef("http://e.test/native")
    graph.add((URIRef("http://e.test/A"), p, Literal("Container")))
    graph.add((URIRef("http://e.test/B"), p, URIRef("http://e.test/modules/Event")))
    a, b, c = _finding("http://e.test/A"), _finding("http://e.test/B"), _finding("http://e.test/C")
    assert finding_modules(graph, [a, b, c], p) == {a: ("Container",), b: ("http://e.test/modules/Event",)}


def test_the_summary_counts_a_shared_finding_in_each_module() -> None:
    modules = {
        _finding("a", severity="warning"): ("M1",),
        _finding("b", severity="info"): ("M1", "M2"),
    }
    assert module_summary(modules) == {"M1": {"warning": 1, "info": 1}, "M2": {"info": 1}}


def test_related_terms_never_change_a_findings_identity_or_json() -> None:
    plain, related = _finding("a"), _finding("a", "b")
    assert plain == related
    assert hash(plain) == hash(related)
    assert "related" not in related.to_dict()


def _focus(text: str) -> str:
    match = re.search(r"Focus: (\S+)\. Suggestion", text)
    assert match is not None
    return match[1]


# --- end to end -------------------------------------------------------------------------------------------


def test_text_names_the_module_and_summarises_by_module(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write(tmp_path, "food.ttl", MOMO)
    _, out, err = _run(capsys, str(path), "--module-annotation", "opla:isNativeTo", "--select", "LEX001")
    assert f"LEX001 {FOOD}Container: Term has no label.\n    Fix:" in out
    assert "\n    In: module Container\n" in out
    assert out.endswith("Findings by module:\n    Container: 1 warning\n")
    assert f"LEX001 {FOOD}Loose" in out
    assert "TOOL006" not in err


def test_json_and_sarif_carry_the_modules(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write(tmp_path, "food.ttl", MOMO)
    argv = (str(path), "--module-annotation", "opla:isNativeTo", "--select", "LEX002")
    document = _json(capsys, *argv)
    modules = {f["focus"].removeprefix(FOOD): f.get("modules") for f in document["findings"]}
    assert modules == {
        "Container": ["Container"],
        "hasCapacity": ["Container"],
        "Event": ["Event"],
        "Shared": ["Container", "Event"],
        "Loose": None,
    }
    assert document["files"][0]["module_summary"] == {"Container": {"info": 3}, "Event": {"info": 2}}
    main([*argv, "--format", "sarif", "--fail-on", "never"])
    sarif = json.loads(capsys.readouterr().out)
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator_for(schema)(schema).validate(sarif)
    results = {_focus(r["message"]["text"]): r for r in sarif["runs"][0]["results"]}
    assert results[f"{FOOD}Shared"]["properties"] == {"modules": ["Container", "Event"]}
    assert "properties" not in results[f"{FOOD}Loose"]


def test_collisions_between_namespaces_belong_to_both(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write(tmp_path, "merged.ttl", MERGED)
    document = _json(capsys, str(path), "--module-by", "namespace", "--select", "IRI003,LEX004,LEX002")
    by_rule = {(f["rule"], f["focus"].rsplit("#")[1]): f["modules"] for f in document["findings"]}
    behaviour, bom = "https://example.test/ontology/behaviour#", "https://example.test/ontology/bill-of-material#"
    assert by_rule[("IRI003", "component")] == [behaviour, bom]
    assert by_rule[("LEX004", "Recipient")] == [behaviour, bom]
    assert by_rule[("LEX002", "Lonely")] == [bom]


def test_grouping_leaves_findings_and_fingerprints_alone(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write(tmp_path, "merged.ttl", MERGED)
    plain, grouped = tmp_path / "plain.json", tmp_path / "grouped.json"
    _run(capsys, str(path), "--write-baseline", str(plain))
    _run(capsys, str(path), "--module-by", "namespace", "--write-baseline", str(grouped))
    assert plain.read_text(encoding="utf-8") == grouped.read_text(encoding="utf-8")
    without = [
        {k: v for k, v in f.items() if k != "modules"}
        for f in _json(capsys, str(path), "--module-by", "namespace")["findings"]
    ]
    assert without == _json(capsys, str(path))["findings"]
    assert "module_summary" not in _json(capsys, str(path))["files"][0]


def test_the_module_summary_counts_only_what_the_baseline_leaves(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, "merged.ttl", MERGED)
    baseline = tmp_path / "baseline.json"
    _run(capsys, str(path), "--select", "LEX002", "--write-baseline", str(baseline))
    document = _json(
        capsys, str(path), "--select", "LEX002,IRI003", "--module-by", "namespace", "--baseline", str(baseline)
    )
    assert {f["rule"] for f in document["findings"]} == {"IRI003"}
    # The one finding left is a collision, so it counts once in each of its two modules.
    assert document["files"][0]["module_summary"] == {
        "https://example.test/ontology/behaviour#": {"info": 1},
        "https://example.test/ontology/bill-of-material#": {"info": 1},
    }


def test_an_undeclared_prefix_is_a_warning_not_a_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write(tmp_path, "food.ttl", MOMO)
    code, out, err = _run(capsys, str(path), "--module-annotation", "momo:isNativeTo")
    assert code == 0
    assert "TOOL006: warning: module annotation 'momo:isNativeTo' is not an IRI" in err
    assert "In: module" not in out


def test_an_unused_predicate_says_so(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write(tmp_path, "merged.ttl", MERGED)
    _, out, err = _run(capsys, str(path), "--module-annotation", "<http://ontologydesignpatterns.org/opla#isNativeTo>")
    assert "TOOL006: note: no term in" in err
    assert "carries <http://ontologydesignpatterns.org/opla#isNativeTo>" in err
    assert "Findings by module" not in out


def test_the_two_options_are_alternatives(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["x.ttl", "--module-by", "namespace", "--module-annotation", "ex:p"])
    assert raised.value.code == USAGE_ERROR
    assert "--module-annotation and --module-by are alternatives" in capsys.readouterr().err


def test_the_policy_file_sets_grouping_and_the_cli_replaces_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, "merged.ttl", MERGED)
    config = _write(
        tmp_path, "policy.json", json.dumps({"module_annotation": "http://ontologydesignpatterns.org/opla#isNativeTo"})
    )
    _, _, err = _run(capsys, str(path), "--config", str(config))
    assert "TOOL006: note" in err  # the policy's annotation was used
    document = _json(capsys, str(path), "--config", str(config), "--module-by", "namespace", "--select", "LEX001")
    assert document["findings"][0]["modules"] == ["https://example.test/ontology/bill-of-material#"]


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"module_annotation": "opla:isNativeTo x"}, "module_annotation must be an absolute predicate IRI"),
        ({"module_annotation": 3}, "module_annotation must be an absolute predicate IRI"),
        ({"module_by": "annotation"}, "module_by must be one of namespace"),
        ({"module_by": "namespace", "module_annotation": "http://e.test/p"}, "alternatives"),
    ],
)
def test_the_policy_file_rejects_bad_grouping(data: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Policy.from_mapping(data)


def test_grouping_keys_are_known_policy_keys() -> None:
    policy = Policy.from_mapping({"module_by": "namespace"})
    assert policy.module_by == "namespace"
    assert policy.unknown_keys == ()
