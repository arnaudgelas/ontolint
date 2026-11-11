"""Exact findings for the coverage gaps closed in the OWL, SHACL and SKOS rules (TODO.md, P1 audit item).

Each gap was a stated exclusion: a construct the W3C specification rejects or makes inconsistent that the rule
left silent.  These tests pin the focus, message and subject of each new condition; the rule cases
(``tests/rule_cases``) carry the positive and negative fixtures, and ``test_coverage_gap_stability`` that the
findings reported before stay as they were.  ``ex:`` stands for the cases' base IRI.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rule_harness import BASE, graph

from ontolint import Linter, main
from ontolint.rules.shacl_authoring import xpath_regex_problem

OWL = "http://www.w3.org/2002/07/owl#"

Found = set[tuple[str, str, tuple[str, ...]]]


def short(text: str) -> str:
    return text.replace(BASE, "ex:")


def found(rule: str, turtle: str, shapes: str | None = None) -> Found:
    """``(focus, message, subject)`` of every ``rule`` finding when only ``rule`` runs, ``ex:`` shortened."""
    shapes_graph = graph(shapes) if shapes is not None else None
    findings = Linter(graph(turtle), shapes_graph).execute([rule]).findings
    return {(short(f.focus), short(f.message), tuple(map(short, f.subject))) for f in findings if f.rule == rule}


# --- OWL010: a chain needs two operands (SS 9.2.1, MAP Table 16) --------------------------------------


def test_owl010_reports_an_empty_chain() -> None:
    assert found("OWL010", "ex:p owl:propertyChainAxiom () .") == {
        ("ex:p", "Property-chain axiom list is empty.", ("empty",))
    }


def test_owl010_reports_a_chain_that_is_no_rdf_list() -> None:
    malformed = {("ex:p", "Property-chain axiom does not point to a well-formed RDF list.", ("malformed",))}
    assert found("OWL010", 'ex:p owl:propertyChainAxiom "ex:q" .') == malformed
    assert found("OWL010", "ex:p owl:propertyChainAxiom _:l . _:l rdf:first ex:q .") == malformed
    assert found("OWL010", "ex:p owl:propertyChainAxiom _:l . _:l rdf:first ex:q ; rdf:rest _:l .") == malformed


def test_owl010_tells_each_defective_chain_of_one_property_apart() -> None:
    turtle = "ex:p owl:propertyChainAxiom ( ex:q ), (), ex:r, ( ex:s ex:t ) ."
    assert found("OWL010", turtle) == {
        ("ex:p", "Property-chain axiom has one operand.", ()),
        ("ex:p", "Property-chain axiom list is empty.", ("empty",)),
        ("ex:p", "Property-chain axiom does not point to a well-formed RDF list.", ("malformed",)),
    }


# --- OWL019: non-simplicity follows SS 11.1's property hierarchy ----------------------------------------

FUNCTIONAL = (f"{OWL}FunctionalProperty",)


def test_owl019_names_the_composite_property_a_super_property_is_non_simple_through() -> None:
    turtle = "ex:t a owl:TransitiveProperty ; rdfs:subPropertyOf ex:m . ex:m rdfs:subPropertyOf ex:p ."
    assert found("OWL019", turtle + " ex:p a owl:FunctionalProperty .") == {
        ("ex:p", "Property is non-simple through ex:t, which is transitive, but declared functional.", FUNCTIONAL)
    }


def test_owl019_follows_inverses_and_equivalences() -> None:
    inverse = "ex:t a owl:TransitiveProperty ; owl:inverseOf ex:p . ex:p a owl:InverseFunctionalProperty ."
    assert found("OWL019", inverse) == {
        (
            "ex:p",
            "Property is non-simple through ex:t, which is transitive, but declared inverse-functional.",
            (f"{OWL}InverseFunctionalProperty",),
        )
    }
    equivalent = "ex:c owl:propertyChainAxiom ( ex:a ex:b ) . ex:p owl:equivalentProperty ex:c ."
    assert found("OWL019", equivalent + " ex:p a owl:IrreflexiveProperty .") == {
        (
            "ex:p",
            "Property is non-simple through ex:c, which is defined by a property chain, but declared irreflexive.",
            (f"{OWL}IrreflexiveProperty",),
        )
    }


def test_owl019_reads_a_blank_inverse_expression_as_its_property() -> None:
    # t -> INV(p) gives INV(t) -> p, and INV(t) is composite with t.
    via_inverse = "ex:t a owl:TransitiveProperty ; rdfs:subPropertyOf [ owl:inverseOf ex:p ] ."
    assert found("OWL019", via_inverse + " ex:p a owl:FunctionalProperty .") == {
        ("ex:p", "Property is non-simple through ex:t, which is transitive, but declared functional.", FUNCTIONAL)
    }
    own_inverse = "[ owl:inverseOf ex:p ] a owl:TransitiveProperty . ex:p a owl:FunctionalProperty ."
    assert found("OWL019", own_inverse) == {
        ("ex:p", "Property is transitive (non-simple) but declared functional.", FUNCTIONAL)
    }


def test_owl019_counts_the_top_object_property_as_composite() -> None:
    assert found("OWL019", "ex:p owl:equivalentProperty owl:topObjectProperty ; a owl:FunctionalProperty .") == {
        (
            "ex:p",
            f"Property is non-simple through {OWL}topObjectProperty, which is the top object property, but declared"
            " functional.",
            FUNCTIONAL,
        )
    }
    assert found("OWL019", "owl:bottomObjectProperty a owl:FunctionalProperty .") == {
        (
            f"{OWL}bottomObjectProperty",
            "Property is the bottom object property (non-simple) but declared functional.",
            FUNCTIONAL,
        )
    }


def test_owl019_keeps_the_direct_message_when_the_property_is_composite_itself() -> None:
    turtle = "ex:t a owl:TransitiveProperty, owl:FunctionalProperty ; rdfs:subPropertyOf ex:c ."
    turtle += " ex:c owl:propertyChainAxiom ( ex:a ex:b ) ; rdfs:subPropertyOf ex:t ."
    assert found("OWL019", turtle) == {
        ("ex:t", "Property is transitive (non-simple) but declared functional.", FUNCTIONAL)
    }


def test_owl019_witness_is_the_first_composite_in_iri_order() -> None:
    turtle = "ex:z a owl:TransitiveProperty ; rdfs:subPropertyOf ex:p . ex:a a owl:TransitiveProperty ;"
    turtle += " rdfs:subPropertyOf ex:p . ex:p a owl:FunctionalProperty ."
    ((_focus, message, _subject),) = found("OWL019", turtle)
    assert "through ex:a," in message


def test_owl019_reports_each_simple_only_restriction_on_a_non_simple_property() -> None:
    turtle = "ex:t a owl:TransitiveProperty ; rdfs:subPropertyOf ex:p . ex:A rdfs:subClassOf [ a owl:Restriction ;"
    turtle += " owl:onProperty ex:p ; owl:maxCardinality 1 ; owl:hasSelf true ] ."
    ((focus, _message, _subject), *_others) = sorted(found("OWL019", turtle))
    owner = "ex:A: restriction on non-simple property ex:p (through ex:t, which is transitive) uses"
    assert {(m, s) for _f, m, s in found("OWL019", turtle)} == {
        (f"{owner} owl:maxCardinality.", ("ex:p", f"{OWL}maxCardinality")),
        (f"{owner} owl:hasSelf.", ("ex:p", f"{OWL}hasSelf")),
    }
    assert focus.startswith("_:")  # the restriction, by its stable identity


def test_owl019_names_an_inverse_expression_and_a_composite_restricted_property() -> None:
    inverse = "ex:t a owl:TransitiveProperty . [ a owl:Restriction ; owl:onProperty [ owl:inverseOf ex:t ] ;"
    inverse += " owl:cardinality 1 ] ."
    ((_focus, message, (restricted, predicate)),) = found("OWL019", inverse)
    assert message == "Restriction on non-simple property ObjectInverseOf(ex:t) (transitive) uses owl:cardinality."
    assert restricted.startswith("_:")
    assert predicate == f"{OWL}cardinality"


def test_owl019_reports_each_non_simple_side_of_a_property_disjointness() -> None:
    turtle = (
        "ex:t a owl:TransitiveProperty ; owl:propertyDisjointWith ex:c . ex:c owl:propertyChainAxiom ( ex:a ex:b ) ."
    )
    assert found("OWL019", turtle) == {
        (
            "ex:t",
            "Property is non-simple (transitive) but declared disjoint with ex:c.",
            (f"{OWL}propertyDisjointWith", "ex:c"),
        ),
        (
            "ex:c",
            "Property is non-simple (defined by a property chain) but declared disjoint with ex:t.",
            (f"{OWL}propertyDisjointWith", "ex:t"),
        ),
    }
    reached = "ex:t a owl:TransitiveProperty ; rdfs:subPropertyOf ex:p . ex:q owl:propertyDisjointWith ex:p ."
    assert found("OWL019", reached) == {
        (
            "ex:p",
            "Property is non-simple (through ex:t, which is transitive) but declared disjoint with ex:q.",
            (f"{OWL}propertyDisjointWith", "ex:q"),
        )
    }


def test_owl019_reports_each_non_simple_member_of_owl_all_disjoint_properties() -> None:
    turtle = "ex:t a owl:TransitiveProperty . ex:c owl:propertyChainAxiom ( ex:a ex:b ) ."
    turtle += " ex:G a owl:AllDisjointProperties ; owl:members ( ex:p ex:t ex:c ) ."
    assert found("OWL019", turtle) == {
        ("ex:G", "owl:AllDisjointProperties contains non-simple property ex:t (transitive).", ("ex:t",)),
        (
            "ex:G",
            "owl:AllDisjointProperties contains non-simple property ex:c (defined by a property chain).",
            ("ex:c",),
        ),
    }


# --- OWL032 / OWL033: owl:disjointUnionOf needs two distinct operands (SS 9.1.4) ------------------------


def test_owl032_reports_a_single_member_disjoint_union() -> None:
    assert found("OWL032", "ex:C owl:disjointUnionOf ( ex:A ) .") == {
        ("ex:C", "owl:disjointUnionOf has a single operand (ex:A).", (f"{OWL}disjointUnionOf", "ex:A"))
    }


def test_owl033_reports_a_disjoint_union_that_repeats_a_member() -> None:
    assert found("OWL033", "ex:C owl:disjointUnionOf ( ex:A ex:B ex:A ) .") == {
        ("ex:C", "owl:disjointUnionOf list repeats a member.", (f"{OWL}disjointUnionOf",))
    }


# --- OWL034-OWL036: a restriction maps to an OWL 2 expression only with one property, constraint, filler --

ON_P = "[] a owl:Restriction ; owl:onProperty ex:p ;"


def _messages(rule: str, turtle: str) -> set[tuple[str, tuple[str, ...]]]:
    return {(message, subject) for _focus, message, subject in found(rule, turtle)}


def test_owl034_reports_both_property_forms_and_several_property_lists() -> None:
    turtle = (
        "[] a owl:Restriction ; owl:onProperty ex:p ; owl:onProperties ( ex:d ), ( ex:e ) ; owl:allValuesFrom ex:R ."
    )
    assert _messages("OWL034", turtle) == {
        ("Restriction has both owl:onProperty and owl:onProperties.", (f"{OWL}onProperty", f"{OWL}onProperties")),
        ("Restriction has more than one owl:onProperties.", (f"{OWL}onProperties", "several")),
    }


def test_owl035_reports_several_constraints_with_their_predicates() -> None:
    assert _messages("OWL035", f"{ON_P} owl:someValuesFrom ex:A ; owl:allValuesFrom ex:B .") == {
        ("Restriction has more than one constraint (owl:allValuesFrom, owl:someValuesFrom).", ("several",))
    }
    assert _messages("OWL035", f"{ON_P} owl:someValuesFrom ex:A, ex:B .") == {
        ("Restriction has more than one constraint (owl:someValuesFrom, owl:someValuesFrom).", ("several",))
    }


def test_owl035_reports_an_owl_has_self_value_that_is_not_true() -> None:
    boolean = "http://www.w3.org/2001/XMLSchema#boolean"
    assert _messages("OWL035", f"{ON_P} owl:hasSelf false .") == {
        (f'owl:hasSelf value "false"^^<{boolean}> is not true.', (f"{OWL}hasSelf", f'"false"^^<{boolean}>'))
    }
    assert _messages("OWL035", f"{ON_P} owl:hasSelf ex:yes .") == {
        ("owl:hasSelf value ex:yes is not true.", (f"{OWL}hasSelf", "ex:yes"))
    }


def test_owl035_names_the_owner_of_a_restriction_with_several_constraints() -> None:
    turtle = "ex:C rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:p ;"
    turtle += " owl:minCardinality 1 ; owl:maxCardinality 2 ] ."
    assert _messages("OWL035", turtle) == {
        (
            "ex:C (restriction on ex:p): Restriction has more than one constraint"
            " (owl:maxCardinality, owl:minCardinality).",
            ("several",),
        )
    }


def test_owl036_reports_a_qualified_cardinality_with_more_than_one_filler() -> None:
    turtle = f"{ON_P} owl:minQualifiedCardinality 1 ; owl:onClass ex:A ; owl:onDataRange xsd:string ."
    assert _messages("OWL036", turtle) == {
        ("Qualified cardinality has more than one filler (owl:onClass, owl:onDataRange).", ("several fillers",))
    }
    assert _messages("OWL036", f"{ON_P} owl:qualifiedCardinality 1 ; owl:onClass ex:A, ex:B .") == {
        ("Qualified cardinality has more than one filler (owl:onClass, owl:onClass).", ("several fillers",))
    }


# --- OWL037: a qualified count never exceeds the unqualified one (Direct Semantics) ----------------------


def test_owl037_compares_the_qualified_lower_bound_with_the_unqualified_upper_bound() -> None:
    turtle = f"{ON_P} owl:maxCardinality 0, 3 ; owl:minQualifiedCardinality 1 ; owl:qualifiedCardinality 2 ;"
    assert _messages("OWL037", turtle + " owl:onClass ex:A .") == {
        ("Qualified lower cardinality bound 2 exceeds unqualified upper bound 0.", ("qualified against unqualified",))
    }
    # Within one group the existing finding stays as it was; the cross-group one comes next to it.
    both = f"{ON_P} owl:cardinality 1 ; owl:qualifiedCardinality 2, 3 ; owl:onClass ex:A ."
    assert _messages("OWL037", both) == {
        ("Qualified lower cardinality bound 3 exceeds unqualified upper bound 1.", ("qualified against unqualified",)),
        ("Lower cardinality bound 3 exceeds upper bound 2.", ("qualified",)),
    }


# --- OWL040: the OWL 2 datatype map's datatypes outside xsd: are datatypes too ---------------------------


def test_owl040_reports_a_non_xsd_datatype_filler_on_an_object_property() -> None:
    turtle = "ex:p a owl:ObjectProperty . [] a owl:Restriction ; owl:onProperty ex:p ; owl:someValuesFrom owl:real ."
    assert _messages("OWL040", turtle) == {
        (f"Restriction on object property ex:p uses datatype filler {OWL}real.", ("ex:p", "filler", f"{OWL}real"))
    }


# --- SHQ008: counts and lengths are literals of datatype xsd:integer (SHACL 4.2, 4.4) --------------------

SH = "http://www.w3.org/ns/shacl#"
XSD = "http://www.w3.org/2001/XMLSchema#"


def _shapes(body: str) -> str:
    return f"ex:S a sh:NodeShape ; sh:targetClass ex:A ; sh:property ex:P . ex:P sh:path ex:p ; {body} ."


def _shq008(body: str) -> set[tuple[str, tuple[str, ...]]]:
    return {(message, subject) for _focus, message, subject in found("SHQ008", "", _shapes(body))}


def test_shq008_reports_a_natural_count_of_a_derived_integer_type() -> None:
    assert _shq008('sh:minCount "1"^^xsd:nonNegativeInteger') == {
        (
            f'sh:minCount value "1"^^<{XSD}nonNegativeInteger> is not of datatype xsd:integer.',
            (f"{SH}minCount", f'"1"^^<{XSD}nonNegativeInteger>'),
        )
    }


def test_shq008_reports_lengths_like_counts() -> None:
    assert _shq008('sh:minLength 1.5 ; sh:maxLength "2"^^xsd:int') == {
        (
            f'sh:minLength value "1.5"^^<{XSD}decimal> is not a non-negative integer.',
            (f"{SH}minLength", f'"1.5"^^<{XSD}decimal>'),
        ),
        (
            f'sh:maxLength value "2"^^<{XSD}int> is not of datatype xsd:integer.',
            (f"{SH}maxLength", f'"2"^^<{XSD}int>'),
        ),
    }
    assert _shq008("sh:minLength ex:two") == {
        ("sh:minLength value ex:two is not a non-negative integer.", (f"{SH}minLength", "ex:two"))
    }


def test_shq008_keeps_the_count_message_for_a_count_that_is_no_natural() -> None:
    assert _shq008("sh:minCount -1") == {
        ("sh:minCount value -1 is not a non-negative integer.", (f"{SH}minCount", f'"-1"^^<{XSD}integer>'))
    }


# --- SHQ011: patterns Python compiles but an XPath regular expression rejects (F&O 5.6.1, XSD F) --------

VALID_XPATH = [
    r"^[a-z]+$",
    r"\d{3}-\d{4}",
    r"[a-z-[aeiou]]+",
    r"(a|b)*?c",
    r"\p{L}+",
    r"\p{IsBasicLatin}",
    r"\P{Nd}",
    r"\$\^",
    r"(a)\1",
    r"(?:ab)+",
    r"[\]\[]",
    r"a{2,}",
    r"a{2,3}?",
    r"[{}]",
    r"[^\s]+",
    r"\i\c*",
    r"^https?://.+$",
    r"\.\-\|\{\}\(\)",
    r"[0-9]{4}-[0-9]{2}",
    r"^*",
    r"[\p{L}\d-[aeiou]]",
    r"",
]
INVALID_XPATH = {
    r"a(?=b)": "the group construct (?= is not XPath",
    r"(?!a)": "the group construct (?! is not XPath",
    r"(?<=a)b": "the group construct (?< is not XPath",
    r"(?i)a": "the group construct (?i is not XPath",
    r"(?P<n>a)": "the group construct (?P is not XPath",
    r"\bword": r"the escape \b is not XPath",
    r"\Ax": r"the escape \A is not XPath",
    r"x\Z": r"the escape \Z is not XPath",
    r"\x41": r"the escape \x is not XPath",
    r"\0": r"the escape \0 is not XPath",
    r"[\1]": r"the escape \1 is not XPath",
    r"[\b]": r"the escape \b is not XPath",
    r"^https?:\/\/": r"the escape \/ is not XPath (write / without the backslash)",
    r"\pL": r"\p is not followed by a {name}",
    r"\p{L": r"\p is not followed by a {name}",
    r"a{": "an unescaped { starts no quantifier",
    r"a{,3}": "an unescaped { starts no quantifier",
    r"{2}": "the quantifier {2} has nothing to repeat",
    r"a|{2}": "the quantifier {2} has nothing to repeat",
    r"({2})": "the quantifier {2} has nothing to repeat",
    r"a}": "an unescaped } outside a character class",
    r"a]": "an unescaped ] outside a character class",
    r"a*+": "the possessive quantifier *+ is not XPath",
    r"a{2}+": "the possessive quantifier {2}+ is not XPath",
    r"a+?+": "the possessive quantifier +?+ is not XPath",
    r"\p{L}**": "the quantifier * follows another quantifier",
}


def test_xpath_regex_problem_accepts_xpath_patterns() -> None:
    assert {text: xpath_regex_problem(text) for text in VALID_XPATH} == dict.fromkeys(VALID_XPATH)


def test_xpath_regex_problem_names_the_first_construct_xpath_rejects() -> None:
    assert {text: xpath_regex_problem(text) for text in INVALID_XPATH} == INVALID_XPATH


def test_xpath_regex_problem_leaves_hyphen_placement_to_python() -> None:
    # XSD 1.0 and 1.1 disagree on "-": not judged.  (Since the SHQ specification, a [ or a leading ] inside a
    # class, which both reject, is: see tests/test_shq_specification.py.)
    assert [xpath_regex_problem(text) for text in (r"[a-]", r"[a-z-]", r"[-a]")] == [None] * 3


def _shq011(body: str) -> set[str]:
    return {message for _focus, message, _subject in found("SHQ011", "", _shapes(body))}


def test_shq011_reports_a_pattern_python_compiles_but_xpath_rejects() -> None:
    assert _shq011(r'sh:pattern "^https?:\\/\\/"') == {
        r"sh:pattern is not an XPath regular expression: the escape \/ is not XPath (write / without the backslash)."
    }
    assert _shq011(r'sh:pattern "a b{" ; sh:flags "x"') == {
        "sh:pattern is not an XPath regular expression: an unescaped { starts no quantifier."
    }


def test_shq011_gives_a_pattern_python_rejects_only_its_compile_finding() -> None:
    (message,) = _shq011(r'sh:pattern "(\\bword"')
    assert message.startswith("sh:pattern does not compile: missing )")


# --- the user-visible effect: CI now fails where the W3C specifications make the input invalid ----------

GAPS_ONTOLOGY = """
@prefix ex: <https://example.test/gaps#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
ex: a owl:Ontology .
ex:partOf a owl:ObjectProperty, owl:TransitiveProperty .
ex:hasPart a owl:ObjectProperty .
ex:Wheel a owl:Class ;
    rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:partOf ; owl:maxCardinality 1 ] .
ex:Car a owl:Class ; rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:hasPart ;
    owl:someValuesFrom ex:Wheel ; owl:allValuesFrom ex:Wheel ] .
ex:Label a owl:Class ;
    rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:hasPart ; owl:someValuesFrom rdf:langString ] .
ex:engine a skos:Concept ; skos:related ex:vehicle ; skos:broadMatch ex:vehicle .
ex:vehicle a skos:Concept .
"""
GAPS_SHAPES = r"""
@prefix ex: <https://example.test/gaps#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
ex:CarShape a sh:NodeShape ; sh:targetClass ex:Car ;
    sh:property [ sh:path ex:homepage ; sh:maxCount "1"^^xsd:nonNegativeInteger ; sh:pattern "^https?:\\/\\/" ] .
"""


def test_fail_on_error_now_fails_on_the_closed_gaps(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Before the gaps closed this exits 0 with no finding (checked on the commit that pinned the old findings).
    ontology, shapes = tmp_path / "ontology.ttl", tmp_path / "shapes.ttl"
    ontology.write_text(GAPS_ONTOLOGY, encoding="utf-8")
    shapes.write_text(GAPS_SHAPES, encoding="utf-8")
    rules = "OWL019,OWL035,OWL040,SKOS009,SHQ008,SHQ011"
    argv = [str(ontology), "--shapes", str(shapes), "--select", rules, "--fail-on", "error", "--format", "json"]
    assert main(argv) == 1
    findings = json.loads(capsys.readouterr().out)["findings"]
    assert sorted((f["rule"], f["severity"]) for f in findings) == [
        (rule, "error") for rule in sorted(rules.split(","))
    ]
