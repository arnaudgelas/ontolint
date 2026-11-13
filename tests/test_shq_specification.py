"""The SHQ family specification (see the ``shapes``, ``shacl_quality`` and ``shacl_authoring`` docstrings).

One section per rule: each pins a condition, an exclusion or a known gap of the rule's specification,
with the W3C section it rests on.  SHACL is the Recommendation of 2017-07-20; XSD Part 2 Appendix F
(1.0) and Appendix G (1.1) give the regular expression grammar that XPath ``fn:matches`` extends.
"""

from __future__ import annotations

import pytest
from rule_harness import graph

from ontolint import Linter
from ontolint.engine import build_context
from ontolint.models import ExecutionStatus
from ontolint.policy import Policy
from ontolint.rules import shacl_authoring
from ontolint.rules.shacl_authoring import xpath_regex_problem
from ontolint.rules.shapes import class_target_reach

NS = "https://example.test/onto#"
SH = "http://www.w3.org/ns/shacl#"
XSD = "http://www.w3.org/2001/XMLSchema#"
DATA = "ex:A a owl:Class ."


def _findings(rule: str, shapes: str, data: str = DATA) -> list[tuple[str, str]]:
    result = Linter(graph(data), graph(shapes)).execute([rule])
    assert {x.status for x in result.executions} == {ExecutionStatus.EXECUTED}, result.executions
    return sorted((f.focus, f.message) for f in result.findings)


def _messages(rule: str, shapes: str, data: str = DATA) -> list[str]:
    return [message for _focus, message in _findings(rule, shapes, data)]


def _foci(rule: str, shapes: str, data: str = DATA) -> list[str]:
    return [focus.removeprefix(NS) for focus, _message in _findings(rule, shapes, data)]


# --- SHQ001-SHQ005: the shapes they judge (SHACL 2.1: a shape is an IRI or a blank node) --------------


@pytest.mark.parametrize("rule", ["SHQ001", "SHQ002", "SHQ003", "SHQ005"])
def test_a_literal_value_of_sh_property_is_not_a_shape(rule: str) -> None:
    shapes = 'ex:S a sh:NodeShape ; sh:targetClass ex:A ; rdfs:label "S" ; rdfs:comment "c" ; sh:property "x" .'
    assert _findings(rule, shapes + ' ex:T sh:property "y" .') == []


def test_shq001_shq002_judge_declared_property_shapes_and_values_of_sh_property() -> None:
    shapes = "ex:S sh:property ex:P . ex:P sh:path ex:p . ex:Q a sh:PropertyShape ; sh:path ex:q ."
    assert _foci("SHQ001", shapes) == ["P", "Q"]
    assert _foci("SHQ002", shapes) == ["P", "Q"]


def test_shq001_shq002_do_not_judge_a_property_shape_reached_only_through_a_logical_list() -> None:
    # Exclusion: a property shape used as an sh:or member is a condition, not a form field (SHACL 2.3.2.1).
    shapes = "ex:S a sh:NodeShape ; sh:or ( [ sh:path ex:p ; sh:minCount 1 ] [ sh:path ex:q ; sh:minCount 1 ] ) ."
    assert _findings("SHQ001", shapes) == []
    assert _findings("SHQ002", shapes) == []


def test_shq001_counts_an_iri_or_untagged_name() -> None:
    assert _findings("SHQ001", "ex:P a sh:PropertyShape ; sh:path ex:p ; sh:name ex:label .") == []
    assert _findings("SHQ001", 'ex:P a sh:PropertyShape ; sh:path ex:p ; sh:name "p" .') == []


# SHACL 2.1.1: a shape declares a constraint for each value of a constraint component's parameter. Every
# SHACL Core parameter that yields a validation result whose sh:sourceShape is the shape itself counts.
CONSTRAINT_BODIES = [
    "sh:class ex:A",
    "sh:datatype xsd:string",
    "sh:nodeKind sh:IRI",
    "sh:minCount 1",
    "sh:maxCount 1",
    "sh:minExclusive 0",
    "sh:minInclusive 0",
    "sh:maxExclusive 9",
    "sh:maxInclusive 9",
    "sh:minLength 1",
    "sh:maxLength 9",
    'sh:pattern "a"',
    'sh:languageIn ( "en" )',
    "sh:uniqueLang true",
    "sh:equals ex:q",
    "sh:disjoint ex:q",
    "sh:lessThan ex:q",
    "sh:lessThanOrEquals ex:q",
    "sh:not ex:T",
    "sh:and ( ex:T ex:U )",
    "sh:or ( ex:T ex:U )",
    "sh:xone ( ex:T ex:U )",
    "sh:node ex:T",
    "sh:qualifiedValueShape ex:T ; sh:qualifiedMinCount 1",
    "sh:qualifiedValueShape ex:T ; sh:qualifiedMaxCount 1",
    "sh:closed true",
    "sh:hasValue ex:v",
    "sh:in ( ex:v )",
    "sh:sparql [ sh:select 'SELECT $this WHERE {}' ]",
]


@pytest.mark.parametrize("body", CONSTRAINT_BODIES)
def test_shq003_every_core_constraint_parameter_bears_a_constraint(body: str) -> None:
    assert _foci("SHQ003", f"ex:P a sh:PropertyShape ; sh:path ex:p ; {body} .") == ["P"]
    assert _findings("SHQ003", f'ex:P a sh:PropertyShape ; sh:path ex:p ; {body} ; sh:message "m" .') == []


@pytest.mark.parametrize(
    "body",
    [
        "sh:property ex:Q",  # the results are the property shape's (SHACL 4.7.2), not this shape's
        "sh:targetClass ex:A",
        'sh:name "n" ; sh:description "d" ; sh:order 1 ; sh:group ex:G',
        'sh:flags "i"',  # an optional parameter, without its sh:pattern
        "sh:ignoredProperties ( rdf:type )",
        "sh:severity sh:Warning ; sh:deactivated false",
    ],
)
def test_shq003_parameters_that_bear_no_constraint_of_their_own(body: str) -> None:
    assert _findings("SHQ003", f"ex:S a sh:NodeShape ; {body} .") == []


@pytest.mark.parametrize(
    "body",
    [
        # SHACL 2.1.1: a constraint is declared only with values for all mandatory parameters, and 4.7.3 makes
        # sh:qualifiedValueShape and a qualified count both mandatory.
        "sh:qualifiedValueShape ex:T",
        "sh:qualifiedValueShape ex:T ; sh:qualifiedValueShapesDisjoint true",
        "sh:qualifiedMaxCount 1",
        # 4.8.1 and 4.4.5: no validation result unless the value is true, and sh:message only fills results (2.1.5).
        "sh:closed false",
        'sh:closed "0"^^xsd:boolean',
        "sh:uniqueLang false",
    ],
)
def test_shq003_a_constraint_needs_its_mandatory_parameters_and_a_switch_that_is_not_false(body: str) -> None:
    assert _findings("SHQ003", f"ex:P a sh:PropertyShape ; sh:path ex:p ; {body} .") == []


@pytest.mark.parametrize("value", ['"1"^^xsd:boolean', "sh:ByTypes", '"true"'])
def test_shq003_a_switch_that_is_not_false_bears_a_constraint(value: str) -> None:
    # True in any lexical form; the SHACL 1.2 draft's sh:ByTypes; an ill-formed value, whose results are undefined.
    assert _foci("SHQ003", f"ex:S a sh:NodeShape ; sh:closed {value} .") == ["S"]


def test_shq003_a_deactivated_shape_has_no_validation_result() -> None:
    # SHACL 2.1.6: all RDF terms conform to a deactivated shape; 3.4: its validation results are empty.
    assert _findings("SHQ003", "ex:P a sh:PropertyShape ; sh:path ex:p ; sh:minCount 1 ; sh:deactivated true .") == []
    shapes = "ex:P a sh:PropertyShape ; sh:path ex:p ; sh:minCount 1 ; sh:deactivated false ."
    assert _foci("SHQ003", shapes) == ["P"]


def test_shq004_needs_both_label_and_comment() -> None:
    assert _foci("SHQ004", 'ex:S a sh:NodeShape ; rdfs:label "S" .') == ["S"]
    assert _foci("SHQ004", 'ex:S a sh:NodeShape ; rdfs:comment "c" .') == ["S"]
    # Exclusion: only rdfs:label and rdfs:comment count; the shape is not an ontology term.
    assert _foci("SHQ004", 'ex:S a sh:NodeShape ; skos:prefLabel "S" ; skos:definition "c" .') == ["S"]
    # Only declared node shapes are judged.
    assert _findings("SHQ004", "ex:S sh:targetClass ex:A ; sh:closed true .") == []


def test_shq005_one_value_per_language_tag() -> None:
    # SHACL 2.1.5 (sh:message) and 2.3.2.1 (sh:name, sh:description): one value per language tag.
    assert _foci("SHQ005", 'ex:P sh:path ex:p ; sh:name "a", "b" . ex:S sh:property ex:P .') == ["P"]
    assert _foci("SHQ005", 'ex:P sh:path ex:p ; sh:name "a"@EN, "b"@en . ex:S sh:property ex:P .') == ["P"]
    assert _foci("SHQ005", 'ex:S a sh:NodeShape ; sh:message "a"@de, "b"@de .') == ["S"]
    assert _messages("SHQ005", 'ex:S a sh:NodeShape ; sh:message "a", "b" ; sh:description "c", "d" .') == [
        f"Multiple {SH}description values in the same language.",
        f"Multiple {SH}message values in the same language.",
    ]  # one finding per predicate
    assert _findings("SHQ005", 'ex:S a sh:NodeShape ; sh:message "a"@en, "b"@en-GB, "c" .') == []
    assert _findings("SHQ005", 'ex:S a sh:NodeShape ; sh:name "a" ; sh:description "a" .') == []


# --- SHQ006: SHACL instances follow rdfs:subClassOf in the data graph (SHACL 1.1, 2.1.3.2) -----------

HIERARCHY = """ex:A a owl:Class . ex:B a owl:Class ; rdfs:subClassOf ex:A .
ex:C a owl:Class ; rdfs:subClassOf ex:B . ex:i a ex:C . ex:j a ex:A ."""


def test_shq006_a_target_on_a_superclass_covers_the_instances_of_its_subclasses() -> None:
    assert _findings("SHQ006", "ex:S a sh:NodeShape ; sh:targetClass ex:A .", HIERARCHY) == []
    assert _findings("SHQ006", "ex:S a sh:NodeShape ; sh:targetClass ex:B .", HIERARCHY) == [
        (NS + "A", "Class has directly typed instances, but no direct sh:targetClass or implicit class target.")
    ]


def test_shq006_an_implicit_class_target_covers_subclasses_and_may_be_a_property_shape() -> None:
    assert _findings("SHQ006", "ex:A a sh:NodeShape, rdfs:Class .", HIERARCHY) == []
    # SHACL 2.1.3.3: a SHACL instance of sh:NodeShape or sh:PropertyShape that is also a class.
    assert _findings("SHQ006", "ex:A a sh:PropertyShape, rdfs:Class ; sh:path ex:p .", HIERARCHY) == []


def test_shq006_a_subclass_cycle_terminates() -> None:
    data = "ex:A a owl:Class ; rdfs:subClassOf ex:B . ex:B a owl:Class ; rdfs:subClassOf ex:A . ex:i a ex:A ."
    assert _foci("SHQ006", "ex:S a sh:NodeShape ; sh:targetClass ex:X .", data) == ["A"]
    assert _findings("SHQ006", "ex:S a sh:NodeShape ; sh:targetClass ex:B .", data) == []


def _reach(shapes: str, data: str) -> list[str]:
    ctx = build_context(graph(data), graph(shapes), Policy())
    return sorted(str(node).removeprefix(NS) for node in class_target_reach(ctx, graph(shapes)))


def test_class_target_reach_is_the_targets_and_their_subclasses_in_the_data_graph() -> None:
    # The set SHQ006 and shacl_class_target_coverage share: targets, implicit targets, subclasses (any depth).
    assert _reach("ex:S a sh:NodeShape ; sh:targetClass ex:A .", HIERARCHY) == ["A", "B", "C"]
    assert _reach("ex:S a sh:NodeShape ; sh:targetClass ex:B .", HIERARCHY) == ["B", "C"]
    assert _reach("ex:B a sh:NodeShape, owl:Class .", HIERARCHY) == ["B", "C"]
    # A class that is not a shape is no implicit target, and a shape that is no class neither.
    assert _reach("ex:A a rdfs:Class . ex:B a sh:NodeShape .", HIERARCHY) == []
    # A target that is no class of the data graph is reached all the same (it has no subclass there).
    assert _reach("ex:S sh:targetClass ex:X .", HIERARCHY) == ["X"]


def test_class_target_reach_ends_on_a_subclass_cycle() -> None:
    data = "ex:A a owl:Class ; rdfs:subClassOf ex:B . ex:B a owl:Class ; rdfs:subClassOf ex:A ."
    assert _reach("ex:S a sh:NodeShape ; sh:targetClass ex:A .", data) == ["A", "B"]


def test_shq006_a_subclass_axiom_in_the_shapes_graph_is_not_followed() -> None:
    # SHACL 2.1.3.2: the rdfs:subClassOf triples that make a SHACL instance must be in the data graph.
    data = "ex:A a owl:Class . ex:C a owl:Class . ex:i a ex:C ."
    assert _foci("SHQ006", "ex:S a sh:NodeShape ; sh:targetClass ex:A . ex:C rdfs:subClassOf ex:A .", data) == ["C"]


# --- SHQ007-SHQ008 -----------------------------------------------------------------------------------


def test_shq008_a_negative_integer_is_well_formed_shacl_but_meaningless() -> None:
    # SHACL 4.2.1/4.2.2/4.4.1/4.4.2 require only datatype xsd:integer; the finding is about the value.
    assert _messages("SHQ008", "ex:P sh:path ex:p ; sh:maxCount -1 .") == [
        "sh:maxCount value -1 is not a non-negative integer."
    ]
    assert _findings("SHQ008", "ex:P sh:path ex:p ; sh:qualifiedMinCount -1 ; sh:minInclusive -1 .") == []


# --- SHQ009 ------------------------------------------------------------------------------------------


def test_shq009_members_are_compared_as_rdf_terms() -> None:
    # SHACL 4.8.3: "04"^^xsd:byte does not match "4"^^xsd:integer, so they are distinct members.
    assert _findings("SHQ009", 'ex:S sh:in ( "4"^^xsd:byte 4 "4" 4.0 ) .') == []
    assert _messages("SHQ009", "ex:S sh:in ( ex:a ex:a ) .") == ["sh:in list repeats 1 member(s)."]


# --- SHQ010: members are xsd:string basic language ranges (SHACL 4.4.4, RFC 4647 2.1) ------------------


def test_shq010_accepts_the_wildcard_basic_language_range() -> None:
    assert _findings("SHQ010", "ex:S sh:languageIn ( '*' 'en' ) .") == []


@pytest.mark.parametrize(
    ("member", "text"),
    [("'en'@en", '"en"@en'), ("'en'^^xsd:token", f'"en"^^<{XSD}token>'), ("1", f'"1"^^<{XSD}integer>')],
)
def test_shq010_a_member_that_is_not_an_xsd_string_literal(member: str, text: str) -> None:
    assert _messages("SHQ010", f"ex:S sh:languageIn ( 'en' {member} ) .") == [
        f"sh:languageIn member {text} is not an xsd:string literal."
    ]


def test_shq010_wildcard_is_only_a_whole_range() -> None:
    assert _messages("SHQ010", "ex:S sh:languageIn ( 'en-*' ) .") == [
        "sh:languageIn member en-* is not a well-formed language tag."
    ]


# --- SHQ011: XPath regular expressions (F&O 7.6.1 over XSD Part 2 Appendix F, F&O 3.1 5.6.1) ---------


def _shq011(pattern: str, flags: str | None = None) -> list[str]:
    literal = pattern.replace("\\", "\\\\").replace('"', '\\"')
    body = f'sh:pattern "{literal}"' + (f' ; sh:flags "{flags}"' if flags is not None else "")
    return _messages("SHQ011", f"ex:P sh:path ex:p ; {body} .")


@pytest.mark.parametrize(
    "pattern",
    [
        r"[^a-[b]]",  # Python reads a-[ as a range; XSD reads -[ as subtraction (1.0 [16], 1.1 [76])
        r"[\d-[5]]",
        r"[\w-[_]]+",
        r"[a-[b]]",
        r"[a-z-[aeiou]]",
        r"[\p{L}-[\p{Lu}]]",
        r"[a-[b-[c]]]",
        r"[\i-[:]][\c-[:]]*",
    ],
)
def test_shq011_class_subtraction_is_valid(pattern: str) -> None:
    assert _shq011(pattern) == []


@pytest.mark.parametrize("pattern", [r"^*", r"a$?", r"(^)+"])
def test_shq011_a_quantified_anchor_is_valid(pattern: str) -> None:
    # F&O 3.1 5.6.1: ^ and $ are atoms, so they can be quantified; Python's re cannot compile ^*.
    assert _shq011(pattern) == []


@pytest.mark.parametrize(
    ("pattern", "problem"),
    [
        (r"\p{L}(", "missing ), unterminated subpattern"),
        (r"\i\c*)", "unbalanced parenthesis"),
        (r"[\p{L}", "unterminated character set"),
    ],
)
def test_shq011_a_pattern_with_an_xpath_only_escape_is_still_compiled(pattern: str, problem: str) -> None:
    (message,) = _shq011(pattern)
    assert message.startswith(f"sh:pattern does not compile: {problem}"), message


def test_shq011_a_python_error_on_the_rewrite_says_how_the_escapes_were_read() -> None:
    # Python quotes the \w it was given; the hyphen after a class escape is a known gap (see [\d-z]).
    assert _shq011(r"[\p{L}-z]") == [
        r"sh:pattern does not compile: bad character range \w-z (reading \p{..}, \i and \c as \w)"
    ]


@pytest.mark.parametrize(
    ("pattern", "problem"),
    [
        # XSD 1.0 F.1 ("The [, ], - and \ characters are not valid character ranges") and XSD 1.1 [82]
        # (SingleCharNoEsc excludes [ and ]): both reject these; Python reads them as members.
        (r"[[a]", "an unescaped [ inside a character class"),
        (r"[a[]", "an unescaped [ inside a character class"),
        (r"[[:alpha:]]+", "an unescaped [ inside a character class"),
        (r"[a\-[b]]", "an unescaped [ inside a character class"),
        (r"[]a]", "an unescaped ] at the start of a character class"),
        (r"[^]a]", "an unescaped ] at the start of a character class"),
        # XSD 1.0 [27]-[36], XSD 1.1 [87]-[96]: charProp is a category of the fixed list or Is + a block name.
        (r"\p{Letter}", r"\p{Letter} names no XSD category or block"),
        (r"\p{Alpha}", r"\p{Alpha} names no XSD category or block"),
        (r"\P{Lx}", r"\P{Lx} names no XSD category or block"),
        (r"\p{Cs}", r"\p{Cs} names no XSD category or block"),
        (r"\p{L&}", r"\p{L&} names no XSD category or block"),
        (r"[\p{Is}]", r"\p{Is} names no XSD category or block"),
        (r"\p{IsLatin_1}", r"\p{IsLatin_1} names no XSD category or block"),
        (r"\p{L ab}", r"\p{L ab} names no XSD category or block"),
    ],
)
def test_shq011_character_class_and_property_errors(pattern: str, problem: str) -> None:
    assert xpath_regex_problem(pattern) == problem
    assert _shq011(pattern) == [f"sh:pattern is not an XPath regular expression: {problem}."]


@pytest.mark.parametrize(
    ("pattern", "problem"),
    [
        # XSD 1.0 [12]/[16] and 1.1 [75]/[76]: charClassExpr ::= '[' charGroup ']', and a subtraction ends its
        # group, so the class closes right after the subtracted class.  Python reads -[ as a member or a range
        # and lets the inner ] close its class, so it accepts these.
        (r"[a-z-[aeiou]", "an unterminated character class"),
        (r"[a-z-[aeiou]+", "a class subtraction does not end its character class"),
        (r"[)-[a-z]", "an unterminated character class"),
        (r"[)-[)-[c]]", "an unterminated character class"),
        (r"[)-[a]c]", "a class subtraction does not end its character class"),
        (r"[)-[a]-[b]]", "a class subtraction does not end its character class"),
    ],
)
def test_shq011_a_subtraction_must_be_followed_by_the_end_of_its_class(pattern: str, problem: str) -> None:
    assert xpath_regex_problem(pattern) == problem
    assert _shq011(pattern) == [f"sh:pattern is not an XPath regular expression: {problem}."]


@pytest.mark.parametrize(
    "pattern",
    [
        r"(a)\10",  # F&O 3.1 5.6.1.4: \1 then 0, as only one capturing group precedes
        r"(a)(b)\12",
        r"((((((((((((a))))))))))))\12",  # twelve groups: \12 is one back-reference
        r"(a)(?:b)\1",
    ],
)
def test_shq011_a_back_reference_takes_further_digits_only_when_that_group_exists(pattern: str) -> None:
    assert _shq011(pattern) == []


@pytest.mark.parametrize(
    ("pattern", "problem"),
    [
        # F&O 3.1 5.6.1.4: "invalid if a back-reference refers to a capturing sub-expression that does not exist
        # or whose closing right parenthesis occurs after the back-reference".  Python reads \123 as octal.
        (r"\123", "invalid group reference 1"),
        (r"(a)\23", "invalid group reference 2"),
        (r"(a\1)", "cannot refer to an open group"),
        (r"(?:a)\1", "invalid group reference 1"),
    ],
)
def test_shq011_a_back_reference_to_a_missing_or_open_group(pattern: str, problem: str) -> None:
    (message,) = _shq011(pattern)
    assert message.partition(" at position")[0] == f"sh:pattern does not compile: {problem}", message


CATEGORIES = "L Lu Ll Lt Lm Lo M Mn Mc Me N Nd Nl No P Pc Pd Ps Pe Pi Pf Po Z Zs Zl Zp S Sm Sc Sk So C Cc Cf Co Cn"


@pytest.mark.parametrize("name", [*CATEGORIES.split(), "IsBasicLatin", "IsLatin-1Supplement", "IsNoSuchBlock"])
def test_shq011_every_xsd_category_and_any_block_name(name: str) -> None:
    # Known gap: a block name is not checked against a list (the Unicode version is implementation-defined).
    assert xpath_regex_problem(rf"\p{{{name}}}\P{{{name}}}[\p{{{name}}}]") is None
    assert _shq011(rf"\p{{{name}}}") == []


@pytest.mark.parametrize("pattern", [r"[a-]", r"[-a]", r"[a-z-]", r"[+--]", r"[a-k-z]"])
def test_shq011_known_gap_hyphen_placement_is_left_to_python(pattern: str) -> None:
    # XSD 1.0 allows a bare - only first or last; XSD 1.1 has other rules ([a-k-z], [+--]). Python decides.
    assert xpath_regex_problem(pattern) is None
    assert _shq011(pattern) == []


def test_shq011_known_gap_hyphen_after_a_class_escape_is_left_to_python() -> None:
    # Invalid in XSD 1.0 (a bare - not first or last), a member in XSD 1.1; Python rejects the range.
    assert xpath_regex_problem(r"[\d-z]") is None
    (message,) = _shq011(r"[\d-z]")
    assert message.startswith(r"sh:pattern does not compile: bad character range \d-z"), message


def test_shq011_known_gap_an_empty_group_before_a_subtraction() -> None:
    # XSD 1.0 [16] and 1.1 [77] need a non-empty group before "-[": [-[a]] is invalid in both, not reported.
    assert _shq011("[-[a]]") == []


def test_shq011_known_gap_xpath_3_constructs_are_accepted() -> None:
    # SPARQL 1.1 REGEX cites F&O 1.0 (XPath 2.0), which has neither (?: nor the q flag.
    assert _shq011("(?:ab)+") == []
    assert _shq011("(ab", "q") == []


def test_shq011_python_form_keeps_an_xpath_pattern_python_can_read() -> None:
    assert shacl_authoring.python_form("^[a-z]+$") == "^[a-z]+$"
    assert shacl_authoring.python_form(r"\p{L}\P{Nd}\i\c") == r"\w\w\w\w"
    assert shacl_authoring.python_form(r"[^a-[b]]") == r"(?:[^a]|[b])"
    assert shacl_authoring.python_form(r"[a-[b-[c]]]x") == r"(?:[a]|(?:[b]|[c]))x"
    assert shacl_authoring.python_form(r"^*a$?") == r"(?:^)*a(?:$)?"
    assert shacl_authoring.python_form(r"[a-[b]c]") == r"[a-[b]c]"  # a subtraction must end its class: not rewritten
    assert shacl_authoring.python_form("[a") == "[a"
    assert shacl_authoring.python_form(r"(a)\1") == r"(a)\1"
    assert shacl_authoring.python_form(r"(a)\10") == r"(a)(?:\1)0"  # F&O 3.1 5.6.1.4: one group, so \1 then 0
    assert shacl_authoring.python_form(r"[\1]\1") == r"[\1]\1"  # in a class it is no back-reference


def test_shq011_python_form_is_linear_on_hostile_input() -> None:
    hostile = "[a-" * 20000
    assert shacl_authoring.python_form(hostile) == hostile
    nested = "[a-" * 300 + "[b" + "]" * 301
    assert shacl_authoring.python_form(nested).startswith("[a-")  # beyond the nesting cap, left to Python


# --- SHQ021: SHACL Advanced Features targets ---------------------------------------------------------


def test_shq021_a_shacl_af_custom_target_counts_as_a_target() -> None:
    assert _findings("SHQ021", "ex:S a sh:NodeShape ; sh:target [ a sh:SPARQLTarget ; sh:select 'x' ] .") == []
    assert _findings("SHQ021", "ex:S a sh:NodeShape ; sh:targetNode ex:n .") == []
    assert _findings("SHQ021", "ex:S a sh:NodeShape, owl:Class .") == []


# --- SHQ023: a shape has at most one value for sh:path (SHACL 2.3) -------------------------------------


def test_shq023_any_subject_of_sh_path_has_at_most_one_path() -> None:
    assert _messages("SHQ023", "ex:P sh:path ex:a, ex:b ; sh:minCount 1 .") == ["Property shape has 2 sh:path values."]
    assert _findings("SHQ023", "ex:P sh:path ex:a ; sh:minCount 1 .") == []


# --- SHQ024: sh:property values' paths are allowed properties of a closed shape (SHACL 4.8.1) ---------


def test_shq024_rdf_type_as_a_property_path_is_allowed() -> None:
    shapes = "ex:S a sh:NodeShape ; sh:targetClass ex:A ; sh:closed true ; sh:property [ sh:path rdf:type ] ."
    assert _findings("SHQ024", shapes) == []
    inverse = "ex:S a sh:NodeShape ; sh:closed true ; sh:property [ sh:path [ sh:inversePath rdf:type ] ] ."
    assert _foci("SHQ024", inverse) == ["S"]  # only an IRI path is an allowed property


def test_shq024_only_a_true_closed_value() -> None:
    assert _findings("SHQ024", "ex:S a sh:NodeShape ; sh:closed 'true' .") == []
    assert _foci("SHQ024", 'ex:S a sh:NodeShape ; sh:closed "1"^^xsd:boolean .') == ["S"]
    assert _foci(
        "SHQ024", "ex:S a sh:NodeShape ; sh:closed true ; sh:ignoredProperties _:l . _:l rdf:first rdf:type ."
    ) == ["S"]


# --- SHQ013, SHQ019, SHQ020, SHQ025, SHQ026, SHQ027: exclusions and known gaps -------------------------


def test_shq013_on_one_shape_only() -> None:
    assert _foci("SHQ013", "ex:S a sh:NodeShape ; sh:datatype xsd:string ; sh:class ex:A .") == ["S"]
    split = (
        "ex:S sh:property ex:P, ex:Q . ex:P sh:path ex:p ; sh:datatype xsd:string . ex:Q sh:path ex:p ; sh:class ex:A ."
    )
    assert _findings("SHQ013", split) == []


def test_shq019_undefined_means_never_a_subject() -> None:
    assert _foci("SHQ019", "ex:S sh:property ex:P .") == ["S"]
    assert _foci("SHQ019", "ex:S sh:node ex:T . ex:U sh:node ex:T .") == ["S", "U"]
    # Known gap: references through sh:not, sh:qualifiedValueShape and logical lists are not judged.
    assert _findings("SHQ019", "ex:S sh:not ex:T ; sh:or ( ex:U ex:V ) ; sh:qualifiedValueShape ex:W .") == []


def test_shq020_only_a_boolean_true() -> None:
    assert _foci("SHQ020", 'ex:S a sh:NodeShape ; sh:deactivated "1"^^xsd:boolean .') == ["S"]
    assert _findings("SHQ020", "ex:S a sh:NodeShape ; sh:deactivated 'true' .") == []


def test_shq025_counts_and_malformed_lists() -> None:
    assert _messages("SHQ025", "ex:S sh:and () .") == ["sh:and has 0 member(s)."]
    assert _messages("SHQ025", "ex:S sh:xone ( ex:T ) .") == ["sh:xone has 1 member(s)."]
    assert _findings("SHQ025", "ex:S sh:or _:l . _:l rdf:first ex:T .") == []


def test_shq026_only_iri_paths_of_one_node_shape() -> None:
    shapes = "ex:S sh:property [ sh:path [ sh:inversePath ex:p ] ], [ sh:path [ sh:inversePath ex:p ] ] ."
    assert _findings("SHQ026", shapes) == []
    two_shapes = "ex:S sh:property [ sh:path ex:p ] . ex:T sh:property [ sh:path ex:p ] ."
    assert _findings("SHQ026", two_shapes) == []


def test_shq027_any_owned_term_counts_as_declared() -> None:
    data = "ex:A a owl:Class . ex:thing a owl:NamedIndividual ."
    result = Linter(graph(data), graph("ex:S sh:targetClass ex:thing ."), base=NS).execute(["SHQ027"])
    assert list(result.findings) == []
