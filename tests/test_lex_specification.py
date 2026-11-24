"""The LEX family specification (see the ``lexical``, ``lexical_quality``, ``iri_lexical_extras`` and
``annotation_whitespace`` docstrings).

One section per rule: each pins a condition, an exclusion or a known gap of the rule's specification, with
the standard it rests on.  SKOS is the SKOS Reference of 2009-08-18, RDFS the RDF Schema 1.1 Recommendation,
RDF 1.1 Concepts the Recommendation of 2014-02-25 and RFC 4647 the language-tag matching standard.
"""

from __future__ import annotations

from rule_harness import graph

from ontolint import Linter
from ontolint.policy import Policy

NS = "https://example.test/onto#"
OIO = "http://www.geneontology.org/formats/oboInOwl#"


def _messages(rule: str, turtle: str, *languages: str) -> list[str]:
    policy = Policy(languages=languages) if languages else Policy()
    result = Linter(graph(turtle), policy=policy).execute([rule])
    return sorted(f.message for f in result.findings)


def _foci(rule: str, turtle: str, *languages: str) -> list[str]:
    policy = Policy(languages=languages) if languages else Policy()
    result = Linter(graph(turtle), policy=policy).execute([rule])
    return sorted(f.focus.removeprefix(NS) for f in result.findings)


# --- defects fixed by this specification ---------------------------------------------------------------


def test_lex008_a_regional_label_satisfies_the_language_range() -> None:
    # RFC 4647 3.3.1 (basic filtering): the range "en" matches the tag "en-GB"; LEX022 and LEX023 already say so.
    assert _foci("LEX008", 'ex:A a owl:Class ; rdfs:label "A"@en-GB .', "en") == []
    assert _foci("LEX008", 'ex:A a owl:Class ; rdfs:label "A"@EN-gb .', "en") == []
    # A range does not match a shorter tag, nor a tag that merely starts with the same letters.
    assert _foci("LEX008", 'ex:A a owl:Class ; rdfs:label "A"@en .', "en-gb") == ["A"]
    assert _foci("LEX008", 'ex:A a owl:Class ; rdfs:label "A"@eng .', "en") == ["A"]


def test_lex003_counts_one_rdf_literal_once() -> None:
    # RDF 1.1 Concepts 3.3: a simple literal is an xsd:string literal, so "A" and "A"^^xsd:string are one
    # RDF term, and SKOS S14 allows one skos:prefLabel per language tag.
    assert _foci("LEX003", 'ex:A a owl:Class ; rdfs:label "A", "A"^^xsd:string .') == []
    assert _foci("LEX003", 'ex:A a owl:Class ; rdfs:label "A", "B"^^xsd:string .') == ["A"]


def test_lex024_counts_one_rdf_literal_once() -> None:
    assert _foci("LEX024", 'ex:A a owl:Class ; skos:definition "x", "x"^^xsd:string .') == []
    assert _foci("LEX024", 'ex:A a owl:Class ; skos:definition "x", "y"^^xsd:string .') == ["A"]


def test_lex003_and_lex024_keep_literals_of_another_datatype_apart() -> None:
    # Only xsd:string and rdf:langString are implied by the plain form; "1" and "1"^^xsd:integer are two terms.
    assert _foci("LEX003", 'ex:A a owl:Class ; rdfs:label "1", "1"^^xsd:integer .') == ["A"]
    assert _foci("LEX024", 'ex:A a owl:Class ; skos:definition "1", "1"^^xsd:integer .') == ["A"]


# --- LEX001, LEX002: a term without label or definition (RDFS 5.4.1 and 5.4.2 make both optional) --------


def test_lex001_a_blank_label_is_a_label_and_a_non_literal_is_not() -> None:
    assert _foci("LEX001", 'ex:A a owl:Class ; rdfs:label "" .') == []
    assert _foci("LEX001", "ex:A a owl:Class ; rdfs:label ex:B .") == ["A"]


def test_lex001_does_not_count_alt_or_hidden_labels_as_labels() -> None:
    # SKOS 5.3 S11 puts them below rdfs:label, but they never name a term.
    assert _foci("LEX001", 'ex:A a owl:Class ; skos:altLabel "A" ; skos:hiddenLabel "a" .') == ["A"]


def test_lex001_exempts_a_deprecated_term_but_lex002_does_not() -> None:
    assert _foci("LEX001", "ex:A a owl:Class ; owl:deprecated true .") == []
    assert _foci("LEX002", "ex:A a owl:Class ; owl:deprecated true .") == ["A"]


def test_lex002_any_value_counts_even_blank_or_not_a_literal() -> None:
    assert _foci("LEX002", 'ex:A a owl:Class ; rdfs:comment "" .') == []
    assert _foci("LEX002", "ex:A a owl:Class ; rdfs:comment ex:B .") == []


def test_lex002_a_change_note_is_no_documentation() -> None:
    assert _foci("LEX002", 'ex:A a owl:Class ; skos:changeNote "c" ; skos:historyNote "h" ; skos:example "e" .') == [
        "A"
    ]


# --- LEX003 (SKOS 5.4 S14) ------------------------------------------------------------------------------


def test_lex003_one_preferred_label_per_language_tag() -> None:
    assert _foci("LEX003", 'ex:A a owl:Class ; skos:prefLabel "a"@en, "b"@en .') == ["A"]
    assert _foci("LEX003", 'ex:A a owl:Class ; skos:prefLabel "a"@en, "b"@fr .') == []
    assert _foci("LEX003", 'ex:A a owl:Class ; skos:prefLabel "a"@en, "b"@EN .') == ["A"]


def test_lex003_an_alt_label_is_not_a_second_preferred_label() -> None:
    assert _foci("LEX003", 'ex:A a owl:Class ; skos:prefLabel "a"@en ; skos:altLabel "b"@en .') == []


# --- LEX004 -----------------------------------------------------------------------------------------------


def test_lex004_compares_case_and_inner_whitespace_as_lex015_lex016_lex017_and_lex020_do() -> None:
    # Decision of #155 (item 1): LEX004 folds case and collapses inner whitespace, as the other label comparisons do.
    both = 'ex:A a owl:Class ; rdfs:label "x y" . ex:B a owl:Class ; rdfs:label "x  y" .'
    assert _foci("LEX004", both) == ["A"]
    assert _foci("LEX004", both.replace("x  y", "x y")) == ["A"]
    assert _foci("LEX004", 'ex:A a owl:Class ; rdfs:label "Heart" . ex:B a owl:Class ; rdfs:label "heart" .') == ["A"]
    assert _foci("LEX004", 'ex:A a owl:Class ; rdfs:label "Heart" . ex:B a owl:Class ; rdfs:label "hearts" .') == []


def test_lex004_a_group_of_variants_names_the_least_spelling_and_exact_duplicates_keep_their_label() -> None:
    variants = 'ex:A a owl:Class ; rdfs:label "heart" . ex:B a owl:Class ; rdfs:label "Heart" .'
    assert [m.split(" for ")[0] for m in _messages("LEX004", variants)] == ["Duplicate label 'Heart'@und"]
    exact = 'ex:A a owl:Class ; rdfs:label "Heart" . ex:B a owl:Class ; rdfs:label "Heart" .'
    assert [m.split(" for ")[0] for m in _messages("LEX004", exact)] == ["Duplicate label 'Heart'@und"]


def test_lex004_languages_and_collections_are_apart() -> None:
    assert _foci("LEX004", 'ex:A a owl:Class ; rdfs:label "x"@en . ex:B a owl:Class ; rdfs:label "x"@fr .') == []
    assert _foci("LEX004", 'ex:A a skos:Collection ; rdfs:label "x" . ex:B a skos:Collection ; rdfs:label "x" .') == []


# --- LEX005 -----------------------------------------------------------------------------------------------


def test_lex005_blank_and_padded_labels_but_not_alt_labels() -> None:
    assert _foci("LEX005", 'ex:A a owl:Class ; rdfs:label " " .') == ["A"]
    assert _foci("LEX005", 'ex:A a owl:Class ; rdfs:label "a " .') == ["A"]
    assert _foci("LEX005", 'ex:A a owl:Class ; rdfs:label "a" ; skos:altLabel " b" .') == []


# --- LEX006 -----------------------------------------------------------------------------------------------


def test_lex006_untagged_beside_tagged_main_labels() -> None:
    assert _foci("LEX006", 'ex:A a owl:Class ; rdfs:label "x", "y"@en .') == ["A"]
    assert _foci("LEX006", 'ex:A a owl:Class ; rdfs:label "x"@fr, "y"@en .') == []
    assert _foci("LEX006", 'ex:A a owl:Class ; rdfs:label "x" ; skos:altLabel "y"@en .') == []


# --- LEX007 -----------------------------------------------------------------------------------------------


def test_lex007_needs_two_styles_and_a_sample() -> None:
    names = ["a_b", "c_d", "eF", "gH"]
    assert _foci("LEX007", " ".join(f"ex:{n} a owl:Class ." for n in names)) == ["(vocabulary)"]
    assert _foci("LEX007", " ".join(f"ex:{n} a owl:Class ." for n in names[:3])) == []
    assert _foci("LEX007", " ".join(f"ex:{n} a owl:Class ." for n in ("a_b", "c_d", "e", "f"))) == []


# --- LEX008 (RFC 4647 3.3.1) ------------------------------------------------------------------------------


def test_lex008_an_untagged_label_satisfies_no_language_and_nothing_is_asked_without_a_policy() -> None:
    assert _foci("LEX008", 'ex:A a owl:Class ; rdfs:label "A" .', "en") == ["A"]
    assert _foci("LEX008", 'ex:A a owl:Class ; rdfs:label "A" .') == []


def test_lex008_reports_each_missing_language() -> None:
    assert _messages("LEX008", 'ex:A a owl:Class ; rdfs:label "A"@en .', "en", "fr", "de") == [
        "Missing preferred label in language de.",
        "Missing preferred label in language fr.",
    ]


# --- LEX009 -----------------------------------------------------------------------------------------------


def _capitalised(count: int, odd: str) -> str:
    rows = [f'ex:c{i} a owl:Class ; rdfs:label "Term {i}" .' for i in range(count - 1)]
    return " ".join([*rows, f'ex:odd a owl:Class ; rdfs:label "{odd}" .'])


def test_lex009_the_minority_case_of_a_clear_majority_and_a_sample() -> None:
    assert _foci("LEX009", _capitalised(10, "term")) == ["odd"]
    assert _foci("LEX009", _capitalised(9, "term")) == []  # under MINIMUM_CAPITALIZATION_SAMPLE
    assert _foci("LEX009", _capitalised(10, "Term")) == []


def test_lex009_reads_only_rdfs_label() -> None:
    rows = " ".join(f'ex:c{i} a owl:Class ; rdfs:label "Term {i}" .' for i in range(9))
    assert _foci("LEX009", rows + ' ex:odd a owl:Class ; skos:prefLabel "term" .') == []


# --- LEX010 -----------------------------------------------------------------------------------------------


def test_lex010_camel_or_underscore_identifier_only() -> None:
    assert _foci("LEX010", 'ex:hasPart a owl:ObjectProperty ; rdfs:label "hasPart" .') == ["hasPart"]
    assert _foci("LEX010", 'ex:has_part a owl:ObjectProperty ; rdfs:label "has_part" .') == ["has_part"]
    assert _foci("LEX010", 'ex:cell a owl:Class ; rdfs:label "cell" .') == []
    assert _foci("LEX010", 'ex:hasPart a owl:ObjectProperty ; rdfs:label "has part" .') == []


def test_lex010_collapses_to_one_ontology_finding_when_most_labels_repeat_their_name() -> None:
    rows = " ".join(f'ex:hasPart{i} a owl:Class ; rdfs:label "hasPart{i}" .' for i in range(10))
    assert _foci("LEX010", rows + " ex:o a owl:Ontology .") == ["o"]
    assert len(_foci("LEX010", rows)) == 1


# --- LEX011, LEX012 ---------------------------------------------------------------------------------------


def test_lex011_inner_breaks_tabs_and_double_spaces_but_not_the_ends() -> None:
    assert _foci("LEX011", 'ex:A a owl:Class ; rdfs:label "a\\nb" .') == ["A"]
    assert _foci("LEX011", 'ex:A a owl:Class ; rdfs:label "a\\tb" .') == ["A"]
    assert _foci("LEX011", 'ex:A a owl:Class ; rdfs:label "a  b" .') == ["A"]
    assert _foci("LEX011", 'ex:A a owl:Class ; rdfs:label "a b\\n" .') == []  # LEX005's


def test_lex012_four_marks_only() -> None:
    for mark in (".", ":", ";", ","):
        assert _foci("LEX012", f'ex:A a owl:Class ; rdfs:label "a{mark}" .') == ["A"]
    for mark in ("!", "?", "…", ")"):
        assert _foci("LEX012", f'ex:A a owl:Class ; rdfs:label "a{mark}" .') == []


# --- LEX013, LEX014 (RDFS 5.4.1, 5.4.2: range rdfs:Literal; SKOS 5.3 S12) ---------------------------------


def test_lex013_non_literal_labels_and_definitions() -> None:
    assert _foci("LEX013", "ex:A a owl:Class ; rdfs:label ex:B .") == ["A"]
    assert _foci("LEX013", "ex:A a owl:Class ; rdfs:comment [ a ex:Note ] .") == ["A"]
    assert _foci("LEX013", 'ex:A a owl:Class ; skos:definition [ rdf:value "d" ] .') == []


def test_lex014_a_label_datatype_other_than_xsd_string() -> None:
    assert _foci("LEX014", 'ex:A a owl:Class ; rdfs:label "1"^^xsd:integer .') == ["A"]
    assert _foci("LEX014", 'ex:A a owl:Class ; rdfs:label "a"^^xsd:string, "b"@en, "c" .') == []
    assert _foci("LEX014", 'ex:A a owl:Class ; rdfs:comment "1"^^xsd:integer .') == []  # not a label


# --- LEX015, LEX016 (SKOS 5.4 S13) ------------------------------------------------------------------------


def test_lex015_same_text_and_language_after_normalisation() -> None:
    assert _foci("LEX015", 'ex:A a owl:Class ; rdfs:label "a b"@en ; skos:altLabel "A  B"@en .') == ["A"]
    assert _foci("LEX015", 'ex:A a owl:Class ; skos:prefLabel "a"@en ; skos:hiddenLabel "a"@en .') == ["A"]
    assert _foci("LEX015", 'ex:A a owl:Class ; rdfs:label "a"@en ; skos:altLabel "a"@fr .') == []


def test_lex015_does_not_report_an_alt_label_equal_to_a_hidden_label() -> None:
    # Known gap: S13 also makes skos:altLabel and skos:hiddenLabel disjoint.
    assert _foci("LEX015", 'ex:A a owl:Class ; skos:altLabel "a"@en ; skos:hiddenLabel "a"@en .') == []


def test_lex016_an_alt_label_that_names_another_term() -> None:
    other = 'ex:A a owl:Class ; skos:altLabel "b" . ex:B a owl:Class ; rdfs:label "B" .'
    assert _foci("LEX016", other) == ["A"]  # case-folded
    assert _foci("LEX016", other.replace('"B"', '"c"')) == []
    assert _foci("LEX016", 'ex:A a owl:Class ; rdfs:label "b" ; skos:altLabel "b" .') == []


def test_lex016_a_deprecated_owner_does_not_count_but_a_deprecated_holder_is_judged() -> None:
    # Decision of #155 (item 3): a deprecated term owns no label here, as in LEX004; the term holding the alternative
    # is judged whether or not it is deprecated.
    owner = 'ex:A a owl:Class ; skos:altLabel "b" . ex:B a owl:Class ; owl:deprecated true ; rdfs:label "b" .'
    assert _foci("LEX016", owner) == []
    holder = 'ex:A a owl:Class ; owl:deprecated true ; skos:altLabel "b" . ex:B a owl:Class ; rdfs:label "b" .'
    assert _foci("LEX016", holder) == ["A"]
    both = owner + ' ex:C a owl:Class ; rdfs:label "b" .'
    assert _foci("LEX016", both) == ["A"]


# --- LEX017, LEX019, LEX020 -------------------------------------------------------------------------------


def test_lex017_definition_equal_to_a_label_after_normalisation() -> None:
    assert _foci("LEX017", 'ex:A a owl:Class ; rdfs:label "Big  cat" ; rdfs:comment "big cat" .') == ["A"]
    assert _foci("LEX017", 'ex:A a owl:Class ; rdfs:label "cat" ; rdfs:comment "a cat" .') == []
    assert _foci("LEX017", 'ex:A a owl:Class ; rdfs:label "cat" ; skos:altLabel "dog" ; rdfs:comment "dog" .') == []


def test_lex019_blank_definitions_and_only_those() -> None:
    assert _foci("LEX019", 'ex:A a owl:Class ; rdfs:comment "" .') == ["A"]
    assert _foci("LEX019", 'ex:A a owl:Class ; skos:definition " \\n" .') == ["A"]
    assert _foci("LEX019", 'ex:A a owl:Class ; rdfs:comment " d " .') == []


def test_lex020_identical_definitions_by_normalised_text_and_language() -> None:
    two = 'ex:A a owl:Class ; rdfs:comment "A  d"@en . ex:B a owl:Class ; rdfs:comment "a d"@en .'
    assert _foci("LEX020", two) == ["A"]
    assert _foci("LEX020", two.replace('"a d"@en', '"a d"@fr')) == []
    assert _foci("LEX020", 'ex:A a owl:Class ; rdfs:comment "" . ex:B a owl:Class ; rdfs:comment "" .') == []


# --- LEX022, LEX023, LEX024 -------------------------------------------------------------------------------


def test_lex022_by_basic_filtering_and_never_for_untagged_labels() -> None:
    assert _foci("LEX022", 'ex:A a owl:Class ; rdfs:label "a"@de .', "en") == ["A"]
    assert _foci("LEX022", 'ex:A a owl:Class ; rdfs:label "a"@en-GB .', "en") == []
    assert _foci("LEX022", 'ex:A a owl:Class ; rdfs:label "a"@eng .', "en") == ["A"]
    assert _foci("LEX022", 'ex:A a owl:Class ; rdfs:label "a" .', "en") == []
    assert _foci("LEX022", 'ex:A a owl:Class ; rdfs:label "a"@de .') == []


def test_lex023_a_defined_term_lacks_a_configured_language() -> None:
    assert _foci("LEX023", 'ex:A a owl:Class ; rdfs:comment "d"@fr .', "en", "fr") == ["A"]
    assert _foci("LEX023", "ex:A a owl:Class .", "en") == []  # LEX002's
    assert _foci("LEX023", 'ex:A a owl:Class ; rdfs:comment "d"@en-GB .', "en") == []
    assert _foci("LEX023", 'ex:A a owl:Class ; rdfs:comment "d" .', "en") == ["A"]  # untagged satisfies none


def test_lex024_distinct_skos_definitions_in_one_language_only() -> None:
    assert _foci("LEX024", 'ex:A a owl:Class ; skos:definition "x"@en, "y"@en .') == ["A"]
    assert _foci("LEX024", 'ex:A a owl:Class ; skos:definition "x"@en, "y"@fr .') == []
    assert _foci("LEX024", 'ex:A a owl:Class ; rdfs:comment "x"@en, "y"@en .') == []  # skos:definition only


# --- LEX018, LEX021 ---------------------------------------------------------------------------------------


def test_lex018_markup_and_entities_in_labels_only() -> None:
    assert _foci("LEX018", 'ex:A a owl:Class ; rdfs:label "<b>a</b>" .') == ["A"]
    assert _foci("LEX018", 'ex:A a owl:Class ; skos:altLabel "a &amp; b" .') == ["A"]
    assert _foci("LEX018", 'ex:A a owl:Class ; rdfs:label "a < b & c" .') == []
    assert _foci("LEX018", 'ex:A a owl:Class ; rdfs:label "Gnathostomata <vertebrates>" .') == []
    assert _foci("LEX018", 'ex:A a owl:Class ; rdfs:comment "<b>a</b>" .') == []
    assert _foci("LEX018", 'ex:A a owl:Class ; skos:hiddenLabel "<b>a</b>" .') == []  # not read


def test_lex021_nfd_labels_but_not_hidden_labels() -> None:
    assert _foci("LEX021", 'ex:A a owl:Class ; rdfs:label "é" .') == ["A"]
    assert _foci("LEX021", 'ex:A a owl:Class ; rdfs:label "é" .') == []
    assert _foci("LEX021", 'ex:A a owl:Class ; skos:hiddenLabel "é" .') == []  # not read


# --- LEX025 -----------------------------------------------------------------------------------------------


def test_lex025_padded_annotation_values_except_labels_and_blank_definitions() -> None:
    assert _foci("LEX025", 'ex:A a owl:Class ; rdfs:comment " d" .') == ["A"]
    assert _foci("LEX025", 'ex:A a owl:Class ; skos:hiddenLabel "h " .') == ["A"]
    assert _foci("LEX025", 'ex:A a owl:Class ; rdfs:label " l " .') == []  # LEX005's
    assert _foci("LEX025", 'ex:A a owl:Class ; rdfs:comment " " .') == []  # LEX019's
    assert _foci("LEX025", 'ex:A a owl:Class ; ex:note " n " .') == []  # undeclared custom predicate: gap
    assert _foci("LEX025", 'ex:note a owl:AnnotationProperty . ex:A a owl:Class ; ex:note " n " .') == ["A"]
    assert _foci("LEX025", 'ex:A a owl:Class ; rdfs:comment " d"^^xsd:integer .') == []


def _padded(turtle: str, **policy: object) -> list[str]:
    result = Linter(graph(turtle), policy=Policy.from_mapping(policy)).execute(["LEX025"])
    return sorted(f.focus.removeprefix(NS) for f in result.findings)


def test_lex025_a_value_typed_xsd_string_is_a_string() -> None:
    # RDF 1.1 Concepts 3.3: a simple literal is an xsd:string; the datatype makes no difference to the lexical form.
    assert _foci("LEX025", 'ex:A a owl:Class ; rdfs:comment " d"^^xsd:string .') == ["A"]
    assert _foci("LEX025", 'ex:A a owl:Class ; rdfs:comment "d"^^xsd:string .') == []


def test_lex025_a_no_break_space_is_padding() -> None:
    # str.strip() removes U+00A0 as it removes U+0020, and so does the rule: a text matcher sees two values.
    assert _foci("LEX025", 'ex:A a owl:Class ; rdfs:comment "\\u00a0d" .') == ["A"]
    assert _foci("LEX025", 'ex:A a owl:Class ; rdfs:comment "d\\u00a0" .') == ["A"]
    assert _foci("LEX025", 'ex:A a owl:Class ; rdfs:comment "d\\u00a0e" .') == []  # inside the value: not padding


def test_lex025_every_built_in_obo_synonym_predicate_is_judged() -> None:
    for name in ("hasSynonym", "hasExactSynonym", "hasBroadSynonym", "hasNarrowSynonym", "hasRelatedSynonym"):
        assert _foci("LEX025", f'ex:A a owl:Class ; <{OIO}{name}> " s" .') == ["A"], name
        assert _foci("LEX025", f'ex:A a owl:Class ; <{OIO}{name}> "s" .') == [], name


def test_lex025_a_configured_definition_predicate_and_its_subproperties_are_judged() -> None:
    extra = f"{NS}define"
    body = 'ex:define a owl:AnnotationProperty . ex:sub rdfs:subPropertyOf ex:define . ex:A a owl:Class ; ex:sub " d" .'
    # A subproperty of a configured definition predicate is judged because of the configuration, declared or not.
    assert _padded(body, extra_definition_predicates=[extra]) == ["A"]
    undeclared = body.replace("ex:define a owl:AnnotationProperty . ", "")
    assert _padded(undeclared) == []
    assert _padded(undeclared, extra_definition_predicates=[extra]) == ["A"]
    # A blank value of a definition predicate is LEX019's.
    assert _padded(undeclared.replace('" d"', '"  "'), extra_definition_predicates=[extra]) == []
