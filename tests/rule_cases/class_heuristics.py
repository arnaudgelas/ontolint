"""Cases for the class-heuristic rules CLS010, CLS015, CLS017, CLS022, CLS023 and CLS024."""

from __future__ import annotations

from rule_harness import rule_cases, ttl

P = "ex:P a owl:Class ; rdfs:label 'P' . "


def _kids(*names: str) -> str:
    return " ".join(f"ex:{n} a owl:Class ; rdfs:subClassOf ex:Vehicle ." for n in names)


VEHICLE = "ex:Vehicle a owl:Class ; rdfs:label 'Vehicle' . "

CASES = {
    "CLS010": rule_cases(
        [
            ttl(
                "same label, different case",
                P + "ex:A a owl:Class ; rdfs:subClassOf ex:P ; rdfs:label 'Thing' . "
                "ex:B a owl:Class ; rdfs:subClassOf ex:P ; skos:prefLabel ' thing ' .",
            )
        ],
        [
            ttl(
                "distinct labels",
                P + "ex:A a owl:Class ; rdfs:subClassOf ex:P ; rdfs:label 'A' . "
                "ex:B a owl:Class ; rdfs:subClassOf ex:P ; rdfs:label 'B' .",
            ),
            ttl(
                "same label, different language",
                P + "ex:A a owl:Class ; rdfs:subClassOf ex:P ; rdfs:label 'Pain'@en . "
                "ex:B a owl:Class ; rdfs:subClassOf ex:P ; rdfs:label 'Pain'@fr .",
            ),
            ttl(
                "same label, different parents",
                "ex:P a owl:Class . ex:Q a owl:Class . "
                "ex:A a owl:Class ; rdfs:subClassOf ex:P ; rdfs:label 'A' . "
                "ex:B a owl:Class ; rdfs:subClassOf ex:Q ; rdfs:label 'A' .",
            ),
        ],
    ),
    "CLS015": rule_cases(
        [
            ttl(
                "three subclasses, no label",
                "ex:P a owl:Class . "
                + " ".join(f"ex:C{i} rdfs:subClassOf ex:P ." for i in "123")
                + " ex:C1 a owl:Class . ex:C2 a owl:Class . ex:C3 a owl:Class .",
            )
        ],
        [
            ttl(
                "two subclasses, no label",
                "ex:P a owl:Class . ex:C1 a owl:Class ; rdfs:subClassOf ex:P . "
                "ex:C2 a owl:Class ; rdfs:subClassOf ex:P .",
            ),
            ttl(
                "labelled parent",
                P + " ".join(f"ex:C{i} a owl:Class ; rdfs:subClassOf ex:P ." for i in "123"),
            ),
            ttl(
                "prefLabel counts",
                "ex:P a owl:Class ; skos:prefLabel 'P' . "
                + " ".join(f"ex:C{i} a owl:Class ; rdfs:subClassOf ex:P ." for i in "123"),
            ),
        ],
    ),
    "CLS017": rule_cases(
        [
            ttl("named individual", "ex:A a owl:Class, owl:NamedIndividual ."),
            ttl("instance of a declared class", "ex:M a owl:Class . ex:A a owl:Class, ex:M ."),
        ],
        [
            ttl("plain class", "ex:A a owl:Class ."),
            ttl("class and concept", "ex:A a owl:Class, skos:Concept ."),
            ttl("rdfs class and owl class", "ex:A a rdfs:Class, owl:Class ."),
        ],
    ),
    "CLS022": rule_cases(
        [
            ttl("hasPart", "ex:hasPart a owl:Class ."),
            ttl("isPartOf", "ex:isPartOf a owl:Class ."),
            ttl("snake case", "ex:has_part a owl:Class ."),
        ],
        [
            ttl("noun", "ex:Part a owl:Class ."),
            ttl("capitalised Has", "ex:HasPart a owl:Class ."),
            ttl("word starting with is", "ex:isolate a owl:Class . ex:hash a owl:Class . ex:has a owl:Class ."),
        ],
    ),
    "CLS023": rule_cases(
        [
            ttl("And", "ex:DogAndCat a owl:Class ."),
            ttl("Or", "ex:CarOrBoat a owl:Class ."),
        ],
        [
            ttl("no conjunction", "ex:Dog a owl:Class . ex:Android a owl:Class . ex:Brand a owl:Class ."),
            ttl("leading or trailing conjunction", "ex:AndGate a owl:Class . ex:Rock_And a owl:Class ."),
        ],
    ),
    "CLS024": rule_cases(
        [ttl("one outlier among four", VEHICLE + _kids("RoadVehicle", "AirVehicle", "WaterVehicle", "Bicycle"))],
        [
            ttl("all follow pattern", VEHICLE + _kids("RoadVehicle", "AirVehicle", "WaterVehicle", "RailVehicle")),
            ttl("only three siblings", VEHICLE + _kids("RoadVehicle", "AirVehicle", "Bicycle")),
            ttl("two outliers", VEHICLE + _kids("RoadVehicle", "AirVehicle", "Bicycle", "Boat")),
        ],
    ),
}
