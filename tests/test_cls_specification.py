"""The CLS family specification (see the ``classes``, ``class_heuristics`` and ``hierarchy_quality`` docstrings).

One section per rule: each pins a condition, an exclusion, a boundary or a known gap of the rule's
specification, with the standard it rests on.  OWL 2 is the OWL 2 Structural Specification and the OWL 2 Direct
Semantics of the 2012-12-11 Recommendations, RDFS the RDF Schema 1.1 Recommendation (RDF Semantics 1.1 for the
entailment patterns) and DCAM the DCMI Abstract Model vocabulary.  A comment saying "gap" marks behaviour that
is pinned as it is today and that deviates from the standard named; changing it is a decision, not a fix.
"""

from __future__ import annotations

from rule_harness import graph

from ontolint import Linter
from ontolint.policy import Policy

NS = "https://example.test/onto#"
C = "a owl:Class"


def _foci(rule: str, turtle: str, **policy: int) -> list[str]:
    result = Linter(graph(turtle), policy=Policy(**policy)).execute([rule])
    return sorted(f.focus.removeprefix(NS) for f in result.findings)


# --- defects fixed by this specification ---------------------------------------------------------------


def test_cls014_reports_a_class_below_disjoint_classes_inside_a_subclass_cycle() -> None:
    # OWL 2 Direct Semantics 9.1.3 (DisjointClasses): A subClassOf B and A disjoint with B leave A empty, and
    # a cycle is a set of equivalent classes (9.1.2), so no member of it is exempt from the check.
    cycle = f"ex:A {C}; rdfs:subClassOf ex:B . ex:B {C}; rdfs:subClassOf ex:A ."
    assert _foci("CLS014", cycle + " ex:A owl:disjointWith ex:B .") == ["A"]
    # The disjoint pair is above the cycle: it is reported once, at the representative of the cycle.
    above = f"{cycle} ex:B rdfs:subClassOf ex:D, ex:E . ex:D {C} . ex:E {C} . ex:D owl:disjointWith ex:E ."
    assert _foci("CLS014", above) == ["A"]
    # A class below the cycle is not reported again.
    assert _foci("CLS014", cycle + " ex:A owl:disjointWith ex:B . ex:X " + C + "; rdfs:subClassOf ex:A .") == ["A"]


def test_cls019_reads_equivalent_class_in_both_directions() -> None:
    # OWL 2 Structural Specification 9.1.1: EquivalentClasses is symmetric, and the RDF triple has no direction,
    # so "owl:Nothing owl:equivalentClass ex:A" asserts ex:A equal to owl:Nothing as much as the reverse.
    assert _foci("CLS019", f"ex:A {C} ; owl:equivalentClass owl:Nothing .") == ["A"]
    assert _foci("CLS019", f"ex:A {C} . owl:Nothing owl:equivalentClass ex:A .") == ["A"]
