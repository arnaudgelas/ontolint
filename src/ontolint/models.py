"""Stable domain models shared by rule engines, adapters, and reporters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from enum import StrEnum
from typing import Any

from .redaction import redact_userinfo

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
    SET = "set"
    """A finding about several documents of one run together: files, or the named graphs of one file."""


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


class MeasurementKind(StrEnum):
    """What a measurement publishes (:mod:`ontolint.rules.measurements`)."""

    RATIO = "ratio"
    """A numerator and a denominator, never the quotient alone; a mean is the sum over the count."""
    COUNT = "count"
    """One integer."""
    HISTOGRAM = "histogram"
    """How many terms of the population have each value."""


# The only values a rule may report as the confidence of a finding.
CONFIDENCES: frozenset[str] = frozenset({"certain", "heuristic"})


@dataclass(frozen=True)
class Finding:
    """A deterministic, actionable observation made by one linter rule.

    A finding holds no IRI userinfo: every text field, related term, subject part and evidence value is masked
    (:func:`ontolint.redaction.redact_userinfo`) when the finding is made, before anything renders or hashes it.
    """

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
    """The backend's structured result (SHACL001: every SHACL result property ``adapters.shacl`` lists); JSON and
    SARIF carry it in full, text its path, value and nested causes."""
    subject: tuple[str, ...] = field(default=(), compare=False)
    """What the finding is about beyond its rule and focus (terms, predicate, literal, axiom key): its baseline
    identity with them, independent of the message wording; never rendered."""

    def __post_init__(self) -> None:
        for name in ("focus", "message", "suggestion"):
            object.__setattr__(self, name, redact_userinfo(getattr(self, name)))
        if self.details is not None:
            object.__setattr__(self, "details", redact_userinfo(self.details))
        object.__setattr__(self, "related", tuple(map(redact_userinfo, self.related)))
        object.__setattr__(self, "subject", tuple(map(redact_userinfo, self.subject)))
        if self.evidence is not None:
            object.__setattr__(self, "evidence", redacted_evidence(self.evidence))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready representation with stable field names (``details`` and ``evidence`` only when set)."""
        data: dict[str, Any] = {f.name: getattr(self, f.name) for f in fields(self)}
        del data["related"]
        del data["subject"]
        if data["details"] is None:
            del data["details"]
        if self.evidence is None:
            del data["evidence"]
        else:
            data["evidence"] = plain_evidence(self.evidence)
        return data


_MEASURED = ("numerator", "denominator", "value", "buckets", "by_namespace")
"""The value fields of a :class:`Measurement`; one that could not be taken has none of them."""
_FIELDS: dict[MeasurementKind, tuple[set[str], set[str]]] = {
    MeasurementKind.RATIO: ({"numerator", "denominator"}, {"by_namespace"}),
    MeasurementKind.COUNT: ({"value"}, set()),
    MeasurementKind.HISTOGRAM: (set(), {"buckets"}),  # an empty population has no bucket
}
"""Per kind, the value fields a measurement that was taken must have, and those it may have."""


@dataclass(frozen=True)
class Measurement:
    """One published measurement (``--measurements``): integers and names only, never a term or a float.

    A ratio has a ``numerator`` and a ``denominator`` (and, for some, ``by_namespace``, which splits the
    numerator), a count a ``value``, a histogram its ``buckets`` (``(value, terms)`` pairs, ascending).  A
    measurement that could not be taken has a ``reason`` and none of these.  The reason and the namespaces are
    masked (:func:`ontolint.redaction.redact_userinfo`), and a record of any other shape is refused.
    """

    id: str
    definition_version: int
    kind: MeasurementKind
    population: str
    numerator: int | None = None
    denominator: int | None = None
    value: int | None = None
    buckets: tuple[tuple[int, int], ...] = ()
    by_namespace: tuple[tuple[str, int], ...] | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", MeasurementKind(self.kind))
        if self.reason is not None:
            object.__setattr__(self, "reason", redact_userinfo(self.reason))
        if self.by_namespace is not None:
            object.__setattr__(self, "by_namespace", tuple((redact_userinfo(ns), n) for ns, n in self.by_namespace))
        present = {name for name in _MEASURED if getattr(self, name) not in (None, ())}
        required, optional = _FIELDS[self.kind] if self.reason is None else (set[str](), set[str]())
        if not required <= present <= required | optional:
            raise ValueError(f"{self.id}: a {self.kind} measurement cannot have the fields {sorted(present)}")
        self._check_shape()
        counts = [self.numerator, self.denominator, self.value, *(n for pair in self.buckets for n in pair)]
        if any(n is not None and n < 0 for n in [*counts, *(n for _ns, n in self.by_namespace or ())]):
            raise ValueError(f"{self.id}: a measurement counts, so it is never negative")

    def _check_shape(self) -> None:
        """Refuse the types and invariants the published schema relies on (integers, ascending buckets, a split)."""

        def whole(n: object) -> bool:
            return isinstance(n, int) and not isinstance(n, bool)

        if not (isinstance(self.id, str) and self.id and isinstance(self.population, str) and self.population):
            raise ValueError("a measurement has a non-empty id and population")
        if not whole(self.definition_version) or self.definition_version < 1:
            raise ValueError(f"{self.id}: a definition version is a positive integer")
        numbers: list[object] = [n for n in (self.numerator, self.denominator, self.value) if n is not None]
        numbers += [n for pair in self.buckets for n in pair]
        by_namespace = self.by_namespace or ()
        if not all(whole(n) for n in numbers) or not all(whole(n) for _ns, n in by_namespace):
            raise ValueError(f"{self.id}: a measurement counts, so its numbers are integers")
        if any(a >= b for (a, _), (b, _) in zip(self.buckets, self.buckets[1:], strict=False)):
            raise ValueError(f"{self.id}: histogram buckets are ascending and distinct")
        if self.by_namespace is not None and sum(n for _ns, n in by_namespace) != self.numerator:
            raise ValueError(f"{self.id}: by_namespace splits the numerator, so it sums to it")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready representation: the identity, then only the fields this measurement has."""
        data: dict[str, Any] = {
            "id": self.id,
            "definition_version": self.definition_version,
            "kind": self.kind.value,
            "population": self.population,
        }
        if self.reason is not None:
            data["reason"] = self.reason
        elif self.kind is MeasurementKind.RATIO:
            data["numerator"], data["denominator"] = self.numerator, self.denominator
            if self.by_namespace is not None:
                data["by_namespace"] = [{"namespace": ns, "count": n} for ns, n in self.by_namespace]
        elif self.kind is MeasurementKind.COUNT:
            data["value"] = self.value
        else:
            data["buckets"] = [{"value": value, "count": n} for value, n in self.buckets]
        return data


PARTITIONS = ("file", "graph", "module")
"""What a :class:`MeasurementPartition` is of, in the order a report lists them."""


@dataclass(frozen=True)
class MeasurementPartition:
    """The measurements of the owned terms placed in one closure file, named graph or in-file module.

    A term is placed exactly where a finding about it is.  ``path`` is the report path of the file (for a graph,
    the file holding it; none for a module) and ``name`` the graph's or module's name (none for a file); the
    name is masked (:func:`ontolint.redaction.redact_userinfo`).
    """

    by: str
    path: str | None
    name: str | None
    measurements: tuple[Measurement, ...]

    def __post_init__(self) -> None:
        if self.by not in PARTITIONS:
            raise ValueError(f"a partition is by one of {PARTITIONS}, not {self.by!r}")
        if self.name is not None:
            object.__setattr__(self, "name", redact_userinfo(self.name))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready representation: ``by``, then ``path`` and ``name`` when set, then the measurements."""
        return {
            "by": self.by,
            **({"path": self.path} if self.path is not None else {}),
            **({"name": self.name} if self.name is not None else {}),
            "measurements": [m.to_dict() for m in self.measurements],
        }


def redacted_evidence(evidence: Evidence) -> Evidence:
    """``evidence`` with every userinfo masked, in the same key order and shape."""
    return {key: _redacted(value) for key, value in evidence.items()}


def _redacted(value: EvidenceValue) -> EvidenceValue:
    if isinstance(value, str):
        return redact_userinfo(value)
    if all(isinstance(item, str) for item in value):
        return tuple(redact_userinfo(item) for item in value if isinstance(item, str))
    return tuple(redacted_evidence(item) for item in value if not isinstance(item, str))


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

    ``detail`` is the reason for every non-executed status and is never empty for them; it holds no userinfo.
    """

    rule_id: str
    status: ExecutionStatus
    detail: str = ""

    def __post_init__(self) -> None:
        # A failed rule's detail is an exception's text, which may quote an IRI (see :mod:`ontolint.redaction`).
        object.__setattr__(self, "detail", redact_userinfo(self.detail))


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


SHARED_SCOPES = ("inputs", "closure", "import-dir", "graphs")
"""Where a :class:`SharedIdentity` was found: among the inputs of one run, the files of one import closure, the
candidates of one ``--import-dir`` for an import, or the named graphs of one dataset file."""


@dataclass(frozen=True)
class SharedIdentity:
    """An ontology or version IRI that several documents of one run declare (rules ``ONT007`` and ``ONT008``).

    The CLI finds these across the set of documents of a run (:mod:`ontolint.declarations`) and hands each
    linted file the ones reported on it, as ``Policy.shared_identities``.
    """

    iri: str
    kind: str
    """``ontology`` (an ``owl:Ontology`` subject) or ``version`` (an ``owl:versionIRI`` of one)."""
    scope: str
    """One of :data:`SHARED_SCOPES`."""
    members: tuple[str, ...]
    """The documents that declare it, in the order ontolint reads them (report paths, or graph names for
    ``graphs``); there are at least two.  For ``import-dir`` the first is the file the import resolved to."""
    identical: bool
    """Whether every member is the same RDF graph (:func:`ontolint.datasets.same_content`)."""
    where: str = ""
    """The dataset file (``graphs``) or the ``--import-dir`` options (``import-dir``) holding the members; else
    empty.  Only the message names it: like the members, it is a path, so it is not part of the identity."""
    unloaded: tuple[tuple[str, str], ...] = ()
    """For ``closure``: ``(import IRI, member)`` for each member the closure did not load, because a file it had
    already loaded declares the IRI the member is imported by."""


@dataclass(frozen=True)
class PatternLibrary:
    """The member ontologies of a pattern library, whose index is the linted file (rules ``LIB001``-``LIB003``)."""

    directory: str
    members: tuple[LibraryMember, ...] = ()
    unreadable: tuple[str, ...] = ()
    """Report paths of RDF files under the directory that did not parse: the library may be incomplete."""
