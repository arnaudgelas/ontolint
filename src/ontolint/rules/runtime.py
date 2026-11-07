"""Shared run-time state handed to every rule family."""

from __future__ import annotations

import re

from rdflib import BNode, Graph, URIRef

from ontolint.context import GraphContext
from ontolint.models import Finding
from ontolint.policy import Policy

from .specs import FIXES, SEVERITY
from .support import DESCRIPTIONS, LABELS, stable_blank_id

EMPTY_FOCUS = "<>"


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
        self._blank_ids: dict[BNode, str] = {}
        self._blank_nodes: dict[str, BNode] | None = None  # label -> node, built on first use
        self._blank_pattern: re.Pattern[str] | None = None
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
        text = self._focus_text(focus)
        message = self._message_text(message)
        key = (code, text, message)
        if key not in self.seen:
            self.seen.add(key)
            self.findings.append(Finding(code, SEVERITY[code], text, message, FIXES[code], confidence))

    def _stable_id(self, node: BNode) -> str:
        if node not in self._blank_ids:
            self._blank_ids[node] = stable_blank_id(self.g, node)
        return self._blank_ids[node]

    def _message_text(self, message: str) -> str:
        """Replace parser-assigned blank-node labels inside ``message`` by their stable identity."""
        if self._blank_nodes is None:
            self._blank_nodes = {str(n): n for t in self.g for n in (t[0], t[2]) if isinstance(n, BNode)}
            labels = sorted(self._blank_nodes, key=lambda label: (-len(label), label))
            if labels:
                alternatives = "|".join(re.escape(label) for label in labels)
                self._blank_pattern = re.compile(rf"(?<![\w/#:-])({alternatives})(?![\w/#:-]|\.\w)")
        if self._blank_pattern is None:
            return message
        nodes = self._blank_nodes
        return self._blank_pattern.sub(lambda match: self._stable_id(nodes[match.group(1)]), message)

    def _focus_text(self, focus: object) -> str:
        """Render a focus: blank nodes by stable content identity, the empty IRI as ``<>``."""
        if isinstance(focus, BNode):
            return self._stable_id(focus)
        return str(focus) or EMPTY_FOCUS
