"""A run whose every selected rule is ignored executes nothing, reports each as skipped and finds nothing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ontolint import main

CLEAN = str(Path(__file__).parent / "fixtures" / "clean.ttl")


def test_selecting_only_ignored_rules_skips_them_all(capsys: pytest.CaptureFixture[str]) -> None:
    code = main([CLEAN, "--select", "ONT", "--ignore", "ONT", "--format", "json", "--fail-on", "error"])

    document = json.loads(capsys.readouterr().out)
    executions = {e["rule"]: (e["status"], e["detail"]) for e in document["files"][0]["executions"]}
    assert code == 0
    assert document["findings"] == []
    assert executions
    assert set(executions.values()) == {("skipped", "ignored by --ignore or profile")}
    assert all(rule.startswith("ONT") for rule in executions)
