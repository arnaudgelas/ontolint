"""SKOS concept-scheme rules: SKOS001-SKOS006."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from rdflib import Literal
from rdflib.namespace import SKOS
from rdflib.term import Node

from ontolint.graph import strongly_connected_components
from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity

from .support import directed_edges

if TYPE_CHECKING:
    from .runtime import RuleContext


SPECS: tuple[RuleSpec, ...] = (
    RuleSpec(
        "SKOS001",
        "SKOS",
        "Multiple preferred labels in one language",
        Severity.ERROR,
        "Keep only one skos:prefLabel per language tag for a given resource.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "skos",
    ),
    RuleSpec(
        "SKOS002",
        "SKOS",
        "Same literal in disjoint SKOS label properties",
        Severity.ERROR,
        "Do not reuse the same literal across prefLabel, altLabel and hiddenLabel of one resource.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "skos",
    ),
    RuleSpec(
        "SKOS003",
        "SKOS",
        "Cycle in skos:broader hierarchy",
        Severity.INFO,
        "Inspect hierarchical cycles; SKOS does not universally prohibit them.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.VOCABULARY,
        "skos",
    ),
    RuleSpec(
        "SKOS004",
        "SKOS",
        "Concept without preferred label",
        Severity.INFO,
        "Give a concept a preferred label in your supported language(s).",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "skos",
    ),
    RuleSpec(
        "SKOS005",
        "SKOS",
        "Concept not in a concept scheme",
        Severity.WARNING,
        "Use skos:Concept with skos:inScheme and an appropriate scheme policy.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "skos",
    ),
    RuleSpec(
        "SKOS006",
        "SKOS",
        "Top concept with a broader concept",
        Severity.INFO,
        "Review whether a scheme top concept should also have a broader concept.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "skos",
    ),
)


def run(ctx: RuleContext) -> None:
    """Run all SKOS rules."""
    _concept_labels(ctx)
    _label_overlaps(ctx)
    _broader_cycles(ctx)
    _top_concepts(ctx)


def _concept_labels(ctx: RuleContext) -> None:
    g = ctx.g
    for c in ctx.concepts:
        by_lang: defaultdict[str, list[Literal]] = defaultdict(list)
        for label in g.objects(c, SKOS.prefLabel):
            if isinstance(label, Literal):
                by_lang[label.language or "und"].append(label)
        for language, labels in by_lang.items():
            if len(labels) > 1:
                ctx.add("SKOS001", c, f"{len(labels)} prefLabels in language {language}.", confidence="certain")
        if not by_lang:
            ctx.add("SKOS004", c, "Concept has no skos:prefLabel.")
        if (c, SKOS.inScheme, None) not in g:
            ctx.add("SKOS005", c, "Concept is not explicitly in a scheme.")


def _label_overlaps(ctx: RuleContext) -> None:
    labelled_resources: set[Node] = set(ctx.concepts) | set(ctx.g.subjects(SKOS.prefLabel, None))
    for resource in labelled_resources:
        sets = [set(ctx.g.objects(resource, p)) for p in (SKOS.prefLabel, SKOS.altLabel, SKOS.hiddenLabel)]
        if (sets[0] & sets[1]) or (sets[0] & sets[2]) or (sets[1] & sets[2]):
            ctx.add(
                "SKOS002",
                resource,
                "Same literal appears in multiple disjoint SKOS label properties.",
                confidence="certain",
            )


def _broader_cycles(ctx: RuleContext) -> None:
    broader_edges = directed_edges(ctx.g, SKOS.broader, ctx.concepts)
    for component in strongly_connected_components(ctx.concepts, broader_edges):
        if len(component) > 1 or any((c, c) in broader_edges for c in component):
            ctx.add(
                "SKOS003",
                sorted(component, key=str)[0],
                "SKOS broader cycle: " + ", ".join(map(str, sorted(component, key=str))),
            )


def _top_concepts(ctx: RuleContext) -> None:
    for concept, scheme in ctx.g.subject_objects(SKOS.topConceptOf):
        if (concept, SKOS.broader, None) in ctx.g:
            ctx.add("SKOS006", concept, f"Top concept of {scheme} also has an asserted broader concept.")
