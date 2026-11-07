"""SKOS integrity rules: SKOS007-SKOS021.

Every rule reads asserted triples only (no entailment).  The conditions come from the SKOS
reference integrity axioms (disjointness of Concept/ConceptScheme/Collection, ``skos:related`` versus
hierarchy, exactMatch versus broad/relatedMatch) and from common vocabulary-quality practice
(labels, notations, scheme membership, mapping scope).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import TYPE_CHECKING

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, SKOS, XSD
from rdflib.term import Node

from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity

from .owl import namespace_of, owned_checker

if TYPE_CHECKING:
    from .runtime import RuleContext

_HIERARCHY = (SKOS.broader, SKOS.narrower, SKOS.broaderTransitive, SKOS.narrowerTransitive)
_INVERSE_HIERARCHY = (SKOS.narrower, SKOS.narrowerTransitive)
_MAPPING = (SKOS.exactMatch, SKOS.closeMatch, SKOS.broadMatch, SKOS.narrowMatch, SKOS.relatedMatch)
_LABELS = (SKOS.prefLabel, SKOS.altLabel, SKOS.hiddenLabel)
_RELATIONS = (
    SKOS.broader,
    SKOS.narrower,
    SKOS.related,
    SKOS.broaderTransitive,
    SKOS.narrowerTransitive,
    SKOS.inScheme,
    SKOS.hasTopConcept,
    SKOS.topConceptOf,
    *_MAPPING,
)
MINIMUM_SHARED = 2
_LINK_TARGETS = (SKOS.broader, SKOS.narrower, SKOS.related, *_MAPPING)


def _spec(rule_id: str, title: str, severity: Severity, suggestion: str, scope: RuleScope) -> RuleSpec:
    return RuleSpec(
        rule_id, "SKOS", title, severity, suggestion, "deterministic", RuleBackend.RDFLIB, scope, "skos_integrity"
    )


SPECS: tuple[RuleSpec, ...] = (
    _spec(
        "SKOS007",
        "Resource typed as both skos:Concept and skos:ConceptScheme",
        Severity.ERROR,
        "Split the resource: skos:Concept and skos:ConceptScheme are disjoint classes.",
        RuleScope.TERM,
    ),
    _spec(
        "SKOS008",
        "skos:Collection typed as concept or concept scheme",
        Severity.ERROR,
        "Do not type a skos:Collection as skos:Concept or skos:ConceptScheme; the classes are disjoint.",
        RuleScope.TERM,
    ),
    _spec(
        "SKOS009",
        "skos:related between concepts that are also hierarchically linked",
        Severity.ERROR,
        "Remove skos:related or the broader/narrower link: associative and hierarchical relations are disjoint.",
        RuleScope.TERM,
    ),
    _spec(
        "SKOS010",
        "Concept related to itself",
        Severity.WARNING,
        "Remove the reflexive skos:related statement.",
        RuleScope.TERM,
    ),
    _spec(
        "SKOS011",
        "SKOS mapping property between concepts of the same scheme",
        Severity.INFO,
        "Use skos:broader/narrower/related inside a scheme; reserve mapping properties for cross-scheme links.",
        RuleScope.TERM,
    ),
    _spec(
        "SKOS012",
        "skos:exactMatch combined with broadMatch, narrowMatch or relatedMatch",
        Severity.ERROR,
        "Keep one mapping type per concept pair: skos:exactMatch is disjoint with broad/narrow/relatedMatch.",
        RuleScope.TERM,
    ),
    _spec(
        "SKOS013",
        "SKOS label that is not a plain or language-tagged string literal",
        Severity.WARNING,
        "Use a plain or language-tagged string literal for skos:prefLabel, altLabel and hiddenLabel.",
        RuleScope.TERM,
    ),
    _spec(
        "SKOS014",
        "SKOS label that is empty or has surrounding whitespace",
        Severity.WARNING,
        "Trim the label and do not leave it empty.",
        RuleScope.TERM,
    ),
    _spec(
        "SKOS015",
        "Concept scheme with concepts but no top concept",
        Severity.INFO,
        "Declare entry points with skos:hasTopConcept or skos:topConceptOf.",
        RuleScope.TERM,
    ),
    _spec(
        "SKOS016",
        "SKOS relation with a literal value",
        Severity.ERROR,
        "SKOS semantic, mapping and scheme relations link resources; replace the literal with an IRI.",
        RuleScope.TERM,
    ),
    _spec(
        "SKOS017",
        "SKOS relation to an undescribed local resource",
        Severity.WARNING,
        "Describe the target concept in the vocabulary or correct the link.",
        RuleScope.TERM,
    ),
    _spec(
        "SKOS018",
        "Redundant skos:broader shortcut",
        Severity.INFO,
        "Remove the direct broader link that is already implied through an asserted intermediate concept.",
        RuleScope.TERM,
    ),
    _spec(
        "SKOS019",
        "Hierarchical link between concepts of different schemes",
        Severity.INFO,
        "Keep broader/narrower inside one scheme and use mapping properties across schemes.",
        RuleScope.TERM,
    ),
    _spec(
        "SKOS020",
        "Same skos:notation on several concepts of one scheme",
        Severity.WARNING,
        "Make notations unique within a concept scheme.",
        RuleScope.TERM,
    ),
    _spec(
        "SKOS021",
        "Same preferred label on several concepts of one scheme",
        Severity.WARNING,
        "Give concepts of one scheme distinguishable preferred labels per language.",
        RuleScope.TERM,
    ),
)


def run(ctx: RuleContext) -> None:
    """Run all SKOS integrity rules."""
    _disjoint_types(ctx)
    _related_conflicts(ctx)
    _mapping_conflicts(ctx)
    _labels(ctx)
    _relation_values(ctx)
    schemes = _schemes_of(ctx.g)
    _scheme_scope(ctx, schemes)
    _scheme_members(ctx, schemes)
    _redundant_broader(ctx)
    _uniqueness(ctx, schemes)


# --- helpers ---------------------------------------------------------------------------------


def _iris(nodes: Iterable[Node]) -> list[URIRef]:
    return sorted({n for n in nodes if isinstance(n, URIRef)})


def _pairs(g: Graph, predicates: Iterable[URIRef], *, inverse: Iterable[URIRef] = ()) -> set[frozenset[URIRef]]:
    """Unordered IRI pairs (``s != o``) linked by ``predicates`` or by ``inverse`` (either direction)."""
    inverted = set(inverse)
    out: set[frozenset[URIRef]] = set()
    for p in predicates:
        for s, o in g.subject_objects(p):
            if isinstance(s, URIRef) and isinstance(o, URIRef) and s != o:
                out.add(frozenset((s, o)))
    return out | {pair for p in inverted for pair in _pairs(g, (p,))}


def _ordered(pair: frozenset[URIRef]) -> tuple[URIRef, URIRef]:
    first, second = sorted(pair)
    return first, second


def _schemes_of(g: Graph) -> dict[URIRef, set[URIRef]]:
    """Asserted scheme membership (``inScheme``, ``topConceptOf``, inverse ``hasTopConcept``)."""
    schemes: defaultdict[URIRef, set[URIRef]] = defaultdict(set)
    for p in (SKOS.inScheme, SKOS.topConceptOf):
        for c, s in g.subject_objects(p):
            if isinstance(c, URIRef) and isinstance(s, URIRef):
                schemes[c].add(s)
    for s, c in g.subject_objects(SKOS.hasTopConcept):
        if isinstance(c, URIRef) and isinstance(s, URIRef):
            schemes[c].add(s)
    return schemes


# --- rules -----------------------------------------------------------------------------------


def _disjoint_types(ctx: RuleContext) -> None:
    g = ctx.g
    concepts = set(g.subjects(RDF.type, SKOS.Concept))
    scheme_nodes = set(g.subjects(RDF.type, SKOS.ConceptScheme))
    for node in _iris(concepts & scheme_nodes):
        if ctx.local(node):
            ctx.add(
                "SKOS007", node, "Resource is typed as both skos:Concept and skos:ConceptScheme.", confidence="certain"
            )
    for node in _iris(g.subjects(RDF.type, SKOS.Collection)):
        if ctx.local(node) and (node in concepts or node in scheme_nodes):
            ctx.add(
                "SKOS008",
                node,
                "skos:Collection is also typed as skos:Concept or skos:ConceptScheme.",
                confidence="certain",
            )


def _related_conflicts(ctx: RuleContext) -> None:
    g = ctx.g
    related = _pairs(g, (SKOS.related,))
    hierarchy = _pairs(g, _HIERARCHY)
    for pair in sorted(related & hierarchy, key=_ordered):
        first, second = _ordered(pair)
        if ctx.local(first) or ctx.local(second):
            ctx.add(
                "SKOS009",
                first,
                f"skos:related and a hierarchical link both connect {first} and {second}.",
                confidence="certain",
            )
    for c in _iris(g.subjects(SKOS.related, None)):
        if (c, SKOS.related, c) in g and ctx.local(c):
            ctx.add("SKOS010", c, "Concept is skos:related to itself.", confidence="certain")


def _mapping_conflicts(ctx: RuleContext) -> None:
    g = ctx.g
    exact = _pairs(g, (SKOS.exactMatch,))
    others = _pairs(g, (SKOS.broadMatch, SKOS.narrowMatch, SKOS.relatedMatch))
    for pair in sorted(exact & others, key=_ordered):
        first, second = _ordered(pair)
        if ctx.local(first) or ctx.local(second):
            ctx.add(
                "SKOS012",
                first,
                f"skos:exactMatch and another mapping type both connect {first} and {second}.",
                confidence="certain",
            )


def _labels(ctx: RuleContext) -> None:
    g = ctx.g
    string_types = (None, XSD.string)
    for p in _LABELS:
        for s, label in sorted(g.subject_objects(p), key=lambda t: (str(t[0]), str(t[1]))):
            if not ctx.local(s):
                continue
            name = p.rsplit("#", 1)[-1]
            if not isinstance(label, Literal) or label.datatype not in string_types:
                ctx.add(
                    "SKOS013",
                    s,
                    f"skos:{name} value {str(label)[:60]!r} is not a string literal.",
                    confidence="certain",
                )
            elif not str(label).strip() or str(label) != str(label).strip():
                ctx.add("SKOS014", s, f"skos:{name} is empty or has leading/trailing whitespace.", confidence="certain")


def _relation_values(ctx: RuleContext) -> None:
    g = ctx.g
    for p in _RELATIONS:
        for s, o in g.subject_objects(p):
            if isinstance(o, Literal) and ctx.local(s):
                ctx.add("SKOS016", s, f"skos:{p.rsplit('#', 1)[-1]} has a literal value.", confidence="certain")
    owned = owned_checker(ctx)
    for p in _LINK_TARGETS:
        for s, o in sorted(g.subject_objects(p), key=lambda t: (str(t[0]), str(t[1]))):
            if (
                isinstance(o, URIRef)
                and ctx.local(s)
                and owned(o)
                and (p not in _MAPPING or namespace_of(o) == namespace_of(s))
                and (o, None, None) not in g
            ):
                ctx.add("SKOS017", s, f"skos:{p.rsplit('#', 1)[-1]} target {o} is not described in the graph.")


def _scheme_scope(ctx: RuleContext, schemes: dict[URIRef, set[URIRef]]) -> None:
    g = ctx.g
    hierarchical = _pairs(g, (SKOS.broader,), inverse=(SKOS.narrower,))
    mapped = _pairs(g, _MAPPING)
    for pair in sorted(mapped, key=_ordered):
        first, second = _ordered(pair)
        if schemes.get(first, set()) & schemes.get(second, set()) and (ctx.local(first) or ctx.local(second)):
            ctx.add("SKOS011", first, f"Mapping property links {first} and {second}, which share a concept scheme.")
    for pair in sorted(hierarchical, key=_ordered):
        first, second = _ordered(pair)
        a, b = schemes.get(first), schemes.get(second)
        if a and b and not a & b and (ctx.local(first) or ctx.local(second)):
            ctx.add("SKOS019", first, f"Hierarchical link between {first} and {second} crosses concept schemes.")


def _scheme_members(ctx: RuleContext, schemes: dict[URIRef, set[URIRef]]) -> None:
    g = ctx.g
    members: defaultdict[URIRef, set[URIRef]] = defaultdict(set)
    for concept, its in schemes.items():
        for scheme in its:
            members[scheme].add(concept)
    for scheme in _iris(g.subjects(RDF.type, SKOS.ConceptScheme)):
        has_top = (scheme, SKOS.hasTopConcept, None) in g or (None, SKOS.topConceptOf, scheme) in g
        if members.get(scheme) and not has_top and ctx.local(scheme):
            ctx.add("SKOS015", scheme, f"Concept scheme has {len(members[scheme])} concept(s) but no top concept.")


def _redundant_broader(ctx: RuleContext) -> None:
    broader: defaultdict[URIRef, set[URIRef]] = defaultdict(set)
    for s, o in ctx.g.subject_objects(SKOS.broader):
        if isinstance(s, URIRef) and isinstance(o, URIRef) and s != o:
            broader[s].add(o)
    for child in sorted(broader):
        parents = broader[child]
        for parent in sorted(parents):
            shortcuts = {c for c in broader.get(parent, set()) if c in parents and c not in (child, parent)}
            for grand in sorted(shortcuts):
                if ctx.local(child):
                    ctx.add(
                        "SKOS018",
                        child,
                        f"skos:broader {grand} is redundant: already reachable through {parent}.",
                        confidence="certain",
                    )


def _uniqueness(ctx: RuleContext, schemes: dict[URIRef, set[URIRef]]) -> None:
    notations: defaultdict[tuple[URIRef, str], set[URIRef]] = defaultdict(set)
    labels: defaultdict[tuple[URIRef, str, str], set[URIRef]] = defaultdict(set)
    for concept, its in schemes.items():
        for scheme in its:
            for n in ctx.g.objects(concept, SKOS.notation):
                if isinstance(n, Literal):
                    notations[scheme, f"{n}^^{n.datatype}"].add(concept)
            for label in ctx.g.objects(concept, SKOS.prefLabel):
                if isinstance(label, Literal) and str(label).strip():
                    labels[scheme, (label.language or "").lower(), str(label).strip().casefold()].add(concept)
    for (scheme, notation), owners in sorted(notations.items()):
        _report_shared(ctx, "SKOS020", owners, f"skos:notation {notation.split('^^')[0][:60]!r}", scheme)
    for (scheme, language, text), owners in sorted(labels.items()):
        _report_shared(ctx, "SKOS021", owners, f"skos:prefLabel {text[:60]!r} ({language or 'no language'})", scheme)


def _report_shared(ctx: RuleContext, rule: str, owners: set[URIRef], what: str, scheme: URIRef) -> None:
    if len(owners) < MINIMUM_SHARED:
        return
    for concept in sorted(o for o in owners if ctx.local(o)):
        ctx.add(rule, concept, f"{what} is shared by {len(owners)} concepts of {scheme}.")
