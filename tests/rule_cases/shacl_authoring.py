"""Cases for SHQ007-SHQ027 (SHACL authoring lints); each shapes graph breaks exactly one thing."""

from __future__ import annotations

from rule_harness import Case, rule_cases, with_shapes

DATA = "ex:A a owl:Class ."
NODE = "ex:S a sh:NodeShape ; sh:targetClass ex:A ; "


def _c(name: str, shapes: str, data: str = DATA, **options: object) -> Case:
    return with_shapes(name, data, shapes, **options)


def _prop(body: str) -> str:
    """A targeted node shape with one property shape ``ex:P`` carrying ``body``."""
    return NODE + f"sh:property ex:P .\nex:P sh:path ex:p ; {body} ."


GOOD = _c("well-formed shapes", _prop("sh:minCount 1 ; sh:maxCount 2 ; sh:datatype xsd:string"))
ANY_CHECK_FREE = _c("empty shapes graph", "")


def _list_case(predicate: str, members: str) -> str:
    return NODE + f"{predicate} {members} ."


CASES = {
    "SHQ007": rule_cases(
        [_c("min above max", _prop("sh:minCount 3 ; sh:maxCount 2"))],
        [GOOD, _c("min equals max", _prop("sh:minCount 2 ; sh:maxCount 2")), _c("only min", _prop("sh:minCount 5"))],
    ),
    "SHQ008": rule_cases(
        [
            _c("negative", _prop("sh:minCount -1")),
        ],
        [GOOD, _c("zero", _prop("sh:minCount 0"))],
    ),
    "SHQ011": rule_cases(
        [_c("unbalanced paren", _prop('sh:pattern "(abc"'))],
        [
            GOOD,
            _c("valid pattern", _prop('sh:pattern "^[a-z]+$" ; sh:flags "i"')),
            _c("xpath-only escape is not judged", _prop('sh:pattern "^\\\\p{L}+$"')),
        ],
    ),
    "SHQ013": rule_cases(
        [_c("datatype and class", _prop("sh:datatype xsd:string ; sh:class ex:A"))],
        [GOOD, _c("class only", _prop("sh:class ex:A"))],
    ),
    "SHQ017": rule_cases(
        [_c("min length above max", _prop("sh:minLength 5 ; sh:maxLength 2"))],
        [
            GOOD,
            _c("equal lengths", _prop("sh:minLength 2 ; sh:maxLength 2")),
        ],
    ),
    "SHQ018": rule_cases(
        [
            _c("inclusive inverted", _prop("sh:minInclusive 10 ; sh:maxInclusive 1")),
            _c("equal but exclusive", _prop("sh:minExclusive 3 ; sh:maxInclusive 3")),
            _c("decimal vs integer", _prop("sh:minInclusive 2.5 ; sh:maxExclusive 2")),
        ],
        [
            GOOD,
            _c("single point", _prop("sh:minInclusive 3 ; sh:maxInclusive 3")),
            _c("non-numeric bounds are not compared", _prop('sh:minInclusive "b" ; sh:maxInclusive "a"')),
        ],
    ),
    "SHQ019": rule_cases(
        [_c("undefined sh:node", _prop("sh:node ex:Missing"))],
        [
            GOOD,
            _c("blank node reference", _prop("sh:node [ sh:nodeKind sh:IRI ]")),
            _c("defined reference", _prop("sh:node ex:T") + "\nex:T a sh:NodeShape ; sh:nodeKind sh:IRI ."),
        ],
    ),
    "SHQ020": rule_cases(
        [_c("deactivated", NODE + "sh:deactivated true .")],
        [GOOD, _c("explicitly active", NODE + "sh:deactivated false .")],
    ),
    "SHQ021": rule_cases(
        [
            _c("floating node shape", "ex:S a sh:NodeShape ."),
            _c(
                "untargeted shape beside a targeted one",
                "ex:S a sh:NodeShape .\nex:T a sh:NodeShape ; sh:targetClass ex:A .",
            ),
        ],
        [
            GOOD,
            _c("referenced shape", NODE + "sh:node ex:T .\nex:T a sh:NodeShape ."),
            _c("implicit class target", "ex:S a sh:NodeShape, rdfs:Class ."),
            _c(
                "referenced from a list",
                NODE + "sh:or ( ex:T ex:U ) .\nex:T a sh:NodeShape .\nex:U a sh:NodeShape .",
            ),
            _c("deactivated is reported by SHQ020 instead", "ex:S a sh:NodeShape ; sh:deactivated true ."),
        ],
    ),
    "SHQ024": rule_cases(
        [
            _c("closed without ignore", NODE + "sh:closed true ."),
            _c(
                "ignore list lacks rdf:type",
                NODE + "sh:closed true ; sh:ignoredProperties ( ex:q ) .",
            ),
        ],
        [
            GOOD,
            _c(
                "closed and ignoring type",
                NODE + "sh:closed true ; sh:ignoredProperties ( rdf:type ) .",
            ),
            _c("open shape", NODE + "sh:closed false ."),
        ],
    ),
    "SHQ025": rule_cases(
        [
            _c("single-member or", _list_case("sh:or", "( ex:T )") + "\nex:T a sh:NodeShape ."),
        ],
        [
            GOOD,
            _c("two members", _list_case("sh:and", "( ex:T ex:U )") + "\nex:T a sh:NodeShape .\nex:U a sh:NodeShape ."),
        ],
    ),
    "SHQ026": rule_cases(
        [
            _c(
                "same path twice",
                NODE + "sh:property ex:P1, ex:P2 .\n"
                "ex:P1 sh:path ex:p ; sh:minCount 1 .\nex:P2 sh:path ex:p ; sh:datatype xsd:string .",
            )
        ],
        [
            GOOD,
            _c(
                "different paths",
                NODE + "sh:property ex:P1, ex:P2 .\n"
                "ex:P1 sh:path ex:p ; sh:minCount 1 .\nex:P2 sh:path ex:q ; sh:minCount 1 .",
            ),
            _c(
                "qualified shapes may repeat a path",
                NODE + "sh:property ex:P1, ex:P2 .\n"
                "ex:P1 sh:path ex:p ; sh:qualifiedValueShape ex:Q ; sh:qualifiedMinCount 1 .\n"
                "ex:P2 sh:path ex:p ; sh:qualifiedValueShape ex:Q ; sh:qualifiedMinCount 1 .\nex:Q a sh:NodeShape .",
            ),
        ],
    ),
    "SHQ027": rule_cases(
        [
            _c(
                "typo in target class",
                "ex:S a sh:NodeShape ; sh:targetClass ex:Typo .",
                base="https://example.test/onto#",
            )
        ],
        [
            _c("declared class", "ex:S a sh:NodeShape ; sh:targetClass ex:A .", base="https://example.test/onto#"),
            _c(
                "external class",
                "ex:S a sh:NodeShape ; sh:targetClass <http://other.test/X> .",
                base="https://example.test/onto#",
            ),
            _c("no base configured", "ex:S a sh:NodeShape ; sh:targetClass ex:Typo ."),
        ],
    ),
}
