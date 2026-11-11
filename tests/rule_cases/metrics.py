"""Cases for the ontology-metric rules METRIC001-METRIC013.

Fixtures use the default policy: ``metric_min_sample`` is 10, so each rule gets a below-sample
negative, an at-limit negative (the comparison is strict) and a just-over positive.
"""

# ruff: noqa: PLR2004

from __future__ import annotations

from collections.abc import Callable

from rule_harness import rule_cases, ttl

LONG = "A long enough definition that states what distinguishes this class from its siblings"


def _each(n: int, line: Callable[[int], str]) -> str:
    return "\n".join(line(i) for i in range(n))


def _classes(n: int, extra: Callable[[int], str] = lambda i: "") -> str:
    return _each(n, lambda i: f"ex:C{i} a owl:Class {extra(i)} .")


def _labelled(n: int, labelled: int) -> str:
    return _classes(n, lambda i: '; rdfs:label "c"@en' if i < labelled else "")


def _commented(n: int, commented: int, text: str = LONG) -> str:
    return _classes(n, lambda i: f'; rdfs:comment "{text}"' if i < commented else "")


def _props(n: int, extra: Callable[[int], str] = lambda i: "", kind: str = "owl:ObjectProperty") -> str:
    return _each(n, lambda i: f"ex:p{i} a {kind} {extra(i)} .")


def _fanout(kids: int, extra_classes: int = 0) -> str:
    lines = ["ex:P a owl:Class ."] + [f"ex:K{i} a owl:Class ; rdfs:subClassOf ex:P ." for i in range(kids)]
    return "\n".join(lines) + "\n" + _classes(extra_classes).replace("ex:C", "ex:X")


def _imports(n: int) -> str:
    return (
        "ex:o a owl:Ontology ; owl:imports " + ", ".join(f"<https://o{i}.test/>" for i in range(n)) + " ." if n else ""
    )


def _external(n: int, external: int) -> str:
    def line(i: int) -> str:
        parent = f"<https://other.test/v#P{i}>" if i < external else f"ex:Q{i}"
        return f"ex:C{i} a owl:Class ; rdfs:subClassOf {parent} ."

    return _each(n, line) + "\n" + _each(n, lambda i: f"ex:Q{i} a owl:Class .") + "\n" + "ex:Q0 a owl:Class ."


CASES = {
    "METRIC001": rule_cases(
        [
            ttl("only 4 of 10 labelled", _labelled(10, 4)),
            ttl("IRI-valued labels do not count", _classes(10, lambda i: "; rdfs:label ex:x")),
        ],
        [
            ttl("all labelled", _labelled(10, 10)),
            ttl("at the limit", _labelled(10, 5)),
            ttl("below the minimum sample", _labelled(9, 0)),
            ttl("empty", ""),
            ttl(
                "deprecated classes count as labelled",
                _classes(10, lambda i: '; rdfs:label "c"@en' if i < 4 else "; owl:deprecated true"),
            ),
        ],
    ),
    "METRIC002": rule_cases(
        [ttl("only 4 of 10 defined", _commented(10, 4))],
        [
            ttl("all defined", _commented(10, 10)),
            ttl("at the limit", _commented(10, 5)),
            ttl("below the minimum sample", _commented(9, 0)),
            ttl("skos:definition counts", _classes(10, lambda i: '; skos:definition "d"')),
        ],
    ),
    "METRIC003": rule_cases(
        [ttl("undocumented properties", _props(10))],
        [
            ttl("documented", _props(10, lambda i: '; rdfs:comment "d"')),
            ttl("at the limit", _props(10, lambda i: '; rdfs:comment "d"' if i < 5 else "")),
            ttl("below the minimum sample", _props(9)),
        ],
    ),
    "METRIC004": rule_cases(
        [ttl("one parent with 9 children", _fanout(9))],
        [
            ttl("one parent with 8 children (mean at the limit)", _fanout(8, 1)),
            ttl("no hierarchy", _classes(10)),
            ttl("below the minimum sample", _fanout(8)),
        ],
    ),
    "METRIC005": rule_cases(
        [ttl("ten isolated classes", _classes(10))],
        [
            ttl(
                "a chain",
                _each(10, lambda i: f"ex:C{i} a owl:Class ; rdfs:subClassOf ex:C{(i + 1) % 10 if i < 9 else 0} ."),
            ),
            ttl("instances use the classes", _classes(10) + "\n" + _each(10, lambda i: f"ex:i{i} a ex:C{i} .")),
            ttl(
                "3 of 10 orphans (at the limit)",
                _each(
                    10, lambda i: f"ex:C{i} a owl:Class" + (" ." if i < 3 else f" ; rdfs:subClassOf ex:C{i % 2 + 3} .")
                ),
            ),
            ttl("below the minimum sample", _classes(9)),
            ttl(
                "restriction superclasses connect",
                "ex:p a owl:ObjectProperty .\n"
                + _classes(
                    10,
                    lambda i: (
                        "; rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:p ; owl:someValuesFrom owl:Thing ]"
                    ),
                ),
            ),
            ttl("equivalent classes connect", _classes(10, lambda i: f"; owl:equivalentClass ex:E{i}")),
            ttl("subclasses of owl:Thing connect", _classes(10, lambda i: "; rdfs:subClassOf owl:Thing")),
            ttl(
                "restriction fillers are used",
                "ex:p a owl:ObjectProperty .\n"
                + _each(
                    10,
                    lambda i: (
                        f"ex:F{i} a owl:Class .\nex:H{i} a owl:Class ; "
                        f"rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:p ; owl:someValuesFrom ex:F{i} ] ."
                    ),
                ),
            ),
            # MFTO: the classes hang directly under an upper ontology the file does not declare.
            ttl(
                "external superclasses",
                _each(
                    10,
                    lambda i: f"ex:C{i} a owl:Class ; rdfs:subClassOf <http://purl.obolibrary.org/obo/BFO_0000030> .",
                ),
            ),
        ],
    ),
    "METRIC006": rule_cases(
        [ttl("a pure taxonomy", _classes(10))],
        [
            ttl("one property per ten classes (at the limit)", _classes(10) + _props(1)),
            ttl("below the minimum sample", _classes(9)),
            ttl("empty", ""),
        ],
    ),
    "METRIC007": rule_cases(
        [ttl("51 properties for 10 classes", _classes(10) + "\n" + _props(51))],
        [
            ttl("50 properties for 10 classes (at the limit)", _classes(10) + "\n" + _props(50)),
            ttl("properties without classes", _props(60)),
        ],
    ),
    "METRIC008": rule_cases(
        [ttl("no signatures", _props(10)), ttl("datatype properties", _props(10, kind="owl:DatatypeProperty"))],
        [
            ttl("all with a domain", _props(10, lambda i: "; rdfs:domain ex:C0")),
            ttl("all with a range", _props(10, lambda i: "; rdfs:range ex:C0")),
            ttl("at the limit", _props(10, lambda i: "; rdfs:domain ex:C0" if i < 5 else "")),
            ttl("annotation properties are ignored", _props(10, kind="owl:AnnotationProperty")),
            ttl("below the minimum sample", _props(9)),
            ttl("domainIncludes is a domain", _props(10, lambda i: "; <https://schema.org/domainIncludes> ex:C0")),
            ttl(
                "dcam domain and range includes",
                _props(
                    10,
                    lambda i: (
                        "; <http://purl.org/dc/dcam/domainIncludes> ex:C0 ; <http://purl.org/dc/dcam/rangeIncludes> ex:C0"  # noqa: E501
                    ),
                ),
            ),
            ttl("deprecated properties are exempt", _props(10, lambda i: "; owl:deprecated true")),
        ],
    ),
    "METRIC009": rule_cases(
        [ttl("untagged labels", _classes(10, lambda i: '; rdfs:label "c"'))],
        [
            ttl("tagged labels", _labelled(10, 10)),
            ttl("at the limit", _classes(10, lambda i: '; rdfs:label "c"@en' if i < 5 else '; rdfs:label "c"')),
            ttl("below the minimum sample", _classes(9, lambda i: '; rdfs:label "c"')),
            ttl("no labels at all", _classes(10)),
        ],
    ),
    "METRIC010": rule_cases(
        [ttl("all superclasses external", _external(10, 10))],
        [
            ttl("all superclasses local", _external(10, 0)),
            ttl("well-known W3C superclasses", _classes(12, lambda i: "; rdfs:subClassOf owl:Thing")),
            ttl("below the minimum sample", _external(9, 9)),
        ],
    ),
    "METRIC011": rule_cases(
        [ttl("11 imports", _imports(11))],
        [ttl("10 imports (at the limit)", _imports(10)), ttl("no imports", _imports(0))],
    ),
    "METRIC012": rule_cases(
        [ttl("one-word definitions", _commented(10, 10, "Thing"))],
        [
            ttl("full definitions", _commented(10, 10)),
            ttl("below the minimum sample", _commented(9, 9, "Thing")),
            ttl("undefined classes are not measured", _classes(10)),
        ],
    ),
    "METRIC013": rule_cases(
        [ttl("ten free blank subjects", _each(10, lambda i: "[] a ex:Thing ."))],
        [
            ttl("named subjects", _each(10, lambda i: f"ex:s{i} a owl:Class .")),
            ttl("below the minimum sample", _each(9, lambda i: "[] a ex:Thing .")),
            ttl("restriction nodes are structure", _each(10, lambda i: "[] a owl:Restriction .")),
        ],
    ),
}
