"""``--measurements``: the vector in the JSON report, which changes nothing else (``docs/measurements.md``)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any

import pytest
from rdflib import Graph
from rule_harness import graph
from test_differential import CLI_CASES, _fake_robot

from ontolint import main
from ontolint.engine import build_context
from ontolint.models import Measurement, MeasurementKind, MeasurementPartition
from ontolint.policy import Policy
from ontolint.reporting import FileReport, RunReport, to_json
from ontolint.rules import measurements, metrics
from ontolint.rules.measurements import Absent, Count, TermValues
from ontolint.rules.runtime import RuleContext

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
KITCHEN = str(FIXTURES / "kitchen_sink.ttl")
KEYS = ("measurements", "measurement_partitions")
USAGE_ERROR = 2


def _ratio(measurement_id: str, population: str, numerator: int, denominator: int, **extra: Any) -> dict[str, Any]:
    head = {"id": measurement_id, "definition_version": 1, "kind": "ratio", "population": population}
    return {**head, "numerator": numerator, "denominator": denominator, **extra}


def _count(measurement_id: str, population: str, value: int) -> dict[str, Any]:
    return {"id": measurement_id, "definition_version": 1, "kind": "count", "population": population, "value": value}


NO_SHAPES = {
    "id": "shacl_class_target_coverage",
    "definition_version": 1,
    "kind": "ratio",
    "population": "owned_classes",
    "reason": "no SHACL shapes graph was supplied",
}
KITCHEN_VECTOR = [
    _ratio("class_label_coverage", "owned_classes", 32, 33),
    _ratio("class_definition_coverage", "owned_classes", 6, 33),
    _ratio("property_documentation_coverage", "owned_properties", 1, 14),
    _ratio("class_fanout", "owned_parent_classes", 15, 14),
    _ratio("orphan_classes", "owned_classes", 6, 33),
    _ratio("relation_properties_per_class", "owned_classes", 14, 33),
    _ratio("unsigned_properties", "owned_object_and_datatype_properties", 3, 14),
    _ratio("label_language_coverage", "labelled_owned_terms", 2, 46),
    _ratio("foreign_references", "structural_references", 0, 36, by_namespace=[]),
    _count("unresolved_imports", "graph", 1),
    _ratio("definition_length", "defined_owned_classes", 7, 6),
    _ratio("blank_subjects", "non_structural_subjects", 0, 58),
    {
        "id": "class_depth",
        "definition_version": 1,
        "kind": "histogram",
        "population": "acyclic_owned_classes",
        "buckets": [{"value": v, "count": n} for v, n in ((1, 22), (2, 4), (3, 2), (4, 1), (5, 1), (6, 1))],
    },
    _ratio("cyclic_classes", "owned_classes", 2, 33),
    _count("hierarchy_components", "owned_classes", 20),
    NO_SHAPES,
]


def _run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    code = main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _vector(argv: list[str], capsys: pytest.CaptureFixture[str], index: int = 0) -> list[dict[str, Any]]:
    code, out, _err = _run([*argv, "--format", "json", "--measurements"], capsys)
    assert code in {0, 1}
    return json.loads(out)["files"][index]["measurements"]


def _without_measurements(document: dict[str, Any]) -> dict[str, Any]:
    files = [{k: v for k, v in entry.items() if k not in KEYS} for entry in document["files"]]
    return {**document, "files": files}


# --- the vector ------------------------------------------------------------------------------------------------


def test_the_kitchen_sink_vector(capsys: pytest.CaptureFixture[str]) -> None:
    assert _vector([KITCHEN], capsys) == KITCHEN_VECTOR


def test_the_vector_follows_executions_and_module_summary(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _err = _run([KITCHEN, "--format", "json", "--measurements", "--module-by", "namespace"], capsys)
    assert code == 1  # the kitchen sink has error findings
    entry = json.loads(out)["files"][0]
    assert list(entry)[:6] == ["path", "summary", "execution_summary", "executions", "module_summary", "measurements"]


def test_shapes_make_the_shacl_coverage_a_measurement(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    shapes = str(FIXTURES / "kitchen_shapes.ttl")
    assert _vector([KITCHEN, "--shapes", shapes], capsys)[-1] == _ratio(
        "shacl_class_target_coverage", "owned_classes", 1, 33
    )
    empty = tmp_path / "empty.ttl"
    empty.write_text("", encoding="utf-8")
    assert _vector([KITCHEN, "--shapes", str(empty)], capsys)[-1] == _ratio(
        "shacl_class_target_coverage", "owned_classes", 0, 33
    )


def test_an_ontology_with_no_owned_term_publishes_empty_populations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    onto = tmp_path / "empty.ttl"
    onto.write_text("<https://example.test/onto> a <http://www.w3.org/2002/07/owl#Ontology> .\n", encoding="utf-8")
    vector = _vector([str(onto)], capsys)
    assert [m["id"] for m in vector] == [spec.id for spec in measurements.SPECS]
    assert {m["id"] for m in vector if "reason" in m} == {"shacl_class_target_coverage"}
    values = {m["id"]: (m.get("numerator"), m.get("denominator"), m.get("value"), m.get("buckets")) for m in vector}
    assert values["class_depth"] == (None, None, None, [])
    assert values["hierarchy_components"] == (None, None, 0, None)
    assert values["unresolved_imports"] == (None, None, 0, None)
    # The only subject is the header, which is no structural blank node.
    assert values["blank_subjects"] == (0, 1, None, None)
    ratios = {k: v for k, v in values.items() if v[0] is not None and k != "blank_subjects"}
    assert set(ratios.values()) == {(0, 0, None, None)}


def test_each_file_has_its_own_vector_and_a_baseline_keeps_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    clean = str(FIXTURES / "clean.ttl")
    _code, out, _err = _run([KITCHEN, clean, "--format", "json", "--measurements"], capsys)
    files = {Path(entry["path"]).name: entry["measurements"] for entry in json.loads(out)["files"]}
    assert files["kitchen_sink.ttl"] == KITCHEN_VECTOR
    assert files["clean.ttl"] != KITCHEN_VECTOR
    assert files["clean.ttl"] == _vector([clean], capsys)
    base = tmp_path / "baseline.json"
    main([KITCHEN, "--write-baseline", str(base)])
    capsys.readouterr()
    assert _vector([KITCHEN, "--baseline", str(base)], capsys) == KITCHEN_VECTOR


# --- nothing else changes ----------------------------------------------------------------------------------------

JSON_CASES = sorted(
    name
    for name, (argv, _robot) in CLI_CASES.items()
    if "json" in argv and not {"--list-rules", "--explain"} & set(argv)
)


def _case(name: str, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    argv, robot = CLI_CASES[name]
    monkeypatch.chdir(FIXTURES)
    if robot is not None:
        monkeypatch.setattr("ontolint.engine.shutil.which", lambda _: "docker" if robot >= 0 else None)
        monkeypatch.setattr("ontolint.ontolint.subprocess.run", _fake_robot(max(robot, 0)))
    return argv


@pytest.mark.parametrize("name", JSON_CASES)
def test_the_flag_adds_the_vector_and_changes_nothing_else(
    name: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = _case(name, monkeypatch)
    plain = _run(argv, capsys)
    measured = _run([*argv, "--measurements"], capsys)
    assert measured[0] == plain[0]
    assert measured[2] == plain[2]
    document = json.loads(measured[1])
    assert all(len(entry["measurements"]) == len(measurements.SPECS) for entry in document["files"])
    assert _without_measurements(document) == json.loads(plain[1])


@pytest.mark.parametrize("name", sorted(CLI_CASES))
def test_without_the_flag_nothing_is_measured_beyond_the_rules(
    name: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A default run never publishes, nor computes what no rule reads: both would raise here.
    def boom(*_args: object) -> Any:
        raise AssertionError("measured without --measurements")

    for name_ in ("publish", "taken", "partition", "partition_terms"):
        monkeypatch.setattr(measurements, name_, boom)
    specs = tuple(spec if spec.rules else replace(spec, compute=boom) for spec in measurements.SPECS)
    monkeypatch.setattr(measurements, "SPECS", specs)
    argv = _case(name, monkeypatch)
    code, out, err = _run(argv, capsys)
    monkeypatch.undo()
    _case(name, monkeypatch)
    assert (code, out, err) == _run(argv, capsys)


@pytest.mark.parametrize(
    "argv",
    [
        [KITCHEN, "--select", "ONT"],
        [KITCHEN, "--ignore", "METRIC"],
        [KITCHEN, "--profile", "minimal"],
        [KITCHEN, "--profile", "strict"],
        [KITCHEN, "--config", str(FIXTURES / "policy.json")],
    ],
    ids=["select", "ignore", "minimal", "strict", "config"],
)
def test_the_vector_does_not_depend_on_selection_profiles_or_thresholds(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert _vector(argv, capsys) == KITCHEN_VECTOR


def test_the_vector_does_not_depend_on_metric_thresholds(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = tmp_path / "policy.json"
    forced = {"metric_min_sample": 1, "metric_max_orphan_ratio": 0.0, "metric_max_imports": 0}
    config.write_text(json.dumps(forced), encoding="utf-8")
    assert _vector([KITCHEN, "--config", str(config)], capsys) == KITCHEN_VECTOR


@pytest.mark.parametrize(
    "argv",
    [[KITCHEN], [KITCHEN, "--format", "text"], [KITCHEN, "--format", "sarif"]],
    ids=["default", "text", "sarif"],
)
def test_the_flag_needs_the_json_format(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main([*argv, "--measurements"])
    assert raised.value.code == USAGE_ERROR
    assert "--measurements requires --format json" in capsys.readouterr().err


@pytest.mark.parametrize("info", [["--version"], ["--list-rules"], ["--explain", "METRIC001"]])
def test_the_info_commands_answer_before_the_usage_check(info: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    expected = _run(info, capsys)
    assert _run([*info, "--measurements"], capsys) == expected


def test_a_failing_computation_is_published_absent_and_changes_nothing_else(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(_ctx: RuleContext, _term: object) -> bool:
        raise ValueError("boom https://u:secret@example.test/x")

    argv = [KITCHEN, "--format", "json", "--ignore", "METRIC"]
    monkeypatch.setattr(measurements, "is_unlabelled", boom)
    plain = _run(argv, capsys)
    code, out, err = _run([*argv, "--measurements"], capsys)
    assert (code, err) == (plain[0], plain[2])
    vector = json.loads(out)["files"][0]["measurements"]
    assert vector[0] == {
        "id": "class_label_coverage",
        "definition_version": 1,
        "kind": "ratio",
        "population": "owned_classes",
        "reason": "failed: ValueError: boom https://****@example.test/x",
    }
    assert vector[1:] == KITCHEN_VECTOR[1:]


def test_a_value_that_does_not_fit_its_kind_is_published_absent() -> None:
    spec = measurements.spec_of("class_depth")
    assert measurements.record(spec, Count(3)).reason == "failed: TypeError: class_depth is not a histogram"
    count_spec = measurements.spec_of("unresolved_imports")
    assert (
        measurements.record(count_spec, TermValues({})).reason == "failed: TypeError: unresolved_imports is not a count"
    )
    assert measurements.record(count_spec, Absent("r")).to_dict()["reason"] == "r"


# --- determinism and userinfo -----------------------------------------------------------------------------------


def _hashed_run(seed: int) -> str:
    done = subprocess.run(  # noqa: S603 -- fixed interpreter and module.
        [sys.executable, "-m", "ontolint", KITCHEN, str(FIXTURES / "clean.ttl"), "--format", "json", "--measurements"],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONHASHSEED": str(seed)},
        cwd=FIXTURES,
    )
    assert done.returncode == 1, done.stderr  # the kitchen sink has error findings
    return done.stdout


def test_the_vector_does_not_depend_on_the_hash_seed() -> None:
    first = _hashed_run(0)
    assert first == _hashed_run(12345)
    assert json.loads(first)["files"][1]["measurements"] == KITCHEN_VECTOR


@pytest.mark.parametrize("extension", ["nt", "rdf", "trig"])
def test_the_vector_does_not_depend_on_the_syntax(extension: str, capsys: pytest.CaptureFixture[str]) -> None:
    twin = _vector([str(FIXTURES / "datasets" / f"single_graph.{extension}")], capsys)
    assert twin == _vector([str(FIXTURES / "datasets" / "single_graph.ttl")], capsys)


CREDENTIALED = (
    "<https://example.test/onto> a owl:Ontology ."
    " ex:A a owl:Class ; rdfs:subClassOf <https://u:pw@ext.test/x#A> ."
    " ex:B a owl:Class ; rdfs:subClassOf <https://v:pw2@ext.test/x#B> ."
)


def test_namespaces_are_masked_and_merged_before_the_report_is_rendered() -> None:
    ctx = build_context(graph(CREDENTIALED), None, Policy())
    published = measurements.publish(ctx)
    (foreign,) = [m for m in published if m.id == "foreign_references"]
    assert foreign.by_namespace == (("https://****@ext.test/x#", 2),)
    report = RunReport((FileReport("onto.ttl", "file:///onto.ttl", (), measurements=published),))
    rendered = json.dumps(to_json(report))
    assert "pw" not in rendered
    assert '"https://****@ext.test/x#", "count": 2' in rendered


def test_the_cli_reports_one_merged_masked_namespace(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    onto = tmp_path / "onto.ttl"
    onto.write_text(graph(CREDENTIALED).serialize(format="turtle"), encoding="utf-8")
    (foreign,) = [m for m in _vector([str(onto)], capsys) if m["id"] == "foreign_references"]
    assert foreign["by_namespace"] == [{"namespace": "https://****@ext.test/x#", "count": 2}]


# --- the record ----------------------------------------------------------------------------------------------


def test_a_record_refuses_fields_its_kind_does_not_have() -> None:
    ratio, count, histogram = MeasurementKind.RATIO, MeasurementKind.COUNT, MeasurementKind.HISTOGRAM
    for wrong in (
        {"kind": ratio, "numerator": 1},  # no denominator
        {"kind": ratio, "numerator": 1, "denominator": 2, "value": 3},
        {"kind": count},
        {"kind": count, "value": 1, "buckets": ((1, 1),)},
        {"kind": count, "value": 1, "by_namespace": (("ns", 1),)},
        {"kind": histogram, "value": 1},
        {"kind": ratio, "reason": "r", "numerator": 0},
        {"kind": histogram, "reason": "r", "buckets": ((1, 1),)},
        {"kind": ratio, "numerator": -1, "denominator": 2},
        {"kind": histogram, "buckets": ((1, -1),)},
        {"kind": ratio, "numerator": 1, "denominator": 1, "by_namespace": (("ns", -1),)},
        {"kind": "mean", "value": 1},
    ):
        with pytest.raises(ValueError, match=r"m: |'mean' is not a valid MeasurementKind"):
            Measurement("m", 1, population="p", **wrong)  # type: ignore[arg-type]


def test_a_record_emits_only_the_fields_it_has() -> None:
    head = {"id": "m", "definition_version": 2, "kind": "ratio", "population": "p"}
    assert Measurement("m", 2, MeasurementKind.RATIO, "p", numerator=0, denominator=0).to_dict() == {
        **head,
        "numerator": 0,
        "denominator": 0,
    }
    assert Measurement("m", 2, MeasurementKind.RATIO, "p", reason="https://a:b@x.test/").to_dict() == {
        **head,
        "reason": "https://****@x.test/",
    }
    histogram = Measurement("m", 2, MeasurementKind.HISTOGRAM, "p")
    assert histogram.to_dict() == {**head, "kind": "histogram", "buckets": []}
    assert Measurement("m", 2, "count", "p", value=0).to_dict() == {**head, "kind": "count", "value": 0}  # type: ignore[arg-type]
    masked = Measurement(
        "m", 2, MeasurementKind.RATIO, "p", numerator=1, denominator=1, by_namespace=(("https://a:b@x.test/", 1),)
    )
    assert masked.by_namespace == (("https://****@x.test/", 1),)


def test_records_are_immutable() -> None:
    # A record masks its reason and namespaces once, in __post_init__; nothing may change it afterwards.
    record = Measurement("m", 1, MeasurementKind.COUNT, "p", value=0)
    partition = MeasurementPartition("file", "o.ttl", None, (record,))
    for value, name in ((record, "reason"), (partition, "name")):
        with pytest.raises(FrozenInstanceError):
            setattr(value, name, "https://a:b@x.test/")


# --- the documentation --------------------------------------------------------------------------------------------

DOC = ROOT / "docs" / "measurements.md"
ROW = re.compile(
    r"^\| `(\w+)` \| (\d+) \| (\w+) \| `(\w+)` \| [^|]+ \| ([^|]+) \| (yes|no) \| ([^|]+) \|$", re.MULTILINE
)


def _empty_value(record: dict[str, Any]) -> str:
    if record["kind"] == "ratio":
        return f"{record['numerator']}/{record['denominator']}"
    return str(record["value"]) if record["kind"] == "count" else json.dumps(record["buckets"])


def test_the_documented_catalogue_is_the_engine_catalogue() -> None:
    rows = ROW.findall(DOC.read_text(encoding="utf-8"))
    assert [(i, int(v), k, p, r.strip(), part) for i, v, k, p, r, part, _empty in rows] == [
        (
            spec.id,
            spec.version,
            spec.kind.value,
            spec.population,
            ", ".join(spec.rules) or "none",
            "yes" if spec.partitioned else "no",
        )
        for spec in measurements.SPECS
    ]
    # The empty column is what an empty graph (and an empty shapes graph) publishes.
    published = measurements.publish(build_context(Graph(), Graph(), Policy()))
    assert [empty.strip() for *_row, empty in rows] == [_empty_value(m.to_dict()) for m in published]


def test_every_metric_bullet_names_the_measurement_it_reads() -> None:
    doc = metrics.__doc__ or ""
    bullets = dict(re.findall(r"^\* \*\*(METRIC\d{3})\.\*\*(.*?)(?=^\* \*\*|\Z)", doc, re.MULTILINE | re.DOTALL))
    for spec in measurements.SPECS:
        for rule in spec.rules:
            assert f"Reads ``{spec.id}``" in " ".join(bullets[rule].split()), rule


@pytest.mark.parametrize(
    "wrong",
    [
        {"definition_version": 0, "numerator": 1, "denominator": 1},
        {"definition_version": True, "numerator": 1, "denominator": 1},
        {"numerator": 1.0, "denominator": 2},
        {"numerator": True, "denominator": 2},
        {"kind": MeasurementKind.COUNT, "value": 1.5},
        {"kind": MeasurementKind.HISTOGRAM, "buckets": ((2, 1), (1, 1))},
        {"kind": MeasurementKind.HISTOGRAM, "buckets": ((1, 1), (1, 2))},
        {"kind": MeasurementKind.HISTOGRAM, "buckets": ((1, 1.0),)},
        {"numerator": 2, "denominator": 3, "by_namespace": (("a", 1),)},
        {"numerator": 1, "denominator": 3, "by_namespace": (("a", 1.0),)},
        {"id": "", "numerator": 1, "denominator": 1},
        {"population": "", "numerator": 1, "denominator": 1},
    ],
)
def test_a_measurement_refuses_what_the_published_schema_does_not_allow(wrong: dict[str, Any]) -> None:
    fields: dict[str, Any] = {"id": "m", "definition_version": 1, "kind": MeasurementKind.RATIO, "population": "p"}
    with pytest.raises(ValueError):
        Measurement(**{**fields, **wrong})


def test_a_measurement_that_fits_the_schema_is_accepted() -> None:
    Measurement("m", 1, MeasurementKind.HISTOGRAM, "p", buckets=((0, 2), (3, 1)))
    Measurement("m", 1, MeasurementKind.RATIO, "p", numerator=2, denominator=3, by_namespace=(("a", 1), ("b", 1)))
