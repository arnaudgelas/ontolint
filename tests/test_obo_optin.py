"""Opt-in rule families: the OBO family never runs unless selected explicitly or by the ``obo`` profile."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from ontolint import engine, main
from ontolint.models import RuleSpec
from ontolint.profiles import OPT_IN_FAMILIES, PROFILES, Profile, is_opt_in
from ontolint.rules import obo, specs
from ontolint.rules.builtin import RULE_SPECS
from ontolint.rules.registry import RuleRegistry
from ontolint.selection import default_rules, resolve_selection

FIXTURES = Path(__file__).parent / "fixtures"
KITCHEN = str(FIXTURES / "kitchen_sink.ttl")
OBO_IDS = {s.rule_id for s in obo.SPECS}
ALL_SPECS: tuple[RuleSpec, ...] = tuple({s.rule_id: s for s in (*RULE_SPECS, *obo.SPECS)}.values())
Run = Callable[..., tuple[int, str, str]]


@pytest.fixture
def registry() -> RuleRegistry:
    """The built-in rules plus OBO, whether or not the OBO module is registered yet."""
    return RuleRegistry(ALL_SPECS)


@pytest.fixture
def run(registry: RuleRegistry, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> Run:
    monkeypatch.chdir(FIXTURES)
    monkeypatch.setattr("ontolint.cli.default_registry", lambda: registry)
    monkeypatch.setitem(engine.FAMILY_RUNNERS, "obo", obo.run)
    for spec in obo.SPECS:
        monkeypatch.setitem(specs.SEVERITY, spec.rule_id, spec.severity.value)
        monkeypatch.setitem(specs.FIXES, spec.rule_id, spec.suggestion)

    def _run(*argv: str) -> tuple[int, str, str]:
        code = main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return _run


def _ids(rules: tuple[RuleSpec, ...]) -> set[str]:
    return {s.rule_id for s in rules}


def _non_obo(registry: RuleRegistry) -> set[str]:
    return {s.rule_id for s in registry.all() if s.family != "OBO" and s.backend.value != "cli"}


def test_opt_in_data() -> None:
    assert {"OBO"} == OPT_IN_FAMILIES
    assert is_opt_in("OBO") and is_opt_in("obo")
    assert not is_opt_in("LEX") and not is_opt_in("")
    assert {s.family for s in obo.SPECS} == {"OBO"}
    assert [s.rule_id for s in obo.SPECS] == [f"OBO{n:03d}" for n in range(1, 13)]
    assert all(s.module == "obo" for s in obo.SPECS)


def test_default_rules_drop_opt_in_families(registry: RuleRegistry) -> None:
    defaults = default_rules(registry.all())
    assert _ids(defaults) == {s.rule_id for s in registry.all()} - OBO_IDS
    assert default_rules(()) == ()


@pytest.mark.parametrize("name", [None, "recommended", "ci", "strict", "minimal"])
def test_obo_is_not_part_of_the_default_profiles(registry: RuleRegistry, name: str | None) -> None:
    selection = resolve_selection(registry, PROFILES[name] if name else None, (), ())
    assert not _ids(selection.run + selection.ignored) & OBO_IDS
    if name != "minimal":
        assert _ids(selection.run) == _non_obo(registry)


def test_explicit_family_and_rule_selectors_opt_in(registry: RuleRegistry) -> None:
    assert _ids(resolve_selection(registry, None, ("OBO",), ()).run) == OBO_IDS
    assert _ids(resolve_selection(registry, None, ("OBO003",), ()).run) == {"OBO003"}
    mixed = _ids(resolve_selection(registry, PROFILES["strict"], ("OBO001", "LEX"), ()).run)
    assert "OBO001" in mixed and "OBO002" not in mixed
    assert {i for i in mixed if not i.startswith("OBO")} == {s.rule_id for s in registry.all() if s.family == "LEX"}


def test_obo_profile_is_the_default_selection_plus_obo(registry: RuleRegistry) -> None:
    profile = PROFILES["obo"]
    assert profile.select == () and profile.opt_in == ("OBO",) and profile.fail_on == "warning"
    assert _ids(resolve_selection(registry, profile, (), ()).run) == _non_obo(registry) | OBO_IDS


def test_explicit_select_replaces_the_obo_profile_opt_in(registry: RuleRegistry) -> None:
    assert {r[:3] for r in _ids(resolve_selection(registry, PROFILES["obo"], ("LEX",), ()).run)} == {"LEX"}


def test_profile_opt_in_is_added_to_a_profile_selection(registry: RuleRegistry) -> None:
    profile = replace(PROFILES["obo"], select=("ONT",))
    chosen = _ids(resolve_selection(registry, profile, (), ()).run)
    assert chosen == {s.rule_id for s in registry.all() if s.family == "ONT"} | OBO_IDS
    assert not _ids(resolve_selection(registry, replace(profile, opt_in=()), (), ()).run) & OBO_IDS


def test_ignores_apply_to_opt_in_rules(registry: RuleRegistry) -> None:
    selection = resolve_selection(registry, PROFILES["obo"], (), ("OBO004", "LEX"))
    assert "OBO004" in _ids(selection.ignored) and "OBO004" not in _ids(selection.run)
    ignored_profile = replace(PROFILES["obo"], ignore=("OBO",))
    selection = resolve_selection(registry, ignored_profile, (), ())
    assert _ids(selection.ignored) == OBO_IDS and not _ids(selection.run) & OBO_IDS
    # Ignoring an opt-in family that was never selected is harmless.
    assert not _ids(resolve_selection(registry, None, (), ("OBO",)).ignored)


def test_profiles_are_valid_pure_data(registry: RuleRegistry) -> None:
    for profile in PROFILES.values():
        assert isinstance(profile, Profile)
        registry.select(profile.opt_in)
        assert set(profile.opt_in) <= OPT_IN_FAMILIES
    assert {n for n, p in PROFILES.items() if p.opt_in} == {"obo"}


def test_cli_default_run_never_executes_obo(run: Run) -> None:
    for argv in ((), ("--profile", "recommended"), ("--profile", "strict"), ("--profile", "minimal")):
        code, out, _ = run(KITCHEN, "--format", "json", "--fail-on", "never", *argv)
        document = json.loads(out)
        assert code == 0
        assert not any(r["id"].startswith("OBO") for r in document["rules"])
        assert not any(f["rule"].startswith("OBO") for f in document["findings"])
        assert not any(x["rule"].startswith("OBO") for x in document["files"][0]["executions"])


def test_cli_select_and_profile_run_obo(run: Run) -> None:
    for argv in (("--select", "OBO"), ("--select", "obo003,OBO004"), ("--profile", "obo")):
        code, out, err = run(KITCHEN, "--format", "json", "--fail-on", "never", *argv)
        document = json.loads(out)
        executed = {x["rule"]: x["status"] for x in document["files"][0]["executions"]}
        assert code == 0, err
        assert executed.get("OBO003") == "executed" and executed.get("OBO004") == "executed"
        assert any(f["rule"] == "OBO003" for f in document["findings"])
    _, out, _ = run(KITCHEN, "--format", "json", "--fail-on", "never", "--select", "OBO003")
    assert {r["id"] for r in json.loads(out)["rules"]} == {"OBO003"}


def test_obo_gating(run: Run) -> None:
    only = ("--select", "OBO003")
    assert run(KITCHEN, *only)[0] == 0  # OBO003 is a warning and the default gate is error
    assert run(KITCHEN, *only, "--fail-on", "warning")[0] == 1
    assert run(KITCHEN, "--profile", "obo", "--select", "OBO003")[0] == 1  # the obo profile gates on warnings


def test_list_rules_marks_opt_in_rules(run: Run) -> None:
    _, text, _ = run("--list-rules")
    lines = {line.split()[0]: line for line in text.splitlines()[1:-1]}
    assert lines["OBO001"].endswith("(opt-in)")
    assert "(opt-in)" not in lines["ONT001"]
    _, out, _ = run("--list-rules", "--format", "json")
    rows = {r["id"]: r for r in json.loads(out)["rules"]}
    assert all(rows[i]["opt_in"] is True and rows[i]["selectable"] for i in OBO_IDS)
    assert "opt_in" not in rows["ONT001"]


def test_explain_marks_opt_in_rules(run: Run) -> None:
    _, text, _ = run("--explain", "OBO003")
    assert "Opt-in rule" in text and "--profile obo" in text
    assert "Opt-in rule" not in run("--explain", "ONT001")[1]
    _, out, _ = run("--explain", "OBO003", "--format", "json")
    assert json.loads(out)["rule"]["opt_in"] is True
    assert "opt_in" not in json.loads(run("--explain", "ONT001", "--format", "json")[1])["rule"]
