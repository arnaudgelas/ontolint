"""``--write-dqv``: the measurements as W3C DQV Turtle (``docs/dqv.md``).

Every kind of measurement, and an absent one, has a defined mapping; the output is deterministic, masked, typed,
parses, lints clean with ontolint's own rules, and exists only when asked for.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from rdflib import RDF, RDFS, XSD, BNode, Graph, Literal, URIRef
from rdflib.namespace import PROV

from ontolint import main
from ontolint.dqv import DQV, DqvError, Subject, build, dumps, generated_at
from ontolint.models import Measurement, MeasurementKind
from ontolint.quality import Entry, Shaping, Snapshot

FIXTURES = Path(__file__).parent / "fixtures"
BEFORE = str(FIXTURES / "quality" / "before.ttl")
RATIO_KIND, COUNT_KIND, HIST_KIND = MeasurementKind.RATIO, MeasurementKind.COUNT, MeasurementKind.HISTOGRAM
USAGE = TOOL_FAILURE = 2
STAMPS = 3  # the run's end, and each of the two values of a ratio
ONTOLOGY = "https://example.test/q"
ON = Subject((ONTOLOGY,), ())
VERSION = "0.0.0"
RATIO = Measurement("class_label_coverage", 1, RATIO_KIND, "owned_classes", numerator=3, denominator=5)
EMPTY = Measurement("orphan_classes", 1, RATIO_KIND, "owned_classes", numerator=0, denominator=0)
COUNT = Measurement("unresolved_imports", 2, COUNT_KIND, "graph", value=4)
HISTOGRAM = Measurement("class_depth", 1, HIST_KIND, "acyclic_owned_classes", buckets=((1, 4), (2, 9)))
NO_BUCKETS = Measurement("class_depth", 1, HIST_KIND, "acyclic_owned_classes")
ABSENT = Measurement(
    "shacl_class_target_coverage", 1, RATIO_KIND, "owned_classes", reason="no SHACL shapes graph was supplied"
)
FOREIGN = Measurement(
    "foreign_references",
    1,
    RATIO_KIND,
    "structural_references",
    numerator=3,
    denominator=10,
    by_namespace=(("http://purl.obolibrary.org/obo/", 3),),
)


def snapshot(*measurements: Measurement) -> Snapshot:
    return Snapshot(Shaping(), tuple(Entry(m) for m in measurements))


def graph_of(*measurements: Measurement, on: Subject = ON, generated: str | None = None) -> Graph:
    return build(snapshot(*measurements), on, tool_version=VERSION, generated=generated)


def values(g: Graph) -> dict[str, Literal]:
    """The published values by metric IRI."""
    out: dict[str, Literal] = {}
    for node in g.subjects(RDF.type, DQV.QualityMeasurement):
        (metric,) = g.objects(node, DQV.isMeasurementOf)
        (value,) = g.objects(node, DQV.value)
        assert isinstance(value, Literal)
        out[str(metric).removeprefix("urn:ontolint:metric:")] = value
    return out


# --- the mapping of each kind ---------------------------------------------------------------------------------


def test_a_ratio_is_its_numerator_and_its_denominator_and_never_the_quotient() -> None:
    assert {k: (str(v), v.datatype) for k, v in values(graph_of(RATIO)).items()} == {
        "class_label_coverage:1:numerator": ("3", XSD.integer),
        "class_label_coverage:1:denominator": ("5", XSD.integer),
    }


def test_an_empty_ratio_is_a_measurement_of_zero_over_zero() -> None:
    assert {k: str(v) for k, v in values(graph_of(EMPTY)).items()} == {
        "orphan_classes:1:numerator": "0",
        "orphan_classes:1:denominator": "0",
    }


def test_a_count_is_one_integer_and_its_definition_version_is_in_the_metric() -> None:
    ((key, value),) = values(graph_of(COUNT)).items()
    assert (key, int(value), value.datatype) == ("unresolved_imports:2:value", 4, XSD.integer)


def test_a_histogram_is_a_metric_per_bucket_and_the_terms_it_counts() -> None:
    assert {k: int(v) for k, v in values(graph_of(HISTOGRAM)).items()} == {
        "class_depth:1:bucket:1": 4,
        "class_depth:1:bucket:2": 9,
        "class_depth:1:terms": 13,
    }


def test_an_empty_histogram_is_a_taken_measurement_of_no_terms() -> None:
    assert {k: int(v) for k, v in values(graph_of(NO_BUCKETS)).items()} == {"class_depth:1:terms": 0}


def test_an_absent_measurement_is_not_published_as_zero_and_the_run_says_why() -> None:
    g = graph_of(ABSENT, RATIO)
    assert set(values(g)) == {"class_label_coverage:1:numerator", "class_label_coverage:1:denominator"}
    assert not any("shacl_class_target_coverage" in str(s) for s in g.subjects())
    (run,) = g.subjects(RDF.type, PROV.Activity)
    notes = [str(c) for c in g.objects(run, RDFS.comment)]
    assert notes == ["not measured: shacl_class_target_coverage: no SHACL shapes graph was supplied"]


def test_a_run_that_measured_everything_makes_no_not_measured_note() -> None:
    assert "not measured" not in dumps(snapshot(RATIO), ON, tool_version=VERSION)


def test_by_namespace_is_not_published() -> None:
    text = dumps(snapshot(FOREIGN), ON, tool_version=VERSION)
    assert "obolibrary" not in text
    assert set(values(graph_of(FOREIGN))) == {"foreign_references:1:numerator", "foreign_references:1:denominator"}


def test_every_value_is_an_xsd_integer_never_a_float_or_a_decimal() -> None:
    g = graph_of(RATIO, EMPTY, COUNT, HISTOGRAM, FOREIGN)
    assert {v.datatype for v in values(g).values()} == {XSD.integer}
    assert "." not in "".join(str(v) for v in values(g).values())


def test_every_taken_measurement_of_a_real_run_is_published_and_the_absent_ones_are_not(tmp_path: Path) -> None:
    snap, out = tmp_path / "snap.json", tmp_path / "dqv.ttl"
    assert main([BEFORE, "--write-quality-snapshot", str(snap), "--write-dqv", str(out)]) == 0
    document = json.loads(snap.read_text(encoding="utf-8"))
    taken = [m for m in document["measurements"] if "reason" not in m]
    absent = [m for m in document["measurements"] if "reason" in m]
    assert absent, "the fixture has no shapes graph, so a measurement is absent"
    published = values(Graph().parse(out))
    for m in taken:
        if m["kind"] == RATIO_KIND:
            assert int(published[f"{m['id']}:1:numerator"]) == m["numerator"]
            assert int(published[f"{m['id']}:1:denominator"]) == m["denominator"]
        elif m["kind"] == COUNT_KIND:
            assert int(published[f"{m['id']}:1:value"]) == m["value"]
        else:
            assert int(published[f"{m['id']}:1:terms"]) == sum(b[COUNT_KIND] for b in m["buckets"])
    assert not any(a["id"] in key for a in absent for key in published)


# --- the shape of the graph -----------------------------------------------------------------------------------


def test_a_measurement_has_its_dqv_properties() -> None:
    g = graph_of(COUNT)
    (node,) = g.subjects(RDF.type, DQV.QualityMeasurement)
    (run,) = g.subjects(RDF.type, PROV.Activity)
    assert set(g.objects(node, DQV.computedOn)) == {URIRef(ONTOLOGY)}
    assert set(g.objects(node, PROV.wasGeneratedBy)) == {run}
    (metric,) = g.objects(node, DQV.isMeasurementOf)
    assert (metric, RDF.type, DQV.Metric) in g
    assert set(g.objects(metric, DQV.expectedDataType)) == {XSD.integer}


def test_the_run_names_the_tool_and_its_version() -> None:
    g = graph_of(COUNT)
    (run,) = g.subjects(RDF.type, PROV.Activity)
    (tool,) = g.objects(run, PROV.wasAssociatedWith)
    assert str(tool) == "urn:ontolint:tool:0.0.0"
    assert (tool, RDF.type, PROV.SoftwareAgent) in g


def test_findings_are_not_published_as_quality_annotations() -> None:
    assert "QualityAnnotation" not in dumps(snapshot(RATIO, COUNT), ON, tool_version=VERSION)


def test_no_blank_node_and_every_minted_iri_is_in_the_urn_namespace() -> None:
    g = graph_of(RATIO, COUNT, HISTOGRAM, ABSENT)
    assert not any(isinstance(n, BNode) for t in g for n in t)
    minted = {s for s in g.subjects() if isinstance(s, URIRef)}
    assert minted
    assert all(str(s).startswith("urn:ontolint:") for s in minted)


def test_the_version_iri_is_what_the_measurements_are_computed_on() -> None:
    g = graph_of(COUNT, on=Subject((ONTOLOGY,), (ONTOLOGY + "/1.0",)))
    (node,) = g.subjects(RDF.type, DQV.QualityMeasurement)
    assert set(g.objects(node, DQV.computedOn)) == {URIRef(ONTOLOGY + "/1.0")}


@pytest.mark.parametrize(
    "on",
    [Subject((), ()), Subject((ONTOLOGY, ONTOLOGY + "2"), ()), Subject((ONTOLOGY,), ("urn:a", "urn:b"))],
    ids=["none", "two ontologies", "two versions"],
)
def test_an_ambiguous_ontology_is_refused(on: Subject) -> None:
    with pytest.raises(DqvError, match="--write-dqv needs"):
        graph_of(COUNT, on=on)


# --- determinism ----------------------------------------------------------------------------------------------


def test_a_run_has_no_timestamp_unless_one_is_supplied() -> None:
    assert "Time" not in dumps(snapshot(RATIO), ON, tool_version=VERSION)
    stamped = dumps(snapshot(RATIO), ON, tool_version=VERSION, generated="2026-01-02T03:04:05Z")
    assert stamped.count('"2026-01-02T03:04:05+00:00"^^xsd:dateTime') == STAMPS


def test_the_same_snapshot_gives_the_same_text_with_a_final_newline() -> None:
    a = dumps(snapshot(RATIO, COUNT, HISTOGRAM), ON, tool_version=VERSION)
    assert a == dumps(snapshot(RATIO, COUNT, HISTOGRAM), ON, tool_version=VERSION)
    assert a.endswith("\n")
    assert "\r" not in a


def test_another_value_is_another_run_and_the_same_metric_is_another_measurement() -> None:
    other = Measurement("class_label_coverage", 1, RATIO_KIND, "owned_classes", numerator=4, denominator=5)
    one, two = graph_of(RATIO), graph_of(other)
    assert set(one.subjects(RDF.type, PROV.Activity)).isdisjoint(two.subjects(RDF.type, PROV.Activity))
    assert set(one.subjects(RDF.type, DQV.QualityMeasurement)).isdisjoint(
        two.subjects(RDF.type, DQV.QualityMeasurement)
    )


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        ({}, None),
        ({"SOURCE_DATE_EPOCH": ""}, None),
        ({"SOURCE_DATE_EPOCH": "0"}, "1970-01-01T00:00:00Z"),
        ({"SOURCE_DATE_EPOCH": "1767323045"}, "2026-01-02T03:04:05Z"),
    ],
)
def test_source_date_epoch_is_the_only_clock(environ: dict[str, str], expected: str | None) -> None:
    assert generated_at(environ) == expected


@pytest.mark.parametrize("raw", ["yesterday", "-1", "1.5", " 1", "1e3", "99999999999999999999", "١٢"])
def test_a_source_date_epoch_that_is_not_a_date_is_refused(raw: str) -> None:
    with pytest.raises(DqvError, match="SOURCE_DATE_EPOCH"):
        generated_at({"SOURCE_DATE_EPOCH": raw})


# --- masking --------------------------------------------------------------------------------------------------


def test_credentials_in_the_ontology_iri_and_the_reason_are_masked() -> None:
    secret = "https://user:hunter2@host.test/onto"  # noqa: S105 -- a fixture, not a credential
    reason = Measurement("x_coverage", 1, RATIO_KIND, "p", reason="read https://bob:pw9@h.test/shapes failed")
    text = dumps(snapshot(COUNT, reason), Subject((secret,), (secret + "/1",)), tool_version=VERSION)
    assert "hunter2" not in text
    assert "pw9" not in text
    assert "user:" not in text
    assert "bob" not in text
    assert "https://****@host.test/onto/1" in text
    assert "https://****@h.test/shapes" in text


def test_two_credentials_give_the_same_masked_report() -> None:
    one = dumps(snapshot(COUNT), Subject(("https://a:b@h.test/o",), ()), tool_version=VERSION)
    two = dumps(snapshot(COUNT), Subject(("https://c:d@h.test/o",), ()), tool_version=VERSION)
    assert one == two


def test_a_credentialed_ontology_in_a_real_run_leaks_nothing(tmp_path: Path) -> None:
    source = tmp_path / "onto.ttl"
    source.write_text(
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
        "<https://user:hunter2@host.test/o> a owl:Ontology ; owl:versionIRI <https://user:hunter2@host.test/o/1> .\n"
        '<https://user:hunter2@host.test/o/A> a owl:Class ; rdfs:label "A"@en .\n',
        encoding="utf-8",
    )
    out = tmp_path / "dqv.ttl"
    assert main([str(source), "--write-dqv", str(out)]) in (0, 1)
    text = out.read_text(encoding="utf-8")
    assert "hunter2" not in text
    assert "https://****@host.test/o/1" in text


# --- the CLI --------------------------------------------------------------------------------------------------


def run_cli(*argv: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- the interpreter running the tests
        [sys.executable, "-m", "ontolint", *argv],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "SOURCE_DATE_EPOCH": "", **(env or {})},
    )


def test_the_published_graph_parses_and_the_file_is_byte_stable_across_processes(tmp_path: Path) -> None:
    runs: list[bytes] = []
    for seed in ("0", "1", "12345"):
        out = tmp_path / f"dqv-{seed}.ttl"
        done = run_cli(BEFORE, "--write-dqv", str(out), env={"PYTHONHASHSEED": seed})
        assert done.returncode in (0, 1), done.stderr
        runs.append(out.read_bytes())
    assert runs[0] == runs[1] == runs[2]
    assert len(Graph().parse(data=runs[0], format="turtle")) > 0


def test_source_date_epoch_dates_the_run_and_the_file_stays_stable(tmp_path: Path) -> None:
    out1, out2 = tmp_path / "a.ttl", tmp_path / "b.ttl"
    for out in (out1, out2):
        done = run_cli(BEFORE, "--write-dqv", str(out), env={"SOURCE_DATE_EPOCH": "1767323045"})
        assert done.returncode in (0, 1), done.stderr
    assert out1.read_bytes() == out2.read_bytes()
    assert "2026-01-02T03:04:05+00:00" in out1.read_text(encoding="utf-8")


def test_the_published_graph_lints_clean_with_ontolints_own_rules(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "dqv.ttl"
    assert main([BEFORE, "--write-dqv", str(out)]) in (0, 1)
    capsys.readouterr()
    # The one finding the file earns is ONT001: it is a data file, not a published ontology, so it has no header
    # (and inventing a licence and a creator for one would be worse); every other rule is silent, at every severity.
    assert main([str(out), "--format", "json", "--fail-on", "never"]) == 0
    assert [f["rule"] for f in json.loads(capsys.readouterr().out)["findings"]] == ["ONT001"]
    assert main([str(out), "--format", "json", "--ignore", "ONT001", "--fail-on", "info"]) == 0
    report: Any = json.loads(capsys.readouterr().out)
    assert report["findings"] == []
    assert report["execution_summary"]["failed"] == 0


def test_the_values_are_those_of_the_snapshot_the_same_run_writes(tmp_path: Path) -> None:
    snap, out = tmp_path / "snap.json", tmp_path / "dqv.ttl"
    assert main([BEFORE, "--write-quality-snapshot", str(snap), "--write-dqv", str(out)]) == 0
    first = json.loads(snap.read_text(encoding="utf-8"))["measurements"][0]
    assert int(values(Graph().parse(out))[f"{first['id']}:1:numerator"]) == first["numerator"]


def test_the_flag_changes_nothing_else_about_the_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main([BEFORE, "--format", "json"])
    plain = capsys.readouterr()
    assert main([BEFORE, "--format", "json", "--write-dqv", str(tmp_path / "d.ttl")]) == code
    assert capsys.readouterr().out == plain.out


def test_two_ontologies_are_a_usage_error(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as raised:
        main([BEFORE, BEFORE, "--write-dqv", str(tmp_path / "d.ttl")])
    assert raised.value.code == USAGE
    assert "--write-dqv" in capsys.readouterr().err


def test_compare_quality_takes_no_dqv_option(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["--compare-quality", "a", "b", "--write-dqv", str(tmp_path / "d.ttl")])
    assert raised.value.code == USAGE


def test_an_ontology_without_an_iri_is_a_tool_failure_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source, out = tmp_path / "o.ttl", tmp_path / "d.ttl"
    source.write_text("@prefix owl: <http://www.w3.org/2002/07/owl#> .\n<urn:x:A> a owl:Class .\n", encoding="utf-8")
    assert main([str(source), "--write-dqv", str(out)]) == TOOL_FAILURE
    assert "TOOL001: --write-dqv needs exactly one owl:Ontology IRI" in capsys.readouterr().err
    assert not out.exists()


def test_a_bad_source_date_epoch_is_a_tool_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "tomorrow")
    assert main([BEFORE, "--write-dqv", str(tmp_path / "d.ttl")]) == TOOL_FAILURE
    assert "SOURCE_DATE_EPOCH" in capsys.readouterr().err


def test_an_unwritable_destination_is_a_tool_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([BEFORE, "--write-dqv", str(tmp_path / "missing" / "d.ttl")]) == TOOL_FAILURE
    assert "DQV report" in capsys.readouterr().err


# --- free text and IRIs are written without a control, format or separator character (#136) -----------------------

HOSTILE_REASON = "boom \x1b[31m\nline two \u202e bidi \u2028 sep \x00 nul \ud800 lone"
ESCAPED_REASON = "boom \\u001B[31m\\u000Aline two \\u202E bidi \\u2028 sep \\u0000 nul \\uD800 lone"


def raw_characters(text: str) -> set[str]:
    """The characters of ``text`` a line-oriented reader or a terminal acts on, apart from its own line ends."""
    import unicodedata  # noqa: PLC0415 -- one test helper

    return {c for c in text if c not in "\n " and unicodedata.category(c) in {"Cc", "Cf", "Cs", "Co", "Zl", "Zp", "Zs"}}


def test_a_reason_with_control_format_and_separator_characters_is_written_with_none_of_them_raw() -> None:
    text = dumps(
        snapshot(Measurement("class_depth", 1, HIST_KIND, "acyclic_owned_classes", reason=HOSTILE_REASON)),
        ON,
        tool_version=VERSION,
    )

    assert raw_characters(text) == set()
    text.encode("utf-8")  # strict: a lone surrogate would raise


def test_the_escaped_reason_is_the_text_the_text_report_shows() -> None:
    g = Graph().parse(
        data=dumps(
            snapshot(Measurement("class_depth", 1, HIST_KIND, "acyclic_owned_classes", reason=HOSTILE_REASON)),
            ON,
            tool_version=VERSION,
        ),
        format="turtle",
    )

    comments = [str(o) for o in g.objects(None, RDFS.comment)]

    assert comments == [f"not measured: class_depth: {ESCAPED_REASON}"]


def test_a_no_break_space_and_an_astral_character_in_a_reason_are_escaped() -> None:
    g = graph_of(Measurement("class_depth", 1, HIST_KIND, "acyclic_owned_classes", reason="a\u00a0b\U000e0001c"))

    assert [str(o) for o in g.objects(None, RDFS.comment)] == ["not measured: class_depth: a\\u00A0b\\U000E0001c"]


def test_a_reason_in_ordinary_text_is_written_as_it_is() -> None:
    reason = "no SHACL shapes graph was supplied: café 本体論 [brackets] 'quotes' \"double\" back\\slash"
    g = graph_of(Measurement("class_depth", 1, HIST_KIND, "acyclic_owned_classes", reason=reason))

    assert [str(o) for o in g.objects(None, RDFS.comment)] == [f"not measured: class_depth: {reason}"]


def test_an_ontology_iri_with_control_or_separator_characters_is_written_as_a_valid_turtle_iri() -> None:
    on = Subject(("https://e.test/a\x1bb\u202ec d\u2028e<f>",), ())

    text = dumps(snapshot(RATIO), on, tool_version=VERSION)

    assert raw_characters(text) == set()
    assert "https://e.test/a%1Bb%E2%80%AEc%20d%E2%80%A8e%3Cf%3E" in text
    assert Graph().parse(data=text, format="turtle")  # it parses: the IRI of the file is a Turtle IRIREF


def test_an_ordinary_ontology_iri_is_unchanged() -> None:
    on = Subject(("https://example.test/q/café#本体?x=1&y=%20",), ())

    assert "<https://example.test/q/café#本体?x=1&y=%20>" in dumps(snapshot(RATIO), on, tool_version=VERSION)
