"""Public Python API for ontology-quality linting."""

from .cli import main
from .linter import Linter
from .models import Finding

__all__ = ["Finding", "Linter", "main"]
