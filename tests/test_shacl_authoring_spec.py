"""Edge cases of the SHQ011 and SHQ018 specifications (see the ``shacl_authoring`` docstring)."""

from __future__ import annotations

import math
from decimal import Decimal

from rule_harness import graph

from ontolint import Linter
from ontolint.models import ExecutionStatus
from ontolint.rules.shacl_authoring import DOUBLE, EXACT, FLOAT, _promote, _strip_whitespace

TENTH = 0.1  # the double nearest 0.1; the float nearest 0.1 differs from it


def _messages(rule: str, body: str) -> list[str]:
    shapes = graph(f"ex:S a sh:NodeShape ; sh:targetClass ex:A ; {body} .")
    result = Linter(graph("ex:A a owl:Class ."), shapes).execute([rule])
    assert {x.status for x in result.executions} == {ExecutionStatus.EXECUTED}, result.executions
    return [f.message for f in result.findings]


def test_promotion_casts_to_the_wider_type() -> None:
    assert _promote(Decimal("0.1"), EXACT) == Decimal("0.1")
    assert _promote(Decimal("0.1"), DOUBLE) == TENTH
    assert _promote(Decimal("0.1"), FLOAT) != TENTH
    assert _promote(10**400, DOUBLE) == math.inf
    assert _promote(-(10**400), FLOAT) == -math.inf
    assert _promote(1e300, FLOAT) == math.inf
    assert _promote(-1e300, FLOAT) == -math.inf


def test_huge_integer_bound_against_a_double() -> None:
    # Regression: math.isnan(10**400) raised OverflowError and the whole rule execution failed.
    assert _messages("SHQ018", f"sh:minInclusive {10**400} ; sh:maxInclusive 1") == [
        f"Numeric bounds {10**400} and 1 admit no value."
    ]
    body = f'sh:minInclusive {10**400} ; sh:maxInclusive "1e308"^^xsd:double'
    assert _messages("SHQ018", body) == [f"Numeric bounds {10**400} and 1e+308 admit no value."]
    assert _messages("SHQ018", f'sh:minInclusive "INF"^^xsd:double ; sh:maxInclusive {10**400}') == []


def test_float_bounds_compare_at_float_precision() -> None:
    assert _messages("SHQ018", 'sh:minInclusive "0.1000000001"^^xsd:float ; sh:maxInclusive "0.1"^^xsd:float') == []
    assert _messages("SHQ018", 'sh:minInclusive "0.1"^^xsd:float ; sh:maxInclusive "0.1"^^xsd:double') == [
        "Numeric bounds 0.1 and 0.1 admit no value."
    ]


def test_x_flag_strips_whitespace_outside_classes_only() -> None:
    assert _strip_whitespace("a b\t(c)\n[ x]\\ ") == "ab(c)[ x]\\ "
    assert _strip_whitespace("[a-[ b]] c") == "[a-[ b]]c"
    assert _messages("SHQ011", 'sh:pattern "[ ]+ (" ; sh:flags "x"') != []
    assert _messages("SHQ011", 'sh:pattern "a(?i)" ; sh:flags "ii"') != []
