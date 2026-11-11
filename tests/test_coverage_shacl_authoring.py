"""SHQ011 and SHQ018: multi-digit back-references, an unclosed class, and xsd:float overflow."""

from __future__ import annotations

import pytest
from rule_harness import graph

from ontolint import Linter
from ontolint.rules.shacl_authoring import xpath_regex_problem

DATA = "ex:A a owl:Class ."
NODE = "ex:S a sh:NodeShape ; sh:targetClass ex:A ; sh:property ex:P .\nex:P sh:path ex:p ; "


def _shapes_rule(rule: str, body: str) -> list[str]:
    result = Linter(graph(DATA), graph(NODE + body + " .")).execute([rule])
    return [f.rule for f in result.findings]


def test_a_two_digit_back_reference_is_accepted() -> None:
    groups = "(a)" * 10

    assert xpath_regex_problem(groups + "\\10") is None
    assert _shapes_rule("SHQ011", f'sh:pattern "{groups}\\\\10"') == []


def test_an_unclosed_class_is_left_to_python() -> None:
    assert xpath_regex_problem("[abc") is None
    assert xpath_regex_problem("[a\\p{L}") is None  # escapes inside it are still judged, a missing ] is not
    assert _shapes_rule("SHQ011", 'sh:pattern "[abc"') == ["SHQ011"]  # and Python's compile reports it


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        # 1e39 and 1e40 both overflow xsd:float to INF, so the bounds meet at a single value...
        ('sh:minInclusive "1e39"^^xsd:float ; sh:maxInclusive "1e40"^^xsd:float', []),
        # ...which an exclusive bound leaves empty.
        ('sh:minExclusive "1e39"^^xsd:float ; sh:maxInclusive "1e40"^^xsd:float', ["SHQ018"]),
        # A negative overflow is -INF: nothing lies below it.
        ('sh:minInclusive 0 ; sh:maxInclusive "-1e39"^^xsd:float', ["SHQ018"]),
    ],
)
def test_float_overflow_is_read_as_infinity(body: str, expected: list[str]) -> None:
    assert _shapes_rule("SHQ018", body) == expected
