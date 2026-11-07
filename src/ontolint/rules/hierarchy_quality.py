"""Class-hierarchy quality rules CLS011-CLS014, CLS016, CLS018-CLS021 and CLS025.

Every rule reads the *asserted* ``rdfs:subClassOf`` graph over declared classes: no entailment,
no imports, no network.  Graph walks are iterative (hierarchies of 100k classes must not recurse).
CLS010, CLS015, CLS017, CLS022-CLS024 stay proposed (see docs/adding-rules.md and the catalogue).
"""

from __future__ import annotations

import re
from collections import defaultdict, deque
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rdflib import Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from ontolint.graph import strongly_connected_components
from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity

from .support import directed_edges, list_items, local_name

if TYPE_CHECKING:
    from .runtime import RuleContext

# A class with more direct subclasses than this is a flat, hard-to-browse fan-out (CLS011).
EXCESSIVE_SUBCLASS_COUNT = 50
# Upper bound on members read from one owl:AllDisjointClasses list.
MAX_DISJOINT_MEMBERS = 500

REMAINDER_MARKERS = frozenset({"other", "others", "misc", "miscellaneous", "remainder", "unclassified"})
REMAINDER_MARKERS |= frozenset({"uncategorized", "uncategorised", "unspecified"})
FILLER_TOKENS = frozenset({"and", "of", "the", "a", "an", "or", "else", "type", "types", "kind", "kinds"})
GENERIC_IS_NAMES = frozenset(
    {
        ("is",),
        ("isa",),
        ("is", "a"),
        ("is", "an"),
        ("is", "kind", "of"),
        ("is", "type", "of"),
        ("is", "a", "kind", "of"),
    }
)
LABEL_PREDICATES = (RDFS.label, SKOS.prefLabel)
TOP_CLASSES = frozenset({OWL.Thing, RDFS.Resource})
TOKEN = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")


def _spec(rule_id: str, title: str, severity: Severity, suggestion: str, scope: RuleScope) -> RuleSpec:
    return RuleSpec(
        rule_id, "CLS", title, severity, suggestion, "heuristic", RuleBackend.RDFLIB, scope, "hierarchy_quality"
    )


SPECS: tuple[RuleSpec, ...] = (
    _spec(
        "CLS011",
        "Excessive direct subclasses",
        Severity.INFO,
        "Introduce intermediate classes to structure a flat fan-out of direct subclasses.",
        RuleScope.TERM,
    ),
    _spec(
        "CLS012",
        "Instantiated class with only unused leaf subclasses",
        Severity.INFO,
        "Check whether the unused leaf subclasses are needed or whether instances should use them.",
        RuleScope.TERM,
    ),
    _spec(
        "CLS013",
        "Miscellaneous remainder class",
        Severity.INFO,
        "Replace the catch-all 'Other' subclass with specific classes or an open-world note on its parent.",
        RuleScope.TERM,
    ),
    _spec(
        "CLS014",
        "Class below two asserted-disjoint classes",
        Severity.WARNING,
        "Remove one of the superclass assertions or the disjointness; the class cannot have instances.",
        RuleScope.TERM,
    ),
    _spec(
        "CLS016",
        "Generic is-a style property",
        Severity.INFO,
        "Use rdfs:subClassOf or rdf:type, or a semantically specific property, instead of a generic 'is' property.",
        RuleScope.TERM,
    ),
    _spec(
        "CLS018",
        "Redundant owl:Thing superclass",
        Severity.INFO,
        "Drop the explicit owl:Thing or rdfs:Resource superclass; the class already has another superclass.",
        RuleScope.TERM,
    ),
    _spec(
        "CLS019",
        "Class asserted equal to or below owl:Nothing",
        Severity.WARNING,
        "Remove the owl:Nothing assertion or the class if it is not meant to be unsatisfiable.",
        RuleScope.TERM,
    ),
    _spec(
        "CLS020",
        "Subclass labelled like its superclass",
        Severity.INFO,
        "Give the subclass a label that says how it specializes its superclass.",
        RuleScope.TERM,
    ),
    _spec(
        "CLS021",
        "Equivalent class that is also an asserted ancestor",
        Severity.INFO,
        "Check whether the subclass chain between equivalent classes is intended; it collapses the chain.",
        RuleScope.TERM,
    ),
    _spec(
        "CLS025",
        "Instance typed with a class and its ancestor",
        Severity.INFO,
        "Remove the redundant type assertion for the ancestor class.",
        RuleScope.TERM,
    ),
)


@dataclass(frozen=True)
class Hierarchy:
    """Asserted subclass edges between declared classes (self-loops dropped)."""

    supers: Mapping[URIRef, frozenset[URIRef]]
    children: Mapping[URIRef, frozenset[URIRef]]

    @classmethod
    def build(cls, ctx: RuleContext) -> Hierarchy:
        """Index ``rdfs:subClassOf`` between declared classes once."""
        supers: dict[URIRef, set[URIRef]] = defaultdict(set)
        children: dict[URIRef, set[URIRef]] = defaultdict(set)
        for child, parent in directed_edges(ctx.g, RDFS.subClassOf, ctx.classes):
            if child != parent:
                supers[child].add(parent)
                children[parent].add(child)
        return cls(
            {k: frozenset(v) for k, v in supers.items()},
            {k: frozenset(v) for k, v in children.items()},
        )

    def edges(self) -> Iterator[tuple[URIRef, URIRef]]:
        """Yield ``(child, parent)`` pairs."""
        for child, parents in self.supers.items():
            for parent in parents:
                yield child, parent

    def ancestors(self, start: URIRef) -> set[URIRef]:
        """Return every class reachable upward from ``start`` (``start`` only when it lies on a cycle)."""
        seen: set[URIRef] = set()
        queue = deque([start])
        while queue:
            for parent in self.supers.get(queue.popleft(), ()):
                if parent not in seen:
                    seen.add(parent)
                    queue.append(parent)
        return seen


def run(ctx: RuleContext) -> None:
    """Run every implemented hierarchy-quality rule."""
    hierarchy = Hierarchy.build(ctx)
    _wide_fan_out(ctx, hierarchy)
    _unused_leaves(ctx, hierarchy)
    _remainder_classes(ctx, hierarchy)
    _disjoint_conflicts(ctx, hierarchy)
    _generic_is_properties(ctx)
    _top_and_bottom(ctx)
    _same_label_as_parent(ctx, hierarchy)
    _equivalent_ancestors(ctx, hierarchy)
    _redundant_types(ctx, hierarchy)


def _has_instance(ctx: RuleContext, cls: URIRef) -> bool:
    return bool(ctx.context.subjects_by_type.get(cls))


def _wide_fan_out(ctx: RuleContext, h: Hierarchy) -> None:
    for parent in sorted(h.children, key=str):
        kids = h.children[parent]
        if len(kids) > EXCESSIVE_SUBCLASS_COUNT:
            ctx.add("CLS011", parent, f"{len(kids)} direct subclasses (threshold {EXCESSIVE_SUBCLASS_COUNT}).")


def _unused_leaves(ctx: RuleContext, h: Hierarchy) -> None:
    for parent in sorted(h.children, key=str):
        kids = h.children[parent]
        if _has_instance(ctx, parent) and all(not h.children.get(k) and not _has_instance(ctx, k) for k in kids):
            ctx.add("CLS012", parent, f"Class has instances but its {len(kids)} subclass(es) are unused leaves.")


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(t.lower() for t in TOKEN.findall(text))


def _names(ctx: RuleContext, cls: URIRef) -> list[tuple[str, ...]]:
    """Token sequences of the local name and of every plain label of ``cls``."""
    names = [_tokens(local_name(cls))]
    for predicate in LABEL_PREDICATES:
        names += [_tokens(str(o)) for o in ctx.g.objects(cls, predicate) if isinstance(o, Literal)]
    return [n for n in names if n]


def _is_remainder(name: tuple[str, ...], parent_tokens: set[str]) -> bool:
    if not REMAINDER_MARKERS.intersection(name):
        return False
    rest = set(name) - REMAINDER_MARKERS - FILLER_TOKENS
    return rest <= parent_tokens


def _remainder_classes(ctx: RuleContext, h: Hierarchy) -> None:
    for cls in sorted(h.supers, key=str):
        names = _names(ctx, cls)
        if not any(REMAINDER_MARKERS.intersection(n) for n in names):
            continue
        for parent in sorted(h.supers[cls], key=str):
            parent_tokens = {t for n in _names(ctx, parent) for t in n}
            if any(_is_remainder(n, parent_tokens) for n in names):
                ctx.add("CLS013", cls, f"Catch-all subclass of {parent}.")
                break


def _disjoint_pairs(ctx: RuleContext) -> set[tuple[URIRef, URIRef]]:
    """Return asserted disjoint class pairs (both orders are folded into sorted order)."""
    pairs: set[tuple[URIRef, URIRef]] = set()
    for a, b in ctx.g.subject_objects(OWL.disjointWith):
        if isinstance(a, URIRef) and isinstance(b, URIRef) and a in ctx.classes and b in ctx.classes and a != b:
            # gremlin: pardon[equivalent] a != b is guarded above, so str(a) == str(b) cannot occur
            pairs.add((a, b) if str(a) < str(b) else (b, a))
    for group in ctx.g.subjects(RDF.type, OWL.AllDisjointClasses):
        head = next(iter(ctx.g.objects(group, OWL.members)), None)
        members = list_items(ctx.g, head, limit=MAX_DISJOINT_MEMBERS) if head is not None else None
        distinct = sorted({m for m in members or () if m in ctx.classes}, key=str)
        pairs.update(
            (a, b)
            for i, a in enumerate(distinct)
            for b in distinct[i + 1 :]
            # gremlin: pardon[equivalent] distinct is filtered by ctx.classes; the check only narrows the type
            if isinstance(a, URIRef) and isinstance(b, URIRef)
        )
    return pairs


def _ancestor_masks(classes: Iterable[URIRef], h: Hierarchy, bits: Mapping[URIRef, int]) -> dict[URIRef, int]:
    """Bit mask of the disjointness-relevant classes at or above each class (parents are visited first)."""
    components = strongly_connected_components(classes, h.edges())
    masks: dict[URIRef, int] = {}
    for component in components:
        mask = 0
        for member in component:
            mask |= 1 << bits[member] if member in bits else 0
            for parent in h.supers.get(member, ()):
                if parent not in component:
                    mask |= masks[parent]
        masks.update(dict.fromkeys(component, mask))
    return masks


def _set_bits(mask: int) -> Iterator[int]:
    while mask:
        low = mask & -mask
        yield low.bit_length() - 1
        mask ^= low


def _disjoint_conflicts(ctx: RuleContext, h: Hierarchy) -> None:
    pairs = _disjoint_pairs(ctx)
    if not pairs:
        return
    involved = sorted({c for pair in pairs for c in pair}, key=str)
    bits = {c: i for i, c in enumerate(involved)}
    partners: dict[int, int] = defaultdict(int)
    for a, b in pairs:
        partners[bits[a]] |= 1 << bits[b]
        partners[bits[b]] |= 1 << bits[a]
    masks = _ancestor_masks(ctx.classes, h, bits)

    def clash(cls: URIRef) -> tuple[int, int] | None:
        mask = masks[cls]
        for bit in _set_bits(mask):
            hit = partners[bit] & mask
            if hit:
                return bit, next(_set_bits(hit))
        return None

    for cls in sorted(ctx.classes, key=str):
        found = clash(cls)
        if found and not any(clash(parent) for parent in h.supers.get(cls, ())):
            ctx.add(
                "CLS014",
                cls,
                f"Below disjoint classes {involved[found[0]]} and {involved[found[1]]}.",
                confidence="certain",
            )


def _generic_is_properties(ctx: RuleContext) -> None:
    for prop in sorted(ctx.properties, key=str):
        if ctx.local(prop) and _tokens(local_name(prop)) in GENERIC_IS_NAMES:
            ctx.add("CLS016", prop, "Generic 'is' property; prefer rdf:type, rdfs:subClassOf or a specific relation.")


def _top_and_bottom(ctx: RuleContext) -> None:
    for cls in sorted(ctx.classes, key=str):
        parents = set(ctx.g.objects(cls, RDFS.subClassOf))
        if parents & TOP_CLASSES and parents - TOP_CLASSES - {cls}:
            ctx.add("CLS018", cls, "Explicit owl:Thing/rdfs:Resource superclass next to another superclass.")
        if OWL.Nothing in parents or OWL.Nothing in set(ctx.g.objects(cls, OWL.equivalentClass)):
            ctx.add("CLS019", cls, "Class is asserted below or equivalent to owl:Nothing.", confidence="certain")


def _label_keys(ctx: RuleContext, cls: URIRef) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for predicate in LABEL_PREDICATES:
        for o in ctx.g.objects(cls, predicate):
            if isinstance(o, Literal) and str(o).strip():
                keys.add(((o.language or "").lower(), " ".join(str(o).casefold().split())))
    return keys


def _same_label_as_parent(ctx: RuleContext, h: Hierarchy) -> None:
    for child, parent in sorted(h.edges(), key=str):
        same = _label_keys(ctx, child) & _label_keys(ctx, parent)
        if same:
            ctx.add("CLS020", child, f"Same label as its superclass {parent}.")


def _equivalent_ancestors(ctx: RuleContext, h: Hierarchy) -> None:
    seen: set[frozenset[URIRef]] = set()
    for a, b in sorted(ctx.g.subject_objects(OWL.equivalentClass), key=str):
        # gremlin: pardon[equivalent] ancestors hold only declared classes, so no extra CLS021
        if not (isinstance(a, URIRef) and isinstance(b, URIRef) and a != b and a in ctx.classes and b in ctx.classes):
            continue
        key = frozenset((a, b))
        if key in seen:
            continue
        seen.add(key)
        for low, high in ((a, b), (b, a)):
            if high in h.ancestors(low):
                ctx.add("CLS021", low, f"Equivalent to its asserted ancestor {high}.")


def _multi_typed(ctx: RuleContext) -> dict[URIRef, frozenset[URIRef]]:
    result: dict[URIRef, frozenset[URIRef]] = {}
    for subject, types in ctx.context.types_by_subject.items():
        # gremlin: pardon[equivalent] ctx.classes holds only URIRefs; the isinstance check only narrows the type
        declared = frozenset(t for t in types if isinstance(t, URIRef) and t in ctx.classes)
        if isinstance(subject, URIRef) and len(declared) > 1 and subject not in ctx.classes:
            result[subject] = declared
    return result


def _redundant_types(ctx: RuleContext, h: Hierarchy) -> None:
    typed = _multi_typed(ctx)
    relevant: set[URIRef] = set().union(*typed.values()) if typed else set()
    above: dict[URIRef, set[URIRef]] = {c: h.ancestors(c) & relevant for c in sorted(relevant, key=str)}
    for subject in sorted(typed, key=str):
        for cls in sorted(typed[subject], key=str):
            for ancestor in sorted(above[cls] & typed[subject] - {cls}, key=str):
                ctx.add("CLS025", subject, f"Typed {cls} and its ancestor {ancestor}.")
