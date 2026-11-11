"""Ontology-quality metric rules METRIC001-METRIC013.

Each rule measures one aggregate of the *asserted* graph (a ratio, a mean or a count), compares it
with a :class:`~ontolint.policy.Policy` threshold and emits at most one finding for the whole
ontology.  Nothing is entailed and no reasoner is involved.  Under ``--follow-imports`` the graph is
the whole closure.  Common to every rule:

* The population is the terms owned by the linted ontology (see :mod:`ontolint.ownership`), except
  METRIC011 and METRIC013, which count the whole graph.
* A rule needs a population of at least ``metric_min_sample`` (default 10) terms, so tiny ontologies
  never fire; METRIC011 has no such gate.  A ratio over an empty population is 0, never a division.
* Comparisons are strict: a value equal to its limit never fires.  The message prints the value and
  the limit with 2 decimals, or as many more (up to 6) as it takes to tell them apart.
* The focus is the lexically first ontology IRI of the graph (``ctx.ontologies``: the root headers
  of a closure, SHACL prefix declarations dropped), else ``urn:ontolint:graph``.  The finding's
  identity is its rule and focus, so counts and thresholds never change a baseline entry.
* Findings are ``heuristic`` (the limits are conventions, not facts) except METRIC011's.
* A numerator that a per-term rule also reports is *exactly* that rule's set, by a shared helper, so
  "METRIC005 says 10 orphans while CLS001 lists 6" cannot happen.

Thresholds, their rationale and how to override them are in ``docs/metric-thresholds.md``.  The
specifications:

* **METRIC001.** (``metric_max_unlabelled_ratio``, 0.5.)  Owned classes (``owl:Class``,
  ``rdfs:Class``); the numerator is the classes LEX001 reports: no ``Literal`` object of a label
  predicate (``ctx.labels``: ``rdfs:label``, ``skos:prefLabel``, the configured extras and the
  predicates below them through ``rdfs:subPropertyOf`` and ``owl:equivalentProperty``) and not
  ``owl:deprecated true``.  Fires when missing / classes exceeds the limit.  Exclusions: an IRI-valued
  label does not count, a deprecated class counts as labelled, an empty literal counts as a label
  (LEX005's), ``skos:altLabel`` and ``skos:hiddenLabel`` (and the predicates below them) do not count
  and the language is ignored.
  *Warning:* labels are the primary human interface; with the 0.5 limit the finding speaks only
  when missing labels are the norm.
* **METRIC002.** (``metric_max_undefined_ratio``, 0.5.)  Owned classes with no triple under
  ``ctx.descriptions``: ``rdfs:comment``, ``skos:definition``, ``dcterms:description`` and the other
  built-in definition predicates, ``extra_definition_predicates`` and the predicates below them
  through asserted ``rdfs:subPropertyOf`` and ``owl:equivalentProperty`` triples.  Exclusions:
  ``skos:note``, ``skos:scopeNote`` and the predicates below them do not count, unlike LEX002's; a
  definition whose value is an IRI or an empty literal counts.
  *Warning:* a class nobody defined cannot be understood or reused.
* **METRIC003.** (``metric_max_undocumented_property_ratio``, 0.5.)  The same for owned properties,
  annotation properties included (the property-documentation counterpart of METRIC002).
  *Info:* property documentation is secondary to class definitions.
* **METRIC004.** (``metric_max_mean_fanout``, 8.0.)  Gated on the owned-class count.  The mean
  number of direct asserted subclasses over the owned classes that have at least one owned
  subclass.  Exclusions: external or blank superclasses and self-loops are not edges; no parent
  means no finding.  The per-class counterpart is CLS011.
  *Info:* a flat list of more than about 7 siblings is hard to browse, but a taxonomy may be
  legitimately flat.
* **METRIC005.** (``metric_max_orphan_ratio``, 0.3.)  Owned classes; the numerator is the classes
  CLS001 reports: no asserted local super- or subclass, no typed instance, not used as a domain,
  range or restriction filler, no ``owl:equivalentClass`` link, not ``rdfs:subClassOf owl:Thing``
  and not deprecated.  A restriction or external superclass connects.  Exclusions: disjointness,
  membership of a union or intersection list and ``dcam:domainIncludes`` do not connect.
  *Info:* a class connected to nothing is usually unfinished, but vocabularies list isolated terms.
* **METRIC006.** (``metric_min_property_class_ratio``, 0.1.)  Gated on the owned-class count.  Owned
  relation properties per owned class: the owned properties that are not annotation-only
  (``owl:AnnotationProperty`` without an object or datatype type).  Fires below the limit.
  Exclusions: annotation properties; properties typed only ``rdf:Property`` count.
  *Info:* below one relation per ten classes the ontology is a taxonomy, which may be intended.
* **METRIC007.** (``metric_max_property_class_ratio``, 5.0.)  The same ratio, firing above the
  limit, with the same population and exclusions.
  *Info:* property proliferation suggests missing generalisation, but is not an error.
* **METRIC008.** (``metric_max_unsigned_property_ratio``, 0.5.)  Owned ``owl:ObjectProperty`` and
  ``owl:DatatypeProperty`` nodes; the numerator is those that both OWL005 and OWL006 report: no
  ``rdfs:domain`` or ``domainIncludes`` and no ``rdfs:range`` or ``rangeIncludes`` (schema.org and
  dcam), not deprecated.  Exclusions: annotation-only and ``rdf:Property``-only properties; a
  domain reached through an inverse or a superproperty is not looked for.
  *Info:* signatures are optional in RDFS and often left open on purpose.
* **METRIC009.** (``metric_min_language_coverage``, 0.5.)  Owned classes and properties with at
  least one ``Literal`` label (``ctx.labels``, as METRIC001); a term is tagged when at least one of
  its labels has a language tag.  Fires when tagged / labelled falls below the limit.  Exclusions:
  unlabelled terms are not in the population; ``policy.languages`` is LEX008's job; ``xsd:string`` counts as untagged.
  *Info:* untagged labels still work, they cannot be localised.
* **METRIC010.** (``metric_max_foreign_reference_ratio``, 0.5.)  References are
  ``rdfs:subClassOf`` from owned classes and ``rdfs:domain`` and ``rdfs:range`` from owned
  properties to IRIs outside the RDF, RDFS, OWL and XSD namespaces.  A reference is foreign when the
  target's namespace (the text up to the last ``#`` or ``/``) differs from the subject's and the
  target is not owned.  Ownership comes from the ontology header's IRI or ``--base``; a graph with
  neither has no owned namespace, so the namespace comparison alone decides.  Exclusions: blank
  targets, ``owl:equivalentClass``, restriction fillers and OBO reuse of another OBO ontology (one
  shared namespace); SKOS, DC and similar targets are foreign.
  *Info:* a mostly foreign ontology is a thin layer over others, which may be its purpose.
* **METRIC011.** (``metric_max_imports``, 10.)  The distinct IRI objects of ``owl:imports`` in the
  graph, of every header, minus ``policy.resolved_imports``.  Fires above the limit; no sample gate.
  *Info, certain:* the count is exact; only the limit is a convention.
* **METRIC012.** (``metric_min_definition_words``, 4.0.)  Owned classes with a ``Literal``
  description (``ctx.descriptions``, as METRIC002); each scores the ``\\w+`` token count of its
  longest description and the value is their mean.  Fires below the limit.  Exclusions: IRI
  descriptions; a long ``rdfs:comment`` masks a short ``skos:definition``; properties are not
  measured.
  *Info:* a definition shorter than "An X that Y" cannot say what distinguishes the class.
* **METRIC013.** (``metric_max_blank_node_ratio``, 0.6.)  The distinct subjects of the graph that
  are not structural blank nodes; the value is blank / all.  Structural blank nodes encode an axiom,
  restriction, class expression, list cell, reified statement or SHACL structure: typed
  ``owl:Axiom``, ``owl:Annotation``, ``owl:Restriction``, ``owl:Class``, ``rdfs:Datatype``,
  ``owl:DataRange``, ``rdf:Statement`` or an ``owl:All*`` / ``owl:NegativePropertyAssertion`` axiom
  node, or the subject of ``rdf:first``, ``rdf:subject``, ``owl:onProperty``,
  ``owl:annotatedSource``, ``owl:intersectionOf``, ``owl:unionOf``, ``owl:complementOf``,
  ``owl:oneOf``, ``owl:onDatatype`` or any ``sh:`` predicate.
  *Info:* beyond structure, blank nodes are anonymous individuals nobody can reference.
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
from ontolint.ownership import OwnershipMode

from .classes import orphan_classes
from .lexical import is_unlabelled
from .owl import annotation_only, lacks_domain, lacks_range, signature_exempt

if TYPE_CHECKING:
    from .runtime import RuleContext

FOCUS_FALLBACK = "urn:ontolint:graph"
W3C_NAMESPACES = (str(OWL), str(RDF), str(RDFS), str(XSD))
SHACL_NS = str(SH)
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


def _vs(value: float, limit: float) -> tuple[str, str]:
    """Format a value and its limit with 2 decimals, or more when fewer would print them as equal.

    Up to 6 decimals; a value that still equals its limit there is printed in full, so a finding never reads
    ``0.303030 > 0.303030``. Equal values never fire, so they only reach here as ``0.300000`` for both.
    """
    for digits in range(2, 7):
        shown, shown_limit = f"{value:.{digits}f}", f"{limit:.{digits}f}"
        if shown != shown_limit:
            return shown, shown_limit
    if value != limit:
        return repr(value), repr(limit)
    return f"{value:.6f}", f"{limit:.6f}"


def _cmp(value: float, operator: str, limit: float) -> str:
    shown, shown_limit = _vs(value, limit)
    return f"{shown} {operator} {shown_limit}"


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


def _missing(ctx: RuleContext, code: str, terms: frozenset[URIRef], predicates: tuple[URIRef, ...]) -> int:
    if code == "METRIC001":  # exactly the classes LEX001 reports
        return sum(is_unlabelled(ctx, term) for term in terms)
    return len(terms) - _covered(ctx, terms, predicates)


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
    missing = _missing(ctx, code, terms, predicates)
    ratio = _ratio(missing, total)
    if ratio > limit:
        ctx.add(
            code,
            _focus(ctx),
            f"{missing} of {total} {noun} lack {what} ({_cmp(ratio, '>', limit)}).",
            subject=(),
        )


def _shape_rules(ctx: RuleContext, classes: frozenset[URIRef], properties: frozenset[URIRef]) -> None:
    policy = ctx.policy
    _coverage_rule(ctx, "METRIC001", classes, ctx.labels)
    _coverage_rule(ctx, "METRIC002", classes, ctx.descriptions)
    _coverage_rule(ctx, "METRIC003", properties, ctx.descriptions)
    if len(classes) >= policy.metric_min_sample:
        # Annotation properties relate no classes; both suggestions are about relations.
        relations = sum(1 for p in properties if not annotation_only(ctx.g, p))
        ratio = relations / len(classes)
        if ratio < policy.metric_min_property_class_ratio:
            ctx.add(
                "METRIC006",
                _focus(ctx),
                f"{relations} properties for {len(classes)} classes "
                f"({_cmp(ratio, '<', policy.metric_min_property_class_ratio)}).",
                subject=(),
            )
        if ratio > policy.metric_max_property_class_ratio:
            ctx.add(
                "METRIC007",
                _focus(ctx),
                f"{relations} properties for {len(classes)} classes "
                f"({_cmp(ratio, '>', policy.metric_max_property_class_ratio)}).",
                subject=(),
            )


def _hierarchy_rules(ctx: RuleContext, classes: frozenset[URIRef]) -> None:
    policy = ctx.policy
    if len(classes) < policy.metric_min_sample:
        return
    h = _hierarchy(ctx, classes)
    if h.children:
        mean = sum(len(kids) for kids in h.children.values()) / len(h.children)
        if mean > policy.metric_max_mean_fanout:
            shown, limit = _vs(mean, policy.metric_max_mean_fanout)
            ctx.add(
                "METRIC004",
                _focus(ctx),
                f"{len(h.children)} parent classes have {shown} direct subclasses on average (threshold {limit}).",
                subject=(),
            )
    orphans = len(orphan_classes(ctx) & classes)  # exactly the owned classes CLS001 reports
    ratio = _ratio(orphans, len(classes))
    if ratio > policy.metric_max_orphan_ratio:
        ctx.add(
            "METRIC005",
            _focus(ctx),
            f"{orphans} of {len(classes)} classes are orphans: no asserted sub/superclass, instance, "
            f"domain or range ({_cmp(ratio, '>', policy.metric_max_orphan_ratio)}).",
            subject=(),
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
    # Exactly the properties that OWL005 and OWL006 both report.
    unsigned = sum(1 for p in props if not signature_exempt(ctx.g, p) and lacks_domain(ctx, p) and lacks_range(ctx, p))
    ratio = _ratio(unsigned, len(props))
    if ratio > ctx.policy.metric_max_unsigned_property_ratio:
        limit = ctx.policy.metric_max_unsigned_property_ratio
        ctx.add(
            "METRIC008",
            _focus(ctx),
            f"{unsigned} of {len(props)} object/datatype properties have neither domain nor range "
            f"({_cmp(ratio, '>', limit)}).",
            subject=(),
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
                f"({_cmp(coverage, '<', policy.metric_min_language_coverage)}).",
                subject=(),
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
            shown, limit = _vs(mean, policy.metric_min_definition_words)
            ctx.add(
                "METRIC012",
                _focus(ctx),
                f"{len(words)} defined classes average {shown} words per definition (threshold {limit}).",
                subject=(),
            )


def _foreign(ctx: RuleContext, subject: URIRef, target: URIRef) -> bool:
    """Return whether ``target`` lies outside the subject's namespace and is not owned by the ontology.

    An ontology that owns several namespaces (a header or base covering them) refers to itself across
    them.  Without any ownership information (``OwnershipMode.ALL``) every IRI counts as owned, so the
    namespace comparison alone decides.
    """
    if _namespace(target) == _namespace(subject):
        return False
    return ctx.context.ownership.mode is OwnershipMode.ALL or not ctx.local(target)


def _reference_rule(ctx: RuleContext, classes: frozenset[URIRef], properties: frozenset[URIRef]) -> None:
    """Share of structural references (subClassOf, domain, range) pointing outside the subject's namespace."""
    total = foreign = 0
    for predicate, subjects in ((RDFS.subClassOf, classes), (RDFS.domain, properties), (RDFS.range, properties)):
        for subject, target in ctx.g.subject_objects(predicate):
            if subject in subjects and isinstance(target, URIRef) and not str(target).startswith(W3C_NAMESPACES):
                total += 1
                foreign += _foreign(ctx, subject, target)  # type: ignore[arg-type]
    limit = ctx.policy.metric_max_foreign_reference_ratio
    ratio = _ratio(foreign, total)
    if total >= ctx.policy.metric_min_sample and ratio > limit:
        ctx.add(
            "METRIC010",
            _focus(ctx),
            f"{foreign} of {total} structural references point to another namespace ({_cmp(ratio, '>', limit)}).",
            subject=(),
        )


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
            subject=(),
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
                f"({_cmp(ratio, '>', ctx.policy.metric_max_blank_node_ratio)}).",
                subject=(),
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
