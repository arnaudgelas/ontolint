"""The SKOS family specification (see the ``skos`` and ``skos_integrity`` docstrings).

One section per rule: each pins a condition, an exclusion or a known gap of the rule's specification, with
the standard it rests on.  SKOS is the SKOS Reference of 2009-08-18 and RDF 1.1 Concepts the Recommendation
of 2014-02-25.  ``test_spec_skos_errors.py`` holds the exact messages of SKOS001, SKOS002 and SKOS009.
"""

from __future__ import annotations

from rule_harness import graph

from ontolint import Linter

NS = "https://example.test/onto#"
SCHEME = "ex:s a skos:ConceptScheme ."


def _foci(rule: str, turtle: str) -> list[str]:
    result = Linter(graph(turtle)).execute([rule])
    return sorted(f.focus.removeprefix(NS) for f in result.findings)


# --- defect fixed by this specification ----------------------------------------------------------------


def test_skos020_counts_one_rdf_literal_once() -> None:
    # RDF 1.1 Concepts 3.3: "1" and "1"^^xsd:string are one RDF term, so two concepts holding them share a notation.
    two = 'ex:a skos:inScheme ex:s ; skos:notation "1" . ex:b skos:inScheme ex:s ; skos:notation "1"^^xsd:string .'
    typed = "a skos:Concept ;"
    both = two.replace("ex:a ", f"ex:a {typed} ").replace("ex:b ", f"ex:b {typed} ")
    assert _foci("SKOS020", both) == ["a", "b"]
    # Another datatype is another term.
    assert _foci("SKOS020", both.replace("xsd:string", "xsd:token")) == []


def _in(*names: str) -> str:
    """Concepts of the scheme ``ex:s`` through an asserted ``skos:inScheme``."""
    return " ".join(f"ex:{n} a skos:Concept ; skos:inScheme ex:s ." for n in names)


# --- SKOS001 (SKOS Reference 5.4 S14; scope decision of #181 kept) --------------------------------------


def test_skos001_one_finding_per_concept_and_language_and_a_deprecated_concept_is_judged() -> None:
    assert _foci("SKOS001", 'ex:c a skos:Concept ; skos:prefLabel "a"@en, "b"@en, "c"@fr, "d"@fr .') == ["c", "c"]
    assert _foci("SKOS001", 'ex:c a skos:Concept ; skos:prefLabel "a"@en, "b"@fr .') == []
    assert _foci("SKOS001", 'ex:c a skos:Concept ; owl:deprecated true ; skos:prefLabel "a"@en, "b"@en .') == ["c"]


def test_skos001_an_explicit_und_tag_joins_the_untagged_labels() -> None:
    assert _foci("SKOS001", 'ex:c a skos:Concept ; skos:prefLabel "a", "b"@und .') == ["c"]
    assert _foci("SKOS001", 'ex:c a skos:Concept ; skos:prefLabel "a", "a"^^xsd:string .') == []
    assert _foci("SKOS001", 'ex:c a skos:Concept ; skos:prefLabel "a", "a"@und .') == ["c"]  # two RDF terms


def test_skos001_scope_is_the_owned_asserted_concept_only() -> None:
    # S14 binds any resource ("A resource has no more than one value of skos:prefLabel per language tag").  The
    # decision on widening the scope (#181, "Count the widened SKOS001 scope") is not taken, so the rule keeps
    # reading owned resources explicitly typed skos:Concept: these three are known gaps, pinned as they are.
    two = 'skos:prefLabel "a"@en, "b"@en .'
    assert _foci("SKOS001", f"ex:c a owl:Class ; {two}") == []  # gap: not a concept
    assert _foci("SKOS001", f"ex:s a skos:ConceptScheme ; {two}") == []  # gap: a scheme
    assert _foci("SKOS001", f"ex:Sub rdfs:subClassOf skos:Concept . ex:c a ex:Sub ; {two}") == []  # gap: subclass
    assert _foci("SKOS001", f"ex:c a skos:Concept ; {two}") == ["c"]


def test_skos001_a_sub_property_of_preflabel_is_not_a_second_preflabel() -> None:
    body = 'ex:p rdfs:subPropertyOf skos:prefLabel . ex:c a skos:Concept ; skos:prefLabel "a"@en ; ex:p "b"@en .'
    assert _foci("SKOS001", body) == []  # gap: S14 holds for the entailed property


def test_skos001_and_lex003_both_report_the_same_concept() -> None:
    body = 'ex:c a skos:Concept ; skos:prefLabel "a"@en, "b"@en .'
    assert _foci("SKOS001", body) == _foci("LEX003", body) == ["c"]


# --- SKOS002 (S13) and the label overlap with LEX015 (#155 undecided) ----------------------------------


def test_skos002_pairs_prefalt_prefhidden_and_althidden() -> None:
    assert _foci("SKOS002", 'ex:c skos:prefLabel "a"@en ; skos:altLabel "a"@en .') == ["c"]
    assert _foci("SKOS002", 'ex:c skos:prefLabel "a"@en ; skos:hiddenLabel "a"@en .') == ["c"]
    assert _foci("SKOS002", 'ex:c skos:altLabel "a"@en ; skos:hiddenLabel "a"@en .') == ["c"]
    assert _foci("SKOS002", 'ex:c skos:prefLabel "a"@en ; skos:altLabel "a"@en ; skos:hiddenLabel "a"@en .') == ["c"]


def test_skos002_deprecated_owners_and_blank_nodes_are_judged_and_other_resources_are_not() -> None:
    assert _foci("SKOS002", 'ex:c owl:deprecated true ; skos:altLabel "a" ; skos:hiddenLabel "a" .') == ["c"]
    assert len(_foci("SKOS002", '[] skos:altLabel "a" ; skos:hiddenLabel "a" .')) == 1


def test_skos002_compares_exact_terms_so_case_and_whitespace_are_not_folded() -> None:
    # S13 disjointness is on values: "a" and "A" are two values.  LEX015 folds both.
    assert _foci("SKOS002", 'ex:c skos:altLabel "a"@en ; skos:hiddenLabel "A"@en .') == []
    assert _foci("SKOS002", 'ex:c skos:altLabel "a b"@en ; skos:hiddenLabel "a  b"@en .') == []
    assert _foci("SKOS002", 'ex:c skos:altLabel "a"@en ; skos:hiddenLabel "a "@en .') == []
    assert _foci("SKOS002", 'ex:c skos:altLabel "a"@en ; skos:hiddenLabel "a"@EN .') == ["c"]


def test_label_overlap_of_skos002_and_lex015_known_gap_of_155() -> None:
    # Gap (#155, SKOS Reference S13): an altLabel and a hiddenLabel that differ in case or inner whitespace are
    # disjoint by S13 only as exact values; LEX015 omits that pair and SKOS002 compares exactly, so no rule
    # reports them.  Pinned as it is; the decision is the maintainer's.
    near = 'ex:c a owl:Class ; skos:altLabel "a b"@en ; skos:hiddenLabel "A  B"@en .'
    assert _foci("SKOS002", near) == []
    assert _foci("LEX015", near) == []
    # The exact pair is SKOS002's alone; the folded pair with rdfs:label or skos:prefLabel is LEX015's alone.
    exact = 'ex:c a owl:Class ; skos:altLabel "a"@en ; skos:hiddenLabel "a"@en .'
    assert (_foci("SKOS002", exact), _foci("LEX015", exact)) == (["c"], [])
    folded = 'ex:c a owl:Class ; skos:prefLabel "a b"@en ; skos:altLabel "A  B"@en .'
    assert (_foci("SKOS002", folded), _foci("LEX015", folded)) == ([], ["c"])
    both = 'ex:c a owl:Class ; skos:prefLabel "a"@en ; skos:altLabel "a"@en .'
    assert (_foci("SKOS002", both), _foci("LEX015", both)) == (["c"], ["c"])


# --- SKOS003 ----------------------------------------------------------------------------------------------


def test_skos003_one_finding_per_component_on_asserted_broader_between_concepts() -> None:
    assert _foci("SKOS003", "ex:a a skos:Concept ; skos:broader ex:b . ex:b a skos:Concept ; skos:broader ex:a .") == [
        "a"
    ]
    three = "ex:a skos:broader ex:b . ex:b skos:broader ex:c . ex:c skos:broader ex:a ."
    assert _foci("SKOS003", " ".join(f"ex:{n} a skos:Concept ." for n in "abc") + three) == ["a"]
    assert _foci("SKOS003", "ex:a a skos:Concept ; skos:broader ex:a .") == ["a"]


def test_skos003_reads_neither_narrower_nor_transitive_nor_untyped_nodes() -> None:
    cycle = "ex:a a skos:Concept ; {p} ex:b . ex:b a skos:Concept ; {p} ex:a ."
    assert _foci("SKOS003", cycle.format(p="skos:narrower")) == []  # gap: the inverse is not read
    assert _foci("SKOS003", cycle.format(p="skos:broaderTransitive")) == []
    assert _foci("SKOS003", "ex:a skos:broader ex:b . ex:b skos:broader ex:a .") == []  # not typed concepts


# --- SKOS004 ----------------------------------------------------------------------------------------------


def test_skos004_a_concept_without_a_literal_label() -> None:
    assert _foci("SKOS004", "ex:c a skos:Concept .") == ["c"]
    assert _foci("SKOS004", 'ex:c a skos:Concept ; skos:altLabel "c" ; skos:hiddenLabel "c" .') == ["c"]
    assert _foci("SKOS004", "ex:c a skos:Concept ; skos:prefLabel ex:d .") == ["c"]  # not a literal
    assert _foci("SKOS004", 'ex:c a skos:Concept ; rdfs:label "c" .') == []
    assert _foci("SKOS004", 'ex:c a skos:Concept ; skos:prefLabel "" .') == []  # SKOS014's


def test_skos004_exempts_retired_concepts_and_reads_only_concepts() -> None:
    assert _foci("SKOS004", "ex:c a skos:Concept ; owl:deprecated true .") == []
    assert _foci("SKOS004", 'ex:c a skos:Concept ; skos:historyNote "gone" .') == []
    assert _foci("SKOS004", "ex:c a skos:Concept ; owl:deprecated false .") == ["c"]
    assert _foci("SKOS004", "ex:c a skos:Collection .") == []


# --- SKOS005 ----------------------------------------------------------------------------------------------


def test_skos005_needs_an_asserted_in_scheme() -> None:
    assert _foci("SKOS005", "ex:c a skos:Concept .") == ["c"]
    assert _foci("SKOS005", _in("c")) == []
    assert _foci("SKOS005", "ex:c a skos:Collection .") == []


def test_skos005_does_not_read_top_concept_of() -> None:
    # Gap (SKOS Reference): skos:topConceptOf is a sub-property of skos:inScheme and skos:hasTopConcept is its
    # inverse, so the concept is in a scheme; SKOS015, SKOS011 and SKOS019 read them, SKOS005 does not.
    assert _foci("SKOS005", "ex:c a skos:Concept ; skos:topConceptOf ex:s .") == ["c"]
    assert _foci("SKOS005", "ex:s skos:hasTopConcept ex:c . ex:c a skos:Concept .") == ["c"]


# --- SKOS006 ----------------------------------------------------------------------------------------------


def test_skos006_top_concept_of_with_a_broader_value() -> None:
    assert _foci("SKOS006", "ex:c skos:topConceptOf ex:s ; skos:broader ex:d .") == ["c"]
    assert _foci("SKOS006", "ex:c skos:topConceptOf ex:s, ex:t ; skos:broader ex:d .") == ["c", "c"]
    assert _foci("SKOS006", "ex:c skos:topConceptOf ex:s .") == []
    assert _foci("SKOS006", "ex:c skos:broader ex:d .") == []


def test_skos006_does_not_read_the_inverse_properties() -> None:
    # Gap: skos:hasTopConcept is the inverse of skos:topConceptOf and skos:narrower of skos:broader.
    assert _foci("SKOS006", "ex:s skos:hasTopConcept ex:c . ex:c skos:broader ex:d .") == []
    assert _foci("SKOS006", "ex:c skos:topConceptOf ex:s . ex:d skos:narrower ex:c .") == []


# --- SKOS007, SKOS008 (S9, S29, S37) ----------------------------------------------------------------------


def test_skos007_concept_and_scheme_on_one_owned_iri() -> None:
    assert _foci("SKOS007", "ex:c a skos:Concept, skos:ConceptScheme .") == ["c"]
    assert _foci("SKOS007", "ex:c a skos:Concept . ex:s a skos:ConceptScheme .") == []
    assert _foci("SKOS007", "ex:Sub rdfs:subClassOf skos:Concept . ex:c a ex:Sub, skos:ConceptScheme .") == []  # gap
    assert _foci("SKOS007", "[] a skos:Concept, skos:ConceptScheme .") == []


def test_skos007_a_deprecated_resource_is_judged() -> None:
    assert _foci("SKOS007", "ex:c a skos:Concept, skos:ConceptScheme ; owl:deprecated true .") == ["c"]


def test_skos008_collections_are_disjoint_from_concepts_and_schemes_but_may_have_members() -> None:
    assert _foci("SKOS008", "ex:k a skos:Collection, skos:Concept .") == ["k"]
    assert _foci("SKOS008", "ex:k a skos:OrderedCollection, skos:ConceptScheme .") == ["k"]
    assert _foci("SKOS008", "ex:k a skos:Collection ; skos:member ex:c . ex:c a skos:Concept .") == []
    assert _foci("SKOS008", "[] a skos:Collection, skos:Concept .") == []


# --- SKOS009 (S27, S41) and SKOS010 -----------------------------------------------------------------------


def test_skos009_boundary_between_a_conflict_and_a_sibling() -> None:
    assert _foci("SKOS009", "ex:a skos:broader ex:b ; skos:related ex:b .") == ["a"]
    assert _foci("SKOS009", "ex:b skos:narrower ex:a . ex:b skos:related ex:a .") == ["a"]
    assert _foci("SKOS009", "ex:a skos:broader ex:p . ex:b skos:broader ex:p . ex:a skos:related ex:b .") == []
    assert _foci("SKOS009", "ex:a skos:broader ex:b ; skos:closeMatch ex:b .") == []


def test_skos010_only_a_reflexive_related_of_an_owned_iri() -> None:
    assert _foci("SKOS010", "ex:a skos:related ex:a .") == ["a"]
    assert _foci("SKOS010", "ex:a skos:related ex:b .") == []
    assert _foci("SKOS010", "ex:a skos:relatedMatch ex:a .") == []  # gap: no rule reports a reflexive relatedMatch


# --- SKOS011, SKOS019 --------------------------------------------------------------------------------------


def test_skos011_mapping_between_concepts_that_share_a_scheme() -> None:
    assert _foci("SKOS011", _in("a", "b") + " ex:a skos:exactMatch ex:b .") == ["a"]
    assert _foci("SKOS011", _in("a") + " ex:b a skos:Concept ; skos:inScheme ex:t . ex:a skos:exactMatch ex:b .") == []
    assert _foci("SKOS011", _in("a") + " ex:a skos:exactMatch ex:b .") == []  # no scheme for b
    assert _foci("SKOS011", _in("a", "b") + " ex:a skos:related ex:b .") == []  # not a mapping property


def test_skos011_reads_top_concept_of_and_has_top_concept_as_membership() -> None:
    assert _foci("SKOS011", "ex:a skos:topConceptOf ex:s . ex:s skos:hasTopConcept ex:b . ex:a skos:closeMatch ex:b .") == [
        "a"
    ]


def test_skos019_hierarchy_across_schemes_needs_both_schemes_and_no_shared_one() -> None:
    assert _foci("SKOS019", "ex:a skos:inScheme ex:s ; skos:broader ex:b . ex:b skos:inScheme ex:t .") == ["a"]
    assert _foci("SKOS019", "ex:a skos:inScheme ex:s, ex:t ; skos:broader ex:b . ex:b skos:inScheme ex:t .") == []
    assert _foci("SKOS019", "ex:a skos:inScheme ex:s ; skos:broader ex:b .") == []
    assert _foci("SKOS019", "ex:a skos:inScheme ex:s ; skos:related ex:b . ex:b skos:inScheme ex:t .") == []


# --- SKOS012 (S46, S43) ------------------------------------------------------------------------------------


def test_skos012_exact_match_with_another_mapping_in_either_direction() -> None:
    assert _foci("SKOS012", "ex:a skos:exactMatch ex:b ; skos:broadMatch ex:b .") == ["a"]
    assert _foci("SKOS012", "ex:a skos:exactMatch ex:b . ex:b skos:narrowMatch ex:a .") == ["a"]
    assert _foci("SKOS012", "ex:a skos:exactMatch ex:b ; skos:closeMatch ex:b .") == []
    assert _foci("SKOS012", "ex:a skos:exactMatch ex:b . ex:b skos:exactMatch ex:c . ex:a skos:broadMatch ex:c .") == []


# --- SKOS013, SKOS014 (S12; whitespace boundary) ---------------------------------------------------------


def test_skos013_labels_that_are_not_string_literals_of_an_owned_subject() -> None:
    assert _foci("SKOS013", 'ex:c skos:prefLabel "a"@en, "b", "c"^^xsd:string .') == []
    assert _foci("SKOS013", 'ex:c skos:altLabel "1"^^xsd:integer .') == ["c"]
    assert _foci("SKOS013", "ex:c skos:hiddenLabel ex:d .") == ["c"]


def test_skos014_empty_or_padded_string_labels_at_the_whitespace_boundary() -> None:
    assert _foci("SKOS014", 'ex:c skos:prefLabel "" .') == ["c"]
    assert _foci("SKOS014", 'ex:c skos:altLabel "a\\n" .') == ["c"]
    assert _foci("SKOS014", 'ex:c skos:altLabel "a\\u00a0" .') == ["c"]  # any Unicode white space
    assert _foci("SKOS014", 'ex:c skos:altLabel "a  b" .') == []  # inner whitespace is not read
    assert _foci("SKOS014", 'ex:c skos:altLabel "a" .') == []
    assert _foci("SKOS014", 'ex:c skos:altLabel " "^^xsd:token .') == []  # SKOS013's
    assert _foci("SKOS014", 'ex:c owl:deprecated true ; skos:altLabel " a" .') == ["c"]


# --- SKOS015 -----------------------------------------------------------------------------------------------


def test_skos015_a_scheme_with_members_and_no_top_concept() -> None:
    assert _foci("SKOS015", f"{SCHEME} ex:c skos:inScheme ex:s .") == ["s"]
    assert _foci("SKOS015", SCHEME) == []  # empty
    assert _foci("SKOS015", f"{SCHEME} ex:c skos:inScheme ex:s ; skos:topConceptOf ex:s .") == []
    assert _foci("SKOS015", f"{SCHEME} ex:s skos:hasTopConcept ex:c .") == []
    assert _foci("SKOS015", "ex:c skos:inScheme ex:s .") == []  # ex:s is not typed a scheme


# --- SKOS016 -----------------------------------------------------------------------------------------------


def test_skos016_a_literal_value_of_a_relation_not_of_member() -> None:
    assert _foci("SKOS016", 'ex:c skos:broader "p" ; skos:related "q" .') == ["c", "c"]
    assert _foci("SKOS016", 'ex:k skos:member "x" ; skos:memberList "y" .') == []
    assert _foci("SKOS016", 'ex:p rdfs:subPropertyOf skos:broader . ex:c ex:p "x" .') == []
    assert _foci("SKOS016", '[] skos:broader "x" .') == []


# --- SKOS017 -----------------------------------------------------------------------------------------------


def test_skos017_an_owned_target_without_any_triple() -> None:
    assert _foci("SKOS017", "ex:c a skos:Concept ; skos:broader ex:missing .") == ["c"]
    assert _foci("SKOS017", "ex:c a skos:Concept ; skos:broader ex:d . ex:d a skos:Concept .") == []
    assert _foci("SKOS017", "ex:c a skos:Concept ; skos:broader <http://elsewhere.test/x> .") == []
    assert _foci("SKOS017", "ex:c a skos:Concept ; skos:inScheme ex:s .") == []  # inScheme is not read: gap
    assert _foci("SKOS017", "ex:c a skos:Concept ; skos:broader [] .") == []


# --- SKOS018 -----------------------------------------------------------------------------------------------


def test_skos018_a_shortcut_through_one_intermediate_concept_only() -> None:
    assert _foci("SKOS018", "ex:a skos:broader ex:b, ex:c . ex:b skos:broader ex:c .") == ["a"]
    assert _foci("SKOS018", "ex:a skos:broader ex:b, ex:d . ex:b skos:broader ex:c . ex:c skos:broader ex:d .") == []
    assert _foci("SKOS018", "ex:a skos:broader ex:b, ex:c . ex:c skos:narrower ex:b .") == []
    assert _foci("SKOS018", "ex:a skos:broader ex:b . ex:b skos:broader ex:a .") == []


# --- SKOS020, SKOS021 --------------------------------------------------------------------------------------


def test_skos020_boundaries_of_a_shared_notation() -> None:
    both = _in("a", "b")
    assert _foci("SKOS020", both + ' ex:a skos:notation "1" . ex:b skos:notation "1" .') == ["a", "b"]
    assert _foci("SKOS020", both + ' ex:a skos:notation "1" . ex:b skos:notation "2" .') == []
    assert _foci("SKOS020", both + ' ex:a skos:notation "1" . ex:b skos:notation "1"^^ex:t .') == []
    assert _foci("SKOS020", both + ' ex:a skos:notation "1" ; owl:deprecated true . ex:b skos:notation "1" .') == []
    # Gap: a language tag is not read, so "1" and "1"@en are one notation here and two RDF terms.
    assert _foci("SKOS020", both + ' ex:a skos:notation "1" . ex:b skos:notation "1"@en .') == ["a", "b"]


def test_skos021_boundaries_of_a_shared_preferred_label() -> None:
    both = _in("a", "b")
    assert _foci("SKOS021", both + ' ex:a skos:prefLabel "x"@en . ex:b skos:prefLabel " X "@EN .') == ["a", "b"]
    assert _foci("SKOS021", both + ' ex:a skos:prefLabel "x"@en . ex:b skos:prefLabel "x"@fr .') == []
    assert _foci("SKOS021", both + ' ex:a skos:prefLabel "x" . ex:b skos:prefLabel "x"@en .') == []
    assert _foci("SKOS021", both + ' ex:a skos:prefLabel "x"@en . ex:b skos:prefLabel "" .') == []
    # Gap: inner whitespace is not collapsed (LEX004 does not either, LEX015 does).
    assert _foci("SKOS021", both + ' ex:a skos:prefLabel "x y"@en . ex:b skos:prefLabel "x  y"@en .') == []
