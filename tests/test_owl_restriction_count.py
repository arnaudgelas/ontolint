"""The count of OWL035 findings on OWL 1 era RDF files (scripts/owl_restriction_count.py, issue #196).

Offline: tiny graphs for the counting, a local git repository for the pinned fetch, and the committed manifest,
results, page and decision record for the record.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from rdflib import Graph

ROOT = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("owl_restriction_count", ROOT / "scripts" / "owl_restriction_count.py")
assert spec is not None
assert spec.loader is not None
count = importlib.util.module_from_spec(spec)
sys.modules["owl_restriction_count"] = count
spec.loader.exec_module(count)
pinned = count.pinned_repos

MIN_REPOSITORIES = 3
SEVERAL_RESTRICTIONS, FINDINGS = (
    1,
    10,
)  # what the page reads: premises905 is the one, and ten findings none of them the idiom
PREFIXES = "@prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix ex: <https://example.test/> . "
XSD_ONE = '"1"^^<http://www.w3.org/2001/XMLSchema#nonNegativeInteger>'
XSD_TWO = '"2"^^<http://www.w3.org/2001/XMLSchema#nonNegativeInteger>'


def _count(turtle: str) -> dict[str, Any]:
    counted = count.count_graph(Graph().parse(data=PREFIXES + turtle, format="turtle"))
    assert counted is not None
    return counted


def _restriction(*constraints: str) -> str:
    return f"[ a owl:Restriction ; owl:onProperty ex:p ; {' ; '.join(constraints)} ]"


# --- the counting ------------------------------------------------------------------------------------------------


def test_a_graph_without_a_restriction_is_not_counted() -> None:
    assert count.count_graph(Graph().parse(data=PREFIXES + "ex:a a owl:Class .", format="turtle")) is None


def test_a_node_with_an_on_property_but_no_restriction_type_is_not_a_restriction() -> None:
    """OWL035 visits the nodes typed owl:Restriction only, so the count must too (it first counted these)."""
    assert count.count_graph(Graph().parse(data=PREFIXES + "[ owl:onProperty ex:p ] .", format="turtle")) is None


def test_a_restriction_with_one_constraint_is_counted_and_not_reported() -> None:
    assert _count(f"ex:A a owl:Class ; owl:equivalentClass {_restriction(f'owl:minCardinality {XSD_ONE}')} .") == {
        "restrictions": 1,
        "several": 0,
        "min_max": 0,
        "split_pairs": 0,
        "owl2": 0,
        "OWL035": 0,
    }


def test_a_minimum_and_a_maximum_in_one_restriction_is_the_idiom_and_is_reported() -> None:
    counted = _count(
        f"ex:A owl:equivalentClass {_restriction(f'owl:minCardinality {XSD_ONE}', f'owl:maxCardinality {XSD_TWO}')} ."
    )

    assert (counted["restrictions"], counted["several"], counted["min_max"], counted["OWL035"]) == (1, 1, 1, 1)


def test_the_qualified_minimum_and_maximum_are_the_idiom_too_and_mark_the_file_as_owl_2() -> None:
    counted = _count(
        "ex:A owl:equivalentClass "
        + _restriction(
            f"owl:minQualifiedCardinality {XSD_ONE}", f"owl:maxQualifiedCardinality {XSD_TWO}", "owl:onClass ex:B"
        )
        + " ."
    )

    assert (counted["min_max"], counted["owl2"]) == (1, 1)


def test_two_constraints_that_are_not_a_minimum_and_a_maximum_are_several_but_not_the_idiom() -> None:
    counted = _count(f"ex:A owl:equivalentClass {_restriction('owl:someValuesFrom ex:B', 'owl:allValuesFrom ex:C')} .")

    assert (counted["several"], counted["min_max"], counted["OWL035"]) == (1, 0, 1)


def test_a_restriction_without_a_constraint_is_reported_by_the_rule_and_is_not_several() -> None:
    counted = _count(f"ex:A owl:equivalentClass {_restriction()} .")

    assert (counted["restrictions"], counted["several"], counted["OWL035"]) == (1, 0, 1)


def test_a_minimum_and_a_maximum_as_two_restrictions_of_one_intersection_are_a_split_pair_the_rule_accepts() -> None:
    counted = _count(
        "ex:A owl:equivalentClass [ a owl:Class ; owl:intersectionOf ( "
        f"{_restriction(f'owl:minCardinality {XSD_ONE}')} {_restriction(f'owl:maxCardinality {XSD_TWO}')} ) ] ."
    )

    assert (counted["split_pairs"], counted["min_max"], counted["several"], counted["OWL035"]) == (1, 0, 0, 0)


def test_a_minimum_and_a_maximum_on_different_properties_are_not_a_split_pair() -> None:
    other = f"[ a owl:Restriction ; owl:onProperty ex:q ; owl:maxCardinality {XSD_TWO} ]"

    assert (
        _count(
            "ex:A owl:equivalentClass [ a owl:Class ; owl:intersectionOf ( "
            f"{_restriction(f'owl:minCardinality {XSD_ONE}')} {other} ) ] ."
        )["split_pairs"]
        == 0
    )


def test_an_intersection_list_that_loops_is_skipped() -> None:
    """A malformed list is data of the corpus: it must neither hang nor stop the count."""
    counted = _count(
        f"ex:A owl:intersectionOf ex:l . ex:l <http://www.w3.org/1999/02/22-rdf-syntax-ns#first> {_restriction()} ; "
        "<http://www.w3.org/1999/02/22-rdf-syntax-ns#rest> ex:l ."
    )

    assert counted["split_pairs"] == 0


def test_a_file_without_owl_2_vocabulary_is_owl_1_only_and_has_property_chain_or_has_self_as_owl_2() -> None:
    assert _count(f"ex:A owl:equivalentClass {_restriction('owl:someValuesFrom ex:B')} .")["owl2"] == 0
    assert (
        _count(
            f"ex:A owl:equivalentClass {_restriction('owl:someValuesFrom ex:B')} . "
            "ex:p owl:propertyChainAxiom ( ex:q ) ."
        )["owl2"]
        == 1
    )
    assert (
        _count(
            "ex:i a owl:NamedIndividual . " + f"ex:A owl:equivalentClass {_restriction('owl:someValuesFrom ex:B')} ."
        )["owl2"]
        == 1
    )


def test_a_disagreement_between_the_rule_and_the_count_is_an_error_not_a_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Silent:
        def __init__(self, _graph: Any) -> None: ...

        def execute(self, _rules: list[str]) -> Any:
            return type("Result", (), {"findings": []})()

    monkeypatch.setattr("ontolint.Linter", Silent)
    graph = Graph().parse(
        data=PREFIXES
        + f"ex:A owl:equivalentClass {_restriction('owl:someValuesFrom ex:B', 'owl:allValuesFrom ex:C')} .",
        format="turtle",
    )

    with pytest.raises(ValueError, match="several constraints"):
        count.count_graph(graph)


# --- the files ---------------------------------------------------------------------------------------------------


def test_only_rdf_files_outside_git_that_are_small_and_not_links_are_read(tmp_path: Path) -> None:
    (tmp_path / "a.owl").write_text("x")
    (tmp_path / "b.TTL").write_text("x")
    (tmp_path / "c.txt").write_text("x")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "d.owl").write_text("x")
    (tmp_path / "e.owl").symlink_to(tmp_path / "a.owl")
    (tmp_path / "big.owl").write_bytes(b"x" * (count.MAX_BYTES + 1))

    assert [p.name for p in count.rdf_files(tmp_path)] == ["a.owl", "b.TTL"]


def test_a_file_rdflib_cannot_read_is_counted_as_not_parsed_not_dropped(tmp_path: Path) -> None:
    (tmp_path / "good.ttl").write_text(
        PREFIXES + f"ex:A owl:equivalentClass {_restriction('owl:someValuesFrom ex:B')} ."
    )
    (tmp_path / "plain.ttl").write_text(PREFIXES + "ex:A a owl:Class .")
    (tmp_path / "bad.owl").write_text("this is <not rdf")

    found = count.count_repository(tmp_path)

    assert (found["parsed"], found["unparsed"], sorted(found["files"])) == (2, 1, ["good.ttl"])


def test_a_file_over_the_size_cap_or_a_link_is_listed_as_skipped_not_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "small.ttl").write_text("")
    (tmp_path / "large.owl").write_text("x" * 10)
    (tmp_path / "link.rdf").symlink_to(tmp_path / "small.ttl")
    (tmp_path / "notes.txt").write_text("x" * 10)
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "big.owl").write_text("x" * 10)
    monkeypatch.setattr(count, "MAX_BYTES", 5)

    assert count.skipped_files(tmp_path) == ["large.owl", "link.rdf"]
    assert count.count_repository(tmp_path)["skipped"] == ["large.owl", "link.rdf"]


def test_reading_a_repository_leaves_the_callers_logging_as_it_found_it(tmp_path: Path) -> None:
    """The reader silences rdflib's conversion warnings for its own run only: a utility, not a process setting."""
    (tmp_path / "good.ttl").write_text(
        PREFIXES + f"ex:A owl:equivalentClass {_restriction('owl:someValuesFrom ex:B')} ."
    )
    logging.disable(logging.WARNING)
    try:
        count.count_repository(tmp_path)

        assert logging.root.manager.disable == logging.WARNING
    finally:
        logging.disable(logging.NOTSET)


def test_reading_a_repository_restores_logging_when_a_counter_raises(tmp_path: Path) -> None:
    (tmp_path / "a.ttl").write_text(PREFIXES + "ex:A a owl:Class .")

    def broken(_graph: Any) -> dict[str, Any] | None:
        raise ValueError("a cross-check failed")

    before = logging.root.manager.disable
    with pytest.raises(ValueError, match="cross-check"):
        pinned.read_repository(tmp_path, broken)

    assert logging.root.manager.disable == before


# --- the pinned fetch --------------------------------------------------------------------------------------------


def _git(directory: Path, *argv: str) -> str:
    return subprocess.run(  # noqa: S603 -- git, on a repository the test just made
        ["git", "-C", str(directory), "-c", "user.name=t", "-c", "user.email=t@example.test", *argv],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def origin(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "origin"
    (repo / "wanted").mkdir(parents=True)
    (repo / "other").mkdir()
    (repo / "wanted" / "a.owl").write_text("a")
    (repo / "other" / "b.owl").write_text("b")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "one")
    return repo, _git(repo, "rev-parse", "HEAD")


def test_fetch_checks_out_only_the_listed_directories_at_the_pinned_commit(
    origin: tuple[Path, str], tmp_path: Path
) -> None:
    repo, commit = origin
    entry = {"id": "r", "url": repo.as_uri(), "commit": commit, "licence": "MIT", "paths": ["wanted"]}

    pinned.fetch(tmp_path / "out", [entry])

    assert sorted(
        p.relative_to(tmp_path / "out" / "r").as_posix() for p in (tmp_path / "out" / "r").rglob("*.owl")
    ) == ["wanted/a.owl"]


def test_fetch_refuses_a_checkout_whose_commit_is_not_the_pinned_one(origin: tuple[Path, str], tmp_path: Path) -> None:
    repo, commit = origin
    entry = {"id": "r", "url": repo.as_uri(), "commit": commit, "licence": "MIT"}
    pinned.fetch(tmp_path / "out", [entry])
    (repo / "wanted" / "c.owl").write_text("c")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "two")
    _git(tmp_path / "out" / "r", "fetch", "-q", "--depth", "1", repo.as_uri(), _git(repo, "rev-parse", "HEAD"))
    _git(tmp_path / "out" / "r", "checkout", "-q", "FETCH_HEAD")

    with pytest.raises(SystemExit, match="the manifest pins"):
        pinned.fetch(tmp_path / "out", [entry])


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
    assert "evidence to review" in message


# --- the manifest ------------------------------------------------------------------------------------------------

GOOD = {"id": "r", "url": "https://example.test/r.git", "commit": "a" * 40, "licence": "MIT", "paths": ["x/y"]}


def _manifest(tmp_path: Path, *repositories: dict[str, Any]) -> Path:
    path = tmp_path / "m.json"
    path.write_text(json.dumps({"repositories": list(repositories)}))
    return path


def test_a_good_manifest_entry_is_accepted(tmp_path: Path) -> None:
    assert pinned.load_manifest(_manifest(tmp_path, GOOD)) == [GOOD]


@pytest.mark.parametrize(
    "bad",
    [
        {"commit": "main"},
        {"commit": "A" * 40},
        {"commit": "a" * 39},
        {"url": "http://example.test/r.git"},
        {"url": "git@example.test:r.git"},
        {"licence": ""},
        {"id": "../r"},
        {"id": ".hidden"},
        {"paths": ["../x"]},
        {"paths": ["/abs"]},
        {"paths": ["a/../b"]},
        {"paths": ["a b"]},
    ],
)
def test_a_repository_not_pinned_licensed_or_safely_named_is_refused(tmp_path: Path, bad: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="repository|id is|directory"):
        pinned.load_manifest(_manifest(tmp_path, {**GOOD, **bad}))


def test_an_id_given_twice_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="given once"):
        pinned.load_manifest(_manifest(tmp_path, GOOD, GOOD))


# --- the record --------------------------------------------------------------------------------------------------

MANIFEST = json.loads((ROOT / "docs" / "validation" / "owl-restrictions-corpus.json").read_text(encoding="utf-8"))
RESULTS = json.loads((ROOT / "docs" / "validation" / "owl-restrictions-results.json").read_text(encoding="utf-8"))
PAGE = (ROOT / "docs" / "validation" / "owl-restrictions.md").read_text(encoding="utf-8")
RECORD = (ROOT / "docs" / "severity-decisions.md").read_text(encoding="utf-8")


def _all(keep: int | None = None) -> dict[str, int]:
    files = {
        p: f for repo in RESULTS["repositories"] for p, f in repo["files"].items() if keep is None or f["owl2"] == keep
    }
    return count.totals(files)


def test_the_committed_manifest_is_valid_and_the_results_name_its_commits() -> None:
    repositories = pinned.load_manifest(ROOT / "docs" / "validation" / "owl-restrictions-corpus.json")

    assert [(r["id"], r["commit"]) for r in repositories] == [(r["id"], r["commit"]) for r in RESULTS["repositories"]]
    assert len(repositories) >= MIN_REPOSITORIES
    assert all(r["paths"] for r in repositories), "each repository is a sparse checkout of its test data"


def test_the_page_table_is_what_the_recorded_results_render() -> None:
    assert count.generated_part() == count.render(RESULTS)


def test_the_generated_part_is_rewritten_between_its_markers_only(tmp_path: Path) -> None:
    page = tmp_path / "p.md"
    page.write_text(f"head\n{count.BEGIN}\nold\n{count.END}\ntail\n")

    count.write_page(RESULTS, page)

    assert page.read_text().startswith(f"head\n{count.BEGIN}\n") and page.read_text().endswith(f"{count.END}\ntail\n")
    assert count.generated_part(page) == count.render(RESULTS)
    with pytest.raises(ValueError, match="one"):
        (tmp_path / "q.md").write_text("no markers")
        count.write_page(RESULTS, tmp_path / "q.md")


def test_the_figures_the_page_and_the_record_quote_are_the_recorded_results() -> None:
    everything, owl1 = _all(), _all(0)
    parsed = sum(r["parsed"] for r in RESULTS["repositories"])
    unparsed = sum(r["unparsed"] for r in RESULTS["repositories"])

    assert everything["min_max"] == owl1["min_max"] == 0, "the page says the idiom does not occur"
    assert (everything["several"], everything["OWL035"]) == (SEVERAL_RESTRICTIONS, FINDINGS)
    for figure in (
        f"0 of {everything['restrictions']:,} restrictions",
        f"0 of {owl1['restrictions']:,} in files",
        f"{everything['split_pairs']} `owl:intersectionOf`",
        f"{unparsed} of the {parsed + unparsed:,} RDF files within the size cap",
        f"({100 * unparsed / (parsed + unparsed):.1f}%)",
    ):
        assert figure in PAGE, figure
    assert (
        f"**0 of {everything['restrictions']:,}\n  restrictions** (3 repositories, {parsed:,} files parsed)" in RECORD
    )
    assert f"({everything['split_pairs']} cases)" in RECORD


def test_the_page_names_every_skipped_file_and_derives_no_rate_and_no_tool_habit_from_test_data() -> None:
    skipped = [f"{r['id']}/{p}" for r in RESULTS["repositories"] for p in r["skipped"]]

    assert [p.rsplit("/", 1)[-1] for p in skipped] == ["vicodi.ttl"], "the page's Limits name this one file"
    assert "`vicodi.ttl`" in PAGE and "one file over the\n  cap" in PAGE
    for claim in ("0.04%", "OWL 1 tools write"):
        assert claim not in PAGE and claim not in RECORD, claim
    assert "no rate is derived" in PAGE


def test_the_results_record_the_versions_that_counted_them() -> None:
    assert {"ontolint", "rdflib"} <= RESULTS.keys()


def test_the_record_keeps_owl035_an_error_and_names_the_page() -> None:
    assert "| OWL035 | keep error;" in RECORD
    assert "| 7 | OWL035 | keep error (medium) | keep error |" in RECORD
    assert "validation/owl-restrictions.md" in RECORD
