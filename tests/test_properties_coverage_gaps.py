"""Properties of the coverage-gap fixes, checked against literal readings of the W3C definitions.

* OWL019: the non-simple properties are those OWL 2 Structural Specification section 11.1 defines, computed
  here over property expressions and their inverses exactly as the specification states the relation ``→``;
  the rule's walk over IRIs must agree on every random property hierarchy, for the characteristics and for
  the cardinality restrictions of SS 11.2.
* SKOS009: the pairs reported are those S27 makes conflicting once S41 puts the mapping properties under
  ``skos:broader``, ``skos:narrower`` and ``skos:related``, less ALIGN004's direct ones, and a pair the
  plain hierarchy already makes conflicting keeps the message it had before.
* SHQ011: a pattern drawn from the grammar of XSD Part 2 Appendix F with the XPath additions (anchors,
  reluctant quantifiers, ``(?:``, back-references, ``\\$``) never gets the "not an XPath regular
  expression" finding, nor any other SHQ011 finding.
"""

from __future__ import annotations

import random
import re
from collections.abc import Iterable

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis_strategies import budget
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS, SKOS
from rdflib.term import Node

from ontolint import Linter
from ontolint.rules.shacl_authoring import pattern_problem, xpath_regex_problem

pytestmark = pytest.mark.slow

EX = "https://example.test/onto#"
PROPERTIES = tuple(URIRef(f"{EX}p{i}") for i in range(5))
CHARACTERISTICS = (
    OWL.FunctionalProperty,
    OWL.InverseFunctionalProperty,
    OWL.IrreflexiveProperty,
    OWL.AsymmetricProperty,
)

Expression = tuple[URIRef, bool]  # a property, and whether the expression is its inverse
Axiom = tuple[str, Expression, Expression]


def _expression() -> st.SearchStrategy[Expression]:
    return st.tuples(st.sampled_from(PROPERTIES), st.booleans())


AXIOMS: st.SearchStrategy[Axiom] = st.tuples(
    st.sampled_from(("sub", "equivalent", "inverse", "symmetric", "transitive", "chain2", "chain1")),
    _expression(),
    _expression(),
)
DECLARATIONS = st.lists(st.tuples(st.sampled_from(PROPERTIES), st.sampled_from(CHARACTERISTICS)), max_size=6)


def _term(graph: Graph, expression: Expression) -> Node:
    """The RDF term of an expression: the IRI, or a fresh blank ``[ owl:inverseOf p ]``."""
    iri, inverted = expression
    if not inverted:
        return iri
    node = BNode()
    graph.add((node, OWL.inverseOf, iri))
    return node


def build(axioms: Iterable[Axiom], declarations: Iterable[tuple[URIRef, URIRef]]) -> Graph:
    graph = Graph()
    for kind, first, second in axioms:
        if kind == "inverse":  # InverseObjectProperties is mapped from IRIs only
            graph.add((first[0], OWL.inverseOf, second[0]))
        elif kind in ("sub", "equivalent"):
            predicate = RDFS.subPropertyOf if kind == "sub" else OWL.equivalentProperty
            graph.add((_term(graph, first), predicate, _term(graph, second)))
        elif kind in ("symmetric", "transitive"):
            kind_type = OWL.SymmetricProperty if kind == "symmetric" else OWL.TransitiveProperty
            graph.add((_term(graph, first), RDF.type, kind_type))
        else:
            head = BNode()
            Collection(graph, head, [first[0], second[0]] if kind == "chain2" else [first[0]])
            graph.add((_term(graph, first), OWL.propertyChainAxiom, head))
    for prop, characteristic in declarations:
        graph.add((prop, RDF.type, characteristic))
    return graph


def _inv(expression: Expression) -> Expression:
    return expression[0], not expression[1]


def specified_non_simple(axioms: Iterable[Axiom]) -> set[URIRef]:
    """Properties OPE with a composite OPE' such that OPE' →* OPE, the relation built as SS 11.1 states it."""
    arrows: set[tuple[Expression, Expression]] = set()
    composite: set[Expression] = set()
    for kind, first, second in axioms:
        if kind == "sub":
            arrows.add((first, second))
        elif kind == "equivalent":
            arrows |= {(first, second), (second, first)}
        elif kind == "inverse":
            a, b = (first[0], False), (second[0], False)
            arrows |= {(a, _inv(b)), (_inv(b), a)}
        elif kind == "symmetric":
            arrows.add((first, _inv(first)))
        elif kind in ("transitive", "chain2"):
            composite |= {first, _inv(first)}  # TransitiveObjectProperty(OPE) or of INV(OPE); chains of n > 1
    arrows |= {(_inv(a), _inv(b)) for a, b in arrows}  # with A → B also INV(A) → INV(B)
    reached = set(composite)
    stack = list(composite)
    while stack:
        here = stack.pop()
        for a, b in arrows:
            if a == here and b not in reached:
                reached.add(b)
                stack.append(b)
    return {iri for iri, inverted in reached if not inverted}


@budget(0.5)
@given(st.lists(AXIOMS, max_size=8), DECLARATIONS)
def test_owl019_reports_the_characteristics_of_exactly_the_properties_ss_11_1_makes_non_simple(
    axioms: list[Axiom], declarations: list[tuple[URIRef, URIRef]]
) -> None:
    declarations = [*declarations, *((p, OWL.FunctionalProperty) for p in PROPERTIES)]  # every property judged
    findings = Linter(build(axioms, declarations)).execute(["OWL019"]).findings
    reported = {(URIRef(f.focus), URIRef(f.subject[0])) for f in findings}
    non_simple = specified_non_simple(axioms)
    assert reported == {(p, c) for p, c in declarations if p in non_simple}


@budget(0.3)
@given(st.lists(AXIOMS, max_size=8), DECLARATIONS, st.integers(0, 2**32))
def test_owl019_does_not_depend_on_the_order_of_the_triples(
    axioms: list[Axiom], declarations: list[tuple[URIRef, URIRef]], seed: int
) -> None:
    graph = build(axioms, declarations)
    triples = list(graph)
    random.Random(seed).shuffle(triples)  # noqa: S311 -- a permutation, not a secret
    shuffled = Graph()
    for triple in triples:
        shuffled.add(triple)

    def messages(g: Graph) -> set[tuple[str, str]]:
        return {(f.focus, f.message) for f in Linter(g).execute(["OWL019"]).findings}

    assert messages(shuffled) == messages(graph)


@budget(0.3)
@given(st.lists(AXIOMS, max_size=8), st.lists(_expression(), min_size=1, max_size=4))
def test_owl019_reports_the_restrictions_on_exactly_the_properties_ss_11_1_makes_non_simple(
    axioms: list[Axiom], restricted: list[Expression]
) -> None:
    graph = build(axioms, ())
    for expression in restricted:
        restriction = BNode()
        graph.add((restriction, RDF.type, OWL.Restriction))
        graph.add((restriction, OWL.onProperty, _term(graph, expression)))
        graph.add((restriction, OWL.maxCardinality, Literal(1)))
    messages = [f.message for f in Linter(graph).execute(["OWL019"]).findings]
    on_restrictions = {
        m.group(1).removeprefix("ObjectInverseOf(").removesuffix(")")
        for message in messages
        if (m := re.fullmatch(r"Restriction on non-simple property (\S+) \(.*\) uses owl:maxCardinality\.", message))
    }
    non_simple = {str(iri) for iri in specified_non_simple(axioms)}
    assert on_restrictions == {str(iri) for iri, _inverted in restricted} & non_simple


def test_the_oracle_reads_the_specification_as_intended() -> None:
    p0, p1, p2 = PROPERTIES[:3]
    # p0 ⊑ INV(p1): INV(p0) → p1, and INV(p0) is composite with p0.
    assert specified_non_simple([("transitive", (p0, False), (p0, False)), ("sub", (p0, False), (p1, True))]) == {
        p0,
        p1,
    }
    # Non-simplicity flows upwards only.
    assert specified_non_simple([("transitive", (p1, False), (p1, False)), ("sub", (p0, False), (p1, False))]) == {p1}
    assert specified_non_simple([("chain1", (p2, False), (p2, False))]) == set()


# --- SHQ011 ---------------------------------------------------------------------------------------------

PLAIN = "abcXYZ019 _/:@#%&=~,;<>'\"!-"  # Char: anything but . \\ ? * + { } ( ) | [ ] ^ $
IN_CLASS = "abcXYZ019 _/:@#%&=~,;<>'\"!.?*+{}()|$"  # XmlChar: anything but \\ - [ ] (and ^ first)
ESCAPES = [f"\\{c}" for c in "nrt\\|.?*+(){}-[]^$sSiIcCdDwW"] + [r"\p{L}", r"\p{IsBasicLatin}", r"\P{Nd}"]
QUANTIFIERS = st.sampled_from(["*", "+", "?", "{2}", "{0,}", "{1,3}", "{3,3}"])


def _class() -> st.SearchStrategy[str]:
    member = st.one_of(st.sampled_from(IN_CLASS), st.sampled_from(ESCAPES), st.just("a-z"), st.just("0-9"))
    group = st.builds(
        lambda negated, members: ("^" if negated else "") + "".join(members),
        st.booleans(),
        st.lists(member, min_size=1, max_size=3),
    )
    simple = group.map(lambda g: f"[{g}]")
    return st.recursive(simple, lambda inner: st.builds(lambda g, sub: f"[{g}-{sub}]", group, inner), max_leaves=3)


def _regex(atom: st.SearchStrategy[str]) -> st.SearchStrategy[str]:
    quantified = st.builds(
        lambda a, q, lazy: a + (q + ("?" if lazy else "") if q else ""),
        atom,
        st.one_of(st.none(), QUANTIFIERS),
        st.booleans(),
    )
    branch = st.lists(quantified, max_size=4).map("".join)
    return st.lists(branch, min_size=1, max_size=3).map("|".join)


ATOMS = st.one_of(st.sampled_from(PLAIN), st.sampled_from(ESCAPES), st.sampled_from(".^$"), _class())
XPATH_PATTERNS = st.recursive(
    _regex(ATOMS),
    lambda inner: _regex(st.one_of(ATOMS, inner.map(lambda r: f"({r})"), inner.map(lambda r: f"(?:{r})"))),
    max_leaves=12,
)


@budget(1)
@given(XPATH_PATTERNS)
def test_shq011_never_rejects_a_pattern_of_the_xpath_grammar(pattern: str) -> None:
    assert xpath_regex_problem(pattern) is None
    assert xpath_regex_problem(f"({pattern})\\1") is None  # a back-reference to a group


@budget(1)
@given(XPATH_PATTERNS)
def test_shq011_reports_no_pattern_of_the_xpath_grammar(pattern: str) -> None:
    # The whole judgement, Python's compilation included: class subtraction ([^a-[b]], [\\d-[5]]) and a
    # quantified anchor (^*) are XPath that Python's re rejects as written.
    assert pattern_problem(pattern, "") is None
    assert pattern_problem(f"({pattern})\\1", "") is None
    # F&O 3.1 5.6.1.4: \\10 is one back-reference only with ten groups before it, otherwise \\1 then 0.
    assert pattern_problem(f"({pattern})\\10", "") is None


# --- SKOS009 --------------------------------------------------------------------------------------------

CONCEPTS = tuple(URIRef(f"{EX}c{i}") for i in range(5))
UPWARD = (SKOS.broader, SKOS.broaderTransitive)
DOWNWARD = (SKOS.narrower, SKOS.narrowerTransitive)
SKOS_EDGES = st.lists(
    st.tuples(
        st.sampled_from(CONCEPTS),
        st.sampled_from((*UPWARD, *DOWNWARD, SKOS.broadMatch, SKOS.narrowMatch, SKOS.related, SKOS.relatedMatch)),
        st.sampled_from(CONCEPTS),
    ),
    max_size=10,
)


def _linked(edges: list[tuple[URIRef, URIRef, URIRef]], a: URIRef, b: URIRef, *, mapping: bool) -> bool:
    """Whether one of ``a`` and ``b`` reaches the other through one or more broader steps (S22, S41)."""
    up = {*UPWARD, SKOS.broadMatch} if mapping else set(UPWARD)
    down = {*DOWNWARD, SKOS.narrowMatch} if mapping else set(DOWNWARD)
    steps = {(s, o) for s, p, o in edges if p in up and s != o} | {(o, s) for s, p, o in edges if p in down and s != o}

    def reaches(start: URIRef, goal: URIRef) -> bool:
        seen, stack = set(), [start]
        while stack:
            here = stack.pop()
            for child, parent in steps:
                if child == here and parent not in seen:
                    seen.add(parent)
                    stack.append(parent)
        return goal in seen

    return reaches(a, b) or reaches(b, a)


@budget(0.5)
@given(SKOS_EDGES)
def test_skos009_reports_the_pairs_s27_makes_conflicting(edges: list[tuple[URIRef, URIRef, URIRef]]) -> None:
    graph = Graph()
    for triple in edges:
        graph.add(triple)
    found = {
        (f.focus, f.subject[0], "through" not in f.message and f.message.startswith("skos:related "))
        for f in Linter(graph).execute(["SKOS009"]).findings
    }

    def linked_by(predicates: tuple[URIRef, ...], a: URIRef, b: URIRef) -> bool:
        return any(p in predicates and {s, o} == {a, b} for s, p, o in edges)

    expected = set()
    for a in CONCEPTS:
        for b in CONCEPTS:
            if not str(a) < str(b):
                continue
            related = linked_by((SKOS.related,), a, b)
            if not (related or linked_by((SKOS.relatedMatch,), a, b)):
                continue
            if _linked(edges, a, b, mapping=False):  # skos:related keeps the message it had before
                expected.add((str(a), str(b), related))
            elif _linked(edges, a, b, mapping=True) and (
                related or not linked_by((SKOS.broadMatch, SKOS.narrowMatch), a, b)
            ):
                expected.add((str(a), str(b), False))
    assert found == expected
