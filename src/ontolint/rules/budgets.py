"""Quality budgets, the explicit thresholds a policy puts over measurements: METRIC014.

A budget is a ``minimum``, a ``maximum`` or both on the value of one measurement of the catalogue
(:mod:`ontolint.rules.measurements`, ``docs/measurements.md``), written in the policy file as
``quality_budgets: {"unresolved_imports": {"maximum": 0}, "class_definition_coverage": {"minimum": 0.95}}``
(``docs/quality-budgets.md``).  There is no default budget: a policy without ``quality_budgets`` runs none.  Common
to the rule:

* The value of a ratio is its numerator over its denominator (a mean is the sum over the count), the value of a
  count is the count; a histogram has no value and cannot be budgeted.  A ratio over an empty population has no
  value, so it breaches nothing.  Unlike a METRIC rule, a budget has no ``metric_min_sample`` gate: the limit is
  the policy's own.
* Bounds are inclusive (:func:`~ontolint.rules.bounds.breached`): a value equal to its limit is within the budget.
* A measurement that was not taken (no shapes graph for the SHACL coverage, or a computation that raised) has
  no value to bound: the rule fails, which is exit ``2`` whatever ``--fail-on`` says, never a pass.  Every budget
  is read before any is compared, so the rule reports no partial verdict.
* A name that is not a measurement, a histogram, a bound a measurement cannot hold (a fraction of a count, above 1
  for a coverage) or a malformed budget is a policy error, ``GOV020`` and exit ``2``, before any input is read.
* The focus is the lexically first ontology IRI of the graph (``ctx.ontologies``), else ``urn:ontolint:graph``, and
  the subject is the measurement and the side, so the identity of a finding is its rule, focus, measurement and
  side: the value and the limit never change a baseline entry.

* **METRIC014.** (``quality_budgets``.)  One finding for each bound a value breaches: ``<measurement> is <value>
  (<numerator> of <denominator>), below the minimum <limit>.`` (``above the maximum`` for a maximum; a count
  prints its value).  The value and the limit print with 2 decimals, or as many more (up to 6) as it takes to
  tell them apart.  Budgets on the measurements of the SEM, CQ and ALIGN gates (``new_unsatisfiable_classes``,
  ``competency_question_pass_rate``, ``unreviewed_equivalence_mappings``) wait for those gates; bounds over the
  classified change against a quality baseline are not read yet (a ``delta`` key is refused).
  *Error, certain, deterministic:* the limit is the policy's own and the value is exact, so a breach is a fact
  the policy declared a failure; ``severity_overrides`` lowers it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ontolint.models import MeasurementKind, RuleBackend, RuleScope, RuleSpec, Severity
from ontolint.policy import Budget, Policy, PolicyBudgetError

from . import measurements
from .bounds import MAXIMUM, MINIMUM, breached
from .metrics import FOCUS_FALLBACK, _vs

if TYPE_CHECKING:
    from .runtime import RuleContext

SPECS: tuple[RuleSpec, ...] = (
    RuleSpec(
        "METRIC014",
        "METRIC",
        "Quality budget breached",
        Severity.ERROR,
        "Bring the measurement within its quality_budgets bound, or change the budget in the policy file.",
        "deterministic",
        RuleBackend.RDFLIB,
        RuleScope.ONTOLOGY,
        "budgets",
    ),
)


def validate(policy: Policy) -> None:
    """Raise :class:`~ontolint.policy.PolicyBudgetError` for a budget no measurement of the catalogue can carry.

    The policy checks the shape of ``quality_budgets``; what a name and its bounds mean is the catalogue's.
    """
    for budget in policy.quality_budgets:
        where = f"quality_budgets.{budget.measurement}"
        try:
            spec = measurements.spec_of(budget.measurement)
        except KeyError:
            known = ", ".join(s.id for s in measurements.SPECS if s.kind is not MeasurementKind.HISTOGRAM)
            raise PolicyBudgetError(
                f"{where}: unknown measurement {budget.measurement!r}; budgets bound {known}"
            ) from None
        bounds = [b for b in (budget.minimum, budget.maximum) if b is not None]
        if spec.kind is MeasurementKind.HISTOGRAM:
            raise PolicyBudgetError(f"{where}: {spec.id} is a histogram, which has no single value to bound")
        if spec.kind is MeasurementKind.COUNT and not all(isinstance(b, int) for b in bounds):
            raise PolicyBudgetError(f"{where}: {spec.id} counts: its bounds are integers")
        if spec.better is not None and any(b > 1 for b in bounds):
            raise PolicyBudgetError(f"{where}: {spec.id} is a share: its bounds are at most 1")


def _value(ctx: RuleContext, measurement_id: str) -> tuple[int | float | None, str]:
    """The value of a measurement and what it is of (``"6 of 33"``, empty for a count); ``None`` over nothing.

    Raises :class:`~ontolint.rules.measurements.MeasurementUnavailable` when it was not taken.
    """
    if measurements.spec_of(measurement_id).kind is MeasurementKind.COUNT:
        return measurements.count(ctx, measurement_id), ""
    numerator, denominator = measurements.ratio(ctx, measurement_id)
    return (numerator / denominator if denominator else None), f"{numerator} of {denominator}"


def _focus(ctx: RuleContext) -> str:
    return str(min(ctx.ontologies, key=str)) if ctx.ontologies else FOCUS_FALLBACK


def _breach(budget: Budget, side: str, limit: float, value: float, of: str) -> str:
    shown, shown_limit = _vs(value, limit) if of else (str(value), str(limit))
    where = f"{budget.measurement} is {shown}" + (f" ({of})" if of else "")
    return f"{where}, {'below the minimum' if side == MINIMUM else 'above the maximum'} {shown_limit}."


def run(ctx: RuleContext) -> None:
    """Report every bound of ``quality_budgets`` that its measurement's value breaches."""
    budgets = ctx.policy.quality_budgets
    if not budgets:
        return
    validate(ctx.policy)
    values = [(budget, *_value(ctx, budget.measurement)) for budget in budgets]  # all read before any is compared
    for budget, value, of in values:
        if value is None:
            continue
        for side, limit in ((MINIMUM, budget.minimum), (MAXIMUM, budget.maximum)):
            if limit is not None and breached(value, side, limit):
                ctx.add(
                    "METRIC014",
                    _focus(ctx),
                    _breach(budget, side, limit, value, of),
                    confidence="certain",
                    subject=(budget.measurement, side),
                )
