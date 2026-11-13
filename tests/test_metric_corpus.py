"""scripts/metric_corpus.py and the METRIC calibration corpus it measures (docs/validation/metric-calibration.md)."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

from ontolint.policy import METRIC_FIELDS, Policy
from ontolint.rules import metrics

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "scripts" / "metric_corpus.py"
spec = importlib.util.spec_from_file_location("metric_corpus", SCRIPT)
assert spec is not None
assert spec.loader is not None
metric_corpus = importlib.util.module_from_spec(spec)
sys.modules["metric_corpus"] = metric_corpus
spec.loader.exec_module(metric_corpus)

# Ten owned classes: four labelled (two tagged), two defined (3 and 5 words), C1-C3 under C0, one
# object property with a domain and no documentation.
FIXTURE = """\
@prefix : <https://example.test/o#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .

<https://example.test/o> a owl:Ontology .
:C0 a owl:Class ; rdfs:label "zero"@en ; skos:definition "A b c" .
:C1 a owl:Class ; rdfs:subClassOf :C0 ; rdfs:label "one"@en ; skos:definition "One two three four five" .
:C2 a owl:Class ; rdfs:subClassOf :C0 ; rdfs:label "two" .
:C3 a owl:Class ; rdfs:subClassOf :C0 ; rdfs:label "three" .
:C4 a owl:Class . :C5 a owl:Class . :C6 a owl:Class . :C7 a owl:Class . :C8 a owl:Class . :C9 a owl:Class .
:p a owl:ObjectProperty ; rdfs:domain :C0 .
"""


def _manifest() -> dict[str, Any]:
    return json.loads(metric_corpus.MANIFEST.read_text(encoding="utf-8"))


def _results() -> dict[str, Any]:
    return json.loads(metric_corpus.RESULTS.read_text(encoding="utf-8"))


def test_the_script_knows_every_metric_rule() -> None:
    assert tuple(rule.rule_id for rule in metrics.SPECS) == metric_corpus.RULES
    assert set(metric_corpus.MESSAGES) == set(metric_corpus.RULES) - {"METRIC007"}


def test_the_forced_policy_sets_every_metric_key_and_is_valid() -> None:
    assert set(metric_corpus.FORCED_POLICY) == set(METRIC_FIELDS)
    Policy.from_mapping(metric_corpus.FORCED_POLICY)  # raises on an invalid value


def test_every_manifest_entry_is_pinned_licensed_and_labelled_well() -> None:
    data = _manifest()
    assert data["label_status"] in {"proposed", "approved"}
    ids = [entry["id"] for entry in data["entries"]]
    assert len(ids) == len(set(ids))
    for entry in data["entries"]:
        assert re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]), entry["id"]
        assert entry["url"].startswith("https://"), entry["id"]
        assert entry["licence"], entry["id"]
        if entry["commit"] is not None:
            assert re.fullmatch(r"[0-9a-f]{40}", entry["commit"]), entry["id"]
            assert f"/{entry['commit']}/" in entry["url"], entry["id"]
        assert set(entry["labels"]) <= {"*", *metric_corpus.RULES}, entry["id"]
        # Every rule is labelled, by name or through "*": an omission is never read as a judgement.
        assert "*" in entry["labels"] or set(entry["labels"]) == set(metric_corpus.RULES), entry["id"]
        for label in entry["labels"].values():
            assert label["expect"] in metric_corpus.EXPECTS, entry["id"]
            assert label["basis"] in metric_corpus.BASES, entry["id"]
            assert label["why"].strip(), entry["id"]
    metric_corpus.load_manifest()  # validates every (entry, rule) pair


def test_an_entry_that_leaves_a_rule_unlabelled_is_refused(tmp_path: Path) -> None:
    data = _manifest()
    mfto = next(entry for entry in data["entries"] if entry["id"] == "mfto.ttl")
    del mfto["labels"]["*"]
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match=r"mfto\.ttl: METRIC003 has no label"):
        metric_corpus.load_manifest(path)


@pytest.mark.parametrize(
    "label",
    [
        {"expect": "maybe", "basis": "checked", "why": "x"},
        {"expect": "silent", "basis": "guessed", "why": "x"},
        {"expect": "silent", "basis": "checked", "why": " "},
    ],
)
def test_a_label_without_a_known_value_basis_or_reason_is_refused(label: dict[str, str]) -> None:
    with pytest.raises(ValueError, match="needs an expect"):
        metric_corpus.validate(metric_corpus.Entry("x", "", "", {"*": label}))


def test_every_counted_positive_or_negative_finding_rests_on_a_checked_label() -> None:
    """A presumed label ("curated, no known problem") may only make a true negative, never a TP, FP or FN."""
    results = _results()["results"]
    for entry in metric_corpus.load_manifest():
        for rule in metric_corpus.RULES:
            found = metric_corpus.outcome(entry, rule, results[entry.id][rule]["fires"])
            if found in ("tp", "fp", "fn"):
                assert entry.label(rule)["basis"] == "checked", (entry.id, rule, found)


def test_the_results_cover_every_entry_and_rule() -> None:
    results = _results()["results"]
    assert set(results) == {entry.id for entry in metric_corpus.load_manifest()}
    for cells in results.values():
        assert list(cells) == list(metric_corpus.RULES)
        for cell in cells.values():
            assert isinstance(cell["fires"], bool)
            assert isinstance(cell["measured"], str)


def test_the_page_shows_the_recorded_results_and_labels() -> None:
    expected = metric_corpus.render(metric_corpus.load_manifest(), _results(), metric_corpus.label_status())
    assert metric_corpus.generated_part() == expected, "run: uv run python scripts/metric_corpus.py render"


def test_the_thresholds_page_counts_agree_with_the_corpus() -> None:
    """docs/metric-thresholds.md quotes the false positives per rule; they must be the corpus's."""
    counts = metric_corpus.confusion(metric_corpus.load_manifest(), _results())
    page = (ROOT / "docs" / "metric-thresholds.md").read_text(encoding="utf-8")
    assert f"({sum(c['fp'] for c in counts.values())} in all)" in page
    assert all(counts[rule]["fp"] == 0 and counts[rule]["fn"] == 0 for rule in ("METRIC001", "METRIC002", "METRIC003"))


def test_the_pages_quote_the_label_counts_of_the_manifest() -> None:
    """The prose says how many labels are presumed, checked, left open and not assessed; keep it true."""
    entries = metric_corpus.load_manifest()
    labels = [entry.label(rule) for entry in entries for rule in metric_corpus.RULES]
    presumed = sum(label["basis"] == "presumed" for label in labels)
    checked = sum(label["basis"] == "checked" for label in labels)
    open_ = sum(label["expect"] == "unknown" for label in labels)
    unassessed = sum(label["expect"] == "unassessed" for label in labels)
    calibration = metric_corpus.PAGE.read_text(encoding="utf-8")
    thresholds = (ROOT / "docs" / "metric-thresholds.md").read_text(encoding="utf-8")
    assert f"Of the {len(labels)} (file, rule) pairs, {presumed} are labelled silent only" in calibration
    assert f"{presumed} of its {len(labels)} (file, rule) labels are presumed" in thresholds
    assert f"checked` (the reason was\nverified in the file: {checked} pairs)" in calibration
    assert f"`unknown` (assessed, left to the maintainer: {open_} pairs)" in calibration
    assert f"`unassessed` (not looked at: {unassessed} pairs" in calibration
    fired = {rule for entry in entries for rule in metric_corpus.RULES if entry.expect(rule) == "fire"}
    assert fired == {"METRIC001", "METRIC002", "METRIC003"}, "the pages say recall is unmeasured for METRIC004-013"


def test_a_forced_and_a_default_run_measure_a_known_fixture(tmp_path: Path) -> None:
    path = tmp_path / "fixture.ttl"
    path.write_text(FIXTURE, encoding="utf-8")
    forced = tmp_path / "forced.json"
    forced.write_text(json.dumps(metric_corpus.FORCED_POLICY), encoding="utf-8")
    measured = metric_corpus.parse_forced(metric_corpus._lint(path, forced))
    assert {rule: cell["measured"] for rule, cell in measured.items()} == {
        "METRIC001": "6 / 10",
        "METRIC002": "8 / 10",
        "METRIC003": "1 / 1",
        "METRIC004": "3.00 over 1",
        "METRIC005": "6 / 10",
        "METRIC006": "1 / 10",
        "METRIC007": "1 / 10",
        "METRIC008": "0",
        "METRIC009": "2 / 4",
        "METRIC010": "0",
        "METRIC011": "0",
        "METRIC012": "4.00 over 2",
        "METRIC013": "0",
    }
    # At the defaults: 0.6 > 0.5 and 0.8 > 0.5 fire, 0.6 > 0.3 fires, 0.1 is not below 0.1, and the
    # property and labelled-term populations are below the sample gate of 10.
    assert set(metric_corpus._lint(path, None)) == {"METRIC001", "METRIC002", "METRIC005"}


@pytest.mark.parametrize(
    "message",
    [
        "Half of the classes lack a label.",
        # The opening numbers are kept, the rest is new: a prefix match would read 6 of 10.
        "6 of 10 classes lack a label (0.60 > 0.00). Deprecated classes are now counted.",
        "6 of 10 classes lack a label or a definition (0.60 > 0.00).",
    ],
)
def test_an_altered_message_is_an_error_not_an_old_measurement(message: str) -> None:
    with pytest.raises(ValueError, match="METRIC001"):
        metric_corpus.parse_forced({"METRIC001": message})


def test_outcomes_follow_the_labels_the_wildcard_and_the_basis() -> None:
    def label(expect: str, basis: str = "checked") -> dict[str, str]:
        return {"expect": expect, "basis": basis, "why": "x"}

    entries = [
        metric_corpus.Entry("a", "", "", {"*": label("silent", "presumed"), "METRIC001": label("fire")}),
        metric_corpus.Entry(
            "b",
            "",
            "",
            {"*": label("unassessed", "none"), "METRIC001": label("silent"), "METRIC002": label("unknown")},
        ),
    ]
    fires = {"a": {"METRIC001", "METRIC002"}, "b": {"METRIC001"}}
    results = {"results": {e: {r: {"fires": r in fires[e]} for r in metric_corpus.RULES} for e in fires}}
    counts = metric_corpus.confusion(entries, results)
    zero = dict.fromkeys(metric_corpus.OUTCOMES, 0)
    assert counts["METRIC001"] == {**zero, "tp": 1, "fp": 1}
    assert counts["METRIC002"] == {**zero, "fp": 1, "unknown": 1}
    assert counts["METRIC003"] == {**zero, "tn_presumed": 1, "unassessed": 1}


def test_writing_the_page_keeps_the_text_around_an_empty_block(tmp_path: Path) -> None:
    page = tmp_path / "page.md"
    page.write_text(f"head\n\n{metric_corpus.BEGIN}\n{metric_corpus.END}\n\ntail\n", encoding="utf-8")
    metric_corpus.write_page("table", page)
    assert page.read_text(encoding="utf-8") == f"head\n\n{metric_corpus.BEGIN}\ntable\n{metric_corpus.END}\n\ntail\n"
    metric_corpus.write_page("other", page)
    assert metric_corpus.generated_part(page) == "other"
    assert page.read_text(encoding="utf-8").endswith(f"{metric_corpus.END}\n\ntail\n")


def test_a_page_without_both_markers_is_refused(tmp_path: Path) -> None:
    page = tmp_path / "page.md"
    page.write_text(f"head\n{metric_corpus.BEGIN}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must hold"):
        metric_corpus.write_page("table", page)


def test_measure_refuses_a_file_whose_checksum_changed(tmp_path: Path) -> None:
    (tmp_path / "x.ttl").write_text(FIXTURE, encoding="utf-8")
    entry = metric_corpus.Entry("x.ttl", "https://example.test/x.ttl", "0" * 64, {})
    with pytest.raises(SystemExit, match="missing or changed"):
        metric_corpus.measure(tmp_path, [entry])


def test_fetch_refuses_a_download_whose_checksum_differs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self) -> bytes:
            return b"tampered"

    monkeypatch.setattr(metric_corpus.urllib.request, "urlopen", lambda *_args, **_kwargs: Response())
    entry = metric_corpus.Entry("x.ttl", "https://example.test/x.ttl", "0" * 64, {})
    with pytest.raises(SystemExit, match="differs from the manifest"):
        metric_corpus.fetch(tmp_path, [entry])
    assert not (tmp_path / "x.ttl").exists()
