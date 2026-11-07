"""Built-in rule specifications, assembled from the rule modules.

Each rule-family module declares its own ``SPECS`` next to its implementation;
:mod:`ontolint.rules.builtin` lists the modules once and concatenates them into ``RULE_SPECS``.
``SEVERITY`` and ``FIXES`` are derived views kept for compatibility.  This module imports no
engine or runtime code, so rules, reporters, adapters and the registry can all depend on it.
"""

from __future__ import annotations

from .builtin import RULE_SPECS

__all__ = ["FIXES", "RULE_SPECS", "SEVERITY"]

# Compatibility views; the engine and reporters read these instead of duplicating metadata.
SEVERITY: dict[str, str] = {spec.rule_id: spec.severity.value for spec in RULE_SPECS}
FIXES: dict[str, str] = {spec.rule_id: spec.suggestion for spec in RULE_SPECS}
