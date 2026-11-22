"""The SHQ specification amendments of issue #182, pinned through ``Linter(data, shapes).execute([ID])``.

Each case encodes the behaviour the ``shapes``, ``shacl_quality`` and ``shacl_authoring`` docstrings state for
one amendment.  The engine claims name pySHACL 0.40.2 only; Apache Jena was not run.
"""

from __future__ import annotations

import pytest
from rule_harness import graph

from ontolint import Linter
from ontolint.models import ExecutionStatus

NS = "https://example.test/onto#"
DATA = "ex:A a owl:Class ."
SHACL_SHACL = "the shapes graph does not conform to SHACL-SHACL"


def _run(rule: str, shapes: str, data: str = DATA):
    return Linter(graph(data), graph(shapes)).execute([rule])


def _found(rule: str, shapes: str, data: str = DATA) -> list[tuple[str, str, str]]:
    result = _run(rule, shapes, data)
    assert {x.status for x in result.executions} == {ExecutionStatus.EXECUTED}, result.executions
    return sorted((f.focus.removeprefix(NS), str(f.severity), f.message) for f in result.findings)


def _messages(rule: str, shapes: str, data: str = DATA) -> list[str]:
    return [message for _focus, _severity, message in _found(rule, shapes, data)]


def _severities(rule: str, shapes: str, data: str = DATA) -> set[str]:
    return {severity for _focus, severity, _message in _found(rule, shapes, data)}


def _shacl001(shapes: str, data: str):
    return _run("SHACL001", shapes, data).executions[0]


# --- A1 SHQ010: a malformed range matches no tag ----------------------------------------------------


def test_shq010_a_list_with_a_well_formed_member_is_reported_for_the_malformed_one_only() -> None:
    assert _messages("SHQ010", "ex:S sh:languageIn ('en' 'e1') .") == [
        "sh:languageIn member e1 is not a well-formed language tag."
    ]


def test_shq010_a_list_without_a_well_formed_member_reports_each_malformed_member() -> None:
    assert _messages("SHQ010", "ex:S sh:languageIn ('e1' '1x') .") == [
        "sh:languageIn member 1x is not a well-formed language tag.",
        "sh:languageIn member e1 is not a well-formed language tag.",
    ]


def test_shq010_a_member_repeated_verbatim_gives_one_finding() -> None:
    assert _messages("SHQ010", "ex:S sh:languageIn ('e1' 'e1') .") == [
        "sh:languageIn member e1 is not a well-formed language tag."
    ]


def test_shq010_the_warning_is_heuristic_in_every_case() -> None:
    assert _severities("SHQ010", "ex:S sh:languageIn ('e1' '1x') .") == {"warning"}


def test_shq010_a_malformed_range_matches_no_tag_but_a_well_formed_member_still_accepts() -> None:
    # ('en' 'e1') still accepts "en": no SHACL001 finding; ('e1') alone rejects every value node.
    data = 'ex:A a owl:Class . ex:i a ex:A ; ex:p "x"@en .'
    shapes = "ex:S a sh:NodeShape ; sh:targetClass ex:A ; sh:property [ sh:path ex:p ; sh:languageIn ({}) ] ."
    mixed = _run("SHACL001", shapes.format("'en' 'e1'"), data)
    assert [x.status for x in mixed.executions] == [ExecutionStatus.EXECUTED]
    assert len(mixed.findings) == 0
    only_bad = _run("SHACL001", shapes.format("'e1'"), data)
    assert [x.status for x in only_bad.executions] == [ExecutionStatus.EXECUTED]
    assert len(only_bad.findings) == 1


# --- A2 SHQ012: defect (2) is reported at Info although SHACL001 fails ----------------------------------


@pytest.mark.parametrize("value", ["true", "false", '"x"'])
def test_shq012_uniquelang_on_a_node_shape_is_reported_at_info(value: str) -> None:
    shapes = f"ex:S a sh:NodeShape ; sh:uniqueLang {value} ."
    assert _found("SHQ012", shapes) == [
        (
            "S",
            "info",
            "sh:uniqueLang is used on a shape with no sh:path; SHACL 4.4.5 allows it only in a property shape.",
        )
    ]


def test_shq012_uniquelang_on_a_node_shape_makes_shacl001_fail_with_the_shacl_shacl_text() -> None:
    execution = _shacl001("ex:S a sh:NodeShape ; sh:targetClass ex:A ; sh:uniqueLang true .", "ex:A a owl:Class .")
    assert execution.status == ExecutionStatus.FAILED
    assert SHACL_SHACL in (execution.detail or "")


def test_shq012_a_typed_node_shape_with_a_path_is_a_property_shape_here_and_is_shq023s() -> None:
    shapes = "ex:S a sh:NodeShape ; sh:path ex:p ; sh:uniqueLang true ."
    assert _found("SHQ012", shapes) == []
    assert _messages("SHQ023", shapes) == ["Node shape has an sh:path."]


# --- A3 SHQ008: pySHACL refuses a negative count or length at load; zero is accepted -------------------


@pytest.mark.parametrize("body", ["sh:minCount -1", "sh:maxCount -1", "sh:minLength -1", "sh:maxLength -1"])
def test_shq008_a_negative_count_or_length_is_reported_and_stops_shacl001_at_load(body: str) -> None:
    shapes = f"ex:S a sh:NodeShape ; sh:targetClass ex:A ; sh:property [ sh:path ex:p ; {body} ] ."
    data = "ex:A a owl:Class . ex:i a ex:A ; ex:p 'x' ."
    assert _severities("SHQ008", shapes) == {"error"}
    assert len(_found("SHQ008", shapes)) == 1
    execution = _shacl001(shapes, data)
    assert execution.status == ExecutionStatus.FAILED
    assert "ConstraintLoadError" in (execution.detail or "")
    assert "SHQ008" not in (execution.detail or "")  # no pointer to this rule


@pytest.mark.parametrize("body", ["sh:minCount 0", "sh:maxCount 0", "sh:minLength 0", "sh:maxLength 0"])
def test_shq008_zero_is_accepted_by_the_rule_and_by_pyshacl(body: str) -> None:
    shapes = f"ex:S a sh:NodeShape ; sh:targetClass ex:A ; sh:property [ sh:path ex:p ; {body} ] ."
    assert _found("SHQ008", shapes) == []
    assert _shacl001(shapes, "ex:A a owl:Class . ex:i a ex:A .").status == ExecutionStatus.EXECUTED


@pytest.mark.parametrize("literal", ["1e0", "1.0"])
def test_shq008_a_count_prints_its_value_as_rdflib_normalises_it(literal: str) -> None:
    shapes = f"ex:S a sh:NodeShape ; sh:minCount {literal} ."
    assert _messages("SHQ008", shapes) == ["sh:minCount value 1.0 is not a non-negative integer."]


def test_shq008_a_negative_length_prints_the_value_in_n_triples() -> None:
    shapes = "ex:S a sh:NodeShape ; sh:minLength -1 ."
    assert _messages("SHQ008", shapes) == [
        'sh:minLength value "-1"^^<http://www.w3.org/2001/XMLSchema#integer> is not a non-negative integer.'
    ]


# --- A4 SHQ011: what pySHACL accepts and which flags it honours ---------------------------------------


def test_shq011_a_closing_bracket_first_in_a_class_without_a_caret_is_a_warning() -> None:
    assert _severities("SHQ011", "ex:S sh:pattern '[]a]' .") == {"warning"}


def test_shq011_a_closing_bracket_first_after_a_caret_stays_an_error_although_pyshacl_accepts_it() -> None:
    shapes = "ex:S a sh:NodeShape ; sh:targetClass ex:A ; sh:property [ sh:path ex:p ; sh:pattern '[^]a]' ] ."
    assert _messages("SHQ011", shapes) == [
        "sh:pattern is not an XPath regular expression: an unescaped ] at the start of a character class."
    ]
    assert _severities("SHQ011", shapes) == {"error"}
    # pySHACL 0.40.2 loads it: ``b`` conforms, ``]`` does not.
    assert _shacl001(shapes, 'ex:A a owl:Class . ex:i a ex:A ; ex:p "b" .').status == ExecutionStatus.EXECUTED
    assert len(_run("SHACL001", shapes, 'ex:A a owl:Class . ex:i a ex:A ; ex:p "b" .').findings) == 0
    assert len(_run("SHACL001", shapes, 'ex:A a owl:Class . ex:i a ex:A ; ex:p "]" .').findings) == 1


@pytest.mark.parametrize(
    ("pattern", "flags", "text", "conforms"),
    [
        ("a.b", "s", "a\\nb", False),  # s is ignored: the dot still does not match a newline
        ("a b", "x", "ab", False),  # x is ignored: the space is part of the pattern
        ("a.b", "q", "axb", True),  # q is ignored: the pattern is still a regex
        ("a", "i", "A", True),  # i is honoured
    ],
)
def test_shq011_pyshacl_honours_only_the_flags_i_and_m(pattern: str, flags: str, text: str, conforms: bool) -> None:
    shapes = (
        "ex:S a sh:NodeShape ; sh:targetClass ex:A ; "
        f'sh:property [ sh:path ex:p ; sh:pattern "{pattern}" ; sh:flags "{flags}" ] .'
    )
    data = f'ex:A a owl:Class . ex:i a ex:A ; ex:p "{text}" .'
    result = _run("SHACL001", shapes, data)
    assert [x.status for x in result.executions] == [ExecutionStatus.EXECUTED]
    assert (len(result.findings) == 0) is conforms


def test_shq011_a_pattern_only_q_makes_valid_is_not_reported_but_still_stops_shacl001() -> None:
    shapes = (
        "ex:S a sh:NodeShape ; sh:targetClass ex:A ; sh:property [ sh:path ex:p ; sh:pattern '(a' ; sh:flags 'q' ] ."
    )
    assert _found("SHQ011", shapes) == []
    execution = _shacl001(shapes, "ex:A a owl:Class . ex:i a ex:A ; ex:p 'x' .")
    assert execution.status == ExecutionStatus.FAILED
    assert "PatternError" in (execution.detail or "")


# --- A5 a deactivated shape is still reported ------------------------------------------------------------


@pytest.mark.parametrize(
    ("rule", "body"),
    [
        ("SHQ007", "sh:minCount 3 ; sh:maxCount 2"),
        ("SHQ013", "sh:datatype xsd:string ; sh:class ex:C"),
        ("SHQ017", "sh:minLength 3 ; sh:maxLength 2"),
        ("SHQ018", "sh:minInclusive 3 ; sh:maxInclusive 2"),
        ("SHQ024", "sh:closed true"),
        ("SHQ025", "sh:or (ex:A)"),
    ],
)
def test_a_deactivated_shape_is_still_reported(rule: str, body: str) -> None:
    active = _found(rule, f"ex:S a sh:NodeShape ; {body} .")
    deactivated = _found(rule, f"ex:S a sh:NodeShape ; {body} ; sh:deactivated true .")
    assert len(deactivated) == 1
    assert deactivated == active


# --- A6 SHQ025: one finding per list; same predicate and member count merge --------------------------


def test_shq025_one_finding_per_list_with_its_member_count() -> None:
    assert _messages("SHQ025", "ex:S a sh:NodeShape ; sh:or () , (ex:A) .") == [
        "sh:or has 0 member(s).",
        "sh:or has 1 member(s).",
    ]


def test_shq025_lists_with_the_same_predicate_and_member_count_merge_into_one_finding() -> None:
    assert _messages("SHQ025", "ex:S a sh:NodeShape ; sh:or (ex:A), (ex:B) .") == ["sh:or has 1 member(s)."]


def test_shq025_a_different_predicate_is_a_separate_finding() -> None:
    assert _messages("SHQ025", "ex:S a sh:NodeShape ; sh:or (ex:A) ; sh:and (ex:B) .") == [
        "sh:and has 1 member(s).",
        "sh:or has 1 member(s).",
    ]


def test_shq025_a_list_over_500_members_is_malformed_and_excluded_while_500_is_read() -> None:
    members = " ".join(f"ex:p{i}" for i in range(500))
    assert _found("SHQ025", f"ex:S a sh:NodeShape ; sh:or ( {members} ex:z ) .") == []
    assert _found("SHQ025", f"ex:S a sh:NodeShape ; sh:or ( {members} ) .") == []


# --- A7 SHQ021: a reference counts wherever it comes from -----------------------------------------------


MESSAGE_021 = "Node shape has no target and no other shape refers to it."


@pytest.mark.parametrize(
    "shapes",
    [
        "ex:S a sh:NodeShape ; sh:node ex:S .",  # a self-reference
        "ex:S a sh:NodeShape ; sh:node ex:T . ex:T a sh:NodeShape ; sh:node ex:S .",  # mutual only
        "ex:S a sh:NodeShape . ex:T a sh:NodeShape ; sh:node ex:S ; sh:deactivated true ; sh:targetClass ex:C .",
    ],
)
def test_shq021_a_self_mutual_or_deactivated_reference_counts(shapes: str) -> None:
    assert _found("SHQ021", shapes) == []


def test_shq021_a_reference_from_a_shape_nothing_reaches_counts_and_that_shape_is_reported() -> None:
    shapes = "ex:S a sh:NodeShape . ex:T a sh:NodeShape ; sh:node ex:S ."
    assert _found("SHQ021", shapes) == [("T", "warning", MESSAGE_021)]


def test_shq021_an_unreferenced_untargeted_node_shape_is_reported() -> None:
    assert _found("SHQ021", "ex:S a sh:NodeShape .") == [("S", "warning", MESSAGE_021)]


# --- A8 SHQ024: a list of more than 500 members is read as malformed --------------------------------------


def test_shq024_an_ignore_list_of_500_members_with_rdf_type_is_read() -> None:
    members = " ".join(f"ex:p{i}" for i in range(499))
    shapes = f"ex:S a sh:NodeShape ; sh:closed true ; sh:ignoredProperties ( {members} rdf:type ) ."
    assert _found("SHQ024", shapes) == []


def test_shq024_an_ignore_list_of_501_members_is_malformed_and_allows_nothing() -> None:
    members = " ".join(f"ex:p{i}" for i in range(500))
    shapes = f"ex:S a sh:NodeShape ; sh:closed true ; sh:ignoredProperties ( {members} rdf:type ) ."
    assert _found("SHQ024", shapes) == [("S", "info", "Closed shape does not list rdf:type in sh:ignoredProperties.")]


# --- A9 SHQ005: @und shares the untagged tag ---------------------------------------------------------------


MESSAGE_005 = "Multiple http://www.w3.org/ns/shacl#name values in the same language."


@pytest.mark.parametrize("values", ["'a', 'b'@und", "'a'@und, 'b'@und", "'a', 'b'@UND"])
def test_shq005_und_and_untagged_share_one_tag(values: str) -> None:
    assert _found("SHQ005", f"ex:S a sh:NodeShape ; sh:name {values} .") == [("S", "warning", MESSAGE_005)]


def test_shq005_a_different_tag_is_not_shared_with_und() -> None:
    assert _found("SHQ005", "ex:S a sh:NodeShape ; sh:name 'a'@und, 'b'@en .") == []
