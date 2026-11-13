"""``--format markdown`` on the command line: its exit codes, its counts against a baseline, its stability, and
hostile labels from real ontologies.

Each hostile vector is an ontology a user could publish: a SKOS label that two rules quote through ``repr``, a
SHACL message that SHACL001 quotes as it stands (line breaks included), and a term IRI spelled with Turtle escapes.
The summary must show each one, in a code span, in its visible form, and hold no markup of its own.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis_strategies import budget, literals, markdown_texts
from markdown_oracle import code_spans, unexpected_tokens, vocabulary_breaches
from metamorphic_support import workdir

from ontolint import main
from ontolint._version import package_version
from ontolint.redaction import redact_rendered
from ontolint.reporting import MARKDOWN_MAX_BYTES, MARKDOWN_SHOWN

FIXTURES = Path(__file__).parent / "fixtures"
KITCHEN, CLEAN = str(FIXTURES / "kitchen_sink.ttl"), str(FIXTURES / "clean.ttl")
SHAPES = str(FIXTURES / "kitchen_shapes.ttl")
COUNT_ROW = re.compile(r"^\| (error|warning|info) \| (\d+) \|(?: (\d+) \|)?$", re.MULTILINE)
Run = Callable[..., tuple[int, str, str]]


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Run:
    monkeypatch.chdir(tmp_path)

    def _run(*argv: str) -> tuple[int, str, str]:
        code = main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return _run


def _counts(markdown: str, column: int = 2) -> dict[str, int]:
    return {match.group(1): int(match.group(column)) for match in COUNT_ROW.finditer(markdown)}


def _findings(markdown: str) -> list[str]:
    return [line for line in markdown.splitlines() if line.startswith("- **")]


# --- exit codes and outputs -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("argv", "code", "verdict"),
    [
        ((CLEAN,), 0, "**Passed** (exit 0)."),
        ((KITCHEN,), 1, "**Failed** (exit 1): a finding reached the `--fail-on` threshold."),
        ((CLEAN, "--owl-profile", "EL"), 2, "**Failed** (exit 2): 1 rule run(s) did not deliver a verdict."),
    ],
    ids=["clean", "findings", "no-docker"],
)
def test_a_summary_exits_as_the_text_report_does_and_says_why(
    run: Run, monkeypatch: pytest.MonkeyPatch, argv: tuple[str, ...], code: int, verdict: str
) -> None:
    monkeypatch.setattr("ontolint.engine.shutil.which", lambda _: None)  # no docker, whatever the host has
    markdown_code, out, err = run(*argv, "--format", "markdown")
    text_code, _text, text_err = run(*argv)
    assert markdown_code == text_code == code
    assert err == text_err
    assert out.startswith(f"## ontolint {package_version()}\n\n{verdict}\n\n")
    assert out.endswith("\n") and not out.endswith("\n\n")
    if code == 2:  # noqa: PLR2004 -- the tool failure: SEM001 is named in the summary and on stderr
        assert "\n\n### Rules that delivered no verdict\n\n- ` SEM001 ` unsupported for ` " in out
        assert "TOOL001: rule SEM001 unsupported for " in err


def test_output_writes_the_summary_stdout_shows(run: Run, tmp_path: Path) -> None:
    code, out, _err = run(KITCHEN, "--format", "markdown")
    assert run(KITCHEN, "--format", "markdown", "--output", "summary.md") == (code, "", "")
    assert (tmp_path / "summary.md").read_text(encoding="utf-8") == out
    assert len(out.encode("utf-8")) <= MARKDOWN_MAX_BYTES


@pytest.mark.parametrize("argv", [("--list-rules",), ("--explain", "LEX001")], ids=["list-rules", "explain"])
def test_the_rule_commands_print_text_for_markdown(run: Run, argv: tuple[str, ...]) -> None:
    text = run(*argv)
    assert run(*argv, "--format", "markdown") == text
    as_json = run(*argv, "--format", "json")
    assert as_json != text
    # SARIF has no rule-list form: the rule commands print JSON for it, as they did before `markdown`.
    assert run(*argv, "--format", "sarif") == as_json
    assert text[0] == 0


def test_the_baselined_findings_and_the_new_ones_add_up_to_the_run(run: Run) -> None:
    """RELATION: with a baseline of the LEX findings, New + Baselined per severity is the run without a baseline,
    and Baselined is the LEX run's counts."""
    _code, plain, _err = run(KITCHEN, "--format", "markdown")
    _code, lex, _err = run(KITCHEN, "--select", "LEX", "--format", "markdown", "--write-baseline", "lex.json")
    _code, split, _err = run(KITCHEN, "--format", "markdown", "--baseline", "lex.json")
    new, baselined = _counts(split), _counts(split, 3)
    assert "| Severity | New | Baselined |" in split
    assert baselined == _counts(lex) != {"error": 0, "warning": 0, "info": 0}
    assert {s: new[s] + baselined[s] for s in new} == _counts(plain)
    assert "new finding(s), most severe first." in split
    assert "Baseline:" not in split  # every LEX entry matched a finding of the run


# --- stability ---------------------------------------------------------------------------------------


@pytest.mark.slow
def test_a_summary_is_the_same_under_every_hash_seed(tmp_path: Path) -> None:
    command = [sys.executable, "-m", "ontolint", KITCHEN, "--shapes", SHAPES, "--format", "markdown"]
    outputs = {
        subprocess.run(  # noqa: S603 -- the interpreter running the tests, with fixed arguments
            command, capture_output=True, check=False, cwd=tmp_path, env={**os.environ, "PYTHONHASHSEED": seed}
        ).stdout
        for seed in ("0", "1", "4242")
    }
    assert len(outputs) == 1
    (summary,) = outputs
    assert summary.startswith(b"## ontolint ")
    assert len(_findings(summary.decode("utf-8"))) == MARKDOWN_SHOWN


# --- hostile labels ----------------------------------------------------------------------------------

LABEL = "[x](https://evil.test) ![i](https://evil.test/i.png) <img src=x onerror=alert(1)> @octocat #1 :smile: ``t``"
HOSTILE_TTL = f"""@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
<https://example.test/onto> a owl:Ontology .
<https://example.test/onto#c1> a skos:Concept ; skos:prefLabel "{LABEL}"@en ; skos:altLabel "{LABEL}"@en .
<https://example.test/onto#a\\u0060b\\u003Cimg\\u000Ad> a owl:Class .
"""
MESSAGE = '"""needs a definition\n\n# h\n[x](javascript:alert(1)) @octocat <script>alert(1)</script>"""'
HOSTILE_SHAPES = f"""@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
<https://example.test/shapes#S> a sh:NodeShape ; sh:targetClass skos:Concept ;
    sh:property [ sh:path skos:definition ; sh:minCount 1 ; sh:message {MESSAGE} ] .
"""


def _assert_inert(markdown: str) -> list[str]:
    """``markdown`` holds no markup of its own and is what the CLI's mask leaves; return its code spans."""
    assert unexpected_tokens(markdown) == []
    assert vocabulary_breaches(markdown) == []
    assert redact_rendered(markdown) == markdown
    return code_spans(markdown)


def test_hostile_labels_messages_and_iris_are_shown_literally(run: Run, tmp_path: Path) -> None:
    (tmp_path / "hostile.ttl").write_text(HOSTILE_TTL, encoding="utf-8")
    (tmp_path / "shapes.ttl").write_text(HOSTILE_SHAPES, encoding="utf-8")
    code, out, _err = run("hostile.ttl", "--shapes", "shapes.ttl", "--format", "markdown")
    assert code == 1
    spans = _assert_inert(out.removesuffix("\n"))
    # SKOS002 cuts the label at 60 characters in its repr; LEX018 quotes it whole, backticks included.
    assert f"Literal {LABEL[:60]!r} (en) appears in skos:prefLabel and skos:altLabel." in spans
    assert f"Label '{LABEL}' contains markup or a character entity." in spans
    # SHACL001 quotes the message with its line breaks, which the span shows escaped.
    assert any(
        span.startswith("needs a definition\\n\\n# h\\n[x](javascript:alert(1)) @octocat <script>alert(1)</script>")
        for span in spans
    )
    # The IRI's backtick, "<" and line feed, from Turtle escapes.
    assert "https://example.test/onto#a`b<img\\nd" in spans


def _turtle_string(text: str) -> str:
    """``text`` as a Turtle string in which every character but a printable ASCII one is a ``\\U`` escape, so a
    control character, a tag character or a lone surrogate reaches rdflib as it stands."""
    return '"' + "".join(c if " " <= c <= "~" and c not in '"\\' else f"\\U{ord(c):08X}" for c in text) + '"'


@pytest.mark.slow
@budget(0.1)
@given(st.one_of(markdown_texts(), literals().map(str)))
def test_any_label_two_rules_quote_is_shown_literally(label: str) -> None:
    """INVARIANT: whatever a SKOS label holds, the summary of a run that quotes it (SKOS002, LEX015, LEX018) holds
    no markup of its own and every finding it lists."""
    string = _turtle_string(label)
    turtle = (
        "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .\n"
        f"<https://example.test/onto#c1> a skos:Concept ; skos:prefLabel {string} ; skos:altLabel {string} .\n"
    )
    with workdir() as root:
        (root / "label.ttl").write_text(turtle, encoding="ascii")
        code = main(["label.ttl", "--format", "markdown", "--output", "summary.md", "--select", "SKOS,LEX"])
        summary = (root / "summary.md").read_text(encoding="utf-8").removesuffix("\n")
    assert code == 1
    _assert_inert(summary)
    assert "` SKOS002 ` ` https://example.test/onto#c1 `: `" in summary
    assert len(_findings(summary)) == sum(_counts(summary).values())
