"""A ``deterministic`` rule never reports a ``heuristic`` finding (issue #180, step one of the catalogue alignment).

``category`` is the rule's claim, in the catalogue, ``--list-rules``, ``--explain`` and the SARIF rule properties;
``confidence`` is the finding's, in the JSON report and the SARIF results.  A rule that calls itself deterministic while
its findings say ``heuristic`` tells a consumer two things about one finding (``docs/severity-decisions.md``, fact 4).

This is the one-direction check of every family.  The other direction (a ``heuristic`` rule whose findings are
``certain``: OWL004, OWL007, OWL009, OWL010, OWL013, OWL014, CLS003, CLS004, CLS014, CLS019, IRI001, ...) is aligned
family by family, and ``tests/test_metric_confidence.py`` checks the METRIC family both ways.  A ``context-dependent``
rule (FAIR, OBO, ALIGN009) makes no claim this test can hold it to.

Only the positive cases of ``tests/rule_cases`` are run, so a rule whose heuristic finding no case reaches is not seen:
the test narrows the gap, it does not close it.
"""

from __future__ import annotations

import pytest
from rule_cases import load_cases
from rule_harness import Case, graph

from ontolint import Linter
from ontolint.rules.specs import RULE_SPECS

CASES = load_cases()
DETERMINISTIC = {spec.rule_id for spec in RULE_SPECS if spec.category == "deterministic"}
RULES = sorted(DETERMINISTIC & set(CASES))
POSITIVES = [
    pytest.param(rule_id, case, id=f"{rule_id}:{case.name}")
    for rule_id in RULES
    for case in CASES[rule_id].positive
    if case.probe is None
]


def test_the_check_reaches_deterministic_rules_of_every_family() -> None:
    """A guard against the parametrisation collapsing: the rules this test runs span the families that have any."""
    families = {rule_id.rstrip("0123456789") for rule_id in RULES}
    assert {"ALIGN", "DATA", "SKOS", "SHQ", "OWL"} <= families


@pytest.mark.parametrize(("rule_id", "case"), POSITIVES)
def test_a_deterministic_rule_reports_no_heuristic_finding(rule_id: str, case: Case) -> None:
    data = case.build() if case.build else graph(case.turtle)
    shapes = graph(case.shapes) if case.shapes is not None else None
    findings = [f for f in Linter(data, shapes, **case.options).execute([rule_id]).findings if f.rule == rule_id]
    assert findings
    assert "heuristic" not in {f.confidence for f in findings}
