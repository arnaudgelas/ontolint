"""Per-rule test harness: build small graphs from Turtle, run one rule, assert what it emits.

Rule authors never edit this file or the meta-tests.  They add ``tests/rule_cases/<family>.py``
exporting ``CASES`` (see :func:`rule_cases`); ``tests/test_rule_cases.py`` discovers it, requires at
least one positive and one negative case for every implemented rule, and runs them all.

* positive case  -- selecting only the rule yields findings, every one of them the rule's;
* negative case  -- selecting only the rule yields no finding of that rule;
* odd inputs     -- :data:`ODD_INPUTS` must never crash any rule module (see ``test_rule_cases``);
* boundary/scale -- :func:`threshold_cases` and :func:`chain_turtle` generate at-limit / over-limit
  fixtures for rules governed by a policy threshold or by hierarchy size.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from ontolint import Linter
from ontolint.models import ExecutionStatus

BASE = "https://example.test/onto#"
PREFIXES = f"""\
@prefix ex: <{BASE}> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
"""


def graph(turtle: str = "") -> Graph:
    """Parse a Turtle snippet (the standard prefixes are prepended) into a graph."""
    return Graph().parse(data=PREFIXES + turtle, format="turtle")


@dataclass(frozen=True)
class Case:
    """One named fixture.  Provide ``turtle``/``build`` for graph rules or ``probe`` for adapters.

    ``options`` are :class:`ontolint.Linter` keyword arguments (``base``, ``languages``, thresholds).
    ``probe`` returns the rule ids that the non-graph component (adapter, CLI front end) produced.
    """

    name: str
    turtle: str = ""
    build: Callable[[], Graph] | None = None
    shapes: str | None = None
    options: Mapping[str, Any] = field(default_factory=dict[str, Any])
    probe: Callable[[], Collection[str]] | None = None
    boundary: bool = False

    def emitted(self, rule_id: str) -> list[str]:
        """Return the rule ids emitted when only ``rule_id`` is selected (graph) or probed (non-graph)."""
        if self.probe is not None:
            return sorted(self.probe())
        data = self.build() if self.build else graph(self.turtle)
        shapes = graph(self.shapes) if self.shapes is not None else None
        result = Linter(data, shapes, **self.options).execute([rule_id])
        assert {x.status for x in result.executions} == {ExecutionStatus.EXECUTED}, result.executions
        return sorted(f.rule for f in result.findings)


@dataclass(frozen=True)
class RuleCases:
    """Positive and negative cases for one rule."""

    positive: tuple[Case, ...] = ()
    negative: tuple[Case, ...] = ()


def rule_cases(positive: Iterable[Case] = (), negative: Iterable[Case] = ()) -> RuleCases:
    """Bundle the cases of one rule; ``CASES = {"ONT001": rule_cases(...), ...}`` in a family file."""
    return RuleCases(tuple(positive), tuple(negative))


def ttl(name: str, turtle: str, **options: Any) -> Case:
    """A graph case from a Turtle snippet; keyword arguments become Linter options."""
    return Case(name, turtle, options=options)


def with_shapes(name: str, turtle: str, shapes: str, **options: Any) -> Case:
    """A graph case that also supplies a SHACL shapes graph."""
    return Case(name, turtle, shapes=shapes, options=options)


def built(name: str, build: Callable[[], Graph], **options: Any) -> Case:
    """A graph case for inputs Turtle cannot express (relative IRIs, whitespace in IRIs)."""
    return Case(name, build=build, options=options)


def probed(name: str, probe: Callable[[], Collection[str]]) -> Case:
    """A case for a non-graph rule; ``probe`` returns the rule ids it observed."""
    return Case(name, probe=probe)


# --- boundary and scale hooks ----------------------------------------------------------------


def chain_turtle(length: int, predicate: str = "rdfs:subClassOf", kind: str = "owl:Class") -> str:
    """Turtle for ``length`` terms linked ``ex:n0 predicate ex:n1 predicate ex:n2 ...``."""
    lines = [f"ex:n{i} a {kind} ." for i in range(length)]
    lines += [f"ex:n{i} {predicate} ex:n{i + 1} ." for i in range(length - 1)]
    return "\n".join(lines)


def threshold_cases(
    option: str, limit: int, factory: Callable[[int], str], **fixed: Any
) -> tuple[tuple[Case, ...], tuple[Case, ...]]:
    """Return ``(positive, negative)`` boundary cases for a ``> limit`` policy threshold.

    ``factory(n)`` returns Turtle whose measured quantity is ``n``.  The negative case sits exactly
    at the limit and the positive case one above it, so off-by-one mistakes are caught.
    """
    options = {option: limit, **fixed}
    over = Case(f"{option}={limit} with {limit + 1}", factory(limit + 1), options=options, boundary=True)
    at = Case(f"{option}={limit} with {limit}", factory(limit), options=options, boundary=True)
    return (over,), (at,)


# --- odd and hostile inputs ------------------------------------------------------------------

HUGE = "x" * 1_000_000


def _relative_iris() -> Graph:
    g = Graph()
    for iri in ("relative.owl", "https://example.test/with space", "urn:x", ""):
        g.add((URIRef(iri), RDF.type, OWL.Ontology))
        g.add((URIRef(iri), RDF.type, OWL.Class))
        g.add((URIRef(iri), RDFS.label, Literal(iri)))
    g.add((BNode(), RDFS.subClassOf, URIRef("")))
    return g


ODD_INPUTS: dict[str, Callable[[], Graph]] = {
    "empty graph": Graph,
    "blank-node subjects and objects": lambda: graph(
        "[] a owl:Class ; rdfs:subClassOf [] ; rdfs:label [] .\n"
        "[] a owl:ObjectProperty ; rdfs:domain [] ; rdfs:range [] ; owl:inverseOf [] .\n"
        "[] a skos:Concept ; skos:broader [] ; skos:prefLabel [] .\n"
        "[] owl:allValuesFrom [] ; owl:equivalentClass [] ."
    ),
    "literals where IRIs are expected": lambda: graph(
        'ex:A a owl:Class ; rdfs:subClassOf "lit" ; owl:equivalentClass "lit" ; owl:disjointWith 1 .\n'
        'ex:p a owl:ObjectProperty, owl:DatatypeProperty ; rdfs:domain "d" ; rdfs:range "r" ;\n'
        '    owl:inverseOf "q" ; owl:propertyChainAxiom "not a list" .\n'
        'ex:c a skos:Concept ; skos:broader "b" ; skos:topConceptOf "t" ; skos:inScheme "s" .\n'
        'ex:o a owl:Ontology ; owl:imports "x", 42 .\n'
        'ex:s sh:property "p" ; sh:targetClass "t" .'
    ),
    "unusual label literals": lambda: graph(
        'ex:A a owl:Class ; rdfs:label 1, true, 1.5, "2026-01-01"^^xsd:date, "x"^^ex:custom, "" .'
    ),
    "huge literal": lambda: graph(f'ex:A a owl:Class ; rdfs:label "{HUGE}" ; rdfs:comment "{HUGE}" .'),
    "unicode": lambda: graph(
        'ex:Café a owl:Class ; rdfs:label "Ünïcödé 😀 שלום مرحبا", "é"@fr-CA ; rdfs:comment "\u200b" .\n'
        'ex:日本語 a owl:Class, skos:Concept ; skos:prefLabel " padded "@ja .'
    ),
    "relative and spaced IRIs": _relative_iris,
    "self-referential structure": lambda: graph(
        "ex:A a owl:Class ; rdfs:subClassOf ex:A ; owl:equivalentClass ex:A .\n"
        "ex:p a owl:ObjectProperty ; owl:inverseOf ex:p ; owl:propertyChainAxiom ex:p .\n"
        "ex:c a skos:Concept ; skos:broader ex:c ."
    ),
    "malformed rdf list": lambda: graph("ex:p owl:propertyChainAxiom _:l . _:l rdf:first ex:q, ex:r ; rdf:rest _:l ."),
}

ODD_SHAPES: dict[str, str] = {
    "blank and literal shape structure": (
        'ex:S a sh:NodeShape ; sh:property [] , "lit" ; sh:name [] , 1 ; sh:message "" .'
    ),
    "huge shape literal": f'ex:S a sh:NodeShape, sh:PropertyShape ; sh:name "{HUGE}" ; sh:minCount 1 .',
}
