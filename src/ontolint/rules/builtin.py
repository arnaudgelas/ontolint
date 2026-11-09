"""The single, ordered list of built-in rule modules and the registry data derived from it.

Adding a rule family is one new module plus one line in :data:`RULE_MODULES`:

* the module declares ``SPECS: tuple[RuleSpec, ...]`` and ``run(ctx: RuleContext) -> None``;
* every spec's ``module`` field equals the module's file name (``"metadata"`` for ``rules/metadata.py``).

Order is part of the observable contract: the engine runs modules in this order and the first
emission of a ``(rule, focus, message)`` triple wins de-duplication.  New modules therefore go at
the end unless a deliberate, golden-reviewed change says otherwise.

Rules that no ``run`` function emits (adapters and the CLI front end) are declared in
:mod:`ontolint.rules.external`.  This module imports only rule modules, never the engine or
:mod:`ontolint.rules.runtime`, so it can be imported from anywhere without circularity.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import TYPE_CHECKING, Protocol, cast

from ontolint.models import RuleBackend, RuleSpec

from . import (
    alignment,
    class_heuristics,
    classes,
    external,
    fair_offline,
    governance,
    governance_metadata,
    hierarchy_quality,
    identifiers,
    imports_note,
    iri_lexical_extras,
    iri_quality,
    lexical,
    lexical_quality,
    literals,
    metadata,
    metrics,
    obo,
    owl,
    owl_axioms,
    owl_expressions,
    policy_rules,
    safe_loader,
    safety,
    shacl_authoring,
    shacl_quality,
    shapes,
    skos,
    skos_integrity,
)

if TYPE_CHECKING:
    from .runtime import RuleContext


class RuleModule(Protocol):
    """What a rule-family module must provide (checked structurally and by :func:`validate_modules`)."""

    SPECS: tuple[RuleSpec, ...]

    def run(self, ctx: RuleContext, /) -> None:
        """Emit findings for the rules declared in ``SPECS`` onto ``ctx``."""
        ...


type RuleRunner = Callable[[RuleContext], None]

# Execution order is the contract (see module docstring).  Add new rule-family modules here.
RULE_MODULES: tuple[ModuleType, ...] = (
    metadata,
    identifiers,
    lexical,
    classes,
    owl,
    skos,
    shapes,
    governance,
    skos_integrity,
    iri_quality,
    lexical_quality,
    shacl_authoring,
    hierarchy_quality,
    owl_axioms,
    owl_expressions,
    metrics,
    class_heuristics,
    iri_lexical_extras,
    shacl_quality,
    safety,
    governance_metadata,
    alignment,
    obo,
    policy_rules,
    imports_note,
    fair_offline,
    literals,
)

# Declared specs with no ``run`` function behind them (adapters, CLI front end).
EXTERNAL_SPECS: tuple[RuleSpec, ...] = external.SPECS + safe_loader.SPECS


def module_name(module: ModuleType) -> str:
    """Return the short name that ``RuleSpec.module`` uses for ``module``."""
    return module.__name__.rsplit(".", 1)[-1]


def as_rule_module(module: ModuleType) -> RuleModule:
    """View ``module`` as a :class:`RuleModule`, failing loudly if it lacks the contract."""
    if not isinstance(getattr(module, "SPECS", None), tuple) or not callable(getattr(module, "run", None)):
        raise TypeError(f"{module.__name__} must define SPECS (a tuple of RuleSpec) and run(ctx)")
    return cast("RuleModule", module)


def module_specs(module: ModuleType) -> tuple[RuleSpec, ...]:
    """Return the specs a rule module declares."""
    return as_rule_module(module).SPECS


def module_runners(modules: tuple[ModuleType, ...] = RULE_MODULES) -> dict[str, RuleRunner]:
    """Map module name to its ``run`` function, in execution order."""
    return {module_name(m): as_rule_module(m).run for m in modules}


def collect_specs(modules: tuple[ModuleType, ...] = RULE_MODULES) -> tuple[RuleSpec, ...]:
    """Return every declared spec: rule modules in order, then the external (non-graph) ones."""
    return tuple(spec for module in modules for spec in module_specs(module)) + EXTERNAL_SPECS


def validate_modules(modules: tuple[ModuleType, ...] = RULE_MODULES) -> list[str]:
    """Return human-readable contract violations (empty when the module list is consistent)."""
    problems: list[str] = []
    seen: dict[str, str] = {}
    names = [module_name(m) for m in modules]
    problems += [f"module listed twice: {n}" for n in sorted({n for n in names if names.count(n) > 1})]
    for module in modules:
        name = module_name(module)
        try:
            specs = module_specs(module)
        except TypeError as exc:
            problems.append(str(exc))
            continue
        for spec in specs:
            if spec.module != name:
                problems.append(f"{spec.rule_id}: spec.module {spec.module!r} != declaring module {name!r}")
            if spec.backend is not RuleBackend.RDFLIB:
                problems.append(f"{spec.rule_id}: non-graph backends belong in rules/external.py")
            if spec.rule_id in seen:
                problems.append(f"{spec.rule_id}: declared in both {seen[spec.rule_id]} and {name}")
            seen[spec.rule_id] = name
    for spec in EXTERNAL_SPECS:
        if spec.module or spec.backend is RuleBackend.RDFLIB:
            problems.append(f"{spec.rule_id}: external specs need module='' and a non-graph backend")
        if spec.rule_id in seen:
            problems.append(f"{spec.rule_id}: declared in both {seen[spec.rule_id]} and external")
    return problems


RULE_SPECS: tuple[RuleSpec, ...] = collect_specs()
