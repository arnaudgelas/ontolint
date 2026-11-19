"""The one comparison of a measured value with a limit, and the METRIC policy keys as built-in budgets.

A *bound* is a ``minimum`` or a ``maximum`` and is inclusive: a value equal to its limit is within it.  A value
is breached when it is above a maximum or below a minimum, strictly.  Every METRIC rule compares through
:func:`breached`, and so does METRIC014 (:mod:`ontolint.rules.budgets`), so a threshold of the policy file and a
budget cannot disagree about a boundary.

:data:`BUILT_IN` is the table of the METRIC001-METRIC013 policy keys read as budgets: the measurement each bounds,
which side and over which quantity of it.  Those keys stay the way to set a METRIC limit (they also carry the
``metric_min_sample`` gate and the METRIC message); the table is what ties them to the measurement catalogue
(:mod:`ontolint.rules.measurements`), and ``docs/quality-budgets.md`` lists it.  This module
imports nothing of the package, so the METRIC rules can use it.
"""

from __future__ import annotations

from dataclasses import dataclass

MINIMUM = "minimum"
MAXIMUM = "maximum"

# What a bound is over: the share (numerator over denominator), the share the numerator lacks (denominator minus
# numerator, over denominator: a METRIC coverage rule bounds how many terms are missing), the mean (a measurement
# of integers per term, as a ratio) or the count.
SHARE = "share"
MISSING = "missing share"
MEAN = "mean"
COUNT = "count"


def breached(value: float, side: str, limit: float) -> bool:
    """Whether ``value`` is outside the bound: above a ``maximum`` or below a ``minimum``; at the limit it is not."""
    return value > limit if side == MAXIMUM else value < limit


@dataclass(frozen=True)
class BuiltIn:
    """One METRIC policy key as a budget: the rule, the measurement it bounds, the side and the quantity."""

    key: str
    rule: str
    measurement: str
    side: str
    over: str
    gate: str | None = "denominator"
    """What the ``metric_min_sample`` gate counts, or ``None`` for a rule without one: the measurement's denominator
    unless said."""


BUILT_IN: tuple[BuiltIn, ...] = (
    BuiltIn("metric_max_unlabelled_ratio", "METRIC001", "class_label_coverage", MAXIMUM, MISSING),
    BuiltIn("metric_max_undefined_ratio", "METRIC002", "class_definition_coverage", MAXIMUM, MISSING),
    BuiltIn("metric_max_undocumented_property_ratio", "METRIC003", "property_documentation_coverage", MAXIMUM, MISSING),
    BuiltIn("metric_max_mean_fanout", "METRIC004", "class_fanout", MAXIMUM, MEAN, "owned classes"),
    BuiltIn("metric_max_orphan_ratio", "METRIC005", "orphan_classes", MAXIMUM, SHARE, "owned classes"),
    BuiltIn("metric_min_property_class_ratio", "METRIC006", "relation_properties_per_class", MINIMUM, MEAN),
    BuiltIn("metric_max_property_class_ratio", "METRIC007", "relation_properties_per_class", MAXIMUM, MEAN),
    BuiltIn("metric_max_unsigned_property_ratio", "METRIC008", "unsigned_properties", MAXIMUM, SHARE),
    BuiltIn("metric_min_language_coverage", "METRIC009", "label_language_coverage", MINIMUM, SHARE),
    BuiltIn("metric_max_foreign_reference_ratio", "METRIC010", "foreign_references", MAXIMUM, SHARE),
    BuiltIn("metric_max_imports", "METRIC011", "unresolved_imports", MAXIMUM, COUNT, None),
    BuiltIn("metric_min_definition_words", "METRIC012", "definition_length", MINIMUM, MEAN),
    BuiltIn("metric_max_blank_node_ratio", "METRIC013", "blank_subjects", MAXIMUM, SHARE),
)
