"""Exact findings for the coverage gaps closed in the OWL, SHACL and SKOS rules (TODO.md, P1 audit item).

Each gap was a stated exclusion: a construct the W3C specification rejects or makes inconsistent that the rule
left silent.  These tests pin the focus, message and subject of each new condition; the rule cases
(``tests/rule_cases``) carry the positive and negative fixtures, and ``test_coverage_gap_stability`` that the
findings reported before stay as they were.  ``ex:`` stands for the cases' base IRI.
"""

from __future__ import annotations

from rule_harness import BASE, graph

from ontolint import Linter

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
