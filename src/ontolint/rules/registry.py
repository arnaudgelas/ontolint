"""Small, deterministic built-in registry; external plugins are intentionally deferred."""

from __future__ import annotations

from collections.abc import Iterable

from ontolint.models import RuleSpec


class RuleRegistry:
    """Store unique built-in specifications and select them by ID or family."""

    def __init__(self, specs: Iterable[RuleSpec] = ()) -> None:
        self._specs: dict[str, RuleSpec] = {}
        for spec in specs:
            self.register(spec)

    def register(self, spec: RuleSpec) -> None:
        """Register a specification, rejecting accidental identifier reuse."""
        if spec.rule_id in self._specs:
            raise ValueError(f"duplicate rule identifier: {spec.rule_id}")
        self._specs[spec.rule_id] = spec

    def all(self) -> tuple[RuleSpec, ...]:
        """Return specifications in deterministic identifier order."""
        return tuple(self._specs[rule_id] for rule_id in sorted(self._specs))

    def select(self, selectors: Iterable[str]) -> tuple[RuleSpec, ...]:
        """Select explicit rule identifiers or complete rule-family prefixes."""
        requested = {selector.upper() for selector in selectors}
        if not requested:
            return self.all()
        return tuple(spec for spec in self.all() if spec.rule_id in requested or spec.family.upper() in requested)
