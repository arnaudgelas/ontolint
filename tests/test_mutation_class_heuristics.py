"""Targeted tests pinning exact behaviour of the class-heuristic rules (boundaries, messages, operands)."""

from __future__ import annotations

import pytest
from rdflib import Graph
from rule_harness import BASE, graph

from ontolint import Linter
from ontolint.models import ExecutionStatus, Finding


def _run(rule: str, data: Graph) -> list[Finding]:
    result = Linter(data).execute([rule])
    assert {x.status for x in result.executions} == {ExecutionStatus.EXECUTED}, result.executions
    return list(result.findings)


def _messages(rule: str, turtle: str) -> list[str]:
    return [f.message for f in _run(rule, graph(turtle))]


def _focus(rule: str, turtle: str) -> list[str]:
    return sorted(f.focus.removeprefix(BASE) for f in _run(rule, graph(turtle)))


def _kids(parent: str, *names: str) -> str:
    return " ".join(f"ex:{n} a owl:Class ; rdfs:subClassOf ex:{parent} ." for n in names)


# --- CLS010 ----------------------------------------------------------------------------------


def test_cls010_message_and_both_siblings_flagged() -> None:
    t = "ex:P a owl:Class . " + _kids("P", "A", "B") + " ex:A rdfs:label 'Same' . ex:B rdfs:label 'same' ."
    assert _messages("CLS010", t) == [
        f"Shares label 'same' with sibling {BASE}B under {BASE}P.",
        f"Shares label 'same' with sibling {BASE}A under {BASE}P.",
    ]


def test_cls010_three_siblings_report_first_other() -> None:
    t = (
        "ex:P a owl:Class . "
        + _kids("P", "A", "B", "C")
        + " ex:A rdfs:label 'x' . ex:B rdfs:label 'x' . ex:C rdfs:label 'x' ."
    )
    assert _messages("CLS010", t) == [
        f"Shares label 'x' with sibling {BASE}B under {BASE}P.",
        f"Shares label 'x' with sibling {BASE}A under {BASE}P.",
        f"Shares label 'x' with sibling {BASE}A under {BASE}P.",
    ]


def test_cls010_whitespace_is_normalised_and_prefix_label_counts() -> None:
    t = "ex:P a owl:Class . " + _kids("P", "A", "B") + " ex:A rdfs:label 'a  b' . ex:B skos:prefLabel ' A B ' ."
    assert _focus("CLS010", t) == ["A", "B"]


def test_cls010_one_class_with_two_equal_labels_is_not_a_clash() -> None:
    t = "ex:P a owl:Class . " + _kids("P", "A") + " ex:A rdfs:label 'x' ; skos:prefLabel 'x' ."
    assert _focus("CLS010", t) == []


def test_cls010_blank_labels_and_non_literals_ignored() -> None:
    t = "ex:P a owl:Class . " + _kids("P", "A", "B") + " ex:A rdfs:label '  ' . ex:B rdfs:label ' ' ."
    assert _focus("CLS010", t) == []
    t = "ex:P a owl:Class . " + _kids("P", "A", "B") + " ex:A rdfs:label ex:L . ex:B rdfs:label ex:L ."
    assert _focus("CLS010", t) == []


def test_cls010_self_loop_is_not_a_sibling_relation() -> None:
    t = "ex:A a owl:Class ; rdfs:subClassOf ex:A ; rdfs:label 'x' ."
    assert _focus("CLS010", t) == []


def test_cls010_language_tags_compare_case_insensitively() -> None:
    t = "ex:P a owl:Class . " + _kids("P", "A", "B") + " ex:A rdfs:label 'x'@EN . ex:B rdfs:label 'x'@en ."
    assert _focus("CLS010", t) == ["A", "B"]


# --- CLS015 ----------------------------------------------------------------------------------


def test_cls015_message_and_boundary() -> None:
    three = "ex:P a owl:Class . " + _kids("P", "A", "B", "C")
    assert _messages("CLS015", three) == ["Class has 3 direct subclasses but no label."]
    four = three + " " + _kids("P", "D")
    assert _messages("CLS015", four) == ["Class has 4 direct subclasses but no label."]
    two = "ex:P a owl:Class . " + _kids("P", "A", "B")
    assert _messages("CLS015", two) == []


def test_cls015_blank_or_non_literal_label_does_not_count() -> None:
    base = "ex:P a owl:Class . " + _kids("P", "A", "B", "C")
    assert _focus("CLS015", base + " ex:P rdfs:label ' ' .") == ["P"]
    assert _focus("CLS015", base + " ex:P rdfs:label ex:L .") == ["P"]
    assert _focus("CLS015", base + " ex:P skos:prefLabel 'x' .") == []
    assert _focus("CLS015", base + " ex:P rdfs:label 'x' .") == []


def test_cls015_subclass_count_ignores_duplicates_and_undeclared() -> None:
    t = "ex:P a owl:Class . " + _kids("P", "A", "B") + " ex:U rdfs:subClassOf ex:P . ex:P rdfs:subClassOf ex:P ."
    assert _focus("CLS015", t) == []


# --- CLS017 ----------------------------------------------------------------------------------


def test_cls017_each_operand_alone_fires() -> None:
    assert _messages("CLS017", "ex:A a owl:Class, owl:NamedIndividual .") == [
        "Class is also typed as an individual (punning)."
    ]
    assert _focus("CLS017", "ex:M a owl:Class . ex:A a owl:Class, ex:M .") == ["A"]
    # the metaclass itself is typed only with owl:Class
    assert _focus("CLS017", "ex:M a owl:Class . ex:A a owl:Class, ex:M .") != ["M"]


def test_cls017_undeclared_type_and_class_types_do_not_fire() -> None:
    assert _focus("CLS017", "ex:A a owl:Class, ex:Undeclared .") == []
    assert _focus("CLS017", "ex:A a rdfs:Class, owl:Class .") == []
    assert _focus("CLS017", "ex:A a rdfs:Class .") == []


def test_cls017_class_types_are_ignored_even_when_declared_as_classes() -> None:
    t = "owl:Class a owl:Class . rdfs:Class a owl:Class . ex:A a rdfs:Class, owl:Class ."
    assert "A" not in _focus("CLS017", t)


def test_cls017_plain_individual_is_not_a_class() -> None:
    assert _focus("CLS017", "ex:C a owl:Class . ex:i a ex:C, owl:NamedIndividual .") == []


# --- CLS022 ----------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["hasPart", "isPartOf", "wasBorn", "canFly", "doesFly", "has2", "has_part", "is-a"])
def test_cls022_prefixes_fire(name: str) -> None:
    t = f"ex:{name} a owl:Class ."
    assert _messages("CLS022", t) == [f"Local name '{name}' looks like a property name."]


@pytest.mark.parametrize(
    "name", ["has", "hash", "isolate", "HasPart", "island", "cant", "wash", "has_", "Is_a", "xhasPart"]
)
def test_cls022_non_property_names_do_not_fire(name: str) -> None:
    assert _focus("CLS022", f"ex:{name} a owl:Class .") == []


def test_cls022_only_classes_are_checked() -> None:
    assert _focus("CLS022", "ex:hasPart a owl:ObjectProperty .") == []


# --- CLS023 ----------------------------------------------------------------------------------


def test_cls023_message_and_interior_positions() -> None:
    assert _messages("CLS023", "ex:DogAndCat a owl:Class .") == [
        "Local name 'DogAndCat' joins concepts with a conjunction."
    ]
    assert _focus("CLS023", "ex:CarOrBoat a owl:Class .") == ["CarOrBoat"]
    assert _focus("CLS023", "ex:A_and_B_C a owl:Class .") == ["A_and_B_C"]
    assert _focus("CLS023", "ex:AB_And_Cd_Ef a owl:Class .") == ["AB_And_Cd_Ef"]


def test_cls023_first_last_and_only_tokens_do_not_fire() -> None:
    assert _focus("CLS023", "ex:And a owl:Class . ex:Or a owl:Class .") == []
    assert _focus("CLS023", "ex:AndGate a owl:Class . ex:RockAnd a owl:Class .") == []
    assert _focus("CLS023", "ex:Android a owl:Class . ex:Orchard a owl:Class .") == []
    assert _focus("CLS023", "ex:XandY a owl:Class .") == []


# --- CLS024 ----------------------------------------------------------------------------------


def test_cls024_message_and_boundary() -> None:
    four = "ex:Vehicle a owl:Class . " + _kids("Vehicle", "RoadVehicle", "AirVehicle", "WaterVehicle", "Bicycle")
    assert _messages("CLS024", four) == [f"Name does not end in 'vehicle' like its 3 siblings under {BASE}Vehicle."]
    assert _focus("CLS024", four) == ["Bicycle"]
    three = "ex:Vehicle a owl:Class . " + _kids("Vehicle", "RoadVehicle", "AirVehicle", "Bicycle")
    assert _focus("CLS024", three) == []


def test_cls024_five_siblings_and_two_outliers() -> None:
    five = "ex:Vehicle a owl:Class . " + _kids(
        "Vehicle", "RoadVehicle", "AirVehicle", "WaterVehicle", "RailVehicle", "Bicycle"
    )
    assert _messages("CLS024", five) == [f"Name does not end in 'vehicle' like its 4 siblings under {BASE}Vehicle."]
    two = "ex:Vehicle a owl:Class . " + _kids("Vehicle", "RoadVehicle", "AirVehicle", "Bicycle", "Boat")
    assert _focus("CLS024", two) == []


def test_cls024_child_equal_to_head_token_is_an_outlier() -> None:
    t = "ex:Vehicle a owl:Class . " + _kids("Vehicle", "RoadVehicle", "AirVehicle", "WaterVehicle", "Vehicle2x")
    assert _focus("CLS024", t) == ["Vehicle2x"]
    t = "ex:Vehicle a owl:Class . " + _kids("Vehicle", "RoadVehicle", "AirVehicle", "WaterVehicle", "Truck_vehicle_")
    assert _focus("CLS024", t) == []


def test_cls024_single_token_child_is_not_a_match() -> None:
    # 'Vehicle' alone has one token: it does not end in the head as a specialisation
    t = "ex:Thing_Vehicle a owl:Class . " + _kids(
        "Thing_Vehicle", "RoadVehicle", "AirVehicle", "WaterVehicle", "Vehicle"
    )
    assert _focus("CLS024", t) == ["Vehicle"]


def test_cls024_parent_without_tokens_is_skipped() -> None:
    t = "ex:_ a owl:Class . " + _kids("_", "A_b", "C_d", "E_f", "G")
    assert _focus("CLS024", t) == []
