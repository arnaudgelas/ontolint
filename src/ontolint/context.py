"""Asserted-graph indexes shared by graph-local ontology rules.

The context deliberately never follows imports or materializes entailments.  Its
contents describe exactly the graph supplied to :class:`ontolint.Linter`.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SH, SKOS
from rdflib.term import Node

from .ownership import Ownership

KINDS = (
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
CLASS_TYPES = (OWL.Class, RDFS.Class)
PROPERTY_TYPES = (OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty, RDF.Property)


def _everything(_value: object) -> bool:
    return True


def _published_ontologies(graph: Graph, ontologies: set[URIRef], imported: frozenset[str]) -> set[URIRef]:
    """The ``owl:Ontology`` nodes that stand for the linted ontology, dropping two kinds of extra header.

    SHACL-SPARQL declares prefixes on an owl:Ontology node (``ex:Prefixes a owl:Ontology ; sh:declare
    [...]``); next to a real ontology header such a node is a prefix declaration, not a second ontology.
    In an import closure (--follow-imports) the published ontology is the root: the headers of the
    imported modules are parts of it, so header rules and derived ownership judge the root only.
    """
    prefix_declarations = {node for node in ontologies if (node, SH.declare, None) in graph}
    if ontologies - prefix_declarations:
        ontologies = ontologies - prefix_declarations
    root_only = {node for node in ontologies if str(node) not in imported}
    return root_only or ontologies


# gremlin: pardon[untestable] every test covers a decorator: too slow to time; test_mutation_pardon_audit kills it
@dataclass(frozen=True)
class GraphContext:
    """Cached graph facts used repeatedly by local lint rules."""

    ontologies: frozenset[URIRef]
    classes: frozenset[URIRef]
    properties: frozenset[URIRef]
    concepts: frozenset[URIRef]
    terms: frozenset[URIRef]
    subjects_by_type: Mapping[Node, frozenset[Node]]
    types_by_subject: Mapping[Node, frozenset[Node]]
    domains_by_property: Mapping[Node, frozenset[Node]]
    ranges_by_property: Mapping[Node, frozenset[Node]]
    properties_by_domain: Mapping[Node, frozenset[URIRef]]
    subjects_by_predicate: Mapping[Node, frozenset[Node]]
    predicates: frozenset[Node]
    ownership: Ownership = Ownership()

    @classmethod
    def build(  # noqa: PLR0913 -- the graph, its locality override and three facts about the linted file.
        cls,
        graph: Graph,
        is_local: Callable[[object], bool] | None = None,
        *,
        restrict_to_local: bool = False,
        base: str | None = None,
        imported_ontologies: frozenset[str] = frozenset(),
        root_terms: frozenset[str] = frozenset(),
    ) -> GraphContext:
        """Index asserted triples once and keep only the terms the file owns.

        Ownership (see :mod:`ontolint.ownership`) comes from ``base`` when given, else from the
        ontology IRIs of the graph.  An explicit ``is_local`` predicate overrides it.
        """
        subjects_by_type: dict[Node, set[Node]] = defaultdict(set)
        types_by_subject: dict[Node, set[Node]] = defaultdict(set)
        domains_by_property: dict[Node, set[Node]] = defaultdict(set)
        ranges_by_property: dict[Node, set[Node]] = defaultdict(set)
        properties_by_domain: dict[Node, set[URIRef]] = defaultdict(set)
        subjects_by_predicate: dict[Node, set[Node]] = defaultdict(set)
        predicates: set[Node] = set()

        for subject, predicate, object_ in graph:
            predicates.add(predicate)
            subjects_by_predicate[predicate].add(subject)
            if predicate == RDF.type:
                subjects_by_type[object_].add(subject)
                types_by_subject[subject].add(object_)
            elif predicate == RDFS.domain:
                domains_by_property[subject].add(object_)
                if isinstance(subject, URIRef):
                    properties_by_domain[object_].add(subject)
            elif predicate == RDFS.range:
                ranges_by_property[subject].add(object_)

        def declared(type_: Node) -> set[URIRef]:
            return {subject for subject in subjects_by_type[type_] if isinstance(subject, URIRef)}

        ontologies = _published_ontologies(graph, declared(OWL.Ontology), imported_ontologies)
        classes = set().union(*(declared(type_) for type_ in CLASS_TYPES))
        properties = set().union(*(declared(type_) for type_ in PROPERTY_TYPES))
        concepts = declared(SKOS.Concept)
        terms = set().union(*(declared(type_) for type_ in KINDS))
        # In an import closure, the root file's own declarations decide ownership, so a large import never
        # outweighs them; an umbrella that declares no term leaves the decision to the whole closure.
        deciding = [t for t in terms if str(t) in root_terms] or terms
        ownership = Ownership.for_terms(base, ontologies, deciding)
        owns: Callable[[object], bool] = ownership.owns
        if is_local is not None:
            owns = is_local if restrict_to_local else _everything
        terms = {term for term in terms if owns(term)}
        classes = {term for term in classes if owns(term)}
        properties = {term for term in properties if owns(term)}
        concepts = {term for term in concepts if owns(term)}

        def frozen_mapping[T: Node, V: Node](mapping: Mapping[T, set[V]]) -> Mapping[T, frozenset[V]]:
            return MappingProxyType({key: frozenset(value) for key, value in mapping.items()})

        return cls(
            ontologies=frozenset(ontologies),
            classes=frozenset(classes),
            properties=frozenset(properties),
            concepts=frozenset(concepts),
            terms=frozenset(terms),
            subjects_by_type=frozen_mapping(subjects_by_type),
            types_by_subject=frozen_mapping(types_by_subject),
            domains_by_property=frozen_mapping(domains_by_property),
            ranges_by_property=frozen_mapping(ranges_by_property),
            properties_by_domain=frozen_mapping(properties_by_domain),
            subjects_by_predicate=frozen_mapping(subjects_by_predicate),
            predicates=frozenset(predicates),
            ownership=ownership,
        )
