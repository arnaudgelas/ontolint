"""Class-quality heuristics CLS010, CLS015, CLS017, CLS022, CLS023 and CLS024.

Every rule reads the *asserted* graph over declared classes: no entailment, no imports, no network.
They complement ``classes`` (CLS001-009) and ``hierarchy_quality`` (CLS011-014, 016, 018-021, 025)
and do not repeat their checks.  A *class* is an owned subject typed ``owl:Class`` or ``rdfs:Class``; a
*sibling* is a class with a subclass edge (an asserted ``rdfs:subClassOf`` between two classes, self-loops
dropped) to the same parent.  A *name* is the local name of the IRI (its last segment after ``/`` or ``#``),
split into lower-cased tokens at case changes, digits, ``_`` and ``-``.  A *label key* is the pair of the
lower-cased language tag and the case-folded text with its inner whitespace collapsed, of a literal that is not
blank.  Every finding is ``heuristic``.  The standards are RDF Schema 1.1 (``rdfs:label`` has the range
``rdfs:Literal``) and OWL 2 punning (an IRI may be a class and an individual); the rules are otherwise
conventions.  Specifications:

* **CLS010.** Two or more siblings of one parent that share a label key among their main labels
  (``RuleContext.main_label_predicates``, as LEX004 reads them).  One finding per sibling and parent, subject
  the parent, the language and the text.  Excluded: labels in different languages, blank labels, two labels of
  one class, an ``skos:altLabel``, siblings of different parents.  The datatype is ignored and a deprecated
  sibling is judged (gap: LEX004 exempts it).  A class below two parents is compared under each.  Warning: two
  sibling classes that cannot be told apart by their label are most probably one class twice.
* **CLS015.** A parent with at least ``MINIMUM_UNLABELLED_PARENT_SUBCLASSES`` (3) subclasses and no
  non-blank literal under any label predicate (``RuleContext.labels``, as LEX001 reads them).  An IRI value, a
  blank label and an alt label are no label; a deprecated parent is judged (gap: LEX001 exempts it).  Info: a
  label is optional in RDFS but a class that heads a subtree is the one readers meet first.
* **CLS017.** An owned class typed ``owl:NamedIndividual``, or typed by a declared class that is not a metaclass
  (a class below ``rdfs:Class``).  This judges the typing only (gap: OWL 2 punning also makes an IRI an
  individual where it is the subject or the object of a property assertion, which is not read).  A type that is
  not a declared class, ``owl:Thing`` and the other builtin types are excluded.  Info: punning is legal in
  OWL 2 DL but often a modelling slip.
* **CLS022.** An owned class whose name starts with ``has``, ``is``, ``was``, ``can`` or ``does`` in lower case,
  followed by an upper-case letter or a digit, or by ``_`` or ``-`` and a letter or a digit (``hasPart``,
  ``is_a``).  A bare ``has``, an
  initial capital and a longer word (``Hashing``, ``Island``) are excluded.  Info: a convention that a class
  names a thing and a property names a relation.
* **CLS023.** An owned class whose name has ``and`` or ``or`` as a token that is neither the first nor the last
  (``CatAndDog``, ``cat_and_dog``, ``CAT_AND_DOG``).  Only the local name is read.  A fixed expression
  (``BedAndBreakfast``) is a finding (gap).  Info: the suggestion is a convention, a union or an intersection.
* **CLS024.** A parent whose name has at least one token and at least ``MINIMUM_NAMING_SIBLINGS`` (4) subclasses,
  exactly one of which does not have a name of at least ``MINIMUM_NAME_TOKENS`` (2) tokens ending in the
  parent's last token.  The outlier is reported, the subject is the parent.  Labels are not read and no
  plural is stemmed (gap).  Info: a naming convention, a different name may be right.

Fixtures: ``tests/rule_cases/class_heuristics.py``, ``tests/test_mutation_class_heuristics.py`` and
``tests/test_cls_specification.py``.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable
from typing import TYPE_CHECKING

from rdflib import Literal, URIRef
from rdflib.namespace import OWL, RDFS
from rdflib.term import Node

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


def _label_keys(ctx: RuleContext, cls: URIRef, predicates: tuple[URIRef, ...]) -> set[LabelKey]:
    """Return ``(language, normalized text)`` for every non-blank plain label of ``cls`` under ``predicates``.

    CLS010 compares the main labels (``ctx.main_label_predicates``), as LEX004 does; CLS015 asks
    whether the class has any label (``ctx.labels``, the closure), as LEX001 does.
    """
    keys: set[LabelKey] = set()
    for predicate in predicates:
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
            labels[cls] = _label_keys(ctx, cls, ctx.main_label_predicates(cls))
        return labels[cls]

    for parent in sorted(children, key=str):
        kids = sorted(children[parent], key=str)
        _sibling_labels(ctx, parent, kids, keys)
        _unlabelled_parent(ctx, parent, kids)
        _sibling_naming(ctx, parent, kids)
    plain_classes = ctx.classes - _metaclasses(ctx)  # computed once: per class it made CLS017 quadratic
    for cls in sorted(ctx.classes, key=str):
        _punned(ctx, cls, plain_classes)
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
                ctx.add(
                    "CLS010",
                    kid,
                    f"Shares label {key[1]!r} with sibling {other} under {parent}.",
                    subject=(parent, *key),
                )


def _unlabelled_parent(ctx: RuleContext, parent: URIRef, kids: list[URIRef]) -> None:
    if len(kids) >= MINIMUM_UNLABELLED_PARENT_SUBCLASSES and not _label_keys(ctx, parent, ctx.labels):
        ctx.add("CLS015", parent, f"Class has {len(kids)} direct subclasses but no label.", subject=())


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
            subject=(parent,),
        )


def _ends_with_head(name: tuple[str, ...], head: str) -> bool:
    return len(name) >= MINIMUM_NAME_TOKENS and name[-1] == head


def _metaclasses(ctx: RuleContext) -> set[URIRef]:
    """Return classes that are (transitively) subclasses of ``rdfs:Class`` (e.g. ``schema:DataType``)."""
    found: set[URIRef] = set()
    todo: list[Node] = [RDFS.Class]
    while todo:
        for child in ctx.g.subjects(RDFS.subClassOf, todo.pop()):
            if isinstance(child, URIRef) and child not in found:
                found.add(child)
                todo.append(child)
    return found


def _punned(ctx: RuleContext, cls: URIRef, plain_classes: frozenset[URIRef]) -> None:
    """``plain_classes`` are the classes that are not metaclasses; typing ``cls`` by one is punning."""
    other = ctx.context.types_by_subject.get(cls, frozenset()).difference(CLASS_TYPES)
    if OWL.NamedIndividual in other or other & plain_classes:
        ctx.add("CLS017", cls, "Class is also typed as an individual (punning).")


def _name_shape(ctx: RuleContext, cls: URIRef) -> None:
    name = local_name(cls)
    if PROPERTY_LIKE_NAME.match(name):
        ctx.add("CLS022", cls, f"Local name '{name}' looks like a property name.", subject=())
    tokens = _tokens(name)
    if any(t in CONJUNCTIONS for t in tokens[1:-1]):
        ctx.add("CLS023", cls, f"Local name '{name}' joins concepts with a conjunction.", subject=())
