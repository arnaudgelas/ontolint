"""A finding's structured ``evidence``: never part of its identity; JSON and SARIF carry it in full when set, and
text prints its path, value and nested causes, each on one escaped line."""

from __future__ import annotations

import json
import unicodedata

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st
from rdflib import Graph, Literal

from ontolint.models import Evidence, Finding, plain_evidence
from ontolint.reporting import (
    _ESCAPED_CATEGORIES,
    FileReport,
    RunReport,
    _escape,
    fingerprint,
    one_line,
    render_report,
    to_json,
    to_sarif_report,
)
from ontolint.rules.support import ntriples_literal

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


# --- text: the evidence lines ---------------------------------------------------------------------------

A = "https://example.test/a"
HEADER = f"[ERROR  ] SHACL001 {A}: message\n    Fix: fix"


def _text(evidence: Evidence | None) -> str:
    return render_report(RunReport((FileReport("a.ttl", "a.ttl", (_finding(evidence=evidence),)),)), "text")


def _lines(evidence: Evidence) -> list[str]:
    """The evidence lines of a one-finding text report."""
    text = _text(evidence)
    prefix = f"Ontology linter: 1 finding(s)\n{HEADER}"
    assert text.startswith(prefix)
    return text.removeprefix(prefix).splitlines()[1:]


def test_a_finding_without_evidence_renders_as_before() -> None:
    assert _text(None) == f"Ontology linter: 1 finding(s)\n{HEADER}"
    assert _text({}) == _text(None)


@pytest.mark.parametrize(
    ("evidence", "expected"),
    [
        ({"focusNode": A, "resultPath": "p", "value": A}, ["    Path: p", f"    Value: {A}"]),  # a self-loop
        ({"focusNode": A, "resultPath": "p", "value": "v"}, ["    Path: p", "    Value: v"]),
        ({"focusNode": A, "value": A}, []),  # a node-level result on its focus
        ({"focusNode": A, "value": "v"}, ["    Value: v"]),
        ({"value": A}, [f"    Value: {A}"]),  # no focus to equal
        ({"focusNode": A, "resultPath": "p"}, ["    Path: p"]),
        ({"focusNode": A}, []),
        ({"resultPath": "(malformed path)"}, ["    Path: (malformed path)"]),
        ({"resultPath": ("p", "q"), "value": ("v",)}, []),  # only text values are printed
    ],
)
def test_path_and_value_lines(evidence: Evidence, expected: list[str]) -> None:
    assert _lines(evidence) == expected


def test_a_detail_line_names_focus_messages_and_shape_with_the_adapters_fallbacks() -> None:
    evidence: Evidence = {
        "focusNode": A,
        "detail": (
            {"focusNode": '"x"', "resultMessage": ("m1", "m2"), "sourceShape": "s", "value": '"x"'},
            {},
            {"resultMessage": ()},
            {"focusNode": ("f",), "resultMessage": "text", "sourceShape": ("s",)},
        ),
    }
    assert _lines(evidence) == [
        '    Detail: "x": m1; m2 [shape: s]',
        "    Detail: (unknown): SHACL constraint violation [shape: (unknown)]",
        "    Detail: (unknown): SHACL constraint violation [shape: (unknown)]",
        "    Detail: (unknown): text [shape: (unknown)]",
    ]
    assert _lines({"focusNode": A, "detail": ("text",)}) == []  # a tuple of text holds no result


def test_nested_lines_indent_two_spaces_per_level_and_escape_their_text() -> None:
    inner: Evidence = {"focusNode": "c", "resultMessage": ("bad\x1b[31m",), "resultPath": "q\u202e", "value": "v"}
    middle: Evidence = {"focusNode": "b", "resultPath": "p", "value": "c", "detail": (inner,)}
    assert _lines({"focusNode": A, "value": "b", "resultPath": "p", "detail": (middle,)}) == [
        "    Path: p",
        "    Value: b",
        "    Detail: b: SHACL constraint violation [shape: (unknown)]",
        "      Path: p",
        "      Value: c",
        "      Detail: c: bad\\u001B[31m [shape: (unknown)]",
        "        Path: q\\u202E",
        "        Value: v",
    ]


def test_evidence_of_any_depth_renders_without_recursion() -> None:
    evidence: Evidence = {"focusNode": "n0"}
    depth = 200
    for level in range(1, depth + 1):
        evidence = {"focusNode": f"n{level}", "detail": (evidence,)}
    lines = _lines(evidence)
    assert len(lines) == depth
    assert lines[-1] == " " * (4 + 2 * (depth - 1)) + "Detail: n0: SHACL constraint violation [shape: (unknown)]"


def test_the_evidence_lines_are_masked_like_the_rest_of_the_finding() -> None:
    assert _lines({"focusNode": A, "value": "https://u:pw@h.test/x"}) == ["    Value: https://****@h.test/x"]


# --- text: escaping --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("char", "escaped"),
    [
        ("\x1b", "\\u001B"),  # ESC (Cc)
        ("\x0b", "\\u000B"),
        ("\x0c", "\\u000C"),
        ("\x7f", "\\u007F"),
        ("\t", "\\u0009"),
        ("\r", "\\u000D"),
        ("\n", "\\u000A"),
        ("\x85", "\\u0085"),
        ("\u2028", "\\u2028"),  # Zl
        ("\u2029", "\\u2029"),  # Zp
        ("\u200b", "\\u200B"),  # Cf: zero width space
        ("\u202e", "\\u202E"),  # Cf: right-to-left override
        ("\ufeff", "\\uFEFF"),  # Cf
        ("\xad", "\\u00AD"),  # Cf: soft hyphen
        ("\xa0", "\\u00A0"),  # Zs: no-break space
        ("\u3000", "\\u3000"),  # Zs
        ("\ue000", "\\uE000"),  # Co
        ("\U000f0000", "\\U000F0000"),  # Co, above the BMP
        ("\ud800", "\\uD800"),  # Cs: a lone surrogate
        ("é", "é"),
        (" ", " "),
    ],
)
def test_one_line_escapes_exactly_the_invisible_and_line_breaking_characters(char: str, escaped: str) -> None:
    text = f"a{char}b"
    line = one_line(text)
    assert line == f"a{escaped}b"
    assert line.splitlines() == [line]
    assert line.encode("utf-8")  # strict: a lone surrogate would raise
    if not 0xD800 <= ord(char) <= 0xDFFF:  # noqa: PLR2004 -- the surrogate block
        term = one_line(ntriples_literal(Literal(text)))
        parsed = Graph().parse(data=f"<https://e.test/s> <https://e.test/p> {term} .", format="nt")
        assert set(parsed.objects()) == {Literal(text)}


def test_escape_writes_four_hex_digits_up_to_ffff_and_eight_above() -> None:
    assert [_escape(c) for c in ("\x00", "\uffff", "\U00010000")] == ["\\u0000", "\\uFFFF", "\\U00010000"]


def test_the_escaped_categories_are_fixed() -> None:
    """Not ``str.isprintable``: unassigned code points (Cn) change with each Unicode version."""
    assert frozenset({"Cc", "Cf", "Cs", "Co", "Zl", "Zp", "Zs"}) == _ESCAPED_CATEGORIES
    assert one_line("a\U000e0080b") == "a\U000e0080b"  # unassigned (Cn): kept


def _shown(char: str) -> bool:
    return char == " " or unicodedata.category(char) not in _ESCAPED_CATEGORIES


@pytest.mark.slow
@given(st.text())
def test_any_text_becomes_one_strict_utf8_line_of_visible_characters(text: str) -> None:
    line = one_line(text)
    assert all(_shown(char) for char in line)
    assert line.splitlines() in ([line], [])
    line.encode("utf-8")  # strict: raises on a lone surrogate


def _pairs_surrogates(text: str) -> bool:
    """Whether ``text`` holds a high surrogate followed by a low one, which an N-Triples reader combines."""
    return any(
        0xD800 <= ord(high) <= 0xDBFF and 0xDC00 <= ord(low) <= 0xDFFF  # noqa: PLR2004 -- surrogate blocks
        for high, low in zip(text, text[1:], strict=False)
    )


@pytest.mark.slow
@given(st.text())
def test_an_escaped_literal_parses_back_to_itself(text: str) -> None:
    assume(not _pairs_surrogates(text))
    term = one_line(ntriples_literal(Literal(text)))
    parsed = Graph().parse(data=f"<https://e.test/s> <https://e.test/p> {term} .", format="nt")
    assert [str(o) for o in parsed.objects()] == [text]
