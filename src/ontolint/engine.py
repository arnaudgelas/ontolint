"""Rule-engine coordinator: builds the run context, runs rule families, de-duplicates and sorts."""

from __future__ import annotations

import shutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path

from rdflib import BNode, Graph, Literal

from .adapters.robot import robot_profile_issues
from .adapters.shacl import bounded_shacl_issues, detail_foci, shacl_issues
from .context import GraphContext
from .models import (
    ExecutionStatus,
    Finding,
    Requirement,
    RuleBackend,
    RuleExecution,
    RuleSpec,
    RunResult,
)
from .policy import Policy
from .profiles import is_opt_in
from .redaction import redact_userinfo
from .reporting import SEVERITY_ORDER
from .rules.builtin import RULE_MODULES, module_name, module_runners, module_specs
from .rules.registry import RuleRegistry, default_registry
from .rules.runtime import RuleContext
from .rules.support import ntriples_literal, stable_blank_id
from .worker import WorkerFailed

type RuleFamily = Callable[[RuleContext], None]

# Execution order is part of the observable contract (first emission wins de-duplication).
# Keys match ``RuleSpec.module``; the order comes from ``rules.builtin.RULE_MODULES``.
FAMILY_RUNNERS: dict[str, RuleFamily] = module_runners()
# Modules whose rules are all opt-in never run unless a selection names them.
OPT_IN_MODULES: frozenset[str] = frozenset(
    module_name(m) for m in RULE_MODULES if all(is_opt_in(spec.family) for spec in module_specs(m))
)
# Modules whose rules all need a shapes graph report on its shapes: their blank nodes are named in it.
SHAPES_MODULES: frozenset[str] = frozenset(
    module_name(m) for m in RULE_MODULES if all(spec.requires is Requirement.SHAPES for spec in module_specs(m))
)


@dataclass(frozen=True)
class RobotRequest:
    """An explicit request for ROBOT OWL-profile validation of an ontology file."""

    ontology: Path
    profile: str
    image: str = "ontolint-robot:1.9.11"
    timeout: int = 120


def build_context(graph: Graph, shapes_graph: Graph | None, policy: Policy) -> RuleContext:
    """Index ``graph`` once and bundle it with ``policy`` for rule execution."""
    graph_context = GraphContext.build(
        graph, base=policy.base, imported_ontologies=policy.imported_ontologies, root_terms=policy.root_terms
    )
    return RuleContext(graph, shapes_graph, policy, graph_context)


def sort_findings(findings: list[Finding]) -> list[Finding]:
    """Order by severity, then rule, focus and message."""
    return sorted(findings, key=lambda x: (SEVERITY_ORDER.index(x.severity), x.rule, x.focus, x.message))


def _run_family(module: str, family: RuleFamily, ctx: RuleContext) -> None:
    """Run one rule module, naming blank nodes in the graph its findings are about."""
    if module in SHAPES_MODULES:
        with ctx.naming_shapes():
            family(ctx)
    else:
        family(ctx)


def run_rules(ctx: RuleContext) -> list[Finding]:
    """Run every rule family against ``ctx`` and return its sorted, de-duplicated findings."""
    for name, family in FAMILY_RUNNERS.items():
        if name not in OPT_IN_MODULES:
            _run_family(name, family, ctx)
    return sort_findings(ctx.findings)


def _not_run(spec: RuleSpec, ctx: RuleContext, robot: RobotRequest | None) -> RuleExecution | None:
    """Return a skipped/unsupported record when ``spec`` cannot run; never a silent pass."""
    skipped, unsupported = ExecutionStatus.SKIPPED, ExecutionStatus.UNSUPPORTED
    reason: tuple[ExecutionStatus, str] | None = None
    if spec.rule_id in ctx.policy.ignored_rules:
        reason = skipped, "ignored by policy"
    elif spec.backend is RuleBackend.CLI:
        reason = skipped, "emitted by the command-line front end on input or tool failure, not by the engine"
    elif spec.requires is Requirement.SHAPES and ctx.shapes is None:
        reason = skipped, "no SHACL shapes graph was supplied"
    elif spec.requires is Requirement.OWL_PROFILE and robot is None:
        reason = skipped, "OWL profile validation was not requested"
    elif spec.requires is Requirement.PATTERN_LIBRARY and ctx.policy.library is None:
        reason = skipped, "no pattern library was supplied (--pattern-library)"
    elif spec.backend is RuleBackend.PYSHACL and find_spec("pyshacl") is None:
        reason = unsupported, "pySHACL is not installed"
    elif spec.backend is RuleBackend.ROBOT_DOCKER and shutil.which("docker") is None:
        reason = unsupported, "the docker executable was not found on PATH"
    return RuleExecution(spec.rule_id, reason[0], reason[1]) if reason else None


def _failure(exc: Exception) -> str:
    """``<ExceptionType>: <message>``; a failure inside a worker names the worker's exception, as in process."""
    if isinstance(exc, WorkerFailed):
        return f"{exc.cause_type}: {exc.detail}"
    return f"{type(exc).__name__}: {exc}"


def _validate(data: Graph, shapes: Graph, seconds: float | None) -> list[Finding]:
    """Validate in this process, or with ``max_validation_seconds`` in a worker stopped at the budget."""
    if seconds is None:
        return shacl_issues(data, shapes)
    return bounded_shacl_issues(data, shapes, seconds)


def _shacl_with_background(ctx: RuleContext) -> list[Finding]:
    """Validate ``ctx.g``, merged with the SHACL-only background when there is one.

    The background (the ontology the shapes import) only supplies context, such as the classes of
    vocabulary individuals: results about nodes that only the background mentions are not findings of
    the linted file.  A node the linted file mentions anywhere is its own, as an object too: a shape
    with ``sh:targetObjectsOf`` focuses on nodes that need not be subjects of anything.  A finding is kept
    when its focus is the file's, or the focus of any result nested in its ``evidence.detail`` is: SHACL
    reports an ``sh:node`` violation on the referencing node, which may be the background's, while its
    nested result is the cause in the linted file.  A finding's focus and evidence are masked
    (:mod:`ontolint.redaction`), so the file's nodes are compared masked too, each spelled as the finding
    or the evidence spells a term (the evidence writes a literal in N-Triples).
    """
    assert ctx.shapes is not None  # noqa: S101 -- _not_run rules out SHACL without shapes.
    seconds = ctx.policy.max_validation_seconds
    if ctx.shacl_background is None:
        return _validate(ctx.g, ctx.shapes, seconds)
    data = ctx.g | ctx.shacl_background
    own: set[str] = set()  # as a finding names its focus
    spelled: set[str] = set()  # as evidence spells a term
    for n in {node for s, _p, o in ctx.g for node in (s, o)}:
        name = stable_blank_id(data, n) if isinstance(n, BNode) else redact_userinfo(str(n))
        own.add(name)
        spelled.add(redact_userinfo(ntriples_literal(n)) if isinstance(n, Literal) else name)
    return [
        finding
        for finding in _validate(data, ctx.shapes, seconds)
        if finding.focus in own or not spelled.isdisjoint(detail_foci(finding.evidence))
    ]


def _run_adapter(spec: RuleSpec, ctx: RuleContext, robot: RobotRequest | None) -> tuple[RuleExecution, list[Finding]]:
    """Run the SHACL or ROBOT adapter, converting any exception into a ``failed`` record."""
    try:
        if spec.backend is RuleBackend.PYSHACL and ctx.shapes is not None:
            found = _shacl_with_background(ctx)
        elif robot is not None:
            found = robot_profile_issues(robot.ontology, robot.profile, robot.image, robot.timeout)
        else:  # pragma: no cover -- _not_run rules out adapters without their inputs.
            raise RuntimeError("adapter inputs missing")
    except Exception as exc:  # noqa: BLE001 -- a backend failure is a result, not a crash.
        return RuleExecution(spec.rule_id, ExecutionStatus.FAILED, _failure(exc)), []
    return RuleExecution(spec.rule_id, ExecutionStatus.EXECUTED), found


def _run_modules(ctx: RuleContext, modules: set[str]) -> dict[str, str]:
    """Run the needed rule modules in contract order; return ``module -> failure detail``."""
    failures: dict[str, str] = {}
    for module, runner in FAMILY_RUNNERS.items():
        if module in modules:
            try:
                _run_family(module, runner, ctx)
            except Exception as exc:  # noqa: BLE001 -- one broken rule module must not abort the run.
                failures[module] = _failure(exc)
    return failures


def execute(
    ctx: RuleContext,
    selectors: Iterable[str] = (),
    *,
    registry: RuleRegistry | None = None,
    robot: RobotRequest | None = None,
) -> RunResult:
    """Run the selected rules and record an execution outcome for each of them.

    Rules whose requirements or backend are unavailable are ``skipped``/``unsupported``
    with a reason; rule modules or adapters that raise are ``failed`` and contribute no
    findings.  Unknown selectors raise :class:`~ontolint.rules.registry.UnknownSelectorError`.
    """
    specs = (registry or default_registry()).select(selectors)
    outcomes: dict[str, RuleExecution] = {}
    runnable: list[RuleSpec] = []
    for spec in specs:
        skipped = _not_run(spec, ctx, robot)
        if skipped:
            outcomes[spec.rule_id] = skipped
        else:
            runnable.append(spec)
    graph_specs = [s for s in runnable if s.backend is RuleBackend.RDFLIB]
    failures = _run_modules(ctx, {s.module for s in graph_specs})
    accepted = {s.rule_id for s in graph_specs if s.module not in failures}
    for spec in graph_specs:
        failure = failures.get(spec.module)
        outcomes[spec.rule_id] = (
            RuleExecution(spec.rule_id, ExecutionStatus.FAILED, failure)
            if failure
            else RuleExecution(spec.rule_id, ExecutionStatus.EXECUTED)
        )
    findings = [f for f in ctx.findings if f.rule in accepted]
    for spec in (s for s in runnable if s.backend is not RuleBackend.RDFLIB):
        outcomes[spec.rule_id], extra = _run_adapter(spec, ctx, robot)
        findings += extra
    return RunResult(tuple(sort_findings(findings)), tuple(outcomes[s.rule_id] for s in specs))
