"""Deterministic synthetic ontology generators for large-input benchmarks."""

from __future__ import annotations

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS

EX = Namespace("https://bench.example/onto/")
ONTOLOGY = URIRef("https://bench.example/onto")


def _base() -> Graph:
    graph = Graph()
    graph.bind("ex", EX)
    graph.add((ONTOLOGY, RDF.type, OWL.Ontology))
    graph.add((ONTOLOGY, DCTERMS.license, URIRef("https://creativecommons.org/licenses/by/4.0/")))
    graph.add((ONTOLOGY, OWL.versionInfo, Literal("1.0")))
    return graph


def _declare(graph: Graph, index: int) -> URIRef:
    term = EX[f"C{index}"]
    graph.add((term, RDF.type, OWL.Class))
    graph.add((term, RDFS.label, Literal(f"Class {index}", lang="en")))
    graph.add((term, RDFS.comment, Literal(f"Definition of class {index}.", lang="en")))
    return term


def deep_chain(size: int) -> Graph:
    """Return a single subclass chain ``C0 <- C1 <- ... <- C{size-1}``."""
    graph = _base()
    previous = _declare(graph, 0)
    for index in range(1, size):
        term = _declare(graph, index)
        graph.add((term, RDFS.subClassOf, previous))
        previous = term
    return graph


def wide_tree(size: int, fanout: int = 10) -> Graph:
    """Return a balanced tree of ``size`` classes with the given fan-out."""
    graph = _base()
    terms = [_declare(graph, index) for index in range(size)]
    for index in range(1, size):
        graph.add((terms[index], RDFS.subClassOf, terms[(index - 1) // fanout]))
    return graph


def dense_dag(size: int, parents: int = 5) -> Graph:
    """Return a layered DAG where each class has up to ``parents`` earlier parents."""
    graph = _base()
    terms = [_declare(graph, index) for index in range(size)]
    for index in range(1, size):
        for step in range(1, min(parents, index) + 1):
            graph.add((terms[index], RDFS.subClassOf, terms[index - 1 - (step * 7919) % index]))
    return graph


def many_labels(size: int) -> Graph:
    """Return a SKOS vocabulary of ``size`` concepts with multilingual labels."""
    graph = _base()
    scheme = EX["scheme"]
    graph.add((scheme, RDF.type, SKOS.ConceptScheme))
    for index in range(size):
        concept = EX[f"T{index}"]
        graph.add((concept, RDF.type, SKOS.Concept))
        graph.add((concept, SKOS.inScheme, scheme))
        graph.add((concept, SKOS.prefLabel, Literal(f"Term {index}", lang="en")))
        graph.add((concept, SKOS.prefLabel, Literal(f"Terme {index}", lang="fr")))
        graph.add((concept, SKOS.altLabel, Literal(f"Alt {index % 5000}", lang="en")))
        graph.add((concept, SKOS.definition, Literal(f"Definition of term {index}.", lang="en")))
        if index:
            graph.add((concept, SKOS.broader, EX[f"T{(index - 1) // 20}"]))
    return graph
