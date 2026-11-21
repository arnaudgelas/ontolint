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
  ``competency_question_pass_rate``, ``unreviewed_equivalence_mappings``) wait for those gates.
* **A ``delta`` budget** bounds the classified change of a coverage measure against a quality baseline
  (``--quality-baseline``): the number of ``regressed``, ``diluted`` and ``removed`` terms (``maximum``) and the share
  of the new terms that are fine (``new_terms``, ``minimum``, ``added_good / (added_good + diluted)``, no value when
  there are no new terms).  It is one more bound of METRIC014, so a breach is a finding of the same rule at the same
  severity, baselinable like the others; its identity is the rule, the focus, the measurement and the delta key
  (``delta:regressed``), never the counts.  The comparison is read before any bound is compared.  A run with no
  quality baseline, or a measurement that is not comparable with it (another definition version or population, a
  different policy shaping, not taken in either snapshot), fails the rule: exit ``2``, never a pass.  Only a
  coverage measure has terms, so a ``delta`` on a count, a histogram or a non-coverage ratio is a policy error.
  *Error, certain, deterministic:* the limit is the policy's own and the value is exact, so a breach is a fact
  the policy declared a failure; ``severity_overrides`` lowers it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ontolint.models import MeasurementKind, RuleBackend, RuleScope, RuleSpec, Severity
from ontolint.policy import DELTA_COUNTS, Budget, DeltaBudget, Policy, PolicyBudgetError

from . import measurements
from .bounds import MAXIMUM, MINIMUM, breached
from .metrics import FOCUS_FALLBACK, _vs

if TYPE_CHECKING:
    from ontolint.quality import Change

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
        if budget.delta is not None and spec.better is None:
            raise PolicyBudgetError(f"{where}.delta: {spec.id} has no terms; a delta bounds a coverage measure")


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


def _change(ctx: RuleContext, measurement_id: str) -> Change:
    """The classified change of a coverage measure against the quality baseline of the run.

    Raises :class:`~ontolint.rules.measurements.MeasurementUnavailable` when the run has no quality baseline or the
    measurement cannot be compared with it, which is exit ``2``: a delta budget never passes on a change it could
    not read.
    """
    comparison = ctx.quality_comparison
    if comparison is None:
        raise measurements.MeasurementUnavailable(
            measurement_id, "a delta budget needs a quality baseline (--quality-baseline FILE)"
        )
    result = {r.id: r for r in comparison.results}[measurement_id]  # the comparison has every measurement of either
    if result.reasons or result.change is None:
        raise measurements.MeasurementUnavailable(
            measurement_id,
            f"cannot be compared with the quality baseline ({'; '.join(result.reasons)}); "
            "write a new one with --write-quality-snapshot",
        )
    return result.change


_COUNT_PHRASES = {
    "regressed": ("term got worse", "terms got worse"),
    "diluted": ("new term is not fine", "new terms are not fine"),
    "removed": ("term was removed", "terms were removed"),
}


def _delta_breaches(budget: Budget, delta: DeltaBudget, change: Change) -> list[tuple[str, str]]:
    """Each bound of ``delta`` that ``change`` breaches, as the delta key and the message."""
    found: list[tuple[str, str]] = []
    counts = change.counts()
    for key in DELTA_COUNTS:
        limit = getattr(delta, key)
        if limit is not None and breached(counts[key], MAXIMUM, limit):
            one, many = _COUNT_PHRASES[key]
            found.append(
                (
                    key,
                    f"{budget.measurement}: {counts[key]} {one if counts[key] == 1 else many} "
                    f"since the quality baseline, above the maximum {limit}.",
                )
            )
    fine, new = counts["added_good"], counts["added_good"] + counts["diluted"]
    if delta.new_terms is not None and new and breached(fine / new, MINIMUM, delta.new_terms):
        shown, shown_limit = _vs(fine / new, delta.new_terms)
        found.append(
            (
                "new_terms",
                f"{budget.measurement}: the share of new terms that are fine is {shown} ({fine} of {new}) "
                f"since the quality baseline, below the minimum {shown_limit}.",
            )
        )
    return found


def run(ctx: RuleContext) -> None:
    """Report every bound of ``quality_budgets`` that its measurement's value or change breaches."""
    budgets = ctx.policy.quality_budgets
    if not budgets:
        return
    validate(ctx.policy)
    # Everything is read before anything is compared, so a failed run reports no partial verdict.
    values = [
        (budget, *_value(ctx, budget.measurement))
        for budget in budgets
        if budget.minimum is not None or budget.maximum is not None
    ]
    changes = [
        (budget, delta, _change(ctx, budget.measurement)) for budget in budgets if (delta := budget.delta) is not None
    ]
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
    for budget, delta, change in changes:
        for key, message in _delta_breaches(budget, delta, change):
            ctx.add(
                "METRIC014", _focus(ctx), message, confidence="certain", subject=(budget.measurement, f"delta:{key}")
            )
