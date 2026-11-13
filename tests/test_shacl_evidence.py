"""SHACL001 keeps every SHACL result property pySHACL writes as its ``evidence`` (JSON and SARIF only).

The message, focus, severity and fingerprint stay as they were; the evidence is what tells two violations of
one shape on one node apart, and what a fix has to change.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pyshacl
import pytest
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import RDF, SH
from rdflib.term import Node

from ontolint import Linter
from ontolint.adapters.shacl import (
    EVIDENCE_FIELDS,
    MALFORMED_PATH,
    MAX_DETAIL_DEPTH,
    MAX_PATH_DEPTH,
    MAX_PATH_SIZE,
    shacl_issues,
    shacl_result_key,
)
from ontolint.cli import main
from ontolint.models import Evidence, Finding
from ontolint.rules.support import stable_blank_id

EX = "https://example.test/"
XSD_INTEGER = "http://www.w3.org/2001/XMLSchema#integer"
PREFIXES = """@prefix ex: <https://example.test/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
"""
TWO_VALUES = PREFIXES + 'ex:a a ex:T ; ex:age "x", "y" .'
INTEGER_AGE = PREFIXES + "ex:AgeShape a sh:NodeShape ; sh:targetClass ex:T ; sh:property ex:Age .\n"
INTEGER_AGE += "ex:Age sh:path ex:age ; sh:datatype xsd:integer ."
ON_T = "ex:S a sh:NodeShape ; sh:targetClass ex:T ;"
VIOLATION = str(SH.Violation)


def _component(name: str) -> str:
    return str(SH[f"{name}ConstraintComponent"])


def _graphs(data: str, shapes: str) -> tuple[Graph, Graph]:
    return Graph().parse(data=PREFIXES + data, format="turtle"), Graph().parse(data=PREFIXES + shapes, format="turtle")


def _findings(data: str, shapes: str) -> list[Finding]:
    return list(Linter(*_graphs(data, shapes)).execute(["SHACL001"]).findings)


def _evidence(data: str, shapes: str) -> list[Evidence | None]:
    return [f.evidence for f in _findings(data, shapes)]


def _details(evidence: Evidence) -> list[Evidence]:
    """The nested results of ``evidence`` (its ``detail`` holds evidence, never text)."""
    nested = evidence.get("detail", ())
    assert not isinstance(nested, str)
    return [d for d in nested if not isinstance(d, str)]


def _files(tmp_path: Path, data: str, shapes: str) -> tuple[str, str]:
    data_file, shapes_file = tmp_path / "data.ttl", tmp_path / "shapes.ttl"
    data_file.write_text(PREFIXES + data, encoding="utf-8")
    shapes_file.write_text(PREFIXES + shapes, encoding="utf-8")
    return str(data_file), str(shapes_file)


def _cli(tmp_path: Path, capsys: pytest.CaptureFixture[str], data: str, shapes: str, fmt: str) -> dict[str, Any]:
    data_file, shapes_file = _files(tmp_path, data, shapes)
    args = [data_file, "--shapes", shapes_file, "--select", "SHACL001", "--format", fmt, "--fail-on", "never"]
    assert main(args) == 0
    document: dict[str, Any] = json.loads(capsys.readouterr().out)
    return document


def _reported_evidence(document: dict[str, Any], fmt: str) -> list[dict[str, Any]]:
    if fmt == "json":
        return [f["evidence"] for f in document["findings"]]
    return [r["properties"]["evidence"] for r in document["runs"][0]["results"]]


# --- the regression -----------------------------------------------------------------------------------


def test_two_violations_of_one_shape_on_one_node_differ_in_their_evidence() -> None:
    """Both findings read alike, as before; only the evidence says which value to fix."""
    first, second = _findings(TWO_VALUES, INTEGER_AGE)
    assert (first.severity, first.focus, first.message) == (second.severity, second.focus, second.message)
    assert first.message == "Value is not Literal with datatype xsd:integer [shape: https://example.test/Age]"
    assert first.evidence is not None
    assert second.evidence is not None
    assert [first.evidence["value"], second.evidence["value"]] == ['"x"', '"y"']
    for evidence in (first.evidence, second.evidence):
        assert evidence["resultPath"] == f"{EX}age"
        assert evidence["sourceConstraintComponent"] == _component("Datatype")
        assert evidence["sourceShape"] == f"{EX}Age"


@pytest.mark.parametrize("fmt", ["json", "sarif"])
def test_the_evidence_reaches_json_and_sarif(tmp_path: Path, capsys: pytest.CaptureFixture[str], fmt: str) -> None:
    document = _cli(tmp_path, capsys, TWO_VALUES.removeprefix(PREFIXES), INTEGER_AGE.removeprefix(PREFIXES), fmt)
    assert [e["value"] for e in _reported_evidence(document, fmt)] == ['"x"', '"y"']


def test_text_output_is_unchanged_by_the_evidence(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data_file, shapes_file = _files(tmp_path, TWO_VALUES.removeprefix(PREFIXES), INTEGER_AGE.removeprefix(PREFIXES))
    assert main([data_file, "--shapes", shapes_file, "--select", "SHACL001", "--fail-on", "never"]) == 0
    text = capsys.readouterr().out
    assert '"x"' not in text
    assert "evidence" not in text
    assert text.count("Value is not Literal with datatype xsd:integer") == len(["x", "y"])


# --- one fixture per constraint component family ------------------------------------------------------


def _expected(focus: str, shape: str, component: str, message: str, **extra: str) -> dict[str, object]:
    """The evidence of a result, in key order; ``extra`` holds ``resultPath`` and ``value`` when present."""
    evidence: dict[str, object] = {"focusNode": focus}
    for key in ("resultPath", "value"):
        if key in extra:
            evidence[key] = extra[key]
    evidence |= {"sourceShape": shape, "sourceConstraintComponent": _component(component)}
    if "sourceConstraint" in extra:
        evidence["sourceConstraint"] = extra["sourceConstraint"]
    return evidence | {"resultMessage": (message,), "resultSeverity": extra.get("resultSeverity", VIOLATION)}


A = f"{EX}a"
PROPERTY = f"{ON_T} sh:property ex:P . ex:P sh:path ex:"
FAMILIES: dict[str, tuple[str, str, list[dict[str, object]]]] = {
    # value type
    "datatype": (
        'ex:a a ex:T ; ex:age "x" .',
        f"{PROPERTY}age ; sh:datatype xsd:integer .",
        [
            _expected(
                A,
                f"{EX}P",
                "Datatype",
                "Value is not Literal with datatype xsd:integer",
                resultPath=f"{EX}age",
                value='"x"',
            )
        ],
    ),
    "class": (
        "ex:a a ex:T ; ex:knows ex:b .",
        f"{PROPERTY}knows ; sh:class ex:Person .",
        [
            _expected(
                A,
                f"{EX}P",
                "Class",
                "Value does not have class ex:Person",
                resultPath=f"{EX}knows",
                value=f"{EX}b",
            )
        ],
    ),
    # cardinality: no value to point at
    "minCount": (
        "ex:a a ex:T .",
        f"{PROPERTY}name ; sh:minCount 1 .",
        [_expected(A, f"{EX}P", "MinCount", "Less than 1 values on ex:a->ex:name", resultPath=f"{EX}name")],
    ),
    "maxCount": (
        'ex:a a ex:T ; ex:name "n", "m" .',
        f"{PROPERTY}name ; sh:maxCount 1 .",
        [_expected(A, f"{EX}P", "MaxCount", "More than 1 values on ex:a->ex:name", resultPath=f"{EX}name")],
    ),
    # property pair
    "lessThan": (
        "ex:a a ex:T ; ex:start 5 ; ex:end 3 .",
        f"{PROPERTY}start ; sh:lessThan ex:end .",
        [
            _expected(
                A,
                f"{EX}P",
                "LessThan",
                'Value of ex:a->ex:end <= Literal("5", datatype=xsd:integer)',
                resultPath=f"{EX}start",
                value=f'"5"^^<{XSD_INTEGER}>',
            )
        ],
    ),
    "equals": (
        "ex:a a ex:T ; ex:start 5 ; ex:end 5, 6 .",
        f"{PROPERTY}start ; sh:equals ex:end .",
        [
            _expected(
                A,
                f"{EX}P",
                "Equals",
                'Value of ex:a->ex:end != Literal("6", datatype=xsd:integer)',
                resultPath=f"{EX}start",
                value=f'"6"^^<{XSD_INTEGER}>',
            )
        ],
    ),
    "disjoint": (
        "ex:a a ex:T ; ex:start 5 ; ex:end 5 .",
        f"{PROPERTY}start ; sh:disjoint ex:end .",
        [
            _expected(
                A,
                f"{EX}P",
                "Disjoint",
                'Value of ex:a->ex:end == Literal("5", datatype=xsd:integer)',
                resultPath=f"{EX}start",
                value=f'"5"^^<{XSD_INTEGER}>',
            )
        ],
    ),
    # logical: the value is the focus node itself, and there is no path
    "or": (
        "ex:a a ex:T .",
        f"{ON_T} sh:or ( ex:F ex:B ) . ex:F sh:class ex:Foo . ex:B sh:class ex:Bar .",
        [_expected(A, f"{EX}S", "Or", "Node ex:a must conform to one or more shapes in ex:F , ex:B", value=A)],
    ),
    "not": (
        "ex:a a ex:T , ex:Foo .",
        f"{ON_T} sh:not ex:F . ex:F sh:class ex:Foo .",
        [_expected(A, f"{EX}S", "Not", "Node ex:a must not conform to shape ex:F", value=A)],
    ),
    "xone": (
        "ex:a a ex:T , ex:Foo , ex:Bar .",
        f"{ON_T} sh:xone ( ex:F ex:B ) . ex:F sh:class ex:Foo . ex:B sh:class ex:Bar .",
        [_expected(A, f"{EX}S", "Xone", "Node ex:a must conform to exactly one shape in ex:F , ex:B", value=A)],
    ),
    # SPARQL-based: the constraint node is named, and ?value is bound
    "sparql": (
        "ex:a a ex:T ; ex:start 5 .",
        f'{ON_T} sh:sparql ex:Big . ex:Big sh:message "Start of {{$this}} too big" ; sh:select '
        '"SELECT $this ?value WHERE { $this <https://example.test/start> ?value . FILTER(?value > 1) }" .',
        [
            _expected(
                A,
                f"{EX}S",
                "SPARQL",
                "Start of https://example.test/a too big",
                value=f'"5"^^<{XSD_INTEGER}>',
                sourceConstraint=f"{EX}Big",
            )
        ],
    ),
}


@pytest.mark.parametrize("family", FAMILIES)
def test_each_constraint_family_keeps_its_result_fields(family: str) -> None:
    data, shapes, expected = FAMILIES[family]
    evidence = _evidence(data, shapes)
    assert evidence == expected
    assert [list(e or {}) for e in evidence] == [list(e) for e in expected]  # key order too


def test_a_value_that_conforms_gives_no_finding() -> None:
    assert _findings('ex:a a ex:T ; ex:name "n" .', f"{PROPERTY}name ; sh:maxCount 1 .") == []


def test_a_blank_value_is_named_by_its_stable_identity_in_the_data_graph() -> None:
    data, shapes = _graphs("ex:a a ex:T ; ex:knows [ ex:x 1 ] .", f"{PROPERTY}knows ; sh:nodeKind sh:IRI .")
    (finding,) = Linter(data, shapes).execute(["SHACL001"]).findings
    blank = next(data.objects(URIRef(A), URIRef(f"{EX}knows")))
    assert finding.evidence is not None
    assert finding.evidence["value"] == stable_blank_id(data, blank)
    assert str(finding.evidence["value"]).startswith("_:")
    assert len(str(finding.evidence["value"])) == len("_:") + 12
    assert finding.evidence["sourceConstraintComponent"] == _component("NodeKind")


def test_a_custom_severity_keeps_its_iri_while_the_finding_is_an_error() -> None:
    (finding,) = _findings("ex:a a ex:T .", f"{PROPERTY}name ; sh:minCount 1 ; sh:severity ex:Blocker .")
    assert finding.severity == "error"
    assert finding.message.endswith("(severity https://example.test/Blocker) [shape: https://example.test/P]")
    assert finding.evidence is not None
    assert finding.evidence["resultSeverity"] == f"{EX}Blocker"


def test_every_message_is_kept_sorted_without_its_language_tag() -> None:
    (finding,) = _findings("ex:a a ex:T .", f'{PROPERTY}name ; sh:minCount 1 ; sh:message "fr"@fr, "en"@en .')
    assert finding.message == "en; fr [shape: https://example.test/P]"
    assert finding.evidence is not None
    assert finding.evidence["resultMessage"] == ("en", "fr")


def test_a_literal_focus_is_in_ntriples_in_the_evidence_and_plain_in_the_focus() -> None:
    shapes = "ex:S a sh:NodeShape ; sh:targetObjectsOf ex:p ; sh:datatype xsd:integer ."
    (finding,) = _findings('ex:a ex:p "x" .', shapes)
    assert finding.focus == "x"
    assert finding.evidence is not None
    assert finding.evidence["focusNode"] == '"x"'
    assert finding.evidence["value"] == '"x"'


def test_a_language_tagged_value_keeps_its_tag() -> None:
    (finding,) = _findings('ex:a a ex:T ; ex:age "x"@en .', f"{PROPERTY}age ; sh:datatype xsd:integer .")
    assert finding.evidence is not None
    assert finding.evidence["value"] == '"x"@en'


def test_a_multi_line_value_is_one_ntriples_term_that_parses_back() -> None:
    escaped = r'"say \"hi\"\\ok\nline 2\r"'  # the Turtle literal and its N-Triples spelling
    (finding,) = _findings(f"ex:a a ex:T ; ex:age {escaped} .", f"{PROPERTY}age ; sh:datatype xsd:integer .")
    assert finding.evidence is not None
    value = finding.evidence["value"]
    assert value == escaped
    assert isinstance(value, str)
    assert "\n" not in value
    parsed = Graph().parse(data=f"<{EX}s> <{EX}p> {value} .", format="nt")
    assert set(parsed.objects()) == {Literal('say "hi"\\ok\nline 2\r')}


# --- shape-based results: sh:node and sh:detail -------------------------------------------------------


NODE_SHAPES = f"{PROPERTY}knows ; sh:node ex:N . ex:N a sh:NodeShape ; sh:property ex:Q . "
NODE_SHAPES += "ex:Q sh:path ex:name ; sh:minCount 1 ."


def test_a_node_violation_links_the_nested_result_and_still_reports_it_alone() -> None:
    parent, nested = _findings("ex:a a ex:T ; ex:knows ex:b .", NODE_SHAPES)
    assert parent.evidence is not None
    assert nested.evidence is not None
    inner = _expected(f"{EX}b", f"{EX}Q", "MinCount", "Less than 1 values on ex:b->ex:name", resultPath=f"{EX}name")
    assert parent.evidence == {
        "focusNode": A,
        "resultPath": f"{EX}knows",
        "value": f"{EX}b",
        "sourceShape": f"{EX}P",
        "sourceConstraintComponent": _component("Node"),
        "detail": (inner,),
        "resultMessage": ("Value does not conform to Shape ex:N. See details for more information.",),
        "resultSeverity": VIOLATION,
    }
    assert nested.focus == f"{EX}b"
    assert nested.evidence == inner  # today's behaviour, kept: the nested result is a finding of its own
    (detail,) = _details(parent.evidence)
    assert detail["focusNode"] == parent.evidence["value"]


def test_nested_details_are_sorted() -> None:
    shapes = f"{PROPERTY}knows ; sh:node ex:N . ex:N a sh:NodeShape ; sh:property ex:Q, ex:R . "
    shapes += "ex:Q sh:path ex:name ; sh:minCount 1 . ex:R sh:path ex:age ; sh:minCount 1 ."
    for _ in range(3):
        parent = _findings("ex:a a ex:T ; ex:knows ex:b .", shapes)[0]
        assert parent.evidence is not None
        assert [d["resultPath"] for d in _details(parent.evidence)] == [f"{EX}age", f"{EX}name"]


# --- complex paths ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("( ex:child ex:parentOf )", f"<{EX}child>/<{EX}parentOf>"),
        ("[ sh:inversePath ex:parentOf ]", f"^<{EX}parentOf>"),
        ("[ sh:alternativePath ( ex:age [ sh:zeroOrMorePath ex:child ] ) ]", f"<{EX}age>|<{EX}child>*"),
        ("[ sh:oneOrMorePath ex:child ]", f"<{EX}child>+"),
        ("[ sh:zeroOrOnePath ex:child ]", f"<{EX}child>?"),
        ("( [ sh:alternativePath ( ex:a ex:b ) ] ex:c )", f"(<{EX}a>|<{EX}b>)/<{EX}c>"),
    ],
)
def test_a_complex_path_is_spelled_in_sparql_property_path_syntax(path: str, expected: str) -> None:
    (evidence,) = _evidence("ex:a a ex:T .", f"{ON_T} sh:property [ sh:path {path} ; sh:class ex:Q ; sh:minCount 1 ] .")
    assert evidence is not None
    assert evidence["resultPath"] == expected


# --- the Done-when check: every result field pySHACL writes reaches JSON and SARIF --------------------


def _local(predicate: URIRef) -> str:
    return str(predicate).removeprefix(str(SH))


def test_each_evidence_key_is_the_local_name_of_its_shacl_property() -> None:
    expected = {
        "focusNode",
        "resultPath",
        "value",
        "sourceShape",
        "sourceConstraintComponent",
        "sourceConstraint",
        "detail",
        "resultMessage",
        "resultSeverity",
    }
    assert {_local(p) for p in EVIDENCE_FIELDS} == expected
    assert all(p == SH[_local(p)] for p in EVIDENCE_FIELDS)


# SHACL-AF result annotations (SHACL Advanced Features, section 4 "Annotation Properties"): sh:resultAnnotation on
# a SPARQL-based constraint component's validators and on an sh:sparql constraint, the spec's own form. pySHACL
# 0.40.2 does not implement them, so its results hold no annotation property and these DONE_WHEN cases pass. They
# are canaries: the day a pySHACL upgrade writes ex:excess, ex:note or ex:x2 on a result, the predicates <=
# EVIDENCE_FIELDS assertion fails. Then map the annotations in adapters.shacl._FIELDS (or decide to drop them),
# update the evidence key list in README "Optional SHACL validation" and rules/external.py, and update
# test_each_evidence_key_is_the_local_name_of_its_shacl_property. A node validator does not select ?value:
# pySHACL pre-binds it to the focus node.
ANNOTATED_COMPONENT = (
    "ex:MaxStart a sh:ConstraintComponent ; sh:parameter [ sh:path ex:maxStart ] ;\n"
    '  sh:nodeValidator [ a sh:SPARQLSelectValidator ; sh:message "Start too big {?excess}" ;\n'
    '    sh:select "SELECT $this ?excess WHERE { $this <https://example.test/start> ?s . '
    'FILTER(?s > $maxStart) BIND(?s - $maxStart AS ?excess) }" ;\n'
    "    sh:resultAnnotation [ a sh:ResultAnnotation ; sh:annotationProperty ex:excess ; "
    'sh:annotationVarName "excess" ] ,\n'
    '      [ a sh:ResultAnnotation ; sh:annotationProperty ex:note ; sh:annotationValue "fixed" ] ] ;\n'
    '  sh:propertyValidator [ a sh:SPARQLSelectValidator ; sh:message "Value too big {?excess}" ;\n'
    '    sh:select "SELECT $this ?value ?excess WHERE { $this $PATH ?value . '
    'FILTER(?value > $maxStart) BIND(?value - $maxStart AS ?excess) }" ;\n'
    "    sh:resultAnnotation [ a sh:ResultAnnotation ; sh:annotationProperty ex:excess ; "
    'sh:annotationVarName "excess" ] ] .\n'
)
ANNOTATED_NODE_VALIDATOR = f"{ANNOTATED_COMPONENT}{ON_T} ex:maxStart 3 ."
ANNOTATED_PROPERTY_VALIDATOR = f"{ANNOTATED_COMPONENT}{ON_T} sh:property [ sh:path ex:start ; ex:maxStart 4 ] ."
ANNOTATED_SPARQL = (
    f'{ON_T} sh:sparql [ a sh:SPARQLConstraint ; sh:message "Start {{?x}}" ;\n'
    '  sh:select "SELECT $this ?x WHERE { $this <https://example.test/start> ?x }" ;\n'
    '  sh:resultAnnotation [ a sh:ResultAnnotation ; sh:annotationProperty ex:x2 ; sh:annotationVarName "x" ] ] .'
)
START = "ex:a a ex:T ; ex:start 5 ."

DONE_WHEN = {
    **{name: (data, shapes) for name, (data, shapes, _expected) in FAMILIES.items()},
    "node": ("ex:a a ex:T ; ex:knows ex:b .", NODE_SHAPES),
    "path": ("ex:a a ex:T .", f"{ON_T} sh:property [ sh:path [ sh:inversePath ex:p ] ; sh:minCount 1 ] ."),
    "blank value": ("ex:a a ex:T ; ex:knows [ ex:x 1 ] .", f"{PROPERTY}knows ; sh:nodeKind sh:IRI ."),
    "annotated node validator": (START, ANNOTATED_NODE_VALIDATOR),
    "annotated property validator": (START, ANNOTATED_PROPERTY_VALIDATOR),
    "annotated SPARQL constraint": (START, ANNOTATED_SPARQL),
}


@pytest.mark.parametrize("fmt", ["json", "sarif"])
@pytest.mark.parametrize("case", DONE_WHEN)
def test_every_result_property_in_the_report_reaches_the_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], case: str, fmt: str
) -> None:
    """Both ways: pySHACL writes no property SHACL001 drops, and each result's properties are its evidence keys."""
    data, shapes = DONE_WHEN[case]
    data_graph, shapes_graph = _graphs(data, shapes)
    _conforms, report, _text = pyshacl.validate(data_graph, shacl_graph=shapes_graph, inference="none", advanced=True)
    assert isinstance(report, Graph)
    raw: Counter[frozenset[str]] = Counter()
    for result in report.subjects(RDF.type, SH.ValidationResult):
        predicates = {p for p in report.predicates(result) if p != RDF.type}
        assert predicates <= EVIDENCE_FIELDS, predicates - EVIDENCE_FIELDS
        raw[frozenset(_local(p) for p in predicates if isinstance(p, URIRef))] += 1
    reported = Counter(frozenset(e) for e in _reported_evidence(_cli(tmp_path, capsys, data, shapes, fmt), fmt))
    assert raw
    assert reported == raw


def test_a_result_of_an_annotated_validator_keeps_its_component_and_raw_message() -> None:
    """No annotation reaches the result (pySHACL 0.40.2), and the message is the validator's, unsubstituted."""
    (finding,) = _findings(START, ANNOTATED_NODE_VALIDATOR)
    assert finding.message == "Start too big {?excess} [shape: https://example.test/S]"
    assert finding.evidence == {
        "focusNode": A,
        "value": A,
        "sourceShape": f"{EX}S",
        "sourceConstraintComponent": f"{EX}MaxStart",
        "resultMessage": ("Start too big {?excess}",),
        "resultSeverity": VIOLATION,
    }


# --- deterministic order and naming -------------------------------------------------------------------


def _result(report: Graph, value: str) -> BNode:
    node = BNode()
    report.add((node, RDF.type, SH.ValidationResult))
    report.add((node, SH.focusNode, URIRef(A)))
    report.add((node, SH.value, Literal(value)))
    report.add((node, SH.resultMessage, Literal("Bad value")))
    report.add((node, SH.sourceShape, URIRef(f"{EX}S")))
    return node


def _fake_validate(report: Graph) -> Callable[..., tuple[bool, Graph, str]]:
    def validate(*args: object, **kwargs: object) -> tuple[bool, Graph, str]:
        return False, report, ""

    return validate


def _issues(monkeypatch: pytest.MonkeyPatch, report: Graph, data: Graph | None = None) -> list[Finding]:
    monkeypatch.setattr(pyshacl, "validate", _fake_validate(report))
    return shacl_issues(Graph() if data is None else data, Graph())


def test_tied_findings_come_out_in_one_order_whatever_the_report_order(monkeypatch: pytest.MonkeyPatch) -> None:
    forward, backward = Graph(), Graph()
    for value in ("y", "x", "z"):
        _result(forward, value)
    for value in ("z", "x", "y"):
        _result(backward, value)
    first = [f.evidence for f in _issues(monkeypatch, forward)]
    second = [f.evidence for f in _issues(monkeypatch, backward)]
    assert [e["value"] for e in first if e is not None] == ['"x"', '"y"', '"z"']
    assert first == second


def test_tied_findings_sort_by_path_before_value_and_by_code_point(monkeypatch: pytest.MonkeyPatch) -> None:
    """Evidence orders in field order (path, then value), and a non-ASCII character after every ASCII one."""
    report = Graph()
    for path, value in (("q", "a"), ("p", "z"), ("p", "é")):
        node = _result(report, value)
        report.add((node, SH.resultPath, URIRef(f"{EX}{path}")))
    evidence = [f.evidence for f in _issues(monkeypatch, report)]
    assert [(e["resultPath"], e["value"]) for e in evidence if e is not None] == [
        (f"{EX}p", '"z"'),
        (f"{EX}p", '"é"'),
        (f"{EX}q", '"a"'),
    ]


def test_tied_findings_sort_by_value_before_constraint_component(monkeypatch: pytest.MonkeyPatch) -> None:
    """Field order, not key order: ``value`` comes before ``sourceConstraintComponent``."""
    report = Graph()
    for value, component in (("b", "A"), ("a", "Z")):
        node = _result(report, value)
        report.add((node, SH.sourceConstraintComponent, URIRef(f"{EX}{component}")))
    evidence = [f.evidence for f in _issues(monkeypatch, report)]
    assert [e["value"] for e in evidence if e is not None] == ['"a"', '"b"']


def test_findings_sort_by_focus_and_message_before_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    report = Graph()
    late = _result(report, "a")
    report.set((late, SH.focusNode, URIRef(f"{EX}b")))
    early = _result(report, "b")
    report.set((early, SH.resultMessage, Literal("A message")))
    _result(report, "c")
    findings = _issues(monkeypatch, report)
    assert [(f.focus, f.message.split(" [")[0]) for f in findings] == [
        (A, "A message"),
        (A, "Bad value"),
        (f"{EX}b", "Bad value"),
    ]


def test_json_bytes_do_not_depend_on_the_hash_seed(tmp_path: Path) -> None:
    """pySHACL's own result order changes with PYTHONHASHSEED: on this input, seeds 1 and 2 give opposite orders."""
    data, shapes = _files(tmp_path, TWO_VALUES.removeprefix(PREFIXES), INTEGER_AGE.removeprefix(PREFIXES))
    command = [sys.executable, "-m", "ontolint", data, "--shapes", shapes, "--select", "SHACL001", "--format", "json"]

    def run(seed: int) -> bytes:
        env = {**os.environ, "PYTHONHASHSEED": str(seed)}
        done = subprocess.run(command, capture_output=True, check=False, env=env, cwd=tmp_path)  # noqa: S603
        assert done.returncode == 1, done.stderr
        return done.stdout

    assert run(1) == run(2)


def test_blank_shapes_constraints_and_values_have_the_same_evidence_on_every_parse() -> None:
    data = "ex:a a ex:T ; ex:knows [ ex:x 1 ] ; ex:start 5 ."
    shapes = f"{ON_T} sh:property [ sh:path ex:knows ; sh:nodeKind sh:IRI ] ; "
    shapes += 'sh:sparql [ sh:select "SELECT $this ?value WHERE { $this <https://example.test/start> ?value }" ] .'
    first, second = _evidence(data, shapes), _evidence(data, shapes)
    assert first == second
    by_component = {str(e["sourceConstraintComponent"]): e for e in first if e is not None}
    kind, sparql = by_component[_component("NodeKind")], by_component[_component("SPARQL")]
    blanks = [kind["value"], kind["sourceShape"], sparql["sourceConstraint"]]
    assert all(str(name).startswith("_:") for name in blanks), blanks


# --- bounded walks over a report that is input like any other graph -----------------------------------


def _path_result(report: Graph, path: Node) -> None:
    node = _result(report, "v")
    report.add((node, SH.resultPath, path))


def _path_of(monkeypatch: pytest.MonkeyPatch, report: Graph) -> object:
    (finding,) = _issues(monkeypatch, report)
    assert finding.evidence is not None
    return finding.evidence["resultPath"]


def _inverse_chain(report: Graph, depth: int) -> BNode:
    """A path ``^^…^<p>`` whose constructors nest ``depth`` deep."""
    head = node = BNode()
    for _ in range(depth - 1):
        inner = BNode()
        report.add((node, SH.inversePath, inner))
        node = inner
    report.add((node, SH.inversePath, URIRef(f"{EX}p")))
    return head


def test_a_blank_path_without_structure_is_malformed(monkeypatch: pytest.MonkeyPatch) -> None:
    report = Graph()
    _path_result(report, BNode())
    assert _path_of(monkeypatch, report) == MALFORMED_PATH


def test_a_literal_path_is_malformed(monkeypatch: pytest.MonkeyPatch) -> None:
    report = Graph()
    _path_result(report, Literal("p"))
    assert _path_of(monkeypatch, report) == MALFORMED_PATH


def test_a_sequence_of_one_path_is_malformed(monkeypatch: pytest.MonkeyPatch) -> None:
    report, cell = Graph(), BNode()
    report.add((cell, RDF.first, URIRef(f"{EX}p")))
    report.add((cell, RDF.rest, RDF.nil))
    _path_result(report, cell)
    assert _path_of(monkeypatch, report) == MALFORMED_PATH


def test_a_cyclic_path_is_malformed_without_recursing(monkeypatch: pytest.MonkeyPatch) -> None:
    report, loop = Graph(), BNode()
    report.add((loop, SH.inversePath, loop))
    _path_result(report, loop)
    assert _path_of(monkeypatch, report) == MALFORMED_PATH


def test_a_cyclic_sequence_is_malformed(monkeypatch: pytest.MonkeyPatch) -> None:
    report, first, second = Graph(), BNode(), BNode()
    report.add((first, RDF.first, URIRef(f"{EX}p")))
    report.add((first, RDF.rest, second))
    report.add((second, RDF.first, URIRef(f"{EX}q")))
    report.add((second, RDF.rest, first))
    _path_result(report, first)
    assert _path_of(monkeypatch, report) == MALFORMED_PATH


@pytest.mark.parametrize(("depth", "renders"), [(MAX_PATH_DEPTH, True), (MAX_PATH_DEPTH + 1, False), (40, False)])
def test_a_path_deeper_than_the_bound_is_malformed(monkeypatch: pytest.MonkeyPatch, depth: int, renders: bool) -> None:
    report = Graph()
    _path_result(report, _inverse_chain(report, depth))
    expected = "^" * depth + f"<{EX}p>" if renders else MALFORMED_PATH
    assert _path_of(monkeypatch, report) == expected


def _sequence(report: Graph, items: list[Node]) -> BNode:
    head = BNode()
    cell: Node = head
    for index, item in enumerate(items):
        report.add((cell, RDF.first, item))
        tail = RDF.nil if index == len(items) - 1 else BNode()
        report.add((cell, RDF.rest, tail))
        cell = tail
    return head


@pytest.mark.parametrize(
    ("inverse", "length", "size"),
    [(True, (MAX_PATH_SIZE - 2) // 2, MAX_PATH_SIZE), (False, (MAX_PATH_SIZE + 1) // 2, MAX_PATH_SIZE + 1)],
)
def test_a_path_larger_than_the_bound_is_malformed(
    monkeypatch: pytest.MonkeyPatch, inverse: bool, length: int, size: int
) -> None:
    """A sequence of ``n`` predicates walks ``2n + 1`` nodes (cells, items, ``rdf:nil``), its inverse one more."""
    report = Graph()
    path = _sequence(report, [URIRef(f"{EX}p{i}") for i in range(length)])
    if inverse:
        wrapper = BNode()
        report.add((wrapper, SH.inversePath, path))
        path = wrapper
    _path_result(report, path)
    assert 2 * length + 1 + inverse == size
    text = _path_of(monkeypatch, report)
    if size <= MAX_PATH_SIZE:
        assert str(text).startswith("^(")
        assert str(text).count(">/<") == length - 1
    else:
        assert text == MALFORMED_PATH


def test_a_shared_part_counts_each_time_so_a_path_cannot_grow_exponentially(monkeypatch: pytest.MonkeyPatch) -> None:
    report = Graph()
    node: Node = URIRef(f"{EX}p")
    for _ in range(12):  # each level is the sequence (below, below): 2**12 leaves, 12 levels deep
        node = _sequence(report, [node, node])
    _path_result(report, node)
    assert _path_of(monkeypatch, report) == MALFORMED_PATH


def test_a_path_missing_from_the_report_is_read_from_the_shapes_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    report, shapes, path = Graph(), Graph(), BNode()
    shapes.add((path, SH.inversePath, URIRef(f"{EX}p")))
    _path_result(report, path)
    monkeypatch.setattr(pyshacl, "validate", _fake_validate(report))
    (finding,) = shacl_issues(Graph(), shapes)
    assert finding.evidence is not None
    assert finding.evidence["resultPath"] == f"^<{EX}p>"


def test_a_detail_pointing_back_to_its_result_is_not_followed(monkeypatch: pytest.MonkeyPatch) -> None:
    report = Graph()
    node = _result(report, "v")
    report.add((node, SH.detail, node))
    (finding,) = _issues(monkeypatch, report)
    assert finding.evidence is not None
    assert "detail" not in finding.evidence


def _detail_chain(report: Graph, length: int) -> None:
    """``length`` results, each the ``sh:detail`` of the one before; the first is about ``ex:a``."""
    above = _result(report, "0")
    for index in range(1, length):
        below = _result(report, str(index))
        report.set((below, SH.focusNode, URIRef(f"{EX}n{index}")))
        report.add((above, SH.detail, below))
        above = below


def _nesting(evidence: Evidence) -> int:
    depth = 0
    while "detail" in evidence:
        (evidence,) = _details(evidence)
        depth += 1
    return depth


@pytest.mark.parametrize(
    ("length", "nested"),
    [(MAX_DETAIL_DEPTH, MAX_DETAIL_DEPTH - 1), (MAX_DETAIL_DEPTH + 1, MAX_DETAIL_DEPTH), (10, MAX_DETAIL_DEPTH)],
)
def test_details_nest_at_most_the_bound_deep(monkeypatch: pytest.MonkeyPatch, length: int, nested: int) -> None:
    report = Graph()
    _detail_chain(report, length)
    findings = _issues(monkeypatch, report)
    assert len(findings) == length  # every nested result is still a finding of its own
    (top,) = [f for f in findings if f.focus == A]
    assert top.evidence is not None
    assert _nesting(top.evidence) == nested


# --- the structured identity BASELINE-V2 builds on ----------------------------------------------------


def test_the_result_key_names_shape_component_path_value_and_constraint() -> None:
    first, second = _findings(TWO_VALUES, INTEGER_AGE)
    assert first.evidence is not None
    assert second.evidence is not None
    keys = [shacl_result_key(first.evidence), shacl_result_key(second.evidence)]
    common = (f"{EX}Age", _component("Datatype"), f"{EX}age")
    assert keys == [(*common, '"x"', ""), (*common, '"y"', "")]
    assert [first.subject, second.subject] == keys  # the finding's identity beyond rule and focus


def test_the_result_key_leaves_missing_or_nested_parts_empty() -> None:
    assert shacl_result_key({}) == ("", "", "", "", "")
    detail: Evidence = {"value": ("a", "b"), "sourceConstraint": "c", "sourceShape": "s", "focusNode": "f"}
    assert shacl_result_key(detail) == ("s", "", "", "", "c")


# --- findings without evidence ------------------------------------------------------------------------


def test_a_report_without_result_nodes_gives_one_finding_without_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    (finding,) = _issues(monkeypatch, Graph())
    assert finding.focus == "(shapes)"
    assert finding.evidence is None


def test_conforming_data_gives_no_finding() -> None:
    assert _findings("ex:a a ex:T ; ex:age 3 .", INTEGER_AGE.removeprefix(PREFIXES)) == []


@pytest.mark.parametrize("fmt", ["json", "sarif"])
def test_findings_of_other_rules_carry_no_evidence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], fmt: str
) -> None:
    ttl = tmp_path / "a.ttl"
    ttl.write_text(f"<{EX}A> a <http://www.w3.org/2002/07/owl#Class> .\n", encoding="utf-8")
    assert main([str(ttl), "--format", fmt, "--fail-on", "never"]) == 0
    document = json.loads(capsys.readouterr().out)
    entries = (
        document["findings"] if fmt == "json" else [r.get("properties", {}) for r in document["runs"][0]["results"]]
    )
    assert entries
    assert all("evidence" not in entry for entry in entries)
