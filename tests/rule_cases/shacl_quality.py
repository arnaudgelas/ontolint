"""Cases for SHQ009, 010, 012, 014, 015, 016, 022 and 023 (SHACL shape-authoring quality heuristics)."""

from __future__ import annotations

from rule_harness import Case, rule_cases, with_shapes

DATA = "ex:A a owl:Class ."
NODE = "ex:S a sh:NodeShape ; sh:targetClass ex:A ; "


def _c(name: str, shapes: str) -> Case:
    return with_shapes(name, DATA, shapes)


def _prop(body: str) -> str:
    """A targeted node shape with one property shape ``ex:P`` carrying ``body``."""
    return NODE + f"sh:property ex:P .\nex:P sh:path ex:p ; {body} ."


GOOD = _c("well-formed shapes", _prop("sh:minCount 1 ; sh:datatype xsd:string ; sh:in ( 'a' 'b' )"))
EMPTY = _c("empty shapes graph", "")

CASES = {
    "SHQ009": rule_cases(
        [
            _c("empty list", _prop("sh:in ()")),
            _c("duplicate member", _prop("sh:in ( 'a' 'b' 'a' )")),
        ],
        [GOOD, EMPTY, _c("distinct members", _prop("sh:in ( 'a' 'A' 1 )")), _c("malformed list", _prop("sh:in _:x"))],
    ),
    "SHQ010": rule_cases(
        [
            _c("underscore tag", _prop("sh:languageIn ( 'en' 'en_US' )")),
            _c("IRI member", _prop("sh:languageIn ( 'en' ex:fr )")),
        ],
        [
            GOOD,
            _c("valid tags", _prop("sh:languageIn ( 'en' 'fr-CA' 'zh-Hant-TW' )")),
            _c("empty list", _prop("sh:languageIn ()")),
        ],
    ),
    "SHQ012": rule_cases(
        [_c("unique lang on string", _prop("sh:datatype xsd:string ; sh:uniqueLang true"))],
        [
            GOOD,
            _c("unique lang on langString", _prop("sh:datatype rdf:langString ; sh:uniqueLang true")),
            _c("unique lang false", _prop("sh:datatype xsd:string ; sh:uniqueLang false")),
            _c("unique lang without datatype", _prop("sh:uniqueLang true")),
        ],
    ),
    "SHQ014": rule_cases(
        [
            _c("typo severity", _prop("sh:severity sh:Warn")),
            _c("literal severity", _prop("sh:severity 'warning'")),
        ],
        [
            GOOD,
            _c("standard severities", _prop("sh:severity sh:Info") + "\nex:Q sh:severity sh:Violation, sh:Warning ."),
            _c("custom severity IRI", _prop("sh:severity ex:Critical")),
        ],
    ),
    "SHQ015": rule_cases(
        [
            _c("unknown flag", _prop("sh:pattern 'a' ; sh:flags 'ig'")),
            _c("unknown flag letter (SHQ011 compiles without it)", _prop("sh:pattern 'a' ; sh:flags 'z'")),
            _c("flags without pattern", _prop("sh:flags 'i'")),
        ],
        [
            GOOD,
            _c("pattern with flags", _prop("sh:pattern 'a' ; sh:flags 'smixq'")),
            _c("empty flags", _prop("sh:pattern 'a' ; sh:flags ''")),
        ],
    ),
    "SHQ016": rule_cases(
        [
            _c("self reference", "ex:S a sh:NodeShape ; sh:node ex:S ."),
            _c(
                "two shapes referencing each other",
                "ex:S a sh:NodeShape ; sh:node ex:T .\nex:T a sh:NodeShape ; sh:node ex:S .",
            ),
            _c("cycle through a property shape", NODE + "sh:property ex:P .\nex:P sh:path ex:p ; sh:node ex:S ."),
        ],
        [
            GOOD,
            EMPTY,
            _c(
                "chain",
                "ex:S a sh:NodeShape ; sh:node ex:T .\nex:T a sh:NodeShape ; sh:node ex:U .\nex:U a sh:NodeShape .",
            ),
            _c("diamond", "ex:S a sh:NodeShape ; sh:node ex:T, ex:U .\nex:T sh:node ex:V .\nex:U sh:node ex:V ."),
        ],
    ),
    "SHQ022": rule_cases(
        [
            _c("literal target class", "ex:S a sh:NodeShape ; sh:targetClass 'A' ."),
            _c("blank target subjects-of", "ex:S a sh:NodeShape ; sh:targetSubjectsOf [] ."),
            _c("literal target objects-of", "ex:S a sh:NodeShape ; sh:targetObjectsOf 1 ."),
        ],
        [
            GOOD,
            EMPTY,
            _c(
                "target node literal is allowed", "ex:S a sh:NodeShape ; sh:targetNode 'x' ; sh:targetSubjectsOf ex:p ."
            ),
        ],
    ),
    "SHQ023": rule_cases(
        [
            _c("missing path", NODE + "sh:property ex:P .\nex:P sh:minCount 1 ."),
            _c("two paths", NODE + "sh:property ex:P .\nex:P sh:path ex:p, ex:q ."),
            _c("typed property shape without path", "ex:P a sh:PropertyShape ; sh:minCount 1 ."),
        ],
        [GOOD, EMPTY, _c("node shape needs no path", "ex:S a sh:NodeShape ; sh:closed true .")],
    ),
}
