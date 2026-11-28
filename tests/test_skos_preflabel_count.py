"""What a widened SKOS001 would report (scripts/skos_preflabel_count.py, issue #195).

Offline: a fixture of non-concept resources with two preferred labels for the counting, and the committed manifest,
results, page and decision record for the record.  The corpus count itself is ``skos_preflabel_count.py check``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from rdflib import Graph

from ontolint import Linter

ROOT = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("skos_preflabel_count", ROOT / "scripts" / "skos_preflabel_count.py")
assert spec is not None
assert spec.loader is not None
count = importlib.util.module_from_spec(spec)
sys.modules["skos_preflabel_count"] = count
spec.loader.exec_module(count)
pinned = count.pinned_repos

FIXTURE = ROOT / "tests" / "fixtures" / "skos_nonconcept_preflabels.ttl"
PREFIXES = (
    "@prefix ex: <https://example.test/skos#> . @prefix owl: <http://www.w3.org/2002/07/owl#> . "
    "@prefix skos: <http://www.w3.org/2004/02/skos/core#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> . "
    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . <https://example.test/skos> a owl:Ontology . "
)
MIN_REPOSITORIES = 12


def _count(turtle: str) -> dict[str, int]:
    counted = count.count_graph(Graph().parse(data=PREFIXES + turtle, format="turtle"))
    assert counted is not None
    return counted


# --- the fixture: what SKOS001 reports today and what a widened rule would add ---------------------------------------


def test_the_fixture_has_one_pair_of_each_kind_of_non_concept_and_skos001_reports_only_the_concept() -> None:
    graph = Graph().parse(FIXTURE)

    counted = count.count_graph(graph)
    findings = Linter(graph).execute(["SKOS001"]).findings

    assert counted == {
        "labelled_concept": 2,
        "labelled_scheme": 2,
        "labelled_collection": 3,
        "labelled_class": 2,
        "labelled_other": 1,
        "labelled_untyped": 1,
        "multi_concept": 1,
        "multi_scheme": 1,
        "multi_collection": 2,
        "multi_class": 1,
        "multi_other": 1,
        "multi_untyped": 1,
        "SKOS001": 1,
        "newly_failing": 0,
    }
    assert [f.focus for f in findings] == ["https://example.test/skos#conceptTwo"], "today only a concept is read"


def test_the_widening_adds_six_pairs_on_the_fixture_and_none_of_the_look_alikes() -> None:
    counted = count.count_graph(Graph().parse(FIXTURE))
    assert counted is not None

    assert sum(counted[f"multi_{kind}"] for kind in count.NON_CONCEPTS) == 6  # noqa: PLR2004


# --- the counting ------------------------------------------------------------------------------------------------


def test_a_graph_without_a_literal_preferred_label_is_not_counted() -> None:
    assert count.count_graph(Graph().parse(data=PREFIXES + "ex:a a skos:Concept .", format="turtle")) is None
    assert count.count_graph(Graph().parse(data=PREFIXES + "ex:a skos:prefLabel ex:b .", format="turtle")) is None


@pytest.mark.parametrize(
    ("labels", "pairs"),
    [
        ('"a"@en, "b"@en', 1),
        ('"a"@en, "b"@EN', 1),  # tags compare case-insensitively
        ('"a"@en, "a"@EN', 0),  # one label spelled twice
        ('"a"@en, "b"@fr', 0),
        ('"a", "b"', 1),  # untagged labels are one language
        ('"a", "b"@und', 1),  # an explicit @und joins them
        ('"a", "a"^^xsd:string', 0),  # RDF 1.1: one literal
        ('"a"^^xsd:string, "b"', 1),
        ('"1"^^xsd:integer, "a"', 1),  # another datatype counts as untagged
        ('"a"@en, "b"@en, "c"@fr, "d"@fr', 2),
    ],
)
def test_the_pairs_of_a_resource_are_counted_by_the_languages_skos001_compares(labels: str, pairs: int) -> None:
    assert _count(f"ex:s a skos:ConceptScheme ; skos:prefLabel {labels} .")["multi_scheme"] == pairs


@pytest.mark.parametrize(
    ("types", "kind"),
    [
        ("skos:Concept", "concept"),
        ("skos:Concept, skos:ConceptScheme", "concept"),
        ("skos:Concept, owl:Class", "concept"),
        ("skos:ConceptScheme, owl:Class", "scheme"),
        ("skos:Collection, owl:Class", "collection"),
        ("skos:OrderedCollection", "collection"),
        ("owl:Class", "class"),
        ("rdfs:Class", "class"),
        ("owl:Class, ex:Thing", "class"),
        ("ex:Thing", "other"),
    ],
)
def test_a_resource_has_the_first_kind_its_asserted_types_name(types: str, kind: str) -> None:
    counted = _count(f"ex:s a {types} ; skos:prefLabel 'a'@en .")

    assert {k for k, v in counted.items() if k.startswith("labelled_") and v} == {f"labelled_{kind}"}


def test_a_resource_without_a_type_is_untyped() -> None:
    assert _count("ex:s skos:prefLabel 'a'@en .")["labelled_untyped"] == 1


def test_a_file_the_rule_already_fails_does_not_newly_fail_and_one_it_passes_does() -> None:
    pair = "skos:prefLabel 'a'@en, 'b'@en"
    both = _count(f"ex:c a skos:Concept ; {pair} . ex:s a skos:ConceptScheme ; {pair} .")
    only = _count(f"ex:s a skos:ConceptScheme ; {pair} .")

    assert (both["SKOS001"], both["newly_failing"]) == (1, 0)
    assert (only["SKOS001"], only["newly_failing"]) == (0, 1)


def test_a_concept_in_a_minority_namespace_is_counted_but_not_reported_by_the_rule() -> None:
    """The count reads every concept, the rule only the owned ones, so the rule's findings are at most the pairs."""
    graph = Graph().parse(
        data=(
            "@prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix skos: <http://www.w3.org/2004/02/skos/core#> . "
            "@prefix a: <https://mine.test/a/> . @prefix b: <https://other.test/b/> . "
            "<https://mine.test/a> a owl:Ontology . "
            "a:1 a skos:Concept ; skos:prefLabel 'x'@en . a:2 a skos:Concept ; skos:prefLabel 'y'@en . "
            "a:3 a skos:Concept ; skos:prefLabel 'z'@en . "
            "b:1 a skos:Concept ; skos:prefLabel 'a'@en, 'b'@en ."
        ),
        format="turtle",
    )

    counted = count.count_graph(graph)

    assert counted is not None
    assert (counted["multi_concept"], counted["SKOS001"]) == (1, 0)


def test_a_rule_that_reports_more_than_was_counted_is_an_error_not_a_number(monkeypatch: pytest.MonkeyPatch) -> None:
    class Noisy:
        def __init__(self, _graph: Any) -> None: ...

        def execute(self, _rules: list[str]) -> Any:
            return type("Result", (), {"findings": [object()]})()

    monkeypatch.setattr("ontolint.Linter", Noisy)

    with pytest.raises(ValueError, match="SKOS001 reports 1 findings"):
        count.count_graph(
            Graph().parse(data=PREFIXES + "ex:s a skos:ConceptScheme ; skos:prefLabel 'a'@en .", format="turtle")
        )


# --- check, render and the manifest -------------------------------------------------------------------------------


def _check(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], **changed: Any) -> tuple[int, str]:
    recorded = json.loads(count.RESULTS.read_text(encoding="utf-8"))
    monkeypatch.setattr(count, "measure", lambda _directory, _repositories: {**recorded, **changed})

    return count.main(["check", "unused"]), capsys.readouterr().err


def test_check_passes_when_the_counts_match_whatever_versions_counted_them(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _check(monkeypatch, capsys, ontolint="9.9.9", rdflib="0.0.1") == (0, "")


def test_check_fails_on_different_counts_and_names_the_recorded_and_the_current_versions(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    recorded = json.loads(count.RESULTS.read_text(encoding="utf-8"))
    moved = [{**recorded["repositories"][0], "parsed": recorded["repositories"][0]["parsed"] + 1}]

    status, message = _check(monkeypatch, capsys, repositories=moved, rdflib="0.0.1")

    assert status == 1
    assert f"recorded with ontolint {recorded['ontolint']}, rdflib {recorded['rdflib']}" in message
    assert "rdflib 0.0.1" in message


def test_the_generated_part_is_rewritten_between_its_markers_only(tmp_path: Path) -> None:
    page = tmp_path / "p.md"
    page.write_text(f"head\n{count.BEGIN}\nold\n{count.END}\ntail\n")
    results = json.loads(count.RESULTS.read_text(encoding="utf-8"))

    count.write_page(results, page)

    assert page.read_text().startswith(f"head\n{count.BEGIN}\n") and page.read_text().endswith(f"{count.END}\ntail\n")
    assert count.generated_part(page) == count.render(results)
    (tmp_path / "q.md").write_text("no markers")
    with pytest.raises(ValueError, match="one"):
        count.write_page(results, tmp_path / "q.md")


# --- the record --------------------------------------------------------------------------------------------------

RESULTS = json.loads((ROOT / "docs" / "validation" / "skos-preflabel-results.json").read_text(encoding="utf-8"))
PAGE = (ROOT / "docs" / "validation" / "skos-preflabel.md").read_text(encoding="utf-8")
RECORD = (ROOT / "docs" / "severity-decisions.md").read_text(encoding="utf-8")


def _flat(text: str) -> str:
    """The text on one line, so a figure is found wherever the prose wraps."""
    return " ".join(text.split())


def _all() -> dict[str, int]:
    return count.totals({p: f for repo in RESULTS["repositories"] for p, f in repo["files"].items()})


def test_the_committed_manifest_is_valid_and_the_results_name_its_commits() -> None:
    repositories = pinned.load_manifest(ROOT / "docs" / "validation" / "skos-preflabel-corpus.json")

    assert [(r["id"], r["commit"]) for r in repositories] == [(r["id"], r["commit"]) for r in RESULTS["repositories"]]
    assert len(repositories) >= MIN_REPOSITORIES
    assert all(r["licence"] for r in repositories)


def test_the_page_table_is_what_the_recorded_results_render() -> None:
    assert count.generated_part() == count.render(RESULTS)


def test_the_figures_the_page_and_the_record_quote_are_the_recorded_results() -> None:
    everything = _all()
    non_concepts = sum(everything[f"labelled_{kind}"] for kind in count.NON_CONCEPTS)
    labelled = everything["labelled_concept"] + non_concepts
    parsed = sum(r["parsed"] for r in RESULTS["repositories"])
    unparsed = sum(r["unparsed"] for r in RESULTS["repositories"])
    repositories = len(RESULTS["repositories"])

    assert sum(everything[f"multi_{k}"] for k in count.NON_CONCEPTS) == 0, "the page says no non-concept has two"
    assert everything["newly_failing"] == 0
    assert everything["labelled_class"] == 1, "the page says a single owl:Class carries a preferred label"
    for figure in (
        f"{repositories} public SKOS vocabularies",
        f"{labelled:,} resources",
        f"{non_concepts} are not typed `skos:Concept`",
        f"{everything['labelled_scheme']} schemes",
        f"{everything['labelled_collection']} collections",
        f"no file of the {everything['files']} with a preferred label",
        f"{unparsed} of the {parsed + unparsed:,} RDF files within the size cap were not parsed",
    ):
        assert figure in _flat(PAGE), figure
    assert f"**{repositories} vocabularies**" in _flat(RECORD)
    assert f"{labelled:,} labelled resources" in _flat(RECORD)
    assert f"{non_concepts} not typed `skos:Concept`" in _flat(RECORD)


def test_the_page_states_the_concentration_of_the_resources_the_results_have() -> None:
    sizes = sorted(
        (
            sum(f[f"labelled_{kind}"] for f in repo["files"].values() for kind in count.KINDS)
            for repo in RESULTS["repositories"]
        ),
        reverse=True,
    )

    assert f"Five repositories hold {100 * sum(sizes[:5]) / sum(sizes):.0f}% of the labelled resources" in _flat(PAGE)
    assert f"alone {100 * sizes[0] / sum(sizes):.0f}%" in _flat(PAGE)


def test_the_page_names_its_gaps_and_derives_no_rate_and_the_record_leaves_the_widening_undecided() -> None:
    assert "a single `owl:Class`" in _flat(PAGE)
    assert "no rate is derived" in PAGE.lower()
    row = next(line for line in RECORD.splitlines() if line.startswith("| SKOS001 scope (S14) |"))
    assert "undecided" in row
    assert "validation/skos-preflabel.md" in RECORD
