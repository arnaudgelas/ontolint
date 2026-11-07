"""Precision fixes for CLS001, CLS002, CLS005, CLS006, CLS015 and CLS017 (exact expectations)."""

from __future__ import annotations

from rule_harness import BASE, chain_turtle, graph

from ontolint import Linter
from ontolint.policy import DEFAULT_DEPTH_LIMIT, DEFAULT_INHERITANCE_LIMIT


def _focus(rule: str, turtle: str, depth_limit: int = 7, inheritance_limit: int = 3) -> list[str]:
    result = Linter(graph(turtle), depth_limit=depth_limit, inheritance_limit=inheritance_limit).execute([rule])
    return sorted(f.focus.removeprefix(BASE) for f in result.findings)


def test_defaults_are_realistic() -> None:
    assert (DEFAULT_DEPTH_LIMIT, DEFAULT_INHERITANCE_LIMIT) == (10, 5)  # noqa: PLR2004


# --- CLS001 ------------------------------------------------------------------------------------

CLS = "ex:A a owl:Class . "


def test_cls001_each_usage_alone_clears_the_class() -> None:
    assert _focus("CLS001", CLS) == ["A"]
    assert _focus("CLS001", CLS + "ex:p rdfs:domain ex:A .") == []
    assert _focus("CLS001", CLS + "ex:p rdfs:range ex:A .") == []
    assert _focus("CLS001", CLS + "ex:i a ex:A .") == []
    for predicate in ("owl:someValuesFrom", "owl:allValuesFrom", "owl:onClass"):
        assert _focus("CLS001", CLS + f"[] {predicate} ex:A .") == []
    sch = "<https://schema.org/%s>"
    assert _focus("CLS001", CLS + f"ex:p {sch % 'domainIncludes'} ex:A .") == []
    assert _focus("CLS001", CLS + f"ex:p {sch % 'rangeIncludes'} ex:A .") == []


def test_cls001_unrelated_reference_still_reported() -> None:
    assert _focus("CLS001", CLS + "ex:p rdfs:seeAlso ex:A .") == ["A"]
    assert _focus("CLS001", CLS + "ex:p rdfs:domain 'A' .") == ["A"]


# --- CLS002 ------------------------------------------------------------------------------------


def test_cls002_silent_without_individuals_fires_with_them() -> None:
    leaves = CLS + "ex:B a owl:Class . ex:B rdfs:subClassOf ex:A ."
    assert _focus("CLS002", leaves) == []
    assert _focus("CLS002", leaves + " ex:C a owl:Class . ex:i a ex:C .") == ["B"]


def test_cls002_needs_a_quarter_of_the_classes_populated() -> None:
    four = "".join(f"ex:C{i} a owl:Class . " for i in range(4))
    assert _focus("CLS002", four + "ex:i a ex:C0 .") == ["C1", "C2", "C3"]
    five = four + "ex:C4 a owl:Class . "
    assert _focus("CLS002", five + "ex:i a ex:C0 .") == []
    assert _focus("CLS002", five + "ex:i a ex:C0 . ex:j a ex:C1 .") == ["C2", "C3", "C4"]


def test_cls002_class_typed_resources_are_not_individuals() -> None:
    # ex:M is a metaclass whose only "instance" is itself a class
    assert _focus("CLS002", "ex:M a owl:Class . ex:A a owl:Class, ex:M .") == []


def test_cls002_foreign_typed_instances_do_not_enable_the_rule() -> None:
    t = "ex:A a owl:Class . ex:i a <http://other.example/Foreign> ."
    assert _focus("CLS002", t) == []


# --- CLS005 ------------------------------------------------------------------------------------


def test_cls005_one_finding_per_deep_branch() -> None:
    # the chain is n0 (leaf) -> ... -> n5 (root); the deep branch is reported at its root
    assert _focus("CLS005", chain_turtle(6), depth_limit=3) == ["n5"]
    result = Linter(graph(chain_turtle(6)), depth_limit=3).execute(["CLS005"])
    assert [f.message for f in result.findings] == ["Asserted subtree depth 6 exceeds 3."]


def test_cls005_boundary_at_limit() -> None:
    assert _focus("CLS005", chain_turtle(3), depth_limit=3) == []
    assert _focus("CLS005", chain_turtle(4), depth_limit=3) == ["n3"]


def test_cls005_two_independent_deep_branches_report_twice() -> None:
    t = chain_turtle(4).replace("n", "a") + chain_turtle(5).replace("n", "b")
    assert _focus("CLS005", t, depth_limit=3) == ["a3", "b4"]


def test_cls005_branch_below_a_shallow_parent_is_reported_at_its_own_top() -> None:
    # r (depth 5) and its child c3 (depth 4) are both deep, so only r is reported
    t = chain_turtle(4).replace("n", "c") + "ex:r a owl:Class . ex:c3 rdfs:subClassOf ex:r ."
    assert _focus("CLS005", t, depth_limit=3) == ["r"]


# --- CLS006 ------------------------------------------------------------------------------------


def _supers(n: int) -> str:
    return CLS + " ".join(f"ex:P{i} a owl:Class . ex:A rdfs:subClassOf ex:P{i} ." for i in range(n))


def test_cls006_boundary_at_the_default_limit() -> None:
    limit = DEFAULT_INHERITANCE_LIMIT
    assert _focus("CLS006", _supers(limit), inheritance_limit=limit) == []
    assert _focus("CLS006", _supers(limit + 1), inheritance_limit=limit) == ["A"]


def test_cls006_foreign_parents_do_not_count() -> None:
    t = _supers(5) + " ".join(f" ex:A rdfs:subClassOf <http://other.example/F{i}> ." for i in range(3))
    assert _focus("CLS006", t, inheritance_limit=5) == []


# --- CLS015 / CLS017 ---------------------------------------------------------------------------


def test_cls015_foreign_parent_is_ignored() -> None:
    kids = " ".join(f"ex:C{i} a owl:Class ; rdfs:subClassOf <http://other.example/Obsolete> ." for i in range(4))
    assert _focus("CLS015", kids) == []


def test_cls017_metaclass_types_are_exempt_but_other_classes_are_not() -> None:
    meta = "ex:DataType a owl:Class ; rdfs:subClassOf rdfs:Class . "
    assert _focus("CLS017", meta + "ex:Text a owl:Class, ex:DataType .") == []
    # transitive: a subclass of a metaclass is a metaclass too
    meta2 = meta + "ex:Sub a owl:Class ; rdfs:subClassOf ex:DataType . "
    assert _focus("CLS017", meta2 + "ex:Text a owl:Class, ex:Sub .") == []
    # a metaclass-typed class that is also NamedIndividual or typed by an ordinary class still fires
    assert _focus("CLS017", meta + "ex:Text a owl:Class, ex:DataType, owl:NamedIndividual .") == ["Text"]
    assert _focus("CLS017", meta + "ex:M a owl:Class . ex:Text a owl:Class, ex:DataType, ex:M .") == ["Text"]


def test_cls001_links_to_foreign_or_anonymous_classes_and_deprecation_clear_the_class() -> None:
    assert _focus("CLS001", CLS + "ex:A rdfs:subClassOf <http://other.example/F> .") == []
    assert _focus("CLS001", CLS + "ex:A rdfs:subClassOf [ a owl:Restriction ] .") == []
    assert _focus("CLS001", CLS + "<http://other.example/F> rdfs:subClassOf ex:A .") == []
    assert _focus("CLS001", CLS + "ex:A owl:equivalentClass [ a owl:Class ] .") == []
    assert _focus("CLS001", CLS + "<http://other.example/F> owl:equivalentClass ex:A .") == []
    assert _focus("CLS001", CLS + "ex:A owl:deprecated true .") == []
    assert _focus("CLS001", CLS + "ex:A owl:deprecated false .") == ["A"]
