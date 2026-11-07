"""OBO Foundry convention rules: OBO001-OBO012.

These rules encode conventions of the OBO Foundry (identifiers, textual definitions, obsolescence,
scoped synonyms, PURLs, naming).  They only make sense for ontologies that follow those conventions,
so the ``OBO`` family is *opt-in*: see :data:`ontolint.profiles.OPT_IN_FAMILIES`.  It runs with
``--select OBO`` / ``--select OBO0xx`` or ``--profile obo`` and never as part of the default selection.

Every rule is an asserted-graph check: nothing is entailed, no import is followed and no network is
used.  Rules that would need outside data (a registry lookup, the full RO term list, a reasoner) are
not implemented; ``OBO005`` is deliberately narrowed to a small embedded table of well-known RO and
BFO relations.  Annotation properties are the IAO and oboInOwl ones used by OBO ontologies.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from typing import TYPE_CHECKING

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DC, DCTERMS, OWL, RDF, RDFS, SKOS, XSD
from rdflib.term import Node

from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity

from .support import META_LICENSE, list_items

if TYPE_CHECKING:
    from .runtime import RuleContext

OBO_NS = "http://purl.obolibrary.org/obo/"
OIO_NS = "http://www.geneontology.org/formats/oboInOwl#"
BFO_PREFIX = OBO_NS + "BFO_"

IAO_DEFINITION = URIRef(OBO_NS + "IAO_0000115")
IAO_DEFINITION_SOURCE = URIRef(OBO_NS + "IAO_0000119")
IAO_OBSOLESCENCE_REASON = URIRef(OBO_NS + "IAO_0000231")
IAO_REPLACED_BY = URIRef(OBO_NS + "IAO_0100001")
IAO_ELUCIDATION = URIRef(OBO_NS + "IAO_0000600")
IAO_TERM_TRACKER = URIRef(OBO_NS + "IAO_0000233")
OIO_DB_XREF = URIRef(OIO_NS + "hasDbXref")
OIO_CONSIDER = URIRef(OIO_NS + "consider")
OIO_SYNONYM = URIRef(OIO_NS + "hasSynonym")

DEFINITION_PROVENANCE = (OIO_DB_XREF, IAO_DEFINITION_SOURCE, DCTERMS.source, DC.source)
TERM_PROVENANCE = (IAO_DEFINITION_SOURCE, DCTERMS.source, DC.source)
DEFINITION_PREDICATES = (IAO_DEFINITION, IAO_ELUCIDATION)
OBSOLESCENCE_REMEDIES = (IAO_OBSOLESCENCE_REASON, IAO_TERM_TRACKER, IAO_REPLACED_BY, OIO_CONSIDER)
UNSCOPED_SYNONYMS = (OIO_SYNONYM, SKOS.altLabel)
MAX_QUOTE = 60  # Characters of a label or synonym quoted in a message.

ID_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z][A-Za-z0-9]*)*_[A-Za-z]*[0-9]+")
ONTOLOGY_PATTERN = re.compile(re.escape(OBO_NS) + r"([a-z][a-z0-9_]*)(?:\.owl|/\S+\.owl)")
VERSION_PATTERN = re.compile(
    re.escape(OBO_NS) + r"([a-z][a-z0-9_]*)/(?:releases/)?(?:[0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]+(?:\.[0-9]+)*)/\S+\.owl"
)
FOUNDATIONAL_IMPORTS = frozenset(OBO_NS + name for name in ("bfo.owl", "omo.owl", "ro.owl"))
FULL_IMPORT_PATTERNS = (
    re.compile(re.escape(OBO_NS) + r"[^/#]+\.owl"),
    re.compile(re.escape(OBO_NS) + r"([^/#]+)/releases/[^/#]+/\1\.owl"),
)

# Well-known relation labels mapped to the BFO/RO term that already provides them.
RO_RELATIONS: dict[str, str] = {
    "part of": "BFO_0000050",
    "has part": "BFO_0000051",
    "occurs in": "BFO_0000066",
    "realizes": "BFO_0000055",
    "participates in": "RO_0000056",
    "has participant": "RO_0000057",
    "has role": "RO_0000087",
    "located in": "RO_0001025",
    "derives from": "RO_0001000",
    "develops from": "RO_0002202",
    "has input": "RO_0002233",
    "has output": "RO_0002234",
    "regulates": "RO_0002211",
    "negatively regulates": "RO_0002212",
    "positively regulates": "RO_0002213",
    "capable of": "RO_0002215",
    "adjacent to": "RO_0002220",
    "overlaps": "RO_0002131",
}


def _spec(rule_id: str, title: str, severity: Severity, suggestion: str, scope: RuleScope) -> RuleSpec:
    return RuleSpec(rule_id, "OBO", title, severity, suggestion, "context-dependent", RuleBackend.RDFLIB, scope, "obo")


SPECS: tuple[RuleSpec, ...] = (
    _spec(
        "OBO001",
        "OBO term IRI that does not follow the PREFIX_0000000 pattern",
        Severity.WARNING,
        "Mint OBO identifiers as http://purl.obolibrary.org/obo/PREFIX_NNNNNNN (optionally PREFIX_SUBSPACE_NNNNNNN).",
        RuleScope.TERM,
    ),
    _spec(
        "OBO002",
        "Ontology header missing OBO-required title, description or license",
        Severity.WARNING,
        "Add dc:title or dcterms:title, dc:description or dcterms:description, and dcterms:license to the header.",
        RuleScope.ONTOLOGY,
    ),
    _spec(
        "OBO003",
        "Term without an IAO textual definition",
        Severity.WARNING,
        "Add an obo:IAO_0000115 (definition) or obo:IAO_0000600 (elucidation) annotation with a non-empty text.",
        RuleScope.TERM,
    ),
    _spec(
        "OBO004",
        "Term without an rdfs:label, or with a label shared by another term",
        Severity.WARNING,
        "Give every term exactly one rdfs:label and make labels unique within each language.",
        RuleScope.TERM,
    ),
    _spec(
        "OBO005",
        "Object property duplicating a well-known RO or BFO relation",
        Severity.INFO,
        "Reuse the RO/BFO relation, or assert rdfs:subPropertyOf or owl:equivalentProperty to it.",
        RuleScope.TERM,
    ),
    _spec(
        "OBO006",
        "Definition without provenance",
        Severity.INFO,
        "Annotate the definition axiom with oboInOwl:hasDbXref, obo:IAO_0000119, dcterms:source or dc:source.",
        RuleScope.TERM,
    ),
    _spec(
        "OBO007",
        "Obsolete term without a reason or replacement annotation",
        Severity.INFO,
        "Add obo:IAO_0000231 (reason), IAO_0000233 (tracker item), IAO_0100001 (replaced by) or oboInOwl:consider.",
        RuleScope.TERM,
    ),
    _spec(
        "OBO008",
        "Class with no asserted path to a BFO class",
        Severity.WARNING,
        "Give the root class an asserted rdfs:subClassOf to a BFO class, or a named BFO genus.",
        RuleScope.TERM,
    ),
    _spec(
        "OBO009",
        "Synonym annotation without scope",
        Severity.INFO,
        "Use oboInOwl:hasExactSynonym, hasBroadSynonym, hasNarrowSynonym or hasRelatedSynonym.",
        RuleScope.TERM,
    ),
    _spec(
        "OBO010",
        "Whole OBO ontology imported instead of a module",
        Severity.INFO,
        "Import an ODK-style module (.../obo/<id>/imports/<term>_import.owl); bfo, omo and ro may be imported whole.",
        RuleScope.ONTOLOGY,
    ),
    _spec(
        "OBO011",
        "Ontology or version IRI that does not follow the OBO PURL pattern",
        Severity.WARNING,
        "Use .../obo/<id>.owl and a version IRI such as .../obo/<id>/releases/YYYY-MM-DD/<id>.owl.",
        RuleScope.ONTOLOGY,
    ),
    _spec(
        "OBO012",
        "Label that breaks OBO naming conventions",
        Severity.INFO,
        "Use labels without leading, trailing or repeated whitespace and without underscores.",
        RuleScope.TERM,
    ),
)


def _ordered(nodes: Iterable[Node]) -> list[Node]:
    return sorted(nodes, key=str)


def _quote(text: str) -> str:
    return repr(text if len(text) <= MAX_QUOTE else text[:MAX_QUOTE] + "...")


def _texts(g: Graph, subject: Node, predicate: Node) -> list[Literal]:
    """Non-blank literal objects of ``(subject, predicate, ?)``."""
    return [o for o in g.objects(subject, predicate) if isinstance(o, Literal) and str(o).strip()]


def _has_value(g: Graph, subject: Node, predicates: Iterable[Node]) -> bool:
    """Whether any predicate has a non-blank literal or any non-literal value."""
    return any(not isinstance(o, Literal) or str(o).strip() for p in predicates for o in g.objects(subject, p))


def _is_true(value: Node) -> bool:
    lexical = str(value).strip().lower()
    return isinstance(value, Literal) and (lexical == "true" or (value.datatype == XSD.boolean and lexical == "1"))


def _deprecated(ctx: RuleContext) -> frozenset[URIRef]:
    return frozenset(s for s, o in ctx.g.subject_objects(OWL.deprecated) if isinstance(s, URIRef) and _is_true(o))


def _terms(ctx: RuleContext) -> list[URIRef]:
    """Local classes plus object and datatype properties, in IRI order."""
    by_type = ctx.context.subjects_by_type
    properties = by_type.get(OWL.ObjectProperty, frozenset()) | by_type.get(OWL.DatatypeProperty, frozenset())
    found = set(ctx.classes) | {p for p in properties if isinstance(p, URIRef) and ctx.local(p)}
    return sorted(found, key=str)


def _identifier_pattern(ctx: RuleContext, terms: list[URIRef], deprecated: frozenset[URIRef]) -> None:
    for term in terms:
        iri = str(term)
        if term not in deprecated and iri.startswith(OBO_NS) and not ID_PATTERN.fullmatch(iri[len(OBO_NS) :]):
            ctx.add(
                "OBO001",
                term,
                f"OBO identifier {iri[len(OBO_NS) :]!r} does not follow the PREFIX_0000000 pattern.",
                confidence="certain",
            )


def _required_metadata(ctx: RuleContext) -> None:
    required = (
        ("title", "dcterms:title", (DCTERMS.title, DC.title)),
        ("description", "dcterms:description", (DCTERMS.description, DC.description)),
        ("license", "dcterms:license", META_LICENSE),
    )
    for ontology in sorted(ctx.ontologies, key=str):
        for name, curie, predicates in required:
            if not _has_value(ctx.g, ontology, predicates):
                ctx.add("OBO002", ontology, f"Ontology header has no {name} ({curie}).", confidence="certain")


def _definitions(ctx: RuleContext, terms: list[URIRef], deprecated: frozenset[URIRef]) -> None:
    for term in terms:
        if term not in deprecated and not any(_texts(ctx.g, term, p) for p in DEFINITION_PREDICATES):
            ctx.add("OBO003", term, "Term has no textual definition (obo:IAO_0000115).", confidence="certain")


def _labels(ctx: RuleContext, terms: list[URIRef], deprecated: frozenset[URIRef]) -> None:
    users: dict[tuple[str, str], set[URIRef]] = defaultdict(set)
    for term in terms:
        if term in deprecated:
            continue
        labels = _texts(ctx.g, term, RDFS.label)
        if not labels:
            ctx.add("OBO004", term, "Term has no rdfs:label.", confidence="certain")
        for label in labels:
            users[str(label), (label.language or "").lower()].add(term)
    for (text, _language), sharing in sorted(users.items()):
        for term in sorted(sharing, key=str):
            others = ", ".join(str(t) for t in sorted(sharing - {term}, key=str))
            if others:
                ctx.add("OBO004", term, f"Label {_quote(text)} is also used by {others}.", confidence="certain")


def _ro_duplicates(ctx: RuleContext, deprecated: frozenset[URIRef]) -> None:
    g = ctx.g
    for prop in _ordered(ctx.context.subjects_by_type.get(OWL.ObjectProperty, frozenset())):
        if not (isinstance(prop, URIRef) and ctx.local(prop)) or prop in deprecated:
            continue
        for label in _texts(g, prop, RDFS.label):
            target = RO_RELATIONS.get(" ".join(str(label).lower().split()))
            ro = URIRef(OBO_NS + target) if target else None
            if ro is None or prop == ro:
                continue
            linked = any(
                (a, predicate, b) in g
                for predicate in (RDFS.subPropertyOf, OWL.equivalentProperty)
                for a, b in ((prop, ro), (ro, prop))
            )
            if not linked:
                ctx.add(
                    "OBO005",
                    prop,
                    f"Object property labelled {_quote(str(label))} duplicates the existing relation {ro}.",
                )


def _definition_sources(ctx: RuleContext, terms: list[URIRef], deprecated: frozenset[URIRef]) -> None:
    g = ctx.g
    sourced: set[tuple[Node, Node]] = set()
    for axiom in g.subjects(RDF.type, OWL.Axiom):
        if (axiom, OWL.annotatedProperty, IAO_DEFINITION) in g and any(
            (axiom, p, None) in g for p in DEFINITION_PROVENANCE
        ):
            sourced.update(
                (s, t) for s in g.objects(axiom, OWL.annotatedSource) for t in g.objects(axiom, OWL.annotatedTarget)
            )
    for term in terms:
        if term in deprecated or _has_value(g, term, TERM_PROVENANCE):
            continue
        if any((term, d) not in sourced for d in _texts(g, term, IAO_DEFINITION)):
            ctx.add(
                "OBO006",
                term,
                "Definition has no source (oboInOwl:hasDbXref, obo:IAO_0000119, dcterms:source or dc:source).",
            )


def _obsolescence(ctx: RuleContext, terms: list[URIRef], deprecated: frozenset[URIRef]) -> None:
    for term in terms:
        if term in deprecated and not _has_value(ctx.g, term, OBSOLESCENCE_REMEDIES):
            ctx.add(
                "OBO007",
                term,
                "Obsolete term has no obsolescence reason, replacement or consider annotation.",
                confidence="certain",
            )


def _superclass_edges(ctx: RuleContext) -> dict[URIRef, set[URIRef]]:
    g = ctx.g
    parents: dict[URIRef, set[URIRef]] = defaultdict(set)
    for c, p in g.subject_objects(RDFS.subClassOf):
        if isinstance(c, URIRef) and isinstance(p, URIRef):
            parents[c].add(p)
    for c, e in g.subject_objects(OWL.equivalentClass):
        if isinstance(c, URIRef) and isinstance(e, URIRef):
            parents[c].add(e)
            parents[e].add(c)
        elif isinstance(c, URIRef):
            for head in g.objects(e, OWL.intersectionOf):
                parents[c].update(i for i in list_items(g, head) or [] if isinstance(i, URIRef))
    return parents


def _closure(seeds: Iterable[URIRef], children: dict[URIRef, set[URIRef]]) -> set[URIRef]:
    seen: set[URIRef] = set()
    stack = list(seeds)
    while stack:
        node = stack.pop()
        if node not in seen:
            seen.add(node)
            stack.extend(children.get(node, ()))
    return seen


def _bfo_placement(ctx: RuleContext, deprecated: frozenset[URIRef]) -> None:
    parents = _superclass_edges(ctx)
    nodes = set(parents) | {p for ps in parents.values() for p in ps} | set(ctx.classes)
    children: dict[URIRef, set[URIRef]] = defaultdict(set)
    for child, ps in parents.items():
        for parent in ps:
            children[parent].add(child)
    bfo = {n for n in nodes if str(n).startswith(BFO_PREFIX)}
    # Only a class with no asserted superclass can be reported, and such a class is settled only by being BFO
    # itself (a chain leaving the graph at an undeclared term always gives it a superclass).
    settled = _closure(bfo, children)
    for cls in sorted(ctx.classes, key=str):
        if cls not in settled and cls not in deprecated and not parents.get(cls, set()) - {OWL.Thing}:
            ctx.add("OBO008", cls, "Class has no asserted superclass and no path to a BFO class.")


def _synonym_scope(ctx: RuleContext) -> None:
    for predicate in UNSCOPED_SYNONYMS:
        for s, o in sorted(ctx.g.subject_objects(predicate), key=lambda pair: (str(pair[0]), str(pair[1]))):
            if isinstance(s, URIRef) and ctx.local(s) and isinstance(o, Literal) and str(o).strip():
                ctx.add("OBO009", s, f"Synonym {_quote(str(o))} ({predicate}) has no scope.")


def _module_imports(ctx: RuleContext) -> None:
    for ontology, target in sorted(ctx.g.subject_objects(OWL.imports), key=lambda pair: (str(pair[0]), str(pair[1]))):
        if str(target) in FOUNDATIONAL_IMPORTS:
            continue
        if isinstance(target, URIRef) and any(p.fullmatch(str(target)) for p in FULL_IMPORT_PATTERNS):
            ctx.add("OBO010", ontology, f"Import {target} is a whole ontology, not an import module.")


def _purl_pattern(ctx: RuleContext) -> None:
    for ontology in sorted(ctx.ontologies, key=str):
        match = ONTOLOGY_PATTERN.fullmatch(str(ontology))
        if match is None:
            ctx.add(
                "OBO011",
                ontology,
                f"Ontology IRI {ontology} does not follow the OBO PURL pattern {OBO_NS}<id>.owl.",
                confidence="certain",
            )
        for version in _ordered(ctx.g.objects(ontology, OWL.versionIRI)):
            found = VERSION_PATTERN.fullmatch(str(version))
            if not isinstance(version, URIRef) or found is None or (match and found.group(1) != match.group(1)):
                ctx.add(
                    "OBO011",
                    ontology,
                    f"Version IRI {version} does not follow {OBO_NS}<id>/releases/YYYY-MM-DD/<id>.owl.",
                    confidence="certain",
                )


def _label_conventions(ctx: RuleContext, terms: list[URIRef], deprecated: frozenset[URIRef]) -> None:
    for term in terms:
        if term in deprecated:
            continue
        for label in _texts(ctx.g, term, RDFS.label):
            text = str(label)
            shown = _quote(text)
            if text != text.strip() or "  " in text:
                ctx.add("OBO012", term, f"Label {shown} has leading, trailing or repeated whitespace.")
            if "_" in text:
                ctx.add("OBO012", term, f"Label {shown} contains an underscore.")


def run(ctx: RuleContext) -> None:
    """Emit OBO001-OBO012."""
    terms = _terms(ctx)
    deprecated = _deprecated(ctx)
    _identifier_pattern(ctx, terms, deprecated)
    _required_metadata(ctx)
    _definitions(ctx, terms, deprecated)
    _labels(ctx, terms, deprecated)
    _ro_duplicates(ctx, deprecated)
    _definition_sources(ctx, terms, deprecated)
    _obsolescence(ctx, terms, deprecated)
    _bfo_placement(ctx, deprecated)
    _synonym_scope(ctx)
    _module_imports(ctx)
    _purl_pattern(ctx)
    _label_conventions(ctx, terms, deprecated)
