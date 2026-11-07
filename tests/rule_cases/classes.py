"""Cases for CLS001-CLS009 and OWL012, with boundaries for every hierarchy threshold."""

from __future__ import annotations

from rule_harness import Case, chain_turtle, rule_cases, threshold_cases, ttl

SUB = "ex:A a owl:Class . ex:B a owl:Class . ex:A rdfs:subClassOf ex:B ."


def _supers(n: int) -> str:
    return "ex:A a owl:Class . " + " ".join(f"ex:P{i} a owl:Class . ex:A rdfs:subClassOf ex:P{i} ." for i in range(n))


def _properties(n: int) -> str:
    return "ex:A a owl:Class . " + " ".join(f"ex:p{i} a owl:ObjectProperty ; rdfs:domain ex:A ." for i in range(n))


_DEPTH = threshold_cases("depth_limit", 3, chain_turtle)
_SUPERS = threshold_cases("inheritance_limit", 2, _supers)
_PROPS = threshold_cases("soup_limit", 2, _properties)
_CHAIN = Case("four-class single-child chain", chain_turtle(4), boundary=True)

CASES = {
    "CLS001": rule_cases(
        [ttl("isolated class", "ex:A a owl:Class .")],
        [
            ttl("linked classes", SUB),
            ttl("explicit owl:Thing parent", "ex:A a owl:Class ; rdfs:subClassOf owl:Thing ."),
            ttl("used as a domain", "ex:A a owl:Class . ex:p a owl:ObjectProperty ; rdfs:domain ex:A ."),
            ttl("used as a range", "ex:A a owl:Class . ex:p a owl:ObjectProperty ; rdfs:range ex:A ."),
            ttl(
                "used as a restriction filler",
                "ex:A a owl:Class . [ a owl:Restriction ; owl:onProperty ex:p ; owl:someValuesFrom ex:A ] .",
            ),
            ttl("has an instance", "ex:A a owl:Class . ex:i a ex:A ."),
        ],
    ),
    "CLS002": rule_cases(
        [ttl("leaf next to a populated class", "ex:A a owl:Class . ex:B a owl:Class . ex:i a ex:B .")],
        [
            ttl("pure vocabulary without individuals", "ex:A a owl:Class ."),
            ttl("typed instance", "ex:A a owl:Class . ex:i a ex:A ."),
            ttl("has a subclass and a leaf instance", SUB + " ex:i a ex:A ."),
        ],
    ),
    "CLS003": rule_cases(
        [
            ttl("two-class cycle", SUB + " ex:B rdfs:subClassOf ex:A ."),
            ttl("self subclass", "ex:A a owl:Class ; rdfs:subClassOf ex:A ."),
        ],
        [ttl("acyclic hierarchy", SUB)],
    ),
    "CLS004": rule_cases(
        [ttl("shortcut edge", chain_turtle(3) + " ex:n0 rdfs:subClassOf ex:n2 .")],
        [
            ttl("plain chain", chain_turtle(3)),
            ttl(
                "diamond is not redundant",
                "ex:A a owl:Class . ex:B a owl:Class . ex:C a owl:Class . ex:D a owl:Class . "
                "ex:A rdfs:subClassOf ex:B, ex:C . ex:B rdfs:subClassOf ex:D .",
            ),
        ],
    ),
    "CLS005": rule_cases(*_DEPTH),
    "CLS006": rule_cases(*_SUPERS),
    "CLS007": rule_cases(
        [_CHAIN],
        [Case("three-class chain", chain_turtle(3), boundary=True)],
    ),
    "CLS008": rule_cases(*_PROPS),
    "CLS009": rule_cases(
        [
            ttl(
                "equivalent with same label",
                'ex:A a owl:Class ; rdfs:label "Same" ; owl:equivalentClass ex:B . '
                'ex:B a owl:Class ; rdfs:label "same" .',
            )
        ],
        [
            ttl(
                "equivalent with different labels",
                'ex:A a owl:Class ; rdfs:label "One" ; owl:equivalentClass ex:B . '
                'ex:B a owl:Class ; rdfs:label "Two" .',
            )
        ],
    ),
    "OWL012": rule_cases(
        [ttl("class equivalent to itself", "ex:A a owl:Class ; owl:equivalentClass ex:A .")],
        [ttl("equivalent to another class", "ex:A a owl:Class ; owl:equivalentClass ex:B . ex:B a owl:Class .")],
    ),
}
