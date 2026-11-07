"""Ontology alignment rules that can be decided inside one file: ALIGN002-005, 007, 009, 013-015.

Every rule reads the mappings asserted in the linted graph (SKOS mapping properties, ``owl:sameAs``,
``owl:equivalentClass``/``equivalentProperty``) together with the file's own hierarchy and
declarations.  Nothing is entailed beyond the transitive closure of asserted ``skos:exactMatch`` and
asserted hierarchy edges, both computed iteratively.  The remaining ALIGN rules need an external
mapping registry, the aligned ontologies or a reasoner and stay proposed.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import replace
from typing import TYPE_CHECKING

from rdflib import Graph, URIRef
from rdflib.namespace import DCTERMS, OWL, RDFS, SKOS
from rdflib.term import Node

from ontolint.context import CLASS_TYPES, PROPERTY_TYPES
from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity

from .support import META_CREATOR, META_LICENSE

if TYPE_CHECKING:
    from .runtime import RuleContext

_SKOS_BASE = "http://www.w3.org/2004/02/skos/core"
_OWL_BASE = "http://www.w3.org/2002/07/owl"
_SSSOM = ("https://w3id.org/sssom/", "http://w3id.org/sssom/")
_MAPPING_SET = tuple(URIRef(base + "MappingSet") for base in _SSSOM)
_SSSOM_VERSION = tuple(URIRef(base + "mapping_set_version") for base in _SSSOM)
_SSSOM_CREATOR = tuple(URIRef(base + "creator_id") for base in _SSSOM)
_SSSOM_LICENSE = tuple(URIRef(base + "license") for base in _SSSOM)
_VERSION = (OWL.versionInfo, OWL.versionIRI, DCTERMS.hasVersion)

_NARROW_FIRST = (SKOS.broadMatch, SKOS.narrowMatch)  # Hierarchical mappings.
_OWL_EQUIVALENCE = (OWL.equivalentClass, OWL.equivalentProperty, OWL.sameAs)
_EQUIVALENCE = (SKOS.exactMatch, *_OWL_EQUIVALENCE)
_MAPPING = (
    SKOS.exactMatch,
    SKOS.closeMatch,
    SKOS.broadMatch,
    SKOS.narrowMatch,
    SKOS.relatedMatch,
    SKOS.mappingRelation,
    OWL.equivalentClass,
    OWL.equivalentProperty,
    OWL.sameAs,
)
_SYMMETRIC_SKOS = (SKOS.exactMatch, SKOS.closeMatch)
_PREFIXES = ((str(SKOS), "skos:"), (str(OWL), "owl:"))
_KNOWN_NAMES = {re.sub(r"[^a-z0-9]", "", str(p).rsplit("#", 1)[-1].lower()): p for p in _MAPPING}


def _spec(rule_id: str, title: str, severity: Severity, suggestion: str, category: str) -> RuleSpec:
    return RuleSpec(
        rule_id, "ALIGN", title, severity, suggestion, category, RuleBackend.RDFLIB, RuleScope.TERM, "alignment"
    )


SPECS: tuple[RuleSpec, ...] = (
    _spec(
        "ALIGN002",
        "Misspelt SKOS or OWL mapping predicate",
        Severity.WARNING,
        "Use the exact SKOS or OWL mapping property IRI (for example skos:exactMatch); the asserted one is unknown.",
        "heuristic",
    ),
    _spec(
        "ALIGN003",
        "exactMatch chain conflicting with broadMatch or narrowMatch",
        Severity.ERROR,
        "skos:exactMatch is transitive and disjoint with broad/narrowMatch; drop one mapping of the chain.",
        "deterministic",
    ),
    _spec(
        "ALIGN004",
        "Contradictory hierarchical or associative mapping strengths",
        Severity.WARNING,
        "Keep one mapping strength per pair: broadMatch, narrowMatch and relatedMatch exclude each other.",
        "deterministic",
    ),
    _spec(
        "ALIGN005",
        "Term with several distinct exactMatch targets in one namespace",
        Severity.WARNING,
        "Keep one exactMatch per target namespace, or relate the targets to each other if they are the same thing.",
        "context-dependent",
    ),
    _spec(
        "ALIGN007",
        "Symmetric SKOS mapping asserted in one direction only",
        Severity.INFO,
        "Assert the inverse skos:exactMatch/closeMatch too, since both terms are described in this file.",
        "context-dependent",
    ),
    _spec(
        "ALIGN009",
        "Mapping between a class and a property",
        Severity.WARNING,
        "Map classes to classes and properties to properties; the declared kinds are incompatible.",
        "context-dependent",
    ),
    _spec(
        "ALIGN013",
        "Duplicate mapping through several predicates",
        Severity.INFO,
        "Keep the most precise mapping predicate; the same pair is related by several equivalent assertions.",
        "context-dependent",
    ),
    _spec(
        "ALIGN014",
        "broadMatch or narrowMatch contradicting the asserted hierarchy",
        Severity.WARNING,
        "Reverse the mapping or fix the hierarchy; the file places the broader term below the narrower one.",
        "deterministic",
    ),
    replace(
        _spec(
            "ALIGN015",
            "Declared mapping set without version, creator or licence",
            Severity.INFO,
            "Add a version, a creator and a licence to the sssom:MappingSet.",
            "deterministic",
        ),
        scope=RuleScope.ONTOLOGY,
    ),
)


# --- helpers ---------------------------------------------------------------------------------


def _name(predicate: Node) -> str:
    text = str(predicate)
    for base, prefix in _PREFIXES:
        if text.startswith(base):
            return prefix + text[len(base) :]
    return text


def _edges(g: Graph, predicates: Iterable[Node]) -> list[tuple[URIRef, Node, URIRef]]:
    """Asserted ``(subject, predicate, object)`` triples between distinct IRIs, in a stable order."""
    found = {
        (s, p, o)
        for p in predicates
        for s, o in g.subject_objects(p)
        if isinstance(s, URIRef) and isinstance(o, URIRef) and s != o
    }
    return sorted(found, key=lambda t: (str(t[0]), str(t[1]), str(t[2])))


def _ordered(nodes: Iterable[URIRef]) -> list[URIRef]:
    return sorted(nodes, key=str)


def _hierarchy_edges(g: Graph) -> list[tuple[URIRef, URIRef]]:
    """``(narrower, broader)`` pairs asserted by SKOS broad/narrowMatch."""
    pairs = {(s, o) for s, _, o in _edges(g, (SKOS.broadMatch,))}
    pairs |= {(o, s) for s, _, o in _edges(g, (SKOS.narrowMatch,))}
    return sorted(pairs, key=lambda t: (str(t[0]), str(t[1])))


def _find(parent: dict[Node, Node], node: Node) -> Node:
    root = node
    while parent.get(root, root) != root:
        root = parent[root]
    while parent.get(node, node) != root:
        parent[node], node = root, parent[node]
    return root


def _union(parent: dict[Node, Node], a: Node, b: Node) -> None:
    parent[_find(parent, a)] = _find(parent, b)


def _namespace(iri: URIRef) -> str:
    text = str(iri)
    return text[: max(text.rfind("#"), text.rfind("/")) + 1]


# --- ALIGN002 --------------------------------------------------------------------------------


def _misspelt_predicates(ctx: RuleContext) -> None:
    for p in _ordered(p for p in ctx.context.predicates if isinstance(p, URIRef) and p not in _MAPPING):
        text = str(p)
        owner = next((b for b in (_SKOS_BASE, _OWL_BASE) if text.startswith(b)), None)
        if owner is None:
            continue
        stem = text[len(owner) :].lstrip("#/")
        known = _KNOWN_NAMES.get(re.sub(r"[^a-z0-9]", "", stem.lower()))
        if known is None and not (owner == _SKOS_BASE and "match" in stem.lower()):
            continue
        hint = f"; did you mean {_name(known)}?" if known is not None else ""
        for s in _ordered(s for s in ctx.g.subjects(p, None) if isinstance(s, URIRef)):
            if ctx.local(s):
                ctx.add("ALIGN002", s, f"{text} is not a SKOS or OWL mapping property{hint}", confidence="certain")


# --- ALIGN003 / ALIGN004 / ALIGN014 ----------------------------------------------------------


def _exact_components(g: Graph) -> tuple[dict[Node, Node], set[frozenset[Node]]]:
    parent: dict[Node, Node] = {}
    direct: set[frozenset[Node]] = set()
    for s, _, o in _edges(g, (SKOS.exactMatch,)):
        _union(parent, s, o)
        direct.add(frozenset((s, o)))
    return parent, direct


def _exact_chain_conflicts(ctx: RuleContext) -> None:
    parent, direct = _exact_components(ctx.g)
    for narrow, broad in _hierarchy_edges(ctx.g):
        if frozenset((narrow, broad)) in direct:
            continue  # A direct exactMatch plus broad/narrowMatch is SKOS012.
        if _find(parent, narrow) == _find(parent, broad) and (ctx.local(narrow) or ctx.local(broad)):
            ctx.add(
                "ALIGN003",
                narrow,
                f"{narrow} and {broad} are exactMatch-equivalent through a chain but also linked by "
                "broadMatch/narrowMatch.",
                confidence="certain",
            )


def _contradictory_strengths(ctx: RuleContext) -> None:
    hierarchy = _hierarchy_edges(ctx.g)
    edges = set(hierarchy)
    reported: set[frozenset[URIRef]] = set()
    for narrow, broad in hierarchy:
        pair = frozenset((narrow, broad))
        if (broad, narrow) in edges and pair not in reported and (ctx.local(narrow) or ctx.local(broad)):
            reported.add(pair)
            ctx.add(
                "ALIGN004",
                narrow,
                f"{narrow} and {broad} are each mapped as broader than the other.",
                confidence="certain",
            )
    undirected = {frozenset(pair) for pair in hierarchy}
    for s, _, o in _edges(ctx.g, (SKOS.relatedMatch,)):
        if frozenset((s, o)) in undirected and (ctx.local(s) or ctx.local(o)):
            ctx.add(
                "ALIGN004",
                s,
                f"{s} and {o} are linked by skos:relatedMatch and by broadMatch/narrowMatch.",
                confidence="certain",
            )


def _parents(g: Graph) -> dict[URIRef, set[URIRef]]:
    parents: defaultdict[URIRef, set[URIRef]] = defaultdict(set)
    for child, _, parent in _edges(g, (RDFS.subClassOf, RDFS.subPropertyOf, SKOS.broader)):
        parents[child].add(parent)
    for parent, _, child in _edges(g, (SKOS.narrower,)):
        parents[child].add(parent)
    return parents


def _reaches(parents: dict[URIRef, set[URIRef]], start: URIRef, goal: URIRef) -> bool:
    seen = {start}
    stack = [start]
    while stack:
        for parent in parents.get(stack.pop(), ()):
            if parent == goal:
                return True
            if parent not in seen:
                seen.add(parent)
                stack.append(parent)
    return False


def _hierarchy_contradictions(ctx: RuleContext) -> None:
    parents = _parents(ctx.g)
    for s, p, o in _edges(ctx.g, _NARROW_FIRST):
        narrow, broad = (s, o) if p == SKOS.broadMatch else (o, s)
        if not (ctx.local(s) or ctx.local(o)):
            continue
        if _reaches(parents, broad, narrow) and not _reaches(parents, narrow, broad):
            ctx.add(
                "ALIGN014",
                s,
                f"{_name(p)} makes {broad} broader than {narrow}, but the asserted hierarchy places {broad} "
                f"below {narrow}.",
                confidence="certain",
            )


# --- ALIGN005 --------------------------------------------------------------------------------


def _distinct_groups(neighbours: dict[URIRef, set[URIRef]], members: set[URIRef], blocked: set[URIRef]) -> int:
    """Count the groups of ``members`` that stay unconnected by equivalences avoiding ``blocked``."""
    remaining = set(members)
    groups = 0
    while remaining:
        groups += 1
        stack = [remaining.pop()]
        seen = {stack[0], *blocked}
        while stack:
            for nxt in neighbours.get(stack.pop(), ()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        remaining -= seen
    return groups


def _exact_targets_per_namespace(ctx: RuleContext) -> None:
    g = ctx.g
    neighbours: defaultdict[URIRef, set[URIRef]] = defaultdict(set)
    for a, _, b in _edges(g, _EQUIVALENCE):
        neighbours[a].add(b)
        neighbours[b].add(a)
    targets: defaultdict[URIRef, set[URIRef]] = defaultdict(set)
    for s, _, o in _edges(g, (SKOS.exactMatch,)):
        if ctx.local(s) and _namespace(o) not in ("", _namespace(s)):
            targets[s].add(o)
    blocked = set(targets)  # Sources never bridge their own targets, nor do other sources.
    for source in _ordered(targets):
        by_namespace: defaultdict[str, set[URIRef]] = defaultdict(set)
        for target in targets[source]:
            by_namespace[_namespace(target)].add(target)
        for namespace in sorted(by_namespace):
            members = by_namespace[namespace]
            if _distinct_groups(neighbours, members, blocked) > 1:
                names = ", ".join(str(t) for t in _ordered(members))
                ctx.add(
                    "ALIGN005",
                    source,
                    f"Term has {len(members)} distinct skos:exactMatch targets in {namespace}: {names}.",
                )


# --- ALIGN007 --------------------------------------------------------------------------------


def _one_way_symmetric(ctx: RuleContext) -> None:
    g = ctx.g
    for s, p, o in _edges(g, _SYMMETRIC_SKOS):
        if (o, p, s) not in g and (o, None, None) in g and ctx.local(s) and ctx.local(o):
            ctx.add("ALIGN007", s, f"{_name(p)} to {o} has no inverse assertion, although {o} is described here.")


# --- ALIGN009 --------------------------------------------------------------------------------


def _incompatible_kinds(ctx: RuleContext) -> None:
    types = ctx.context.types_by_subject

    def kind(node: URIRef) -> str:
        declared = types.get(node, frozenset())
        is_class, is_property = bool(declared & set(CLASS_TYPES)), bool(declared & set(PROPERTY_TYPES))
        return "class" if is_class > is_property else "property" if is_property > is_class else ""

    for s, p, o in _edges(ctx.g, _MAPPING):
        if not (ctx.local(s) or ctx.local(o)):
            continue
        kinds = kind(s), kind(o)
        if kinds not in (("class", "property"), ("property", "class")):
            continue
        ctx.add(
            "ALIGN009",
            s,
            f"{_name(p)} maps {kinds[0]} {s} to {kinds[1]} {o}.",
            confidence="certain" if p in _OWL_EQUIVALENCE else "heuristic",
        )


# --- ALIGN013 --------------------------------------------------------------------------------


def _duplicate_mappings(ctx: RuleContext) -> None:
    g = ctx.g
    similar: defaultdict[frozenset[URIRef], set[Node]] = defaultdict(set)
    for s, p, o in _edges(g, (*_EQUIVALENCE, SKOS.closeMatch)):
        similar[frozenset((s, o))].add(p)
    for pair in sorted(similar, key=lambda t: sorted(map(str, t))):
        used = similar[pair]
        first, second = _ordered(pair)
        if len(used) > 1 and (ctx.local(first) or ctx.local(second)):
            names = ", ".join(sorted(_name(p) for p in used))
            ctx.add("ALIGN013", first, f"{first} and {second} are related by several equivalence predicates: {names}.")
    for narrow, broad in _hierarchy_edges(g):
        if (
            (narrow, SKOS.broadMatch, broad) in g
            and (broad, SKOS.narrowMatch, narrow) in g
            and (ctx.local(narrow) or ctx.local(broad))
        ):
            ctx.add(
                "ALIGN013",
                narrow,
                f"{broad} being broader than {narrow} is asserted by both skos:broadMatch and skos:narrowMatch.",
            )


# --- ALIGN015 --------------------------------------------------------------------------------


def _mapping_set_metadata(ctx: RuleContext) -> None:
    g = ctx.g
    required = (
        ("a version", (*_VERSION, *_SSSOM_VERSION)),
        ("a creator", (*META_CREATOR, *_SSSOM_CREATOR)),
        ("a licence", (*META_LICENSE, *_SSSOM_LICENSE)),
    )
    for kind in _MAPPING_SET:
        for node in _ordered(s for s in ctx.context.subjects_by_type.get(kind, ()) if isinstance(s, URIRef)):
            missing = [label for label, predicates in required if not any((node, p, None) in g for p in predicates)]
            if missing and ctx.local(node):
                ctx.add("ALIGN015", node, f"Mapping set has no {', no '.join(missing)}.")


def run(ctx: RuleContext) -> None:
    """Run every graph-local alignment rule."""
    _misspelt_predicates(ctx)
    _exact_chain_conflicts(ctx)
    _contradictory_strengths(ctx)
    _exact_targets_per_namespace(ctx)
    _one_way_symmetric(ctx)
    _incompatible_kinds(ctx)
    _duplicate_mappings(ctx)
    _hierarchy_contradictions(ctx)
    _mapping_set_metadata(ctx)


__all__ = ["SPECS", "run"]
