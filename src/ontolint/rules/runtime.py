"""Shared run-time state handed to every rule family."""

from __future__ import annotations

import re
from collections.abc import Iterable

from rdflib import BNode, Graph, URIRef
from rdflib.namespace import RDFS

from ontolint.context import GraphContext
from ontolint.models import CONFIDENCES, Finding
from ontolint.policy import Policy

from .specs import FIXES, SEVERITY
from .support import DESCRIPTIONS, LABELS, stable_blank_id

EMPTY_FOCUS = "<>"


def _with_extras(defaults: tuple[URIRef, ...], extras: tuple[str, ...]) -> tuple[URIRef, ...]:
    """Return the default predicates followed by the configured extra ones, without duplicates."""
    return tuple(dict.fromkeys((*defaults, *(URIRef(extra) for extra in extras))))


def _subproperties(graph: Graph, predicates: tuple[URIRef, ...]) -> tuple[URIRef, ...]:
    """Predicates the graph declares ``rdfs:subPropertyOf`` one of ``predicates``: local definition annotations."""
    found = {s for p in predicates for s in graph.subjects(RDFS.subPropertyOf, p) if isinstance(s, URIRef)}
    return tuple(sorted(found - set(predicates), key=str))


class RuleContext:
    """Graphs, policy, indexed facts, and the de-duplicating finding emitter for one lint run."""

    def __init__(self, graph: Graph, shapes: Graph | None, policy: Policy, context: GraphContext) -> None:
        self.g = graph
        self.shapes = shapes
        # SHACL-only background (stage 4 of the import closure): the ontology the shapes import, merged
        # into the data graph for validation but never judged by the term rules.
        self.shacl_background: Graph | None = None
        self.policy = policy
        self.context = context
        self.findings: list[Finding] = []
        self.seen: set[tuple[str, str, str]] = set()
        self._blank_ids: dict[BNode, str] = {}
        self._blank_nodes: dict[str, BNode] | None = None  # label -> node, built on first use
        self._blank_pattern: re.Pattern[str] | None = None
        self.descriptions: tuple[URIRef, ...] = _with_extras(
            (*DESCRIPTIONS, *_subproperties(graph, DESCRIPTIONS)), policy.extra_definition_predicates
        )
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

    def add(
        self, code: str, focus: object, message: str, *, confidence: str = "heuristic", related: Iterable[object] = ()
    ) -> None:
        """Record a finding once per ``(rule, focus, message)``; severity and fix come from the specs.

        ``related`` names the other terms a finding is about (the rest of a collision); they place the
        finding in every module involved (``--module-by``) and never change its identity or text.
        """
        if confidence not in CONFIDENCES:
            raise ValueError(f"{code}: confidence must be one of {sorted(CONFIDENCES)}, not {confidence!r}")
        text = self._focus_text(focus)
        message = self._message_text(message)
        key = (code, text, message)
        if key not in self.seen:
            self.seen.add(key)
            others = tuple(dict.fromkeys(t for t in map(self._focus_text, related) if t != text))
            self.findings.append(Finding(code, SEVERITY[code], text, message, FIXES[code], confidence, related=others))

    def _stable_id(self, node: BNode) -> str:
        if node not in self._blank_ids:
            self._blank_ids[node] = stable_blank_id(self.g, node)
        return self._blank_ids[node]

    def _message_text(self, message: str) -> str:
        """Replace parser-assigned blank-node labels inside ``message`` by their stable identity.

        A label after the ``_:`` prefix is always replaced. A bare label is replaced only when it contains a
        digit, as generated labels do, so a hand-written label such as ``a`` cannot rewrite an ordinary word
        of the message.
        """
        if self._blank_nodes is None:
            self._blank_nodes = {str(n): n for t in self.g for n in (t[0], t[2]) if isinstance(n, BNode)}
            labels = sorted(self._blank_nodes, key=lambda label: (-len(label), label))
            bare = [label for label in labels if any(c.isdigit() for c in label)]
            if labels:
                prefixed = "|".join(re.escape(label) for label in labels)
                alone = "|".join(re.escape(label) for label in bare) or "(?!)"
                self._blank_pattern = re.compile(
                    rf"(?<![\w/#:-])(?:_:(?P<prefixed>{prefixed})|(?P<bare>{alone}))(?![\w/#:-]|\.\w)"
                )
        if self._blank_pattern is None:
            return message
        nodes = self._blank_nodes
        return self._blank_pattern.sub(
            lambda match: self._stable_id(nodes[match.group("prefixed") or match.group("bare")]), message
        )

    def _focus_text(self, focus: object) -> str:
        """Render a focus: blank nodes by stable content identity, the empty IRI as ``<>``."""
        if isinstance(focus, BNode):
            return self._stable_id(focus)
        return str(focus) or EMPTY_FOCUS
