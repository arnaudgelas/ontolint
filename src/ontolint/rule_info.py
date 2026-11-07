"""Read-only rule views for ``--list-rules`` and ``--explain``.

Three different questions are kept apart on purpose: the catalogue *status* (implemented or
proposed: is the rule built?), the engine's *execution status* (executed, skipped, unsupported,
failed: did it run on this input?) and the *requirements* (what a rule needs before it can run).
Listings only speak about the first; proposed rules cannot be selected, executed or skipped.
"""

from __future__ import annotations

import json
from typing import Any

from .catalogue import CatalogueRow, load_catalogue
from .models import CatalogueStatus, RuleSpec
from .profiles import is_opt_in
from .rules.registry import RuleRegistry

DASH = "-"
OPT_IN_MARK = " (opt-in)"


class UnknownRuleError(KeyError):
    """Raised by :func:`explain_rule` for an identifier that is neither implemented nor catalogued."""


def _implemented(spec: RuleSpec, row: CatalogueRow | None) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "id": spec.rule_id,
        "family": spec.family,
        "title": spec.title,
        "severity": spec.severity.value,
        "category": spec.category,
        "backend": spec.backend.value,
        "scope": spec.scope.value,
        "requires": spec.requires.value,
        "status": (row.status if row else CatalogueStatus.IMPLEMENTED).value,
        "selectable": True,
    }
    if is_opt_in(spec.family):  # Only opt-in rules carry the key, so other rows are unchanged.
        detail["opt_in"] = True
    return detail


def _proposed(row: CatalogueRow) -> dict[str, Any]:
    return {
        "id": row.rule_id,
        "family": row.family,
        "title": row.title,
        "severity": None,
        "category": row.category,
        "backend": row.backend,
        "scope": None,
        "requires": None,
        "status": row.status.value,
        "selectable": False,
    }


def _catalogue_by_id() -> dict[str, CatalogueRow]:
    return {row.rule_id: row for row in load_catalogue()}


def rule_rows(registry: RuleRegistry) -> list[dict[str, Any]]:
    """Every implemented rule followed by every catalogue-only rule, each group ordered by identifier."""
    catalogue = _catalogue_by_id()
    rows = [_implemented(spec, catalogue.get(spec.rule_id)) for spec in registry.all()]
    planned = sorted(
        (row for row in catalogue.values() if row.rule_id not in registry),
        key=lambda row: row.rule_id,
    )
    return rows + [_proposed(row) for row in planned]


def render_rule_list(rows: list[dict[str, Any]], output_format: str) -> str:
    """Render the rule table as text or JSON (``sarif`` is not meaningful here and falls back to JSON)."""
    if output_format != "text":
        return json.dumps({"schema_version": 1, "rules": rows}, indent=2)
    header = ("ID", "FAMILY", "SEVERITY", "CATEGORY", "BACKEND", "SCOPE", "STATUS")
    keys = ("id", "family", "severity", "category", "backend", "scope", "status")
    body = [[str(row[key]) if row[key] is not None else DASH for key in keys] for row in rows]
    for line, row in zip(body, rows, strict=True):
        if row.get("opt_in"):
            line[-1] += OPT_IN_MARK
    widths = [max(len(line[i]) for line in [header, *body]) for i in range(len(header))]
    lines = [
        "  ".join(cell.ljust(width) for cell, width in zip(line, widths, strict=True)).rstrip()
        for line in [header, *body]
    ]
    implemented = sum(row["selectable"] for row in rows)
    lines.append(
        f"{implemented} implemented, {len(rows) - implemented} proposed (proposed rules cannot be selected or run)"
    )
    return "\n".join(lines)


def explain_rule(rule_id: str, registry: RuleRegistry) -> dict[str, Any]:
    """Return everything known about one rule; raise :class:`UnknownRuleError` if nothing is."""
    key = rule_id.strip().upper()
    row = _catalogue_by_id().get(key)
    if key in registry:
        detail = _implemented(registry.get(key), row)
        spec = registry.get(key)
        detail["suggestion"] = spec.suggestion
    elif row is not None:
        detail = _proposed(row)
        detail["suggestion"] = None
    else:
        raise UnknownRuleError(rule_id)
    detail["test_requirement"] = row.test_requirement if row else None
    return detail


def render_explanation(detail: dict[str, Any], output_format: str) -> str:
    """Render :func:`explain_rule` output as text or JSON."""
    if output_format != "text":
        return json.dumps({"schema_version": 1, "rule": detail}, indent=2)
    lines = [f"{detail['id']}: {detail['title']}"]
    lines += [f"  {label:17}{DASH if detail[key] is None else detail[key]}" for label, key in _EXPLAIN_FIELDS]
    if detail.get("opt_in"):
        lines.append(
            "  Opt-in rule: it runs only with --select (family or id) or a profile that enables it, "
            "e.g. --profile obo or --profile fair."
        )
    if not detail["selectable"]:
        lines.append("  This rule is proposed only: it is not implemented, so it cannot be selected or executed.")
    return "\n".join(lines)


_EXPLAIN_FIELDS = (
    ("Catalogue status", "status"),
    ("Family", "family"),
    ("Severity", "severity"),
    ("Category", "category"),
    ("Backend", "backend"),
    ("Scope", "scope"),
    ("Requires", "requires"),
    ("Suggestion", "suggestion"),
    ("Test requirement", "test_requirement"),
)
