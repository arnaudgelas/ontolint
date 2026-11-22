"""Class-hierarchy quality rules CLS011-CLS014, CLS016, CLS018-CLS021 and CLS025.

Every rule reads the *asserted* ``rdfs:subClassOf`` graph over declared classes: no entailment,
no imports, no network.  Graph walks are iterative (hierarchies of 100k classes must not recurse).
CLS010, CLS015, CLS017 and CLS022-CLS024 live in ``class_heuristics``.  A *class* is an owned subject typed
``owl:Class`` or ``rdfs:Class``; a *subclass edge* is an asserted ``rdfs:subClassOf`` between two classes, with
self-loops dropped; an *ancestor* is a class reached by one or more edges.  A *label key* is the pair of the
lower-cased language tag and the case-folded text with its inner whitespace collapsed, of a non-blank literal
under ``rdfs:label`` or ``skos:prefLabel`` (only these two, not a configured extra).  Every finding is
``heuristic`` unless said otherwise, and the category of every rule in the catalogue is ``heuristic``.  The
standards are the OWL 2 Structural Specification (5.1 ``owl:Thing`` and ``owl:Nothing``, 9.1.2
EquivalentClasses, 9.1.3 DisjointClasses, 9.1.4 DisjointUnion) and RDF Schema 1.1 with the RDF 1.1 Semantics
entailment patterns (rdfs9, rdfs11); thresholds are conventions and sit on ``Policy``.  Specifications:

* **CLS011.** An owned class with more than ``Policy.subclass_limit`` (50) subclass edges below it.  A foreign or
  an undeclared subclass is not counted.  Info: a flat fan-out is hard to browse but may be legitimate.
* **CLS012.** An owned class that is the type of a subject (a class typed by it counts) all of whose subclasses
  are leaves (no subclass below) that are the type of no subject; at least one subclass.  A deprecated leaf is
  unused (gap: CLS001 exempts deprecated classes).  Info: the leaves may be there for later use.
* **CLS013.** An owned class with a declared parent (a subclass edge leaving it) whose names (its local name and
  every ``rdfs:label`` and ``skos:prefLabel`` literal, in any language) hold a marker token (``other``,
  ``others``, ``misc``, ``miscellaneous``, ``remainder``, ``unclassified``, ``uncategorized``, ``uncategorised``,
  ``unspecified``) and, without the markers and the filler tokens (``and``, ``of``, ``the``, ``a``, ``an``,
  ``or``, ``else``, ``type``, ``types``, ``kind``, ``kinds``), only tokens of a name of the parent; the first
  parent by IRI that satisfies this is named.  A marker alone (``Other``) qualifies under any parent; a plural or
  an accent does not match (gap); a class below ``owl:Thing`` only has no declared parent.  Info: a catch-all
  class is a modelling choice that OWL's open world makes unnecessary.
* **CLS014.** A class that is at or below two classes declared pairwise disjoint (``owl:disjointWith`` in
  either direction, or two members of an ``owl:AllDisjointClasses`` list under ``owl:members``, at most
  ``MAX_DISJOINT_MEMBERS`` of them), through the subclass edges (9.1.3).  Reported at the topmost class only: not
  when a parent already clashes.  A subclass cycle is judged as one class and reported at its first member
  unless a parent outside the cycle clashes.  Not read (gaps): ``owl:disjointUnionOf`` (9.1.4), an
  equivalent class's disjointness (9.1.2), a class disjoint with itself, an undeclared ancestor.  Confidence
  ``certain``.  Warning: such a class cannot have an instance, which is an unsatisfiable class, not a style
  point.
* **CLS016.** An owned property (any kind, an annotation property included) whose name is one of ``is``, ``isa``,
  ``is a``, ``is an``, ``is kind of``, ``is type of``, ``is a kind of`` as a token sequence, in any case and
  style (``isA``, ``is_a``).  Only the local name is read.  Info: a generic relation says nothing; use
  ``rdf:type``, ``rdfs:subClassOf`` or a specific property.
* **CLS018.** An owned class with ``rdfs:subClassOf owl:Thing`` or ``rdfs:Resource`` and at least one other object
  of ``rdfs:subClassOf`` that is not the class itself (a restriction, a foreign class and ``owl:Nothing``
  count; an equivalent class does not).  Every class is below ``owl:Thing`` (5.1).  Info: redundant, not wrong.
* **CLS019.** An owned class that is the object of ``rdfs:subClassOf owl:Nothing`` or either end of an
  ``owl:equivalentClass`` triple whose other end is ``owl:Nothing``, the triple having no direction (9.1.2).
  Not read (gaps): a class below an empty class, disjoint with ``owl:Thing``, or equivalent to its complement.
  Confidence ``certain``.  Warning: the class is empty by assertion.
* **CLS020.** A subclass edge whose two classes share a label key, the subject being the parent.  The datatype
  is ignored; an ``rdfs:label`` of one matches an ``skos:prefLabel`` of the other; only direct edges, and the
  members of a cycle are each other's parent.  Info: a subclass should say how it specialises.
* **CLS021.** A pair of distinct owned classes asserted ``owl:equivalentClass`` (in either direction) of which
  one is an ancestor of the other by the subclass edges (9.1.2); the finding is the lower class, the subject the
  higher.  Two classes that are each other's ancestor are both reported.  An ancestor path through an
  undeclared class is not seen (gap).  Info: the chain between them collapses, which may be intended.
* **CLS025.** A resource that is not a class, typed by two or more owned classes of which one is an ancestor of
  another (rdfs9); one finding per (class, ancestor) pair, so a chain of three types gives three.  A blank node
  and a class are excluded; an undeclared ancestor, an equivalent class and ``owl:Thing`` are not followed
  (gaps).  Info: the ancestor type is entailed.

Fixtures: ``tests/rule_cases/hierarchy_quality.py``, ``tests/test_coverage_hierarchy_quality.py``,
``tests/test_mutation_hierarchy.py`` and ``tests/test_cls_specification.py``.
"""

from __future__ import annotations

import re
from collections import defaultdict, deque
from collections.abc import Iterable, Iterator, Mapping, Set
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rdflib import Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from ontolint.graph import strongly_connected_components
from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity

from .support import directed_edges, list_items, local_name

if TYPE_CHECKING:
    from .runtime import RuleContext

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


_EXACT = frozenset({"CLS014", "CLS019"})
"""The rules whose condition is exact and forbidden or given a fixed meaning by the cited specification: their findings
are ``certain``, so their category is ``deterministic`` (decision D1 of ``docs/severity-decisions.md``, issue #180)."""


def _spec(rule_id: str, title: str, severity: Severity, suggestion: str, scope: RuleScope) -> RuleSpec:
    category = "deterministic" if rule_id in _EXACT else "heuristic"
    return RuleSpec(
        rule_id, "CLS", title, severity, suggestion, category, RuleBackend.RDFLIB, scope, "hierarchy_quality"
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
    limit = ctx.policy.subclass_limit
    for parent in sorted(h.children, key=str):
        kids = h.children[parent]
        if len(kids) > limit:
            ctx.add("CLS011", parent, f"{len(kids)} direct subclasses (threshold {limit}).", subject=())


def _unused_leaves(ctx: RuleContext, h: Hierarchy) -> None:
    for parent in sorted(h.children, key=str):
        kids = h.children[parent]
        if _has_instance(ctx, parent) and all(not h.children.get(k) and not _has_instance(ctx, k) for k in kids):
            ctx.add(
                "CLS012", parent, f"Class has instances but its {len(kids)} subclass(es) are unused leaves.", subject=()
            )


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
                ctx.add("CLS013", cls, f"Catch-all subclass of {parent}.", subject=())
                break


def _disjoint_pairs(ctx: RuleContext) -> set[tuple[URIRef, URIRef]]:
    """Return asserted disjoint class pairs (both orders are folded into sorted order)."""
    pairs: set[tuple[URIRef, URIRef]] = set()
    for a, b in ctx.g.subject_objects(OWL.disjointWith):
        if isinstance(a, URIRef) and isinstance(b, URIRef) and a in ctx.classes and b in ctx.classes and a != b:
            low, high = sorted((a, b), key=str)
            pairs.add((low, high))
    for group in ctx.g.subjects(RDF.type, OWL.AllDisjointClasses):
        head = next(iter(ctx.g.objects(group, OWL.members)), None)
        members = list_items(ctx.g, head, limit=MAX_DISJOINT_MEMBERS) if head is not None else None
        distinct = sorted(ctx.classes.intersection(members or ()), key=str)
        pairs.update((a, b) for i, a in enumerate(distinct) for b in distinct[i + 1 :])
    return pairs


def _ancestor_masks(components: Iterable[Set[URIRef]], h: Hierarchy, bits: Mapping[URIRef, int]) -> dict[URIRef, int]:
    """Bit mask of the disjointness-relevant classes at or above each class (parents are visited first)."""
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
    components = strongly_connected_components(ctx.classes, h.edges())
    masks = _ancestor_masks(components, h, bits)

    def clash(cls: URIRef) -> tuple[int, int] | None:
        mask = masks[cls]
        for bit in _set_bits(mask):
            hit = partners[bit] & mask
            if hit:
                return bit, next(_set_bits(hit))
        return None

    # The members of a subclass cycle are equivalent (OWL 2 Structural Specification 9.1.2) and each is the other's
    # parent: the cycle is judged as one class, reported at its first member, unless a parent outside it clashes.
    for component in sorted(components, key=lambda members: min(map(str, members))):
        found = clash(next(iter(component)))
        outside = {parent for member in component for parent in h.supers.get(member, ()) if parent not in component}
        if found and not any(clash(parent) for parent in outside):
            ctx.add(
                "CLS014",
                min(component, key=str),
                f"Below disjoint classes {involved[found[0]]} and {involved[found[1]]}.",
                confidence="certain",
                subject=(),
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
        # owl:equivalentClass is symmetric (OWL 2 Structural Specification 9.1.2): either end may be owl:Nothing.
        equivalents = set(ctx.g.objects(cls, OWL.equivalentClass)) | set(ctx.g.subjects(OWL.equivalentClass, cls))
        if OWL.Nothing in parents or OWL.Nothing in equivalents:
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
            ctx.add("CLS020", child, f"Same label as its superclass {parent}.", subject=(parent,))


def _equivalent_ancestors(ctx: RuleContext, h: Hierarchy) -> None:
    seen: set[frozenset[URIRef]] = set()
    for a, b in sorted(ctx.g.subject_objects(OWL.equivalentClass), key=str):
        if not (isinstance(a, URIRef) and isinstance(b, URIRef) and a != b and a in ctx.classes and b in ctx.classes):
            continue
        key = frozenset((a, b))
        if key in seen:
            continue
        seen.add(key)
        for low, high in ((a, b), (b, a)):
            if high in h.ancestors(low):
                ctx.add("CLS021", low, f"Equivalent to its asserted ancestor {high}.", subject=(high,))


def _multi_typed(ctx: RuleContext) -> dict[URIRef, frozenset[URIRef]]:
    result: dict[URIRef, frozenset[URIRef]] = {}
    for subject, types in ctx.context.types_by_subject.items():
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
                ctx.add("CLS025", subject, f"Typed {cls} and its ancestor {ancestor}.", subject=(cls, ancestor))
