"""The JSON Schemas of the other documents ontolint writes (issue #172): the rule listing, the rule detail, the quality
snapshot and the baseline file, shipped in ``src/ontolint/schemas/`` beside the lint report's (issue #171).

The listing, the detail and the baseline are open (a consumer ignores keys it does not know, ``docs/report-
compatibility.md``). The quality snapshot is read by ontolint itself and its reader refuses a key it does not know,
so its schema is closed exactly where the reader is. Enumerations the policy calls closed are generated from the
code here. Every shape the CLI can write validates (the 0.16.0 samples, the same commands with the current code,
every rule of the catalogue), a negative fixture is refused per schema, and the two documents ontolint reads round-
trip through its readers.
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
from jsonschema.validators import validator_for
from test_differential import FIXTURES

from ontolint import baseline, quality
from ontolint.catalogue import load_catalogue
from ontolint.cli import main
from ontolint.models import MeasurementKind
from ontolint.reporting import SEVERITY_ORDER
from ontolint.rule_info import explain_rule, render_explanation, render_rule_list, rule_rows
from ontolint.rules.registry import default_registry

ROOT = Path(__file__).parent.parent
SAMPLES = FIXTURES / "reports" / "0.16.0"
POLICY = (ROOT / "docs" / "report-compatibility.md").read_text(encoding="utf-8")
NAMES = {
    "listing": "rule-listing.v1.schema.json",
    "detail": "rule-detail.v1.schema.json",
    "snapshot": "quality-snapshot.v1.schema.json",
    "baseline": "baseline.v2.schema.json",
}


def _load(kind: str) -> dict[str, Any]:
    return json.loads((resources.files("ontolint") / "schemas" / NAMES[kind]).read_text(encoding="utf-8"))


SCHEMAS = {kind: _load(kind) for kind in NAMES}


def _valid(kind: str, document: Any) -> bool:
    return validator_for(SCHEMAS[kind])(SCHEMAS[kind]).is_valid(document)


def _validate(kind: str, document: Any) -> None:
    validator_for(SCHEMAS[kind])(SCHEMAS[kind]).validate(document)


def _run(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.chdir(FIXTURES)
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        main(argv)
    return out.getvalue()


def _write(argv: list[str], flag: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    target = tmp_path / "document.json"
    _run([*argv, flag, str(target), "--fail-on", "never"], monkeypatch)
    return target.read_text(encoding="utf-8")


def _walk(node: Any, path: str = "$") -> list[tuple[str, Any]]:
    found = [(path, node)]
    if isinstance(node, dict):
        for key, child in node.items():
            found += _walk(child, f"{path}.{key}")
    elif isinstance(node, list):
        for index, child in enumerate(node):
            found += _walk(child, f"{path}[{index}]")
    return found


# --- the schemas themselves ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", sorted(NAMES))
def test_each_schema_is_shipped_valid_and_names_itself(kind: str) -> None:
    schema = SCHEMAS[kind]
    validator_for(schema).check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"].endswith(NAMES[kind])
    source = ROOT / "src" / "ontolint" / "schemas" / NAMES[kind]
    assert source.read_text(encoding="utf-8") == (resources.files("ontolint") / "schemas" / NAMES[kind]).read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize("kind", ["listing", "detail", "baseline"])
def test_the_open_documents_have_no_closed_object(kind: str) -> None:
    closed = [p for p, n in _walk(SCHEMAS[kind]) if isinstance(n, dict) and n.get("additionalProperties") is False]
    assert closed == []


def test_the_snapshot_schema_is_closed_where_the_reader_is() -> None:
    schema = SCHEMAS["snapshot"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["policy"]["additionalProperties"] is False
    assert schema["$defs"]["measurement"]["additionalProperties"] is False


def test_the_enumerations_are_those_of_the_code() -> None:
    assert SCHEMAS["listing"]["$defs"]["severity"]["enum"] == list(SEVERITY_ORDER)
    assert SCHEMAS["detail"]["$defs"]["severity"]["enum"] == list(SEVERITY_ORDER)
    measurement = SCHEMAS["snapshot"]["$defs"]["measurement"]["properties"]
    assert measurement["kind"]["enum"] == [kind.value for kind in MeasurementKind]
    assert measurement["better"]["enum"] == list(quality.BETTER)


def test_the_version_keys_are_those_of_the_policy_and_the_code() -> None:
    assert SCHEMAS["listing"]["properties"]["schema_version"] == {"const": 1}
    assert SCHEMAS["detail"]["properties"]["schema_version"] == {"const": 1}
    assert SCHEMAS["snapshot"]["properties"]["format"] == {"const": quality.SNAPSHOT_FORMAT}
    assert SCHEMAS["snapshot"]["properties"]["version"] == {"const": quality.SNAPSHOT_VERSION}
    assert SCHEMAS["baseline"]["properties"]["version"] == {"const": baseline.BASELINE_VERSION}
    for row in ("`schema_version`", "`format`", "`version`"):
        assert row in POLICY


def test_the_policy_names_the_schemas() -> None:
    for name in NAMES.values():
        assert name.removesuffix(".schema.json") in POLICY


# --- the rule listing and the rule detail -------------------------------------------------------------------------


def test_the_listing_the_cli_writes_validates_and_has_every_catalogue_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    document = json.loads(_run(["--list-rules", "--format", "json"], monkeypatch))
    _validate("listing", document)
    assert [row["id"] for row in document["rules"] if row["status"] == "proposed"], "proposed rules are listed"
    assert {row["id"] for row in document["rules"]} == {row.rule_id for row in load_catalogue()}


def test_the_0_16_0_listing_and_detail_validate() -> None:
    _validate("listing", json.loads((SAMPLES / "rules-list.json").read_text(encoding="utf-8")))
    _validate("detail", json.loads((SAMPLES / "rule-explain.json").read_text(encoding="utf-8")))


def test_the_listing_keys_follow_the_catalogue_columns() -> None:
    """The catalogue's columns are rule_id, family, title, status, category, backend, test_requirement: each is a key of
    the listing (rule_id as id) or of the detail (test_requirement), so a renamed column or key fails here."""
    rows = {row["id"]: row for row in rule_rows(default_registry())}
    assert set(rows) == {row.rule_id for row in load_catalogue()}
    for entry in load_catalogue():
        row = rows[entry.rule_id]
        assert (row["family"], row["title"], row["status"], row["category"]) == (
            entry.family,
            entry.title,
            entry.status.value,
            entry.category,
        )
        if entry.status.value == "proposed":
            assert row["backend"] == entry.backend
    columns = set(load_catalogue()[0].__dataclass_fields__)
    assert columns == {"rule_id", "family", "title", "status", "category", "backend", "test_requirement"}
    assert set(SCHEMAS["listing"]["$defs"]["rule"]["properties"]) >= columns - {"rule_id", "test_requirement"}
    assert "test_requirement" in SCHEMAS["detail"]["$defs"]["detail"]["properties"]


def test_the_listing_in_text_and_json_describes_the_same_rules() -> None:
    rows = rule_rows(default_registry())
    text = render_rule_list(rows, "text")
    assert all(row["id"] in text for row in rows[:5])
    _validate("listing", json.loads(render_rule_list(rows, "json")))


def test_the_detail_of_every_rule_of_the_catalogue_validates() -> None:
    registry = default_registry()
    for entry in load_catalogue():
        document = json.loads(render_explanation(explain_rule(entry.rule_id, registry), "json"))
        _validate("detail", document)
        assert document["rule"]["id"] == entry.rule_id
        assert document["rule"]["test_requirement"] == entry.test_requirement


def test_the_detail_the_cli_writes_validates(monkeypatch: pytest.MonkeyPatch) -> None:
    for rule in ("OWL004", "SHACL001", "ALIGN001", "OBO001"):
        _validate("detail", json.loads(_run(["--explain", rule, "--format", "json"], monkeypatch)))


def _listing_mutations(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cases: dict[str, dict[str, Any]] = {}

    def make(name: str, change: Callable[[dict[str, Any]], None]) -> None:
        copied = copy.deepcopy(document)
        change(copied)
        cases[name] = copied

    make("no rules", lambda d: d.pop("rules"))
    make("another version", lambda d: d.update(schema_version=2))
    make("an unknown severity", lambda d: d["rules"][0].update(severity="fatal"))
    make("a rule without its id", lambda d: d["rules"][0].pop("id"))
    make("a title that is a number", lambda d: d["rules"][0].update(title=3))
    make("selectable as text", lambda d: d["rules"][0].update(selectable="yes"))
    make("opt_in false", lambda d: d["rules"][0].update(opt_in=False))
    return cases


def test_a_listing_with_a_missing_key_a_wrong_type_or_an_unknown_severity_is_refused() -> None:
    document = json.loads(render_rule_list(rule_rows(default_registry()), "json"))
    assert _valid("listing", document)
    assert [name for name, bad in _listing_mutations(document).items() if _valid("listing", bad)] == []


def test_a_detail_with_a_missing_key_a_wrong_type_or_an_unknown_severity_is_refused() -> None:
    document = json.loads(render_explanation(explain_rule("OWL004", default_registry()), "json"))
    assert _valid("detail", document)
    for change in (
        lambda d: d.pop("rule"),
        lambda d: d["rule"].pop("suggestion"),
        lambda d: d["rule"].pop("test_requirement"),
        lambda d: d["rule"].update(severity="fatal"),
        lambda d: d["rule"].update(suggestion=3),
        lambda d: d.update(schema_version="1"),
    ):
        copied = copy.deepcopy(document)
        change(copied)
        assert not _valid("detail", copied)


def test_an_unknown_key_is_accepted_in_a_listing_and_a_detail() -> None:
    listing = json.loads(render_rule_list(rule_rows(default_registry()), "json"))
    listing["generated"] = "x"
    listing["rules"][0]["owner"] = "y"
    assert _valid("listing", listing)
    detail = json.loads(render_explanation(explain_rule("OWL004", default_registry()), "json"))
    detail["rule"]["docs"] = "https://example.test"
    assert _valid("detail", detail)


# --- the quality snapshot -----------------------------------------------------------------------------------------

SNAPSHOT_SOURCES = {
    "clean": ["clean.ttl"],
    "kitchen sink": ["kitchen_sink.ttl"],
    "populated": ["populated.ttl"],
    "empty ontology": ["reports/inputs/empty.ttl"],
    "a base and a config": ["kitchen_sink.ttl", "--base", "https://example.test/onto#", "--config", "policy.json"],
}


@pytest.mark.parametrize("name", sorted(SNAPSHOT_SOURCES))
def test_a_snapshot_the_cli_writes_validates_and_round_trips(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    text = _write(SNAPSHOT_SOURCES[name], "--write-quality-snapshot", tmp_path, monkeypatch)
    _validate("snapshot", json.loads(text))
    assert quality.dumps(quality.loads(text)) == text  # write, validate, read, compare


def test_the_0_16_0_snapshot_validates_and_round_trips() -> None:
    text = (SAMPLES / "quality-snapshot.json").read_text(encoding="utf-8")
    _validate("snapshot", json.loads(text))
    assert quality.dumps(quality.loads(text)) == text


def _snapshot() -> dict[str, Any]:
    return json.loads((SAMPLES / "quality-snapshot.json").read_text(encoding="utf-8"))


def _snapshot_mutations(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cases: dict[str, dict[str, Any]] = {}

    def make(name: str, change: Callable[[dict[str, Any]], None]) -> None:
        copied = copy.deepcopy(document)
        change(copied)
        cases[name] = copied

    ratio = next(i for i, m in enumerate(document["measurements"]) if m["kind"] == "ratio")
    make("another version", lambda d: d.update(version=2))
    make("another format", lambda d: d.update(format="ontolint-quality-comparison"))
    make("no policy", lambda d: d.pop("policy"))
    make("an unknown top-level key", lambda d: d.update(generated="today"))
    make("an unknown policy key", lambda d: d["policy"].update(extra=1))
    make("a policy base that is a number", lambda d: d["policy"].update(base=3))
    make("an unknown measurement key", lambda d: d["measurements"][ratio].update(unit="terms"))
    make("a ratio without its numerator", lambda d: d["measurements"][ratio].pop("numerator"))
    make("a ratio with a value", lambda d: d["measurements"][ratio].update(value=1))
    make("an unknown kind", lambda d: d["measurements"][ratio].update(kind="mean"))
    make("a better that is neither", lambda d: d["measurements"][ratio].update(better="more"))
    make("a better without its term sets", lambda d: d["measurements"][ratio].pop("numerator_terms"))
    make("a negative numerator", lambda d: d["measurements"][ratio].update(numerator=-1))
    make("a definition version of 0", lambda d: d["measurements"][ratio].update(definition_version=0))
    return cases


def test_a_snapshot_the_reader_would_refuse_is_refused_by_the_schema() -> None:
    document = _snapshot()
    assert _valid("snapshot", document)
    assert [name for name, bad in _snapshot_mutations(document).items() if _valid("snapshot", bad)] == []


def test_every_snapshot_the_schema_refuses_here_is_refused_by_the_reader_too() -> None:
    """The schema is closed where the reader is: what it refuses for a closed-object reason, the reader refuses."""
    for name, bad in _snapshot_mutations(_snapshot()).items():
        if name in {
            "an unknown top-level key",
            "an unknown policy key",
            "an unknown measurement key",
            "another version",
        }:
            with pytest.raises(quality.SnapshotError):
                quality.loads(json.dumps(bad))


# --- the baseline file --------------------------------------------------------------------------------------------

BASELINE_SOURCES = {
    "kitchen sink": ["kitchen_sink.ttl"],
    "clean": ["clean.ttl"],
    "several files": ["clean.ttl", "populated.ttl"],
    "empty ontology": ["reports/inputs/empty.ttl"],
}


@pytest.mark.parametrize("name", sorted(BASELINE_SOURCES))
def test_a_baseline_the_cli_writes_validates_and_round_trips(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    text = _write(BASELINE_SOURCES[name], "--write-baseline", tmp_path, monkeypatch)
    document = json.loads(text)
    _validate("baseline", document)
    assert baseline.dumps(baseline.loads(text)) == text  # write, validate, read, compare
    assert document["version"] == baseline.BASELINE_VERSION


def test_the_0_16_0_baseline_validates_and_round_trips() -> None:
    text = (SAMPLES / "baseline.json").read_text(encoding="utf-8")
    _validate("baseline", json.loads(text))
    assert baseline.dumps(baseline.loads(text)) == text


def test_a_baseline_with_a_missing_section_a_wrong_type_or_a_short_hash_is_refused() -> None:
    document = json.loads((SAMPLES / "baseline.json").read_text(encoding="utf-8"))
    assert _valid("baseline", document)
    path = next(iter(document["identities"]))
    identity = next(iter(document["identities"][path]))
    for change in (
        lambda d: d.pop("fingerprints"),
        lambda d: d.pop("identities"),
        lambda d: d.pop("files"),
        lambda d: d.update(version=1),
        lambda d: d.update(version="2"),
        lambda d: d.update(files="a.ttl"),
        lambda d: d["fingerprints"].append("abc"),
        lambda d: d["fingerprints"].append(3),
        lambda d: d["identities"][path].update({"not-a-hash": d["identities"][path][identity]}),
        lambda d: d["identities"][path].update({identity: "short"}),
        lambda d: d["identities"].update({path: []}),
    ):
        copied = copy.deepcopy(document)
        change(copied)
        assert not _valid("baseline", copied)


def test_an_unknown_section_is_accepted_in_a_baseline_as_the_reader_ignores_it() -> None:
    text = (SAMPLES / "baseline.json").read_text(encoding="utf-8")
    document = json.loads(text)
    document["notes"] = ["reviewed 2026-11-23"]
    assert _valid("baseline", document)
    assert baseline.dumps(baseline.loads(json.dumps(document))) == text  # the reader drops it, as the policy says
