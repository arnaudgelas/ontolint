"""Class-quality heuristics CLS010, CLS015, CLS017, CLS022, CLS023 and CLS024.

Every rule reads the *asserted* graph over declared classes: no entailment, no imports, no network.
They complement ``classes`` (CLS001-009) and ``hierarchy_quality`` (CLS011-014, 016, 018-021, 025)
and do not repeat their checks.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable
from typing import TYPE_CHECKING

from rdflib import Literal, URIRef
from rdflib.namespace import OWL, RDFS

from ontolint.context import CLASS_TYPES
from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity

from .support import directed_edges, local_name

if TYPE_CHECKING:
    from .runtime import RuleContext

# An unlabelled class needs at least this many direct subclasses to be reported (CLS015).
MINIMUM_UNLABELLED_PARENT_SUBCLASSES = 3
# A parent needs at least this many direct subclasses for sibling naming comparisons (CLS024).
MINIMUM_NAMING_SIBLINGS = 4
# A specialised name has a modifier plus the head token (CLS024).
MINIMUM_NAME_TOKENS = 2

TOKEN = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
PROPERTY_LIKE_NAME = re.compile(r"(?:has|is|was|can|does)(?:[A-Z0-9]|[_-][A-Za-z0-9])")
CONJUNCTIONS = frozenset({"and", "or"})

type LabelKey = tuple[str, str]
type LabelLookup = Callable[[URIRef], set[LabelKey]]


def _spec(rule_id: str, title: str, severity: Severity, suggestion: str) -> RuleSpec:
    return RuleSpec(
        rule_id,
        "CLS",
        title,
        severity,
        suggestion,
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "class_heuristics",
    )


SPECS: tuple[RuleSpec, ...] = (
    _spec(
        "CLS010",
        "Sibling classes with identical labels",
        Severity.WARNING,
        "Give each sibling class a distinct label, or merge the classes if they mean the same thing.",
    ),
    _spec(
        "CLS015",
        "Unlabelled class with several subclasses",
        Severity.INFO,
        "Add an rdfs:label or skos:prefLabel to the class that heads a subtree.",
    ),
    _spec(
        "CLS017",
        "Class also used as an individual",
        Severity.INFO,
        "Check whether the class/individual punning is intended; otherwise model the individual separately.",
    ),
    _spec(
        "CLS022",
        "Class named like a property",
        Severity.INFO,
        "Name classes with nouns; a has/is-style name usually denotes a property.",
    ),
    _spec(
        "CLS023",
        "Class name encodes a conjunction",
        Severity.INFO,
        "Split the class, or use owl:unionOf / owl:intersectionOf instead of 'And'/'Or' in the name.",
    ),
    _spec(
        "CLS024",
        "Sibling class breaking the naming pattern",
        Severity.INFO,
        "Check whether the class belongs under this parent or should follow its siblings' naming pattern.",
    ),
)


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(t.lower() for t in TOKEN.findall(text))


def _label_keys(ctx: RuleContext, cls: URIRef) -> set[LabelKey]:
    """Return ``(language, normalized text)`` for every non-blank plain label of ``cls``."""
    keys: set[LabelKey] = set()
    for predicate in ctx.labels:
        for o in ctx.g.objects(cls, predicate):
            if isinstance(o, Literal) and str(o).strip():
                keys.add(((o.language or "").lower(), " ".join(str(o).casefold().split())))
    return keys


def run(ctx: RuleContext) -> None:
    """Run every class-heuristic rule."""
    children: defaultdict[URIRef, set[URIRef]] = defaultdict(set)
    for child, parent in directed_edges(ctx.g, RDFS.subClassOf, ctx.classes):
        if child != parent:
            children[parent].add(child)
    labels: dict[URIRef, set[LabelKey]] = {}

    def keys(cls: URIRef) -> set[LabelKey]:
        if cls not in labels:
            labels[cls] = _label_keys(ctx, cls)
        return labels[cls]

    for parent in sorted(children, key=str):
        kids = sorted(children[parent], key=str)
        _sibling_labels(ctx, parent, kids, keys)
        _unlabelled_parent(ctx, parent, kids, keys)
        _sibling_naming(ctx, parent, kids)
    for cls in sorted(ctx.classes, key=str):
        _punned(ctx, cls)
        _name_shape(ctx, cls)


def _sibling_labels(ctx: RuleContext, parent: URIRef, kids: list[URIRef], keys: LabelLookup) -> None:
    by_key: dict[LabelKey, list[URIRef]] = defaultdict(list)
    for kid in kids:
        for key in keys(kid):
            by_key[key].append(kid)
    for key in sorted(by_key):
        group = by_key[key]
        if len(group) > 1:
            for kid in group:
                other = next(k for k in group if k != kid)
                ctx.add("CLS010", kid, f"Shares label {key[1]!r} with sibling {other} under {parent}.")


def _unlabelled_parent(ctx: RuleContext, parent: URIRef, kids: list[URIRef], keys: LabelLookup) -> None:
    if len(kids) >= MINIMUM_UNLABELLED_PARENT_SUBCLASSES and not keys(parent):
        ctx.add("CLS015", parent, f"Class has {len(kids)} direct subclasses but no label.")


def _sibling_naming(ctx: RuleContext, parent: URIRef, kids: list[URIRef]) -> None:
    if len(kids) < MINIMUM_NAMING_SIBLINGS:
        return
    head = _tokens(local_name(parent))
    if not head:
        return
    outliers = [k for k in kids if not _ends_with_head(_tokens(local_name(k)), head[-1])]
    if len(outliers) == 1:
        ctx.add(
            "CLS024",
            outliers[0],
            f"Name does not end in '{head[-1]}' like its {len(kids) - 1} siblings under {parent}.",
        )


def _ends_with_head(name: tuple[str, ...], head: str) -> bool:
    return len(name) >= MINIMUM_NAME_TOKENS and name[-1] == head


def _punned(ctx: RuleContext, cls: URIRef) -> None:
    other = ctx.context.types_by_subject.get(cls, frozenset()).difference(CLASS_TYPES)
    if OWL.NamedIndividual in other or other & ctx.classes:
        ctx.add("CLS017", cls, "Class is also typed as an individual (punning).")


def _name_shape(ctx: RuleContext, cls: URIRef) -> None:
    name = local_name(cls)
    if PROPERTY_LIKE_NAME.match(name):
        ctx.add("CLS022", cls, f"Local name '{name}' looks like a property name.")
    tokens = _tokens(name)
    if any(t in CONJUNCTIONS for t in tokens[1:-1]):
        ctx.add("CLS023", cls, f"Local name '{name}' joins concepts with a conjunction.")
