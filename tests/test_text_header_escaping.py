"""The text report's finding header (``[SEV] RULE focus: message``) is one physical line of visible characters.

A message or focus quotes input (a SHACL ``sh:message``, a literal an import points to), so a line break in it
would start a line that reads like a finding of its own, a bidi control would reorder what follows, and an escape
sequence would reach a terminal.  The header is escaped as the evidence lines are (:func:`ontolint.reporting.one_line`)
at render time only: ``Finding.message``, JSON, SARIF, the Markdown summary and every fingerprint keep the raw text.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rdflib import Graph

from ontolint import Linter, main
from ontolint.models import ExecutionStatus, Finding, RuleExecution
from ontolint.reporting import (
    FileReport,
    Origin,
    RunReport,
    fingerprint,
    one_line,
    render_executions,
    render_report,
    render_text,
)

PAYLOAD = "line one\nFake: [ERROR  ] SHACL001 https://evil: injected \u202ebidi \x1b[31mred"
ESCAPED_PAYLOAD = "line one\\u000AFake: [ERROR  ] SHACL001 https://evil: injected \\u202Ebidi \\u001B[31mred"
EVIDENCE_TTL = "@prefix e: <http://e/> .\ne:a e:p 1 .\n"


def _text(finding: Finding) -> str:
    return render_text(RunReport((FileReport("a.ttl", "a.ttl", (finding,)),)))


def _lines(finding: Finding) -> list[str]:
    return _text(finding).splitlines()  # splitlines also breaks at \r, \x0b, \x0c, \x1c-\x1e, \x85, U+2028, U+2029


# --- one physical header line, whichever character tries to end it -----------------------------------------------

CHARS = [
    ("\n", "\\u000A"),
    ("\r", "\\u000D"),
    ("\x0b", "\\u000B"),
    ("\x0c", "\\u000C"),
    ("\x1c", "\\u001C"),
    ("\x00", "\\u0000"),
    ("\x1b", "\\u001B"),  # ESC: a terminal escape sequence
    ("\x7f", "\\u007F"),
    ("\x85", "\\u0085"),  # C1: next line
    ("\x9b", "\\u009B"),  # C1: a single-character CSI
    ("\u2028", "\\u2028"),
    ("\u2029", "\\u2029"),
    ("\u061c", "\\u061C"),
    ("\u200b", "\\u200B"),
    ("\u200d", "\\u200D"),  # a joiner: a format character, as in the evidence lines
    ("\u200e", "\\u200E"),
    ("\u200f", "\\u200F"),
    ("\u202a", "\\u202A"),
    ("\u202e", "\\u202E"),
    ("\u2066", "\\u2066"),
    ("\u2069", "\\u2069"),
    ("\ufeff", "\\uFEFF"),
    ("\xa0", "\\u00A0"),
    ("\ue000", "\\uE000"),
    ("\ud800", "\\uD800"),  # a lone surrogate: UTF-8 cannot write it
    ("\U000e0001", "\\U000E0001"),  # a tag character, above the BMP
]


@pytest.mark.parametrize(("char", "escaped"), CHARS)
def test_a_message_never_adds_a_line_or_a_raw_control(char: str, escaped: str) -> None:
    finding = Finding("ONT001", "error", "https://e.test/a", f"x{char}y", "fix")
    assert _lines(finding) == [
        "Ontology linter: 1 finding(s)",
        f"[ERROR  ] ONT001 https://e.test/a: x{escaped}y",
        "    Fix: fix",
    ]
    _text(finding).encode("utf-8")  # strict: a lone surrogate would raise


@pytest.mark.parametrize(("char", "escaped"), CHARS)
def test_a_focus_is_escaped_the_same_way(char: str, escaped: str) -> None:
    finding = Finding("ONT001", "warning", f"https://e.test/a{char}b", "m", "fix")
    assert _lines(finding) == [
        "Ontology linter: 1 finding(s)",
        f"[WARNING] ONT001 https://e.test/a{escaped}b: m",
        "    Fix: fix",
    ]


def test_the_issue_payload_is_one_header_line() -> None:
    finding = Finding("SHACL001", "error", "https://ex.test/a", f"{PAYLOAD} [shape: _:s]", "fix")
    assert _lines(finding)[1:] == [
        f"[ERROR  ] SHACL001 https://ex.test/a: {ESCAPED_PAYLOAD} [shape: _:s]",
        "    Fix: fix",
    ]


def test_every_file_of_a_multi_file_run_keeps_its_headers_whole() -> None:
    finding = Finding("ONT001", "error", "https://e.test/a", PAYLOAD, "fix")
    report = RunReport((FileReport("a.ttl", "a.ttl", (finding,)), FileReport("b.ttl", "b.ttl", (finding,))))
    lines = render_text(report).splitlines()
    assert [line for line in lines if line.startswith("[")] == [
        f"[ERROR  ] ONT001 https://e.test/a: {ESCAPED_PAYLOAD}"
    ] * 2
    assert not any(line.startswith("Fake:") for line in lines)


# --- what must not change ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Café déjà vu, naïve, Ünï",
        "本体論 オントロジー 온톨로지",
        "emoji \U0001f600 \U0001f9d1 and a flag \U0001f1eb\U0001f1f7",
        "עברית ועוד العربية",
        "combining e\u0301 and ß, Ǆ",
        "C:\\Users\\a\\onto.ttl and \\n written with a backslash and \\u202e",
        "tab-free text with  two spaces and a trailing dot.",
        "[brackets] <angles> `ticks` \"quotes\" 'single' # hash",
    ],
)
def test_ordinary_text_is_printed_as_it_is(text: str) -> None:
    finding = Finding("ONT001", "info", f"https://e.test/{text}", text, "fix")
    assert _lines(finding)[1] == f"[INFO   ] ONT001 https://e.test/{text}: {text}"


def test_the_header_layout_is_unchanged_for_each_severity() -> None:
    for severity, label in (("error", "ERROR  "), ("warning", "WARNING"), ("info", "INFO   ")):
        finding = Finding("ONT001", severity, "f", "m", "s")
        assert _lines(finding)[1] == f"[{label}] ONT001 f: m"


def test_escaping_the_header_is_idempotent() -> None:
    assert one_line(one_line(PAYLOAD)) == one_line(PAYLOAD) == ESCAPED_PAYLOAD


def test_the_evidence_lines_are_escaped_once_and_the_header_alone_is_not_the_evidence() -> None:
    evidence = {"resultPath": "https://e.test/p", "value": '"a\u202eb"', "focusNode": "https://e.test/a"}
    finding = Finding("SHACL001", "error", "https://e.test/a", "bad \u202e", "fix", evidence=evidence)
    assert _lines(finding)[1:] == [
        "[ERROR  ] SHACL001 https://e.test/a: bad \\u202E",
        "    Fix: fix",
        "    Path: https://e.test/p",
        '    Value: "a\\u202Eb"',
    ]


def test_a_finding_keeps_its_raw_message_and_its_fingerprint() -> None:
    """The v1 baseline fingerprint hashes the message: a hash pinned on 0.15.1 shows rendering never touches it."""
    finding = Finding("SHACL001", "error", "https://ex.test/a", PAYLOAD, "fix")
    _text(finding)
    assert finding.message == PAYLOAD
    assert fingerprint(finding) == "6086c0948dd024199bff0aa75bcf67b4d1a0fb7815900241663fda20767fe862"


def test_json_sarif_and_markdown_keep_the_raw_message() -> None:
    finding = Finding("ONT001", "error", "https://e.test/a", PAYLOAD, "fix")
    report = RunReport((FileReport("a.ttl", "a.ttl", (finding,)),))
    assert json.loads(render_report(report, "json"))["findings"][0]["message"] == PAYLOAD
    sarif = json.loads(render_report(report, "sarif"))
    assert sarif["runs"][0]["results"][0]["message"]["text"].startswith(PAYLOAD)
    markdown = render_report(report, "markdown")
    assert "\\n" in markdown  # the summary's own escape (Python style), unchanged by this fix
    assert not any(line.startswith("Fake:") for line in markdown.splitlines())


# --- through the real CLI, for SHACL001 and for rules whose message quotes a literal -----------------------------

SHAPES = """\
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ex: <https://ex.test/> .
ex:S a sh:NodeShape ; sh:targetClass ex:T ;
  sh:property [ sh:path ex:p ; sh:minCount 1 ;
    sh:message "line one\\nFake: [ERROR  ] SHACL001 https://evil: injected \\u202ebidi \\u001b[31mred" ] .
"""
IMPORTS = """\
@prefix ex: <https://ex.test/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
ex:o a owl:Ontology ; owl:imports "not an iri\\nFake: [ERROR  ] SHACL001 https://evil: x\\u202e\\u001b[31m" .
"""


def _headers(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("[")]


def test_shacl001_through_the_cli_is_one_header_line(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "d.ttl").write_text("@prefix ex: <https://ex.test/> .\nex:a a ex:T .\n", encoding="utf-8")
    (tmp_path / "s.ttl").write_text(SHAPES, encoding="utf-8")
    argv = [str(tmp_path / "d.ttl"), "--shapes", str(tmp_path / "s.ttl"), "--select", "SHACL001", "--fail-on", "never"]
    assert main(argv) == 0
    out = capsys.readouterr().out
    (header,) = _headers(out)
    assert header.startswith(f"[ERROR  ] SHACL001 https://ex.test/a: {ESCAPED_PAYLOAD} [shape: ")
    assert not any(line.startswith("Fake:") for line in out.splitlines())
    assert "\u202e" not in out and "\x1b" not in out
    assert main([*argv, "--format", "json"]) == 0
    (finding,) = json.loads(capsys.readouterr().out)["findings"]
    assert finding["message"].startswith(PAYLOAD)  # JSON keeps the raw string


def test_other_rules_with_an_input_derived_message_through_the_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """GOV002 and SEC007 quote the literal an ``owl:imports`` points to."""
    (tmp_path / "o.ttl").write_text(IMPORTS, encoding="utf-8")
    assert main([str(tmp_path / "o.ttl"), "--select", "GOV002,SEC007", "--fail-on", "never"]) == 0
    out = capsys.readouterr().out
    escaped = "not an iri\\u000AFake: [ERROR  ] SHACL001 https://evil: x\\u202E\\u001B[31m."
    assert _headers(out) == [
        f"[INFO   ] GOV002 https://ex.test/o: Non-IRI import target: {escaped}",
        f"[INFO   ] SEC007 (imports): 1 owl:import was not followed: {escaped}",
    ]
    assert not any(line.startswith("Fake:") for line in out.splitlines())


def test_owl027_message_with_a_literal_value_is_one_line() -> None:
    data = Graph().parse(
        data=(
            "@prefix ex: <https://ex.test/> . @prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
            'ex:a ex:p "v\\nFake: [ERROR  ] X\\u202e" .\n'
            "[] a owl:NegativePropertyAssertion ; owl:sourceIndividual ex:a ; owl:assertionProperty ex:p ;"
            ' owl:targetValue "v\\nFake: [ERROR  ] X\\u202e" .\n'
        ),
        format="turtle",
    )
    result = Linter(data).execute(["OWL027"])
    (finding,) = result.findings
    assert "\n" in finding.message  # the finding itself carries the raw literal
    text = render_report(RunReport((FileReport("a.ttl", "a.ttl", (finding,)),)), "text")
    assert len(_headers(text)) == 1
    assert [line for line in text.splitlines() if line.startswith("Fake:")] == []
    assert "with v\\u000AFake: [ERROR  ] X\\u202E contradicts" in text


# --- the baseline and the quality snapshot do not move -----------------------------------------------------------


def test_a_baseline_written_from_a_hostile_run_holds_the_raw_message_fingerprint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "o.ttl"
    source.write_text(IMPORTS, encoding="utf-8")
    baseline = tmp_path / "b.json"
    assert main([str(source), "--select", "GOV002", "--fail-on", "never", "--write-baseline", str(baseline)]) == 0
    capsys.readouterr()
    shown = json.loads(baseline.read_text(encoding="utf-8"))
    raw = Finding(
        "GOV002",
        "info",
        "https://ex.test/o",
        "Non-IRI import target: not an iri\nFake: [ERROR  ] SHACL001 https://evil: x\u202e\x1b[31m.",
        "",
    )
    assert fingerprint(raw) in json.dumps(shown)
    # the same baseline suppresses the finding on a second run (so the text report is not part of the identity)
    assert main([str(source), "--select", "GOV002", "--baseline", str(baseline)]) == 0
    assert capsys.readouterr().out == "Ontology linter: 0 finding(s)\n"


# --- the rest of the text report: file headings, locations, module names and execution details (#125, #133) ---------

HOSTILE = "a\nFake: [ERROR  ] ONT001 https://evil: injected \u202e\x1b[31m.ttl"
HOSTILE_ESCAPED = "a\\u000AFake: [ERROR  ] ONT001 https://evil: injected \\u202E\\u001B[31m.ttl"
OWN_LINES = ("Ontology linter:", "== ", "[ERROR", "[FAILED", "    Fix:", "    In:", "Findings by module:", "    ")


def _no_added_line(text: str, allowed: tuple[str, ...]) -> None:
    """Every physical line of ``text`` starts as the report's own lines do: nothing a name wrote starts one."""
    for line in text.splitlines():
        assert line.startswith(allowed), line
    assert "\x1b" not in text
    assert "\u202e" not in text


def test_a_file_name_is_escaped_in_the_heading_of_a_multi_file_run() -> None:
    finding = Finding("ONT001", "error", "https://e.test/a", "m", "fix")
    report = RunReport((FileReport(HOSTILE, HOSTILE, (finding,)), FileReport("b.ttl", "b.ttl", (finding,))))

    text = render_text(report)

    assert f"== {HOSTILE_ESCAPED}: 1 finding(s)" in text.splitlines()
    _no_added_line(text, OWN_LINES)


def test_a_module_name_is_escaped_in_the_findings_by_module_summary() -> None:
    finding = Finding("ONT001", "error", "https://e.test/a", "m", "fix")
    report = RunReport((FileReport("a.ttl", "a.ttl", (finding,), modules={finding: (HOSTILE,)}),))

    text = render_text(report)

    assert f"    {HOSTILE_ESCAPED}: 1 error" in text.splitlines()
    _no_added_line(text, OWN_LINES)


def test_the_in_line_escapes_the_module_file_the_graph_and_the_module_names() -> None:
    finding = Finding("ONT001", "error", "https://e.test/a", "m", "fix")
    file = FileReport(
        "a.ttl",
        "a.ttl",
        (finding,),
        origins={finding: Origin(HOSTILE, HOSTILE)},
        graphs={finding: (HOSTILE, "https://e.test/g")},
        modules={finding: (HOSTILE,)},
    )

    text = render_text(RunReport((file,)))

    assert f"    In: {HOSTILE_ESCAPED}, graphs {HOSTILE_ESCAPED}, https://e.test/g, module {HOSTILE_ESCAPED}" in text
    _no_added_line(text, OWN_LINES)


def test_a_rule_execution_detail_is_escaped() -> None:
    execution = RuleExecution("SHACL001", ExecutionStatus.FAILED, f"ValueError: {HOSTILE}")

    text = render_executions([execution])

    assert text.splitlines()[1] == f"[FAILED     ] SHACL001: ValueError: {HOSTILE_ESCAPED}"
    _no_added_line(text, ("Rule execution:", "[FAILED"))


def test_the_execution_lines_of_a_multi_file_run_escape_the_file_name_too() -> None:
    execution = RuleExecution("SHACL001", ExecutionStatus.FAILED, f"boom {HOSTILE}")
    report = RunReport(
        (
            FileReport(HOSTILE, HOSTILE, (), (execution,)),
            FileReport("b.ttl", "b.ttl", (), (RuleExecution("SHACL001", ExecutionStatus.EXECUTED),)),
        )
    )

    text = render_report(report, "text")

    assert f"{HOSTILE_ESCAPED}: Rule execution:" in text
    _no_added_line(text, (*OWN_LINES, "b.ttl:"))


def test_json_and_sarif_keep_the_raw_names_and_details() -> None:
    finding = Finding("ONT001", "error", "https://e.test/a", "m", "fix")
    execution = RuleExecution("SHACL001", ExecutionStatus.FAILED, HOSTILE)
    report = RunReport((FileReport(HOSTILE, HOSTILE, (finding,), (execution,), modules={finding: (HOSTILE,)}),))

    document = json.loads(render_report(report, "json"))

    assert document["files"][0]["path"] == HOSTILE
    assert document["files"][0]["executions"][0]["detail"] == HOSTILE
    assert json.dumps(HOSTILE)[1:-1] in render_report(report, "sarif")  # the raw text, as JSON writes it


def test_ordinary_names_print_as_they_did() -> None:
    finding = Finding("ONT001", "error", "https://e.test/a", "m", "fix")
    file = FileReport(
        "dir/Café ünï.ttl",
        "x",
        (finding,),
        origins={finding: Origin("mod/本体.ttl", "x")},
        modules={finding: ("モジュール",)},
    )

    text = render_text(RunReport((file, FileReport("b.ttl", "b.ttl", ()))))

    assert "== dir/Café ünï.ttl: 1 finding(s)" in text
    assert "    In: mod/本体.ttl, module モジュール" in text
    assert "    モジュール: 1 error" in text
