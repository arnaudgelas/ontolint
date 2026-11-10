"""Shared run-time state handed to every rule family."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import replace

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import RDFS
from rdflib.term import Node

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
    """IRIs that reach one of ``predicates`` through one or more ``rdfs:subPropertyOf`` triples.

    These are the ontology's own definition annotations (``ex:def2 ⊑ ex:def1 ⊑ skos:definition``).
    The walk is iterative and expands each node once, so a cycle or self-loop ends it and its cost is
    bounded by the graph's ``rdfs:subPropertyOf`` triples (which ``max_triples`` caps); rdflib's
    ``transitive_subjects`` recurses once per link instead.  Blank nodes carry the chain but are never
    returned, as only an IRI can be used as a predicate.  The seeds themselves are left out, and the
    result is sorted by IRI.
    """
    seeds: set[Node] = set(predicates)
    seen: set[Node] = set(seeds)
    stack: list[Node] = list(predicates)
    while stack:
        for sub in graph.subjects(RDFS.subPropertyOf, stack.pop()):
            if sub not in seen:
                seen.add(sub)
                stack.append(sub)
    return tuple(sorted((node for node in seen - seeds if isinstance(node, URIRef)), key=str))


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
        self._emitted: dict[tuple[str, str, str], int] = {}  # each seen key's position in ``findings``
        self._blank_ids: dict[BNode, str] = {}
        self._blank_nodes: dict[str, BNode] | None = None  # label -> node, built on first use
        self._blank_pattern: re.Pattern[str] | None = None
        # The configured definition predicates, then every IRI below one of them (sorted).
        seeds = _with_extras(DESCRIPTIONS, policy.extra_definition_predicates)
        self.descriptions: tuple[URIRef, ...] = (*seeds, *_subproperties(graph, seeds))
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

    def add(  # noqa: PLR0913 -- the finding's parts; everything after the message is keyword-only.
        self,
        code: str,
        focus: object,
        message: str,
        *,
        confidence: str = "heuristic",
        related: Iterable[object] = (),
        subject: Iterable[object] = (),
    ) -> None:
        """Record a finding once per ``(rule, focus, message)``; severity and fix come from the specs.

        ``related`` names the other terms a finding is about (the rest of a collision); they place the
        finding in every module involved (``--module-by``) and never change its identity or text.

        ``subject`` is what tells this finding from another of the same rule on the same focus, in a fixed
        order (sorted where it is a set): the baseline identity is the rule, the focus and the subject, so
        a reworded message keeps matching a baseline.  It holds machine values only: IRIs, blank nodes
        (rendered by their stable identity), literals (in N3, with their language or datatype), language
        tags and other keys.  Never prose, counts, ratios, thresholds or labels quoted for readability:
        a measurement that changes is not a new problem.  ``subject=()`` states that the rule reports at
        most one finding per focus.  It is never rendered.  When one message is emitted with several
        subjects, the finding keeps the least of them, so it does not depend on iteration order; a subject
        should still say no more than the message does.
        """
        if confidence not in CONFIDENCES:
            raise ValueError(f"{code}: confidence must be one of {sorted(CONFIDENCES)}, not {confidence!r}")
        text = self._focus_text(focus)
        message = self._message_text(message)
        key = (code, text, message)
        about = tuple(map(self._subject_text, subject))
        if key in self.seen:
            # One finding per message: of the subjects offered for it, keep the least, so the subject does not
            # depend on the order the graph is iterated in (a rule's subject finer than its message).
            index = self._emitted[key]
            # gremlin: pardon[equivalent] replacing an equal subject by itself changes nothing
            if about < self.findings[index].subject:
                self.findings[index] = replace(self.findings[index], subject=about)
            return
        self.seen.add(key)
        self._emitted[key] = len(self.findings)
        others = tuple(dict.fromkeys(t for t in map(self._focus_text, related) if t != text))
        self.findings.append(
            Finding(code, SEVERITY[code], text, message, FIXES[code], confidence, related=others, subject=about)
        )

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

    def _subject_text(self, item: object) -> str:
        """Render one part of a subject: a blank node by its stable identity, a literal in N3, an IRI as is.

        A string is taken as an already rendered key; anything else (a count, say) is refused, because a
        subject names what a finding is about, never how much.
        """
        if isinstance(item, BNode):
            return self._stable_id(item)
        if isinstance(item, Literal):
            return item.n3()
        if isinstance(item, URIRef):
            return str(item) or EMPTY_FOCUS
        if isinstance(item, str):
            return item
        raise TypeError(f"a finding subject holds terms and keys, not {type(item).__name__}: {item!r}")

    def _focus_text(self, focus: object) -> str:
        """Render a focus: blank nodes by stable content identity, the empty IRI as ``<>``."""
        if isinstance(focus, BNode):
            return self._stable_id(focus)
        return str(focus) or EMPTY_FOCUS
