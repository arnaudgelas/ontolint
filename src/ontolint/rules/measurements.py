"""Named, versioned measurements of the asserted graph, which the METRIC rules threshold.

A measurement is one figure of the linted graph with an ID, a definition version, a kind (a ratio, a count
or a histogram) and a population.  The METRIC rules (:mod:`ontolint.rules.metrics`) take their values here
and keep only what is about thresholds: the limit, the ``metric_min_sample`` gate, the strict comparison
and the message.  Each measurement is computed once per :class:`~ontolint.rules.runtime.RuleContext`, on
first use, and cached in ``ctx.measured``, so a rule and anything reading the cache afterwards see the same
value; like :class:`~ontolint.context.GraphContext`, the cache assumes the graph does not change once the
context is built.  Nothing is entailed and no reasoner runs.  Under ``--follow-imports`` the graph is the
whole closure, as for the rules.  The catalogue (:data:`SPECS`), each population and its exclusions are
documented in ``docs/measurements.md``.  Every measurement keeps to these rules:

* A ratio is a numerator and a denominator, never the quotient alone; a mean is a ratio, the sum over the
  count.  The rules divide the same two integers they always divided, so every float they compare is the
  same.
* A measurement that cannot be taken is :class:`Absent`, with a reason, never 0.  :func:`require` raises
  :class:`MeasurementUnavailable` for it, so the METRIC module fails and the run exits 2; a rule asks before
  its sample gate, so an absent measurement never passes.  An empty population is taken: a ratio of 0
  over 0, an empty histogram, a count of 0.
* A computation that raises is not cached and its exception reaches the caller unchanged, so a failing
  METRIC module reports the exception as it always did.
* A value depends only on the graph, the shapes graph and the policy that shapes a population (``base``,
  ``extra_label_predicates``, ``extra_definition_predicates`` and the import closure); never on a
  threshold, the rule selection, a profile or a baseline.
* A numerator that a per-term rule also reports is *exactly* that rule's set, through the rule's own helper
  (LEX001's :func:`~ontolint.rules.lexical.is_unlabelled`, CLS001's
  :func:`~ontolint.rules.classes.orphan_classes`, OWL005's and OWL006's).
* Term-level values (which terms lack a definition) are kept here as sets, for the snapshot a later item
  builds; what is published holds counts only.
* A change to what a measurement counts, a bug fix included, increments its definition version.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Set
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SH, XSD
from rdflib.term import Node

from ontolint.graph import hierarchy_depths, weakly_connected_components
from ontolint.models import Measurement, MeasurementKind
from ontolint.ownership import OwnershipMode
from ontolint.redaction import redact_userinfo

from .classes import orphan_classes
from .lexical import is_unlabelled
from .owl import annotation_only, lacks_domain, lacks_range, signature_exempt
from .shapes import class_target_reach
from .support import directed_edges

if TYPE_CHECKING:
    from .runtime import RuleContext

W3C_NAMESPACES = (str(OWL), str(RDF), str(RDFS), str(XSD))
SHACL_NS = str(SH)
WORD = re.compile(r"\w+")


@dataclass(frozen=True)
class TermRatio:
    """A ratio of two term sets: the terms that count, and the population (a numerator may be of other terms)."""

    numerator: frozenset[Node]
    denominator: frozenset[Node]


@dataclass(frozen=True)
class TermValues:
    """One integer per term of the population: a ratio (their sum over their count) or a histogram."""

    values: Mapping[Node, int]


@dataclass(frozen=True)
class CountRatio:
    """A ratio whose parts are not terms (references, subjects); ``by_namespace`` splits the numerator, if set."""

    numerator: int
    denominator: int
    by_namespace: tuple[tuple[str, int], ...] | None = None


@dataclass(frozen=True)
class Count:
    """A count of things that are not terms of the population (import IRIs, hierarchy components)."""

    value: int


@dataclass(frozen=True)
class Absent:
    """A measurement that could not be taken, and why: never published, nor read, as 0."""

    reason: str


type Value = TermRatio | TermValues | CountRatio | Count
"""A measurement that was taken."""


@dataclass(frozen=True)
class MeasurementSpec:
    """One measurement: its identity, what it counts over, and how it is computed."""

    id: str
    version: int
    """The definition version, incremented whenever what the measurement counts changes."""
    kind: MeasurementKind
    population: str
    """The name of what the denominator (a histogram's terms, a count's scope) counts."""
    compute: Callable[[RuleContext], Value | Absent]
    rules: tuple[str, ...] = ()
    """The METRIC rules that threshold it."""
    partitioned: bool = False
    """Whether its value is of owned terms, so a module, file or graph partition can restrict it (:func:`partition`)."""


class MeasurementUnavailable(Exception):
    """A rule needs a measurement that could not be taken; the text is ``<id>: <reason>``."""

    def __init__(self, measurement_id: str, reason: str) -> None:
        super().__init__(f"{measurement_id}: {reason}")
        self.measurement_id = measurement_id
        self.reason = reason


def spec_of(measurement_id: str) -> MeasurementSpec:
    """The catalogue entry of ``measurement_id``, looked up in :data:`SPECS` at call time; ``KeyError`` if none."""
    for spec in SPECS:
        if spec.id == measurement_id:
            return spec
    raise KeyError(measurement_id)


def measure(ctx: RuleContext, measurement_id: str) -> Value | Absent:
    """The value of ``measurement_id`` on ``ctx``, computed on first use and cached; an exception propagates."""
    if measurement_id not in ctx.measured:
        ctx.measured[measurement_id] = spec_of(measurement_id).compute(ctx)
    return ctx.measured[measurement_id]


def require(ctx: RuleContext, measurement_id: str) -> Value:
    """The value of ``measurement_id``; raises :class:`MeasurementUnavailable` when it could not be taken."""
    value = measure(ctx, measurement_id)
    if isinstance(value, Absent):
        raise MeasurementUnavailable(measurement_id, value.reason)
    return value


def ratio(ctx: RuleContext, measurement_id: str) -> tuple[int, int]:
    """``(numerator, denominator)`` of a ratio measurement (a mean's sum and count) that was taken."""
    return _parts(measurement_id, require(ctx, measurement_id))


def count(ctx: RuleContext, measurement_id: str) -> int:
    """The value of a count measurement that was taken."""
    return _count(measurement_id, require(ctx, measurement_id))


def _parts(measurement_id: str, value: Value) -> tuple[int, int]:
    if isinstance(value, TermRatio):
        return len(value.numerator), len(value.denominator)
    if isinstance(value, TermValues):
        return sum(value.values.values()), len(value.values)
    if isinstance(value, CountRatio):
        return value.numerator, value.denominator
    raise TypeError(f"{measurement_id} is a count, not a ratio")


def _count(measurement_id: str, value: Value) -> int:
    if not isinstance(value, Count):
        raise TypeError(f"{measurement_id} is not a count")
    return value.value


# --- publication ---------------------------------------------------------------------------------------------


def taken(ctx: RuleContext) -> tuple[tuple[MeasurementSpec, Value | Absent], ...]:
    """Every measurement of :data:`SPECS` on ``ctx``, in order; one whose computation raises is absent.

    The reason of such a failure is ``failed: <ExceptionType>: <message>``: publishing never fails a run, and a
    METRIC rule that read the measurement has already failed with the exception itself.
    """
    return tuple((spec, _safely(ctx, spec)) for spec in SPECS)


def _safely(ctx: RuleContext, spec: MeasurementSpec) -> Value | Absent:
    try:
        return measure(ctx, spec.id)
    except Exception as exc:  # noqa: BLE001 -- the published reason says what failed.
        return Absent(_failure(exc))


def _failure(exc: Exception) -> str:
    return f"failed: {type(exc).__name__}: {exc}"


def publish(ctx: RuleContext) -> tuple[Measurement, ...]:
    """The published record of every measurement on ``ctx``, in catalogue order; never raises."""
    return tuple(record(spec, value) for spec, value in taken(ctx))


def record(spec: MeasurementSpec, value: Value | Absent, terms: Set[Node] | None = None) -> Measurement:
    """The published record of ``value`` (restricted to ``terms`` if given): counts only, the term sets left out.

    A value that does not fit its kind, or that is not of terms when ``terms`` is given, is published as absent.
    """
    try:
        return _record(spec, value if terms is None else restrict(value, terms))
    except Exception as exc:  # noqa: BLE001 -- a value that does not fit its kind is published as absent.
        return Measurement(spec.id, spec.version, spec.kind, spec.population, reason=_failure(exc))


def partition_terms(ctx: RuleContext) -> dict[str, frozenset[Node]]:
    """The terms a partition places, by the text a finding about each has as its focus.

    They are the owned classes and properties, of which every partitioned population is.  IRIs that differ only
    in their userinfo share one text, as they share one finding.
    """
    texts: dict[str, set[Node]] = {}
    for term in owned_classes(ctx) | owned_properties(ctx):
        texts.setdefault(ctx._focus_text(term), set()).add(term)  # the focus text a finding about it has
    return {text: frozenset(terms) for text, terms in texts.items()}


def partition(vector: Iterable[tuple[MeasurementSpec, Value | Absent]], terms: Set[Node]) -> tuple[Measurement, ...]:
    """The partitioned measurements of ``vector`` (:func:`taken`) restricted to ``terms``, as published records.

    A partition restricts and never recomputes: each of its terms counts with its value in the whole file (a
    class's depth, a parent's number of subclasses), and an absent measurement is absent with the same reason.
    """
    return tuple(record(spec, value, terms) for spec, value in vector if spec.partitioned)


def restrict(value: Value | Absent, terms: Set[Node]) -> Value | Absent:
    """``value`` with only the terms of ``terms`` in its sets (both of a ratio's); an absent value stays absent."""
    if isinstance(value, Absent):
        return value
    if isinstance(value, TermRatio):
        return TermRatio(value.numerator & terms, value.denominator & terms)
    if isinstance(value, TermValues):
        return TermValues(MappingProxyType({term: n for term, n in value.values.items() if term in terms}))
    raise TypeError(f"a {type(value).__name__} is not of terms")


def _record(spec: MeasurementSpec, value: Value | Absent) -> Measurement:
    identity = (spec.id, spec.version, spec.kind, spec.population)
    if isinstance(value, Absent):
        return Measurement(*identity, reason=value.reason)
    if spec.kind is MeasurementKind.COUNT:
        return Measurement(*identity, value=_count(spec.id, value))
    if spec.kind is MeasurementKind.HISTOGRAM:
        if not isinstance(value, TermValues):
            raise TypeError(f"{spec.id} is not a histogram")
        return Measurement(*identity, buckets=tuple(sorted(Counter(value.values.values()).items())))
    numerator, denominator = _parts(spec.id, value)
    by_namespace = value.by_namespace if isinstance(value, CountRatio) else None
    return Measurement(*identity, numerator=numerator, denominator=denominator, by_namespace=by_namespace)


# --- populations -----------------------------------------------------------------------------------------------


def _local(ctx: RuleContext, terms: Iterable[URIRef]) -> frozenset[URIRef]:
    return frozenset(term for term in terms if ctx.local(term))


def owned_classes(ctx: RuleContext) -> frozenset[URIRef]:
    """The classes (``owl:Class``, ``rdfs:Class``) the linted ontology owns (see :mod:`ontolint.ownership`)."""
    return _local(ctx, ctx.classes)


def owned_properties(ctx: RuleContext) -> frozenset[URIRef]:
    """The properties the linted ontology owns, annotation properties and ``rdf:Property`` ones included."""
    return _local(ctx, ctx.properties)


def owned_signature_properties(ctx: RuleContext) -> frozenset[URIRef]:
    """The owned IRIs typed ``owl:ObjectProperty`` or ``owl:DatatypeProperty``: the ones a signature is for."""
    typed = ctx.context.subjects_by_type
    kinds = (OWL.ObjectProperty, OWL.DatatypeProperty)
    return _local(ctx, (p for kind in kinds for p in typed.get(kind, frozenset()) if isinstance(p, URIRef)))


# --- METRIC001-METRIC013 -----------------------------------------------------------------------------------------


def _class_label_coverage(ctx: RuleContext) -> TermRatio:
    """Owned classes LEX001 does not report: a ``Literal`` under ``ctx.labels``, or ``owl:deprecated true``."""
    classes = owned_classes(ctx)
    return TermRatio(frozenset(c for c in classes if not is_unlabelled(ctx, c)), classes)


def _documented(ctx: RuleContext, terms: frozenset[URIRef]) -> TermRatio:
    """``terms`` that are the subject of at least one ``ctx.descriptions`` predicate, any value."""
    having: set[Node] = set()
    for predicate in ctx.descriptions:
        having |= ctx.context.subjects_by_predicate.get(predicate, frozenset())
    return TermRatio(frozenset(term for term in terms if term in having), terms)


def _class_definition_coverage(ctx: RuleContext) -> TermRatio:
    return _documented(ctx, owned_classes(ctx))


def _property_documentation_coverage(ctx: RuleContext) -> TermRatio:
    return _documented(ctx, owned_properties(ctx))


@dataclass(frozen=True)
class _Hierarchy:
    parents: dict[URIRef, set[URIRef]]  # class -> asserted declared superclasses
    children: dict[URIRef, set[URIRef]]  # class -> asserted declared direct subclasses


def _hierarchy(ctx: RuleContext, classes: frozenset[URIRef]) -> _Hierarchy:
    parents: dict[URIRef, set[URIRef]] = defaultdict(set)
    children: dict[URIRef, set[URIRef]] = defaultdict(set)
    for child, parent in ctx.g.subject_objects(RDFS.subClassOf):
        if isinstance(child, URIRef) and isinstance(parent, URIRef) and child != parent:
            if child not in classes or parent not in classes:
                continue
            parents[child].add(parent)
            children[parent].add(child)
    return _Hierarchy(parents, children)


def _class_fanout(ctx: RuleContext) -> TermValues:
    """Per owned class with an owned direct subclass, how many it has (self-loops and external classes are not)."""
    children = _hierarchy(ctx, owned_classes(ctx)).children
    return TermValues(MappingProxyType({parent: len(kids) for parent, kids in children.items()}))


def _orphan_classes(ctx: RuleContext) -> TermRatio:
    """Owned classes CLS001 reports."""
    classes = owned_classes(ctx)
    return TermRatio(orphan_classes(ctx) & classes, classes)


def _relation_properties_per_class(ctx: RuleContext) -> TermRatio:
    """Owned properties that are not annotation-only, over the owned classes."""
    relations = frozenset(p for p in owned_properties(ctx) if not annotation_only(ctx.g, p))
    return TermRatio(relations, owned_classes(ctx))


def _unsigned_properties(ctx: RuleContext) -> TermRatio:
    """Owned object and datatype properties that OWL005 and OWL006 both report."""
    props = owned_signature_properties(ctx)
    unsigned = (p for p in props if not signature_exempt(ctx.g, p) and lacks_domain(ctx, p) and lacks_range(ctx, p))
    return TermRatio(frozenset(unsigned), props)


def _label_language_coverage(ctx: RuleContext) -> TermRatio:
    """Owned classes and properties with a language-tagged label, over those with any ``Literal`` label."""
    terms = owned_classes(ctx) | owned_properties(ctx)
    labelled: set[Node] = set()
    tagged: set[Node] = set()
    for predicate in ctx.labels:
        for subject, label in ctx.g.subject_objects(predicate):
            if subject in terms and isinstance(label, Literal):
                labelled.add(subject)
                if label.language:
                    tagged.add(subject)
    return TermRatio(frozenset(tagged), frozenset(labelled))


def _namespace(iri: str) -> str:
    text = str(iri)
    cut = max(text.rfind("#"), text.rfind("/"))
    return text[: cut + 1] if cut >= 0 else text


def _foreign(ctx: RuleContext, subject: URIRef, target: URIRef) -> bool:
    """Return whether ``target`` lies outside the subject's namespace and is not owned by the ontology.

    An ontology that owns several namespaces (a header or base covering them) refers to itself across
    them.  Without any ownership information (``OwnershipMode.ALL``) every IRI counts as owned, so the
    namespace comparison alone decides.
    """
    # One expression: an early ``return False`` read by an ``if`` would make its ``None`` mutant equivalent.
    return _namespace(target) != _namespace(subject) and (
        ctx.context.ownership.mode is OwnershipMode.ALL or not ctx.local(target)
    )


def _foreign_references(ctx: RuleContext) -> CountRatio:
    """Structural references (subClassOf, domain, range) from owned terms, and the foreign ones by namespace.

    A foreign target's namespace is cut from its masked spelling, so no namespace holds a userinfo, and two
    namespaces that differ only in theirs are one.
    """
    classes, properties = owned_classes(ctx), owned_properties(ctx)
    total = 0
    foreign: dict[str, int] = {}
    for predicate, subjects in ((RDFS.subClassOf, classes), (RDFS.domain, properties), (RDFS.range, properties)):
        for subject, target in ctx.g.subject_objects(predicate):
            if subject in subjects and isinstance(target, URIRef) and not str(target).startswith(W3C_NAMESPACES):
                total += 1
                if _foreign(ctx, subject, target):  # type: ignore[arg-type]
                    namespace = _namespace(redact_userinfo(str(target)))
                    foreign[namespace] = foreign.get(namespace, 0) + 1
    return CountRatio(sum(foreign.values()), total, tuple(sorted(foreign.items())))


def _unresolved_imports(ctx: RuleContext) -> Count:
    """Distinct IRI objects of ``owl:imports`` in the graph, of every header, minus the imports the closure loaded."""
    imports = {o for o in ctx.g.objects(None, OWL.imports) if isinstance(o, URIRef)}
    # Imports resolved to local modules (--follow-imports) are parts of the same artefact, not dependencies.
    return Count(len({o for o in imports if str(o) not in ctx.policy.resolved_imports}))


def _definition_length(ctx: RuleContext) -> TermValues:
    """Per owned class with a ``Literal`` description, the ``\\w+`` token count of its longest one."""
    classes = owned_classes(ctx)
    words: dict[Node, int] = {}
    for predicate in ctx.descriptions:
        for subject, text in ctx.g.subject_objects(predicate):
            if subject in classes and isinstance(text, Literal):
                words[subject] = max(words.get(subject, 0), len(WORD.findall(str(text))))
    return TermValues(MappingProxyType(words))


_STRUCTURAL_TYPES = frozenset(
    {
        OWL.Axiom,
        RDF.Statement,  # reification is the RDF counterpart of owl:Axiom
        OWL.Annotation,
        OWL.Restriction,
        OWL.Class,
        RDFS.Datatype,
        OWL.DataRange,
        OWL.NegativePropertyAssertion,
        OWL.AllDisjointClasses,
        OWL.AllDisjointProperties,
        OWL.AllDifferent,
    }
)
_STRUCTURAL_PREDICATES = (
    RDF.first,
    RDF.subject,
    # SHACL structures (inline property shapes, prefix declarations) are anonymous by design.
    SH.path,
    SH.prefix,
    OWL.onProperty,
    OWL.annotatedSource,
    OWL.intersectionOf,
    OWL.unionOf,
    OWL.complementOf,
    OWL.oneOf,
    OWL.onDatatype,
)


def _is_structural_blank(g: Graph, node: object) -> bool:
    """Return whether a blank node only encodes an axiom, restriction, class expression or list cell."""
    if not isinstance(node, BNode):
        return False
    return (
        any(t in _STRUCTURAL_TYPES for t in g.objects(node, RDF.type))
        or any((node, p, None) in g for p in _STRUCTURAL_PREDICATES)
        # Member shapes of sh:or/sh:and/sh:not, qualified shapes and SPARQL constraints: any sh: statement.
        or any(str(p).startswith(SHACL_NS) for p in g.predicates(node, None))
    )


def _blank_subjects(ctx: RuleContext) -> CountRatio:
    """Blank subjects of the graph, over its distinct subjects that are not structural blank nodes."""
    # Axioms, restrictions, class expressions and RDF-list cells are structure, not free blank nodes.
    subjects = {s for s in ctx.g.subjects() if not _is_structural_blank(ctx.g, s)}
    return CountRatio(sum(1 for s in subjects if isinstance(s, BNode)), len(subjects))


# --- measurements no rule thresholds ------------------------------------------------------------------------


def _class_depth(ctx: RuleContext) -> TermValues:
    """Per owned class, the number of classes on the longest asserted chain from a top class down to it.

    A class with no owned superclass is 1.  A class on a subclass cycle (CLS003) is 0 and adds nothing to the
    depth of its subclasses; a self-loop is ignored.  The chains are the asserted ``rdfs:subClassOf`` triples
    between owned classes, read upwards: :func:`~ontolint.graph.hierarchy_depths` over the reversed edges, so
    the deepest class is as deep as the highest subtree CLS005 measures with ``--depth-limit``.
    """
    classes = owned_classes(ctx)
    upwards = ((parent, child) for child, parent in directed_edges(ctx.g, RDFS.subClassOf, classes))
    return TermValues(MappingProxyType(hierarchy_depths(classes, upwards)))


def _hierarchy_components(ctx: RuleContext) -> Count:
    """The weakly connected components of the asserted ``rdfs:subClassOf`` triples between owned classes.

    ``owl:Thing`` and every class that is not owned are left out, so a common external superclass connects
    nothing, and a class with no owned sub- or superclass is a component of its own.
    """
    classes = owned_classes(ctx) - {OWL.Thing}
    return Count(len(weakly_connected_components(classes, directed_edges(ctx.g, RDFS.subClassOf, classes))))


NO_SHAPES = "no SHACL shapes graph was supplied"


def _shacl_class_target_coverage(ctx: RuleContext) -> TermRatio | Absent:
    """Owned classes that a class target of the shapes graph reaches: SHQ006's set (:func:`class_target_reach`).

    Absent without a shapes graph, since nothing could target a class then; an empty shapes graph is 0 of them.
    """
    if ctx.shapes is None:
        return Absent(NO_SHAPES)
    classes = owned_classes(ctx)
    return TermRatio(classes & class_target_reach(ctx, ctx.shapes), classes)


RATIO, COUNT, HISTOGRAM = MeasurementKind.RATIO, MeasurementKind.COUNT, MeasurementKind.HISTOGRAM

SPECS: tuple[MeasurementSpec, ...] = (
    MeasurementSpec(
        "class_label_coverage", 1, RATIO, "owned_classes", _class_label_coverage, rules=("METRIC001",), partitioned=True
    ),
    MeasurementSpec(
        "class_definition_coverage",
        1,
        RATIO,
        "owned_classes",
        _class_definition_coverage,
        rules=("METRIC002",),
        partitioned=True,
    ),
    MeasurementSpec(
        "property_documentation_coverage",
        1,
        RATIO,
        "owned_properties",
        _property_documentation_coverage,
        rules=("METRIC003",),
        partitioned=True,
    ),
    MeasurementSpec(
        "class_fanout", 1, RATIO, "owned_parent_classes", _class_fanout, rules=("METRIC004",), partitioned=True
    ),
    MeasurementSpec(
        "orphan_classes", 1, RATIO, "owned_classes", _orphan_classes, rules=("METRIC005",), partitioned=True
    ),
    MeasurementSpec(
        "relation_properties_per_class",
        1,
        RATIO,
        "owned_classes",
        _relation_properties_per_class,
        rules=("METRIC006", "METRIC007"),
        partitioned=True,
    ),
    MeasurementSpec(
        "unsigned_properties",
        1,
        RATIO,
        "owned_object_and_datatype_properties",
        _unsigned_properties,
        rules=("METRIC008",),
        partitioned=True,
    ),
    MeasurementSpec(
        "label_language_coverage",
        1,
        RATIO,
        "labelled_owned_terms",
        _label_language_coverage,
        rules=("METRIC009",),
        partitioned=True,
    ),
    MeasurementSpec("foreign_references", 1, RATIO, "structural_references", _foreign_references, rules=("METRIC010",)),
    MeasurementSpec("unresolved_imports", 1, COUNT, "graph", _unresolved_imports, rules=("METRIC011",)),
    MeasurementSpec(
        "definition_length",
        1,
        RATIO,
        "defined_owned_classes",
        _definition_length,
        rules=("METRIC012",),
        partitioned=True,
    ),
    MeasurementSpec("blank_subjects", 1, RATIO, "non_structural_subjects", _blank_subjects, rules=("METRIC013",)),
    MeasurementSpec("class_depth", 1, HISTOGRAM, "owned_classes", _class_depth, partitioned=True),
    MeasurementSpec("hierarchy_components", 1, COUNT, "owned_classes", _hierarchy_components),
    MeasurementSpec(
        "shacl_class_target_coverage", 1, RATIO, "owned_classes", _shacl_class_target_coverage, partitioned=True
    ),
)
"""The catalogue, in publication order."""
