"""The report compatibility policy (``docs/report-compatibility.md``, issue #170) against the frozen 0.16.0 samples.

``tests/fixtures/reports/0.16.0/`` holds real outputs of the ``v0.16.0`` tag, one per report shape, and a manifest
of the command behind each. The tests run the same commands with the current code and compare key paths and JSON
types: a key of a sample that is gone or has another type is a breaking change, and a key the current output adds
must be named in the ledger of the policy page. Keys that hold data (the severity names under ``summary``, the
hashes of a baseline) are compared as ``{*}``.
"""

from __future__ import annotations

import contextlib
import io
import json
import re
from pathlib import Path
from typing import Any

import pytest

from ontolint.cli import main

ROOT = Path(__file__).parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
SAMPLES = FIXTURES / "reports" / "0.16.0"
POLICY = ROOT / "docs" / "report-compatibility.md"
MANIFEST = json.loads((SAMPLES / "manifest.json").read_text(encoding="utf-8"))
ENTRIES = {entry["file"]: entry for entry in MANIFEST["samples"]}

# Objects whose keys are data, not names: compared as ``{*}``.
MAPS = frozenset(
    {
        "$.summary",
        "$.files[].summary",
        "$.files[].module_summary",
        "$.findings[].evidence",
        "$.identities",
        "$.identities.{*}",
    }
)

type Shape = set[tuple[str, str]]


def shape_of(document: Any) -> Shape:
    """Every (key path, JSON type) of ``document``; arrays are ``[]`` and a map's keys are ``{*}``."""
    found: Shape = set()

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            found.add((path, "object"))
            for key, child in value.items():
                walk(child, f"{path}.{'{*}' if path in MAPS else key}")
        elif isinstance(value, list):
            found.add((path, "array"))
            for child in value:
                walk(child, f"{path}[]")
        else:
            found.add((path, "null" if value is None else type(value).__name__))

    walk(document, "$")
    return found


def current_document(entry: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """What the current code writes for the command of a sample."""
    monkeypatch.chdir(FIXTURES)
    if entry["kind"] in {"quality-snapshot", "baseline"}:
        out = tmp_path / entry["file"]
        main([str(out) if arg == "{out}" else arg for arg in entry["args"]])
        return json.loads(out.read_text(encoding="utf-8"))
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(io.StringIO()):
        code = main(entry["args"])
    assert code == entry["exit"], entry["file"]
    return json.loads(buffer.getvalue())


def ledger() -> set[tuple[str, str]]:
    """The (document kind, key path) rows of the ledger of the policy page."""
    section = POLICY.read_text(encoding="utf-8").split("### Ledger", 1)[1]
    rows = re.findall(r"^\| `?([\w-]+)`? \| `([^`]+)` \| [^|]+\|$", section, re.MULTILINE)
    return {(kind, path) for kind, path in rows}


# --- the policy page and the samples ------------------------------------------------------------------------------


def test_the_policy_page_exists_and_the_readme_links_it() -> None:
    assert POLICY.is_file()
    assert "docs/report-compatibility.md" in (ROOT / "README.md").read_text(encoding="utf-8")


def test_the_policy_names_every_document_kind_of_the_samples_and_the_version_keys() -> None:
    page = POLICY.read_text(encoding="utf-8")
    for kind in {entry["kind"] for entry in MANIFEST["samples"]}:
        assert f"(`{kind}`)" in page or f"`{kind}`" in page, kind
    for key in ("schema_version", "`version`", "ontolintIdentity/v2"):
        assert key in page


def test_the_manifest_lists_every_sample_and_every_sample_is_a_document() -> None:
    files = {path.name for path in SAMPLES.iterdir() if path.name != "manifest.json"}
    assert files == set(ENTRIES)
    assert MANIFEST["tool"] == "ontolint 0.16.0"
    for name in files:
        document = json.loads((SAMPLES / name).read_text(encoding="utf-8"))
        assert isinstance(document, dict), name


def test_the_samples_were_written_by_0_16_0() -> None:
    sarif = json.loads((SAMPLES / "sarif-default.sarif").read_text(encoding="utf-8"))
    assert sarif["runs"][0]["tool"]["driver"]["version"] == "0.16.0"
    assert json.loads((SAMPLES / "quality-snapshot.json").read_text(encoding="utf-8"))["version"] == 1


# --- additive evolution -------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(ENTRIES))
def test_no_key_of_a_0_16_0_report_is_removed_or_retyped(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = shape_of(json.loads((SAMPLES / name).read_text(encoding="utf-8")))
    new = shape_of(current_document(ENTRIES[name], tmp_path, monkeypatch))
    assert not old - new, (
        f"{name}: removed or retyped (a breaking change, docs/report-compatibility.md): {sorted(old - new)}"
    )


def unnamed_additions(name: str, document: Any) -> list[str]:
    """The key paths ``document`` has and the 0.16.0 sample ``name`` has not, that the ledger does not name."""
    kind = ENTRIES[name]["kind"]
    old = shape_of(json.loads((SAMPLES / name).read_text(encoding="utf-8")))
    return sorted(path for path, _type in shape_of(document) - old if (kind, path) not in ledger())


@pytest.mark.parametrize("name", sorted(ENTRIES))
def test_every_key_a_report_adds_is_in_the_ledger(name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    added = unnamed_additions(name, current_document(ENTRIES[name], tmp_path, monkeypatch))
    assert not added, f"{name}: added without a ledger row in docs/report-compatibility.md: {added}"


def test_a_key_added_to_a_report_without_a_ledger_row_fails_the_check() -> None:
    document = json.loads((SAMPLES / "lint-clean.json").read_text(encoding="utf-8"))
    assert unnamed_additions("lint-clean.json", document) == []
    document["catalogue"] = {"rule_count": 1}
    document["files"][0]["timing"] = {"seconds": 0.1}
    assert unnamed_additions("lint-clean.json", document) == [
        "$.catalogue",
        "$.catalogue.rule_count",
        "$.files[].timing",
        "$.files[].timing.seconds",
    ]


def test_the_ledger_has_no_row_for_a_key_that_is_not_there(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A ledger row names a key the current output has and the samples have not."""
    present: set[tuple[str, str]] = set()
    for name, entry in ENTRIES.items():
        old = shape_of(json.loads((SAMPLES / name).read_text(encoding="utf-8")))
        new = shape_of(current_document(entry, tmp_path, monkeypatch))
        present |= {(entry["kind"], path) for path, _type in new - old}
    assert ledger() <= present


# --- the checks catch what they are for ---------------------------------------------------------------------------


def test_a_removed_key_a_retyped_key_and_an_added_key_are_seen() -> None:
    old = shape_of({"a": 1, "b": {"c": "x"}, "summary": {"error": 1}})
    assert shape_of({"a": 1, "b": {"c": "x"}, "summary": {"error": 1}}) == old
    assert ("$.b.c", "str") in old - shape_of({"a": 1, "b": {}, "summary": {}})  # removed
    assert ("$.a", "int") in old - shape_of({"a": "1", "b": {"c": "x"}, "summary": {}})  # retyped
    assert ("$.d", "int") in shape_of({"a": 1, "b": {"c": "x"}, "d": 2}) - old  # added


def test_a_map_is_compared_by_its_value_types_not_its_key_names() -> None:
    assert shape_of({"summary": {"error": 1}}) == shape_of({"summary": {"info": 3}})
    assert shape_of({"summary": {"error": 1}}) != shape_of({"summary": {"error": "1"}})
