"""Stable domain models shared by rule engines, adapters, and reporters."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum


class Severity(StrEnum):
    """Supported diagnostic severities, ordered by release-gate impact."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ExecutionStatus(StrEnum):
    """Whether a requested rule ran, rather than merely produced no finding."""

    EXECUTED = "executed"
    SKIPPED = "skipped"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


@dataclass(frozen=True)
class Finding:
    """A deterministic, actionable observation made by one linter rule."""

    rule: str
    severity: str
    focus: str
    message: str
    suggestion: str
    confidence: str = "heuristic"

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-ready representation with stable field names."""
        return asdict(self)


@dataclass(frozen=True)
class RuleSpec:
    """Static metadata and execution requirements for an individual rule."""

    rule_id: str
    family: str
    title: str
    severity: Severity
    suggestion: str
    category: str
    backend: str


@dataclass(frozen=True)
class RuleExecution:
    """The outcome of attempting one rule, including non-execution states."""

    rule_id: str
    status: ExecutionStatus
    detail: str = ""
