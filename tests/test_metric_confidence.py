"""A METRIC finding is ``certain`` exactly when its rule's category is ``deterministic`` (issue #63, #183).

METRIC001-METRIC013 have the category ``heuristic`` (each limit is a convention), so none may report a finding with
confidence ``certain``; METRIC014 (a quality budget the policy declared) is ``deterministic`` and always ``certain``.
A category and a confidence that disagree tell a consumer two things about one finding.  METRIC011 was the exception
(an exact count against a conventional limit of ten, and one false positive on the calibration corpus); the decision
of #63 made its findings ``heuristic`` like the rest.

The invariant is checked for the METRIC family only, on the positive cases of ``tests/rule_cases``.  Other families
still have rules whose category is ``heuristic`` and whose findings are ``certain`` (``docs/severity-decisions.md``,
"What the decisions leave open"): the check widens when the catalogue is aligned.
"""

from __future__ import annotations

import pytest
from rule_cases import load_cases
from rule_harness import Case, graph

from ontolint import Linter
from ontolint.rules.specs import RULE_SPECS

FAMILY = "METRIC"
SPECS = {spec.rule_id: spec for spec in RULE_SPECS if spec.family == FAMILY}
CASES = load_cases()
POSITIVES = [
    pytest.param(rule_id, case, id=f"{rule_id}:{case.name}")
    for rule_id in sorted(SPECS)
    for case in (CASES[rule_id].positive if rule_id in CASES else ())
    if case.probe is None
]


def test_the_threshold_rules_are_heuristic_and_the_budget_rule_deterministic() -> None:
    assert {spec.category for rule_id, spec in SPECS.items() if rule_id != "METRIC014"} == {"heuristic"}
    assert SPECS["METRIC014"].category == "deterministic"


def test_every_registered_metric_rule_has_a_positive_case_this_invariant_runs() -> None:
    """A new METRIC rule without a positive case fails here instead of escaping the check."""
    assert {param.values[0] for param in POSITIVES} == set(SPECS)


@pytest.mark.parametrize(("rule_id", "case"), POSITIVES)
def test_confidence_follows_the_category(rule_id: str, case: Case) -> None:
    data = case.build() if case.build else graph(case.turtle)
    findings = Linter(data, **case.options).execute([rule_id]).findings
    assert findings
    expected = "certain" if SPECS[rule_id].category == "deterministic" else "heuristic"
    assert {f.confidence for f in findings} == {expected}
