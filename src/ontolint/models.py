"""Stable domain models shared by rule engines, adapters, and reporters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from enum import StrEnum
from typing import Any

type EvidenceValue = str | tuple[str, ...] | tuple[Evidence, ...]
"""One value of a finding's evidence: a term or text, several of them, or nested evidence."""
type Evidence = Mapping[str, EvidenceValue]
"""A backend's structured result behind a finding, keyed by the backend's own field names."""


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
    PATTERN_LIBRARY = "pattern-library"


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
    related: tuple[str, ...] = field(default=(), compare=False)
    """Other terms the finding is about (the rest of a collision), used to place it in modules; never rendered."""
    evidence: Evidence | None = field(default=None, compare=False)
    """The backend's structured result behind the finding, keyed by its own field names; JSON and SARIF only."""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready representation with stable field names (``details`` and ``evidence`` only when set)."""
        data: dict[str, Any] = {f.name: getattr(self, f.name) for f in fields(self)}
        del data["related"]
        if data["details"] is None:
            del data["details"]
        if self.evidence is None:
            del data["evidence"]
        else:
            data["evidence"] = plain_evidence(self.evidence)
        return data


def plain_evidence(evidence: Evidence) -> dict[str, Any]:
    """``evidence`` as JSON values: each mapping a ``dict`` and each tuple a ``list``, in the same key order."""
    return {key: _plain(value) for key, value in evidence.items()}


def _plain(value: EvidenceValue) -> Any:
    if isinstance(value, str):
        return value
    return [item if isinstance(item, str) else plain_evidence(item) for item in value]


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


@dataclass(frozen=True)
class LibraryMember:
    """One ontology of a pattern library (``--pattern-library``): where it is and what its header says."""

    display: str
    """The member file's report path."""
    uri: str
    """The member file's URI (a SARIF artifact)."""
    ontology: str
    """Its ontology IRI."""
    identities: frozenset[str]
    """Its ontology IRI and version IRIs: what an index entry may name it by."""
    names: tuple[str, ...] = ()
    """The names its header gives it (``opla-core:hasPatternName``, ``rdfs:label``, ``dcterms:title`` ...)."""
    references: tuple[tuple[str, str], ...] = ()
    """``(predicate, IRI)`` for every IRI its header names, as an IRI or as a literal spelling one."""


@dataclass(frozen=True)
class PatternLibrary:
    """The member ontologies of a pattern library, whose index is the linted file (rules ``LIB001``-``LIB003``)."""

    directory: str
    members: tuple[LibraryMember, ...] = ()
    unreadable: tuple[str, ...] = ()
    """Report paths of RDF files under the directory that did not parse: the library may be incomplete."""
