"""GOV001 stops at the list depth limit and ignores foreign statements about a deprecated property."""

from __future__ import annotations

from rule_harness import graph

from ontolint import Linter
from ontolint.rules.governance import _LIST_DEPTH  # noqa: PLC2701 -- the limit is what the test pins.


def _gov001(turtle: str, base: str | None = None) -> list[str]:
    result = Linter(graph(turtle), base=base).execute(["GOV001"])
    return sorted(f.message for f in result.findings)


def _union_ending_in_old(length: int) -> str:
    members = " ".join([*(f"ex:m{i}" for i in range(length - 1)), "ex:Old"])
    return (
        "ex:Old a owl:Class ; owl:deprecated true .\n"
        f"ex:A a owl:Class ; owl:equivalentClass [ owl:unionOf ( {members} ) ] ."
    )


def test_a_deprecated_term_in_a_short_list_is_reported_on_the_owner() -> None:
    messages = _gov001(_union_ending_in_old(3))

    assert messages == [
        "Deprecated term https://example.test/onto#Old appears in a list of http://www.w3.org/2002/07/owl#unionOf."
    ]


def test_a_list_longer_than_the_depth_limit_is_not_walked_back_to_its_owner() -> None:
    assert _gov001(_union_ending_in_old(_LIST_DEPTH + 6)) == []


def test_a_foreign_statement_with_a_deprecated_property_is_not_reported() -> None:
    turtle = (
        "ex:old a owl:ObjectProperty ; owl:deprecated true .\n"
        "<http://elsewhere.test/i> ex:old <http://elsewhere.test/j> .\n"
        "ex:i ex:old ex:j .\n"
    )

    messages = _gov001(turtle, base="https://example.test/onto#")

    assert messages == ["Deprecated property https://example.test/onto#old used in assertion."]
