"""Built-in rule metadata and execution registry."""

from .registry import RuleRegistry, UnknownSelectorError, default_registry

__all__ = ["RuleRegistry", "UnknownSelectorError", "default_registry"]
