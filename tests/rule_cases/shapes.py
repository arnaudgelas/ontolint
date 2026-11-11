"""Cases for SHQ001-SHQ006; each omits exactly one thing from an otherwise well-formed shapes graph."""

from __future__ import annotations

from rule_harness import rule_cases, with_shapes

DATA = "ex:A a owl:Class ."


def _shapes(*, name: bool = True, description: bool = True, message: bool = True, node_doc: bool = True) -> str:
    node = "ex:S a sh:NodeShape ; sh:targetClass ex:A ; sh:property ex:P ;" + (
        ' rdfs:label "S" ; rdfs:comment "c" .' if node_doc else " ."
    )
    prop = "ex:P a sh:PropertyShape ; sh:path ex:p ; sh:minCount 1"
    prop += ' ; sh:name "p"' if name else ""
    prop += ' ; sh:description "d"' if description else ""
    prop += ' ; sh:message "m"' if message else ""
    return node + "\n" + prop + " ."


GOOD = with_shapes("fully documented shapes", DATA, _shapes())

CASES = {
    "SHQ001": rule_cases(
        [with_shapes("no sh:name", DATA, _shapes(name=False))],
        [GOOD, with_shapes("a literal sh:property value is not a shape", DATA, _shapes() + ' ex:S sh:property "x" .')],
    ),
    "SHQ002": rule_cases([with_shapes("no sh:description", DATA, _shapes(description=False))], [GOOD]),
    "SHQ003": rule_cases(
        [
            with_shapes("constraint without sh:message", DATA, _shapes(message=False)),
            with_shapes(
                "sh:maxLength is a constraint", DATA, "ex:P a sh:PropertyShape ; sh:path ex:p ; sh:maxLength 9 ."
            ),
            with_shapes("sh:closed is a constraint", DATA, "ex:S a sh:NodeShape ; sh:closed true ."),
        ],
        [
            GOOD,
            with_shapes(
                "sh:property is the property shape's constraint", DATA, "ex:S a sh:NodeShape ; sh:property ex:P ."
            ),
        ],
    ),
    "SHQ004": rule_cases([with_shapes("node shape without label/comment", DATA, _shapes(node_doc=False))], [GOOD]),
    "SHQ005": rule_cases(
        [with_shapes("two names in one language", DATA, _shapes() + ' ex:P sh:name "q" .')],
        [GOOD, with_shapes("names in different languages", DATA, _shapes() + ' ex:P sh:name "q"@fr .')],
    ),
    "SHQ006": rule_cases(
        [
            with_shapes(
                "class with instances but no target",
                "ex:A a owl:Class . ex:i a ex:A .",
                'ex:S a sh:NodeShape ; rdfs:label "S" ; rdfs:comment "c" .',
            )
        ],
        [
            with_shapes("targeted class", "ex:A a owl:Class . ex:i a ex:A .", _shapes()),
            with_shapes(
                "a target on a superclass covers its subclasses",
                "ex:A a owl:Class . ex:B a owl:Class ; rdfs:subClassOf ex:A . ex:i a ex:B .",
                _shapes(),
            ),
        ],
    ),
}
