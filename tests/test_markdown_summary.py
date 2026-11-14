"""The Markdown summary (:func:`render_markdown`): its layout, its caps and the code span every report text goes in.

The layout tests compare exact strings, so a change to a count, a cap or a sentence shows.  The code-span tests
read the span back with a CommonMark parser (:mod:`markdown_oracle`): what it shows is the text, escaped and
masked, and nothing of it is markup.  The worst-case test is the proof of the size bound: every field at its
longest escape, every list at its cap, every optional part shown.  The properties are in
``test_properties_markdown.py``.
"""

from __future__ import annotations

import pytest
from markdown_oracle import code_spans, unexpected_tokens

from ontolint._version import package_version
from ontolint.models import ExecutionStatus, Finding, RuleExecution
from ontolint.redaction import redact_rendered
from ontolint.reporting import (
    MARKDOWN_BROKEN_SHOWN,
    MARKDOWN_MAX_BYTES,
    MARKDOWN_SHOWN,
    FileReport,
    Origin,
    RunReport,
    markdown_code,
    render_markdown,
    render_report,
    to_sarif_report,
)

HEADING = f"## ontolint {package_version()}"
ERROR = Finding(
    "OWL003", "error", "https://example.test/onto#p", "Property is typed as both object and datatype property.", "x"
)
WARNING = Finding("LEX002", "warning", "https://example.test/onto#B", "Term has no definition.", "x")
INFO = Finding("LEX001", "info", "https://example.test/onto#A", "Term has no label.", "x")
RAN = (
    RuleExecution("LEX001", ExecutionStatus.EXECUTED),
    RuleExecution("OWL003", ExecutionStatus.EXECUTED),
    RuleExecution("SHACL001", ExecutionStatus.SKIPPED, "no shapes graph supplied"),
)
UNSUPPORTED = RuleExecution("SEM001", ExecutionStatus.UNSUPPORTED, "the docker executable was not found")
FAILED = RuleExecution("SHACL001", ExecutionStatus.FAILED, "ValueError: boom")


def _finding(n: int, severity: str = "warning") -> Finding:
    return Finding("LEX001", severity, f"https://example.test/onto#T{n}", "Term has no label.", "x")


def _items(markdown: str) -> list[str]:
    return [line for line in markdown.splitlines() if line.startswith("- ")]


# --- layout -----------------------------------------------------------------------------------------


def test_a_run_without_a_baseline_is_counted_and_listed_most_severe_first() -> None:
    report = RunReport((FileReport("onto.ttl", "onto.ttl", (INFO, ERROR), RAN),))
    assert render_report(report, "markdown", 1) == render_markdown(report, 1)
    assert render_markdown(report, 1) == "\n".join(
        [
            HEADING,
            "",
            "**Failed** (exit 1): a finding reached the `--fail-on` threshold.",
            "",
            "| Severity | Findings |",
            "| --- | ---: |",
            "| error | 1 |",
            "| warning | 0 |",
            "| info | 1 |",
            "| total | 2 |",
            "",
            "Rule execution: 2 executed, 1 skipped, 0 unsupported, 0 failed",
            "",
            "### Findings",
            "",
            "All 2 finding(s), most severe first. "
            "The SARIF report (`--format sarif`) lists every finding, with its source location where known.",
            "",
            "- **error** ` OWL003 ` ` https://example.test/onto#p `: "
            "` Property is typed as both object and datatype property. `",
            "- **info** ` LEX001 ` ` https://example.test/onto#A `: ` Term has no label. `",
        ]
    )


def test_a_baseline_splits_the_counts_into_new_and_baselined_and_notes_stale_entries() -> None:
    old = (_finding(1), _finding(2))
    report = RunReport(
        (FileReport("onto.ttl", "onto.ttl", (INFO, ERROR), RAN),), stale_baseline=("a" * 64,), baselined=(old,)
    )
    assert render_markdown(report, 1) == "\n".join(
        [
            HEADING,
            "",
            "**Failed** (exit 1): a finding reached the `--fail-on` threshold, "
            "or the baseline has stale entries (`--fail-on-stale-baseline`).",
            "",
            "| Severity | New | Baselined |",
            "| --- | ---: | ---: |",
            "| error | 1 | 0 |",
            "| warning | 0 | 2 |",
            "| info | 1 | 0 |",
            "| total | 2 | 2 |",
            "",
            "Rule execution: 2 executed, 1 skipped, 0 unsupported, 0 failed",
            "",
            "### Findings",
            "",
            "All 2 new finding(s), most severe first. "
            "The SARIF report (`--format sarif`) lists every new finding, with its source location where known.",
            "",
            "- **error** ` OWL003 ` ` https://example.test/onto#p `: "
            "` Property is typed as both object and datatype property. `",
            "- **info** ` LEX001 ` ` https://example.test/onto#A `: ` Term has no label. `",
            "",
            "Baseline: 1 fingerprint(s) match no finding of this run (fixed, or not selected); "
            "regenerate the baseline with --write-baseline to drop them.",
        ]
    )


def test_a_baseline_that_accepted_everything_leaves_no_new_findings() -> None:
    report = RunReport((FileReport("onto.ttl", "onto.ttl", ()),), stale_baseline=(), baselined=((ERROR,),))
    markdown = render_markdown(report, 0)
    assert "**Passed** (exit 0)." in markdown
    assert "| error | 0 | 1 |\n| warning | 0 | 0 |\n| info | 0 | 0 |\n| total | 0 | 1 |" in markdown
    assert markdown.endswith("### Findings\n\nNo new findings.")
    assert "--fail-on-stale-baseline" not in render_markdown(report, 1)


def test_the_rule_runs_without_a_verdict_are_the_reason_for_exit_two() -> None:
    report = RunReport((FileReport("onto.ttl", "onto.ttl", (), (UNSUPPORTED, *RAN, FAILED)),))
    assert render_markdown(report, 2) == "\n".join(
        [
            HEADING,
            "",
            "**Failed** (exit 2): 2 rule run(s) did not deliver a verdict.",
            "",
            "| Severity | Findings |",
            "| --- | ---: |",
            "| error | 0 |",
            "| warning | 0 |",
            "| info | 0 |",
            "| total | 0 |",
            "",
            "Rule execution: 2 executed, 1 skipped, 1 unsupported, 1 failed",
            "",
            "### Rules that delivered no verdict",
            "",
            "- ` SEM001 ` unsupported for ` onto.ttl `: ` the docker executable was not found `",
            "- ` SHACL001 ` failed for ` onto.ttl `: ` ValueError: boom `",
            "",
            "### Findings",
            "",
            "No findings.",
        ]
    )


@pytest.mark.parametrize(
    ("count", "lead"),
    [
        (MARKDOWN_SHOWN, f"All {MARKDOWN_SHOWN} finding(s), most severe first."),
        (MARKDOWN_SHOWN + 1, f"The first {MARKDOWN_SHOWN} of {MARKDOWN_SHOWN + 1} finding(s), most severe first."),
    ],
)
def test_the_findings_listed_stop_at_the_cap(count: int, lead: str) -> None:
    report = RunReport((FileReport("onto.ttl", "onto.ttl", tuple(_finding(n) for n in range(count))),))
    markdown = render_markdown(report)
    assert f"\n\n{lead} The SARIF report" in markdown
    assert _items(markdown) == [
        f"- **warning** ` LEX001 ` ` https://example.test/onto#T{n} `: ` Term has no label. `"
        for n in range(MARKDOWN_SHOWN)
    ]


@pytest.mark.parametrize("count", [MARKDOWN_BROKEN_SHOWN, MARKDOWN_BROKEN_SHOWN + 1, MARKDOWN_BROKEN_SHOWN + 2])
def test_the_rule_runs_listed_stop_at_their_cap(count: int) -> None:
    files = tuple(FileReport(f"f{n}.ttl", f"f{n}.ttl", (), (FAILED,)) for n in range(count))
    markdown = render_markdown(RunReport(files), 2)
    assert f"**Failed** (exit 2): {count} rule run(s) did not deliver a verdict." in markdown
    assert _items(markdown) == [
        f"- ` SHACL001 ` failed for ` f{n}.ttl `: ` ValueError: boom `" for n in range(MARKDOWN_BROKEN_SHOWN)
    ]
    hidden = count - MARKDOWN_BROKEN_SHOWN
    assert (f"\n\n{hidden} more not shown.\n\n" in markdown) == (hidden > 0)
    assert ("more not shown" in markdown) == (hidden > 0)


def test_errors_come_first_and_equal_severities_keep_file_and_report_order() -> None:
    first = FileReport("a.ttl", "a.ttl", (INFO, _finding(1), _finding(2)))
    second = FileReport("b.ttl", "b.ttl", (_finding(3), ERROR))
    assert _items(render_markdown(RunReport((first, second)))) == [
        "- **error** ` OWL003 ` ` https://example.test/onto#p ` in ` b.ttl `: "
        "` Property is typed as both object and datatype property. `",
        *(
            f"- **warning** ` LEX001 ` ` https://example.test/onto#T{n} ` in ` {path} `: ` Term has no label. `"
            for n, path in ((1, "a.ttl"), (2, "a.ttl"), (3, "b.ttl"))
        ),
        "- **info** ` LEX001 ` ` https://example.test/onto#A ` in ` a.ttl `: ` Term has no label. `",
    ]


def test_a_file_is_named_only_for_several_files_or_an_imported_module() -> None:
    imported = FileReport("onto.ttl", "onto.ttl", (WARNING, INFO), origins={INFO: Origin("imports/m.ttl", "m.ttl")})
    assert _items(render_markdown(RunReport((imported,)))) == [
        "- **warning** ` LEX002 ` ` https://example.test/onto#B `: ` Term has no definition. `",
        "- **info** ` LEX001 ` ` https://example.test/onto#A ` in ` imports/m.ttl `: ` Term has no label. `",
    ]
    pair = (FileReport("a.ttl", "a.ttl", (WARNING,)), FileReport("b.ttl", "b.ttl", ()))
    assert _items(render_markdown(RunReport(pair))) == [
        "- **warning** ` LEX002 ` ` https://example.test/onto#B ` in ` a.ttl `: ` Term has no definition. `"
    ]


@pytest.mark.parametrize(
    ("status", "verdict"),
    [
        (0, "**Passed** (exit 0)."),
        (1, "**Failed** (exit 1): a finding reached the `--fail-on` threshold."),
        (2, "**Failed** (exit 2)."),
        (3, "Exit status 3."),
        (141, "Exit status 141."),
    ],
)
def test_the_verdict_names_the_exit_status(status: int, verdict: str) -> None:
    markdown = render_markdown(RunReport(()), status)
    assert markdown.split("\n\n")[:2] == [HEADING, verdict]


def test_an_empty_run_without_a_status_has_no_verdict_and_zero_counts() -> None:
    assert render_markdown(RunReport(())) == "\n".join(
        [
            HEADING,
            "",
            "| Severity | Findings |",
            "| --- | ---: |",
            "| error | 0 |",
            "| warning | 0 |",
            "| info | 0 |",
            "| total | 0 |",
            "",
            "Rule execution: 0 executed, 0 skipped, 0 unsupported, 0 failed",
            "",
            "### Findings",
            "",
            "No findings.",
        ]
    )


def test_an_unknown_severity_is_refused_as_in_sarif_and_never_rendered() -> None:
    report = RunReport((FileReport("a.ttl", "a.ttl", (Finding("X001", "[x](y)", "f", "m", "s"),)),))
    with pytest.raises(KeyError, match=r"\[x\]\(y\)"):
        render_markdown(report)
    with pytest.raises(KeyError):
        to_sarif_report(report)


def test_a_shacl001_finding_shows_its_message_in_a_code_span_and_never_its_evidence() -> None:
    hostile = "[x](https://evil.test) <b>`|`</b>\n# h"
    evidence = {
        "focusNode": "https://example.test/a",
        "resultPath": "https://example.test/p",
        "value": "[v](https://evil.test)\n| a |",
        "resultMessage": (hostile,),
        "detail": ({"resultMessage": (hostile,), "value": "`<i>`"},),
    }
    finding = Finding("SHACL001", "error", "https://example.test/a", hostile, "x", evidence=evidence)
    markdown = render_markdown(RunReport((FileReport("a.ttl", "a.ttl", (finding,)),)))
    assert unexpected_tokens(markdown) == []
    item = _items(markdown)
    assert len(item) == 1
    assert "`<i>`" not in markdown
    assert "Path:" not in markdown
    assert hostile not in markdown


# --- the code span ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "span", "shown"),
    [
        ("", "` `", " "),
        (" ", "` `", " "),
        ("  ", "`  `", "  "),
        ("a", "` a `", "a"),
        (" a", "`  a `", " a"),
        ("a ", "` a  `", "a "),
        # Spaces other than U+0020 are text: the padding is stripped (markdown-it-py keeps it, see markdown_oracle).
        ("\xa0", "` \xa0 `", "\xa0"),
        (" 　 ", "`  　  `", " 　 "),
        ("`", "`` ` ``", "`"),
        ("a`a", "`` a`a ``", "a`a"),
        ("a``b`c", "``` a``b`c ```", "a``b`c"),
        ("``", "``` `` ```", "``"),
        ("a\\", "` a\\ `", "a\\"),
        ("a\n\n# h", "` a\\n\\n# h `", "a\\n\\n# h"),
        ("\t\r\x0b\x7f\xad", "` \\t\\r\\x0b\\x7f\\xad `", "\\t\\r\\x0b\\x7f\\xad"),
        (
            "\u202ex\u2028\u2029\u200b\ufeff",
            "` \\u202ex\\u2028\\u2029\\u200b\\ufeff `",
            "\\u202ex\\u2028\\u2029\\u200b\\ufeff",
        ),
        ("\U000e0001\U000e0041", "` \\U000e0001\\U000e0041 `", "\\U000e0001\\U000e0041"),
        # Variation selectors and the other default-ignorable characters outside Cf, last of each range included.
        (
            "\u2764\ufe0f\u034f\u1160\u17b5\u180f\u3164\uffa0\U000e01ef",
            "` \u2764\\ufe0f\\u034f\\u1160\\u17b5\\u180f\\u3164\\uffa0\\U000e01ef `",
            "\u2764\\ufe0f\\u034f\\u1160\\u17b5\\u180f\\u3164\\uffa0\\U000e01ef",
        ),
        (
            "\ufe00\U000e0100\u115f\u17b4\u180b",
            "` \\ufe00\\U000e0100\\u115f\\u17b4\\u180b `",
            "\\ufe00\\U000e0100\\u115f\\u17b4\\u180b",
        ),
        # The unassigned default-ignorable code points (Cn), first and last of each range: drawn as nothing too.
        (
            "\u2065\ufff0\ufff8\U000e0000\U000e0002\U000e0080\U000e01f0\U000e0fff",
            "` \\u2065\\ufff0\\ufff8\\U000e0000\\U000e0002\\U000e0080\\U000e01f0\\U000e0fff `",
            "\\u2065\\ufff0\\ufff8\\U000e0000\\U000e0002\\U000e0080\\U000e01f0\\U000e0fff",
        ),
        ("\udfff", "` \\udfff `", "\\udfff"),
        ("@octocat #1 :smile: [x](https://evil.test) <img>", None, "@octocat #1 :smile: [x](https://evil.test) <img>"),
    ],
)
def test_a_code_span_shows_the_text_escaped_and_nothing_else(text: str, span: str | None, shown: str) -> None:
    code = markdown_code(text, 300)
    if span is not None:
        assert code == span
    assert code_spans(code) == [shown]
    assert unexpected_tokens(code) == []
    code.encode("utf-8")


DEFAULT_IGNORABLE = (
    (0x00AD, 0x00AD),
    (0x034F, 0x034F),
    (0x061C, 0x061C),
    (0x115F, 0x1160),
    (0x17B4, 0x17B5),
    (0x180B, 0x180F),
    (0x200B, 0x200F),
    (0x202A, 0x202E),
    (0x2060, 0x206F),
    (0x3164, 0x3164),
    (0xFE00, 0xFE0F),
    (0xFEFF, 0xFEFF),
    (0xFFA0, 0xFFA0),
    (0xFFF0, 0xFFF8),
    (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A),
    (0xE0000, 0xE0FFF),
)
"""Unicode's ``Default_Ignorable_Code_Point`` (``DerivedCoreProperties.txt``, Unicode 15.1 and 16.0), assigned
and unassigned: what a renderer draws as nothing."""


def test_a_code_span_shows_every_default_ignorable_code_point_as_an_escape() -> None:
    """A run of any of them could carry a hidden text, whatever its category in Python's Unicode database."""
    hidden = [chr(code) for first, last in DEFAULT_IGNORABLE for code in range(first, last + 1)]
    shown = [c for c in hidden if c in markdown_code(c, 300)]
    assert shown == []


def test_a_code_span_is_cut_to_its_limit_after_masking() -> None:
    assert markdown_code("x" * 300, 300) == "` " + "x" * 300 + " `"
    assert markdown_code("x" * 301, 300) == "` " + "x" * 300 + "... `"
    # Cut first, the userinfo would lose its "@" and its first part would be shown.
    assert markdown_code("https://alice:" + "s" * 80 + "@h/x", 20) == "` https://****@h/x `"


def test_a_userinfo_is_masked_before_escaping_hides_its_scheme_or_its_end() -> None:
    # Escaped first, "\n" would stop the rendered-report mask before the "@": "alice:pw" and "Zq" would be shown.
    assert markdown_code("https://alice:pw\nZq@h", 200) == "` https://****@h `"
    # The escape makes "x00" a scheme, which the CLI's own mask would act on: the span is masked again.
    code = markdown_code("a\x00://u@h", 200)
    assert code == "` a\\x00://****@h `"
    assert redact_rendered(code) == code


# --- the size bound ---------------------------------------------------------------------------------


def _widest(text: str) -> RunReport:
    """Every list at its cap plus one, every field ``text`` (longer than any limit), every optional part shown."""
    finding = Finding(text, "warning", text, text, text)
    findings = tuple(Finding(f"{text}{n}", "warning", text, text, text) for n in range(MARKDOWN_SHOWN + 1))
    files = tuple(
        FileReport(
            text,
            text,
            findings,
            (RuleExecution(text, ExecutionStatus.UNSUPPORTED, text),) * (MARKDOWN_BROKEN_SHOWN + 1),
            origins=dict.fromkeys(findings, Origin(text, text)),
        )
        for _ in range(2)
    )
    return RunReport(files, stale_baseline=("a" * 64,) * 1000, baselined=((finding,) * 1000,) * 2)


def test_the_widest_summary_fits_the_size_bound() -> None:
    """Every field is the character with the longest escape (10 bytes), so the summary is the largest there is."""
    tag = "\U000e0001"
    markdown = render_markdown(_widest(tag * 1000), 1)
    size = len(markdown.encode("utf-8"))
    assert size <= MARKDOWN_MAX_BYTES
    # Every field is cut at its limit and every capped list is full: this is the worst case, not a smaller one.
    per_finding = 40 + 200 + 200 + 300  # rule, focus, path, message
    per_run = 40 + 200 + 300  # rule, path, detail
    assert markdown.count("\\U000e0001") == MARKDOWN_SHOWN * per_finding + MARKDOWN_BROKEN_SHOWN * per_run
    assert unexpected_tokens(markdown) == []


def test_the_widest_summary_of_backticks_fits_the_size_bound() -> None:
    markdown = render_markdown(_widest("`" * 1000), 1)
    assert len(markdown.encode("utf-8")) <= MARKDOWN_MAX_BYTES
    assert set(code_spans(markdown)) == {
        "--fail-on",
        "--fail-on-stale-baseline",
        "--format sarif",
        *("`" * limit + "..." for limit in (40, 200, 300)),
    }
