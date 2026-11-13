"""Properties of the Markdown summary: no text of a report becomes markup, and the summary is bounded and stable.

Every text of a hostile report (:func:`hostile_run_reports`: links, images, HTML, mentions, backtick runs, line
breaks, bidi and tag characters, surrogates, userinfos) is compared with a benign twin, the same report with each
distinct text replaced by its own ``x<n>``.  A CommonMark parser (:mod:`markdown_oracle`) must read the two
summaries as the same token stream once code-span contents are set aside, so no text changed the structure; each
code span must hold its field exactly, escaped and masked; and the summary must be what the CLI writes.
"""

from __future__ import annotations

import copy
from dataclasses import replace

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis_strategies import budget, hostile_run_reports
from markdown_oracle import code_spans, shape, unexpected_tokens, vocabulary_breaches

from ontolint.models import Finding, RuleExecution
from ontolint.redaction import clip, redact_rendered
from ontolint.reporting import (
    _QUOTE_LIMITS,
    MARKDOWN_BROKEN_SHOWN,
    MARKDOWN_MAX_BYTES,
    MARKDOWN_SHOWN,
    SEVERITY_ORDER,
    FileReport,
    Origin,
    RunReport,
    _visible,
    render_markdown,
)

pytestmark = pytest.mark.slow

statuses = st.sampled_from((None, 0, 1, 2, 3))


def _twin(report: RunReport) -> RunReport:
    """``report`` with each distinct text replaced by its own ``x<n>``: the same shape, nothing to escape.

    The finding texts are mapped as the findings hold them, masked, so two findings are equal exactly when their
    twins are, and an origin keyed by one finding keys its twin."""
    names: dict[str, str] = {}

    def name(text: str) -> str:
        return names.setdefault(text, f"x{len(names)}")

    def finding(f: Finding) -> Finding:
        return replace(
            f, rule=name(f.rule), focus=name(f.focus), message=name(f.message), suggestion=name(f.suggestion)
        )

    files = tuple(
        FileReport(
            name(r.path),
            name(r.uri),
            tuple(map(finding, r.findings)),
            tuple(RuleExecution(name(x.rule_id), x.status, name(x.detail)) for x in r.executions),
            origins={finding(f): Origin(name(o.path), name(o.uri)) for f, o in r.origins.items()},
        )
        for r in report.files
    )
    baselined = None if report.baselined is None else tuple(tuple(map(finding, b)) for b in report.baselined)
    return replace(report, files=files, baselined=baselined)


def _quoted(text: str, kind: str) -> str:
    """What the code span of a field of kind ``kind`` holds, as a CommonMark parser reads it."""
    return redact_rendered(_visible(clip(text, _QUOTE_LIMITS[kind], "..."))) or " "


def _expected_spans(report: RunReport, status: int | None) -> list[str]:
    """Every code span of the summary, in order: the flags the verdict names, then each quoted field."""
    spans = []
    if status == 1:
        spans += ["--fail-on", *(["--fail-on-stale-baseline"] if report.stale_baseline else [])]
    for path, x in report.broken[:MARKDOWN_BROKEN_SHOWN]:
        spans += [_quoted(x.rule_id, "rule"), _quoted(path, "path"), _quoted(x.detail, "detail")]
    entries = [
        (r, f) for severity in SEVERITY_ORDER for r in report.files for f in r.findings if f.severity == severity
    ]
    if entries:
        spans.append("--format sarif")
    for r, f in entries[:MARKDOWN_SHOWN]:
        where = [_quoted(r.path_of(f), "path")] if len(report.files) > 1 or f in r.origins else []
        spans += [_quoted(f.rule, "rule"), _quoted(f.focus, "focus"), *where, _quoted(f.message, "message")]
    return spans


@budget(1)
@given(hostile_run_reports(), statuses)
def test_no_text_of_a_report_becomes_markup(report: RunReport, status: int | None) -> None:
    """INVARIANT: a hostile report's summary has its benign twin's structure, holds no link, image, HTML or line
    break, quotes every field exactly, has only the renderer's own text outside code spans, and is what the CLI
    writes after masking it again."""
    markdown = render_markdown(report, status)
    written = redact_rendered(markdown)

    assert written == markdown
    assert shape(written) == shape(render_markdown(_twin(report), status))
    assert unexpected_tokens(written) == []
    assert code_spans(written) == _expected_spans(report, status)
    assert vocabulary_breaches(written) == []


@budget(1)
@given(hostile_run_reports(), statuses)
def test_a_summary_is_bounded_and_encodes_as_utf8(report: RunReport, status: int | None) -> None:
    """INVARIANT: any summary, even of surrogates and tag characters, encodes as UTF-8 within the size bound."""
    assert len(render_markdown(report, status).encode("utf-8")) <= MARKDOWN_MAX_BYTES


@budget(0.5)
@given(hostile_run_reports(), statuses)
def test_a_summary_depends_on_the_report_only(report: RunReport, status: int | None) -> None:
    """INVARIANT: equal reports give byte-identical summaries, whatever object holds them."""
    assert render_markdown(report, status) == render_markdown(copy.deepcopy(report), status)
    assert render_markdown(report, status) == render_markdown(report, status)
