"""CLS021 reports an equivalence stated in both directions once."""

from __future__ import annotations

from rule_harness import graph

from ontolint import Linter


def test_an_equivalence_stated_both_ways_is_reported_once() -> None:
    turtle = (
        "ex:A a owl:Class ; rdfs:subClassOf ex:B ; owl:equivalentClass ex:B .\n"
        "ex:B a owl:Class ; owl:equivalentClass ex:A .\n"
    )

    result = Linter(graph(turtle)).execute(["CLS021"])

    assert [(f.rule, f.message) for f in result.findings] == [
        ("CLS021", "Equivalent to its asserted ancestor https://example.test/onto#B.")
    ]
