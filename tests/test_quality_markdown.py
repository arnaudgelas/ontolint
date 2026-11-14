"""The quality comparison in the Markdown summary: its layout, the code spans that hold what a snapshot file says,
and the size bound (``test_markdown_summary.py`` proves the rest of the summary)."""

from __future__ import annotations

from dataclasses import replace

from markdown_oracle import code_spans, unexpected_tokens
from test_markdown_summary import _widest

from ontolint.models import Measurement, MeasurementKind
from ontolint.quality import Comparison, Coverage, Entry, Result, Shaping, Snapshot, compare
from ontolint.reporting import (
    MARKDOWN_MAX_BYTES,
    MARKDOWN_QUALITY_SHOWN,
    FileReport,
    RunReport,
    render_comparison,
    render_markdown,
)

RATIO, COUNT, HISTOGRAM = MeasurementKind.RATIO, MeasurementKind.COUNT, MeasurementKind.HISTOGRAM
Q = "https://example.test/q#"


def pair() -> Comparison:
    def entry(numerator: tuple[str, ...], denominator: tuple[str, ...], version: int = 1) -> Entry:
        m = Measurement(
            "class_definition_coverage",
            version,
            RATIO,
            "owned_classes",
            numerator=len(numerator),
            denominator=len(denominator),
        )
        return Entry(m, Coverage("higher", numerator, denominator))

    def terms(names: str) -> tuple[str, ...]:
        return tuple(Q + n for n in names)

    count = Measurement("unresolved_imports", 1, COUNT, "graph", value=1)
    depth = Measurement("class_depth", 1, HISTOGRAM, "acyclic_owned_classes", buckets=((1, 2),))
    old = Snapshot(Shaping(), (entry(terms("ABC"), terms("ABCDE")), Entry(count), Entry(depth)))
    new = Snapshot(
        Shaping(),
        (
            entry(terms("AD"), terms("ABDFGH")),
            Entry(replace(count, value=0)),
            Entry(Measurement("class_depth", 2, HISTOGRAM, "acyclic_owned_classes", buckets=((1, 2),))),
        ),
    )
    return compare(old, new)


def test_the_comparison_lists_a_line_per_measurement_with_its_split() -> None:
    markdown = render_comparison(pair(), "markdown")
    assert markdown.split("\n\n")[:3] == [
        markdown.split("\n\n")[0],  # the heading carries the version
        "### Quality comparison",
        "- ` class_definition_coverage `: 3/5 -> 2/6, delta -0.2667; regressed 1, diluted 3, removed 2, improved 1, "
        "new and fine 0\n"
        "- ` unresolved_imports `: 1 -> 0, delta -1\n"
        "- ` class_depth `: not comparable: ` definition version 1 -> 2 `",
    ]
    assert markdown.endswith("(the COMP rules will add it).")


def test_a_run_summary_names_the_baseline_and_keeps_its_other_sections() -> None:
    report = RunReport((FileReport("a.ttl", "file:///a.ttl", ()),), quality=pair())
    markdown = render_markdown(report, 0)
    assert "### Quality against the baseline\n\n- ` class_definition_coverage `: 3/5" in markdown
    assert markdown.index("### Findings") < markdown.index("### Quality against the baseline")
    assert render_markdown(replace(report, quality=None), 0) == render_markdown(
        RunReport((FileReport("a.ttl", "file:///a.ttl", ()),)), 0
    )


def test_what_a_snapshot_file_says_is_shown_in_code_spans_and_never_as_markup() -> None:
    hostile = "[click](https://evil.test) <img src=x> @everyone | `tick`"
    comparison = Comparison((Result(hostile, (hostile, "population a -> b")),), notes=())
    markdown = render_comparison(comparison, "markdown")
    assert unexpected_tokens(markdown) == []
    assert hostile in code_spans(markdown)[0] or "[click]" in "".join(code_spans(markdown))


def test_a_userinfo_in_a_snapshot_is_masked_in_the_summary() -> None:
    comparison = Comparison((Result("m", ("population https://alice:secret@h/x -> y",)),), notes=())
    assert "secret" not in render_comparison(comparison, "markdown")


def test_only_the_first_measurements_are_listed_and_the_rest_counted() -> None:
    results = tuple(Result(f"m{n}", ("measured in the new snapshot only",)) for n in range(MARKDOWN_QUALITY_SHOWN + 2))
    markdown = render_comparison(Comparison(results, notes=()), "markdown")
    assert f"` m{MARKDOWN_QUALITY_SHOWN - 1} `" in markdown and f"` m{MARKDOWN_QUALITY_SHOWN} `" not in markdown
    assert markdown.endswith("2 more not shown.")


def test_the_widest_summary_with_a_quality_comparison_fits_the_size_bound() -> None:
    tag = "\U000e0001"
    widest = Comparison(
        tuple(
            Result(tag * 1000, (tag * 1000,) * 5)  # every id and reason at its longest escape
            for _ in range(MARKDOWN_QUALITY_SHOWN + 1)
        )
    )
    markdown = render_markdown(replace(_widest(tag * 1000), quality=widest), 1)
    assert len(markdown.encode("utf-8")) <= MARKDOWN_MAX_BYTES
    assert markdown.count("\\U000e0001") >= MARKDOWN_QUALITY_SHOWN * (40 + 80)
    assert unexpected_tokens(markdown) == []
