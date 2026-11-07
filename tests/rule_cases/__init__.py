"""Per-family rule cases.  Each module exports ``CASES: Mapping[str, RuleCases]``; discovery is automatic."""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Mapping

from rule_harness import RuleCases


def load_cases() -> dict[str, RuleCases]:
    """Merge the ``CASES`` of every module in this package; the same rule may appear in several files."""
    merged: dict[str, RuleCases] = {}
    for info in pkgutil.iter_modules(__path__):
        module = importlib.import_module(f"{__name__}.{info.name}")
        cases: Mapping[str, RuleCases] = getattr(module, "CASES", {})
        for rule_id, new in cases.items():
            old = merged.get(rule_id, RuleCases())
            merged[rule_id] = RuleCases(old.positive + new.positive, old.negative + new.negative)
    return merged
