"""Validated, immutable linting policy independent of CLI argument parsing."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .models import Severity

DEFAULT_DEPTH_LIMIT = 7
DEFAULT_INHERITANCE_LIMIT = 3
DEFAULT_SOUP_LIMIT = 15


@dataclass(frozen=True)
class Policy:
    """Configuration for graph-local rules and report post-processing."""

    base: str | None = None
    languages: tuple[str, ...] = ()
    depth_limit: int = DEFAULT_DEPTH_LIMIT
    inheritance_limit: int = DEFAULT_INHERITANCE_LIMIT
    soup_limit: int = DEFAULT_SOUP_LIMIT
    ignored_rules: frozenset[str] = frozenset()
    severity_overrides: tuple[tuple[str, str], ...] = ()

    @property
    def severity_mapping(self) -> dict[str, str]:
        """Return overrides in the shape expected by report filtering."""
        return dict(self.severity_overrides)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> Policy:
        """Create policy from JSON-compatible data and reject malformed values."""
        base = data.get("base")
        languages = data.get("languages", [])
        ignored_rules = data.get("ignored_rules", [])
        overrides = data.get("severity_overrides", {})
        numeric_values = {
            "depth_limit": data.get("depth_limit", DEFAULT_DEPTH_LIMIT),
            "inheritance_limit": data.get("inheritance_limit", DEFAULT_INHERITANCE_LIMIT),
            "soup_limit": data.get("soup_limit", DEFAULT_SOUP_LIMIT),
        }
        if base is not None and not isinstance(base, str):
            raise ValueError("base must be a string or null")
        if not isinstance(languages, list) or not all(isinstance(value, str) for value in languages):
            raise ValueError("languages must be a list of strings")
        if not isinstance(ignored_rules, list) or not all(isinstance(value, str) for value in ignored_rules):
            raise ValueError("ignored_rules must be a list of rule identifiers")
        if not isinstance(overrides, dict) or not all(
            isinstance(rule, str) and isinstance(severity, str) for rule, severity in overrides.items()
        ):
            raise ValueError("severity_overrides must map rule identifiers to severities")
        valid_severities = {severity.value for severity in Severity}
        if any(severity not in valid_severities for severity in overrides.values()):
            raise ValueError("severity_overrides must be error, warning or info")
        if any(not isinstance(value, int) or isinstance(value, bool) for value in numeric_values.values()):
            raise ValueError("policy thresholds must be integers")
        return cls(
            base=base,
            languages=tuple(language.lower() for language in languages),
            depth_limit=numeric_values["depth_limit"],
            inheritance_limit=numeric_values["inheritance_limit"],
            soup_limit=numeric_values["soup_limit"],
            ignored_rules=frozenset(ignored_rules),
            severity_overrides=tuple(sorted(overrides.items())),
        )
