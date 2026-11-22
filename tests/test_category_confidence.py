"""A ``deterministic`` rule never reports a ``heuristic`` finding (issue #180, step one of the catalogue alignment).

``category`` is the rule's claim, in the catalogue, ``--list-rules``, ``--explain`` and the SARIF rule properties;
``confidence`` is the finding's, in the JSON report and the SARIF results.  A rule that calls itself deterministic while
its findings say ``heuristic`` tells a consumer two things about one finding (``docs/severity-decisions.md``, fact 4).

This is the one-direction check of every family.  The other direction (a ``heuristic`` rule whose findings are
``certain``: OWL004, OWL007, OWL009, OWL010, OWL013, OWL014, CLS003, CLS004, CLS014, CLS019, IRI001, ...) is aligned
family by family, and ``tests/test_metric_confidence.py`` checks the METRIC family both ways.  A ``context-dependent``
rule (FAIR, OBO, ALIGN009) makes no claim this test can hold it to.

The other direction is held for the rules in ``ALIGNED``: each reports ``certain`` findings and is
``deterministic``, because its condition is exact and the cited specification forbids the pattern or gives it a
fixed meaning (decision D1 of ``docs/severity-decisions.md``). A rule joins the list when its row is decided. The
rules that report ``certain`` on a convention (IRI006, IRI010, IRI012, IRI016, IRI017, IRI018, LEX001, LEX002,
LEX005, LEX011, LEX019, LEX025) are not on it: D1 would make their findings ``heuristic``, a change for consumers
that filter on confidence, left to the maintainer.

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


ALIGNED = (
    # OWL 2 DL violations and exact axiom conditions (the decisions of #63)
    "OWL003",
    "OWL004",
    "OWL007",
    "OWL009",
    "OWL010",
    "OWL013",
    "OWL014",
    # classes: an unsatisfiable class, and the two conditions RDFS and OWL 2 entail
    "CLS003",
    "CLS004",
    "CLS014",
    "CLS019",
    # syntax tests against RFC 3986 and the SKOS label ranges
    "IRI001",
    "IRI009",
    "LEX014",
)
SPECS = {spec.rule_id: spec for spec in RULE_SPECS}
ALIGNED_POSITIVES = [
    pytest.param(rule_id, case, id=f"{rule_id}:{case.name}")
    for rule_id in ALIGNED
    for case in CASES[rule_id].positive
    if case.probe is None
]


@pytest.mark.parametrize("rule_id", ALIGNED)
def test_an_aligned_rule_is_deterministic(rule_id: str) -> None:
    assert SPECS[rule_id].category == "deterministic"


@pytest.mark.parametrize(("rule_id", "case"), ALIGNED_POSITIVES)
def test_an_aligned_rule_reports_only_certain_findings(rule_id: str, case: Case) -> None:
    data = case.build() if case.build else graph(case.turtle)
    shapes = graph(case.shapes) if case.shapes is not None else None
    findings = [f for f in Linter(data, shapes, **case.options).execute([rule_id]).findings if f.rule == rule_id]
    assert findings
    assert {f.confidence for f in findings} == {"certain"}
