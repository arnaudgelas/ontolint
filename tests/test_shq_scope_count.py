"""The count of SHQ001-SHQ003 findings on production shapes graphs (scripts/shq_scope_count.py, issue #208).

Offline: tiny shapes graphs for the counting, and the committed manifest, results and page for the record.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from rdflib import Graph

ROOT = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("shq_scope_count", ROOT / "scripts" / "shq_scope_count.py")
assert spec is not None
assert spec.loader is not None
count = importlib.util.module_from_spec(spec)
sys.modules["shq_scope_count"] = count
spec.loader.exec_module(count)

MIN_REPOSITORIES = 5
TINY = 5  # bytes: a size cap below any file
PREFIXES = "@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <https://example.test/> . "
NAMED = 'sh:name "n" ; sh:description "d" ; '


def _count(turtle: str) -> dict[str, Any]:
    graph = Graph().parse(data=PREFIXES + turtle, format="turtle")
    counted = count.count_graph(graph)
    assert counted is not None
    return counted


def test_a_graph_without_a_shape_is_not_counted() -> None:
    assert count.count_graph(Graph().parse(data=PREFIXES + "ex:a ex:b ex:c .", format="turtle")) is None


# --- SHQ001 and SHQ002: judged before, and the directly targeted shapes issue #63 added ---------------------------


def test_a_property_shape_of_a_node_shape_was_judged_before() -> None:
    counted = _count("ex:N a sh:NodeShape ; sh:property [ sh:path ex:p ] .")
    assert (counted["judged"], counted["targeted"], counted["SHQ001"], counted["SHQ001_new"]) == (1, 0, 1, 0)


def test_a_directly_targeted_property_shape_is_the_new_scope() -> None:
    counted = _count("ex:P sh:path ex:p ; sh:targetClass ex:C .")
    assert (counted["judged"], counted["targeted"]) == (0, 1)
    assert (counted["SHQ001"], counted["SHQ001_new"], counted["SHQ002"], counted["SHQ002_new"]) == (1, 1, 1, 1)


@pytest.mark.parametrize(
    "target", ["sh:targetClass ex:C", "sh:targetNode ex:n", "sh:targetSubjectsOf ex:p", "sh:targetObjectsOf ex:p"]
)
def test_each_direct_target_makes_a_property_shape_stand_alone(target: str) -> None:
    assert _count(f"ex:P sh:path ex:p ; {target} .")["targeted"] == 1


def test_a_path_without_a_target_that_is_not_a_value_of_sh_property_is_not_judged() -> None:
    """Reached through sh:or or sh:node it has no target of its own: SHQ001 leaves it out on purpose."""
    counted = _count("ex:N a sh:NodeShape ; sh:or ( [ sh:path ex:p ] ) .")
    assert (counted["judged"], counted["targeted"], counted["SHQ001"]) == (0, 0, 0)


def test_a_node_shape_with_a_path_and_a_target_is_not_a_targeted_property_shape() -> None:
    assert _count("ex:N a sh:NodeShape ; sh:path ex:p ; sh:targetClass ex:C .")["targeted"] == 0


def test_an_annotated_targeted_shape_adds_no_finding() -> None:
    counted = _count(f"ex:P sh:path ex:p ; sh:targetClass ex:C ; {NAMED.rstrip(' ;')} .")
    assert (counted["targeted"], counted["SHQ001_new"], counted["SHQ002_new"]) == (1, 0, 0)


def test_blank_nodes_with_one_parent_and_one_content_share_a_finding_and_the_count_allows_it() -> None:
    """The rule names a blank node by its content, so two alike under one shape are one finding; the split holds."""
    counted = _count("ex:A sh:property [ sh:path ex:p ] , [ sh:path ex:p ] .")
    assert (counted["judged"], counted["SHQ001"], counted["SHQ001_new"]) == (2, 1, 0)


# --- SHQ003: the widened condition against the nine parameters of 0.12.0 ----------------------------------------


def test_a_shape_with_only_a_widened_parameter_is_the_widening() -> None:
    counted = _count(f"ex:N a sh:NodeShape ; sh:property [ sh:path ex:p ; {NAMED} sh:nodeKind sh:IRI ] .")
    assert (counted["SHQ003"], counted["SHQ003_narrow"]) == (1, 0)
    assert counted["extra_parameters"] == {"sh:nodeKind": 1}


def test_a_shape_with_a_narrow_parameter_is_in_both() -> None:
    counted = _count(
        f"ex:N a sh:NodeShape ; sh:property [ sh:path ex:p ; {NAMED} sh:minCount 1 ; sh:nodeKind sh:IRI ] ."
    )
    assert (counted["SHQ003"], counted["SHQ003_narrow"], counted["extra_parameters"]) == (1, 1, {})


def test_a_message_or_a_deactivation_leaves_a_shape_out_of_both() -> None:
    counted = _count(
        f"ex:A sh:property [ sh:path ex:p ; {NAMED} sh:minCount 1 ; sh:message 'm' ] . "
        f"ex:B sh:property [ sh:path ex:q ; {NAMED} sh:minCount 1 ; sh:deactivated true ] ."
    )
    assert (counted["SHQ003"], counted["SHQ003_narrow"]) == (0, 0)


def test_a_switch_counts_unless_it_is_false() -> None:
    on = _count(f"ex:A sh:property [ sh:path ex:p ; {NAMED} sh:closed true ] .")
    off = _count(f"ex:A sh:property [ sh:path ex:p ; {NAMED} sh:closed false ] .")
    assert (on["SHQ003"], on["extra_parameters"]) == (1, {"sh:closed": 1})
    assert (off["SHQ003"], off["extra_parameters"]) == (0, {})


def test_a_file_the_widening_alone_fails_under_strict_is_flagged() -> None:
    """Every other SHQ finding is answered (target, label, comment, name, description): only SHQ003 is left."""
    rdfs = "<http://www.w3.org/2000/01/rdf-schema#"
    turtle = (
        f"ex:N a sh:NodeShape ; sh:targetClass ex:C ; {rdfs}label> 'N' ; {rdfs}comment> 'c' ; sh:property ex:P . "
        f"ex:P sh:path ex:p ; {NAMED} sh:nodeKind sh:IRI ."
    )
    counted = _count(turtle)
    assert (counted["SHQ003"], counted["SHQ003_narrow"], counted["strict_flip"]) == (1, 0, 1)
    assert _count(turtle.replace("sh:nodeKind sh:IRI", "sh:minCount 1"))["strict_flip"] == 0


# --- the manifest ---------------------------------------------------------------------------------------------


def test_the_committed_manifest_pins_and_licenses_every_repository() -> None:
    repositories = count.load_manifest()
    assert len(repositories) >= MIN_REPOSITORIES
    assert all(
        count.COMMIT.fullmatch(r["commit"]) and r["licence"] and r["url"].startswith("https://") for r in repositories
    )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"commit": "main"}, "40-hex commit"),
        ({"url": "http://example.test/x.git"}, "https URL"),
        ({"licence": ""}, "licence"),
        ({"id": "../escape"}, "plain file name"),
    ],
)
def test_a_manifest_that_is_not_pinned_licensed_or_safely_named_is_refused(
    tmp_path: Path, change: dict[str, str], message: str
) -> None:
    entry = {"id": "x", "url": "https://example.test/x.git", "commit": "0" * 40, "licence": "MIT", **change}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"repositories": [entry]}), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        count.load_manifest(path)


def test_an_id_given_twice_is_refused(tmp_path: Path) -> None:
    entry = {"id": "x", "url": "https://example.test/x.git", "commit": "0" * 40, "licence": "MIT"}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"repositories": [entry, entry]}), encoding="utf-8")
    with pytest.raises(ValueError, match="given once"):
        count.load_manifest(path)


def test_fetch_refuses_a_checkout_at_another_commit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "x" / ".git").mkdir(parents=True)

    class Done:
        stdout = "f" * 40 + "\n"

    monkeypatch.setattr(count.subprocess, "run", lambda *a, **k: Done())
    entry = {"id": "x", "url": "https://example.test/x.git", "commit": "0" * 40, "licence": "MIT"}
    with pytest.raises(SystemExit, match="checked out"):
        count.fetch(tmp_path, [entry])


# --- the counting of a checkout ----------------------------------------------------------------------------------


def test_a_checkout_counts_its_shapes_files_and_skips_the_rest(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "ignored.ttl").write_text(PREFIXES + "ex:P sh:path ex:p .", encoding="utf-8")
    (tmp_path / "shapes.ttl").write_text(PREFIXES + "ex:P sh:path ex:p ; sh:targetClass ex:C .", encoding="utf-8")
    (tmp_path / "ontology.ttl").write_text(PREFIXES + "ex:a ex:b ex:c .", encoding="utf-8")
    (tmp_path / "broken.ttl").write_text("this is not turtle", encoding="utf-8")
    (tmp_path / "notes.md").write_text("ignored", encoding="utf-8")
    found = count.count_repository(tmp_path)
    assert list(found) == ["shapes.ttl"]
    assert found["shapes.ttl"]["SHQ001_new"] == 1


def test_a_file_over_the_size_cap_or_a_link_is_not_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "big.ttl").write_text(PREFIXES + "ex:P sh:path ex:p .", encoding="utf-8")
    (tmp_path / "link.ttl").symlink_to(tmp_path / "big.ttl")
    assert [p.name for p in count.shapes_files(tmp_path)] == ["big.ttl"]
    monkeypatch.setattr(count, "MAX_BYTES", TINY)
    assert count.shapes_files(tmp_path) == []


# --- the record -----------------------------------------------------------------------------------------------------


def _results() -> dict[str, Any]:
    return json.loads(count.RESULTS.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_the_results_are_of_the_manifests_repositories_at_its_commits() -> None:
    recorded = [(r["id"], r["commit"]) for r in _results()["repositories"]]
    assert recorded == [(r["id"], r["commit"]) for r in count.load_manifest()]


def test_every_recorded_file_is_internally_consistent() -> None:
    for repository in _results()["repositories"]:
        assert repository["files"], repository["id"]
        for path, counted in repository["files"].items():
            where = f"{repository['id']}/{path}"
            assert counted["SHQ001_new"] <= counted["targeted"] and counted["SHQ002_new"] <= counted["targeted"], where
            assert counted["strict_flip"] in (0, 1), where
            assert set(counted) == {*count.FIELDS, "extra_parameters"}, where


def test_the_committed_page_is_what_the_script_renders_from_the_results() -> None:
    assert count.generated_part() == count.render(_results())


def test_the_rendering_is_deterministic() -> None:
    assert count.render(_results()) == count.render(_results())


def test_the_results_are_written_as_sorted_indented_json_with_a_final_newline() -> None:
    text = count.RESULTS.read_text(encoding="utf-8")
    assert text == count.dump(json.loads(text)) and text.endswith("}\n")


def test_check_compares_the_counts_and_not_the_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    recorded = _results()
    assert count._comparable({**recorded, "ontolint": "9.9.9"}) == count._comparable(recorded)  # noqa: SLF001
    monkeypatch.setattr(count, "measure", lambda *a: {**recorded, "ontolint": "9.9.9"})
    assert count.main(["check", str(tmp_path)]) == 0
    changed = json.loads(json.dumps(recorded))
    changed["repositories"][0]["files"].popitem()
    monkeypatch.setattr(count, "measure", lambda *a: changed)
    assert count.main(["check", str(tmp_path)]) == 1
