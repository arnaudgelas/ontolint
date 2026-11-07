"""Contracts of the rule-module list that agents extend: one file plus one line adds a family."""

from __future__ import annotations

import re
import types

import pytest
from rule_harness import BASE, graph

from ontolint import Linter, engine
from ontolint.catalogue import load_catalogue, planned_rows
from ontolint.models import CatalogueStatus, RuleBackend, RuleScope, RuleSpec, Severity
from ontolint.rules import builtin
from ontolint.rules.builtin import RULE_MODULES, RULE_SPECS, module_name, validate_modules
from ontolint.rules.registry import default_registry
from ontolint.rules.specs import FIXES, SEVERITY


def test_the_module_list_is_consistent() -> None:
    assert validate_modules() == []
    assert tuple(engine.FAMILY_RUNNERS) == tuple(module_name(m) for m in RULE_MODULES)
    # The original eight modules keep their relative order and stay first; new modules append.
    assert tuple(engine.FAMILY_RUNNERS)[:8] == (
        "metadata", "identifiers", "lexical", "classes", "owl", "skos", "shapes", "governance",
    )  # fmt: skip


def test_every_module_declares_its_own_specs() -> None:
    declared = [s.rule_id for m in RULE_MODULES for s in m.SPECS]
    assert len(declared) == len(set(declared))
    assert set(declared) | {s.rule_id for s in builtin.EXTERNAL_SPECS} == {s.rule_id for s in RULE_SPECS}
    assert set(SEVERITY) == set(FIXES) == {s.rule_id for s in RULE_SPECS}
    assert default_registry().all() == tuple(sorted(RULE_SPECS, key=lambda s: s.rule_id))


@pytest.mark.parametrize("module", RULE_MODULES, ids=module_name)
def test_a_module_emits_only_rules_it_declares(module: types.ModuleType) -> None:
    ode = (
        "ex:A a owl:Class ; rdfs:label ' x ' ; rdfs:subClassOf ex:B, ex:C . "
        "ex:p a owl:ObjectProperty, owl:DatatypeProperty . "
        "ex:c a skos:Concept . ex:i ex:q ex:A . ex:Old owl:deprecated true . ex:A owl:equivalentClass ex:A ."
    )
    shapes = "ex:S a sh:NodeShape ; sh:minCount 1 ; sh:property [ sh:path ex:p ] ."
    for graph_ in (graph(), graph(ode)):
        linter = Linter(graph_, graph(shapes), base=BASE)
        module.run(linter.rule_context)
        assert {f.rule for f in linter.rule_context.findings} <= {s.rule_id for s in module.SPECS}


def _spec(rule_id: str, module: str, backend: RuleBackend = RuleBackend.RDFLIB) -> RuleSpec:
    return RuleSpec(rule_id, "ZZZ", "t", Severity.INFO, "fix", "heuristic", backend, RuleScope.TERM, module)


def _fake(name: str, *specs: RuleSpec) -> types.ModuleType:
    module = types.ModuleType(f"ontolint.rules.{name}")
    module.SPECS = specs  # type: ignore[attr-defined]
    module.run = lambda ctx: None  # type: ignore[attr-defined]
    return module


def test_validation_reports_each_contract_violation() -> None:
    good = _fake("zzz", _spec("ZZZ001", "zzz"))
    assert validate_modules((*RULE_MODULES, good)) == []
    problems = validate_modules(
        (
            *RULE_MODULES,
            _fake("wrongmod", _spec("ZZZ002", "other")),
            _fake("dup", _spec("ONT001", "dup")),
            _fake("cli", _spec("ZZZ003", "cli", RuleBackend.CLI)),
            RULE_MODULES[0],
            types.ModuleType("ontolint.rules.nospecs"),
        )
    )
    text = "\n".join(problems)
    assert "ZZZ002: spec.module 'other'" in text
    assert "ONT001: declared in both metadata and dup" in text
    assert "ZZZ003: non-graph backends belong in rules/external.py" in text
    assert "module listed twice: metadata" in text
    assert "nospecs must define SPECS" in text


def test_proposed_catalogue_rules_are_never_registered_or_reported_as_executed() -> None:
    proposed = {row.rule_id for row in planned_rows()}
    assert proposed and proposed.isdisjoint(s.rule_id for s in default_registry().all())
    result = Linter(graph("ex:A a owl:Class ."), graph("ex:S a sh:NodeShape ."), base=BASE).execute()
    reported = {x.rule_id for x in result.executions} | {f.rule for f in result.findings}
    assert reported.isdisjoint(proposed)
    assert all(row.status is CatalogueStatus.IMPLEMENTED for row in load_catalogue() if row.rule_id in reported)


def test_catalogue_is_the_authority_on_what_is_planned_and_what_is_implemented() -> None:
    rows = {row.rule_id: row for row in load_catalogue()}
    registered = {spec.rule_id: spec for spec in default_registry().all()}
    assert set(registered) <= set(rows), "register a rule only after adding its catalogue row"
    for rule_id, row in rows.items():
        assert re.fullmatch(r"[A-Z]+\d{3}", rule_id), f"malformed rule id {rule_id}"
        assert rule_id.startswith(row.family), f"{rule_id} does not start with its family {row.family}"
        assert (row.status is CatalogueStatus.IMPLEMENTED) == (rule_id in registered), (
            f"{rule_id}: catalogue says {row.status.value}, registry says "
            f"{'registered' if rule_id in registered else 'absent'}; flip status and spec together"
        )
    for rule_id, spec in registered.items():
        assert rule_id.startswith(spec.family) and spec.family == rows[rule_id].family
