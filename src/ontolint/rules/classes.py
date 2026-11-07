"""Class-hierarchy rules (CLS001-CLS009) and class-equivalence checks (OWL012)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Set
from typing import TYPE_CHECKING

from rdflib import Literal, URIRef
from rdflib.namespace import OWL, RDFS

from ontolint.graph import hierarchy_depths, strongly_connected_components, transitively_redundant_edges
from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity

from .support import MINIMUM_SINGLE_CHILD_CHAIN_LENGTH, directed_edges

if TYPE_CHECKING:
    from .runtime import RuleContext


type Adjacency = defaultdict[URIRef, set[URIRef]]
type Edges = set[tuple[URIRef, URIRef]]


SPECS: tuple[RuleSpec, ...] = (
    RuleSpec(
        "CLS001",
        "CLS",
        "Disconnected class",
        Severity.INFO,
        (
            "Inspect whether the class is intentional: it has no sub/superclass or equivalence link, "
            "is not deprecated and is never used as a domain, range, restriction filler or type."
        ),
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "classes",
    ),
    RuleSpec(
        "CLS002",
        "CLS",
        "Class without instances or subclasses",
        Severity.INFO,
        "Check whether this class is intentionally uninstantiated, abstract, or imported.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "classes",
    ),
    RuleSpec(
        "CLS003",
        "CLS",
        "Asserted subclass cycle",
        Severity.WARNING,
        "Review the asserted subclass cycle; an OWL subclass cycle is not by itself inconsistent.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.VOCABULARY,
        "classes",
    ),
    RuleSpec(
        "CLS004",
        "CLS",
        "Transitively redundant subclass axiom",
        Severity.INFO,
        "Remove a redundant asserted subclass axiom if it adds no documentation value.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "classes",
    ),
    RuleSpec(
        "CLS005",
        "CLS",
        "Excessive hierarchy depth",
        Severity.INFO,
        "Review unusually deep asserted hierarchy and possible re-modeling.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "classes",
    ),
    RuleSpec(
        "CLS006",
        "CLS",
        "Excessive direct superclasses",
        Severity.INFO,
        "Review the intended meaning of multiple direct superclasses.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "classes",
    ),
    RuleSpec(
        "CLS007",
        "CLS",
        "Long single-child taxonomic chain",
        Severity.INFO,
        "Check long single-child taxonomic chains for needless subdivisions.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "classes",
    ),
    RuleSpec(
        "CLS008",
        "CLS",
        "Class with excessive asserted properties",
        Severity.INFO,
        "Consider splitting classes or using property groups/shapes where appropriate.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "classes",
    ),
    RuleSpec(
        "CLS009",
        "CLS",
        "Equivalent classes with identical labels",
        Severity.INFO,
        "Check whether class equivalence is purposeful and not merely a duplicate name.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "classes",
    ),
    RuleSpec(
        "OWL012",
        "OWL",
        "Class equivalent to itself",
        Severity.INFO,
        "Review the use of owl:equivalentClass on the class itself.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "classes",
    ),
)


def run(ctx: RuleContext) -> None:
    """Run all class-hierarchy rules."""
    classes = ctx.classes
    edges = directed_edges(ctx.g, RDFS.subClassOf, classes)
    supers: Adjacency = defaultdict(set)
    children: Adjacency = defaultdict(set)
    for child, parent in edges:
        supers[child].add(parent)
        children[parent].add(child)
    _per_class(ctx, supers, children)
    components = strongly_connected_components(classes, edges)
    _cycles(ctx, components, edges)
    _redundant_edges(ctx, edges, components)
    _depth(ctx, components, edges)
    _single_child_chains(ctx, children)
    _equivalences(ctx)


# CLS002 needs at least 1/POPULATED_CLASS_SHARE_DENOMINATOR of the owned classes to have individuals.
POPULATED_CLASS_SHARE_DENOMINATOR = 4

# Predicates whose object is a class *used* by the ontology (domain, range, restriction filler,
# schema.org style domain/range hints).  Used by CLS001.
USAGE_PREDICATES = (
    RDFS.domain,
    RDFS.range,
    OWL.someValuesFrom,
    OWL.allValuesFrom,
    OWL.onClass,
    URIRef("https://schema.org/domainIncludes"),
    URIRef("https://schema.org/rangeIncludes"),
    URIRef("http://schema.org/domainIncludes"),
    URIRef("http://schema.org/rangeIncludes"),
)


def _used_classes(ctx: RuleContext) -> set[URIRef]:
    """Return classes that are used or connected: domain/range/filler, typed individuals, links, deprecated."""
    used = {o for p in USAGE_PREDICATES for o in ctx.g.objects(None, p) if isinstance(o, URIRef)}
    used.update(c for c in ctx.classes if ctx.context.subjects_by_type.get(c))
    # Any asserted hierarchy or equivalence link, even to a foreign or anonymous class, is a connection.
    for predicate in (RDFS.subClassOf, OWL.equivalentClass):
        for s, o in ctx.g.subject_objects(predicate):
            used.update(n for n in (s, o) if isinstance(n, URIRef))
    # Deprecated terms are expected to be detached.
    used.update(s for s in ctx.g.subjects(OWL.deprecated, Literal(True)) if isinstance(s, URIRef))
    return used


def _has_individuals(ctx: RuleContext) -> bool:
    """Return whether the graph is instance-oriented: at least a quarter of the owned classes have individuals.

    "Individuals" are non-class resources typed with an owned class.  A vocabulary that only ships a
    few enumeration members (``time:Monday``) is not populated, so empty leaves are the norm there.
    """
    by_type = ctx.context.subjects_by_type
    populated = sum(1 for c in ctx.classes if any(s not in ctx.classes for s in by_type.get(c, ())))
    return populated > 0 and populated * POPULATED_CLASS_SHARE_DENOMINATOR >= len(ctx.classes)


def _per_class(ctx: RuleContext, supers: Adjacency, children: Adjacency) -> None:
    policy = ctx.policy
    used = _used_classes(ctx)
    individuals = _has_individuals(ctx)
    # Orphan = no asserted local class-to-class hierarchy and no use anywhere, not no semantic links.
    for c in ctx.classes:
        if not supers[c] and not children[c] and c not in used and (c, RDFS.subClassOf, OWL.Thing) not in ctx.g:
            ctx.add("CLS001", c, "No asserted local super-/subclass links.")
        has_instance = bool(ctx.context.subjects_by_type.get(c))
        if individuals and not has_instance and not children[c]:
            ctx.add("CLS002", c, "Class has no directly typed instance or subclass in this graph.")
        if len(supers[c]) > policy.inheritance_limit:
            ctx.add("CLS006", c, f"{len(supers[c])} direct superclasses (threshold {policy.inheritance_limit}).")
        direct_properties = ctx.context.properties_by_domain.get(c, frozenset())
        if len(direct_properties) > policy.soup_limit:
            ctx.add("CLS008", c, f"{len(direct_properties)} properties with asserted domain {c}.")


def _cycles(ctx: RuleContext, components: Iterable[Set[URIRef]], edges: Edges) -> None:
    for component in components:
        if len(component) > 1 or any((c, c) in edges for c in component):
            representative = sorted(component, key=str)[0]
            ctx.add(
                "CLS003",
                representative,
                "Asserted subclass cycle: " + ", ".join(str(n) for n in sorted(component, key=str)),
                confidence="certain",
            )


def _redundant_edges(ctx: RuleContext, edges: Edges, components: list[set[URIRef]]) -> None:
    redundant = transitively_redundant_edges(edges, components)
    for c, parent in edges:
        if (c, parent) in redundant:
            ctx.add("CLS004", c, f"Asserted subclass edge to {parent} is transitively redundant.", confidence="certain")


def _depth(ctx: RuleContext, components: Iterable[Set[URIRef]], edges: Edges) -> None:
    """Report each deep branch once, at its topmost over-deep class (not at every ancestor)."""
    cyclic = {n for comp in components if len(comp) > 1 for n in comp}
    limit = ctx.policy.depth_limit
    depths = hierarchy_depths(ctx.classes, edges)
    deep = {c for c in ctx.classes if c not in cyclic and depths[c] > limit}
    below = {child for child, parent in edges if parent in deep and child != parent}
    for c in deep - below:
        ctx.add("CLS005", c, f"Asserted subtree depth {depths[c]} exceeds {limit}.")


def _chain_lengths(classes: Iterable[URIRef], children: Adjacency) -> dict[URIRef, int]:
    """Return the legacy per-class single-child chain length, each class computed once.

    The chain below a class follows the sole child while a node has exactly one
    child, stopping at the first node already walked (cycles); the length is the
    number of distinct nodes stepped through.
    """
    lengths: dict[URIRef, int] = {}
    for start in classes:
        path: list[URIRef] = []
        index: dict[URIRef, int] = {}
        node = start
        # gremlin: pardon[untestable] mutant never terminates on a single-child cycle; tests bound it with an alarm
        while node not in lengths and node not in index and len(children[node]) == 1:
            index[node] = len(path)
            path.append(node)
            node = next(iter(children[node]))
        if node in lengths or len(children[node]) != 1:
            base = lengths.get(node, 0)
            tail = path
        else:  # walked back into this path: the ring nodes each see the whole ring
            ring = len(path) - index[node]
            for member in path[index[node] :]:
                lengths[member] = ring
            base, tail = ring, path[: index[node]]
        for member in reversed(tail):
            base += 1
            lengths[member] = base
        lengths.setdefault(start, 0)
    return lengths


def _single_child_chains(ctx: RuleContext, children: Adjacency) -> None:
    lengths = _chain_lengths(ctx.classes, children)
    for c in ctx.classes:
        if lengths[c] >= MINIMUM_SINGLE_CHILD_CHAIN_LENGTH:
            ctx.add("CLS007", c, f"Single-child hierarchy extends {lengths[c]} edges below class.")


def _equivalences(ctx: RuleContext) -> None:
    classes, g = ctx.classes, ctx.g
    for left, right in g.subject_objects(OWL.equivalentClass):
        if left in classes and left == right:
            ctx.add("OWL012", left, "Class is explicitly equivalent to itself.")
        elif left in classes and right in classes:
            ls = {str(x).casefold() for x in g.objects(left, RDFS.label)}
            rs = {str(x).casefold() for x in g.objects(right, RDFS.label)}
            if ls and (ls & rs):
                ctx.add("CLS009", left, f"Equivalent class {right} has an identical label (review duplication).")
