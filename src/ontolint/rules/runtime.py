"""Shared run-time state handed to every rule family."""

from __future__ import annotations

from rdflib import Graph, URIRef

from ontolint.context import GraphContext
from ontolint.models import Finding
from ontolint.policy import Policy

from .specs import FIXES, SEVERITY
from .support import is_local


class RuleContext:
    """Graphs, policy, indexed facts, and the de-duplicating finding emitter for one lint run."""

    def __init__(self, graph: Graph, shapes: Graph | None, policy: Policy, context: GraphContext) -> None:
        self.g = graph
        self.shapes = shapes
        self.policy = policy
        self.context = context
        self.findings: list[Finding] = []
        self.seen: set[tuple[str, str, str]] = set()

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
        """Return whether ``node`` belongs to the policy's base namespace (all IRIs if unset)."""
        return is_local(self.policy.base, node)

    def add(self, code: str, focus: object, message: str, *, confidence: str = "heuristic") -> None:
        """Record a finding once per ``(rule, focus, message)``; severity and fix come from the specs."""
        key = (code, str(focus), message)
        if key not in self.seen:
            self.seen.add(key)
            self.findings.append(Finding(code, SEVERITY[code], str(focus), message, FIXES[code], confidence))
