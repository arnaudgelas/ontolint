"""Cases for the hierarchy-quality rules, including large-hierarchy scale cases."""

from __future__ import annotations

from collections.abc import Callable

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS
from rule_harness import BASE, Case, rule_cases, ttl

C = "ex:A a owl:Class . ex:B a owl:Class . ex:C a owl:Class . ex:D a owl:Class . "
SCALE = 20_000


def _big(name: str, build: Callable[[], Graph]) -> Case:
    return Case(name, build=build, boundary=True)


def _node(i: int) -> URIRef:
    return URIRef(f"{BASE}n{i}")


def _chain(length: int) -> Graph:
    g = Graph()
    for i in range(length):
        g.add((_node(i), RDF.type, OWL.Class))
        if i:
            g.add((_node(i - 1), RDFS.subClassOf, _node(i)))
    return g


def _wide(n: int) -> Graph:
    g = Graph()
    g.add((_node(0), RDF.type, OWL.Class))
    for i in range(1, n + 1):
        g.add((_node(i), RDF.type, OWL.Class))
        g.add((_node(i), RDFS.subClassOf, _node(0)))
    return g


def _wide_case(n: int) -> Case:
    return _big(f"{n} direct subclasses", lambda: _wide(n))


def _disjoint_chain() -> Graph:
    g = _chain(SCALE)
    g.add((_node(SCALE - 1), OWL.disjointWith, _node(SCALE - 2)))
    return g


def _equivalent_chain() -> Graph:
    g = _chain(SCALE)
    g.add((_node(0), OWL.equivalentClass, _node(SCALE - 1)))
    return g


def _typed_chain() -> Graph:
    g = _chain(SCALE)
    g.add((URIRef(f"{BASE}i"), RDF.type, _node(0)))
    g.add((URIRef(f"{BASE}i"), RDF.type, _node(SCALE - 1)))
    return g


CASES = {
    "CLS011": rule_cases(
        [_wide_case(51)],
        [_wide_case(50)],
    ),
    "CLS012": rule_cases(
        [ttl("instantiated parent, unused leaves", C + "ex:B rdfs:subClassOf ex:A . ex:i a ex:A .")],
        [
            ttl("child used", C + "ex:B rdfs:subClassOf ex:A . ex:i a ex:A . ex:j a ex:B ."),
            ttl("child has subclass", C + "ex:B rdfs:subClassOf ex:A . ex:C rdfs:subClassOf ex:B . ex:i a ex:A ."),
            ttl("parent uninstantiated", C + "ex:B rdfs:subClassOf ex:A ."),
        ],
    ),
    "CLS013": rule_cases(
        [
            ttl("Other under parent", "ex:Dairy a owl:Class . ex:OtherDairy a owl:Class ; rdfs:subClassOf ex:Dairy ."),
            ttl(
                "Misc by label",
                'ex:Z a owl:Class . ex:K a owl:Class ; rdfs:label "Miscellaneous" ; rdfs:subClassOf ex:Z .',
            ),
            ttl("snake case", "ex:Dairy a owl:Class . ex:other_dairy a owl:Class ; rdfs:subClassOf ex:Dairy ."),
        ],
        [
            ttl("root Other", "ex:Other a owl:Class ."),
            ttl(
                "Other unrelated word",
                "ex:Party a owl:Class . ex:OtherCounterparty a owl:Class ; rdfs:subClassOf ex:Party .",
            ),
            ttl("no marker", "ex:A a owl:Class . ex:B a owl:Class ; rdfs:subClassOf ex:A ."),
            ttl("marker as substring", "ex:A a owl:Class . ex:Mother a owl:Class ; rdfs:subClassOf ex:A ."),
        ],
    ),
    "CLS014": rule_cases(
        [
            ttl("direct", C + "ex:A owl:disjointWith ex:B . ex:C rdfs:subClassOf ex:A, ex:B ."),
            ttl(
                "through ancestors",
                C + "ex:A owl:disjointWith ex:B . ex:A2 a owl:Class . ex:B2 a owl:Class . "
                "ex:A2 rdfs:subClassOf ex:A . ex:B2 rdfs:subClassOf ex:B . ex:C rdfs:subClassOf ex:A2, ex:B2 .",
            ),
            ttl("subclass of its disjoint", C + "ex:A owl:disjointWith ex:B . ex:A rdfs:subClassOf ex:B ."),
            ttl(
                "all disjoint list",
                C + "[ a owl:AllDisjointClasses ; owl:members ( ex:A ex:B ex:D ) ] . ex:C rdfs:subClassOf ex:A, ex:D .",
            ),
            _big("scale: deep chain", _disjoint_chain),
        ],
        [
            ttl(
                "siblings only",
                C + "ex:A owl:disjointWith ex:B . ex:C rdfs:subClassOf ex:A . ex:D rdfs:subClassOf ex:B .",
            ),
            ttl("no disjointness", C + "ex:C rdfs:subClassOf ex:A, ex:B ."),
            ttl(
                "malformed members list",
                C + "[ a owl:AllDisjointClasses ; owl:members _:x ] . ex:C rdfs:subClassOf ex:A, ex:B .",
            ),
            ttl("self disjoint", C + "ex:A owl:disjointWith ex:A ."),
            ttl("cycle without disjointness", C + "ex:A rdfs:subClassOf ex:B . ex:B rdfs:subClassOf ex:A ."),
        ],
    ),
    "CLS016": rule_cases(
        [
            ttl("isA", "ex:isA a owl:ObjectProperty ."),
            ttl("is", "ex:is a rdf:Property ."),
            ttl("snake kind of", "ex:is_kind_of a owl:ObjectProperty ."),
        ],
        [
            ttl("specific", "ex:isPartOf a owl:ObjectProperty ."),
            ttl("island", "ex:island a owl:ObjectProperty ."),
            ttl("only a class named is", "ex:IsA a owl:Class ."),
            ttl("foreign namespace", "<http://other.example/isA> a owl:ObjectProperty .", base=BASE),
        ],
    ),
    "CLS018": rule_cases(
        [
            ttl("Thing plus parent", C + "ex:A rdfs:subClassOf owl:Thing, ex:B ."),
            ttl(
                "Resource plus restriction", "ex:A a owl:Class ; rdfs:subClassOf rdfs:Resource, [ a owl:Restriction ] ."
            ),
        ],
        [
            ttl("Thing alone", "ex:A a owl:Class ; rdfs:subClassOf owl:Thing ."),
            ttl("Thing and self", "ex:A a owl:Class ; rdfs:subClassOf owl:Thing, ex:A ."),
            ttl("no top", C + "ex:A rdfs:subClassOf ex:B ."),
        ],
    ),
    "CLS019": rule_cases(
        [
            ttl("below Nothing", "ex:A a owl:Class ; rdfs:subClassOf owl:Nothing ."),
            ttl("equivalent to Nothing", "ex:A a owl:Class ; owl:equivalentClass owl:Nothing ."),
        ],
        [ttl("below Thing", "ex:A a owl:Class ; rdfs:subClassOf owl:Thing ."), ttl("plain", "ex:A a owl:Class .")],
    ),
    "CLS020": rule_cases(
        [
            ttl(
                "same label",
                'ex:A a owl:Class ; rdfs:label "Wine" . ex:B a owl:Class ; rdfs:label " wine "; rdfs:subClassOf ex:A .',
            ),
            ttl(
                "same tagged label",
                'ex:A a owl:Class ; skos:prefLabel "Vin"@fr . '
                'ex:B a owl:Class ; rdfs:label "VIN"@FR ; rdfs:subClassOf ex:A .',
            ),
        ],
        [
            ttl(
                "different",
                'ex:A a owl:Class ; rdfs:label "Wine" . '
                'ex:B a owl:Class ; rdfs:label "Red wine" ; rdfs:subClassOf ex:A .',
            ),
            ttl(
                "different languages",
                'ex:A a owl:Class ; rdfs:label "Pizza"@en . '
                'ex:B a owl:Class ; rdfs:label "Pizza"@it ; rdfs:subClassOf ex:A .',
            ),
            ttl(
                "siblings sharing a label",
                'ex:A a owl:Class . ex:B a owl:Class ; rdfs:label "X" ; rdfs:subClassOf ex:A . '
                'ex:C a owl:Class ; rdfs:label "X" ; rdfs:subClassOf ex:A .',
            ),
            ttl(
                "blank labels",
                'ex:A a owl:Class ; rdfs:label " " . ex:B a owl:Class ; rdfs:label " " ; rdfs:subClassOf ex:A .',
            ),
        ],
    ),
    "CLS021": rule_cases(
        [
            ttl("direct parent", C + "ex:B rdfs:subClassOf ex:A . ex:A owl:equivalentClass ex:B ."),
            ttl(
                "grandparent",
                C + "ex:C rdfs:subClassOf ex:B . ex:B rdfs:subClassOf ex:A . ex:C owl:equivalentClass ex:A .",
            ),
            _big("scale: deep chain", _equivalent_chain),
        ],
        [
            ttl(
                "siblings",
                C + "ex:B rdfs:subClassOf ex:A . ex:C rdfs:subClassOf ex:A . ex:B owl:equivalentClass ex:C .",
            ),
            ttl("unrelated", C + "ex:A owl:equivalentClass ex:B ."),
            ttl("self equivalence", "ex:A a owl:Class ; owl:equivalentClass ex:A ."),
            ttl(
                "equivalent to restriction",
                C + "ex:B rdfs:subClassOf ex:A . ex:B owl:equivalentClass [ a owl:Restriction ] .",
            ),
        ],
    ),
    "CLS025": rule_cases(
        [
            ttl("class and parent", C + "ex:B rdfs:subClassOf ex:A . ex:i a ex:A, ex:B ."),
            ttl(
                "class and grandparent",
                C + "ex:C rdfs:subClassOf ex:B . ex:B rdfs:subClassOf ex:A . ex:i a ex:A, ex:C .",
            ),
            _big("scale: deep chain", _typed_chain),
        ],
        [
            ttl("siblings", C + "ex:B rdfs:subClassOf ex:A . ex:C rdfs:subClassOf ex:A . ex:i a ex:B, ex:C ."),
            ttl("single type", C + "ex:B rdfs:subClassOf ex:A . ex:i a ex:B ."),
            ttl("owl:Thing is not a declared class", C + "ex:i a ex:A, owl:Thing ."),
            ttl("blank instance", C + "ex:B rdfs:subClassOf ex:A . [] a ex:A, ex:B ."),
        ],
    ),
}
