"""Targeted tests that pin exact behaviour of the OBO rules (messages, boundaries, both operands)."""

from __future__ import annotations

from typing import Any

from rdflib import Graph
from rule_harness import graph

from ontolint import Linter
from ontolint.models import ExecutionStatus, Finding
from ontolint.rules.obo import RO_RELATIONS

HEAD = """\
@prefix obo: <http://purl.obolibrary.org/obo/> .
@prefix oio: <http://www.geneontology.org/formats/oboInOwl#> .
"""
OBO = "http://purl.obolibrary.org/obo/"
EX = "https://example.test/onto#"
DEFN = 'obo:IAO_0000115 "A thing."'
PAIR, TRIPLE, RO_COUNT = 2, 3, 18


def _run(rule: str, data: Graph, **options: Any) -> list[Finding]:
    result = Linter(data, None, **options).execute([rule])
    assert {x.status for x in result.executions} == {ExecutionStatus.EXECUTED}, result.executions
    return list(result.findings)


def _messages(rule: str, turtle: str, **options: Any) -> list[str]:
    return [f.message for f in _run(rule, graph(HEAD + turtle), **options)]


def _focus(rule: str, turtle: str, **options: Any) -> list[str]:
    return [f.focus for f in _run(rule, graph(HEAD + turtle), **options)]


# --- OBO001 ----------------------------------------------------------------------------------


def test_obo001_message_focus_and_pattern_boundaries() -> None:
    found = _run("OBO001", graph(HEAD + "obo:xyz a owl:Class . obo:XYZ_0000001 a owl:Class ."))
    assert [(f.focus, f.message, f.confidence, f.severity) for f in found] == [
        (
            OBO + "xyz",
            "OBO identifier 'xyz' does not follow the PREFIX_0000000 pattern.",
            "certain",
            "warning",
        )
    ]
    for ok in ("X_1", "Xy1_00", "A_b_1", "NCBITaxon_Union_0000002", "RO_HOM0000001", "X_ab1"):
        assert _messages("OBO001", f"obo:{ok} a owl:Class .") == []
    for bad in ("1_2", "X__1", "X_1_", "_1", "X_1a", "X-1", "X_b", "x"):
        assert len(_messages("OBO001", f"<{OBO}{bad}> a owl:Class .")) == 1, bad


def test_obo001_respects_the_base_namespace_and_obo_prefix() -> None:
    turtle = f"<{OBO}bad> a owl:Class . <{EX}bad> a owl:Class ."
    assert _focus("OBO001", turtle) == [OBO + "bad"]
    assert _focus("OBO001", turtle, base=OBO) == [OBO + "bad"]
    assert _focus("OBO001", turtle, base=EX) == []
    assert _messages("OBO001", "<http://purl.obolibrary.org/ob/bad> a owl:Class .") == []


def test_obo001_scope_is_active_classes_and_properties_only() -> None:
    odd = f"<{OBO}envo#envoAstro>"
    assert _focus("OBO001", f"{odd} a owl:AnnotationProperty .") == []
    assert _focus("OBO001", f"{odd} a owl:NamedIndividual .") == []
    assert _focus("OBO001", f"{odd} a owl:ObjectProperty ; owl:deprecated true .") == []
    assert _focus("OBO001", f'{odd} a owl:Class ; owl:deprecated "false" .') == [OBO + "envo#envoAstro"]
    assert _focus("OBO001", f"{odd} a owl:DatatypeProperty .") == [OBO + "envo#envoAstro"]
    assert _focus("OBO001", f"{odd} a owl:ObjectProperty .") == [OBO + "envo#envoAstro"]
    assert _focus("OBO001", f"<{OBO}FOO_abc> a owl:Class .") == [OBO + "FOO_abc"]


# --- OBO002 ----------------------------------------------------------------------------------


def test_obo002_reports_each_missing_item_separately() -> None:
    assert _messages("OBO002", "ex:o a owl:Ontology .") == [
        "Ontology header has no description (dcterms:description).",
        "Ontology header has no license (dcterms:license).",
        "Ontology header has no title (dcterms:title).",
    ]
    only_license = _messages("OBO002", 'ex:o a owl:Ontology ; dcterms:title "t" ; dcterms:description "d" .')
    assert only_license == ["Ontology header has no license (dcterms:license)."]


def test_obo002_accepts_alternative_predicates_and_rejects_blank_literals() -> None:
    cc = "<http://creativecommons.org/ns#license>"
    full = f'ex:o a owl:Ontology ; <http://purl.org/dc/elements/1.1/title> "t" ; dcterms:description "d" ; {cc} ex:L .'
    assert _messages("OBO002", full) == []
    dc_description = 'ex:o a owl:Ontology ; dcterms:title "t" ; <http://purl.org/dc/elements/1.1/description> "d" ;'
    assert _messages("OBO002", dc_description + " dcterms:license ex:L .") == []
    blank = 'ex:o a owl:Ontology ; dcterms:title "" ; dcterms:description "\\t" ; dcterms:license "  " .'
    assert len(_messages("OBO002", blank)) == TRIPLE
    assert (
        _messages(
            "OBO002", 'ex:o a owl:Ontology ; dcterms:title "t" ; dcterms:description "d" ; dcterms:license "MIT" .'
        )
        == []
    )


def test_obo002_header_with_dc_title_and_description_and_dcterms_license_is_complete() -> None:
    dc = "<http://purl.org/dc/elements/1.1/"
    turtle = f'ex:o a owl:Ontology ; {dc}title> "t" ; {dc}description> "d" ; dcterms:license ex:L .'
    assert _messages("OBO002", turtle) == []


def test_obo002_checks_every_ontology() -> None:
    assert _focus("OBO002", "ex:a a owl:Ontology . ex:b a owl:Ontology .") == [EX + "a"] * TRIPLE + [EX + "b"] * TRIPLE


# --- OBO003 and OBO004 -----------------------------------------------------------------------


def test_obo003_message_and_definition_forms() -> None:
    found = _run("OBO003", graph(HEAD + "ex:A a owl:Class ."))
    assert [(f.focus, f.message) for f in found] == [(EX + "A", "Term has no textual definition (obo:IAO_0000115).")]
    assert _messages("OBO003", 'ex:A a owl:Class ; obo:IAO_0000115 "x"@en .') == []
    assert _messages("OBO003", "ex:A a owl:Class ; obo:IAO_0000115 ex:B .") != []  # an IRI is not a text
    assert _messages("OBO003", 'ex:A a owl:Class, owl:NamedIndividual ; owl:deprecated "TRUE" .') == []
    assert _messages("OBO003", 'ex:A a owl:Class ; owl:deprecated "0"^^xsd:boolean .') != []
    assert _messages("OBO003", 'ex:A a owl:Class ; owl:deprecated "1"^^xsd:boolean .') == []


def test_obo003_applies_to_properties_not_annotation_properties_and_honours_base() -> None:
    turtle = "ex:p a owl:ObjectProperty . ex:d a owl:DatatypeProperty . ex:a a owl:AnnotationProperty ."
    assert _focus("OBO003", turtle) == [EX + "d", EX + "p"]
    foreign = f"ex:p a owl:ObjectProperty . <{OBO}X_2> a owl:ObjectProperty ."
    assert _focus("OBO003", foreign, base=EX) == [EX + "p"]
    assert _focus("OBO003", f"<{OBO}X_1> a owl:Class . ex:A a owl:Class .", base=EX) == [EX + "A"]


def test_obo003_elucidation_counts_as_definition() -> None:
    assert _messages("OBO003", 'ex:A a owl:Class ; obo:IAO_0000600 "e" .') == []
    assert _messages("OBO003", 'ex:A a owl:Class ; obo:IAO_0000600 " " .') != []
    assert _messages("OBO003", 'ex:A a owl:Class ; rdfs:comment "c" .') != []
    assert _focus("OBO003", "ex:p a owl:ObjectProperty .") == [EX + "p"]


def test_obo004_skips_obsolete_terms() -> None:
    assert _messages("OBO004", "ex:A a owl:Class ; owl:deprecated true .") == []
    twice = 'ex:{n} a owl:Class ; owl:deprecated true ; rdfs:label "obsolete x" . '
    assert _messages("OBO004", twice.format(n="A") + twice.format(n="B")) == []
    active = 'ex:C a owl:Class ; rdfs:label "obsolete x" . '
    assert _focus("OBO004", twice.format(n="A") + active) == []
    assert _focus("OBO004", 'ex:A a owl:Class ; rdfs:label "x" . ex:B a owl:Class ; rdfs:label "x" .') == [
        EX + "A",
        EX + "B",
    ]
    assert _focus("OBO004", 'ex:A a owl:Class ; owl:deprecated "false" .') == [EX + "A"]


def test_obo004_messages_for_missing_and_shared_labels() -> None:
    assert _messages("OBO004", "ex:A a owl:Class .") == ["Term has no rdfs:label."]
    shared = _run("OBO004", graph(HEAD + 'ex:A a owl:Class ; rdfs:label "x" . ex:B a owl:Class ; rdfs:label "x" .'))
    assert [(f.focus, f.message) for f in shared] == [
        (EX + "A", f"Label 'x' is also used by {EX}B."),
        (EX + "B", f"Label 'x' is also used by {EX}A."),
    ]


def test_obo004_lists_all_other_users_sorted_and_compares_exactly() -> None:
    turtle = (
        'ex:C a owl:Class ; rdfs:label "x" . ex:B a owl:Class ; rdfs:label "x" . ex:A a owl:Class ; rdfs:label "x" .'
    )
    assert _messages("OBO004", turtle)[0] == f"Label 'x' is also used by {EX}B, {EX}C."
    assert _messages("OBO004", 'ex:A a owl:Class ; rdfs:label "x" . ex:B a owl:Class ; rdfs:label "X" .') == []
    lang = 'ex:A a owl:Class ; rdfs:label "x"@EN . ex:B a owl:Class ; rdfs:label "x"@en .'
    assert len(_messages("OBO004", lang)) == PAIR  # language tags compare case-insensitively
    assert _messages("OBO004", 'ex:A a owl:Class ; rdfs:label "x" . ex:B a owl:Class ; rdfs:label "x"@en .') == []


def test_obo004_truncates_long_labels() -> None:
    at_limit, over = "y" * 60, "y" * 61
    for label, shown in ((at_limit, at_limit), (over, "y" * 60 + "...")):
        turtle = f'ex:A a owl:Class ; rdfs:label "{label}" . ex:B a owl:Class ; rdfs:label "{label}" .'
        assert _messages("OBO004", turtle)[0] == f"Label '{shown}' is also used by {EX}B."


# --- OBO005 ----------------------------------------------------------------------------------


def test_obo005_message_and_relation_table() -> None:
    found = _run("OBO005", graph(HEAD + 'ex:p a owl:ObjectProperty ; rdfs:label "Part  of" .'))
    assert [(f.focus, f.message, f.severity) for f in found] == [
        (
            EX + "p",
            f"Object property labelled 'Part  of' duplicates the existing relation {OBO}BFO_0000050.",
            "info",
        )
    ]
    assert len(RO_RELATIONS) == RO_COUNT
    for label, ro in RO_RELATIONS.items():
        turtle = f'ex:p a owl:ObjectProperty ; rdfs:label "{label}" .'
        assert _messages("OBO005", turtle) == [
            f"Object property labelled '{label}' duplicates the existing relation {OBO}{ro}."
        ]


def test_obo005_dropped_relations_and_current_equivalences() -> None:
    assert "inheres in" not in RO_RELATIONS
    assert "bearer of" not in RO_RELATIONS
    assert _messages("OBO005", 'ex:p a owl:ObjectProperty ; rdfs:label "inheres in" .') == []
    equivalent = 'ex:p a owl:ObjectProperty ; rdfs:label "regulates" ; owl:equivalentProperty obo:RO_0002211 .'
    assert _messages("OBO005", equivalent) == []


def test_obo005_link_directions_and_scope() -> None:
    base = 'ex:p a owl:ObjectProperty ; rdfs:label "has part" .'
    for link in (
        "ex:p rdfs:subPropertyOf obo:BFO_0000051 .",
        "ex:p owl:equivalentProperty obo:BFO_0000051 .",
        "obo:BFO_0000051 owl:equivalentProperty ex:p .",
        "obo:BFO_0000051 rdfs:subPropertyOf ex:p .",
    ):
        assert _messages("OBO005", base + link) == [], link
    assert _messages("OBO005", base + "ex:p owl:inverseOf obo:BFO_0000051 .") != []
    assert _focus("OBO005", base, base=OBO) == []  # ex:p is outside the base
    assert _messages("OBO005", 'ex:p a owl:ObjectProperty ; rdfs:label "part of" ; owl:deprecated true .') == []


# --- OBO006 ----------------------------------------------------------------------------------


def _axiom(annotation: str, target: str = "A thing.") -> str:
    return (
        "[] a owl:Axiom ; owl:annotatedSource ex:A ; owl:annotatedProperty obo:IAO_0000115 ;"
        f' owl:annotatedTarget "{target}" ; {annotation} .'
    )


def test_obo006_message_and_provenance_forms() -> None:
    term = f"ex:A a owl:Class ; {DEFN} . "
    found = _run("OBO006", graph(HEAD + term))
    assert [(f.focus, f.message, f.severity) for f in found] == [
        (
            EX + "A",
            "Definition has no source (oboInOwl:hasDbXref, obo:IAO_0000119, dcterms:source or dc:source).",
            "info",
        )
    ]
    dc_source = '<http://purl.org/dc/elements/1.1/source> "x"'
    for annotation in ('oio:hasDbXref "x"', 'obo:IAO_0000119 "x"', 'dcterms:source "x"', dc_source):
        assert _messages("OBO006", term + _axiom(annotation)) == [], annotation
    for predicate in ("obo:IAO_0000119", "dcterms:source", "<http://purl.org/dc/elements/1.1/source>"):
        assert _messages("OBO006", term + f'ex:A {predicate} "x" .') == [], predicate
    assert _messages("OBO006", term + 'ex:A oio:hasDbXref "x" .') != []  # only axiom-level xrefs count
    assert _messages("OBO006", term + _axiom('obo:IAO_0010000 "x"')) != []
    assert _messages("OBO006", term + _axiom('rdfs:comment "x"')) != []
    assert _messages("OBO006", term + "ex:A obo:IAO_0000119 ex:Source .") == []
    assert _messages("OBO006", term + _axiom('oio:hasDbXref "x"', target="other")) != []
    assert (
        _messages("OBO006", 'ex:A a owl:Class ; obo:IAO_0000115 "A thing.", "B" . ' + _axiom('oio:hasDbXref "x"')) != []
    )
    # A blank source is still a source: only the presence of the annotation matters.
    assert _messages("OBO006", term + _axiom('oio:hasDbXref ""')) == []
    # An axiom whose annotated property is not the definition does not count.
    other = _axiom('oio:hasDbXref "x"').replace("obo:IAO_0000115 ;", "rdfs:comment ;")
    assert _messages("OBO006", term + other) != []


def test_obo006_ignores_blank_definitions_and_properties_are_in_scope() -> None:
    assert _messages("OBO006", 'ex:A a owl:Class ; obo:IAO_0000115 " " .') == []
    assert _focus("OBO006", f"ex:p a owl:ObjectProperty ; {DEFN} .") == [EX + "p"]
    assert _focus("OBO006", f"ex:A a owl:Class ; {DEFN} .", base=OBO) == []


# --- OBO007 ----------------------------------------------------------------------------------


def test_obo007_message_severity_and_all_remedies() -> None:
    found = _run("OBO007", graph(HEAD + "ex:A a owl:Class ; owl:deprecated true ."))
    assert [(f.focus, f.message, f.severity) for f in found] == [
        (EX + "A", "Obsolete term has no obsolescence reason, replacement or consider annotation.", "info")
    ]
    for remedy in (
        "obo:IAO_0000231 ex:R",
        "obo:IAO_0000233 ex:T",
        "obo:IAO_0100001 ex:B",
        'oio:consider "x"',
        'obo:IAO_0000231 "x"',
    ):
        assert _messages("OBO007", f"ex:A a owl:Class ; owl:deprecated true ; {remedy} .") == [], remedy
    assert _messages("OBO007", 'ex:A a owl:Class ; owl:deprecated true ; obo:IAO_0000231 "" .') != []
    assert _messages("OBO007", 'ex:A a owl:Class ; owl:deprecated true ; obo:IAO_0000233 "" .') != []
    assert _focus("OBO007", "ex:A a owl:Class ; owl:deprecated true .", base=OBO) == []
    assert _messages("OBO007", "[] a owl:Class ; owl:deprecated true .") == []
    assert _messages("OBO007", "ex:A a owl:Class ; owl:deprecated ex:B .") == []
    assert _messages("OBO007", 'ex:A a owl:Class ; owl:deprecated " TRUE " .') != []


def test_obo007_scope_is_classes_and_object_datatype_properties() -> None:
    for kind in ("owl:Class", "owl:ObjectProperty", "owl:DatatypeProperty"):
        assert _focus("OBO007", f"ex:A a {kind} ; owl:deprecated true .") == [EX + "A"], kind
    for kind in ("owl:NamedIndividual", "owl:AnnotationProperty"):
        assert _focus("OBO007", f"ex:A a {kind} ; owl:deprecated true .") == [], kind
    assert _focus("OBO007", "ex:A owl:deprecated true .") == []


# --- OBO008 ----------------------------------------------------------------------------------


def test_obo008_reports_roots_only() -> None:
    found = _run("OBO008", graph(HEAD + "ex:A a owl:Class ."))
    assert [(f.focus, f.message) for f in found] == [
        (EX + "A", "Class has no asserted superclass and no path to a BFO class.")
    ]
    chain = "ex:A a owl:Class ; rdfs:subClassOf ex:B . ex:B a owl:Class ."
    assert _focus("OBO008", chain) == [EX + "B"]
    assert _focus("OBO008", "ex:A a owl:Class ; rdfs:subClassOf ex:Unknown .") == []
    assert _focus("OBO008", "ex:A a owl:Class ; rdfs:subClassOf owl:Thing .") == [EX + "A"]
    assert _focus("OBO008", "ex:A a owl:Class ; rdfs:subClassOf [ a owl:Restriction ] .") == [EX + "A"]
    assert _focus("OBO008", "ex:A a owl:Class ; rdfs:subClassOf obo:BFO_0000001 .") == []
    deep = "ex:A rdfs:subClassOf ex:B . ex:B rdfs:subClassOf ex:C . ex:C rdfs:subClassOf obo:BFO_0000002 ."
    assert _focus("OBO008", "ex:A a owl:Class . ex:B a owl:Class . ex:C a owl:Class . " + deep) == []
    genus = "ex:A a owl:Class ; owl:equivalentClass [ owl:intersectionOf ( ex:G [ a owl:Restriction ] ) ] ."
    assert _focus("OBO008", genus + " ex:G a owl:Class .") == [EX + "G"]
    assert _focus("OBO008", genus + " ex:G a owl:Class ; rdfs:subClassOf obo:BFO_0000001 .") == []
    bfo = "ex:A a owl:Class ; owl:equivalentClass [ owl:intersectionOf ( obo:BFO_0000004 [ a owl:Restriction ] ) ] ."
    assert _focus("OBO008", bfo) == []
    assert _focus("OBO008", "ex:A a owl:Class ; owl:equivalentClass [ owl:intersectionOf ( ex:G ) ] .") == []
    assert _focus("OBO008", "ex:A a owl:Class ; owl:equivalentClass [ owl:intersectionOf ( ) ] .") == [EX + "A"]
    assert _focus("OBO008", "ex:A a owl:Class . obo:BFO_0000002 owl:equivalentClass ex:A .") == []
    assert _focus("OBO008", "ex:A a owl:Class ; rdfs:subClassOf ex:B . ex:B a owl:Class ; rdfs:subClassOf ex:A .") == []


def test_obo008_honours_base_and_obsolescence() -> None:
    turtle = f"<{OBO}X_1> a owl:Class . ex:A a owl:Class ."
    assert _focus("OBO008", turtle, base=EX) == [EX + "A"]
    assert _focus("OBO008", "ex:A a owl:Class ; owl:deprecated true .") == []
    assert _focus("OBO008", 'ex:A a owl:Class ; owl:deprecated "false" .') == [EX + "A"]
    assert _focus("OBO008", "obo:BFO_0000001 a owl:Class . obo:BFO_0000002 a owl:Class .") == []
    assert _focus("OBO008", "ex:A a owl:Class ; rdfs:subClassOf ex:B .", base=EX) == []
    assert _focus("OBO008", "ex:A a owl:Class ; rdfs:subClassOf ex:B . ex:B a owl:Class .", base=EX) == [EX + "B"]


# --- OBO009 ----------------------------------------------------------------------------------


def test_obo009_scoped_synonyms_are_fine() -> None:
    assert _messages("OBO009", 'ex:A oio:hasExactSynonym "alias" .') == []
    assert _messages("OBO009", 'ex:A obo:IAO_0000118 "alias" .') == []


def test_obo009_messages_and_scope() -> None:
    found = _messages("OBO009", 'ex:A oio:hasSynonym "alias" ; skos:altLabel "other" .')
    assert sorted(found) == [
        "Synonym 'alias' (http://www.geneontology.org/formats/oboInOwl#hasSynonym) has no scope.",
        "Synonym 'other' (http://www.w3.org/2004/02/skos/core#altLabel) has no scope.",
    ]
    assert _focus("OBO009", 'ex:A skos:altLabel "a" .') == [EX + "A"]
    assert _focus("OBO009", 'ex:A skos:altLabel "a" .', base=OBO) == []
    assert _messages("OBO009", '[] skos:altLabel "a" .') == []
    assert _messages("OBO009", 'ex:A skos:altLabel "" .') == []
    long = "z" * 61
    assert _messages("OBO009", f'ex:A skos:altLabel "{long}" .')[0].startswith(f"Synonym '{'z' * 60}...' ")
    assert _messages("OBO009", f'ex:A skos:altLabel "{"z" * 60}" .')[0].startswith(f"Synonym '{'z' * 60}' ")


# --- OBO010 ----------------------------------------------------------------------------------


def test_obo010_patterns() -> None:
    whole = f"{OBO}uberon.owl"
    found = _run("OBO010", graph(HEAD + f"ex:o owl:imports <{whole}> ."))
    assert [(f.focus, f.message) for f in found] == [
        (EX + "o", f"Import {whole} is a whole ontology, not an import module.")
    ]
    released = f"{OBO}uberon/releases/2020-01-01/uberon.owl"
    assert len(_messages("OBO010", f"ex:o owl:imports <{released}> .")) == 1
    for ok in (
        f"{OBO}uberon/releases/2020-01-01/ro.owl",  # \1 back-reference: another ontology's file
        f"{OBO}uberon/imports/uberon_import.owl",
        f"{OBO}uberon.owl#x",
        f"{OBO}uberon.obo",
        f"x{OBO}uberon.owl",
        f"{OBO}uberon.owl/extra",
        "https://example.org/uberon.owl",
        f"{OBO}.owl/x",
    ):
        assert _messages("OBO010", f"ex:o owl:imports <{ok}> .") == [], ok
    assert len(_messages("OBO010", f"ex:o owl:imports <{OBO}x.owl>, <{OBO}y.owl> .")) == PAIR
    for name in ("bfo", "omo", "ro"):
        assert _messages("OBO010", f"ex:o owl:imports <{OBO}{name}.owl> .") == [], name
    assert len(_messages("OBO010", f"ex:o owl:imports <{OBO}chebi.owl> .")) == 1
    assert len(_messages("OBO010", f"ex:o owl:imports <{OBO}bfo2.owl>, <{OBO}ro.owl> .")) == 1


# --- OBO011 ----------------------------------------------------------------------------------


def test_obo011_ontology_iri_messages_and_patterns() -> None:
    found = _run("OBO011", graph(HEAD + "ex:o a owl:Ontology ."))
    assert [(f.focus, f.message) for f in found] == [
        (EX + "o", f"Ontology IRI {EX}o does not follow the OBO PURL pattern {OBO}<id>.owl.")
    ]
    for ok in ("a.owl", "z9_a.owl", "go/x.owl", "go/imports/a-b_import.owl", "go/a.b.owl"):
        assert _focus("OBO011", f"<{OBO}{ok}> a owl:Ontology .") == [], ok
    for bad in (
        "A.owl",
        "9a.owl",
        "_a.owl",
        "a-b.owl",
        "a.owl.txt",
        "go/x.ttl",
        "go/ x.owl",
        "a",
        "go/.owl",
        "a b.owl",
    ):
        assert len(_focus("OBO011", f"<{OBO}{bad}> a owl:Ontology .")) == 1, bad
    assert _focus("OBO011", f"<{OBO[:-1]}xyz.owl> a owl:Ontology .") != []
    assert _focus("OBO011", f"<{OBO.replace('http:', 'https:')}xyz.owl> a owl:Ontology .") != []


def test_obo011_version_iri_messages_and_patterns() -> None:
    ontology = f"<{OBO}xyz.owl> a owl:Ontology ; owl:versionIRI "
    good = f"<{OBO}xyz/releases/2020-01-01/xyz.owl>"
    assert _focus("OBO011", ontology + good + " .") == []
    bad = f"<{OBO}xyz/releases/2020-01-1/xyz.owl>"
    found = _run("OBO011", graph(HEAD + ontology + bad + " ."))
    assert [(f.focus, f.message, f.confidence) for f in found] == [
        (OBO + "xyz.owl", f"Version IRI {bad[1:-1]} does not follow {OBO}<id>/releases/YYYY-MM-DD/<id>.owl.", "certain")
    ]
    for bad_version in (
        f"{OBO}abc/releases/2020-01-01/abc.owl",  # a different ontology id
        f"{OBO}xyz/releases/2020-1-01/xyz.owl",
        f"{OBO}xyz/releases//xyz.owl",
        f"{OBO}xyz/1../xyz.owl",
        f"{OBO}xyz/v1/xyz.owl",
        f"{OBO}xyz/releases/2020-01-01/",
        f"{OBO}xyz/releases/2020-01-01/xyz.ttl",
        f"{OBO}Xyz/releases/2020-01-01/xyz.owl",
        f"{OBO}xyz/releases/2020-01-011/xyz.owl",
        f"{OBO}xyz/releases/x2020-01-01/xyz.owl",
        "http://example.org/v1",
    ):
        assert len(_focus("OBO011", ontology + f"<{bad_version}> .")) == 1, bad_version
    for release in ("2019-08-26", "257", "1.2.3", "releases/2026-09-04", "releases/257"):
        assert _focus("OBO011", ontology + f"<{OBO}xyz/{release}/xyz.owl> .") == [], release
    assert _focus("OBO011", ontology + f"<{OBO}xyz/releases/2026-09-04/core.owl> .") == []
    other = f"<{OBO}bar/releases/2020-01-01/bar.owl>"
    assert len(_focus("OBO011", ontology + other + " .")) == 1
    chebi = f"<{OBO}chebi.owl> a owl:Ontology ; owl:versionIRI <{OBO}chebi/257/chebi.owl> ."
    assert _focus("OBO011", chebi) == []
    assert len(_focus("OBO011", "<http://example.org/x.owl> a owl:Ontology .")) == 1
    ok_other_file = f"{OBO}xyz/releases/2020-01-01/extensions/xyz-plus.owl"
    assert _focus("OBO011", ontology + f"<{ok_other_file}> .") == []
    assert _messages("OBO011", ontology + '"not an iri" .') != []
    both_bad = f"<{EX}o> a owl:Ontology ; owl:versionIRI <{EX}v> ."
    assert len(_focus("OBO011", both_bad)) == PAIR
    unrelated_but_valid = f"<{EX}o> a owl:Ontology ; owl:versionIRI <{OBO}abc/releases/2020-01-01/abc.owl> ."
    assert len(_focus("OBO011", unrelated_but_valid)) == 1  # only the ontology IRI is wrong


# --- OBO012 ----------------------------------------------------------------------------------


def test_obo012_messages_and_triggers() -> None:
    def labelled(label: str) -> list[str]:
        return _messages("OBO012", f'ex:A a owl:Class ; rdfs:label "{label}" .')

    assert labelled(" cell") == ["Label ' cell' has leading, trailing or repeated whitespace."]
    assert labelled("cell ") == ["Label 'cell ' has leading, trailing or repeated whitespace."]
    assert labelled("a  b") == ["Label 'a  b' has leading, trailing or repeated whitespace."]
    assert labelled("two  spaces") == ["Label 'two  spaces' has leading, trailing or repeated whitespace."]
    assert labelled("a b c") == []
    assert labelled("a_b") == ["Label 'a_b' contains an underscore."]
    for capitalised in ("Ab", "A", "AB", "aB", "1b", "Kupffer cell"):
        assert labelled(capitalised) == [], capitalised
    assert sorted(labelled(" Ab_c")) == [
        "Label ' Ab_c' contains an underscore.",
        "Label ' Ab_c' has leading, trailing or repeated whitespace.",
    ]
    deprecated = 'ex:A a owl:Class ; owl:deprecated true ; rdfs:label "obsolete_x" .'
    assert _messages("OBO012", deprecated) == []
    assert len(_messages("OBO012", deprecated.replace("true", '"false"'))) == 1


def test_obo012_language_and_scope() -> None:
    def tagged(label: str, tag: str) -> int:
        return len(_messages("OBO012", f'ex:A a owl:Class ; rdfs:label "{label}"@{tag} .'))

    assert tagged("Cell", "en") == 0
    assert tagged("Cell", "fr") == 0
    assert tagged("A_b", "fr") == 1  # whitespace and underscore rules are language independent
    assert tagged(" a", "fr") == 1
    assert _focus("OBO012", 'ex:p a owl:DatatypeProperty ; rdfs:label "A_b" .') == [EX + "p"]
    assert _focus("OBO012", 'ex:A a owl:Class ; rdfs:label "A_b" .', base=OBO) == []
    long = "q" * 59 + "_"
    assert _messages("OBO012", f'ex:A a owl:Class ; rdfs:label "{long}" .') == [
        f"Label '{long}' contains an underscore."
    ]
    longer = "q" * 61 + "_"
    assert _messages("OBO012", f'ex:A a owl:Class ; rdfs:label "{longer}" .') == [
        f"Label '{'q' * 60}...' contains an underscore."
    ]
