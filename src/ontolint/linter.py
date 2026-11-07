"""Public :class:`Linter` facade over the rule engine."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Set
from dataclasses import replace

from rdflib import Graph, URIRef
from rdflib.term import Identifier, Node

from . import engine
from .graph import reachable as graph_reachable
from .graph import strongly_connected_components
from .models import Finding, RunResult
from .policy import DEFAULT_DEPTH_LIMIT, DEFAULT_INHERITANCE_LIMIT, DEFAULT_SOUP_LIMIT, Policy
from .rules import support


class Linter:
    """Lint one RDF graph (and optionally a SHACL shapes graph) with graph-local rules."""

    def __init__(  # noqa: PLR0913 -- policy thresholds are independently configurable.
        self,
        graph: Graph,
        shapes: Graph | None = None,
        *,
        base: str | None = None,
        languages: tuple[str, ...] = (),
        depth_limit: int = DEFAULT_DEPTH_LIMIT,
        inheritance_limit: int = DEFAULT_INHERITANCE_LIMIT,
        soup_limit: int = DEFAULT_SOUP_LIMIT,
        policy: Policy | None = None,
    ):
        self.g = graph
        self.shapes = shapes
        self.base = base
        self.languages = tuple(x.lower() for x in languages)
        self.depth_limit = depth_limit
        self.inheritance_limit = inheritance_limit
        self.soup_limit = soup_limit
        built = Policy(
            base=base,
            languages=self.languages,
            depth_limit=depth_limit,
            inheritance_limit=inheritance_limit,
            soup_limit=soup_limit,
        )
        if policy is not None:  # a full policy (extra thresholds, annotations ...); explicit base/languages win
            built = replace(
                policy, base=base if base is not None else policy.base, languages=self.languages or policy.languages
            )
        self.rule_context = engine.build_context(graph, shapes, built)
        self.context = self.rule_context.context
        self.issues: list[Finding] = self.rule_context.findings
        self.seen: set[tuple[str, str, str]] = self.rule_context.seen
        self.ontologies = self.context.ontologies
        self.classes = self.context.classes
        self.properties = self.context.properties
        self.concepts = self.context.concepts
        self.terms = self.context.terms

    def local(self, node: object) -> bool:
        if self.base:
            return support.is_local(self.base, node)
        return self.rule_context.local(node)

    def add(self, code: str, focus: object, message: str, *, confidence: str = "heuristic") -> None:
        self.rule_context.add(code, focus, message, confidence=confidence)

    def run(self) -> list[Finding]:
        return engine.run_rules(self.rule_context)

    def execute(self, selectors: Iterable[str] = (), *, robot: engine.RobotRequest | None = None) -> RunResult:
        """Run the selected rules (all by default) and report findings with per-rule execution status."""
        return engine.execute(self.rule_context, selectors, robot=robot)

    @staticmethod
    def local_name(iri: URIRef) -> str:
        return support.local_name(iri)

    @staticmethod
    def directed_edges(g: Graph, predicate: Identifier, allowed: Set[URIRef]) -> set[tuple[URIRef, URIRef]]:
        return support.directed_edges(g, predicate, allowed)

    @staticmethod
    def components(nodes: Iterable[URIRef], edges: Iterable[tuple[URIRef, URIRef]]) -> list[set[URIRef]]:
        """Compatibility wrapper around the iterative, stack-safe implementation."""
        return strongly_connected_components(nodes, edges)

    @staticmethod
    def reachable(
        adj: Mapping[URIRef, set[URIRef]],
        source: URIRef,
        target: URIRef,
        *,
        ignore: tuple[URIRef, URIRef] | None = None,
    ) -> bool:
        return graph_reachable(adj, source, target, ignore=ignore)

    @staticmethod
    def list_items(g: Graph, head: Node, *, limit: int = 500) -> list[Node] | None:
        return support.list_items(g, head, limit=limit)
