"""Public Python API for ontology-quality linting."""

from .ontolint import Finding, Linter, main

__all__ = ["Finding", "Linter", "main"]
