"""OWL026 reports a sameAs/differentFrom clash once, however many ways the pair is stated."""

from __future__ import annotations

from rule_harness import graph

from ontolint import Linter


def test_a_different_from_pair_stated_both_ways_is_reported_once() -> None:
    turtle = "ex:a owl:differentFrom ex:b . ex:b owl:differentFrom ex:a . ex:a owl:sameAs ex:b ."

    result = Linter(graph(turtle)).execute(["OWL026"])

    assert [f.rule for f in result.findings] == ["OWL026"]
    assert result.findings[0].focus == "https://example.test/onto#a"
