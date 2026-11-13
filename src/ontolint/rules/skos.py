"""SKOS concept-scheme rules: SKOS001-SKOS006.

All rules read asserted triples only.  "Integrity condition Sn" refers to the SKOS Reference (W3C
Recommendation, 18 August 2009).  Specifications of the error rules:

* **SKOS001.** Scope: the owned resources explicitly typed ``skos:Concept`` (``ctx.concepts``; no
  subclass typing).  Condition: two or more distinct literal values of ``skos:prefLabel`` share a
  language tag.  Tags compare case-insensitively (``@en`` and ``@EN`` are one tag, as in RDF 1.1), and
  untagged labels (plain or ``xsd:string``) form one group reported as ``und``; an explicit ``@und`` tag
  joins that group.  Literals are compared as RDF 1.1 terms: ``"a"`` equals ``"a"^^xsd:string``, and
  ``"a"@en`` equals ``"a"@EN``, so a repeated label is not counted twice.  Other datatypes count as
  untagged labels (SKOS013 reports them).  Exclusions: non-literal values; resources that are not owned
  concepts (a scheme or an ``owl:Class`` with two prefLabels is not checked).  One finding per concept
  and language.  Severity error, confidence certain: the triples violate integrity condition S14.
* **SKOS002.** Scope: the owned concepts plus every resource that is the subject of
  ``skos:prefLabel``, ``skos:altLabel`` or ``skos:hiddenLabel`` and is either an owned IRI or a blank
  node.  Condition: the same literal is a value of two or three of those properties of one resource.
  Literals compare as RDF 1.1 terms: lexical form and language tag (case-insensitively) must both match,
  ``"a"`` equals ``"a"^^xsd:string``, but ``"a"`` and ``"a"@en`` differ.  Exclusions: same text with a
  different language tag; non-owned IRIs; sub-properties of the label properties (not entailed).  One
  finding per resource and literal.  Severity error, confidence certain: the triples violate integrity
  condition S13 (the three label properties are pairwise disjoint).
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from rdflib import Literal, URIRef
from rdflib.namespace import OWL, SKOS, XSD
from rdflib.term import Node

from ontolint.graph import strongly_connected_components
from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity

from .support import directed_edges, quoted_text, value_text

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
        # Language tags compare case-insensitively (RDF 1.1, BCP 47); an untagged label is in "und".
        by_lang: defaultdict[str, set[Literal]] = defaultdict(set)
        spellings: defaultdict[str, set[str]] = defaultdict(set)
        for label in g.objects(c, SKOS.prefLabel):
            if isinstance(label, Literal):
                tag = label.language or "und"
                by_lang[tag.lower()].add(_plain(label))
                spellings[tag.lower()].add(tag)
        for language, labels in by_lang.items():
            if len(labels) > 1:
                # A tag written one way is reported as written; mixed spellings are reported in lower case.
                tags = spellings[language]
                shown = next(iter(tags)) if len(tags) == 1 else language
                ctx.add(
                    "SKOS001",
                    c,
                    f"{len(labels)} prefLabels in language {shown}.",
                    confidence="certain",
                    subject=(language,),
                )
        if not by_lang and _needs_label(ctx, c):
            ctx.add("SKOS004", c, "Concept has no skos:prefLabel.")
        if (c, SKOS.inScheme, None) not in g:
            ctx.add("SKOS005", c, "Concept is not explicitly in a scheme.")


def _plain[T: Node](node: T) -> T | Literal:
    """``node`` with an ``xsd:string`` datatype dropped: in RDF 1.1 ``"a"`` and ``"a"^^xsd:string`` are one literal."""
    if isinstance(node, Literal) and node.datatype == XSD.string:
        return Literal(str(node))
    return node


def _needs_label(ctx: RuleContext, concept: URIRef) -> bool:
    """Return whether an unlabelled concept is a defect: retired concepts and rdfs:label users are exempt."""
    g = ctx.g
    if (concept, OWL.deprecated, Literal(True)) in g or (concept, SKOS.historyNote, None) in g:
        return False
    return not any(isinstance(o, Literal) for p in ctx.labels for o in g.objects(concept, p))


def _label_overlaps(ctx: RuleContext) -> None:
    properties = (SKOS.prefLabel, SKOS.altLabel, SKOS.hiddenLabel)
    labelled_resources: set[Node] = set(ctx.concepts)
    for p in properties:
        labelled_resources.update(s for s in ctx.g.subjects(p, None) if not isinstance(s, URIRef) or ctx.local(s))
    for resource in sorted(labelled_resources, key=str):
        holders: defaultdict[Node, list[str]] = defaultdict(list)
        for p in properties:
            for value in {_plain(o) for o in ctx.g.objects(resource, p)}:
                holders[value].append("skos:" + p.removeprefix(str(SKOS)))
        for value, names in sorted(
            holders.items(), key=lambda item: (str(item[0]), str(getattr(item[0], "language", "")))
        ):
            if len(names) > 1:
                language = getattr(value, "language", None) or "no language"
                ctx.add(
                    "SKOS002",
                    resource,
                    f"Literal {quoted_text(value, 60)} ({language}) appears in {' and '.join(names)}.",
                    confidence="certain",
                    subject=(value,),
                )


def _broader_cycles(ctx: RuleContext) -> None:
    broader_edges = directed_edges(ctx.g, SKOS.broader, ctx.concepts)
    for component in strongly_connected_components(ctx.concepts, broader_edges):
        if len(component) > 1 or any((c, c) in broader_edges for c in component):
            ctx.add(
                "SKOS003",
                sorted(component, key=str)[0],
                "SKOS broader cycle: " + ", ".join(map(str, sorted(component, key=str))),
                subject=(),
            )


def _top_concepts(ctx: RuleContext) -> None:
    for concept, scheme in ctx.g.subject_objects(SKOS.topConceptOf):
        if (concept, SKOS.broader, None) in ctx.g:
            ctx.add(
                "SKOS006",
                concept,
                f"Top concept of {value_text(scheme)} also has an asserted broader concept.",
                subject=(scheme,),
            )
