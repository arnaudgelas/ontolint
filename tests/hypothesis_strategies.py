"""Shared Hypothesis strategies and profiles for the ``tests/test_properties_*.py`` suite.

Profiles
--------
``HYPOTHESIS_PROFILE`` selects how hard the property tests work: ``default`` (about 150 examples per
property, whole suite well under a minute) or ``ci-deep`` (10x more).  :func:`budget` scales an
individual test relative to the active profile, so expensive properties (full linting) use a fraction.

Strategies
----------
Graphs are small (a few dozen triples) and drawn from a deliberately tiny vocabulary so that terms
collide: an owned namespace, a foreign namespace, OBO-style identifiers, built-in rdf/rdfs/owl/skos/
dcterms terms, blank nodes from a small shared pool and hostile literals.  Triples come from *patterns*
(type declarations, hierarchies, restrictions, RDF lists built correctly and incorrectly, ontology
headers, SKOS relations, mappings, deprecation, nested blank nodes) plus a few completely random triples.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from typing import Any

from hypothesis import HealthCheck, settings
from hypothesis import strategies as st
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS, XSD
from rdflib.term import Node

from ontolint.policy import Policy
from ontolint.rules.specs import SEVERITY

type Triple = tuple[Node, Node, Node]

# --- profiles ----------------------------------------------------------------------------------------

_CHECKS = [HealthCheck.too_slow, HealthCheck.data_too_large, HealthCheck.filter_too_much]
settings.register_profile(
    "default", settings(max_examples=150, deadline=None, print_blob=True, suppress_health_check=_CHECKS)
)
settings.register_profile(
    "ci-deep", settings(max_examples=1500, deadline=None, print_blob=True, suppress_health_check=_CHECKS)
)
PROFILE_NAME = os.environ.get("HYPOTHESIS_PROFILE", "default")
PROFILE = settings.get_profile(PROFILE_NAME)


def budget(fraction: float = 1.0, floor: int = 10) -> settings:
    """Settings for one property: the active profile scaled by ``fraction`` (never below ``floor`` examples)."""
    return settings(PROFILE, max_examples=max(floor, int(PROFILE.max_examples * fraction)))


# --- vocabulary --------------------------------------------------------------------------------------

BASE = "https://example.test/onto#"
FOREIGN = "https://other.example/ns#"
OBO = "http://purl.obolibrary.org/obo/"
OWNED_NAMES = ("A", "B", "C", "D", "E", "p", "q", "r", "Café", "日本語", "a_b", "Thing2", "has_part")

OWNED = tuple(URIRef(BASE + n) for n in OWNED_NAMES)
FOREIGN_TERMS = tuple(URIRef(FOREIGN + n) for n in ("X", "Y", "z"))
OBO_TERMS = tuple(URIRef(OBO + n) for n in ("TST_0000001", "TST_0000002", "tst_0000003", "RO_0000087", "IAO_0000115"))
ONTOLOGY_IRIS = (
    URIRef("https://example.test/onto"),
    URIRef(BASE),
    URIRef(OBO + "tst.owl"),
    URIRef("https://other.example/ns"),
)
ODD_IRIS = (
    URIRef("relative.owl"),
    URIRef("urn:x:1"),
    URIRef("https://example.test/with space"),
    URIRef(""),
    URIRef("s://]"),  # urlsplit raises ValueError on this one
)

KIND_TYPES = (
    OWL.Class,
    RDFS.Class,
    OWL.ObjectProperty,
    OWL.DatatypeProperty,
    OWL.AnnotationProperty,
    RDF.Property,
    SKOS.Concept,
    SKOS.ConceptScheme,
    SKOS.Collection,
    OWL.NamedIndividual,
)
OTHER_TYPES = (
    OWL.Ontology,
    OWL.Restriction,
    OWL.FunctionalProperty,
    OWL.InverseFunctionalProperty,
    OWL.TransitiveProperty,
    OWL.SymmetricProperty,
    OWL.AsymmetricProperty,
    OWL.ReflexiveProperty,
    OWL.IrreflexiveProperty,
    OWL.AllDisjointClasses,
    OWL.AllDifferent,
    OWL.Axiom,
    OWL.DeprecatedClass,
    OWL.DeprecatedProperty,
    OWL.Thing,
    URIRef("http://www.w3.org/ns/shacl#NodeShape"),
    URIRef(FOREIGN + "Custom"),
)
ALL_TYPES = KIND_TYPES + OTHER_TYPES
LABEL_PREDICATES = (RDFS.label, SKOS.prefLabel, SKOS.altLabel, SKOS.hiddenLabel, URIRef(OBO + "IAO_0000118"))
COMMENT_PREDICATES = (
    RDFS.comment,
    SKOS.definition,
    SKOS.scopeNote,
    DCTERMS.description,
    URIRef(OBO + "IAO_0000115"),
    URIRef(OBO + "IAO_0000600"),
)
HEADER_PREDICATES = (
    DCTERMS.title,
    DCTERMS.license,
    DCTERMS.creator,
    DCTERMS.contributor,
    DCTERMS.created,
    DCTERMS.description,
    OWL.versionIRI,
    OWL.versionInfo,
    OWL.imports,
    OWL.priorVersion,
    RDFS.seeAlso,
    RDFS.isDefinedBy,
)
CLASS_RELATIONS = (RDFS.subClassOf, OWL.equivalentClass, OWL.disjointWith, OWL.complementOf)
PROPERTY_RELATIONS = (RDFS.subPropertyOf, OWL.inverseOf, OWL.equivalentProperty, OWL.propertyDisjointWith)
SKOS_RELATIONS = (
    SKOS.broader,
    SKOS.narrower,
    SKOS.related,
    SKOS.broaderTransitive,
    SKOS.narrowerTransitive,
    SKOS.inScheme,
    SKOS.topConceptOf,
    SKOS.hasTopConcept,
    SKOS.member,
)
MAPPING_PREDICATES = (
    SKOS.exactMatch,
    SKOS.closeMatch,
    SKOS.broadMatch,
    SKOS.narrowMatch,
    SKOS.relatedMatch,
    SKOS.mappingRelation,
    OWL.sameAs,
)
RESTRICTION_FILLERS = (
    OWL.someValuesFrom,
    OWL.allValuesFrom,
    OWL.hasValue,
    OWL.cardinality,
    OWL.minCardinality,
    OWL.maxCardinality,
    OWL.onClass,
    OWL.onDataRange,
    OWL.hasSelf,
)
LIST_OWNERS = (
    OWL.unionOf,
    OWL.intersectionOf,
    OWL.oneOf,
    OWL.propertyChainAxiom,
    OWL.disjointUnionOf,
    OWL.members,
    OWL.distinctMembers,
    OWL.hasKey,
)
ANY_PREDICATES = (
    (RDF.type,)
    + LABEL_PREDICATES
    + COMMENT_PREDICATES
    + HEADER_PREDICATES
    + CLASS_RELATIONS
    + PROPERTY_RELATIONS
    + SKOS_RELATIONS
    + MAPPING_PREDICATES
    + (RDFS.domain, RDFS.range, OWL.deprecated, OWL.onProperty, RDF.first, RDF.rest, FOREIGN_TERMS[0])
)
DEPRECATION_POINTERS = (DCTERMS.isReplacedBy, DCTERMS.replaces, URIRef(OBO + "IAO_0100001"), OWL.deprecated)

BNODES = tuple(BNode(f"QBNA{i}") for i in range(12))
BNODE_LABEL = re.compile(r"QBN[A-Z]\w*")

# --- terms and literals ------------------------------------------------------------------------------

iris = st.sampled_from(OWNED + FOREIGN_TERMS + OBO_TERMS)
owned_iris = st.sampled_from(OWNED)
class_iris = st.sampled_from(OWNED[:5] + FOREIGN_TERMS[:2] + OBO_TERMS[:3] + (OWL.Thing, OWL.Nothing))
property_iris = st.sampled_from(OWNED[5:8] + OWNED[12:] + FOREIGN_TERMS[2:] + OBO_TERMS[3:4] + (RDFS.label,))
ontology_iris = st.sampled_from(ONTOLOGY_IRIS)
bnodes = st.sampled_from(BNODES)
subjects = st.one_of(iris, iris, iris, bnodes, st.sampled_from(ODD_IRIS), st.sampled_from(ONTOLOGY_IRIS))
terms = st.one_of(iris, iris, bnodes, st.sampled_from(ALL_TYPES + ODD_IRIS))

RLO, PDF_, BOM = chr(0x202E), chr(0x202C), chr(0xFEFF)
_HOSTILE = (
    "",
    " ",
    "  padded  ",
    "\u200b",
    RLO + "evil" + PDF_,
    "á",
    "tab\there",
    "line\nbreak",
    "\x00nul",
    "\x1b[31mred",
    BOM + "bom",
    " nbsp",
    "😀 emoji",
    "Ünïcödé שלום مرحبا",
    "x" * 2500,
    "<script>&amp;</script>",
    'quote"s and \\backslashes\\',
    "A_label",
    "label with several words in it",
)
_texts = st.one_of(
    st.sampled_from(_HOSTILE),
    st.text(max_size=40),
    st.text(alphabet=st.characters(codec="ascii", categories=("L", "N", "Zs", "P")), max_size=30),
)
LANGS = ("en", "fr", "en-GB", "de", "EN", "ja", "x-klingon", "zh-Hant")
_datatypes = (
    XSD.string,
    XSD.integer,
    XSD.boolean,
    XSD.date,
    XSD.dateTime,
    XSD.anyURI,
    XSD.decimal,
    RDF.langString,
    URIRef(FOREIGN + "custom"),
)


@st.composite
def literals(draw: st.DrawFn) -> Literal:
    """Plain, language-tagged and typed literals, including empty, huge, control and bidi text."""
    text = draw(_texts)
    kind = draw(st.sampled_from(("plain", "plain", "lang", "lang", "typed", "number", "bool", "int")))
    if kind == "lang":
        return Literal(text, lang=draw(st.sampled_from(LANGS)))
    if kind == "typed":
        datatype = draw(st.sampled_from((XSD.string, XSD.anyURI, URIRef(FOREIGN + "custom"))))
        return Literal(text, datatype=datatype)
    if kind == "number":
        datatype = draw(st.sampled_from((XSD.integer, XSD.decimal, XSD.date, XSD.dateTime)))
        lexical = {XSD.date: "2026-01-02", XSD.dateTime: "2026-01-02T03:04:05"}.get(datatype, "42")
        return Literal(lexical, datatype=datatype)
    if kind == "int":
        return Literal(draw(st.integers(-5, 5)))
    if kind == "bool":
        return Literal(draw(st.booleans()))
    return Literal(text)


def xml_safe_text(text: str) -> bool:
    """Whether ``text`` survives every RDF serialisation (no C0 controls except whitespace, no BOM)."""
    return all(c in "\t\n" or (c >= " " and c != "\x7f" and c not in BOM + "\ufffe\uffff") for c in text)


nodes = st.one_of(terms, literals())
objects_ = st.one_of(iris, iris, bnodes, st.sampled_from(ALL_TYPES), literals())

# --- triple patterns ---------------------------------------------------------------------------------


def _fresh(draw: st.DrawFn) -> BNode:
    return draw(bnodes)


@st.composite
def _declaration(draw: st.DrawFn) -> list[Triple]:
    triples: list[Triple] = [(draw(subjects), RDF.type, draw(st.sampled_from(ALL_TYPES)))]
    if draw(st.booleans()):
        triples.append((triples[0][0], RDF.type, draw(st.sampled_from(KIND_TYPES))))
    return triples


@st.composite
def _annotation(draw: st.DrawFn) -> list[Triple]:
    predicate = draw(st.sampled_from(LABEL_PREDICATES + COMMENT_PREDICATES))
    value = draw(st.one_of(literals(), literals(), iris, bnodes))
    return [(draw(subjects), predicate, value)]


@st.composite
def _hierarchy(draw: st.DrawFn) -> list[Triple]:
    relation = draw(st.sampled_from(CLASS_RELATIONS + CLASS_RELATIONS[:1] * 4))
    child, parent = draw(class_iris), draw(st.one_of(class_iris, bnodes, literals()))
    triples: list[Triple] = [(child, relation, parent)]
    if draw(st.booleans()):
        triples.append((child, RDF.type, OWL.Class))
    if draw(st.booleans()) and isinstance(parent, URIRef):
        triples.append((parent, RDF.type, OWL.Class))
    return triples


@st.composite
def _property_axiom(draw: st.DrawFn) -> list[Triple]:
    prop = draw(property_iris)
    triples: list[Triple] = [(prop, RDF.type, draw(st.sampled_from(KIND_TYPES[2:6] + OTHER_TYPES[2:9])))]
    triples.append((prop, draw(st.sampled_from(PROPERTY_RELATIONS)), draw(st.one_of(property_iris, bnodes))))
    if draw(st.booleans()):
        triples.append((prop, RDFS.domain, draw(st.one_of(class_iris, bnodes, literals()))))
    if draw(st.booleans()):
        triples.append((prop, RDFS.range, draw(st.one_of(class_iris, st.sampled_from(_datatypes), bnodes))))
    return triples


@st.composite
def _restriction(draw: st.DrawFn) -> list[Triple]:
    node = _fresh(draw)
    triples: list[Triple] = []
    if draw(st.integers(0, 9)):  # Occasionally leave the restriction untyped.
        triples.append((node, RDF.type, OWL.Restriction))
    if draw(st.integers(0, 9)):  # ... or without owl:onProperty.
        triples.append((node, OWL.onProperty, draw(st.one_of(property_iris, bnodes))))
    for _ in range(draw(st.integers(0, 2))):
        filler = draw(st.sampled_from(RESTRICTION_FILLERS))
        value = draw(st.one_of(class_iris, literals(), bnodes, st.just(Literal(1))))
        triples.append((node, filler, value))
    triples.append((draw(class_iris), draw(st.sampled_from((RDFS.subClassOf, OWL.equivalentClass))), node))
    return triples


@st.composite
def _rdf_list(draw: st.DrawFn) -> list[Triple]:
    """An RDF list attached to a list-valued predicate; ``flaw`` makes it malformed in a specific way."""
    members = draw(st.lists(st.one_of(class_iris, property_iris, bnodes, literals()), max_size=5))
    cells = draw(st.lists(bnodes, min_size=len(members), max_size=len(members), unique=True))
    flaw = draw(st.sampled_from(("ok", "ok", "ok", "no-rest", "cycle", "two-firsts", "no-first", "no-nil", "literal")))
    triples: list[Triple] = []
    for index, (cell, member) in enumerate(zip(cells, members, strict=True)):
        tail: Node = cells[index + 1] if index + 1 < len(cells) else RDF.nil
        triples.append((cell, RDF.first, member))
        triples.append((cell, RDF.rest, tail))
    if cells:
        last = cells[-1]
        match flaw:
            case "no-rest":
                triples.remove((last, RDF.rest, RDF.nil))
            case "cycle":
                triples.append((last, RDF.rest, cells[0]))
            case "two-firsts":
                triples.append((cells[0], RDF.first, Literal("extra")))
            case "no-first":
                triples.remove((cells[0], RDF.first, members[0]))
            case "no-nil":
                triples.remove((last, RDF.rest, RDF.nil))
                triples.append((last, RDF.rest, draw(iris)))
            case _:
                pass
    head: Node = cells[0] if cells else RDF.nil
    if flaw == "literal":
        head = Literal("not a list")
    triples.append((draw(st.one_of(class_iris, property_iris, bnodes)), draw(st.sampled_from(LIST_OWNERS)), head))
    return triples


@st.composite
def _ontology_header(draw: st.DrawFn) -> list[Triple]:
    ontology = draw(ontology_iris)
    triples: list[Triple] = [(ontology, RDF.type, OWL.Ontology)]
    for predicate in draw(st.lists(st.sampled_from(HEADER_PREDICATES), max_size=5, unique=True)):
        triples.append((ontology, predicate, draw(st.one_of(literals(), iris, ontology_iris))))
    return triples


@st.composite
def _skos(draw: st.DrawFn) -> list[Triple]:
    concept = draw(iris)
    triples: list[Triple] = [
        (concept, RDF.type, draw(st.sampled_from((SKOS.Concept, SKOS.Concept, SKOS.ConceptScheme))))
    ]
    for _ in range(draw(st.integers(1, 3))):
        predicate = draw(st.sampled_from(SKOS_RELATIONS + MAPPING_PREDICATES))
        triples.append((concept, predicate, draw(st.one_of(iris, bnodes, literals()))))
    return triples


@st.composite
def _deprecation(draw: st.DrawFn) -> list[Triple]:
    term = draw(iris)
    value = draw(st.sampled_from((Literal(True), Literal("true"), Literal(False), Literal("yes"))))
    triples: list[Triple] = [(term, OWL.deprecated, value), (term, RDF.type, draw(st.sampled_from(KIND_TYPES)))]
    if draw(st.booleans()):
        triples.append((term, draw(st.sampled_from(DEPRECATION_POINTERS[:3])), draw(st.one_of(iris, literals()))))
    return triples


@st.composite
def _nested_bnodes(draw: st.DrawFn) -> list[Triple]:
    """A chain/tree/cycle of blank nodes hanging from an IRI (SEC004 territory)."""
    chain = draw(st.lists(bnodes, min_size=1, max_size=8))
    predicate = draw(st.sampled_from((OWL.someValuesFrom, RDFS.subClassOf, OWL.unionOf, RDF.rest, RDF.first)))
    triples: list[Triple] = [(draw(iris), draw(st.sampled_from((RDFS.subClassOf, OWL.equivalentClass))), chain[0])]
    triples.extend((a, predicate, b) for a, b in zip(chain, chain[1:], strict=False))
    return triples


@st.composite
def _random_triple(draw: st.DrawFn) -> list[Triple]:
    return [(draw(subjects), draw(st.sampled_from(ANY_PREDICATES)), draw(nodes))]


@st.composite
def _label_cluster(draw: st.DrawFn) -> list[Triple]:
    """Several terms with labels in assorted languages and forms (naming-convention rules)."""
    triples: list[Triple] = []
    for term in draw(st.lists(owned_iris, min_size=1, max_size=4, unique=True)):
        triples.append((term, RDF.type, draw(st.sampled_from(KIND_TYPES))))
        triples.extend((term, RDFS.label, draw(literals())) for _ in range(draw(st.integers(0, 3))))
        if draw(st.booleans()):
            triples.append((term, draw(st.sampled_from(COMMENT_PREDICATES)), draw(literals())))
    return triples


@st.composite
def _multi_valued(draw: st.DrawFn) -> list[Triple]:
    """One subject with several values for one predicate (exposes "first value wins" nondeterminism)."""
    subject = draw(st.one_of(iris, bnodes))
    predicate = draw(st.sampled_from(ANY_PREDICATES + (OWL.onProperty, OWL.onClass, OWL.allValuesFrom)))
    return [(subject, predicate, value) for value in draw(st.lists(nodes, min_size=2, max_size=3))]


PATTERNS: tuple[st.SearchStrategy[list[Triple]], ...] = (
    _declaration(),
    _declaration(),
    _annotation(),
    _annotation(),
    _hierarchy(),
    _hierarchy(),
    _property_axiom(),
    _restriction(),
    _rdf_list(),
    _ontology_header(),
    _skos(),
    _deprecation(),
    _nested_bnodes(),
    _label_cluster(),
    _random_triple(),
    _multi_valued(),
    _multi_valued(),
)


@st.composite
def triple_lists(draw: st.DrawFn, max_patterns: int = 16, min_patterns: int = 2) -> list[Triple]:
    """A list of triples (ordered, possibly duplicated) assembled from random patterns."""
    out: list[Triple] = []
    for pattern in draw(st.lists(st.one_of(*PATTERNS), min_size=min_patterns, max_size=max_patterns)):
        out.extend(pattern)
    return out


def build_graph(triples: Sequence[Triple]) -> Graph:
    """Insert ``triples`` into a fresh graph in the given order."""
    graph = Graph()
    for triple in triples:
        graph.add(triple)
    return graph


rdf_graphs = triple_lists().map(build_graph)


@st.composite
def roundtrip_triple_lists(draw: st.DrawFn) -> list[Triple]:
    """Triples every RDF serialisation can carry: absolute IRIs, XML-safe text, lower-case language tags."""
    triples = draw(triple_lists(8))
    kept: list[Triple] = []
    for s, p, o in triples:
        if any(
            isinstance(n, URIRef) and not re.fullmatch(r"[A-Za-z][\w+.-]*:[^\s<>\"{}|\\^`]+", str(n)) for n in (s, p, o)
        ):
            continue
        if isinstance(s, URIRef) and not str(s):
            continue
        if isinstance(o, Literal):
            if not xml_safe_text(str(o)) or str(o) != str(o).strip() or not str(o):
                continue
            if o.language:
                kept.append((s, p, Literal(str(o), lang=o.language.lower())))
                continue
            if o.datatype is not None:
                o = Literal(str(o))  # noqa: PLW2901 -- typed lexical forms may be ill-typed; keep plain text.
        if isinstance(s, URIRef) and s in (OWL.Ontology,):
            continue
        kept.append((s, p, o))
    return kept


# --- shapes ------------------------------------------------------------------------------------------

SH = "http://www.w3.org/ns/shacl#"


@st.composite
def shapes_graphs(draw: st.DrawFn) -> tuple[Graph, bool]:
    """A small SHACL shapes graph; the flag is True when it was made deliberately malformed."""
    graph = Graph()
    malformed = draw(st.booleans())
    for index in range(draw(st.integers(0, 2))):
        shape = URIRef(f"{BASE}Shape{index}")
        graph.add((shape, RDF.type, URIRef(SH + "NodeShape")))
        graph.add((shape, URIRef(SH + "targetClass"), draw(class_iris)))
        prop = BNode(f"QBNA{index}")
        graph.add((shape, URIRef(SH + "property"), prop))
        graph.add((prop, URIRef(SH + "path"), draw(property_iris)))
        graph.add((prop, URIRef(SH + "minCount"), Literal(draw(st.integers(0, 2)))))
        if draw(st.booleans()):
            graph.add((prop, URIRef(SH + "datatype"), XSD.string))
    if malformed:
        graph.add((URIRef(BASE + "Bad"), URIRef(SH + "property"), draw(st.one_of(literals(), bnodes))))
        graph.add((URIRef(BASE + "Bad"), URIRef(SH + "minCount"), Literal("many")))
        graph.add((URIRef(BASE + "Bad"), URIRef(SH + "pattern"), Literal("(unclosed")))
        graph.add((URIRef(BASE + "Bad"), URIRef(SH + "path"), draw(bnodes)))
    return graph, malformed


# --- policy, selectors and configuration -------------------------------------------------------------

BASES = (
    None,
    BASE,
    "https://example.test/onto",
    "https://example.test/",
    FOREIGN,
    OBO + "TST_",
    OBO,
    "https://nowhere.example/",
)
RULE_IDS = tuple(sorted(SEVERITY))
FAMILIES = tuple(sorted({r.rstrip("0123456789") for r in RULE_IDS}))
_INTS = st.integers(0, 12)
_RATIOS = st.sampled_from((0.0, 0.1, 0.5, 0.9, 1.0))
_QUANTITIES = st.sampled_from((0.0, 0.5, 2.0, 8.0, 100.0))
_PREDICATE_IRIS = st.sampled_from((FOREIGN + "label", FOREIGN + "def", "urn:x:p", OBO + "IAO_0000118"))


@st.composite
def valid_policy_mappings(draw: st.DrawFn) -> dict[str, Any]:
    """JSON-like mappings that :meth:`Policy.from_mapping` must accept (every key optional)."""
    optional: dict[str, st.SearchStrategy[Any]] = {
        "base": st.one_of(st.none(), st.sampled_from(BASES[1:]), st.just("")),
        "languages": st.lists(st.sampled_from(LANGS), max_size=3),
        "depth_limit": _INTS,
        "inheritance_limit": _INTS,
        "soup_limit": _INTS,
        "metric_min_sample": st.integers(1, 12),
        "metric_max_imports": _INTS,
        "metric_max_unlabelled_ratio": _RATIOS,
        "metric_max_undefined_ratio": _RATIOS,
        "metric_max_undocumented_property_ratio": _RATIOS,
        "metric_max_orphan_ratio": _RATIOS,
        "metric_max_unsigned_property_ratio": _RATIOS,
        "metric_min_language_coverage": _RATIOS,
        "metric_max_foreign_reference_ratio": _RATIOS,
        "metric_max_blank_node_ratio": _RATIOS,
        "metric_max_mean_fanout": _QUANTITIES,
        "metric_min_property_class_ratio": _QUANTITIES,
        "metric_max_property_class_ratio": _QUANTITIES,
        "metric_min_definition_words": _QUANTITIES,
        "max_input_bytes": st.integers(1, 10**9),
        "max_triples": st.integers(1, 10**7),
        "max_import_depth": st.integers(1, 64),
        "max_imported_files": st.integers(1, 1000),
        "extra_definition_predicates": st.lists(_PREDICATE_IRIS, max_size=3),
        "extra_label_predicates": st.lists(_PREDICATE_IRIS, max_size=3),
        "ignored_rules": st.lists(st.sampled_from(RULE_IDS + ("NOPE999",)), max_size=4),
        "required_annotations": st.dictionaries(
            st.sampled_from(("class", "property", "individual", "concept")),
            st.lists(_PREDICATE_IRIS, max_size=3),
            max_size=4,
        ),
        "alignment_namespaces": st.lists(_PREDICATE_IRIS, max_size=3),
        "alignment_min_coverage": st.one_of(st.none(), _RATIOS),
        "policy_version": st.just(1),
        "severity_overrides": st.dictionaries(
            st.sampled_from(RULE_IDS), st.sampled_from(("error", "warning", "info")), max_size=4
        ),
    }
    mapping = {key: draw(strategy) for key, strategy in optional.items() if draw(st.booleans())}
    # A property-to-class minimum above the maximum is a contradictory policy, which is rejected.
    low = mapping.get("metric_min_property_class_ratio", Policy().metric_min_property_class_ratio)
    if low > mapping.get("metric_max_property_class_ratio", Policy().metric_max_property_class_ratio):
        mapping["metric_max_property_class_ratio"] = low
    return mapping


@st.composite
def policies(draw: st.DrawFn) -> Policy:
    """Valid policies (always built through :meth:`Policy.from_mapping`)."""
    return Policy.from_mapping(draw(valid_policy_mappings()))


@st.composite
def linter_options(draw: st.DrawFn) -> dict[str, Any]:
    """Keyword arguments accepted by :class:`ontolint.Linter`."""
    options: dict[str, Any] = {}
    if draw(st.booleans()):
        options["base"] = draw(st.sampled_from(BASES[1:]))
    if draw(st.booleans()):
        options["languages"] = tuple(draw(st.lists(st.sampled_from(LANGS), max_size=2)))
    for name in ("depth_limit", "inheritance_limit", "soup_limit"):
        if draw(st.booleans()):
            options[name] = draw(st.integers(1, 6))
    return options


json_scalars = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(-(2**70), 2**70),
    st.floats(allow_nan=True, allow_infinity=True),
    st.text(max_size=12),
)
json_values: st.SearchStrategy[Any] = st.recursive(
    json_scalars,
    lambda inner: st.one_of(st.lists(inner, max_size=3), st.dictionaries(st.text(max_size=8), inner, max_size=3)),
    max_leaves=8,
)


@st.composite
def hostile_mappings(draw: st.DrawFn) -> dict[str, Any]:
    """A valid mapping with some values replaced by arbitrary JSON, plus unknown keys."""
    mapping = draw(valid_policy_mappings())
    keys = list(mapping) or ["base"]
    for key in draw(st.lists(st.sampled_from(keys + ["depth_limit", "languages", "unknown_key"]), max_size=3)):
        mapping[key] = draw(json_values)
    return mapping


@st.composite
def selector_tokens(draw: st.DrawFn) -> str:
    """A valid rule selector: a rule id or a family, in any case."""
    token = draw(st.sampled_from(RULE_IDS + FAMILIES))
    return draw(st.sampled_from((token, token.lower())))


selector_lists = st.lists(selector_tokens(), max_size=5)


def canonical(text: str) -> str:
    """Replace blank-node labels in ``text`` by one token so relabelled graphs compare equal."""
    return BNODE_LABEL.sub("_:B", text)
