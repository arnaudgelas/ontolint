"""Meta-tests: every implemented rule has positive and negative cases, and every case holds.

Add rule cases in ``tests/rule_cases/<family>.py`` (see ``tests/rule_harness.py``); nothing here
needs editing when a rule is added.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from rdflib import BNode, Graph
from rule_cases import load_cases
from rule_harness import ODD_INPUTS, ODD_SHAPES, Case, chain_turtle, graph

from ontolint import Linter
from ontolint.models import ExecutionStatus
from ontolint.rules.builtin import RULE_MODULES, module_name
from ontolint.rules.registry import default_registry

CASES = load_cases()
PYTHON_REPR = re.compile(r"rdflib\.|\b(?:Literal|URIRef|BNode)\(")
IMPLEMENTED = sorted(spec.rule_id for spec in default_registry().all())


def _params(kind: str) -> list[Any]:
    return [
        pytest.param(rule_id, case, id=f"{rule_id}-{case.name}")
        for rule_id in sorted(CASES)
        for case in getattr(CASES[rule_id], kind)
    ]


def test_every_implemented_rule_has_positive_and_negative_cases() -> None:
    missing = {
        rule_id: [kind for kind in ("positive", "negative") if not getattr(CASES.get(rule_id), kind, ())]
        for rule_id in IMPLEMENTED
    }
    missing = {rule_id: kinds for rule_id, kinds in missing.items() if kinds}
    assert not missing, f"rules without dedicated cases in tests/rule_cases/*.py: {missing}"


def test_cases_exist_only_for_implemented_rules() -> None:
    assert sorted(set(CASES) - set(IMPLEMENTED)) == [], "proposed rules must flip to implemented before gaining cases"


@pytest.mark.parametrize(("rule_id", "case"), _params("positive"))
def test_positive_case_emits_exactly_the_rule(rule_id: str, case: Case) -> None:
    emitted = case.emitted(rule_id)
    assert emitted, f"{rule_id} did not fire on {case.name!r}"
    assert set(emitted) == {rule_id}


@pytest.mark.parametrize(("rule_id", "case"), _params("negative"))
def test_negative_case_does_not_emit_the_rule(rule_id: str, case: Case) -> None:
    assert rule_id not in case.emitted(rule_id)


@pytest.mark.parametrize(
    ("rule_id", "case"), [p for p in _params("positive") + _params("negative") if not p.values[1].probe]
)
def test_cases_neither_crash_nor_print_python_reprs_under_a_full_run(rule_id: str, case: Case) -> None:
    data = case.build() if case.build else graph(case.turtle)
    shapes = graph(case.shapes) if case.shapes is not None else None
    result = Linter(data, shapes, **case.options).execute()
    # Shape-authoring rules inspect malformed shapes that pySHACL may reject (a recorded SHACL001 failure).
    failed = {x.rule_id for x in result.with_status(ExecutionStatus.FAILED)}
    assert failed <= {"SHACL001"}, failed
    # Messages and foci print RDF terms (``support.term_text``), never ``rdflib.term.Literal('x')``.
    reprs = [(f.rule, text) for f in result.findings for text in (f.focus, f.message) if PYTHON_REPR.search(text)]
    assert not reprs, reprs


@pytest.mark.parametrize(
    ("rule_id", "case"), [p for p in _params("positive") + _params("negative") if not p.values[1].probe]
)
def test_cases_never_print_a_parsers_blank_node_label(rule_id: str, case: Case) -> None:
    # A message names a blank node by its content (``_:`` and 12 hex digits): a rule writes it ``_:label``
    # (``support.value_text``), the only spelling rewritten, so a node printed with ``str()`` leaves the parser's
    # label (32 hex digits, never a word of a message) in the text (#54).  Every rule runs, opt-in ones included,
    # so a case with a blank value guards the message of each rule it reaches.
    data = case.build() if case.build else graph(case.turtle)
    shapes = graph(case.shapes) if case.shapes is not None else None
    labels = {str(n) for g in (data, shapes) if g is not None for t in g for n in t if isinstance(n, BNode)}
    findings = Linter(data, shapes, **case.options).execute(IMPLEMENTED).findings
    leaks = [(f.rule, text) for f in findings for text in (f.focus, f.message) if any(x in text for x in labels)]
    assert not leaks, leaks


# --- odd inputs ------------------------------------------------------------------------------


def _assert_no_module_failed(data: Graph, shapes: Graph | None, **options: Any) -> None:
    linter = Linter(data, shapes, **options)
    assert isinstance(linter.run(), list)
    result = Linter(data, shapes, **options).execute()
    # pySHACL may legitimately reject a malformed shapes graph; that is a recorded SHACL001 failure.
    failed = {x.rule_id for x in result.with_status(ExecutionStatus.FAILED)}
    assert failed <= {"SHACL001"}, failed


@pytest.mark.parametrize("name", ODD_INPUTS)
def test_odd_inputs_never_crash_any_rule(name: str) -> None:
    for options in ({}, {"base": "https://example.test/onto#", "languages": ("en", "fr")}):
        _assert_no_module_failed(ODD_INPUTS[name](), graph(ODD_SHAPES["blank and literal shape structure"]), **options)


@pytest.mark.parametrize("name", ODD_SHAPES)
def test_odd_shapes_never_crash_the_shape_rules(name: str) -> None:
    _assert_no_module_failed(graph("ex:A a owl:Class . ex:i a ex:A ."), graph(ODD_SHAPES[name]))


@pytest.mark.parametrize("module", RULE_MODULES, ids=module_name)
def test_each_module_tolerates_an_empty_graph_without_findings_from_other_modules(module: Any) -> None:
    linter = Linter(Graph())
    module.run(linter.rule_context)
    declared = {spec.rule_id for spec in module.SPECS}
    assert {f.rule for f in linter.rule_context.findings} <= declared


# --- scale -----------------------------------------------------------------------------------


@pytest.mark.parametrize("size", [2_000, 20_000])
def test_long_hierarchies_neither_recurse_nor_crash(size: int) -> None:
    result = Linter(graph(chain_turtle(size)), depth_limit=7).execute()
    assert not result.with_status(ExecutionStatus.FAILED)
    assert {f.rule for f in result.findings} >= {"CLS005", "CLS007"}


@pytest.mark.parametrize("size", [2_000])
def test_long_broader_cycles_are_found_without_recursion(size: int) -> None:
    turtle = chain_turtle(size, "skos:broader", "skos:Concept") + f"\nex:n{size - 1} skos:broader ex:n0 ."
    result = Linter(graph(turtle)).execute(["SKOS003"])
    assert [f.rule for f in result.findings] == ["SKOS003"]
