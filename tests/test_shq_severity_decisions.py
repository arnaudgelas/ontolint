"""The SHQ severity and confidence decisions of issue #63 (``docs/severity-decisions.md``), through the CLI.

* SHQ011 reports ``\\/`` and ``[]a]`` as warnings (pySHACL and Apache Jena accept them) and every other malformed
  pattern as an error, in one run, from one rule (``RuleContext.add(severity=...)``).
* SHQ015 reports an unknown flag letter as an error and flags without a pattern as a warning.
* SHQ013, SHQ008 and SHQ018 findings report confidence ``certain``; SHQ008 still reports a derived integer type as an
  error.
* ``--fail-on`` follows each finding, ``severity_overrides`` replaces both severities of a rule, and a baseline
  written before the change still matches.

The engine behaviour that justifies SHQ011 is a fixture (pySHACL, run here); Jena's was measured by hand and is
recorded in the decision record, because a Java runtime is not part of the test environment.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

import pytest
from pyshacl import validate
from rdflib import Graph

from ontolint.cli import main
from ontolint.rules.specs import SEVERITY

PREFIXES = (
    "@prefix ex: <https://example.test/> .\n"
    "@prefix sh: <http://www.w3.org/ns/shacl#> .\n"
    "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
)
DATA = '@prefix ex: <https://example.test/> .\nex:n ex:p "abc" .\n'
TWO_PATTERNS = PREFIXES + (
    "ex:A a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:pattern 'a\\\\/b' ] .\n"
    "ex:B a sh:NodeShape ; sh:property [ sh:path ex:q ; sh:pattern '[[a]' ] .\n"
)


def _shape(*triples: str) -> str:
    return PREFIXES + "ex:S a sh:NodeShape ; sh:targetNode ex:n ;\n  " + " ;\n  ".join(triples) + " .\n"


def _pattern(turtle_pattern: str) -> str:
    """A shapes graph whose pattern is ``turtle_pattern`` as Turtle reads it: ``\\\\`` is one backslash."""
    return _shape(f'sh:property [ sh:path ex:p ; sh:pattern "{turtle_pattern}" ]')


def _write(tmp_path: Path, shapes: str) -> tuple[Path, Path]:
    data, shapes_file = tmp_path / "data.ttl", tmp_path / "shapes.ttl"
    data.write_text(DATA, encoding="utf-8")
    shapes_file.write_text(shapes, encoding="utf-8")
    return data, shapes_file


def _run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], shapes: str, rule: str, *extra: str, fail_on: str = "never"
) -> tuple[int, list[dict[str, Any]]]:
    data, shapes_file = _write(tmp_path, shapes)
    argv = [str(data), "--shapes", str(shapes_file), "--select", rule, "--format", "json", "--fail-on", fail_on, *extra]
    code = main(argv)
    findings = json.loads(capsys.readouterr().out)["findings"]
    return code, [f for f in findings if f["rule"] == rule]


# --- SHQ011 -------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("turtle_pattern", "severity"),
    [
        (r"a\\/b", "warning"),  # Turtle reads \\ as one backslash: the pattern is a\/b
        (r"[]a]", "warning"),
        (r"[\\/]", "warning"),
        (r"[]a]\\/b", "warning"),
        (r"[[a]", "error"),
        (r"[^]a]", "error"),
        (r"\\y", "error"),
        (r"a(?i)", "error"),
        (r"[a-z", "error"),
        (r"a\\/[[b]", "error"),
        (r"[[b]\\/", "error"),
    ],
)
def test_shq011_severity_follows_the_form(
    turtle_pattern: str, severity: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, findings = _run(tmp_path, capsys, _pattern(turtle_pattern), "SHQ011")
    assert [f["severity"] for f in findings] == [severity]
    assert [f["confidence"] for f in findings] == ["heuristic"]


@pytest.mark.parametrize(
    ("turtle_pattern", "named"),
    [
        (r"a\\/[[b]", "unescaped ["),  # an accepted escape first: the message names the construct that fails
        (r"[[b]\\/", "unescaped ["),
        (r"a\\/b", "\\/"),  # only an accepted escape: the warning names it
    ],
)
def test_shq011_message_names_the_construct_that_decides_the_severity(
    turtle_pattern: str, named: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, findings = _run(tmp_path, capsys, _pattern(turtle_pattern), "SHQ011")
    assert named in findings[0]["message"]


def test_shq011_two_severities_in_one_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, findings = _run(tmp_path, capsys, TWO_PATTERNS, "SHQ011", fail_on="error")
    assert sorted(f["severity"] for f in findings) == ["error", "warning"]
    assert code == 1
    only_warning = TWO_PATTERNS.replace("[[a]", "ab")
    assert _run(tmp_path, capsys, only_warning, "SHQ011", fail_on="error")[0] == 0  # --fail-on error stops failing
    assert _run(tmp_path, capsys, only_warning, "SHQ011", fail_on="warning")[0] == 1


def test_shq011_override_replaces_both_severities(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"severity_overrides": {"SHQ011": "info"}}), encoding="utf-8")
    code, findings = _run(tmp_path, capsys, TWO_PATTERNS, "SHQ011", "--config", str(policy), fail_on="warning")
    assert [f["severity"] for f in findings] == ["info", "info"]
    assert code == 0


def test_shq011_baseline_written_before_the_change_still_matches(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Before this change SHQ011 reported ``\\/`` as an error: its baseline entry has the same identity now."""
    shapes = _pattern(r"a\\/b")
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"severity_overrides": {"SHQ011": "error"}}), encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    data, shapes_file = _write(tmp_path, shapes)
    main(
        [str(data), "--shapes", str(shapes_file), "--select", "SHQ011", "--config", str(policy)]
        + ["--write-baseline", str(baseline), "--fail-on", "never", "--output", str(tmp_path / "ignored")]
    )
    capsys.readouterr()
    code, findings = _run(tmp_path, capsys, shapes, "SHQ011", "--baseline", str(baseline), fail_on="info")
    assert (code, findings) == (0, [])


@pytest.mark.parametrize("turtle_pattern", [r"a\\/b", r"[]a]", r"[[a]"])
def test_pyshacl_accepts_the_forms_the_decision_relies_on(turtle_pattern: str) -> None:
    """pySHACL 0.40.2 runs a shape whose pattern is one of these (Jena 4.10.0 accepts the first two, not ``[[a]``)."""
    shapes = Graph().parse(data=_pattern(turtle_pattern), format="turtle")
    data = Graph().parse(data=DATA, format="turtle")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # Python warns of a possible nested set for [[a]
        conforms, _, _ = validate(data, shacl_graph=shapes)
    assert isinstance(conforms, bool)


# --- SHQ015 -------------------------------------------------------------------------------------------------------


def test_shq015_unknown_letter_is_an_error_and_flags_without_a_pattern_a_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    both = PREFIXES + (
        'ex:A a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:pattern "a" ; sh:flags "z" ] .\n'
        'ex:B a sh:NodeShape ; sh:property [ sh:path ex:q ; sh:flags "i" ] .\n'
    )
    code, findings = _run(tmp_path, capsys, both, "SHQ015", fail_on="error")
    assert sorted(f["severity"] for f in findings) == ["error", "warning"]
    assert code == 1
    only_warning = both.replace('sh:flags "z"', 'sh:flags "i"')
    assert _run(tmp_path, capsys, only_warning, "SHQ015", fail_on="error")[0] == 0
    assert _run(tmp_path, capsys, only_warning, "SHQ015", fail_on="warning")[0] == 1


def test_shq015_is_registered_at_the_gravest_condition() -> None:
    assert SEVERITY["SHQ015"] == "error"
    assert SEVERITY["SHQ011"] == "error"


# --- confidence ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rule", "triples", "severity"),
    [
        ("SHQ013", ["sh:datatype xsd:string", "sh:class ex:C"], "warning"),
        ("SHQ008", ['sh:minCount "1"^^xsd:nonNegativeInteger'], "error"),
        ("SHQ008", ['sh:minLength "-1"^^xsd:integer'], "error"),
        ("SHQ018", ["sh:minInclusive 5", "sh:maxInclusive 3"], "error"),
    ],
)
def test_exact_checks_report_certain(
    rule: str, triples: list[str], severity: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, findings = _run(tmp_path, capsys, _shape(*triples), rule)
    assert findings
    assert {(f["severity"], f["confidence"]) for f in findings} == {(severity, "certain")}
