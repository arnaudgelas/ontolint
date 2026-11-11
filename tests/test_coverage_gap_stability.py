"""The coverage-gap fixes add findings; they never reword, refocus or re-key one that was already reported.

The 0.9.0 specification review left thirteen known gaps in OWL010, OWL019, OWL032-OWL037, OWL040, SHQ008,
SHQ011, SHQ017, ALIGN003 and SKOS009 (TODO.md, P1 audit item).  Closing them adds conditions and messages to
those rules.  A baseline matches a finding by its rule, focus and subject (version 2) or by its message
(version 1), so every finding these rules reported before must keep all three.  :data:`PINNED` holds them,
captured from each pre-existing positive case before any gap was closed (``ex:`` stands for the cases' base
IRI); each case must still yield them, next to whatever the new conditions add.
"""

from __future__ import annotations

import pytest
from rule_cases import load_cases
from rule_harness import BASE, Case, graph

from ontolint import Linter

PINNED: dict[tuple[str, str], tuple[tuple[str, str, tuple[str, ...]], ...]] = {
    ("OWL010", "one-operand chain"): (("ex:p", "Property-chain axiom has one operand.", ()),),
    ("OWL010", "one-operand chain on an undeclared property"): (("ex:p", "Property-chain axiom has one operand.", ()),),
    ("OWL019", "transitive functional"): (
        (
            "ex:p",
            "Property is transitive (non-simple) but declared functional.",
            ("http://www.w3.org/2002/07/owl#FunctionalProperty",),
        ),
    ),
    ("OWL019", "chain-defined irreflexive"): (
        (
            "ex:p",
            "Property is defined by a property chain (non-simple) but declared irreflexive.",
            ("http://www.w3.org/2002/07/owl#IrreflexiveProperty",),
        ),
    ),
    ("OWL019", "transitive inverse-functional"): (
        (
            "ex:p",
            "Property is transitive (non-simple) but declared inverse-functional.",
            ("http://www.w3.org/2002/07/owl#InverseFunctionalProperty",),
        ),
    ),
    ("OWL019", "transitive asymmetric"): (
        (
            "ex:p",
            "Property is transitive (non-simple) but declared asymmetric.",
            ("http://www.w3.org/2002/07/owl#AsymmetricProperty",),
        ),
    ),
    ("OWL019", "chain-defined functional"): (
        (
            "ex:p",
            "Property is defined by a property chain (non-simple) but declared functional.",
            ("http://www.w3.org/2002/07/owl#FunctionalProperty",),
        ),
    ),
    ("OWL032", "one-operand union"): (
        ("ex:C", "owl:unionOf has a single operand (ex:A).", ("http://www.w3.org/2002/07/owl#unionOf", "ex:A")),
    ),
    ("OWL032", "one-operand intersection"): (
        (
            "ex:C",
            "owl:intersectionOf has a single operand (ex:A).",
            ("http://www.w3.org/2002/07/owl#intersectionOf", "ex:A"),
        ),
    ),
    ("OWL033", "duplicate union member"): (
        ("ex:C", "owl:unionOf list repeats a member.", ("http://www.w3.org/2002/07/owl#unionOf",)),
    ),
    ("OWL033", "duplicate oneOf individual"): (
        ("ex:C", "owl:oneOf list repeats a member.", ("http://www.w3.org/2002/07/owl#oneOf",)),
    ),
    ("OWL033", "duplicate intersection member"): (
        ("ex:C", "owl:intersectionOf list repeats a member.", ("http://www.w3.org/2002/07/owl#intersectionOf",)),
    ),
    ("OWL033", "duplicate literal in a data oneOf"): (
        ("ex:D", "owl:oneOf list repeats a member.", ("http://www.w3.org/2002/07/owl#oneOf",)),
    ),
    ("OWL034", "no onProperty"): (
        ("_:e0b5635e79bf", "Restriction has no owl:onProperty.", ("http://www.w3.org/2002/07/owl#onProperty", "none")),
    ),
    ("OWL034", "two onProperty"): (
        (
            "_:205c6cc014f4",
            "Restriction has more than one owl:onProperty.",
            ("http://www.w3.org/2002/07/owl#onProperty", "several"),
        ),
    ),
    ("OWL034", "literal onProperty"): (
        (
            "_:1fb16f3e7f37",
            'owl:onProperty points to literal "p".',
            ("http://www.w3.org/2002/07/owl#onProperty", '"p"'),
        ),
    ),
    ("OWL034", "anonymous restriction of a class"): (
        (
            "_:532ef54953da",
            "ex:C (restriction): Restriction has no owl:onProperty.",
            ("http://www.w3.org/2002/07/owl#onProperty", "none"),
        ),
    ),
    ("OWL035", "bare restriction"): (
        ("_:dfd11a52c8c7", "Restriction has no value, cardinality or self constraint.", ()),
    ),
    ("OWL035", "only onClass"): (("_:91c24c806ac9", "Restriction has no value, cardinality or self constraint.", ()),),
    ("OWL035", "only onDataRange"): (
        ("_:c2b7777854ff", "Restriction has no value, cardinality or self constraint.", ()),
    ),
    ("OWL036", "negative cardinality"): (
        (
            "_:e7e0e4beb360",
            'owl:minCardinality value "-1"^^<http://www.w3.org/2001/XMLSchema#integer> is not a non-negative integer.',
            ("http://www.w3.org/2002/07/owl#minCardinality", '"-1"^^<http://www.w3.org/2001/XMLSchema#integer>'),
        ),
    ),
    ("OWL036", "decimal cardinality"): (
        (
            "_:d9a9a334f4b7",
            'owl:cardinality value "1.5"^^<http://www.w3.org/2001/XMLSchema#decimal> is not a non-negative integer.',
            ("http://www.w3.org/2002/07/owl#cardinality", '"1.5"^^<http://www.w3.org/2001/XMLSchema#decimal>'),
        ),
    ),
    ("OWL036", "resource cardinality"): (
        (
            "_:6a7ac2a9285c",
            "owl:maxCardinality value ex:two is not a non-negative integer.",
            ("http://www.w3.org/2002/07/owl#maxCardinality", "ex:two"),
        ),
    ),
    ("OWL036", "word cardinality"): (
        (
            "_:c0dd6114337b",
            'owl:maxCardinality value "two" is not a non-negative integer.',
            ("http://www.w3.org/2002/07/owl#maxCardinality", '"two"'),
        ),
    ),
    ("OWL036", "qualified without class"): (
        (
            "_:5229ab35a3ed",
            "Qualified cardinality has neither owl:onClass nor owl:onDataRange.",
            ("http://www.w3.org/2002/07/owl#onClass", "http://www.w3.org/2002/07/owl#onDataRange"),
        ),
    ),
    ("OWL036", "negative qualified cardinality"): (
        (
            "_:360af3f0ba5c",
            'owl:maxQualifiedCardinality value "-2" is not a non-negative integer.',
            ("http://www.w3.org/2002/07/owl#maxQualifiedCardinality", '"-2"'),
        ),
    ),
    ("OWL036", "exact qualified without class or data range"): (
        (
            "_:925f32c955b2",
            "Qualified cardinality has neither owl:onClass nor owl:onDataRange.",
            ("http://www.w3.org/2002/07/owl#onClass", "http://www.w3.org/2002/07/owl#onDataRange"),
        ),
    ),
    ("OWL036", "language-tagged word"): (
        (
            "_:c30428da9a4f",
            'owl:cardinality value "one"@en is not a non-negative integer.',
            ("http://www.w3.org/2002/07/owl#cardinality", '"one"@en'),
        ),
    ),
    ("OWL037", "min above max"): (
        ("_:89271aa1044b", "Lower cardinality bound 3 exceeds upper bound 2.", ("unqualified",)),
    ),
    ("OWL037", "exact below min"): (
        ("_:2f8fefbeb7f3", "Lower cardinality bound 2 exceeds upper bound 1.", ("unqualified",)),
    ),
    ("OWL037", "exact conflicting"): (
        ("_:562828b75e2c", "Lower cardinality bound 2 exceeds upper bound 1.", ("unqualified",)),
    ),
    ("OWL037", "qualified min above max"): (
        ("_:020fa61b65af", "Lower cardinality bound 5 exceeds upper bound 1.", ("qualified",)),
    ),
    ("OWL037", "exact above max"): (
        ("_:4f943552b8af", "Lower cardinality bound 3 exceeds upper bound 2.", ("unqualified",)),
    ),
    ("OWL037", "qualified exact conflicting"): (
        ("_:cdeb0a129a75", "Lower cardinality bound 2 exceeds upper bound 1.", ("qualified",)),
    ),
    ("OWL040", "literal hasValue on object property"): (
        (
            "_:b6bc3a0fa189",
            'Restriction on object property ex:p uses literal hasValue "x".',
            ("ex:p", "http://www.w3.org/2002/07/owl#hasValue", '"x"'),
        ),
    ),
    ("OWL040", "datatype filler on object property"): (
        (
            "_:8a6ee3fbebc8",
            "Restriction on object property ex:p uses datatype filler http://www.w3.org/2001/XMLSchema#string.",
            ("ex:p", "filler", "http://www.w3.org/2001/XMLSchema#string"),
        ),
    ),
    ("OWL040", "resource hasValue on datatype property"): (
        (
            "_:de8c481715ef",
            "Restriction on datatype property ex:DP uses resource hasValue ex:i.",
            ("ex:DP", "http://www.w3.org/2002/07/owl#hasValue", "ex:i"),
        ),
    ),
    ("OWL040", "class filler on datatype property"): (
        (
            "_:3ce8a4744ee6",
            "Restriction on datatype property ex:DP uses class filler ex:A.",
            ("ex:DP", "filler", "ex:A"),
        ),
    ),
    ("OWL040", "owl:Thing filler on datatype property"): (
        (
            "_:c2e79d8d672a",
            "Restriction on datatype property ex:DP uses class filler http://www.w3.org/2002/07/owl#Thing.",
            ("ex:DP", "filler", "http://www.w3.org/2002/07/owl#Thing"),
        ),
    ),
    ("OWL040", "onDataRange on object property"): (
        (
            "_:e53cf9d5f42e",
            "Restriction on object property ex:p uses owl:onDataRange http://www.w3.org/2001/XMLSchema#string.",
            ("ex:p", "http://www.w3.org/2002/07/owl#onDataRange", "http://www.w3.org/2001/XMLSchema#string"),
        ),
    ),
    ("OWL040", "onClass on datatype property"): (
        (
            "_:9f19a73ec1db",
            "Restriction on datatype property ex:DP uses owl:onClass ex:A.",
            ("ex:DP", "http://www.w3.org/2002/07/owl#onClass", "ex:A"),
        ),
    ),
    ("OWL040", "rdfs:Literal filler on object property"): (
        (
            "_:52b77b72c234",
            "Restriction on object property ex:p uses datatype filler http://www.w3.org/2000/01/rdf-schema#Literal.",
            ("ex:p", "filler", "http://www.w3.org/2000/01/rdf-schema#Literal"),
        ),
    ),
    ("OWL040", "declared datatype filler on object property"): (
        (
            "_:b3d58fb4cc40",
            "Restriction on object property ex:p uses datatype filler ex:Dt.",
            ("ex:p", "filler", "ex:Dt"),
        ),
    ),
    ("OWL040", "restriction filler on datatype property"): (
        (
            "_:b252c542c53b",
            "Restriction on datatype property ex:DP uses class filler _:466e3447c60e.",
            ("ex:DP", "filler", "_:466e3447c60e"),
        ),
    ),
    ("SHQ008", "negative"): (
        (
            "ex:P",
            "sh:minCount value -1 is not a non-negative integer.",
            ("http://www.w3.org/ns/shacl#minCount", '"-1"^^<http://www.w3.org/2001/XMLSchema#integer>'),
        ),
    ),
    ("SHQ008", "negative max"): (
        (
            "ex:P",
            "sh:maxCount value -2 is not a non-negative integer.",
            ("http://www.w3.org/ns/shacl#maxCount", '"-2"^^<http://www.w3.org/2001/XMLSchema#integer>'),
        ),
    ),
    ("SHQ008", "decimal"): (
        (
            "ex:P",
            "sh:minCount value 1.0 is not a non-negative integer.",
            ("http://www.w3.org/ns/shacl#minCount", '"1.0"^^<http://www.w3.org/2001/XMLSchema#decimal>'),
        ),
    ),
    ("SHQ008", "double"): (
        (
            "ex:P",
            "sh:maxCount value 1.0 is not a non-negative integer.",
            ("http://www.w3.org/ns/shacl#maxCount", '"1.0"^^<http://www.w3.org/2001/XMLSchema#double>'),
        ),
    ),
    ("SHQ008", "string"): (
        ("ex:P", "sh:minCount value 1 is not a non-negative integer.", ("http://www.w3.org/ns/shacl#minCount", '"1"')),
    ),
    ("SHQ008", "boolean"): (
        (
            "ex:P",
            "sh:minCount value true is not a non-negative integer.",
            ("http://www.w3.org/ns/shacl#minCount", '"true"^^<http://www.w3.org/2001/XMLSchema#boolean>'),
        ),
    ),
    ("SHQ008", "IRI"): (
        (
            "ex:P",
            "sh:maxCount value ex:one is not a non-negative integer.",
            ("http://www.w3.org/ns/shacl#maxCount", "ex:one"),
        ),
    ),
    ("SHQ008", "ill-typed integer"): (
        (
            "ex:P",
            "sh:minCount value one is not a non-negative integer.",
            ("http://www.w3.org/ns/shacl#minCount", '"one"^^<http://www.w3.org/2001/XMLSchema#integer>'),
        ),
    ),
    ("SHQ008", "ill-typed derived integer"): (
        (
            "ex:P",
            "sh:minCount value -1 is not a non-negative integer.",
            ("http://www.w3.org/ns/shacl#minCount", '"-1"^^<http://www.w3.org/2001/XMLSchema#nonNegativeInteger>'),
        ),
    ),
    ("SHQ008", "one bad value among good ones"): (
        (
            "ex:P",
            "sh:maxCount value -1 is not a non-negative integer.",
            ("http://www.w3.org/ns/shacl#maxCount", '"-1"^^<http://www.w3.org/2001/XMLSchema#integer>'),
        ),
    ),
    ("SHQ011", "unbalanced paren"): (
        ("ex:P", "sh:pattern does not compile: missing ), unterminated subpattern at position 0", ('"(abc"',)),
    ),
    ("SHQ011", "inverted repetition"): (
        ("ex:P", "sh:pattern does not compile: min repeat greater than max repeat at position 2", ('"a{2,1}"',)),
    ),
    ("SHQ011", "unbalanced with flags"): (
        ("ex:P", "sh:pattern does not compile: unterminated character set at position 0", ('"[a-z"',)),
    ),
    ("SHQ011", "x flag keeps the error"): (
        ("ex:P", "sh:pattern does not compile: missing ), unterminated subpattern at position 2", ('"a b ("',)),
    ),
    ("SHQ011", "one bad pattern among good ones"): (
        ("ex:P", "sh:pattern does not compile: missing ), unterminated subpattern at position 0", ('"(b"',)),
    ),
    ("SHQ015", "unknown flag"): (("ex:P", "sh:flags value ig is not made of the flags s, m, i, x and q.", ('"ig"',)),),
    ("SHQ015", "flags without pattern"): (
        ("ex:P", "sh:flags is used without an sh:pattern.", ("http://www.w3.org/ns/shacl#pattern",)),
    ),
    ("SHQ017", "min length above max"): (("ex:P", "sh:minLength 5 exceeds sh:maxLength 2.", ()),),
    ("SHQ017", "max length zero"): (("ex:P", "sh:minLength 1 exceeds sh:maxLength 0.", ()),),
    ("SHQ017", "derived integer types"): (("ex:P", "sh:minLength 3 exceeds sh:maxLength 2.", ()),),
    ("ALIGN003", "chain with broad"): (
        (
            "http://a.test/X",
            "http://a.test/X and http://c.test/Z are exactMatch-equivalent through a chain "
            "but also linked by broadMatch/narrowMatch.",
            ("http://c.test/Z",),
        ),
    ),
    ("ALIGN003", "chain with narrow"): (
        (
            "http://a.test/X",
            "http://a.test/X and http://c.test/Z are exactMatch-equivalent through a chain "
            "but also linked by broadMatch/narrowMatch.",
            ("http://c.test/Z",),
        ),
    ),
    ("ALIGN003", "longer chain"): (
        (
            "ex:W",
            "ex:W and http://a.test/X are exactMatch-equivalent through a chain "
            "but also linked by broadMatch/narrowMatch.",
            ("http://a.test/X",),
        ),
    ),
    ("SKOS009", "related and broader"): (
        ("ex:a", "skos:related and a hierarchical link both connect ex:a and ex:b.", ("ex:b",)),
    ),
    ("SKOS009", "related and inverse narrower"): (
        ("ex:a", "skos:related and a hierarchical link both connect ex:a and ex:b.", ("ex:b",)),
    ),
    ("SKOS009", "related to a grandparent"): (
        ("ex:a", "skos:related and a hierarchical link both connect ex:a and ex:c.", ("ex:c",)),
    ),
    ("SKOS009", "related to a grandchild, mixed predicates"): (
        ("ex:a", "skos:related and a hierarchical link both connect ex:a and ex:c.", ("ex:c",)),
    ),
    ("SKOS009", "related and narrowerTransitive"): (
        ("ex:a", "skos:related and a hierarchical link both connect ex:a and ex:b.", ("ex:b",)),
    ),
}


def _case(rule: str, name: str) -> Case:
    (case,) = (case for case in load_cases()[rule].positive if case.name == name)
    return case


def short(text: str) -> str:
    return text.replace(BASE, "ex:")


def _found(rule: str, case: Case) -> set[tuple[str, str, tuple[str, ...]]]:
    data = case.build() if case.build is not None else graph(case.turtle)
    shapes = graph(case.shapes) if case.shapes is not None else None
    findings = Linter(data, shapes, **case.options).execute([rule]).findings  # type: ignore[arg-type]
    return {(short(f.focus), short(f.message), tuple(map(short, f.subject))) for f in findings if f.rule == rule}


@pytest.mark.parametrize(("rule", "name"), sorted(PINNED), ids=[f"{r}:{n}" for r, n in sorted(PINNED)])
def test_a_finding_reported_before_the_gaps_closed_keeps_its_focus_message_and_subject(rule: str, name: str) -> None:
    assert set(PINNED[rule, name]) <= _found(rule, _case(rule, name))


def test_the_pins_cover_every_rule_whose_gap_closes() -> None:
    touched = {"OWL010", "OWL019", "OWL032", "OWL033", "OWL034", "OWL035", "OWL036", "OWL037", "OWL040"}
    touched |= {"SHQ008", "SHQ011", "SHQ015", "SHQ017", "ALIGN003", "SKOS009"}
    assert {rule for rule, _name in PINNED} == touched
    assert all(PINNED.values())
