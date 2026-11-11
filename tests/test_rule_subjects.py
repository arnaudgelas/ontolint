"""The structured subject of findings that a rule can report several times on one focus.

A finding's identity is its rule, its focus and its subject (``Finding.subject``), never its message: these
cases pin, for each rule that reports more than one problem about the same focus, the subject that tells them
apart, in the rule's canonical order.
"""

from __future__ import annotations

import pytest
from rule_harness import BASE, graph

from ontolint import Linter
from ontolint.engine import build_context
from ontolint.models import SourceFacts
from ontolint.policy import Policy
from ontolint.rules import iri_quality

OWL = "http://www.w3.org/2002/07/owl#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
XSD = "http://www.w3.org/2001/XMLSchema#"


def _short(text: str) -> str:
    return text.removeprefix(BASE).replace(OWL, "owl:").replace(RDFS, "rdfs:").replace(XSD, "xsd:")


def subjects(rule: str, turtle: str, shapes: str | None = None, **options: object) -> set[tuple[str, tuple[str, ...]]]:
    """``(focus, subject)`` of every finding ``rule`` reports on ``turtle``, with the usual prefixes shortened."""
    shapes_graph = graph(shapes) if shapes is not None else None
    findings = Linter(graph(turtle), shapes_graph, **options).execute([rule]).findings  # type: ignore[arg-type]
    pairs = [(_short(f.focus), tuple(map(_short, f.subject))) for f in findings if f.rule == rule]
    assert len(pairs) == len(set(pairs)), f"{rule}: two findings share a subject: {pairs}"
    return set(pairs)


# --- OWL ---------------------------------------------------------------------------------------------


OWL_CASES = [
    (
        "OWL002",
        "ex:p rdfs:domain ex:A ; rdfs:range ex:B .",
        {("p", ("rdfs:domain",)), ("p", ("rdfs:range",))},
    ),
    (
        "OWL004",
        "ex:p a owl:ObjectProperty ; rdfs:domain ex:A, ex:B ; rdfs:range ex:C, ex:D .",
        {("p", ("rdfs:domain",)), ("p", ("rdfs:range",))},
    ),
    (
        "OWL009",
        "ex:p a owl:DatatypeProperty, owl:TransitiveProperty, owl:SymmetricProperty ; owl:inverseOf ex:q .",
        {("p", ("owl:inverseOf",)), ("p", ("owl:TransitiveProperty",)), ("p", ("owl:SymmetricProperty",))},
    ),
    (
        "OWL013",
        'ex:p a owl:ObjectProperty . ex:q a owl:ObjectProperty . ex:i ex:p "a" ; ex:q "b"@en .',
        {("i", ("p", '"a"')), ("i", ("q", '"b"@en'))},
    ),
    (
        "OWL018",
        "ex:p a owl:ReflexiveProperty, owl:IrreflexiveProperty, owl:AsymmetricProperty .",
        {
            ("p", ("owl:ReflexiveProperty", "owl:IrreflexiveProperty")),
            ("p", ("owl:ReflexiveProperty", "owl:AsymmetricProperty")),
        },
    ),
    (
        "OWL026",
        "ex:a owl:differentFrom ex:a . ex:a owl:sameAs ex:b ; owl:differentFrom ex:b .",
        {("a", ("a",)), ("a", ("b",))},
    ),
    (
        "OWL029",
        "ex:p a owl:AsymmetricProperty . ex:a ex:p ex:a, ex:b . ex:b ex:p ex:a .",
        {("a", ("p",)), ("a", ("p", "b"))},
    ),
    (
        "OWL031",
        "ex:A owl:unionOf () ; owl:intersectionOf ( ex:B ex:C ) ; owl:oneOf ex:x .",
        {("A", ("owl:unionOf", "empty")), ("A", ("owl:oneOf", "malformed"))},
    ),
    (
        "OWL045",
        "ex:x a owl:AllDifferent, owl:AllDisjointClasses .",
        {
            ("x", ("owl:AllDifferent", "no member list")),
            ("x", ("owl:AllDisjointClasses", "no member list")),
        },
    ),
    (
        "DATA001",
        "ex:p a owl:DatatypeProperty ; rdfs:range xsd:date . ex:q a owl:DatatypeProperty ; rdfs:range xsd:date ."
        ' ex:i ex:p "1"^^xsd:boolean ; ex:q "x" .',
        {("i", ("p", "xsd:boolean")), ("i", ("q", ""))},
    ),
]


@pytest.mark.parametrize(("rule", "turtle", "expected"), OWL_CASES, ids=[c[0] for c in OWL_CASES])
def test_owl_subjects(rule: str, turtle: str, expected: set[tuple[str, tuple[str, ...]]]) -> None:
    assert subjects(rule, turtle) == expected


def test_owl011_tells_a_general_class_axiom_from_a_restriction_of_the_class() -> None:
    turtle = """
        ex:p a owl:ObjectProperty .
        ex:A a owl:Class ; rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:p ; owl:allValuesFrom ex:B ] .
        [ a owl:Restriction ; owl:onProperty ex:p ; owl:allValuesFrom ex:C ] rdfs:subClassOf ex:A .
    """
    assert subjects("OWL011", turtle) == {("A", ("p",)), ("A", ("general class axiom", "p"))}


def test_owl040_names_the_property_and_the_offending_value_not_its_repr() -> None:
    turtle = """
        ex:p a owl:ObjectProperty .
        ex:A rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:p ;
            owl:hasValue "v" ; owl:allValuesFrom xsd:int ] .
    """
    found = subjects("OWL040", turtle)
    assert {s for _focus, s in found} == {("p", "owl:hasValue", '"v"'), ("p", "filler", "xsd:int")}


def test_owl036_and_owl037_keep_the_predicate_value_or_group_out_of_the_message() -> None:
    turtle = """
        ex:A rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:p ;
            owl:minCardinality "x" ; owl:maxCardinality 1 ; owl:cardinality 3 ] .
    """
    assert {s for _f, s in subjects("OWL036", turtle)} == {("owl:minCardinality", '"x"')}
    assert {s for _f, s in subjects("OWL037", turtle)} == {("unqualified",)}


def test_owl043_names_the_operator_the_use_and_the_operands() -> None:
    turtle = """
        ex:A owl:intersectionOf ( ex:B ex:C owl:Nothing ) . ex:B owl:disjointWith ex:C .
    """
    assert subjects("OWL043", turtle) == {
        ("A", ("owl:intersectionOf", "B", "C")),
        ("A", ("owl:intersectionOf", "owl:Nothing")),
    }


# --- lexical and IRI ---------------------------------------------------------------------------------


def test_lex008_names_each_missing_language() -> None:
    found = subjects("LEX008", 'ex:A a owl:Class ; rdfs:label "A"@de .', languages=("en", "fr"))
    assert found == {("A", ("en",)), ("A", ("fr",))}


def test_lex003_names_the_language_not_the_count() -> None:
    turtle = 'ex:A a owl:Class ; rdfs:label "A"@en, "B"@en, "C"@fr, "D"@fr, "E"@fr .'
    assert subjects("LEX003", turtle) == {("A", ("en",)), ("A", ("fr",))}


def test_lex004_and_iri003_name_the_collision_key_not_its_members() -> None:
    two = 'ex:A a owl:Class ; rdfs:label "Same"@en . ex:B a owl:Class ; rdfs:label "Same"@en .'
    three = two + ' ex:C a owl:Class ; rdfs:label "Same"@en .'
    assert subjects("LEX004", two) == subjects("LEX004", three) == {("A", ("Same", "en", "class"))}
    collision = "ex:Thing a owl:Class . ex:thing a owl:Class . ex:THING a owl:ObjectProperty, owl:Class ."
    assert subjects("IRI003", collision) == {("THING", ("thing", "class"))}


def test_lex014_names_the_label_and_its_datatype() -> None:
    labels = 'ex:A a owl:Class ; rdfs:label "A"^^xsd:token, "B"^^xsd:token .'
    assert subjects("LEX014", labels) == {("A", ("A", "xsd:token")), ("A", ("B", "xsd:token"))}


def test_iri019_names_each_unused_prefix_of_a_namespace() -> None:
    declared = (("a", "https://unused.test/"), ("b", "https://unused.test/"))
    ctx = build_context(graph("ex:A a owl:Class ."), None, Policy(source=SourceFacts(declared_prefixes=declared)))
    iri_quality.run(ctx)
    found = {(f.focus, f.subject) for f in ctx.findings if f.rule == "IRI019"}
    assert found == {("https://unused.test/", ("a",)), ("https://unused.test/", ("b",))}


def test_data003_names_the_predicate_and_the_whole_literal() -> None:
    turtle = 'ex:A a owl:Class ; ex:p "x"^^xsd:integer ; ex:q "y"^^xsd:integer .'
    assert subjects("DATA003", turtle) == {
        ("A", ("p", '"x"^^<xsd:integer>')),
        ("A", ("q", '"y"^^<xsd:integer>')),
    }


# --- SKOS and alignment ------------------------------------------------------------------------------

SKOS = "http://www.w3.org/2004/02/skos/core#"


def _skos(found: set[tuple[str, tuple[str, ...]]]) -> set[tuple[str, tuple[str, ...]]]:
    return {(focus, tuple(part.replace(SKOS, "skos:") for part in about)) for focus, about in found}


def test_skos001_names_the_language_not_the_count() -> None:
    turtle = 'ex:c a skos:Concept ; skos:prefLabel "a"@en, "b"@en, "c"@fr, "d"@FR .'
    assert subjects("SKOS001", turtle) == {("c", ("en",)), ("c", ("fr",))}


def test_skos018_names_the_redundant_broader_and_the_path_through_it() -> None:
    turtle = """
        ex:c skos:broader ex:p1, ex:p2, ex:g . ex:p1 skos:broader ex:g . ex:p2 skos:broader ex:g .
        ex:c a skos:Concept . ex:p1 a skos:Concept . ex:p2 a skos:Concept . ex:g a skos:Concept .
    """
    assert subjects("SKOS018", turtle) == {("c", ("g", "p1")), ("c", ("g", "p2"))}


def test_skos021_names_the_scheme_and_the_shared_label_not_how_many_share_it() -> None:
    two = """
        ex:s a skos:ConceptScheme .
        ex:a a skos:Concept ; skos:inScheme ex:s ; skos:prefLabel "Same"@en .
        ex:b a skos:Concept ; skos:inScheme ex:s ; skos:prefLabel "same"@en .
    """
    three = two + 'ex:c a skos:Concept ; skos:inScheme ex:s ; skos:prefLabel "SAME"@en .'
    expected = {("a", ("s", "en", "same")), ("b", ("s", "en", "same"))}
    assert subjects("SKOS021", two) == expected
    assert subjects("SKOS021", three) == {*expected, ("c", ("s", "en", "same"))}


def test_align004_tells_mutual_broader_from_related_and_broader() -> None:
    turtle = """
        ex:a skos:broadMatch ex:b . ex:b skos:broadMatch ex:a .
        ex:a skos:relatedMatch ex:b .
    """
    assert _skos(subjects("ALIGN004", turtle)) == {
        ("a", ("skos:broadMatch", "b")),
        ("a", ("skos:relatedMatch", "b")),
    }


def test_align013_tells_equivalence_predicates_from_both_hierarchy_directions() -> None:
    turtle = """
        ex:a skos:exactMatch ex:b ; skos:closeMatch ex:b ; skos:broadMatch ex:b .
        ex:b skos:narrowMatch ex:a .
    """
    assert _skos(subjects("ALIGN013", turtle)) == {
        ("a", ("equivalence", "b")),
        ("a", ("skos:broadMatch", "skos:narrowMatch", "b")),
    }


# --- OBO, metadata, governance and FAIR --------------------------------------------------------------

DCT = "http://purl.org/dc/terms/"


def _dct(found: set[tuple[str, tuple[str, ...]]]) -> set[tuple[str, tuple[str, ...]]]:
    return {(focus, tuple(part.replace(DCT, "dcterms:") for part in about)) for focus, about in found}


def test_obo002_names_each_missing_header_field_by_its_predicate() -> None:
    assert _dct(subjects("OBO002", "<https://example.test/o> a owl:Ontology .")) == {
        ("https://example.test/o", ("dcterms:title",)),
        ("https://example.test/o", ("dcterms:description",)),
        ("https://example.test/o", ("dcterms:license",)),
    }


def test_obo011_tells_the_ontology_iri_from_each_version_iri() -> None:
    turtle = "<https://example.test/o> a owl:Ontology ; owl:versionIRI <https://example.test/o/1> ."
    assert subjects("OBO011", turtle) == {
        ("https://example.test/o", ()),
        ("https://example.test/o", ("owl:versionIRI", "https://example.test/o/1")),
    }


def test_obo004_and_obo012_name_the_label_and_the_problem() -> None:
    turtle = """
        <http://purl.obolibrary.org/obo/X_0000001> a owl:Class ; rdfs:label " a_b"@en .
        <http://purl.obolibrary.org/obo/X_0000002> a owl:Class ; rdfs:label " a_b"@en .
        <http://purl.obolibrary.org/obo/X_0000003> a owl:Class .
    """
    obo = "http://purl.obolibrary.org/obo/"
    assert subjects("OBO012", turtle) >= {
        (f"{obo}X_0000001", (" a_b", "whitespace")),
        (f"{obo}X_0000001", (" a_b", "underscore")),
    }
    assert subjects("OBO004", turtle) == {
        (f"{obo}X_0000001", (" a_b", "en")),
        (f"{obo}X_0000002", (" a_b", "en")),
        (f"{obo}X_0000003", ()),
    }


def test_ont005_names_the_missing_provenance_by_predicate() -> None:
    assert _dct(subjects("ONT005", "<https://example.test/o> a owl:Ontology .")) == {
        ("https://example.test/o", ("dcterms:creator", "dcterms:created")),
    }
    with_creator = '<https://example.test/o> a owl:Ontology ; dcterms:creator "A" .'
    assert _dct(subjects("ONT005", with_creator)) == {("https://example.test/o", ("dcterms:created",))}


def test_gov001_tells_a_list_member_an_object_and_a_predicate_apart() -> None:
    turtle = """
        ex:old a owl:Class ; owl:deprecated true .
        ex:oldp a owl:ObjectProperty ; owl:deprecated true .
        ex:A a owl:Class ; rdfs:subClassOf ex:old ; owl:unionOf ( ex:old ex:B ) ; ex:oldp ex:B .
    """
    found = {about for focus, about in subjects("GOV001", turtle) if focus == "A"}
    assert found == {("old", "object", "rdfs:subClassOf"), ("old", "list", "owl:unionOf"), ("oldp", "predicate")}


def test_fair011_names_the_value_kind_and_identifier() -> None:
    iri = "<https://example.test/o> a owl:Ontology ; dcterms:creator <https://orcid.org/0000-0002-1825-0099> ."
    assert subjects("FAIR011", iri) == {
        ("https://example.test/o", ("https://orcid.org/0000-0002-1825-0099", "ORCID iD", "0000-0002-1825-0099")),
    }
    # Two identifiers failing the same way give one message, hence one finding: it keeps the least subject.
    text = "0000-0002-1825-0099 and 0000-0002-1825-0098"
    found = subjects("FAIR011", f'<https://example.test/o> a owl:Ontology ; dcterms:creator "{text}" .')
    assert found == {("https://example.test/o", (text, "ORCID iD", "0000-0002-1825-0098"))}


# --- SHACL authoring and quality ---------------------------------------------------------------------

SH = "http://www.w3.org/ns/shacl#"


def _sh(found: set[tuple[str, tuple[str, ...]]]) -> set[tuple[str, tuple[str, ...]]]:
    return {(focus, tuple(part.replace(SH, "sh:") for part in about)) for focus, about in found}


def test_shq009_tells_an_empty_list_from_a_repeating_one() -> None:
    shapes = "ex:S a sh:NodeShape ; sh:in () ; sh:in ( ex:a ex:a ) ."
    assert _sh(subjects("SHQ009", "", shapes)) == {("S", ("sh:in", "empty")), ("S", ("sh:in", "repeated"))}


def test_shq015_tells_a_bad_flag_from_flags_without_a_pattern() -> None:
    shapes = 'ex:S a sh:NodeShape ; sh:flags "z" .'
    assert _sh(subjects("SHQ015", "", shapes)) == {("S", ('"z"',)), ("S", ("sh:pattern",))}


def test_shq019_and_shq008_name_the_predicate_and_the_value() -> None:
    shapes = """
        ex:S a sh:NodeShape ; sh:node ex:Missing ; sh:property ex:Gone .
        ex:P a sh:PropertyShape ; sh:path ex:p ; sh:minCount -1 ; sh:maxCount [ ] .
    """
    assert _sh(subjects("SHQ019", "", shapes)) == {("S", ("sh:node", "Missing")), ("S", ("sh:property", "Gone"))}
    assert _sh(subjects("SHQ008", "", shapes)) == {
        ("P", ("sh:minCount", '"-1"^^<xsd:integer>')),
        ("P", ("sh:maxCount", "(blank node)")),
    }


# --- classes, hierarchy, metrics, safety and policy --------------------------------------------------


def test_cls010_names_the_parent_and_the_shared_label_not_the_sibling() -> None:
    turtle = """
        ex:P a owl:Class . ex:Q a owl:Class .
        ex:A a owl:Class ; rdfs:subClassOf ex:P, ex:Q ; rdfs:label "Thing" .
        ex:B a owl:Class ; rdfs:subClassOf ex:P, ex:Q ; rdfs:label "thing" .
    """
    found = {about for focus, about in subjects("CLS010", turtle) if focus == "A"}
    assert {about[0] for about in found} == {"P", "Q"}
    assert all("B" not in about for about in found)


def test_cls025_names_both_types() -> None:
    turtle = """
        ex:A a owl:Class . ex:B a owl:Class ; rdfs:subClassOf ex:A . ex:C a owl:Class ; rdfs:subClassOf ex:B .
        ex:i a ex:A, ex:B, ex:C .
    """
    assert subjects("CLS025", turtle) == {("i", ("B", "A")), ("i", ("C", "A")), ("i", ("C", "B"))}


def test_gov016_names_the_missing_annotations_by_iri() -> None:
    policy = Policy.from_mapping({"required_annotations": {"class": [RDFS + "label", RDFS + "comment"]}})
    assert subjects("GOV016", "ex:A a owl:Class .", policy=policy) == {("A", ("rdfs:comment", "rdfs:label"))}


def test_sec012_tells_literals_on_two_predicates_apart_and_ignores_which_characters() -> None:
    turtle = 'ex:a ex:p "x\\u202Ey" ; ex:q "x\\u0007y" .'
    assert subjects("SEC012", turtle) == {("a", ("p",)), ("a", ("q",))}


def test_metric_findings_carry_no_subject_so_a_new_ratio_is_the_same_finding() -> None:
    few = "".join(f"ex:C{i} a owl:Class . " for i in range(12))
    more = few + "".join(f"ex:D{i} a owl:Class . " for i in range(5))
    assert subjects("METRIC001", few) == subjects("METRIC001", more) == {("urn:ontolint:graph", ())}


def test_sec012_reports_every_hazardous_character_of_one_predicate_in_one_finding() -> None:
    # Two literals with different characters were two findings with one identity, so one baselined hid the other.
    turtle = 'ex:a ex:p "x\\u202Ey", "x\\u0007y" .'
    assert subjects("SEC012", turtle) == {("a", ("p",))}
    (finding,) = Linter(graph(turtle)).execute(["SEC012"]).findings
    assert finding.message.endswith("contains control or bidirectional-override characters (U+0007, U+202E).")


def test_sec005_reports_the_longest_literal_of_one_predicate_in_one_finding() -> None:
    from ontolint.rules.safety import MAX_LITERAL_LENGTH  # noqa: PLC0415 -- the limit the fixture exceeds

    long, longer = "x" * (MAX_LITERAL_LENGTH + 1), "y" * (MAX_LITERAL_LENGTH + 2)
    turtle = f'ex:a ex:p "{long}", "{longer}" .'
    assert subjects("SEC005", turtle) == {("a", ("p",))}
    (finding,) = Linter(graph(turtle)).execute(["SEC005"]).findings
    assert f"has {MAX_LITERAL_LENGTH + 2} characters" in finding.message
