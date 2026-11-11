"""SKOS018 and SKOS020 skip what is not the author's or not a notation literal."""

from __future__ import annotations

from rule_harness import graph

from ontolint import Linter

BASE = "https://example.test/onto#"


def _run(turtle: str, rule: str, base: str | None = None) -> list[tuple[str, str]]:
    return sorted((f.rule, str(f.focus)) for f in Linter(graph(turtle), base=base).execute([rule]).findings)


def test_a_redundant_broader_is_reported_for_a_local_concept_only() -> None:
    turtle = (
        "ex:a skos:broader ex:b, ex:c . ex:b skos:broader ex:c .\n"
        "<http://elsewhere.test/a> skos:broader <http://elsewhere.test/b>, <http://elsewhere.test/c> .\n"
        "<http://elsewhere.test/b> skos:broader <http://elsewhere.test/c> .\n"
    )

    assert _run(turtle, "SKOS018", base=BASE) == [("SKOS018", BASE + "a")]


def test_a_notation_that_is_not_a_literal_is_not_a_duplicate() -> None:
    concepts = (
        "ex:a a skos:Concept ; skos:inScheme ex:s ; skos:notation {n} .\n"
        "ex:b a skos:Concept ; skos:inScheme ex:s ; skos:notation {n} ."
    )

    assert _run(concepts.format(n="ex:n"), "SKOS020") == []
    assert [rule for rule, _ in _run(concepts.format(n='"1"'), "SKOS020")] == ["SKOS020"] * 2
