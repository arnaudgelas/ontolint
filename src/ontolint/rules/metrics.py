"""Ontology-quality metric rules METRIC001-METRIC013.

Each rule measures one aggregate of the *asserted* graph (a ratio, a mean or a count), compares it
with a :class:`~ontolint.policy.Policy` threshold and emits at most one finding for the whole
ontology.  Every metric needs a minimum sample (``Policy.metric_min_sample``) so tiny ontologies
never fire, and every ratio is defined only on a non-empty population (no division by zero).
All values are computed in single passes over the indexes in ``ctx.context``; terms are never
re-scanned.  Per-term checks (missing labels, depth, fan-out of one class) live in the LEX, CLS
and SKOS families; these rules are the corpus-level counterparts.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SH, XSD

from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity

if TYPE_CHECKING:
    from .runtime import RuleContext

FOCUS_FALLBACK = "urn:ontolint:graph"
W3C_NAMESPACES = (str(OWL), str(RDF), str(RDFS), str(XSD))
WORD = re.compile(r"\w+")


def _spec(rule_id: str, title: str, severity: Severity, suggestion: str, scope: RuleScope) -> RuleSpec:
    return RuleSpec(rule_id, "METRIC", title, severity, suggestion, "heuristic", RuleBackend.RDFLIB, scope, "metrics")


SPECS: tuple[RuleSpec, ...] = (
    _spec(
        "METRIC001",
        "Low class label coverage",
        Severity.WARNING,
        "Add an rdfs:label or skos:prefLabel to the unlabelled classes.",
        RuleScope.ONTOLOGY,
    ),
    _spec(
        "METRIC002",
        "Low class definition coverage",
        Severity.WARNING,
        "Add rdfs:comment, skos:definition or dcterms:description to the undefined classes.",
        RuleScope.ONTOLOGY,
    ),
    _spec(
        "METRIC003",
        "Low property documentation coverage",
        Severity.INFO,
        "Document properties with rdfs:comment, skos:definition or dcterms:description.",
        RuleScope.ONTOLOGY,
    ),
    _spec(
        "METRIC004",
        "High mean class fan-out",
        Severity.INFO,
        "Introduce intermediate classes where parents have many direct subclasses on average.",
        RuleScope.ONTOLOGY,
    ),
    _spec(
        "METRIC005",
        "High orphan class ratio",
        Severity.INFO,
        "Connect orphan classes to the hierarchy, properties or instances, or remove them.",
        RuleScope.ONTOLOGY,
    ),
    _spec(
        "METRIC006",
        "Low property-to-class ratio",
        Severity.INFO,
        "Check whether relations between the classes are missing; the ontology may be only a taxonomy.",
        RuleScope.ONTOLOGY,
    ),
    _spec(
        "METRIC007",
        "High property-to-class ratio",
        Severity.INFO,
        "Check for property proliferation: generalise properties or add the classes they should describe.",
        RuleScope.ONTOLOGY,
    ),
    _spec(
        "METRIC008",
        "Low property signature coverage",
        Severity.INFO,
        "Declare rdfs:domain or rdfs:range on object and datatype properties where the intent is clear.",
        RuleScope.ONTOLOGY,
    ),
    _spec(
        "METRIC009",
        "Low label language-tag coverage",
        Severity.INFO,
        'Tag labels with their language (for example rdfs:label "x"@en).',
        RuleScope.ONTOLOGY,
    ),
    _spec(
        "METRIC010",
        "High cross-namespace reference ratio",
        Severity.INFO,
        "Check that the ontology is not mostly a thin layer over external vocabularies; consider importing instead.",
        RuleScope.ONTOLOGY,
    ),
    _spec(
        "METRIC011",
        "Excessive number of imports",
        Severity.INFO,
        "Reduce owl:imports to the ontologies actually needed, or use import modules.",
        RuleScope.ONTOLOGY,
    ),
    _spec(
        "METRIC012",
        "Terse class definitions",
        Severity.INFO,
        "Expand very short class definitions so that they state what distinguishes the class.",
        RuleScope.ONTOLOGY,
    ),
    _spec(
        "METRIC013",
        "High blank node ratio",
        Severity.INFO,
        "Check whether anonymous resources could be named, or are restrictions that should be reviewed.",
        RuleScope.ONTOLOGY,
    ),
)


def _focus(ctx: RuleContext) -> str:
    return str(min(ctx.ontologies, key=str)) if ctx.ontologies else FOCUS_FALLBACK


def _ratio(part: int, whole: int) -> float:
    return part / whole if whole else 0.0


def _namespace(iri: URIRef) -> str:
    text = str(iri)
    cut = max(text.rfind("#"), text.rfind("/"))
    return text[: cut + 1] if cut >= 0 else text


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


def _local(ctx: RuleContext, terms: Iterable[URIRef]) -> frozenset[URIRef]:
    return frozenset(term for term in terms if ctx.local(term))


def _covered(ctx: RuleContext, terms: frozenset[URIRef], predicates: tuple[URIRef, ...]) -> int:
    """Count ``terms`` that are the subject of at least one of ``predicates``."""
    having: set[object] = set()
    for predicate in predicates:
        having |= ctx.context.subjects_by_predicate.get(predicate, frozenset())
    return sum(1 for term in terms if term in having)


def _coverage_rule(ctx: RuleContext, code: str, terms: frozenset[URIRef], predicates: tuple[URIRef, ...]) -> None:
    """Emit ``code`` when too many ``terms`` lack every one of ``predicates``."""
    policy = ctx.policy
    limit, noun, what = {
        "METRIC001": (policy.metric_max_unlabelled_ratio, "classes", "a label"),
        "METRIC002": (policy.metric_max_undefined_ratio, "classes", "a definition"),
        "METRIC003": (policy.metric_max_undocumented_property_ratio, "properties", "documentation"),
    }[code]
    total = len(terms)
    if total < policy.metric_min_sample:
        return
    missing = total - _covered(ctx, terms, predicates)
    ratio = _ratio(missing, total)
    if ratio > limit:
        ctx.add(code, _focus(ctx), f"{missing} of {total} {noun} lack {what} ({ratio:.2f} > {limit:.2f}).")


def _shape_rules(ctx: RuleContext, classes: frozenset[URIRef], properties: frozenset[URIRef]) -> None:
    policy = ctx.policy
    _coverage_rule(ctx, "METRIC001", classes, ctx.labels)
    _coverage_rule(ctx, "METRIC002", classes, ctx.descriptions)
    _coverage_rule(ctx, "METRIC003", properties, ctx.descriptions)
    if len(classes) >= policy.metric_min_sample:
        ratio = len(properties) / len(classes)
        if ratio < policy.metric_min_property_class_ratio:
            ctx.add(
                "METRIC006",
                _focus(ctx),
                f"{len(properties)} properties for {len(classes)} classes "
                f"({ratio:.2f} < {policy.metric_min_property_class_ratio:.2f}).",
            )
        if ratio > policy.metric_max_property_class_ratio:
            ctx.add(
                "METRIC007",
                _focus(ctx),
                f"{len(properties)} properties for {len(classes)} classes "
                f"({ratio:.2f} > {policy.metric_max_property_class_ratio:.2f}).",
            )


def _hierarchy_rules(ctx: RuleContext, classes: frozenset[URIRef]) -> None:
    policy = ctx.policy
    if len(classes) < policy.metric_min_sample:
        return
    h = _hierarchy(ctx, classes)
    if h.children:
        mean = sum(len(kids) for kids in h.children.values()) / len(h.children)
        if mean > policy.metric_max_mean_fanout:
            ctx.add(
                "METRIC004",
                _focus(ctx),
                f"{len(h.children)} parent classes have {mean:.2f} direct subclasses on average "
                f"(threshold {policy.metric_max_mean_fanout:.2f}).",
            )
    used: set[object] = set(ctx.context.subjects_by_type)  # typed subjects include every instance
    for prop in ctx.context.properties_by_domain:
        used.add(prop)
    for ranges in ctx.context.ranges_by_property.values():
        used |= ranges
    # A named superclass outside the ontology connects a class too: an ontology aligned to BFO or another
    # upper ontology hangs most of its classes directly under external parents.
    external_parent = {
        c for c in classes if any(isinstance(o, URIRef) and o != OWL.Thing for o in ctx.g.objects(c, RDFS.subClassOf))
    }
    orphans = sum(
        1 for c in classes if c not in h.parents and c not in h.children and c not in used and c not in external_parent
    )
    ratio = _ratio(orphans, len(classes))
    if ratio > policy.metric_max_orphan_ratio:
        ctx.add(
            "METRIC005",
            _focus(ctx),
            f"{orphans} of {len(classes)} classes are orphans: no asserted sub/superclass, instance, "
            f"domain or range ({ratio:.2f} > {policy.metric_max_orphan_ratio:.2f}).",
        )


def _signature_rule(ctx: RuleContext) -> None:
    props = _local(
        ctx,
        (
            p
            for kind in (OWL.ObjectProperty, OWL.DatatypeProperty)
            for p in ctx.context.subjects_by_type.get(kind, frozenset())
            if isinstance(p, URIRef)
        ),
    )
    if len(props) < ctx.policy.metric_min_sample:
        return
    signed = sum(1 for p in props if p in ctx.context.domains_by_property or p in ctx.context.ranges_by_property)
    unsigned = len(props) - signed
    ratio = _ratio(unsigned, len(props))
    if ratio > ctx.policy.metric_max_unsigned_property_ratio:
        limit = ctx.policy.metric_max_unsigned_property_ratio
        ctx.add(
            "METRIC008",
            _focus(ctx),
            f"{unsigned} of {len(props)} object/datatype properties have neither domain nor range "
            f"({ratio:.2f} > {limit:.2f}).",
        )


def _language_rule(ctx: RuleContext, terms: frozenset[URIRef]) -> None:
    policy = ctx.policy
    labelled: set[object] = set()
    tagged: set[object] = set()
    for predicate in ctx.labels:
        for subject, label in ctx.g.subject_objects(predicate):
            if subject in terms and isinstance(label, Literal):
                labelled.add(subject)
                if label.language:
                    tagged.add(subject)
    if len(labelled) >= policy.metric_min_sample:
        coverage = len(tagged) / len(labelled)
        if coverage < policy.metric_min_language_coverage:
            ctx.add(
                "METRIC009",
                _focus(ctx),
                f"{len(tagged)} of {len(labelled)} labelled terms have a language-tagged label "
                f"({coverage:.2f} < {policy.metric_min_language_coverage:.2f}).",
            )


def _definition_rule(ctx: RuleContext, classes: frozenset[URIRef]) -> None:
    policy = ctx.policy
    words: dict[object, int] = {}
    for predicate in ctx.descriptions:
        for subject, text in ctx.g.subject_objects(predicate):
            if subject in classes and isinstance(text, Literal):
                words[subject] = max(words.get(subject, 0), len(WORD.findall(str(text))))
    if len(words) >= policy.metric_min_sample:
        mean = sum(words.values()) / len(words)
        if mean < policy.metric_min_definition_words:
            ctx.add(
                "METRIC012",
                _focus(ctx),
                f"{len(words)} defined classes average {mean:.2f} words per definition "
                f"(threshold {policy.metric_min_definition_words:.2f}).",
            )


def _reference_rule(ctx: RuleContext, classes: frozenset[URIRef], properties: frozenset[URIRef]) -> None:
    """Share of structural references (subClassOf, domain, range) pointing outside the subject's namespace."""
    total = foreign = 0
    for predicate, subjects in ((RDFS.subClassOf, classes), (RDFS.domain, properties), (RDFS.range, properties)):
        for subject, target in ctx.g.subject_objects(predicate):
            if subject in subjects and isinstance(target, URIRef) and not str(target).startswith(W3C_NAMESPACES):
                total += 1
                foreign += _namespace(target) != _namespace(subject)  # type: ignore[arg-type]
    limit = ctx.policy.metric_max_foreign_reference_ratio
    ratio = _ratio(foreign, total)
    if total >= ctx.policy.metric_min_sample and ratio > limit:
        ctx.add(
            "METRIC010",
            _focus(ctx),
            f"{foreign} of {total} structural references point to another namespace ({ratio:.2f} > {limit:.2f}).",
        )


_STRUCTURAL_TYPES = frozenset(
    {
        OWL.Axiom,
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
    return any(t in _STRUCTURAL_TYPES for t in g.objects(node, RDF.type)) or any(
        (node, p, None) in g for p in _STRUCTURAL_PREDICATES
    )


def _graph_rules(ctx: RuleContext) -> None:
    # Imports resolved to local modules (--follow-imports) are parts of the same artefact, not dependencies.
    imports = {o for o in ctx.g.objects(None, OWL.imports) if isinstance(o, URIRef)}
    imports = {o for o in imports if str(o) not in ctx.policy.resolved_imports}
    if len(imports) > ctx.policy.metric_max_imports:
        ctx.add(
            "METRIC011",
            _focus(ctx),
            f"{len(imports)} distinct owl:imports (threshold {ctx.policy.metric_max_imports}).",
            confidence="certain",
        )
    # Axioms, restrictions, class expressions and RDF-list cells are structure, not free blank nodes.
    subjects = {s for s in ctx.g.subjects() if not _is_structural_blank(ctx.g, s)}
    if len(subjects) >= ctx.policy.metric_min_sample:
        blanks = sum(1 for s in subjects if isinstance(s, BNode))
        ratio = _ratio(blanks, len(subjects))
        if ratio > ctx.policy.metric_max_blank_node_ratio:
            ctx.add(
                "METRIC013",
                _focus(ctx),
                f"{blanks} of {len(subjects)} subjects are blank nodes "
                f"({ratio:.2f} > {ctx.policy.metric_max_blank_node_ratio:.2f}).",
            )


def run(ctx: RuleContext) -> None:
    """Evaluate every metric rule against ``ctx``."""
    classes = _local(ctx, ctx.classes)
    properties = _local(ctx, ctx.properties)
    _shape_rules(ctx, classes, properties)
    _hierarchy_rules(ctx, classes)
    _signature_rule(ctx)
    _language_rule(ctx, classes | properties)
    _definition_rule(ctx, classes)
    _reference_rule(ctx, classes, properties)
    _graph_rules(ctx)
