"""Version 2 baselines: findings are matched by rule, focus and subject, never by message wording.

A version 1 fingerprint hashes ``(rule, focus, message)`` (and the path in a multi-file run), so a reworded
message, a pySHACL upgrade or a ratio that moves makes a baselined finding reappear, and a baseline written
from one file matches nothing in a multi-file run. ``--write-baseline`` now also records, per report path,
the message-independent identity of each finding next to its version 1 hash; ``--baseline`` accepts either.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from rdflib import Graph
from rule_cases import load_cases
from rule_harness import graph
from test_shacl_evidence import FAMILIES, INTEGER_AGE, TWO_VALUES, _graphs

from ontolint import Linter, baseline, engine, main
from ontolint.baseline import Baseline, BaselineError
from ontolint.models import Finding
from ontolint.reporting import IDENTITY_TAG, FileReport, fingerprint, identity
from ontolint.rules import runtime
from ontolint.rules.registry import default_registry

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
KITCHEN = FIXTURES / "kitchen_sink.ttl"
ALL_RULES = [spec.rule_id for spec in default_registry().all()]
CLASS_A = "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n<https://example.test/A> a owl:Class .\n"
CLASS_B = "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n<https://example.test/B> a owl:Class .\n"
HEX = re.compile(r"[0-9a-f]{64}")

type Run = Callable[..., tuple[int, dict[str, Any]]]


@pytest.fixture
def run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Run:
    """Run the CLI in ``tmp_path`` (report paths relative to it) and return its exit code and JSON report."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.ttl").write_text(CLASS_A, encoding="utf-8")
    (tmp_path / "b.ttl").write_text(CLASS_B, encoding="utf-8")

    def invoke(*argv: str) -> tuple[int, dict[str, Any]]:
        code = main([*argv, "--format", "json", "--output", "out.json"])
        return code, json.loads(Path("out.json").read_text(encoding="utf-8"))

    return invoke


def _messages(document: dict[str, Any]) -> list[str]:
    return [f["message"] for f in document["findings"]]


# --- identity ------------------------------------------------------------------------------------------


def test_identity_hashes_a_tagged_rule_focus_subject_list() -> None:
    finding = Finding("OWL004", "warning", "https://example.test/p", "message", "fix", subject=("x", "é"))
    payload = json.dumps([IDENTITY_TAG, "OWL004", "https://example.test/p", ["x", "é"]], ensure_ascii=False)
    import hashlib  # noqa: PLC0415 -- the expected digest, spelled out

    expected = hashlib.sha256(payload.replace(", ", ",").encode("utf-8")).hexdigest()
    assert identity(finding) == expected
    assert IDENTITY_TAG == "ontolint-identity-2"


def test_identity_ignores_message_severity_fix_confidence_and_evidence() -> None:
    base = Finding("OWL004", "warning", "f", "message", "fix", subject=("x",))
    other = replace(base, message="other", severity="error", suggestion="y", confidence="certain", evidence={})
    assert identity(other) == identity(base)
    assert identity(replace(base, subject=("y",))) != identity(base)
    assert identity(replace(base, subject=("x", ""))) != identity(base)
    assert identity(replace(base, focus="g")) != identity(base)
    assert identity(replace(base, rule="OWL005")) != identity(base)


def test_an_identity_is_never_a_version_1_fingerprint() -> None:
    # The tag makes the payloads differ even for a finding whose message is the tag.
    finding = Finding("ONT001", "warning", "f", IDENTITY_TAG, "fix")
    assert identity(finding) not in {fingerprint(finding), fingerprint(finding, "a.ttl")}


def test_identity_survives_a_lone_surrogate() -> None:
    finding = Finding("ONT001", "warning", "\ud800", "m", "fix", subject=("\udfff",))
    assert HEX.fullmatch(identity(finding))


# --- the regressions -----------------------------------------------------------------------------------


def test_rewording_every_message_keeps_every_baselined_finding(run: Run, monkeypatch: pytest.MonkeyPatch) -> None:
    code, before = run("a.ttl", "--write-baseline", "base.json", "--fail-on", "never")
    assert code == 0
    assert before["findings"]
    original = runtime.RuleContext._message_text  # noqa: SLF001
    monkeypatch.setattr(runtime.RuleContext, "_message_text", lambda self, m: "Reworded: " + original(self, m))

    code, after = run("a.ttl", "--baseline", "base.json", "--fail-on", "info", "--fail-on-stale-baseline")

    assert code == 0
    assert after["findings"] == []
    assert after["baseline"]["stale_fingerprints"] == []
    code, plain = run("a.ttl", "--fail-on", "never")
    assert _messages(plain) and all(m.startswith("Reworded: ") for m in _messages(plain))


def test_a_one_file_baseline_applies_to_that_file_in_a_multi_file_run(run: Run) -> None:
    run("a.ttl", "--write-baseline", "base.json", "--fail-on", "never")
    _code, alone = run("b.ttl", "--fail-on", "never")

    code, both = run("a.ttl", "b.ttl", "--baseline", "base.json", "--fail-on", "never", "--fail-on-stale-baseline")

    assert code == 0
    assert both["findings"]
    assert {f["path"] for f in both["findings"]} == {"b.ttl"}
    assert _messages(both) == _messages(alone)
    assert both["baseline"]["stale_fingerprints"] == []


def test_a_multi_file_baseline_applies_to_one_of_its_files_alone(run: Run) -> None:
    run("a.ttl", "b.ttl", "--write-baseline", "multi.json", "--fail-on", "never")
    written = json.loads(Path("multi.json").read_text(encoding="utf-8"))
    b_entries = set(written["identities"]["b.ttl"].values())

    code, alone = run("a.ttl", "--baseline", "multi.json", "--fail-on", "info")

    assert code == 0
    assert alone["findings"] == []
    # b.ttl was not linted, so its entries are stale, as entries of unselected rules are.
    assert set(alone["baseline"]["stale_fingerprints"]) == b_entries


def test_a_one_file_baseline_still_follows_a_renamed_file(run: Run) -> None:
    run("a.ttl", "--write-baseline", "base.json", "--fail-on", "never")
    Path("renamed.ttl").write_text(CLASS_A, encoding="utf-8")
    code, document = run("renamed.ttl", "--baseline", "base.json", "--fail-on", "info")
    assert code == 0
    assert document["findings"] == []


def test_a_one_file_baseline_follows_a_renamed_file_through_a_rewording(
    run: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the message, only the identity can match, and the paths differ: a one-file run is path-free."""
    run("a.ttl", "--write-baseline", "base.json", "--fail-on", "never")
    Path("renamed.ttl").write_text(CLASS_A, encoding="utf-8")
    original = runtime.RuleContext._message_text  # noqa: SLF001
    monkeypatch.setattr(runtime.RuleContext, "_message_text", lambda self, m: "Reworded: " + original(self, m))
    code, document = run("renamed.ttl", "--baseline", "base.json", "--fail-on", "info", "--fail-on-stale-baseline")
    assert code == 0
    assert document["findings"] == []
    assert document["baseline"]["stale_fingerprints"] == []


def test_a_one_file_baseline_does_not_apply_to_another_file_of_a_multi_file_run(run: Run) -> None:
    run("a.ttl", "--write-baseline", "base.json", "--fail-on", "never")
    Path("c.ttl").write_text(CLASS_A, encoding="utf-8")  # the same findings as a.ttl, in another file
    _code, alone = run("b.ttl", "c.ttl", "--fail-on", "never")
    _code, document = run("b.ttl", "c.ttl", "--baseline", "base.json", "--fail-on", "never")
    assert document["findings"] == alone["findings"]


def test_a_multi_file_baseline_with_one_file_of_findings_is_not_path_free(run: Run) -> None:
    Path("clean.ttl").write_text((FIXTURES / "clean.ttl").read_text(encoding="utf-8"), encoding="utf-8")
    run("a.ttl", "clean.ttl", "--write-baseline", "multi.json", "--fail-on", "never")
    written = json.loads(Path("multi.json").read_text(encoding="utf-8"))
    assert written["files"] == ["a.ttl", "clean.ttl"]
    assert list(written["identities"]) == ["a.ttl"]
    Path("c.ttl").write_text(CLASS_A, encoding="utf-8")
    _code, alone = run("c.ttl", "--fail-on", "never")

    _code, document = run("c.ttl", "--baseline", "multi.json", "--fail-on", "never")

    assert document["findings"] == alone["findings"]


# --- every rule ----------------------------------------------------------------------------------------


def _cases() -> Iterator[tuple[str, Graph, Graph | None, dict[str, Any]]]:
    for rule_id, cases in sorted(load_cases().items()):
        for case in cases.positive:
            if case.probe is None:
                data = case.build() if case.build is not None else graph(case.turtle)
                shapes = graph(case.shapes) if case.shapes is not None else None
                yield f"{rule_id}:{case.name}", data, shapes, dict(case.options)
    kitchen = Graph().parse(KITCHEN, format="turtle")
    yield "kitchen", kitchen, None, {}
    yield "kitchen shapes", kitchen, Graph().parse(FIXTURES / "kitchen_shapes.ttl", format="turtle"), {}
    for family, (data_text, shapes_text, _expected) in sorted(FAMILIES.items()):  # SHACL001 of each family
        yield f"SHACL001:{family}", *_graphs(data_text, shapes_text), {}


def _report(data: Graph, shapes: Graph | None, options: dict[str, Any]) -> FileReport:
    findings = Linter(data, shapes, **options).execute(ALL_RULES).findings
    return FileReport("o.ttl", "file:///o.ttl", findings)


@pytest.mark.slow
def test_rewording_every_message_of_every_rule_keeps_every_baseline_matching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every positive rule case and the kitchen sink: written, reworded, then applied, nothing is new or stale."""
    accepted: list[tuple[str, Baseline, tuple[Graph, Graph | None, dict[str, Any]]]] = []
    for label, data, shapes, options in _cases():
        report = _report(data, shapes, options)
        if report.findings:
            accepted.append((label, baseline.loads(baseline.dumps(baseline.build([report]))), (data, shapes, options)))
    rules = set()
    with monkeypatch.context() as patch:
        original = runtime.RuleContext._message_text  # noqa: SLF001
        patch.setattr(runtime.RuleContext, "_message_text", lambda self, m: "Reworded: " + original(self, m))
        issues = engine.shacl_issues
        patch.setattr(
            engine,
            "shacl_issues",
            lambda g, sg: [replace(f, message="Reworded: " + f.message) for f in issues(g, sg)],
        )
        problems: dict[str, tuple[list[str], tuple[str, ...]]] = {}
        for label, accepted_baseline, (data, shapes, options) in accepted:
            report = _report(data, shapes, options)
            assert all(f.message.startswith("Reworded: ") for f in report.findings), label
            rules |= {f.rule for f in report.findings}
            applied = baseline.apply(accepted_baseline, [report])
            if applied.files[0].findings or applied.stale:
                problems[label] = ([f.rule for f in applied.files[0].findings], applied.stale)
    assert problems == {}
    assert len(rules) > 200  # noqa: PLR2004 -- nearly every graph rule, SHACL001 included
    assert "SHACL001" in rules


def test_a_reworded_shacl_result_stays_baselined(run: Run, monkeypatch: pytest.MonkeyPatch) -> None:
    Path("d.ttl").write_text(TWO_VALUES, encoding="utf-8")  # two datatype violations of one shape on one node
    Path("s.ttl").write_text(INTEGER_AGE, encoding="utf-8")
    shacl = ("d.ttl", "--shapes", "s.ttl", "--select", "SHACL001")
    _code, before = run(*shacl, "--write-baseline", "base.json", "--fail-on", "never")
    assert len(before["findings"]) == 2  # noqa: PLR2004
    written = json.loads(Path("base.json").read_text(encoding="utf-8"))
    assert len(written["fingerprints"]) == 1  # one message, so one version 1 hash, but
    assert len(written["identities"]["d.ttl"]) == 2  # noqa: PLR2004 -- two identities
    issues = engine.shacl_issues
    monkeypatch.setattr(
        engine, "shacl_issues", lambda g, sg: [replace(f, message="pySHACL 2: " + f.message) for f in issues(g, sg)]
    )
    _code, plain = run(*shacl, "--fail-on", "never")
    assert all(m.startswith("pySHACL 2: ") for m in _messages(plain))

    code, document = run(*shacl, "--baseline", "base.json", "--fail-on", "info", "--fail-on-stale-baseline")

    assert code == 0
    assert document["findings"] == []
    assert document["baseline"]["stale_fingerprints"] == []


def test_a_sem001_verdict_with_other_counts_stays_baselined() -> None:
    before = Finding("SEM001", "error", "(ontology)", "ROBOT OWL DL profile validation failed: 7 violations", "f")
    after = replace(before, message="ROBOT OWL DL profile validation failed: 8 violations")
    accepted = baseline.build([FileReport("o.ttl", "o.ttl", (replace(before, subject=("DL",)),))])
    applied = baseline.apply(accepted, [FileReport("o.ttl", "o.ttl", (replace(after, subject=("DL",)),))])
    assert applied.files[0].findings == ()
    assert applied.stale == ()
    other_profile = replace(after, subject=("EL",))
    assert baseline.apply(accepted, [FileReport("o.ttl", "o.ttl", (other_profile,))]).files[0].findings == (
        other_profile,
    )


# --- compatibility -------------------------------------------------------------------------------------


def _version_1_apply(text: str, reports: list[FileReport]) -> tuple[list[tuple[Finding, ...]], tuple[str, ...]]:
    """How ontolint 0.10.2 applied a baseline file (cli._apply_baselines at f7f3db4)."""
    multi = len(reports) > 1
    prior = set(json.loads(text).get("fingerprints", []))
    current = {fingerprint(f, r.path if multi else None) for r in reports for f in r.findings}
    kept = [tuple(f for f in r.findings if fingerprint(f, r.path if multi else None) not in prior) for r in reports]
    return kept, tuple(sorted(prior - current))


def _kitchen_reports() -> list[FileReport]:
    return [_report(Graph().parse(KITCHEN, format="turtle"), None, {})]


def test_a_baseline_written_by_0_10_2_gives_the_same_results() -> None:
    """``baseline_0_10_2.json``: ontolint 0.10.2's baseline of the kitchen sink, every second entry kept, plus the
    0.10.2 fingerprint of a finding that no longer occurs (so some findings are new and one entry is stale)."""
    text = (FIXTURES / "baseline_0_10_2.json").read_text(encoding="utf-8")
    reports = _kitchen_reports()
    applied = baseline.apply(baseline.loads(text), reports)
    kept, stale = _version_1_apply(text, reports)
    assert [r.findings for r in applied.files] == kept
    assert applied.stale == stale
    assert kept[0]  # the file holds only part of the findings, so both branches are exercised
    assert stale  # and one entry of a finding since fixed


def test_a_version_2_file_read_by_0_10_2_gives_the_version_1_results() -> None:
    reports = [*_kitchen_reports(), FileReport("b.ttl", "b.ttl", _kitchen_reports()[0].findings[:3])]
    text = baseline.dumps(baseline.build(reports))
    assert json.loads(text)["fingerprints"] == sorted({fingerprint(f, r.path) for r in reports for f in r.findings})
    kept, stale = _version_1_apply(text, reports)
    assert kept == [(), ()]
    assert stale == ()


def test_the_version_1_list_of_a_one_file_baseline_is_path_free() -> None:
    reports = _kitchen_reports()
    written = json.loads(baseline.dumps(baseline.build(reports)))
    assert written["fingerprints"] == sorted({fingerprint(f) for f in reports[0].findings})


# --- the file ------------------------------------------------------------------------------------------


def _finding(focus: str, message: str = "m", subject: tuple[str, ...] = ()) -> Finding:
    return Finding("ONT001", "warning", focus, message, "fix", subject=subject)


def test_the_file_records_version_files_fingerprints_and_identities_in_order() -> None:
    x, y = _finding("x"), _finding("y")
    text = baseline.dumps(baseline.build([FileReport("b.ttl", "b.ttl", (y,)), FileReport("a.ttl", "a.ttl", (x,))]))
    written = json.loads(text)
    assert list(written) == ["version", "files", "fingerprints", "identities"]
    assert written["version"] == baseline.BASELINE_VERSION == 2  # noqa: PLR2004
    assert written["files"] == ["a.ttl", "b.ttl"]
    assert written["fingerprints"] == sorted([fingerprint(y, "b.ttl"), fingerprint(x, "a.ttl")])
    assert written["identities"] == {
        "a.ttl": {identity(x): fingerprint(x, "a.ttl")},
        "b.ttl": {identity(y): fingerprint(y, "b.ttl")},
    }
    assert list(written["identities"]) == ["a.ttl", "b.ttl"]
    assert text.endswith("}\n")
    assert text == json.dumps(written, indent=2) + "\n"


def test_two_findings_with_one_identity_are_recorded_by_version_1_only() -> None:
    first, second = _finding("x", "one", ("k",)), _finding("x", "two", ("k",))
    accepted = baseline.build([FileReport("a.ttl", "a.ttl", (first, second, _finding("y")))])
    assert accepted.fingerprints == {fingerprint(first), fingerprint(second), fingerprint(_finding("y"))}
    assert list(accepted.identities["a.ttl"]) == [identity(_finding("y"))]


def test_an_ambiguous_identity_never_suppresses_a_new_finding() -> None:
    known = _finding("x", "one", ("k",))
    accepted = baseline.build([FileReport("a.ttl", "a.ttl", (known,))])
    new = _finding("x", "two", ("k",))  # a rule bug: two problems with one subject

    applied = baseline.apply(accepted, [FileReport("a.ttl", "a.ttl", (known, new))])

    assert applied.files[0].findings == (new,)
    assert applied.baselined == ((known,),)
    assert applied.stale == ()


def test_a_reworded_finding_is_accepted_by_identity_alone() -> None:
    known = _finding("x", "one", ("k",))
    accepted = baseline.build([FileReport("a.ttl", "a.ttl", (known,))])
    reworded = replace(known, message="ONE")
    applied = baseline.apply(accepted, [FileReport("a.ttl", "a.ttl", (reworded,))])
    assert applied.files[0].findings == ()
    assert applied.baselined == ((reworded,),)
    assert applied.stale == ()


def test_an_entry_is_stale_only_when_neither_hash_matches() -> None:
    kept, fixed = _finding("x", "one", ("k",)), _finding("y", "two", ("k",))
    accepted = baseline.build([FileReport("a.ttl", "a.ttl", (kept, fixed))])
    applied = baseline.apply(accepted, [FileReport("a.ttl", "a.ttl", (replace(kept, message="ONE"),))])
    assert applied.stale == (fingerprint(fixed),)


def test_entries_of_a_version_1_file_are_stale_exactly_as_before() -> None:
    known, gone = _finding("x"), _finding("y")
    v1 = baseline.loads(json.dumps({"fingerprints": [fingerprint(known), fingerprint(gone)]}))
    assert v1 == Baseline(frozenset({fingerprint(known), fingerprint(gone)}))
    applied = baseline.apply(v1, [FileReport("a.ttl", "a.ttl", (known, _finding("z")))])
    assert [r.findings for r in applied.files] == [(_finding("z"),)]
    assert applied.stale == (fingerprint(gone),)
    reworded = baseline.apply(v1, [FileReport("a.ttl", "a.ttl", (replace(known, message="M"),))])
    assert reworded.files[0].findings == (replace(known, message="M"),)  # a version 1 file matches by message


def test_unknown_keys_and_a_later_version_are_read_for_what_this_version_knows() -> None:
    known = _finding("x")
    written = json.loads(baseline.dumps(baseline.build([FileReport("a.ttl", "a.ttl", (known,))])))
    later = {**written, "version": 3, "rationale": {"x": "accepted"}}
    assert baseline.loads(json.dumps(later)) == baseline.loads(json.dumps(written))


def test_deleting_a_fingerprint_withdraws_its_identity() -> None:
    kept, withdrawn = _finding("x", "one", ("k",)), _finding("y", "two", ("k",))
    written = json.loads(baseline.dumps(baseline.build([FileReport("a.ttl", "a.ttl", (kept, withdrawn))])))
    written["fingerprints"].remove(fingerprint(withdrawn))  # its identities entry is left in place
    assert identity(withdrawn) in written["identities"]["a.ttl"]

    edited = baseline.loads(json.dumps(written))

    assert edited.identities == {"a.ttl": {identity(kept): fingerprint(kept)}}
    reworded = [replace(kept, message="ONE"), replace(withdrawn, message="TWO")]
    applied = baseline.apply(edited, [FileReport("a.ttl", "a.ttl", tuple(reworded))])
    assert applied.files[0].findings == (reworded[1],)
    assert applied.baselined == ((reworded[0],),)
    assert applied.stale == ()


MALFORMED = {
    "not json": "{",
    "not an object": "[]",
    "fingerprints a string": '{"fingerprints": "abc"}',
    "fingerprints of numbers": '{"fingerprints": [1]}',
    "version a string": '{"version": "2", "fingerprints": []}',
    "version a boolean": '{"version": true, "fingerprints": []}',
    "files a string": '{"version": 2, "files": "a.ttl", "fingerprints": []}',
    "identities a list": '{"version": 2, "fingerprints": [], "identities": []}',
    "identities of a list": '{"version": 2, "fingerprints": [], "identities": {"a.ttl": []}}',
    "identity not hex": '{"version": 2, "fingerprints": [], "identities": {"a.ttl": {"x": "y"}}}',
    "identity of a number": '{"version": 2, "fingerprints": [], "identities": {"a.ttl": {"' + "a" * 64 + '": 1}}}',
    "version 0": '{"version": 0, "fingerprints": []}',
    "version negative": '{"version": -2, "fingerprints": []}',
    "identities of an unlisted path": '{"version": 2, "files": ["a.ttl"], "identities": {"b.ttl": {}}}',
}


@pytest.mark.parametrize("text", MALFORMED.values(), ids=MALFORMED.keys())
def test_a_malformed_baseline_is_rejected(text: str) -> None:
    with pytest.raises(BaselineError):
        baseline.loads(text)


@pytest.mark.usefixtures("run")
@pytest.mark.parametrize("name", ["fingerprints a string", "identity not hex", "not json"])
def test_the_cli_reports_a_malformed_baseline_as_a_tool_failure(name: str, capsys: pytest.CaptureFixture[str]) -> None:
    Path("bad.json").write_text(MALFORMED[name], encoding="utf-8")
    code = main(["a.ttl", "--baseline", "bad.json", "--format", "json", "--output", "out.json"])
    assert code == 2  # noqa: PLR2004
    assert capsys.readouterr().err.startswith("TOOL001: lint execution failed: BaselineError: ")
