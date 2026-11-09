"""Ownership patterns seen in published ontologies: the linted ontology's terms, never what it merges in.

Each fixture copies the shape of a real file (named in the test) with synthetic IRIs.
"""

from __future__ import annotations

import pytest
from rdflib import Graph

from ontolint import Linter

PREFIXES = "@prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
FOREIGN = "https://vocab.test/co/"  # a merged or referenced vocabulary


def _foci(turtle: str, rules: list[str]) -> set[str]:
    graph = Graph().parse(data=PREFIXES + turtle, format="turtle")
    return {finding.focus for finding in Linter(graph).execute(rules).findings}


def _merged_release(ontology_iri: str) -> str:
    """An ODK release: the ontology's ID-prefixed terms plus unlabelled terms of a merged import."""
    terms = "".join(
        f'<https://ex.test/pmd/onto/ONTO_000000{i}> a owl:Class ; rdfs:label "t{i}"@en .\n' for i in range(3)
    )
    merged = "".join(f"<{FOREIGN}CO_000000{i}> a owl:Class .\n" for i in range(5))
    return f"<{ontology_iri}> a owl:Ontology .\n{terms}{merged}"


@pytest.mark.parametrize(
    "ontology_iri",
    [
        "https://ex.test/pmd/onto.ttl",  # automatce.ttl: a file extension other than .owl
        "https://ex.test/pmd/onto/onto-full.ttl",  # automatce-full.ttl: an ODK release suffix
        "https://ex.test/pmd/onto/onto-base.owl",  # automatce-base: same rule with .owl
    ],
)
def test_an_odk_release_owns_its_id_prefix_and_not_what_it_merges(ontology_iri: str) -> None:
    assert not {f for f in _foci(_merged_release(ontology_iri), ["LEX001"]) if f.startswith(FOREIGN)}


def test_a_placeholder_ontology_iri_owns_the_dominant_term_namespace() -> None:
    # MFTO: a Protege "untitled-ontology" IRI owns none of the terms, which hang under an upper ontology.
    turtle = "<http://ex.test/ontologies/2018/8/untitled-ontology-139> a owl:Ontology .\n" + "".join(
        f"<http://ex.test/mfto#C{i}> a owl:Class ; rdfs:subClassOf <http://purl.obolibrary.org/obo/BFO_000003{i}> .\n"
        for i in range(4)
    )
    foci = _foci(turtle, ["OWL001", "LEX001"])
    assert not {f for f in foci if f.startswith("http://purl.obolibrary.org/")}  # no "declare local classes"
    assert {f for f in foci if f.startswith("http://ex.test/mfto#")}  # the ontology's own terms are judged


def test_without_a_dominant_namespace_everything_is_still_judged() -> None:
    turtle = "<https://a.test/A> a owl:Class . <https://b.test/B> a owl:Class ."
    assert _foci(turtle, ["LEX001"]) == {"https://a.test/A", "https://b.test/B"}


def test_restrictions_and_deprecations_of_a_merged_vocabulary_are_not_reported() -> None:
    # automatce-full: BFO and PMDco axioms merged into the release.
    turtle = (
        "<https://ex.test/pmd/onto/onto-full.ttl> a owl:Ontology .\n"
        "<https://ex.test/pmd/onto/ONTO_1> a owl:Class ; rdfs:subClassOf "
        "[ a owl:Restriction ; owl:onProperty <https://ex.test/pmd/onto/ONTO_9> ; owl:allValuesFrom owl:Thing ] .\n"
        f"<{FOREIGN}CO_1> a owl:Class ; rdfs:subClassOf "
        f"[ a owl:Restriction ; owl:onProperty <{FOREIGN}CO_9> ; owl:allValuesFrom owl:Thing ] .\n"
        f"<{FOREIGN}CO_2> owl:deprecated true . <{FOREIGN}CO_3> a <{FOREIGN}CO_2> .\n"
        "<https://ex.test/pmd/onto/ONTO_2> a owl:Class ; rdfs:subClassOf <https://vocab.test/co/CO_2> .\n"
    )
    foci = _foci(turtle, ["OWL011", "GOV001"])
    assert foci == {"https://ex.test/pmd/onto/ONTO_1", "https://ex.test/pmd/onto/ONTO_2"}
