"""Properties of term ownership: which declared terms a linted file owns."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis_strategies import (
    BASE,
    BASES,
    FOREIGN,
    OBO,
    ONTOLOGY_IRIS,
    OWNED,
    budget,
    iris,
    rdf_graphs,
)
from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS, XSD

from ontolint.context import KINDS, GraphContext
from ontolint.ownership import (
    BUILTIN_NAMESPACES,
    Ownership,
    OwnershipMode,
    _dominant_namespace,
    base_matches,
    derive_prefixes,
    is_builtin,
    is_well_known,
    namespace_of_iri,
)

pytestmark = pytest.mark.slow

BUILTINS = (
    RDF.type,
    RDFS.Class,
    RDFS.label,
    OWL.Class,
    OWL.Thing,
    OWL.ObjectProperty,
    XSD.string,
    XSD.integer,
    URIRef(str(RDF) + "nonexistent"),
)
# Bases that do not overlap the built-in namespaces (an empty base or a base inside them is a user choice).
SANE_BASES = [b for b in BASES if b is not None]
declared_lists = st.lists(st.one_of(iris, st.sampled_from(BUILTINS)), max_size=8)
ontology_lists = st.lists(st.sampled_from(ONTOLOGY_IRIS), max_size=3)


def test_builtin_namespaces_are_what_the_docs_say() -> None:
    """INVARIANT: the built-in vocabularies are exactly RDF, RDFS, OWL and XSD."""
    assert set(BUILTIN_NAMESPACES) == {str(RDF), str(RDFS), str(OWL), str(XSD)}
    assert all(is_builtin(term) for term in BUILTINS)
    assert not is_builtin(SKOS.Concept)
    assert not is_builtin("http://www.w3.org/2002/07/owl#Class")  # a plain string is not an IRI node


@budget(1)
@given(rdf_graphs, st.sampled_from(BASES))
def test_owned_terms_are_declared_terms_of_the_right_kind(graph: Graph, base: str | None) -> None:
    """INVARIANT: owned classes/properties/concepts are declared terms and every owned term is declared."""
    context = GraphContext.build(graph, base=base)

    declared = {s for kind in KINDS for s in graph.subjects(RDF.type, kind) if isinstance(s, URIRef)}
    assert context.terms <= declared
    assert context.classes <= context.terms
    assert context.properties <= context.terms
    assert context.concepts <= context.terms
    assert context.terms <= {t for t in declared if context.ownership.owns(t)}
    assert context.ontologies <= {s for s in graph.subjects(RDF.type, OWL.Ontology) if isinstance(s, URIRef)}
    assert all(context.ownership.owns(t) for t in context.terms)


@budget(1)
@given(rdf_graphs)
def test_without_a_base_builtin_terms_are_never_owned(graph: Graph) -> None:
    """INVARIANT: with no base, no rdf/rdfs/owl/xsd IRI is ever an owned term."""
    context = GraphContext.build(graph)

    assert not any(is_builtin(term) for term in context.terms)
    assert not any(context.ownership.owns(term) for term in BUILTINS)


@budget(1)
@given(declared_lists, ontology_lists, st.one_of(st.none(), st.sampled_from(SANE_BASES)))
def test_builtin_iris_are_never_owned_in_any_mode(
    declared: list[URIRef], ontologies: list[URIRef], base: str | None
) -> None:
    """INVARIANT: for every ownership mode and any base outside the built-in namespaces, built-ins are not owned."""
    ownership = Ownership.for_terms(base, ontologies, declared)

    assert not any(ownership.owns(term) for term in BUILTINS)


def test_empty_base_does_not_own_builtin_iris() -> None:
    """The module docstring promises built-in vocabularies are never owned; an empty base must not break that."""
    ownership = Ownership.for_terms("", [], [OWL.Thing])

    assert not ownership.owns(OWL.Thing)
    assert not ownership.owns(RDFS.label)


@budget(1)
@given(declared_lists, ontology_lists, st.sampled_from(BASES[1:]))
def test_with_a_base_only_the_base_decides(declared: list[URIRef], ontologies: list[URIRef], base: str) -> None:
    """INVARIANT: given a base, ownership is base_matches and ignores the ontology IRIs and the declared terms."""
    ownership = Ownership.for_terms(base, ontologies, declared)
    unrelated = Ownership.for_terms(base, [], [])

    assert ownership.mode is OwnershipMode.BASE
    for term in (*declared, *OWNED, *BUILTINS, URIRef(base + "x")):
        assert ownership.owns(term) == base_matches(base, term) == unrelated.owns(term)
    non_builtin = [t for t in declared if not is_builtin(t)]
    nothing = bool(non_builtin) and not any(base_matches(base, t) for t in non_builtin)
    assert ownership.base_selected_nothing == nothing


@budget(1)
@given(st.one_of(st.none(), st.sampled_from(SANE_BASES)), st.one_of(iris, st.text(max_size=5)))
def test_non_iris_are_never_owned(base: str | None, node: object) -> None:
    """INVARIANT: only URIRef nodes can be owned, whatever the base."""
    assert base_matches(base, str(node)) is False
    assert Ownership.for_terms(base, [], []).owns(str(node)) is False


alnum_bases = st.from_regex(r"https://x\.org/[a-z]{1,6}", fullmatch=True)
punct_bases = st.from_regex(r"https://x\.org/[a-z]{1,6}[#/_]", fullmatch=True)
suffixes = st.text(alphabet="abcXYZ09_#/.-", max_size=6)


@budget(1)
@given(alnum_bases, suffixes)
def test_alphanumeric_base_requires_a_namespace_boundary(base: str, suffix: str) -> None:
    """INVARIANT: a base ending in a letter or digit matches itself and base#.. / base/.. only."""
    node = URIRef(base + suffix)

    expected = suffix == "" or suffix.startswith(("#", "/"))
    assert base_matches(base, node) is expected
    assert base_matches(base, URIRef(base + "x")) is False
    assert base_matches(base, URIRef(base[:-1])) is False


@budget(1)
@given(punct_bases, suffixes)
def test_punctuated_base_is_a_plain_prefix(base: str, suffix: str) -> None:
    """INVARIANT: a base ending in #, / or _ is an ordinary prefix test."""
    assert base_matches(base, URIRef(base + suffix)) is True
    assert base_matches(base, URIRef(base[:-1])) is False


@budget(1)
@given(st.one_of(st.none(), st.just(""), st.sampled_from(SANE_BASES)), st.sampled_from(OWNED + (OWL.Thing,)))
def test_matching_implies_prefix_and_empty_base_matches_every_iri(base: str | None, node: URIRef) -> None:
    """INVARIANT: a match implies the IRI starts with the base; an empty or missing base matches every non-built-in IRI."""  # noqa: E501
    if not base:
        assert base_matches(base, node) == (node != OWL.Thing)
    elif base_matches(base, node):
        assert str(node).startswith(base)


@budget(1)
@given(declared_lists, ontology_lists)
def test_fallback_never_owns_fewer_terms_than_the_derived_heuristic(
    declared: list[URIRef], ontologies: list[URIRef]
) -> None:
    """INVARIANT: without a base, ownership covers the derived prefixes; if they own nothing, the dominant namespace
    of the declared terms, and only without one every non-builtin term. Borrowed well-known terms take no part,
    unless the file declares nothing else."""
    exact, folded = derive_prefixes(ontologies)
    heuristic = Ownership(OwnershipMode.DERIVED, None, exact, folded)

    ownership = Ownership.for_terms(None, ontologies, declared)

    non_builtin = [t for t in declared if not is_builtin(t)]
    overall = _dominant_namespace(list(dict.fromkeys(non_builtin)))
    borrowed = {
        t for t in non_builtin if is_well_known(t) and not heuristic.owns(t) and namespace_of_iri(str(t)) != overall
    }
    deciding = [t for t in dict.fromkeys(non_builtin) if t not in borrowed] or list(dict.fromkeys(non_builtin))
    derived_owned = {t for t in non_builtin if heuristic.owns(t)}
    owned = {t for t in non_builtin if ownership.owns(t)}
    assert owned >= derived_owned
    if derived_owned:
        assert ownership.mode is OwnershipMode.DERIVED
        assert owned == derived_owned
    elif (dominant := _dominant_namespace(deciding)) is not None:  # distinct terms
        assert ownership.dominant_namespace == dominant
        assert {t for t in deciding if str(t).startswith(dominant)} <= owned
    else:
        assert ownership.mode is OwnershipMode.ALL
        assert owned == (set(deciding) if len(deciding) < len(set(non_builtin)) else set(non_builtin))
    assert not ownership.base_selected_nothing


@budget(1)
@given(ontology_lists, st.randoms(use_true_random=False))
def test_derived_prefixes_ignore_ontology_order_and_cover_each_ontology(ontologies: list[URIRef], rnd: object) -> None:
    """INVARIANT: derived prefixes are order independent and an ontology IRI owns itself."""
    shuffled = list(ontologies)
    rnd.shuffle(shuffled)  # type: ignore[attr-defined]

    assert derive_prefixes(ontologies) == derive_prefixes(shuffled)
    exact, folded = derive_prefixes(ontologies)
    ownership = Ownership(OwnershipMode.DERIVED, None, exact, folded)
    assert all(ownership.owns(o) for o in ontologies)
    assert list(exact) == sorted(exact)


@budget(1)
@given(st.from_regex(r"[a-z]{2,5}", fullmatch=True), st.from_regex(r"[0-9]{1,7}", fullmatch=True), st.booleans())
def test_obo_ontology_owns_its_id_space_case_insensitively(name: str, number: str, upper: bool) -> None:
    """INVARIANT: ``obo/<name>.owl`` owns ``obo/<NAME>_<n>`` in any case but not a longer ontology name."""
    ontology = URIRef(f"{OBO}{name}.owl")
    owned = URIRef(f"{OBO}{name.upper() if upper else name}_{number}")
    other = URIRef(f"{OBO}{name}x_{number}")
    exact, folded = derive_prefixes([ontology])
    ownership = Ownership(OwnershipMode.DERIVED, None, exact, folded)

    assert ownership.owns(owned)
    assert ownership.owns(ontology)
    assert not ownership.owns(other)
    assert not ownership.owns(URIRef(f"{FOREIGN}{name}_{number}"))
    assert Ownership.for_terms(None, [ontology], [owned, other]).owns(owned)
    assert not Ownership.for_terms(None, [ontology], [owned, other]).owns(other)


@budget(1)
@given(
    st.sampled_from(("https://example.test/onto", BASE, "https://example.test/onto/")), st.sampled_from(("", "#", "/"))
)
def test_ontology_iri_namespace_is_owned_with_or_without_separator(ontology: str, separator: str) -> None:
    """INVARIANT: terms in ``<ontology>#`` or ``<ontology>/`` are owned when the ontology IRI is declared."""
    stripped = ontology.rstrip("#/")
    term = URIRef(f"{stripped}{separator or '#'}Term")
    ownership = Ownership.for_terms(None, [URIRef(ontology)], [term, URIRef(FOREIGN + "X")])

    assert ownership.mode is OwnershipMode.DERIVED
    assert ownership.owns(term)
    assert not ownership.owns(URIRef(FOREIGN + "X"))
    assert not ownership.owns(URIRef(stripped + "ology#Term"))
