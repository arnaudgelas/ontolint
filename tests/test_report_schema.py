"""The JSON Schema of the lint report (``src/ontolint/schemas/lint-report.v1.schema.json``, issue #171).

The schema is shipped in the wheel and describes ``--format json`` for ``schema_version`` 1. Its objects are open (a
consumer ignores keys it does not know, ``docs/report-compatibility.md``); its closed enumerations are generated
from the code here, so a value added to severity, confidence, execution status or measurement kind without the
schema fails. Every report shape the CLI can write is validated: the 0.16.0 samples, the same commands with the
current code, the golden CLI cases, every profile, each seed of the fuzz corpus and random hostile reports; negative
fixtures show that a missing key or a wrong type is refused.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
from collections.abc import Callable
from importlib import resources
from pathlib import Path
from typing import Any

import pytest
from fuzz import fuzzer
from hypothesis import given
from hypothesis_strategies import budget, hostile_run_reports
from jsonschema.validators import validator_for
from test_differential import CLI_CASES, FIXTURES, _fake_robot

from ontolint.cli import main
from ontolint.models import CONFIDENCES, ExecutionStatus, MeasurementKind
from ontolint.profiles import PROFILES
from ontolint.reporting import SEVERITY_ORDER, RunReport, to_json

ROOT = Path(__file__).parent.parent
SCHEMA_NAME = "lint-report.v1.schema.json"
SCHEMA = json.loads((resources.files("ontolint") / "schemas" / SCHEMA_NAME).read_text(encoding="utf-8"))
SAMPLES = FIXTURES / "reports" / "0.16.0"
MANIFEST = json.loads((SAMPLES / "manifest.json").read_text(encoding="utf-8"))
LINT_SAMPLES = [entry for entry in MANIFEST["samples"] if entry["kind"] == "lint"]
MINIMUM_SEEDS = 10  # seeds that parse; the rest of the corpus is hostile on purpose
JSON_CASES = sorted(
    name
    for name, (argv, _robot) in CLI_CASES.items()
    if "--format" in argv and "json" in argv and not {"--list-rules", "--explain"} & set(argv)
)


@pytest.fixture(scope="module")
def validate() -> Callable[[Any], None]:
    validator = validator_for(SCHEMA)
    validator.check_schema(SCHEMA)
    return validator(SCHEMA).validate


def _run(argv: list[str], monkeypatch: pytest.MonkeyPatch, *, cwd: Path = FIXTURES) -> tuple[int, str]:
    monkeypatch.chdir(cwd)
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = main(argv)
    return code, out.getvalue()


# --- the schema itself --------------------------------------------------------------------------------------------


def test_the_schema_is_shipped_in_the_package_and_in_the_source_tree() -> None:
    packaged = resources.files("ontolint") / "schemas" / SCHEMA_NAME
    assert packaged.is_file()
    assert (ROOT / "src" / "ontolint" / "schemas" / SCHEMA_NAME).read_text(encoding="utf-8") == packaged.read_text(
        encoding="utf-8"
    )


def test_the_schema_is_a_draft_2020_12_schema_that_names_its_version(validate: Callable[[Any], None]) -> None:
    assert SCHEMA["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert SCHEMA["properties"]["schema_version"] == {"const": 1}
    assert SCHEMA["$id"].endswith(SCHEMA_NAME)


def _walk(node: Any, path: str = "$") -> list[tuple[str, Any]]:
    found = [(path, node)]
    if isinstance(node, dict):
        for key, child in node.items():
            found += _walk(child, f"{path}.{key}")
    elif isinstance(node, list):
        for index, child in enumerate(node):
            found += _walk(child, f"{path}[{index}]")
    return found


def test_no_object_of_the_schema_is_closed() -> None:
    """The policy (docs/report-compatibility.md): a consumer ignores unknown keys, so the schema accepts them."""
    closed = [
        path for path, node in _walk(SCHEMA) if isinstance(node, dict) and node.get("additionalProperties") is False
    ]
    assert closed == []


def test_the_closed_enumerations_are_those_of_the_code() -> None:
    defs = SCHEMA["$defs"]
    assert defs["severity"]["enum"] == list(SEVERITY_ORDER)
    assert set(defs["confidence"]["enum"]) == CONFIDENCES
    assert defs["executionStatus"]["enum"] == [status.value for status in ExecutionStatus]
    assert defs["measurementKind"]["enum"] == [kind.value for kind in MeasurementKind]
    assert set(defs["severityCounts"]["propertyNames"]) == {"$ref"}


def test_every_severity_and_status_of_the_catalogue_and_the_rules_is_in_the_schema() -> None:
    from ontolint.rules.specs import RULE_SPECS  # noqa: PLC0415 -- the registry, for the severities of every rule

    assert {spec.severity.value for spec in RULE_SPECS} <= set(SCHEMA["$defs"]["severity"]["enum"])


def test_the_readme_refers_to_the_schema() -> None:
    assert SCHEMA_NAME in (ROOT / "README.md").read_text(encoding="utf-8")


# --- every shape validates ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("entry", LINT_SAMPLES, ids=lambda entry: entry["file"])
def test_every_0_16_0_sample_validates(entry: dict[str, Any], validate: Callable[[Any], None]) -> None:
    validate(json.loads((SAMPLES / entry["file"]).read_text(encoding="utf-8")))


@pytest.mark.parametrize("entry", LINT_SAMPLES, ids=lambda entry: entry["file"])
def test_the_same_commands_with_the_current_code_validate(
    entry: dict[str, Any], validate: Callable[[Any], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    code, out = _run(entry["args"], monkeypatch)
    assert code == entry["exit"]
    validate(json.loads(out))


@pytest.mark.parametrize("name", JSON_CASES)
def test_every_json_case_of_the_golden_suite_validates(
    name: str, validate: Callable[[Any], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    argv, robot = CLI_CASES[name]
    if robot is not None:
        monkeypatch.setattr("ontolint.engine.shutil.which", lambda _: "docker" if robot >= 0 else None)
        monkeypatch.setattr("ontolint.ontolint.subprocess.run", _fake_robot(max(robot, 0)))
    _code, out = _run(argv, monkeypatch)
    validate(json.loads(out))


@pytest.mark.parametrize("profile", sorted(PROFILES))
@pytest.mark.parametrize("source", ["clean.ttl", "kitchen_sink.ttl"])
def test_every_profile_validates(
    profile: str, source: str, validate: Callable[[Any], None], monkeypatch: pytest.MonkeyPatch
) -> None:
    _code, out = _run([source, "--format", "json", "--profile", profile, "--fail-on", "never"], monkeypatch)
    validate(json.loads(out))


def test_the_report_of_every_seed_of_the_fuzz_corpus_validates(
    validate: Callable[[Any], None], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A seed that cannot be read has no report (exit 2, nothing on stdout); every report that is written validates."""
    validated = 0
    for seed in fuzzer.load_corpus().rdf:
        path = tmp_path / f"seed{validated}{seed.ext}"
        path.write_bytes(seed.data)
        _code, out = _run([str(path), "--format", "json", "--fail-on", "never"], monkeypatch)
        if out.strip():
            validate(json.loads(out))
            validated += 1
    assert validated >= MINIMUM_SEEDS


@given(hostile_run_reports())
@budget(0.3)
def test_a_random_hostile_report_validates(report: RunReport) -> None:
    validator = validator_for(SCHEMA)
    validator(SCHEMA).validate(json.loads(json.dumps(to_json(report))))


# --- what the schema refuses --------------------------------------------------------------------------------------


def _document(monkeypatch: pytest.MonkeyPatch, *args: str) -> dict[str, Any]:
    _code, out = _run(["kitchen_sink.ttl", "--format", "json", "--fail-on", "never", *args], monkeypatch)
    return json.loads(out)


def _invalid(document: Any) -> bool:
    return not validator_for(SCHEMA)(SCHEMA).is_valid(document)


@pytest.mark.parametrize("key", ["schema_version", "summary", "findings", "execution_summary", "rules", "files"])
def test_a_report_without_a_required_key_is_refused(key: str, monkeypatch: pytest.MonkeyPatch) -> None:
    document = _document(monkeypatch)
    del document[key]
    assert _invalid(document)


def _mutations(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cases: dict[str, dict[str, Any]] = {}

    def make(name: str, change: Callable[[dict[str, Any]], None]) -> None:
        copied = copy.deepcopy(document)
        change(copied)
        cases[name] = copied

    make("another schema version", lambda d: d.update(schema_version=2))
    make("a string for the version", lambda d: d.update(schema_version="1"))
    make("an unknown severity in a finding", lambda d: d["findings"][0].update(severity="fatal"))
    make("an unknown severity in the summary", lambda d: d["summary"].update(fatal=1))
    make("an unknown confidence", lambda d: d["findings"][0].update(confidence="maybe"))
    make("a finding without its rule", lambda d: d["findings"][0].pop("rule"))
    make("a finding without its path", lambda d: d["findings"][0].pop("path"))
    make("a finding message that is a number", lambda d: d["findings"][0].update(message=3))
    make("a rule without its default severity", lambda d: d["rules"][0].pop("default_severity"))
    make("an unknown execution status", lambda d: d["files"][0]["executions"][0].update(status="crashed"))
    make("an execution summary without a status", lambda d: d["execution_summary"].pop("failed"))
    make("a negative count", lambda d: d["summary"].update(error=-1))
    make("findings that are not a list", lambda d: d.update(findings={}))
    make("a file without its path", lambda d: d["files"][0].pop("path"))
    return cases


def test_a_missing_key_a_wrong_type_or_an_unknown_enumeration_value_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    document = _document(monkeypatch)
    assert not _invalid(document)
    accepted = [name for name, mutated in _mutations(document).items() if not _invalid(mutated)]
    assert accepted == []


def test_a_measurement_must_match_its_kind_and_a_reason_excludes_a_value(monkeypatch: pytest.MonkeyPatch) -> None:
    document = _document(monkeypatch, "--measurements")
    measurements = document["files"][0]["measurements"]
    ratio = next(m for m in measurements if m["kind"] == "ratio")
    assert not _invalid(document)
    for change in (
        lambda m: m.pop("numerator"),
        lambda m: m.update(reason="could not be taken"),  # a reason and a value
        lambda m: m.update(kind="histogram"),  # a histogram without buckets
        lambda m: m.update(kind="mean"),
        lambda m: m.update(definition_version=0),
    ):
        copied = copy.deepcopy(document)
        change(next(m for m in copied["files"][0]["measurements"] if m["id"] == ratio["id"]))
        assert _invalid(copied)


def test_an_unknown_key_is_accepted_at_every_level(monkeypatch: pytest.MonkeyPatch) -> None:
    """Additive evolution: a consumer's schema check must not break when a later release adds a key."""
    document = _document(monkeypatch, "--measurements")
    document["forecast"] = {"rule_count": 1}
    document["findings"][0]["tags"] = ["x"]
    document["rules"][0]["owner"] = "y"
    document["files"][0]["timing"] = {"seconds": 0.1}
    document["files"][0]["executions"][0]["seconds"] = 0.1
    document["files"][0]["measurements"][0]["unit"] = "terms"
    assert not _invalid(document)


def _sample(name: str) -> dict[str, Any]:
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


def _partitioned() -> dict[str, Any]:
    """The measurements sample with its measurements also given as one partition per module."""
    document = _sample("lint-measurements.json")
    file = document["files"][0]
    file["measurement_partitions"] = [
        {"by": "module", "name": "https://example.test/m#", "measurements": copy.deepcopy(file["measurements"])}
    ]
    return document


def _optional_section_mutations() -> dict[str, dict[str, Any]]:
    """Documents valid but for one change in a section that only some reports carry."""
    cases: dict[str, dict[str, Any]] = {}

    def make(name: str, document: dict[str, Any], change: Callable[[dict[str, Any]], None]) -> None:
        change(document)
        cases[name] = document

    quality = "lint-quality-comparison.json"
    make("a quality comparison without its format", _sample(quality), lambda d: d["quality_comparison"].pop("format"))
    make(
        "a quality comparison of another format",
        _sample(quality),
        lambda d: d["quality_comparison"].update(format="something-else"),
    )
    make("a quality comparison without its notes", _sample(quality), lambda d: d["quality_comparison"].pop("notes"))
    make(
        "a quality comparison measurement without its status",
        _sample(quality),
        lambda d: d["quality_comparison"]["measurements"][0].pop("status"),
    )
    make(
        "a quality comparison measurement of an unknown status",
        _sample(quality),
        lambda d: d["quality_comparison"]["measurements"][0].update(status="unknown"),
    )
    stale = "lint-baseline-stale.json"
    make("stale fingerprints that are integers", _sample(stale), lambda d: d["baseline"].update(stale_fingerprints=[1]))
    make(
        "stale fingerprints that are not a list", _sample(stale), lambda d: d["baseline"].update(stale_fingerprints="x")
    )
    make("a baseline without its stale fingerprints", _sample(stale), lambda d: d["baseline"].pop("stale_fingerprints"))
    modules = "lint-modules.json"
    make(
        "a module summary with an unknown severity",
        _sample(modules),
        lambda d: next(iter(d["files"][0]["module_summary"].values())).update(fatal=1),
    )
    make(
        "a module summary with a negative count",
        _sample(modules),
        lambda d: next(iter(d["files"][0]["module_summary"].values())).update(info=-1),
    )
    make(
        "finding modules that are not strings",
        _sample(modules),
        lambda d: next(f for f in d["findings"] if "modules" in f).update(modules=[1]),
    )
    make(
        "finding graphs that are not a list",
        _sample(modules),
        lambda d: d["findings"][0].update(graphs="https://example.test/g"),
    )
    make("a partition without its by", _partitioned(), lambda d: d["files"][0]["measurement_partitions"][0].pop("by"))
    make(
        "a partition by an unknown axis",
        _partitioned(),
        lambda d: d["files"][0]["measurement_partitions"][0].update(by="tenant"),
    )
    make(
        "a partition without its measurements",
        _partitioned(),
        lambda d: d["files"][0]["measurement_partitions"][0].pop("measurements"),
    )
    make(
        "a partition measurement of an unknown kind",
        _partitioned(),
        lambda d: d["files"][0]["measurement_partitions"][0]["measurements"][0].update(kind="histogramme"),
    )
    return cases


def test_the_optional_sections_are_valid_unchanged_and_refused_once_broken() -> None:
    """Each shape below only has valid inputs elsewhere: loosening its definition to {} must fail here."""
    for name in ("lint-quality-comparison.json", "lint-baseline-stale.json", "lint-modules.json"):
        assert not _invalid(_sample(name)), name
    assert not _invalid(_partitioned())
    accepted = [name for name, document in _optional_section_mutations().items() if not _invalid(document)]
    assert accepted == []
