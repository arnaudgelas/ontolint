"""Exact expectations for the specified error rules SKOS001, SKOS002, SKOS009 and ALIGN003."""

from __future__ import annotations

from rule_harness import BASE, chain_turtle, graph

from ontolint import Linter


def run(rule: str, turtle: str) -> list[tuple[str, str]]:
    result = Linter(graph(turtle)).execute([rule])
    return sorted((f.focus.removeprefix(BASE), f.message) for f in result.findings if f.rule == rule)


def test_skos001_mixed_case_tags_are_one_language_reported_in_lower_case() -> None:
    assert run("SKOS001", 'ex:c a skos:Concept ; skos:prefLabel "a"@en, "b"@EN .') == [
        ("c", "2 prefLabels in language en.")
    ]


def test_skos001_a_uniform_tag_is_reported_as_written() -> None:
    assert run("SKOS001", 'ex:c a skos:Concept ; skos:prefLabel "a"@en-US, "b"@en-US .') == [
        ("c", "2 prefLabels in language en-US.")
    ]


def test_skos001_untagged_labels_are_language_und() -> None:
    assert run("SKOS001", 'ex:c a skos:Concept ; skos:prefLabel "a", "b" .') == [("c", "2 prefLabels in language und.")]


def test_skos002_plain_and_xsd_string_report_no_language() -> None:
    assert run("SKOS002", 'ex:c skos:prefLabel "a" ; skos:hiddenLabel "a"^^xsd:string .') == [
        ("c", "Literal 'a' (no language) appears in skos:prefLabel and skos:hiddenLabel.")
    ]


def test_skos009_transitive_conflict_is_reported_once_on_the_smaller_iri() -> None:
    body = "ex:a skos:broader ex:b . ex:b skos:broader ex:c . ex:c skos:related ex:a . ex:a skos:related ex:c ."
    assert run("SKOS009", body) == [
        ("a", f"skos:related and a hierarchical link both connect {BASE}a and {BASE}c."),
    ]


def test_skos009_follows_a_long_chain() -> None:
    body = chain_turtle(2000, "skos:broader", "skos:Concept") + " ex:n0 skos:related ex:n1999 ."
    assert [focus for focus, _ in run("SKOS009", body)] == ["n0"]


def test_align003_broad_and_inverse_narrow_on_one_pair_is_one_finding() -> None:
    body = (
        "ex:x skos:exactMatch ex:y . ex:y skos:exactMatch ex:z . "
        "ex:x skos:broadMatch ex:z . ex:z skos:narrowMatch ex:x ."
    )
    assert run("ALIGN003", body) == [
        (
            "x",
            f"{BASE}x and {BASE}z are exactMatch-equivalent through a chain but also linked by broadMatch/narrowMatch.",
        )
    ]


def test_skos001_mixed_spellings_of_a_subtag_are_reported_in_lower_case() -> None:
    body = 'ex:c a skos:Concept ; skos:prefLabel "a"@en-US, "b"@EN-us .'
    assert run("SKOS001", body) == [("c", "2 prefLabels in language en-us.")]


def test_align003_reports_related_match_in_an_exact_match_chain_once_on_the_smaller_iri() -> None:
    body = (
        "ex:x skos:exactMatch ex:y . ex:z skos:exactMatch ex:y . "
        "ex:z skos:relatedMatch ex:x . ex:x skos:relatedMatch ex:z ."
    )
    assert run("ALIGN003", body) == [
        ("x", f"{BASE}x and {BASE}z are exactMatch-equivalent through a chain but also linked by relatedMatch."),
    ]
    (finding,) = Linter(graph(body)).execute(["ALIGN003"]).findings
    assert finding.subject == ("http://www.w3.org/2004/02/skos/core#relatedMatch", f"{BASE}z")


def test_align003_reports_a_broad_and_a_related_match_on_one_pair_apart() -> None:
    body = (
        "ex:x skos:exactMatch ex:y . ex:y skos:exactMatch ex:z . ex:x skos:broadMatch ex:z ; skos:relatedMatch ex:z ."
    )
    assert [message.split(" but also linked by ")[1] for _focus, message in run("ALIGN003", body)] == [
        "broadMatch/narrowMatch.",
        "relatedMatch.",
    ]
