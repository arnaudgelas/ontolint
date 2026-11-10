"""A finding's structured ``evidence``: in JSON and SARIF only when set, never part of its identity."""

from __future__ import annotations

import json

from ontolint.models import Evidence, Finding, plain_evidence
from ontolint.reporting import FileReport, RunReport, fingerprint, render_report, to_json, to_sarif_report

NESTED: Evidence = {"focusNode": '"x"', "resultMessage": ("m1", "m2")}
EVIDENCE: Evidence = {
    "focusNode": "https://example.test/a",
    "value": '"x"',
    "detail": (NESTED,),
    "resultMessage": ("Value is wrong",),
}
PLAIN = {
    "focusNode": "https://example.test/a",
    "value": '"x"',
    "detail": [{"focusNode": '"x"', "resultMessage": ["m1", "m2"]}],
    "resultMessage": ["Value is wrong"],
}


def _finding(*, details: str | None = None, related: tuple[str, ...] = (), evidence: Evidence | None = None) -> Finding:
    return Finding(
        "SHACL001", "error", "https://example.test/a", "message", "fix", "certain", details, related, evidence
    )


def test_plain_evidence_turns_tuples_into_lists_and_keeps_key_order() -> None:
    plain = plain_evidence(EVIDENCE)
    assert plain == PLAIN
    assert list(plain) == ["focusNode", "value", "detail", "resultMessage"]
    assert type(plain["detail"]) is list
    assert type(plain["detail"][0]) is dict


def test_evidence_is_omitted_from_the_dict_unless_set() -> None:
    assert "evidence" not in _finding().to_dict()
    assert _finding(evidence=EVIDENCE).to_dict()["evidence"] == PLAIN
    assert _finding(evidence={}).to_dict()["evidence"] == {}  # set but empty still says so


def test_evidence_follows_details_in_the_dict() -> None:
    finding = _finding(details="full", related=("x",), evidence=EVIDENCE)
    assert list(finding.to_dict()) == [
        "rule",
        "severity",
        "focus",
        "message",
        "suggestion",
        "confidence",
        "details",
        "evidence",
    ]


def test_evidence_is_not_part_of_identity_or_fingerprint() -> None:
    plain, carrying = _finding(), _finding(evidence=EVIDENCE)
    assert plain == carrying
    assert hash(plain) == hash(carrying)
    assert fingerprint(carrying) == fingerprint(plain)
    assert fingerprint(carrying, "a.ttl") == fingerprint(plain, "a.ttl")


def test_evidence_appears_in_json_and_sarif_only_when_set() -> None:
    plain = Finding("ONT001", "warning", "focus", "message", "fix")
    carrying = _finding(evidence=EVIDENCE)
    report = RunReport((FileReport("a.ttl", "file:///a.ttl", (plain, carrying)),))
    findings = to_json(report)["findings"]
    assert [f.get("evidence") for f in findings] == [None, PLAIN]
    assert list(findings[1])[-2:] == ["evidence", "path"]
    assert json.loads(render_report(report, "json"))["findings"][1]["evidence"] == PLAIN
    results = to_sarif_report(report)["runs"][0]["results"]
    assert [r.get("properties") for r in results] == [None, {"evidence": PLAIN}]


def test_sarif_properties_keep_details_evidence_graphs_modules_order() -> None:
    finding = _finding(details="full", evidence=EVIDENCE)
    file = FileReport("a.trig", "file:///a.trig", (finding,), graphs={finding: ("g",)}, modules={finding: ("m",)})
    (result,) = to_sarif_report(RunReport((file,)))["runs"][0]["results"]
    assert list(result["properties"]) == ["details", "evidence", "graphs", "modules"]
    assert result["properties"]["evidence"] == PLAIN
    document = to_json(RunReport((file,)))
    assert list(document["findings"][0])[-5:] == ["details", "evidence", "path", "graphs", "modules"]


def test_text_output_never_shows_evidence() -> None:
    plain, carrying = _finding(), _finding(evidence=EVIDENCE)
    assert render_report(RunReport((FileReport("a.ttl", "a.ttl", (carrying,)),)), "text") == render_report(
        RunReport((FileReport("a.ttl", "a.ttl", (plain,)),)), "text"
    )
