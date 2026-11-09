"""Stable domain models shared by rule engines, adapters, and reporters."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum


class Severity(StrEnum):
    """Supported diagnostic severities, ordered by release-gate impact."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class RuleBackend(StrEnum):
    """Stable identifiers for the component that evaluates a rule."""

    RDFLIB = "rdflib"
    PYSHACL = "pyshacl"
    ROBOT_DOCKER = "robot-docker"
    CLI = "cli"


class RuleScope(StrEnum):
    """The kind of artefact a rule's findings are about."""

    ONTOLOGY = "ontology"
    VOCABULARY = "vocabulary"
    TERM = "term"
    AXIOM = "axiom"
    SHAPES = "shapes"
    INPUT = "input"
    TOOL = "tool"


class Requirement(StrEnum):
    """Optional run input a rule needs before it can be evaluated."""

    NONE = "none"
    SHAPES = "shapes"
    OWL_PROFILE = "owl-profile"


class CatalogueStatus(StrEnum):
    """Planning state of a catalogue rule (not a runtime outcome; see ExecutionStatus)."""

    IMPLEMENTED = "implemented"
    PROPOSED = "proposed"


class ExecutionStatus(StrEnum):
    """Whether a requested rule ran, rather than merely produced no finding."""

    EXECUTED = "executed"
    SKIPPED = "skipped"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


# The only values a rule may report as the confidence of a finding.
CONFIDENCES: frozenset[str] = frozenset({"certain", "heuristic"})


@dataclass(frozen=True)
class Finding:
    """A deterministic, actionable observation made by one linter rule."""

    rule: str
    severity: str
    focus: str
    message: str
    suggestion: str
    confidence: str = "heuristic"
    details: str | None = field(default=None, compare=False)
    """Full tool output behind a summarised message (ROBOT's profile report); JSON and SARIF only."""

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-ready representation with stable field names (``details`` only when set)."""
        data = asdict(self)
        if data["details"] is None:
            del data["details"]
        return data


@dataclass(frozen=True)
class SourceFacts:
    """What the loader read from a file's text that its RDF graph does not keep."""

    comment_license: str | None = None
    """The licence an ``SPDX-License-Identifier:`` comment names, if any."""
    declared_prefixes: tuple[tuple[str, str], ...] | None = None
    """The ``(prefix, namespace)`` pairs the file declares; ``None`` when unknown (a graph not read by ontolint),
    ``()`` for a syntax whose prefixes are not the author's own (a JSON-LD ``@context``)."""


@dataclass(frozen=True)
class RuleSpec:
    """Static metadata and execution requirements for an individual rule."""

    rule_id: str
    family: str
    title: str
    severity: Severity
    suggestion: str
    category: str
    backend: RuleBackend
    scope: RuleScope
    module: str
    requires: Requirement = Requirement.NONE


@dataclass(frozen=True)
class RuleExecution:
    """The outcome of attempting one rule, including non-execution states.

    ``detail`` is the reason for every non-executed status and is never empty for them.
    """

    rule_id: str
    status: ExecutionStatus
    detail: str = ""


@dataclass(frozen=True)
class RunResult:
    """Findings plus one execution record per selected rule for a single lint run."""

    findings: tuple[Finding, ...]
    executions: tuple[RuleExecution, ...]

    def with_status(self, status: ExecutionStatus) -> tuple[RuleExecution, ...]:
        """Return the executions that ended in ``status``."""
        return tuple(x for x in self.executions if x.status == status)
