"""``measurement_partitions``: the term measurements per in-file module, named graph and closure file.

A term is placed exactly where a finding about it is, so the parity tests compare each partition's terms with
the modules, graphs and file the JSON report gives the LEX001 and LEX002 findings of the same terms.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis_strategies import budget
from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF

from ontolint import cli, main
from ontolint.engine import build_context
from ontolint.loader import loaded_graph
from ontolint.models import MeasurementPartition
from ontolint.paths import resolve_inputs
from ontolint.policy import Policy
from ontolint.rules import measurements
from ontolint.rules.measurements import Absent, Count, CountRatio, TermRatio, TermValues

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TWO_GRAPHS = str(FIXTURES / "datasets" / "one_term_two_graphs.trig")
MODULAR = str(FIXTURES / "modular" / "umbrella.ttl")
DATASET_CLOSURE = str(FIXTURES / "datasets" / "closure" / "root.ttl")
PARTITIONED = [spec.id for spec in measurements.SPECS if spec.partitioned]
UNPARTITIONED = {"foreign_references", "unresolved_imports", "blank_subjects", "hierarchy_components"}
PREFIXES = """@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix a: <https://example.test/a#> .
@prefix b: <https://example.test/b#> .
@prefix opla: <http://ontologydesignpatterns.org/opla#> .
<https://example.test/> a owl:Ontology .
"""

type Places = dict[tuple[str, str | None, str | None], set[str]]


def _report(argv: list[str], capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    code = main([*argv, "--format", "json", "--measurements"])
    out = capsys.readouterr().out
    assert code in {0, 1}, out
    return json.loads(out)


def _partitions(entry: Mapping[str, Any]) -> dict[tuple[str, str | None, str | None], dict[str, Any]]:
    return {(p["by"], p.get("path"), p.get("name")): p for p in entry["measurement_partitions"]}


def _value(partition: Mapping[str, Any], measurement_id: str) -> tuple[int, int] | list[dict[str, int]]:
    (found,) = [m for m in partition["measurements"] if m["id"] == measurement_id]
    return found["buckets"] if found["kind"] == "histogram" else (found["numerator"], found["denominator"])


def _write(tmp_path: Path, name: str, text: str) -> str:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


# --- which partitions, and their values -------------------------------------------------------------------------


def test_named_graphs_partition_the_terms_they_describe(capsys: pytest.CaptureFixture[str]) -> None:
    (entry,) = _report([TWO_GRAPHS], capsys)["files"]
    partitions = _partitions(entry)
    path = entry["path"]
    # Every graph of the index is listed, the default graph first, though no owned term is described there.
    assert list(partitions) == [
        ("graph", path, "(default graph)"),
        ("graph", path, "http://example.org/g1"),
        ("graph", path, "http://example.org/g2"),
    ]
    # ex:Thing is described in both graphs and counts in both; its label, in g2, counts in g1 too.
    assert [_value(p, "class_label_coverage") for p in partitions.values()] == [(0, 0), (2, 2), (1, 1)]
    assert [[m["id"] for m in p["measurements"]] for p in partitions.values()] == [PARTITIONED] * 3


def test_modules_by_namespace_and_by_annotation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    onto = _write(
        tmp_path,
        "onto.ttl",
        PREFIXES + 'a:A a owl:Class ; rdfs:label "A" ; opla:isNativeTo "Core" .\n'
        'a:B a owl:Class ; opla:isNativeTo "Core", "Extra" ; rdfs:subClassOf a:A .\n'
        'b:C a owl:Class ; rdfs:label "C" ; rdfs:comment "A class of b." .\n'
        "<https://other.example/Z> a owl:Class .\n",
    )
    by_namespace = _partitions(_report([onto, "--module-by", "namespace"], capsys)["files"][0])
    assert list(by_namespace) == [
        ("module", None, "https://example.test/a#"),
        ("module", None, "https://example.test/b#"),
    ]
    assert [_value(p, "class_label_coverage") for p in by_namespace.values()] == [(1, 2), (1, 1)]
    assert [_value(p, "class_definition_coverage") for p in by_namespace.values()] == [(0, 2), (1, 1)]
    by_annotation = _partitions(_report([onto, "--module-annotation", "opla:isNativeTo"], capsys)["files"][0])
    # b:C carries no annotation, so it is in no module.
    assert list(by_annotation) == [("module", None, "Core"), ("module", None, "Extra")]
    assert [_value(p, "class_label_coverage") for p in by_annotation.values()] == [(1, 2), (0, 1)]
    # A partition restricts and never recomputes: B keeps its depth in the whole file.
    assert _value(by_annotation["module", None, "Extra"], "class_depth") == [{"value": 2, "count": 1}]


def test_closure_files_partition_the_terms_they_declare(capsys: pytest.CaptureFixture[str]) -> None:
    (entry,) = _report([MODULAR, "--follow-imports"], capsys)["files"]
    partitions = _partitions(entry)
    # Every closure file, the umbrella root first though it declares no term; no file has named graphs.
    assert [(by, Path(path or "").name, name) for by, path, name in partitions] == [
        ("file", "umbrella.ttl", None),
        ("file", "core.ttl", None),
        ("file", "data.ttl", None),
        ("file", "meta.ttl", None),
    ]
    assert next(iter(partitions))[1] == entry["path"]
    assert [_value(p, "class_label_coverage") for p in partitions.values()] == [(0, 0), (2, 2), (0, 0), (1, 1)]
    _sums_equal_the_file(entry)


def test_an_imported_dataset_partitions_its_terms_by_its_own_graphs(capsys: pytest.CaptureFixture[str]) -> None:
    (entry,) = _report([DATASET_CLOSURE, "--follow-imports"], capsys)["files"]
    partitions = _partitions(entry)
    # The graphs are the imported file's, under its path; the root, a Turtle file, has none.
    assert [(by, Path(path or "").name, name) for by, path, name in partitions] == [
        ("file", "root.ttl", None),
        ("file", "part.trig", None),
        ("graph", "part.trig", "(default graph)"),
        ("graph", "part.trig", "http://example.org/g1"),
        ("graph", "part.trig", "http://example.org/g2"),
    ]
    # ex:R is declared by the root, so it is in no graph of part.trig, though g2 mentions it.
    assert [_value(p, "class_label_coverage") for p in partitions.values()] == [(0, 1), (1, 2), (0, 0), (1, 1), (0, 1)]
    _sums_equal_the_file(entry)


def _sums_equal_the_file(entry: Mapping[str, Any]) -> None:
    """Each term is in one closure file, so the file partitions add up to the file's own record."""
    files = [p for p in entry["measurement_partitions"] if p["by"] == "file"]
    whole = {m["id"]: m for m in entry["measurements"]}
    for measurement_id in PARTITIONED:
        parts = [next(m for m in p["measurements"] if m["id"] == measurement_id) for p in files]
        if "reason" in whole[measurement_id]:
            assert {m.get("reason") for m in parts} == {whole[measurement_id]["reason"]}
        elif whole[measurement_id]["kind"] == "histogram":
            counts: dict[int, int] = {}
            for m in parts:
                for bucket in m["buckets"]:
                    counts[bucket["value"]] = counts.get(bucket["value"], 0) + bucket["count"]
            assert sorted(counts.items()) == [(b["value"], b["count"]) for b in whole[measurement_id]["buckets"]]
        else:
            assert sum(m["numerator"] for m in parts) == whole[measurement_id]["numerator"], measurement_id
            assert sum(m["denominator"] for m in parts) == whole[measurement_id]["denominator"], measurement_id


def test_a_closure_of_the_root_alone_has_one_file_partition(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    onto = _write(tmp_path, "onto.ttl", PREFIXES + "a:A a owl:Class .\n")
    (entry,) = _report([onto, "--follow-imports"], capsys)["files"]
    assert list(_partitions(entry)) == [("file", entry["path"], None)]
    assert _value(entry["measurement_partitions"][0], "class_label_coverage") == (0, 1)


def test_a_file_without_modules_graphs_or_closure_has_no_partitions(capsys: pytest.CaptureFixture[str]) -> None:
    (entry,) = _report([str(FIXTURES / "kitchen_sink.ttl")], capsys)["files"]
    assert "measurement_partitions" not in entry


def test_shapes_make_the_shacl_coverage_of_a_partition_a_measurement(capsys: pytest.CaptureFixture[str]) -> None:
    shapes = str(FIXTURES / "modular" / "shapes.ttl")
    (entry,) = _report([MODULAR, "--follow-imports", "--shapes", shapes], capsys)["files"]
    whole = next(m for m in entry["measurements"] if m["id"] == "shacl_class_target_coverage")
    assert "reason" not in whole
    _sums_equal_the_file(entry)


def test_an_absent_measurement_is_absent_in_every_partition(capsys: pytest.CaptureFixture[str]) -> None:
    (entry,) = _report([TWO_GRAPHS], capsys)["files"]
    reasons = {
        next(m for m in p["measurements"] if m["id"] == "shacl_class_target_coverage").get("reason")
        for p in entry["measurement_partitions"]
    }
    assert reasons == {"no SHACL shapes graph was supplied"}


def test_an_unresolved_module_annotation_is_reported_once(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    onto = _write(tmp_path, "onto.ttl", PREFIXES + "a:A a owl:Class .\n")
    code = main([onto, "--format", "json", "--measurements", "--module-annotation", "nope:native"])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.err.count("TOOL006") == 1
    assert "measurement_partitions" not in json.loads(captured.out)["files"][0]


# --- restriction ------------------------------------------------------------------------------------------------


def test_restrict_keeps_the_terms_of_both_sets_and_leaves_absence_alone() -> None:
    a, b, c = (URIRef(f"https://example.test/{n}") for n in "abc")
    assert measurements.restrict(TermRatio(frozenset({a}), frozenset({a, b})), {a, c}) == TermRatio(
        frozenset({a}), frozenset({a})
    )
    restricted = measurements.restrict(TermValues({a: 3, b: 1}), {b})
    assert isinstance(restricted, TermValues)
    assert dict(restricted.values) == {b: 1}
    assert measurements.restrict(Absent("why"), {a}) == Absent("why")
    for value in (Count(1), CountRatio(1, 2)):
        with pytest.raises(TypeError, match="is not of terms"):
            measurements.restrict(value, {a})


def test_a_partition_of_a_value_that_is_not_of_terms_is_published_absent() -> None:
    spec = measurements.spec_of("class_label_coverage")
    (published,) = measurements.partition([(spec, Count(2))], set())
    assert published.reason == "failed: TypeError: a Count is not of terms"


def test_a_partition_names_its_kind() -> None:
    with pytest.raises(ValueError, match="a partition is by one of"):
        MeasurementPartition("namespace", None, "x", ())
    masked = MeasurementPartition("module", None, "https://u:pw@x.test/#", ())
    assert masked.to_dict() == {"by": "module", "name": "https://****@x.test/#", "measurements": []}


def test_partition_terms_are_spelled_as_finding_foci() -> None:
    graph = Graph()
    for term in (URIRef(""), URIRef("https://u:pw@ext.test/x#A"), URIRef("https://v:pw2@ext.test/x#A")):
        graph.add((term, RDF.type, OWL.Class))
    terms = measurements.partition_terms(build_context(graph, None, Policy()))
    assert sorted(terms) == ["<>", "https://****@ext.test/x#A"]
    assert terms["https://****@ext.test/x#A"] == {
        URIRef("https://u:pw@ext.test/x#A"),
        URIRef("https://v:pw2@ext.test/x#A"),
    }


def test_the_empty_iri_is_in_no_module_and_in_the_root_file() -> None:
    graph = Graph()
    graph.add((URIRef(""), RDF.type, OWL.Class))
    graph.add((URIRef("https://example.test/a#A"), RDF.type, OWL.Class))
    item = resolve_inputs([str(FIXTURES / "clean.ttl")], FIXTURES)[0]
    texts = {"<>": None, "https://example.test/a#A": None}
    places = cli._term_places(item, loaded_graph(graph), texts, cli._ModuleGrouping(None))
    assert places == {("module", None, "https://example.test/a#"): {"https://example.test/a#A"}}


# --- parity with the placement of findings ----------------------------------------------------------------------


def _placed_run(argv: list[str]) -> tuple[dict[str, Any], Places]:
    """The JSON report of ``argv`` with ``--measurements``, and the term places its one file was partitioned by."""
    seen: list[Places] = []
    original: Callable[..., Places] = cli._term_places

    def spy(*args: Any) -> Places:
        seen.append(original(*args))
        return seen[-1]

    out, err = io.StringIO(), io.StringIO()
    cli._term_places = spy  # type: ignore[assignment]
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([*argv, "--format", "json", "--measurements"])
    finally:
        cli._term_places = original  # type: ignore[assignment]
    assert code in {0, 1}, err.getvalue()
    (places,) = seen
    return json.loads(out.getvalue()), places


def assert_placed_like_findings(argv: list[str], *, compared: bool = True) -> dict[str, Any]:
    """Every term finding (LEX001, LEX002) on a placed term is in the partitions that term is in, and no other."""
    report, places = _placed_run(argv)
    (entry,) = report["files"]
    by_term: dict[str, set[tuple[str, str | None, str | None]]] = {}
    for key, texts in places.items():
        for text in texts:
            by_term.setdefault(text, set()).add(key)
    closure = any(key[0] == "file" for key in places)
    checked = 0
    for finding in report["findings"]:
        if finding["rule"] not in {"LEX001", "LEX002"} or finding["focus"] not in by_term:
            continue
        expected = {("module", None, name) for name in finding.get("modules", ())}
        expected |= {("graph", finding["path"], name) for name in finding.get("graphs", ())}
        if closure:
            expected.add(("file", finding["path"], None))
        assert by_term[finding["focus"]] == expected, finding
        checked += 1
    assert checked or not compared, "no finding was compared"
    # Every place is a partition of the report, in the same order, with the same terms counted.
    assert [(p["by"], p.get("path"), p.get("name")) for p in entry.get("measurement_partitions", ())] == list(places)
    return entry


def assert_partitions_restrict(entry: Mapping[str, Any]) -> None:
    """A partition counts no more than its file, and holds the partitioned measurements only."""
    whole = {m["id"]: m for m in entry["measurements"]}
    for partition in entry.get("measurement_partitions", ()):
        assert [m["id"] for m in partition["measurements"]] == PARTITIONED
        for m in partition["measurements"]:
            if m["kind"] == "ratio" and "reason" not in m:
                assert m["numerator"] <= whole[m["id"]]["numerator"], m
                assert m["denominator"] <= whole[m["id"]]["denominator"], m
            if m["kind"] == "histogram":
                assert sum(b["count"] for b in m["buckets"]) <= sum(b["count"] for b in whole[m["id"]]["buckets"])


@pytest.mark.parametrize(
    "argv",
    [
        [TWO_GRAPHS, "--module-by", "namespace"],
        [MODULAR, "--follow-imports", "--module-by", "namespace"],
        [str(FIXTURES / "kitchen_sink.ttl"), "--module-by", "namespace"],
        [str(FIXTURES / "datasets" / "single_graph.trig"), "--module-by", "namespace"],
        [DATASET_CLOSURE, "--follow-imports", "--module-by", "namespace"],
    ],
    ids=["graphs", "closure", "kitchen", "trig", "dataset-closure"],
)
def test_terms_are_placed_like_their_findings(argv: list[str]) -> None:
    assert_partitions_restrict(assert_placed_like_findings(argv))


def test_a_credentialed_term_is_placed_under_its_masked_spelling(tmp_path: Path) -> None:
    onto = _write(
        tmp_path,
        "onto.ttl",
        "<https://u:pw@ext.test/x> a <http://www.w3.org/2002/07/owl#Ontology> .\n"
        "<https://u:pw@ext.test/x#A> a <http://www.w3.org/2002/07/owl#Class> .\n",
    )
    entry = assert_placed_like_findings([onto, "--module-by", "namespace"])
    assert list(_partitions(entry)) == [("module", None, "https://****@ext.test/x#")]
    assert "pw" not in json.dumps(entry)


CLASSES = ("a:A", "a:B", "a:C", "b:D", "b:E", "<https://other.example/X>")
GRAPHS = ("", "<https://example.test/g1>", "<https://example.test/g2>")


@st.composite
def trig_documents(draw: st.DrawFn) -> str:
    """A small TriG dataset: owned and foreign classes, labels, comments, subclass links and module annotations."""
    statements = [(draw(st.sampled_from(GRAPHS)), f"{c} a owl:Class") for c in draw(st.sets(st.sampled_from(CLASSES)))]
    for _ in range(draw(st.integers(0, 10))):
        subject, other = draw(st.sampled_from(CLASSES)), draw(st.sampled_from(CLASSES))
        statement = draw(
            st.sampled_from(
                [
                    f"{subject} rdfs:subClassOf {other}",
                    f'{subject} rdfs:label "l"',
                    f'{subject} rdfs:comment "c"',
                    f'{subject} opla:isNativeTo "M1"',
                    f'{subject} opla:isNativeTo "M2"',
                ]
            )
        )
        statements.append((draw(st.sampled_from(GRAPHS)), statement))
    default = "".join(f"{text} .\n" for name, text in statements if not name)
    named = ((g, [text for name, text in statements if name == g]) for g in GRAPHS[1:])
    return PREFIXES + default + "".join(f"{g} {{ {' . '.join(texts)} . }}\n" for g, texts in named if texts)


@pytest.mark.slow
@given(trig_documents(), st.sampled_from([["--module-by", "namespace"], ["--module-annotation", "opla:isNativeTo"]]))
@budget(0.3)
def test_random_datasets_place_terms_like_their_findings(document: str, grouping: list[str]) -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "onto.trig"
        path.write_text(document, encoding="utf-8")
        entry = assert_placed_like_findings([str(path), *grouping], compared=False)
    assert_partitions_restrict(entry)


def test_the_partitioned_measurements_are_those_of_owned_terms() -> None:
    graph = Graph().parse(FIXTURES / "kitchen_sink.ttl")
    ctx = build_context(graph, Graph(), Policy())
    owned = frozenset(t for terms in measurements.partition_terms(ctx).values() for t in terms)
    assert {spec.id for spec in measurements.SPECS if not spec.partitioned} == UNPARTITIONED
    for spec, value in measurements.taken(ctx):
        assert spec.partitioned == isinstance(value, TermRatio | TermValues), spec.id
        if isinstance(value, TermRatio):
            assert value.denominator <= owned
        if isinstance(value, TermValues):
            assert set(value.values) <= owned
