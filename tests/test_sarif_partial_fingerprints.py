"""``--sarif-fingerprints``: SARIF ``partialFingerprints`` that keep code scanning's alerts apart (issue #92).

The design is ``TODO.md``'s (``ontolintIdentity/v2``, and ``ontolintFingerprint/v1`` only for a result whose identity
another result shares).  Without the flag the SARIF report is unchanged, which the ``sarif_*`` goldens pin.  What
GitHub does with the keys is not tested here: it needs an upload (the issue's Done-when).
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from jsonschema.validators import validator_for
from rdflib import Graph

from ontolint.cli import main
from ontolint.models import Finding
from ontolint.reporting import (
    FINGERPRINT_KEY,
    IDENTITY_KEY,
    IDENTITY_TAG,
    FileReport,
    RunReport,
    fingerprint,
    identity,
    to_sarif_report,
)

FIXTURES = Path(__file__).parent / "fixtures"
KITCHEN = FIXTURES / "kitchen_sink.ttl"
USAGE_ERROR = 2
SHA256_HEX = 64
CROWDED_GROUPS = 10  # the kitchen sink has 14 groups of one rule on one line
KEPT_RESULTS = 50
SCHEMA = Path(__file__).parent / "schemas" / "sarif-schema-2.1.0.json"


@pytest.fixture(scope="module")
def validate() -> Callable[[dict[str, Any]], None]:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    return validator_for(schema)(schema).validate


def _finding(message: str = "Missing label.", focus: str = "https://example.test/A") -> Finding:
    return Finding("ONT001", "warning", focus, message, "Add a label.")


def _results(capsys: pytest.CaptureFixture[str], *argv: str, flag: bool = True) -> list[dict[str, Any]]:
    assert main([*argv, "--format", "sarif", *(["--sarif-fingerprints"] if flag else [])]) in (0, 1)
    return json.loads(capsys.readouterr().out)["runs"][0]["results"]


def _constructed(*findings: Finding, path: str = "a.ttl") -> list[dict[str, Any]]:
    report = RunReport((FileReport(path, f"file:///{path}", findings),), sarif_fingerprints=True)
    return to_sarif_report(report)["runs"][0]["results"]


def _identities(results: list[dict[str, Any]]) -> Counter[tuple[str, str]]:
    return Counter((r["ruleId"], r["partialFingerprints"][IDENTITY_KEY]) for r in results)


def _start_line(result: dict[str, Any]) -> int | None:
    return result["locations"][0]["physicalLocation"].get("region", {}).get("startLine")


def test_the_keys_follow_the_identity_version() -> None:
    assert IDENTITY_TAG == "ontolint-identity-2"
    assert IDENTITY_KEY == "ontolintIdentity/v2"
    assert FINGERPRINT_KEY == "ontolintFingerprint/v1"


def test_the_default_sarif_report_has_no_partial_fingerprints(capsys: pytest.CaptureFixture[str]) -> None:
    results = _results(capsys, str(KITCHEN), flag=False)
    assert results
    assert all("partialFingerprints" not in r for r in results)


def test_the_option_needs_the_sarif_format(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stop:
        main([str(KITCHEN), "--sarif-fingerprints"])
    assert stop.value.code == USAGE_ERROR
    assert "--sarif-fingerprints requires --format sarif" in capsys.readouterr().err


def test_the_kitchen_sink_report_validates_and_carries_the_baseline_identities(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], validate: Callable[[dict[str, Any]], None]
) -> None:
    baseline = tmp_path / "baseline.json"
    main([str(KITCHEN), "--write-baseline", str(baseline), "--format", "json"])
    capsys.readouterr()
    recorded = {i for per_path in json.loads(baseline.read_text())["identities"].values() for i in per_path}
    assert main([str(KITCHEN), "--format", "sarif", "--sarif-fingerprints"]) == 1
    document = json.loads(capsys.readouterr().out)
    validate(document)
    results = document["runs"][0]["results"]
    assert results
    values = {r["partialFingerprints"][IDENTITY_KEY] for r in results}
    assert all(len(v) == SHA256_HEX for v in values)
    assert recorded <= values  # a baseline holds the identity of every unshared finding
    assert all(
        FINGERPRINT_KEY not in r["partialFingerprints"]
        for r in results
        if r["partialFingerprints"][IDENTITY_KEY] in recorded
    )


def test_results_of_one_rule_on_one_line_get_different_fingerprints(capsys: pytest.CaptureFixture[str]) -> None:
    results = _results(capsys, str(KITCHEN))
    groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        if (line := _start_line(result)) is not None:
            groups[result["ruleId"], line].append(result)
    crowded = [g for g in groups.values() if len(g) > 1]
    assert len(crowded) >= CROWDED_GROUPS, "the fixture must keep exercising the same-line case"
    for group in crowded:
        sets = [json.dumps(r["partialFingerprints"], sort_keys=True) for r in group]
        assert len(set(sets)) == len(sets)


def test_a_run_is_stable_across_runs(capsys: pytest.CaptureFixture[str]) -> None:
    assert _results(capsys, str(KITCHEN)) == _results(capsys, str(KITCHEN))


def test_fingerprints_survive_a_reserialization_that_moves_every_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    moved = tmp_path / "moved.nt"
    Graph().parse(KITCHEN, format="turtle").serialize(moved, format="nt", encoding="utf-8")
    original = _results(capsys, str(KITCHEN))
    again = _results(capsys, str(moved))
    assert Counter(map(_start_line, original)) != Counter(map(_start_line, again))

    def named(results: list[dict[str, Any]]) -> Counter[tuple[str, str]]:
        # A re-serialization relabels blank nodes, so the comparison is on results whose focus is an IRI.
        return _identities([r for r in results if "Focus: _:" not in r["message"]["text"]])

    kept = named(original)
    assert sum(kept.values()) > KEPT_RESULTS
    assert not kept - named(again)


def test_a_one_file_run_gives_each_result_the_value_of_a_multi_file_run(capsys: pytest.CaptureFixture[str]) -> None:
    alone = _results(capsys, str(KITCHEN))
    together = _results(capsys, str(FIXTURES / "clean.ttl"), str(KITCHEN))
    uri = alone[0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
    in_kitchen = [r for r in together if r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == uri]
    assert in_kitchen
    assert _identities(in_kitchen) == _identities(alone)


def test_the_value_ignores_the_message_and_the_severity() -> None:
    a = _finding("Missing label.")
    b = _finding("Reworded.")
    c = Finding("ONT001", "error", a.focus, a.message, a.suggestion)
    for f in (a, b, c):
        assert _constructed(f)[0]["partialFingerprints"] == {IDENTITY_KEY: identity(a)}


def test_a_shared_identity_adds_the_version_1_fingerprint_to_those_results_only() -> None:
    one, two = _finding("First."), _finding("Second.")
    other = _finding("Other.", focus="https://example.test/B")
    sets = [r["partialFingerprints"] for r in _constructed(one, two, other)]
    assert sets[0][IDENTITY_KEY] == sets[1][IDENTITY_KEY]
    assert sets[0][FINGERPRINT_KEY] == fingerprint(one)
    assert sets[1][FINGERPRINT_KEY] == fingerprint(two)
    assert sets[0][FINGERPRINT_KEY] != sets[1][FINGERPRINT_KEY]
    assert FINGERPRINT_KEY not in sets[2]
    assert len({json.dumps(s, sort_keys=True) for s in sets}) == len(sets)


def test_the_version_1_fingerprint_holds_no_path() -> None:
    one, two = _finding("First."), _finding("Second.")
    a = _constructed(one, two, path="a.ttl")
    b = _constructed(one, two, path="dir/b.ttl")
    assert [r["partialFingerprints"] for r in a] == [r["partialFingerprints"] for r in b]


def test_a_report_with_a_shared_identity_validates(validate: Callable[[dict[str, Any]], None]) -> None:
    report = RunReport((FileReport("a.ttl", "file:///a.ttl", (_finding("First."), _finding("Second."))),))
    document = to_sarif_report(RunReport(report.files, sarif_fingerprints=True))
    validate(document)
    assert FINGERPRINT_KEY in document["runs"][0]["results"][0]["partialFingerprints"]


def test_the_same_finding_in_two_files_is_told_apart_by_the_artifact_location_only() -> None:
    f = _finding()
    report = RunReport(
        (FileReport("a.ttl", "file:///a.ttl", (f,)), FileReport("b.ttl", "file:///b.ttl", (f,))),
        sarif_fingerprints=True,
    )
    first, second = to_sarif_report(report)["runs"][0]["results"]
    assert first["partialFingerprints"] == second["partialFingerprints"] == {IDENTITY_KEY: identity(f)}
    uris = [r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] for r in (first, second)]
    assert uris[0] != uris[1]


def test_a_sibling_coming_or_going_keeps_the_identity_key_and_only_moves_the_version_1_one() -> None:
    one, two = _finding("First."), _finding("Second.")
    alone = _constructed(one)[0]["partialFingerprints"]
    crowded = _constructed(one, two)[0]["partialFingerprints"]
    assert alone == {IDENTITY_KEY: identity(one)}
    assert crowded[IDENTITY_KEY] == alone[IDENTITY_KEY]
    assert set(crowded) - set(alone) == {FINGERPRINT_KEY}
