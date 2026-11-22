"""scripts/corpus_counts.py: per-rule finding counts on the pinned corpus, recorded, checked and diffed (#168).

A small synthetic corpus (no network): files written into a directory laid out as ``scripts/corpus.py fetch`` leaves it,
a manifest whose checksums are theirs, and the real ontolint on them.
"""

# ruff: noqa: PLR2004

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("corpus_counts", ROOT / "scripts" / "corpus_counts.py")
assert spec is not None
assert spec.loader is not None
counts = importlib.util.module_from_spec(spec)
sys.modules["corpus_counts"] = counts
spec.loader.exec_module(counts)
corpus = counts.corpus

COMMIT = "0123456789abcdef0123456789abcdef01234567"
PREFIXES = "@prefix : <https://e.test/o#> .\n@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
PREFIXES += "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
CLEAN = PREFIXES + '<https://e.test/o> a owl:Ontology ; rdfs:label "o"@en .\n:A a owl:Class ; rdfs:label "A"@en .\n'
UNLABELLED = CLEAN + ":B a owl:Class .\n:C a owl:Class .\n"
BROKEN = PREFIXES + ":A a owl:Class ; rdfs:label .\n"
FIXED = ["--format", "json", "--fail-on", "never"]
VERSION = "9.9.9"


def _sources(files: dict[str, str], inputs: list[str], exit_status: int = 0) -> list[Any]:
    item = {
        "id": "synthetic",
        "repository": "owner/repo",
        "commit": COMMIT,
        "licence": "MIT",
        "files": {path: corpus.sha256(text.encode()) for path, text in files.items()},
        "runs": [{"name": "all", "inputs": inputs, "args": ["--select", "LEX001,GOV004"], "exit_status": exit_status}],
    }
    return [corpus.source_of(item)]


def _lay_out(directory: Path, files: dict[str, str]) -> None:
    for path, text in files.items():
        target = directory / "synthetic" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def _record(directory: Path, files: dict[str, str], inputs: list[str], exit_status: int = 0) -> dict[str, Any]:
    _lay_out(directory, files)
    return counts.record(directory, _sources(files, inputs, exit_status), FIXED)


FILES = {"a.ttl": CLEAN, "b.ttl": UNLABELLED}


def test_two_records_are_byte_identical_from_any_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = tmp_path / "elsewhere"
    other.mkdir()

    monkeypatch.chdir(tmp_path)
    first = counts.dump(_record(tmp_path / "corpus", FILES, ["a.ttl", "b.ttl"]), VERSION)
    monkeypatch.chdir(other)
    second = counts.dump(_record(tmp_path / "corpus", FILES, ["a.ttl", "b.ttl"]), VERSION)

    assert first == second
    assert first.endswith("\n")
    assert str(tmp_path) not in first, "paths are relative to the source"


def test_the_document_is_sorted_relative_and_has_the_version_beside_the_counts(tmp_path: Path) -> None:
    document = _record(tmp_path / "corpus", FILES, ["a.ttl", "b.ttl"])
    text = counts.dump(document, VERSION)
    loaded = json.loads(text)

    assert text == json.dumps(loaded, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    assert loaded["ontolint_version"] == VERSION
    assert "ontolint_version" not in counts.comparable(loaded)
    run = loaded["runs"]["synthetic/all"]
    assert run["exit_status"] == 0 and run["expected_exit_status"] == 0
    assert run["files"]["b.ttl"]["counts"]["LEX001"] == 2
    assert run["files"]["a.ttl"]["counts"].get("LEX001", 0) == 0
    assert loaded["command"][-4:] == FIXED


def test_adding_a_finding_makes_check_exit_1_and_diff_name_the_rule_and_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    before = _record(tmp_path / "one", FILES, ["a.ttl", "b.ttl"])
    changed = {**FILES, "a.ttl": CLEAN + ":D a owl:Class .\n"}
    after = _record(tmp_path / "two", changed, ["a.ttl", "b.ttl"])
    committed = tmp_path / "rule-counts.json"
    committed.write_text(counts.dump(before, VERSION), encoding="utf-8")
    monkeypatch.setattr(counts, "COUNTS", committed)
    monkeypatch.setattr(counts, "fixed_arguments", lambda: FIXED)
    monkeypatch.setattr(counts.corpus, "load", lambda: _sources(changed, ["a.ttl", "b.ttl"]))

    assert counts.main(["check", str(tmp_path / "two")]) == 1

    out = capsys.readouterr().out
    assert "LEX001" in out and "a.ttl" in out
    assert "| LEX001 | `synthetic/all` `a.ttl` | 0 | 1 | +1 |" in counts.diff(before, after)


def test_check_passes_when_nothing_changed_even_if_the_version_did(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    document = _record(tmp_path / "one", FILES, ["a.ttl", "b.ttl"])
    committed = tmp_path / "rule-counts.json"
    committed.write_text(counts.dump(document, "0.0.1"), encoding="utf-8")
    monkeypatch.setattr(counts, "COUNTS", committed)
    monkeypatch.setattr(counts, "fixed_arguments", lambda: FIXED)
    monkeypatch.setattr(counts.corpus, "load", lambda: _sources(FILES, ["a.ttl", "b.ttl"]))

    assert counts.main(["check", str(tmp_path / "one")]) == 0
    assert capsys.readouterr().out == ""


def test_a_file_that_now_exits_2_is_a_status_change_not_a_count_change(tmp_path: Path) -> None:
    before = _record(tmp_path / "one", {"b.ttl": UNLABELLED}, ["b.ttl"])
    after = _record(tmp_path / "two", {"b.ttl": BROKEN}, ["b.ttl"])

    assert after["runs"]["synthetic/all"]["exit_status"] == 2
    assert "error" in after["runs"]["synthetic/all"]
    assert "files" not in after["runs"]["synthetic/all"], "a file that could not be linted has no counts, not zeros"
    report = counts.diff(before, after)
    assert "### Status changes" in report
    assert "| `synthetic/all` | exit status | 0 -> 2 |" in report
    assert "### By file" not in report, "no count changed: there are none to compare"
    assert counts.unexpected_exits(after) == ["synthetic/all: exited 2, the manifest expects 0"]


def test_record_and_check_fail_for_an_exit_status_the_manifest_does_not_expect(tmp_path: Path) -> None:
    document = _record(tmp_path / "one", {"b.ttl": UNLABELLED}, ["b.ttl"], exit_status=2)

    assert counts.unexpected_exits(document) == ["synthetic/all: exited 0, the manifest expects 2"]


def test_a_rule_that_doubled_is_flagged_and_a_new_one_is_called_new() -> None:
    def document(**per_rule: int) -> dict[str, Any]:
        return {"runs": {"s/r": {"exit_status": 0, "files": {"f.ttl": {"counts": per_rule}}}}}

    report = counts.diff(document(LEX001=10, GOV004=4, SKOS001=5), document(LEX001=20, GOV004=7, SKOS001=0, OWL001=1))

    assert "| LEX001 | 10 | 20 | +10 **doubled** |" in report
    assert "| GOV004 | 4 | 7 | +3 |" in report
    assert "| SKOS001 | 5 | 0 | -5 |" in report
    assert "| OWL001 | 0 | 1 | +1 new |" in report
    assert counts.diff(document(LEX001=3), document(LEX001=3)) == ""


def test_failed_and_unsupported_rules_are_recorded_and_not_counted_as_zero(tmp_path: Path) -> None:
    report = {
        "findings": [{"rule": "LEX001", "path": str(tmp_path / "f.ttl")}],
        "files": [
            {
                "path": str(tmp_path / "f.ttl"),
                "executions": [
                    {"rule": "LEX001", "status": "executed"},
                    {"rule": "SEM001", "status": "unsupported"},
                    {"rule": "SHACL001", "status": "failed"},
                    {"rule": "OWL001", "status": "skipped"},
                ],
            }
        ],
    }

    summary = counts.summarise(report, tmp_path)

    assert summary == {"files": {"f.ttl": {"counts": {"LEX001": 1}, "failed": ["SHACL001"], "unsupported": ["SEM001"]}}}
    before: dict[str, Any] = {"runs": {"s/r": {"exit_status": 0, **summary}}}
    after = copy.deepcopy(before)
    after["runs"]["s/r"]["files"]["f.ttl"]["failed"] = []
    del after["runs"]["s/r"]["files"]["f.ttl"]["failed"]
    assert "| `s/r` `f.ttl` | failed rules | SHACL001 -> none |" in counts.diff(before, after)


def test_a_finding_about_a_module_of_the_closure_counts_on_that_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = {
        "findings": [
            {"rule": "GOV004", "path": str(tmp_path / "m" / "mod.ttl")},
            {"rule": "GOV004", "path": "top.ttl"},
        ],
        "files": [{"path": "top.ttl", "executions": []}],
    }

    monkeypatch.chdir(tmp_path)
    summary = counts.summarise(report, tmp_path)

    assert sorted(summary["files"]) == ["m/mod.ttl", "top.ttl"]
    assert summary["files"]["m/mod.ttl"]["counts"] == {"GOV004": 1}


def test_a_finding_on_a_file_outside_the_source_is_refused_not_recorded_as_an_absolute_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "source"
    root.mkdir()
    report = {
        "findings": [{"rule": "GOV004", "path": str(tmp_path / "elsewhere" / "imported.ttl")}],
        "files": [{"path": "top.ttl", "executions": []}],
    }
    monkeypatch.chdir(root)

    with pytest.raises(SystemExit, match="outside the source directory"):
        counts.summarise(report, root)


def test_record_refuses_a_directory_that_is_not_the_pinned_corpus(tmp_path: Path) -> None:
    _lay_out(tmp_path / "corpus", FILES)
    sources = _sources({**FILES, "a.ttl": CLEAN + "# edited\n"}, ["a.ttl", "b.ttl"])

    with pytest.raises(SystemExit, match="not the pinned corpus"):
        counts.record(tmp_path / "corpus", sources, FIXED)


def test_diff_command_prints_a_table_or_says_there_is_none(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    same = tmp_path / "a.json"
    same.write_text(json.dumps({"runs": {}}), encoding="utf-8")

    assert counts.main(["diff", str(same), str(same)]) == 0
    assert capsys.readouterr().out == "No difference.\n"


def test_the_fixed_command_is_the_manifests() -> None:
    assert counts.fixed_arguments() == ["--format", "json", "--fail-on", "never"]
    manifest = json.loads(corpus.MANIFEST.read_text(encoding="utf-8"))
    assert manifest["counts"]["file"] == counts.COUNTS.name


def test_the_committed_counts_are_the_runs_of_the_manifest_and_use_relative_paths() -> None:
    committed = json.loads(counts.COUNTS.read_text(encoding="utf-8"))
    sources = corpus.load()

    assert committed["ontolint_version"]
    assert list(committed["runs"]) == sorted(committed["runs"])
    assert set(committed["runs"]) == {f"{s.id}/{run.name}" for s in sources for run in s.runs}
    for name, run in committed["runs"].items():
        assert run["exit_status"] == run["expected_exit_status"], name
        assert "error" not in run, name
        assert not any(path.startswith("/") for path in run["files"]), name
    assert counts.unexpected_exits(committed) == []
    assert counts.dump(committed, committed["ontolint_version"]) == counts.COUNTS.read_text(encoding="utf-8")


def test_record_writes_nothing_when_a_run_does_not_exit_as_the_manifest_expects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = {"command": [], "runs": {"s/r": {"exit_status": 2, "expected_exit_status": 0, "error": "refused"}}}
    target = tmp_path / "rule-counts.json"
    monkeypatch.setattr(counts, "COUNTS", target)
    monkeypatch.setattr(counts, "record", lambda *args, **kwargs: bad)

    assert counts.main(["record", str(tmp_path)]) == 1

    assert not target.exists(), "a baseline that records an unexpected exit is not written"
    assert "Nothing written" in capsys.readouterr().out
