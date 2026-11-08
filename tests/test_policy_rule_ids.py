"""OPS009: a policy file cannot name a rule that does not exist (a typo there would be silent)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ontolint.cli import main

TURTLE = "<https://example.test/A> a <http://www.w3.org/2002/07/owl#Class> .\n"
TOOL_FAILURE = 2


def _lint(tmp_path: Path, policy: dict[str, object], capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    source = tmp_path / "a.ttl"
    source.write_text(TURTLE, encoding="utf-8")
    config = tmp_path / "policy.json"
    config.write_text(json.dumps({"policy_version": 1, **policy}), encoding="utf-8")
    code = main([str(source), "--config", str(config), "--fail-on", "never"])
    return code, capsys.readouterr().err


@pytest.mark.parametrize(
    ("policy", "named"),
    [
        ({"ignored_rules": ["NOPE999"]}, "ignored_rules: NOPE999"),
        ({"severity_overrides": {"ALSO999": "error"}}, "severity_overrides: ALSO999"),
        ({"ignored_rules": ["lex001"]}, "ignored_rules: lex001"),  # matched exactly, as the engine does
        ({"ignored_rules": ["LEX"]}, "ignored_rules: LEX"),  # a family is a selector, not a rule
    ],
)
def test_an_unknown_rule_id_in_the_policy_is_a_configuration_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], policy: dict[str, object], named: str
) -> None:
    code, err = _lint(tmp_path, policy, capsys)
    assert code == TOOL_FAILURE
    assert err.startswith("GOV020: policy file rejected: unknown rule identifier(s) in ")
    assert named in err
    assert "use --list-rules" in err


def test_both_policy_keys_are_reported_together(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _code, err = _lint(tmp_path, {"ignored_rules": ["B999", "A999"], "severity_overrides": {"C999": "info"}}, capsys)
    assert "ignored_rules: A999, B999; severity_overrides: C999" in err


def test_a_proposed_rule_is_rejected_with_a_hint(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, err = _lint(tmp_path, {"ignored_rules": ["COMP001"]}, capsys)
    assert code == TOOL_FAILURE
    assert "COMP001 exist in the catalogue as proposed rules and are not implemented" in err


def test_known_rule_ids_are_accepted(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, err = _lint(tmp_path, {"ignored_rules": ["LEX001"], "severity_overrides": {"ONT001": "info"}}, capsys)
    assert code == 0
    assert "GOV020" not in err
