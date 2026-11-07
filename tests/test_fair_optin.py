"""The FAIR family is opt-in: it never runs unless selected explicitly or by the ``fair`` profile."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from ontolint import engine, main
from ontolint.models import RuleSpec
from ontolint.profiles import OPT_IN_FAMILIES, PROFILES, is_opt_in
from ontolint.rules import fair_offline, specs
from ontolint.rules.builtin import RULE_SPECS
from ontolint.rules.registry import RuleRegistry
from ontolint.selection import default_rules, resolve_selection

FIXTURES = Path(__file__).parent / "fixtures"
KITCHEN = str(FIXTURES / "kitchen_sink.ttl")
FAIR_IDS = {s.rule_id for s in fair_offline.SPECS}
ALL_SPECS: tuple[RuleSpec, ...] = tuple({s.rule_id: s for s in (*RULE_SPECS, *fair_offline.SPECS)}.values())
Run = Callable[..., tuple[int, str, str]]


@pytest.fixture
def registry() -> RuleRegistry:
    """The built-in rules plus FAIR, whether or not the FAIR module is registered yet."""
    return RuleRegistry(ALL_SPECS)


@pytest.fixture
def run(registry: RuleRegistry, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> Run:
    monkeypatch.setattr("ontolint.cli.default_registry", lambda: registry)
    monkeypatch.setitem(engine.FAMILY_RUNNERS, "fair_offline", fair_offline.run)
    for spec in fair_offline.SPECS:
        monkeypatch.setitem(specs.SEVERITY, spec.rule_id, spec.severity.value)
        monkeypatch.setitem(specs.FIXES, spec.rule_id, spec.suggestion)

    def _run(*argv: str) -> tuple[int, str, str]:
        monkeypatch.chdir(FIXTURES)
        code = main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return _run


def _ids(rules: tuple[RuleSpec, ...]) -> set[str]:
    return {s.rule_id for s in rules}


def _default_ids(registry: RuleRegistry) -> set[str]:
    return {s.rule_id for s in registry.all() if not is_opt_in(s.family) and s.backend.value != "cli"}


def test_opt_in_data() -> None:
    assert "FAIR" in OPT_IN_FAMILIES and is_opt_in("fair") and is_opt_in("FAIR")
    assert {s.family for s in fair_offline.SPECS} == {"FAIR"}
    assert sorted(FAIR_IDS) == ["FAIR004", "FAIR006", "FAIR007", "FAIR011", "FAIR017"]
    assert all(s.module == "fair_offline" for s in fair_offline.SPECS)
    assert all(s.severity.value in {"info", "warning"} for s in fair_offline.SPECS)


def test_default_rules_drop_fair(registry: RuleRegistry) -> None:
    assert not _ids(default_rules(registry.all())) & FAIR_IDS


@pytest.mark.parametrize("name", [None, "recommended", "ci", "strict", "obo"])
def test_fair_is_not_part_of_the_other_profiles(registry: RuleRegistry, name: str | None) -> None:
    selection = resolve_selection(registry, PROFILES[name] if name else None, (), ())
    assert not _ids(selection.run + selection.ignored) & FAIR_IDS


def test_explicit_selectors_opt_in(registry: RuleRegistry) -> None:
    assert _ids(resolve_selection(registry, None, ("FAIR",), ()).run) == FAIR_IDS
    assert _ids(resolve_selection(registry, None, ("fair007",), ()).run) == {"FAIR007"}
    mixed = _ids(resolve_selection(registry, PROFILES["strict"], ("FAIR004", "LEX"), ()).run)
    assert "FAIR004" in mixed and "FAIR006" not in mixed


def test_fair_profile_is_the_default_selection_plus_fair(registry: RuleRegistry) -> None:
    profile = PROFILES["fair"]
    assert profile.select == () and profile.opt_in == ("FAIR",) and profile.fail_on == "warning"
    assert profile.severity_overrides == () and profile.ignore == ()
    assert _ids(resolve_selection(registry, profile, (), ()).run) == _default_ids(registry) | FAIR_IDS


def test_explicit_select_replaces_the_fair_profile_opt_in(registry: RuleRegistry) -> None:
    assert {r[:3] for r in _ids(resolve_selection(registry, PROFILES["fair"], ("LEX",), ()).run)} == {"LEX"}


def test_ignores_apply_to_fair_rules(registry: RuleRegistry) -> None:
    selection = resolve_selection(registry, PROFILES["fair"], (), ("FAIR004",))
    assert "FAIR004" in _ids(selection.ignored) and "FAIR004" not in _ids(selection.run)
    ignored_profile = replace(PROFILES["fair"], ignore=("FAIR",))
    selection = resolve_selection(registry, ignored_profile, (), ())
    assert _ids(selection.ignored) == FAIR_IDS and not _ids(selection.run) & FAIR_IDS


def test_cli_default_run_never_executes_fair(run: Run) -> None:
    for argv in ((), ("--profile", "recommended"), ("--profile", "obo")):
        code, out, _ = run(KITCHEN, "--format", "json", "--fail-on", "never", *argv)
        document = json.loads(out)
        assert code == 0
        assert not any(r["id"].startswith("FAIR") for r in document["rules"])
        assert not any(f["rule"].startswith("FAIR") for f in document["findings"])
        assert not any(x["rule"].startswith("FAIR") for x in document["files"][0]["executions"])


def test_cli_select_and_profile_run_fair(run: Run) -> None:
    for argv in (("--select", "FAIR"), ("--select", "fair006,FAIR007"), ("--profile", "fair")):
        code, out, err = run(KITCHEN, "--format", "json", "--fail-on", "never", *argv)
        executed = {x["rule"]: x["status"] for x in json.loads(out)["files"][0]["executions"]}
        assert code == 0, err
        assert executed.get("FAIR006") == "executed" and executed.get("FAIR007") == "executed"
    _, out, _ = run(KITCHEN, "--format", "json", "--fail-on", "never", "--select", "FAIR006")
    assert {r["id"] for r in json.loads(out)["rules"]} == {"FAIR006"}


def test_list_rules_marks_fair_as_opt_in(run: Run) -> None:
    _, text, _ = run("--list-rules")
    lines = {line.split()[0]: line for line in text.splitlines()[1:-1]}
    assert lines["FAIR004"].endswith("(opt-in)")
    _, out, _ = run("--list-rules", "--format", "json")
    rows = {r["id"]: r for r in json.loads(out)["rules"]}
    assert all(rows[i]["opt_in"] is True and rows[i]["selectable"] for i in FAIR_IDS)


def test_explain_marks_fair_as_opt_in(run: Run) -> None:
    _, text, _ = run("--explain", "FAIR004")
    assert "Opt-in rule" in text
    _, out, _ = run("--explain", "FAIR004", "--format", "json")
    assert json.loads(out)["rule"]["opt_in"] is True
