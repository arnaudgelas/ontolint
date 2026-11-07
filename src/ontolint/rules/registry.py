"""Small, deterministic built-in registry; external plugins are intentionally deferred."""

from __future__ import annotations

from collections.abc import Iterable

from ontolint.models import RuleSpec

from .builtin import RULE_SPECS


class UnknownSelectorError(ValueError):
    """Raised when a rule selector matches neither a rule identifier nor a family."""

    def __init__(self, selectors: Iterable[str]) -> None:
        self.selectors = tuple(sorted(selectors))
        super().__init__(f"unknown rule selector(s): {', '.join(self.selectors)}")


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

    def get(self, rule_id: str) -> RuleSpec:
        """Return the specification for ``rule_id`` or raise :class:`KeyError`."""
        return self._specs[rule_id]

    def __contains__(self, rule_id: object) -> bool:
        return rule_id in self._specs

    def __len__(self) -> int:
        return len(self._specs)

    def all(self) -> tuple[RuleSpec, ...]:
        """Return specifications in deterministic identifier order."""
        return tuple(self._specs[rule_id] for rule_id in sorted(self._specs))

    def select(self, selectors: Iterable[str]) -> tuple[RuleSpec, ...]:
        """Select rule identifiers or complete families (case-insensitive); no selectors selects everything.

        Raises :class:`UnknownSelectorError` for selectors that match nothing, so a typo can
        never silently turn into "nothing to check".
        """
        requested = {selector.strip().upper() for selector in selectors}
        if not requested:
            return self.all()
        families = {spec.family.upper() for spec in self._specs.values()}
        unknown = requested - self._specs.keys() - families
        if unknown:
            raise UnknownSelectorError(unknown)
        return tuple(spec for spec in self.all() if spec.rule_id in requested or spec.family.upper() in requested)


def default_registry() -> RuleRegistry:
    """Return a fresh registry holding every implemented built-in rule."""
    return RuleRegistry(RULE_SPECS)
