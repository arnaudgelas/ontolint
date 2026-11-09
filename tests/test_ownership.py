"""Term ownership: which declared terms does the linted file own (derived namespaces, --base, fallback)?"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from ontolint import Linter, main
from ontolint.context import GraphContext
from ontolint.ownership import Ownership, OwnershipMode, base_matches, derive_prefixes, is_builtin
from ontolint.policy import Policy

HEADER = """\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix obo: <http://purl.obolibrary.org/obo/> .
@prefix ex: <https://example.test/onto#> .
"""


def parse(body: str) -> Graph:
    return Graph().parse(data=HEADER + body, format="turtle")


def ctx(body: str, base: str | None = None) -> GraphContext:
    return GraphContext.build(parse(body), base=base)


def names(terms: frozenset[URIRef]) -> set[str]:
    return {str(t).rsplit("/", 1)[-1].rsplit("#", 1)[-1] for t in terms}


class TestDerivedNamespaces:
    def test_ontology_iri_with_hash_owns_its_namespace_and_not_stubs(self) -> None:
        context = ctx(
            """
            <https://example.test/onto> a owl:Ontology .
            ex:Own a owl:Class .
            <https://foreign.test/ns#Other> a owl:Class .
            ex:Stub rdfs:seeAlso <https://foreign.test/ns#Ref> .
            """
        )
        assert names(context.terms) == {"Own"}
        assert names(context.classes) == {"Own"}
        assert context.ownership.mode is OwnershipMode.DERIVED

    def test_stub_in_owned_namespace_is_not_a_term(self) -> None:
        context = ctx("<https://example.test/onto> a owl:Ontology . ex:A a owl:Class . ex:B rdfs:subClassOf ex:A .")
        assert names(context.terms) == {"A"}

    def test_obo_id_prefix_is_matched_case_insensitively(self) -> None:
        context = ctx(
            """
            obo:ro.owl a owl:Ontology .
            obo:RO_0000050 a owl:ObjectProperty .
            <http://purl.obolibrary.org/obo/ro#part> a owl:ObjectProperty .
            obo:BFO_0000050 a owl:ObjectProperty .
            obo:ro_0000001 a owl:ObjectProperty .
            """
        )
        assert names(context.properties) == {"RO_0000050", "ro_0000001", "part"}

    def test_ontology_iri_minus_owl_and_trailing_separator(self) -> None:
        context = ctx(
            """
            <http://x.test/voc.owl/> a owl:Ontology .
            <http://x.test/voc#A> a owl:Class .
            <http://x.test/voc/B> a owl:Class .
            <http://x.test/vocab/C> a owl:Class .
            """
        )
        assert names(context.classes) == {"A", "B"}

    def test_stripped_prefix_requires_a_name_boundary(self) -> None:
        context = ctx(
            "<http://x.test/voc> a owl:Ontology . <http://x.test/voc> a owl:Class . <http://x.test/voco> a owl:Class ."
        )
        assert context.terms == {URIRef("http://x.test/voc")}

    def test_builtin_vocabularies_are_never_owned(self) -> None:
        context = ctx(
            "<https://example.test/onto> a owl:Ontology . ex:A a owl:Class . rdfs:label a owl:AnnotationProperty ."
        )
        assert names(context.terms) == {"A"}

    def test_fallback_when_nothing_declared_is_owned(self) -> None:
        context = ctx(
            "<http://prov.example/ontology> a owl:Ontology . <http://prov.example/ns#A> a owl:Class . "
            "rdfs:comment a owl:AnnotationProperty ."
        )
        assert names(context.classes) == {"A"}
        assert context.ownership.dominant_namespace == "http://prov.example/ns#"  # nothing owned: dominant ns

    def test_fallback_without_ontology_declaration(self) -> None:
        context = ctx("ex:A a owl:Class . <https://other.test/B> a owl:Class .")
        assert names(context.terms) == {"A", "B"}

    def test_one_owned_term_is_enough_to_stay_derived(self) -> None:
        context = ctx(
            "<https://example.test/onto> a owl:Ontology . ex:A a owl:Class . <https://other.test/B> a owl:Class ."
        )
        assert names(context.terms) == {"A"}

    def test_linter_local_and_terms_follow_ownership(self) -> None:
        linter = Linter(
            parse(
                "<https://example.test/onto> a owl:Ontology . ex:A a owl:Class . <https://other.test/B> a owl:Class ."
            )
        )
        assert linter.local(URIRef("https://example.test/onto#A")) is True
        assert linter.local(URIRef("https://other.test/B")) is False
        assert linter.local(URIRef("http://www.w3.org/2002/07/owl#Thing")) is False
        assert linter.terms == {URIRef("https://example.test/onto#A")}

    def test_foreign_terms_get_no_findings(self) -> None:
        graph = parse(
            "<https://example.test/onto> a owl:Ontology . ex:A a owl:Class ; rdfs:label 'A'@en ; "
            "rdfs:comment 'An A thing here.' . "
            "<https://other.test/B> a owl:Class ."
        )
        result = Linter(graph).execute(["LEX001"])
        assert not [f for f in result.findings if f.focus == "https://other.test/B"]
        assert not [f for f in result.findings if f.rule == "LEX001"]

    def test_foreign_term_is_flagged_when_ownership_falls_back(self) -> None:
        graph = parse("<https://other.test/B> a owl:Class .")
        assert [f.focus for f in Linter(graph).execute(["LEX001"]).findings] == ["https://other.test/B"]


class TestOwnershipUnits:
    def test_derive_prefixes(self) -> None:
        exact, folded = derive_prefixes([URIRef("http://purl.obolibrary.org/obo/envo.owl"), URIRef("http://x.test/o#")])
        assert exact == (
            "http://purl.obolibrary.org/obo/envo",
            "http://purl.obolibrary.org/obo/envo.owl",
            "http://x.test/o",
            "http://x.test/o#",
        )
        assert folded == ("http://purl.obolibrary.org/obo/envo_",)

    def test_obo_prefix_uses_first_path_segment_of_obo_iris_only(self) -> None:
        obo = "http://purl.obolibrary.org/obo/"
        assert derive_prefixes([URIRef(obo + "envo")])[1] == (obo + "envo_",)
        assert derive_prefixes([URIRef(obo + "ro/core.owl")])[1] == (obo + "ro_",)
        assert derive_prefixes([URIRef(obo + "iao#x")])[1] == (obo + "iao_",)
        assert derive_prefixes([URIRef(obo + ".owl")])[1] == ()
        assert derive_prefixes([URIRef(obo)])[1] == ()
        # Outside purl.obolibrary.org the generic ODK rule applies: <dir>/<NAME>_ of a file-named IRI.
        assert derive_prefixes([URIRef("http://other.test/obo/envo.owl")])[1] == ("http://other.test/obo/envo_",)

    def test_is_builtin(self) -> None:
        assert is_builtin(URIRef("http://www.w3.org/2002/07/owl#Thing"))
        assert is_builtin(URIRef("http://www.w3.org/2000/01/rdf-schema#label"))
        assert is_builtin(URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"))
        assert is_builtin(URIRef("http://www.w3.org/2001/XMLSchema#string"))
        assert not is_builtin(URIRef("http://www.w3.org/2004/02/skos/core#Concept"))
        assert not is_builtin("http://www.w3.org/2002/07/owl#Thing")

    def test_owns_rejects_non_iris(self) -> None:
        for mode in (Ownership(), Ownership(OwnershipMode.BASE, "x"), Ownership(OwnershipMode.DERIVED, None, ("x",))):
            assert not mode.owns(BNode())
            assert not mode.owns(Literal("x"))
            assert not mode.owns("x")

    def test_all_mode_owns_every_non_builtin_iri(self) -> None:
        assert Ownership().owns(URIRef("http://any.test/x"))
        assert not Ownership().owns(URIRef("http://www.w3.org/2002/07/owl#Thing"))

    def test_derived_mode_matches_prefixes_and_folded_prefixes(self) -> None:
        own = Ownership(OwnershipMode.DERIVED, None, ("http://a.test/o#",), ("http://a.test/o_",))
        assert own.owns(URIRef("http://a.test/o#x"))
        assert own.owns(URIRef("http://a.test/O_1"))
        assert not own.owns(URIRef("http://a.test/p#x"))
        assert not own.owns(URIRef("http://a.test/o#x".replace("o#", "oo#")))


class TestBase:
    @pytest.mark.parametrize(
        ("base", "iri", "expected"),
        [
            ("http://purl.obolibrary.org/obo/RO_", "http://purl.obolibrary.org/obo/RO_0000050", True),
            ("http://purl.obolibrary.org/obo/RO_", "http://purl.obolibrary.org/obo/BFO_0000050", False),
            ("http://x.test/o:", "http://x.test/o:a", True),
            ("http://x.test/o#", "http://x.test/o#a", True),
            ("http://x.test/o#", "http://x.test/o", False),
            ("http://x.test/o/", "http://x.test/o/a", True),
            ("http://x.test/o", "http://x.test/o", True),
            ("http://x.test/o", "http://x.test/o#a", True),
            ("http://x.test/o", "http://x.test/o/a", True),
            ("http://x.test/o", "http://x.test/ontology", False),
            ("http://x.test/o1", "http://x.test/o1x", False),
            ("", "http://anything", True),
            (None, "http://anything", True),
        ],
    )
    def test_base_matches(self, base: str | None, iri: str, expected: bool) -> None:
        assert base_matches(base, URIRef(iri)) is expected

    def test_base_matches_rejects_non_iri(self) -> None:
        assert base_matches("x", "x") is False
        assert base_matches(None, "x") is False

    def test_underscore_base_selects_terms_and_ignores_derivation(self) -> None:
        body = """
            obo:ro.owl a owl:Ontology .
            obo:RO_1 a owl:Class . obo:BFO_1 a owl:Class .
            """
        context = ctx(body, base="http://purl.obolibrary.org/obo/BFO_")
        assert names(context.classes) == {"BFO_1"}
        assert context.ownership.mode is OwnershipMode.BASE
        assert context.ownership.base_selected_nothing is False

    def test_base_selecting_nothing_is_flagged(self) -> None:
        context = ctx("ex:A a owl:Class .", base="http://nowhere.test/")
        assert context.terms == frozenset()
        assert context.ownership.base_selected_nothing is True

    def test_base_selecting_nothing_not_flagged_without_declared_terms_or_with_empty_base(self) -> None:
        assert (
            ctx(
                "<https://example.test/onto> a owl:Ontology .", base="http://nowhere.test/"
            ).ownership.base_selected_nothing
            is False
        )
        assert ctx("ex:A a owl:Class .", base="").ownership.base_selected_nothing is False

    def test_base_only_counts_non_builtin_declared_terms(self) -> None:
        assert (
            ctx("rdfs:label a owl:AnnotationProperty .", base="http://nowhere.test/").ownership.base_selected_nothing
            is False
        )

    def test_explicit_is_local_predicate_still_overrides(self) -> None:
        graph = parse("ex:A a owl:Class . <https://other.test/B> a owl:Class .")
        only_ex = GraphContext.build(
            graph, lambda n: str(n).startswith("https://example.test/"), restrict_to_local=True
        )
        assert names(only_ex.classes) == {"A"}
        everything = GraphContext.build(graph, lambda _n: False)
        assert names(everything.classes) == {"A", "B"}


class TestCliWarning:
    def write(self, tmp_path: Path) -> Path:
        path = tmp_path / "o.ttl"
        path.write_text(HEADER + "ex:A a owl:Class .\n", encoding="utf-8")
        return path

    def test_warns_on_stderr_when_base_selects_nothing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        main([str(self.write(tmp_path)), "--base", "http://nowhere.test/RO_", "--fail-on", "never"])
        err = capsys.readouterr().err
        assert err.startswith("TOOL002: warning: --base 'http://nowhere.test/RO_' selects none of the terms")
        assert "o.ttl" in err

    def test_no_warning_when_base_matches(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        main([str(self.write(tmp_path)), "--base", "https://example.test/onto#", "--fail-on", "never"])
        assert capsys.readouterr().err == ""

    def test_no_warning_without_base(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        main([str(self.write(tmp_path)), "--fail-on", "never"])
        assert capsys.readouterr().err == ""

    def test_json_output_unaffected_by_warning(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        main([str(self.write(tmp_path)), "--base", "http://nowhere.test/", "--format", "json", "--fail-on", "never"])
        json.loads(capsys.readouterr().out)


def test_policy_default_is_unrestricted() -> None:
    assert Policy().base is None


def test_obo_subontology_iri_owns_its_id_space() -> None:
    context = ctx(
        "<http://purl.obolibrary.org/obo/ro/core.owl> a owl:Ontology . obo:RO_1 a owl:Class . obo:BFO_1 a owl:Class ."
    )
    assert names(context.classes) == {"RO_1"}
    assert context.ownership.mode is OwnershipMode.DERIVED


def test_empty_base_owns_every_non_builtin_iri_but_never_a_builtin() -> None:
    assert base_matches("", URIRef("https://example.test/x")) is True
    assert base_matches("", OWL.Thing) is False
    assert base_matches("", RDFS.label) is False
    assert base_matches("", URIRef("http://www.w3.org/2001/XMLSchema#string")) is False
    assert base_matches("", RDF.type) is False


def test_a_base_inside_a_builtin_namespace_still_does_not_own_builtin_terms() -> None:
    assert base_matches(str(OWL), OWL.Thing) is False
    assert base_matches("http://www.w3.org/2002/07/", OWL.Thing) is False
    assert base_matches("https://example.test/", URIRef("https://example.test/OWL")) is True


def test_for_terms_with_an_empty_base_does_not_own_builtins() -> None:
    ownership = Ownership.for_terms("", [], [OWL.Thing])
    assert ownership.mode is OwnershipMode.BASE
    assert ownership.owns(OWL.Thing) is False
    assert ownership.owns(RDFS.label) is False
    assert ownership.owns(URIRef("https://example.test/x")) is True
    assert ownership.base_selected_nothing is False
