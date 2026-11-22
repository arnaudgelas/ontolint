"""Class-hierarchy rules (CLS001-CLS009) and class-equivalence checks (OWL012).

Every rule reads the *asserted* graph (no reasoner, no imports, no network).  A *class* is an owned subject
typed ``owl:Class`` or ``rdfs:Class`` (``RuleContext.classes``); a *subclass edge* is an asserted
``rdfs:subClassOf`` triple whose subject and object are both such classes, a self-loop included, so a
restriction, a foreign or an undeclared parent is no edge.  Every finding is ``heuristic`` unless said
otherwise, and the category of every rule in the catalogue is ``heuristic``.  The standards are the OWL 2
Structural Specification (9.1.1 SubClassOf, 9.1.2 EquivalentClasses) and RDF Schema 1.1 with the RDF 1.1
Semantics entailment patterns (rdfs9 and rdfs11, the transitivity of ``rdfs:subClassOf``); thresholds are
conventions and sit on ``Policy``.  Specifications:

* **CLS001.** An owned class that is connected to nothing.  It is connected when it is the subject of an
  ``rdfs:subClassOf`` or ``owl:equivalentClass`` triple, or an IRI object of one, whatever the other end is
  (a foreign class, an anonymous restriction and the class itself included); the IRI object of
  ``rdfs:domain``, ``rdfs:range``, ``owl:someValuesFrom``, ``owl:allValuesFrom``, ``owl:onClass`` or of the
  ``domainIncludes`` and ``rangeIncludes`` of schema.org (http and https) and DCAM (since 0.16.0); the type of
  any subject, a class included; ``owl:deprecated true`` (read as the boolean); or ``rdfs:subClassOf
  owl:Thing``.  METRIC005 counts exactly this set (``orphan_classes``).  Not connections: disjointness,
  membership of ``owl:unionOf``, ``owl:intersectionOf`` or ``owl:complementOf``, an ``owl:hasValue`` filler, a
  member of a class expression used as a domain or range, and being the subject of a ``domainIncludes`` or
  ``rangeIncludes`` triple.  Info: neither OWL 2 nor RDFS asks for a connected class and a vocabulary may list
  isolated terms; the finding asks whether the class is unfinished.
* **CLS002.** Gated: at least one owned class has an individual (a resource that is not an owned class, typed by
  the class) and these classes are at least ``1 / POPULATED_CLASS_SHARE_DENOMINATOR`` (a quarter) of the owned
  classes.  Then an owned class that is the type of no subject (a class typed by it counts) and has no subclass
  edge below it (a self-loop counts).  A deprecated class is judged, and so is an equivalent of a populated
  class.  Info: a leaf may be abstract or imported; a vocabulary without individuals is never judged.
* **CLS003.** A strongly connected component of more than one class, or a class with a self-loop, in the
  subclass edges.  One finding per component, focused on its first member by IRI, naming all members.
  Excluded: an equivalence (``owl:equivalentClass``) is not a cycle, and a cycle through a class that is not a
  declared owned class is not seen.  Confidence ``certain``.  Warning: a cycle is legal OWL 2 and means that its
  members are equivalent (9.1.1), so it is not an error, but it is rarely meant and it hides the hierarchy.
* **CLS004.** A subclass edge from a class to a parent that is also reachable through the other edges of the
  class (rdfs11).  Each edge is judged alone, so the two shortcuts of two equivalent classes are both
  reported.  The focus is the child, the subject is the parent.  Excluded: an edge on a cycle that nothing
  else implies, a self-loop, and any path through a class that is not a declared owned class or through an
  ``owl:equivalentClass``.  Confidence ``certain``.  Info: the edge is entailed, so removing it loses nothing,
  but it may document the intent.
* **CLS005.** The longest descending chain of subclass edges, counted in classes (a leaf is 1), is longer than
  ``Policy.depth_limit`` (10).  The classes of a cycle count 0 and a self-loop is ignored.  Reported once per
  branch, at the topmost class that is over the limit and is not itself a child of one.  Info: depth is a
  convention of readability, not a defect.
* **CLS006.** An owned class with more than ``Policy.inheritance_limit`` (5) subclass edges leaving it.  A
  restriction, a foreign or an undeclared parent is not counted; a self-loop is (gap: CLS011 to CLS013 drop
  self-loops).  Info: several parents are legal and often meant.
* **CLS007.** The chain below a class follows the only child while a class has exactly one subclass edge below
  it; its length is the number of edges followed, and a class is reported when it is at least
  ``MINIMUM_SINGLE_CHILD_CHAIN_LENGTH`` (3).  Every class above the boundary is reported, not only the top
  one.  A ring of classes is a chain whose members each see the whole ring (gap: CLS003 reports the ring).  A
  second child, or a second parent of the leaf, ends the chain.  Info: a convention against needless
  subdivisions.
* **CLS008.** An owned class that is the object of ``rdfs:domain`` of more than ``Policy.soup_limit`` (15)
  distinct IRI subjects, whatever their type.  The ``domainIncludes`` hints, a class that is a member of a
  domain expression and the properties inherited from a superclass are not counted (gap: CLS001 and OWL005 read
  the hints).  Info: a convention against crowded classes.
* **CLS009.** For each ``owl:equivalentClass`` triple between two distinct owned classes, the case-folded text of
  their ``rdfs:label`` values has a common member; the focus is the subject of the triple, the subject of the
  finding is the object.  The text is compared as it is: the language, the datatype and the kind of node are
  ignored, a blank label equals another, and whitespace is not normalised (gaps: CLS010 and CLS020 compare the
  language).  Only ``rdfs:label`` is read.  A class equivalent to itself is OWL012's.  Info: two names for one
  class may be on purpose.

Fixtures: ``tests/rule_cases/classes.py``, ``tests/test_precision_cls.py``, ``tests/test_mutation_hierarchy.py``
and ``tests/test_cls_specification.py``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Set
from typing import TYPE_CHECKING

from rdflib import Literal, URIRef
from rdflib.namespace import OWL, RDFS

from ontolint.graph import hierarchy_depths, strongly_connected_components, transitively_redundant_edges
from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity

from .owl import DOMAIN_SUBSTITUTES, RANGE_SUBSTITUTES
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
        "deterministic",
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
        "deterministic",
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
    _per_class(ctx, supers, children, orphan_classes(ctx, edges))
    components = strongly_connected_components(classes, edges)
    _cycles(ctx, components, edges)
    _redundant_edges(ctx, edges, components)
    _depth(ctx, edges)
    _single_child_chains(ctx, children)
    _equivalences(ctx)


# CLS002 needs at least 1/POPULATED_CLASS_SHARE_DENOMINATOR of the owned classes to have individuals.
POPULATED_CLASS_SHARE_DENOMINATOR = 4

# Predicates whose object is a class *used* by the ontology (domain, range, restriction filler,
# schema.org and dcam style domain/range hints, the same ones OWL005 and OWL006 read).  Used by CLS001.
USAGE_PREDICATES = (
    RDFS.domain,
    RDFS.range,
    OWL.someValuesFrom,
    OWL.allValuesFrom,
    OWL.onClass,
    *DOMAIN_SUBSTITUTES,
    *RANGE_SUBSTITUTES,
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


def orphan_classes(ctx: RuleContext, edges: Iterable[tuple[URIRef, URIRef]] | None = None) -> frozenset[URIRef]:
    """Return the classes CLS001 reports (METRIC005 counts the same set).

    An orphan has no asserted local super- or subclass, is not used anywhere (domain, range, filler,
    instance, link, deprecation) and is not a ``rdfs:subClassOf owl:Thing``.  ``edges`` are the subclass
    edges between ``ctx.classes``; they are derived when not given.
    """
    if edges is None:
        edges = directed_edges(ctx.g, RDFS.subClassOf, ctx.classes)
    linked: set[URIRef] = set()
    for child, parent in edges:
        linked.update((child, parent))
    used = _used_classes(ctx)
    return frozenset(
        c for c in ctx.classes if c not in linked and c not in used and (c, RDFS.subClassOf, OWL.Thing) not in ctx.g
    )


def _per_class(ctx: RuleContext, supers: Adjacency, children: Adjacency, orphans: frozenset[URIRef]) -> None:
    policy = ctx.policy
    individuals = _has_individuals(ctx)
    # Orphan = no asserted local class-to-class hierarchy and no use anywhere, not no semantic links.
    for c in ctx.classes:
        if c in orphans:
            ctx.add("CLS001", c, "No asserted local super-/subclass links.")
        has_instance = bool(ctx.context.subjects_by_type.get(c))
        if individuals and not has_instance and not children[c]:
            ctx.add("CLS002", c, "Class has no directly typed instance or subclass in this graph.")
        if len(supers[c]) > policy.inheritance_limit:
            ctx.add(
                "CLS006", c, f"{len(supers[c])} direct superclasses (threshold {policy.inheritance_limit}).", subject=()
            )
        direct_properties = ctx.context.properties_by_domain.get(c, frozenset())
        if len(direct_properties) > policy.soup_limit:
            ctx.add("CLS008", c, f"{len(direct_properties)} properties with asserted domain {c}.", subject=())


def _cycles(ctx: RuleContext, components: Iterable[Set[URIRef]], edges: Edges) -> None:
    for component in components:
        if len(component) > 1 or any((c, c) in edges for c in component):
            representative = sorted(component, key=str)[0]
            ctx.add(
                "CLS003",
                representative,
                "Asserted subclass cycle: " + ", ".join(str(n) for n in sorted(component, key=str)),
                confidence="certain",
                subject=(),
            )


def _redundant_edges(ctx: RuleContext, edges: Edges, components: list[set[URIRef]]) -> None:
    redundant = transitively_redundant_edges(edges, components)
    for c, parent in edges:
        if (c, parent) in redundant:
            ctx.add(
                "CLS004",
                c,
                f"Asserted subclass edge to {parent} is transitively redundant.",
                confidence="certain",
                subject=(parent,),
            )


def _depth(ctx: RuleContext, edges: Edges) -> None:
    """Report each deep branch once, at its topmost over-deep class (not at every ancestor)."""
    limit = ctx.policy.depth_limit
    depths = hierarchy_depths(ctx.classes, edges)
    deep = {c for c in ctx.classes if depths[c] > limit}
    below = {child for child, parent in edges if parent in deep and child != parent}
    for c in deep - below:
        ctx.add("CLS005", c, f"Asserted subtree depth {depths[c]} exceeds {limit}.", subject=())


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
            ctx.add("CLS007", c, f"Single-child hierarchy extends {lengths[c]} edges below class.", subject=())


def _equivalences(ctx: RuleContext) -> None:
    classes, g = ctx.classes, ctx.g
    for left, right in g.subject_objects(OWL.equivalentClass):
        if left in classes and left == right:
            ctx.add("OWL012", left, "Class is explicitly equivalent to itself.")
        elif left in classes and right in classes:
            ls = {str(x).casefold() for x in g.objects(left, RDFS.label)}
            rs = {str(x).casefold() for x in g.objects(right, RDFS.label)}
            if ls and (ls & rs):
                ctx.add(
                    "CLS009",
                    left,
                    f"Equivalent class {right} has an identical label (review duplication).",
                    subject=(right,),
                )
