"""Shared run-time state handed to every rule family."""

from __future__ import annotations

from rdflib import Graph, URIRef

from ontolint.context import GraphContext
from ontolint.models import Finding
from ontolint.policy import Policy

from .specs import FIXES, SEVERITY
from .support import DESCRIPTIONS, LABELS


def _with_extras(defaults: tuple[URIRef, ...], extras: tuple[str, ...]) -> tuple[URIRef, ...]:
    """Return the default predicates followed by the configured extra ones, without duplicates."""
    return tuple(dict.fromkeys((*defaults, *(URIRef(extra) for extra in extras))))


class RuleContext:
    """Graphs, policy, indexed facts, and the de-duplicating finding emitter for one lint run."""

    def __init__(self, graph: Graph, shapes: Graph | None, policy: Policy, context: GraphContext) -> None:
        self.g = graph
        self.shapes = shapes
        self.policy = policy
        self.context = context
        self.findings: list[Finding] = []
        self.seen: set[tuple[str, str, str]] = set()
        self.descriptions: tuple[URIRef, ...] = _with_extras(DESCRIPTIONS, policy.extra_definition_predicates)
        self.labels: tuple[URIRef, ...] = _with_extras(LABELS, policy.extra_label_predicates)

    @property
    def ontologies(self) -> frozenset[URIRef]:
        return self.context.ontologies

    @property
    def classes(self) -> frozenset[URIRef]:
        return self.context.classes

    @property
    def properties(self) -> frozenset[URIRef]:
        return self.context.properties

    @property
    def concepts(self) -> frozenset[URIRef]:
        return self.context.concepts

    @property
    def terms(self) -> frozenset[URIRef]:
        return self.context.terms

    def local(self, node: object) -> bool:
        """Return whether ``node`` is owned by the linted ontology (see :mod:`ontolint.ownership`)."""
        return self.context.ownership.owns(node)

    def add(self, code: str, focus: object, message: str, *, confidence: str = "heuristic") -> None:
        """Record a finding once per ``(rule, focus, message)``; severity and fix come from the specs."""
        key = (code, str(focus), message)
        if key not in self.seen:
            self.seen.add(key)
            self.findings.append(Finding(code, SEVERITY[code], str(focus), message, FIXES[code], confidence))
