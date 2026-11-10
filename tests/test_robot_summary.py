"""SEM001 summarises ROBOT's profile report; the full report stays in JSON and SARIF ``details``.

The reports below are copied from ``robot validate-profile`` (ROBOT 1.9.11) runs on small fixtures.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from ontolint.adapters import robot as robot_adapter
from ontolint.adapters.robot import summarise_profile_report
from ontolint.models import Finding
from ontolint.reporting import FileReport, RunReport, to_json, to_sarif_report

DL_HEADER = (
    "OWL 2 DL Profile Report: Ontology and imports closure NOT in profile. The following violations are present:"
)
EL_HEADER = DL_HEADER.replace("DL", "EL")


def _undeclared(iri: str, subject: str) -> str:
    return (
        f'Use of undeclared annotation property: <{iri}> in annotation [Annotation(<{iri}> "text"@en) in '
        f'AnnotationAssertion(<{iri}> <{subject}> "text"@en)]'
    )


SKOS_DEFINITION = "http://www.w3.org/2004/02/skos/core#definition"
DCT_TITLE = "http://purl.org/dc/terms/title"
DL_REPORT = "\n".join(
    [
        DL_HEADER,
        _undeclared(DCT_TITLE, "https://example.test/onto"),
        *(_undeclared(SKOS_DEFINITION, f"https://example.test/onto#T{i}") for i in range(6)),
    ]
)
EL_REPORT = "\n".join(
    [
        EL_HEADER,
        "Axiom type not allowed in profile [DisjointUnion(<https://example.test/el#C> <https://example.test/el#A> "
        "<https://example.test/el#B>) in OntologyID(OntologyIRI(<https://example.test/el>) VersionIRI(<null>))]",
        "Class expressions not allowed in profile: ObjectMaxCardinality [SubClassOf(<https://example.test/el#C> "
        "ObjectMaxCardinality(1 <https://example.test/el#q> owl:Thing)) in OntologyID(...)]",
        "Class expressions not allowed in profile: ObjectAllValuesFrom [SubClassOf(<https://example.test/el#A> "
        "ObjectAllValuesFrom(<https://example.test/el#p> <https://example.test/el#B>)) in OntologyID(...)]",
        "Class expressions not allowed in profile: ObjectUnionOf [SubClassOf(<https://example.test/el#B> "
        "ObjectUnionOf(<https://example.test/el#A> <https://example.test/el#C>)) in OntologyID(...)]",
    ]
)


def test_a_dl_report_is_grouped_by_kind_and_property() -> None:
    assert summarise_profile_report(DL_REPORT) == (
        f"7 violations: Use of undeclared annotation property: {SKOS_DEFINITION} (6), {DCT_TITLE} (1)."
    )


def test_an_el_report_names_constructors_and_axiom_types() -> None:
    assert summarise_profile_report(EL_REPORT) == (
        "4 violations: Class expressions not allowed in profile: ObjectAllValuesFrom (1), ObjectMaxCardinality (1), "
        "ObjectUnionOf (1); Axiom type not allowed in profile: DisjointUnion (1)."
    )


def test_one_violation_is_singular() -> None:
    report = f"{DL_HEADER}\n{_undeclared(DCT_TITLE, 'https://example.test/onto')}"
    assert summarise_profile_report(report) == f"1 violation: Use of undeclared annotation property: {DCT_TITLE} (1)."


def test_lists_at_the_limit_are_not_cut() -> None:
    subjects = [_undeclared(f"https://example.test/p{i}", "https://example.test/s") for i in range(5)]
    kinds = [f"Kind {chr(65 + i)} not allowed [Thing]" for i in range(9)]  # with the subjects' kind: 10
    summary = summarise_profile_report("\n".join([DL_HEADER, *subjects, *kinds]))
    assert summary is not None
    assert "more" not in summary
    assert "https://example.test/p4 (1);" in summary


def test_long_lists_are_cut() -> None:
    subjects = [_undeclared(f"https://example.test/p{i}", "https://example.test/s") for i in range(7)]
    kinds = [f"Kind {chr(65 + i)} not allowed [Thing]" for i in range(11)]
    summary = summarise_profile_report("\n".join([DL_HEADER, *subjects, *kinds]))
    assert summary is not None
    assert "https://example.test/p4 (1), 2 more;" in summary
    assert "https://example.test/p5" not in summary
    assert summary.endswith("; 2 more kinds.")  # 12 kinds, 10 shown
    assert summary.startswith("18 violations: Use of undeclared annotation property: https://example.test/p0 (1)")


def test_a_kind_with_and_without_subjects_gives_its_own_count() -> None:
    report = "\n".join(
        [DL_HEADER, "Cycle in declarations: <https://example.test/a>", "Cycle in declarations", "Odd line"]
    )
    assert summarise_profile_report(report) == (
        "3 violations: Cycle in declarations (2): https://example.test/a (1); Odd line (1)."
    )


@pytest.mark.parametrize("text", ["ROBOT failed: java.lang.OutOfMemoryError", DL_HEADER, ""])
def test_no_violation_list_gives_no_summary(text: str) -> None:
    assert summarise_profile_report(text) is None


def _fake_robot(report: str | None, stderr: str = "") -> Any:  # noqa: ANN401 -- a subprocess.run stand-in
    def fake_run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        output = next(arg.split(":", 1)[0] for arg in command if arg.endswith(":/output"))
        if report is not None:
            Path(output, "profile.txt").write_text(report, encoding="utf-8")
        return subprocess.CompletedProcess(command, 1, stdout="", stderr=stderr)

    return fake_run


def test_the_finding_summarises_and_keeps_the_full_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ttl = tmp_path / "a.ttl"
    ttl.write_text("", encoding="utf-8")
    monkeypatch.setattr(robot_adapter.subprocess, "run", _fake_robot(DL_REPORT))
    [finding] = robot_adapter.robot_profile_issues(ttl, "DL", "img", 5)
    assert finding.message == (
        "ROBOT OWL DL profile validation failed: 7 violations: Use of undeclared annotation property: "
        f"{SKOS_DEFINITION} (6), {DCT_TITLE} (1)."
    )
    assert finding.details == DL_REPORT


def test_output_that_is_no_violation_list_fails_the_check(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A crash, a missing image or a permission error is no verdict on the ontology (cut at 500 characters)."""
    ttl = tmp_path / "a.ttl"
    ttl.write_text("", encoding="utf-8")
    monkeypatch.setattr(robot_adapter.subprocess, "run", _fake_robot(None, "x" * 600))
    with pytest.raises(robot_adapter.ProfileCheckFailed) as raised:
        robot_adapter.robot_profile_issues(ttl, "DL", "img", 5)
    assert str(raised.value) == f"ROBOT exited 1 without a profile report: {'x' * 500}…"
    monkeypatch.setattr(robot_adapter.subprocess, "run", _fake_robot(None, "y" * 500))
    with pytest.raises(robot_adapter.ProfileCheckFailed, match=r"report: y{500}$"):
        robot_adapter.robot_profile_issues(ttl, "DL", "img", 5)


def test_details_appear_in_json_and_sarif_only_when_set() -> None:
    plain = Finding("ONT001", "warning", "focus", "message", "fix")
    detailed = Finding("SEM001", "error", "a.ttl", "summary", "fix", "certain", "full report")
    assert "details" not in plain.to_dict()
    assert detailed.to_dict()["details"] == "full report"
    assert detailed == Finding("SEM001", "error", "a.ttl", "summary", "fix", "certain")  # identity ignores details
    report = RunReport((FileReport("a.ttl", "file:///a.ttl", (plain, detailed)),))
    assert [f.get("details") for f in to_json(report)["findings"]] == [None, "full report"]
    results = to_sarif_report(report)["runs"][0]["results"]
    assert [r.get("properties") for r in results] == [None, {"details": "full report"}]
