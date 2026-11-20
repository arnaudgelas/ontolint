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


_TARGETED = "ex:T sh:path ex:p ; sh:targetClass ex:A"  # an untyped property shape of its own, no sh:property parent

GOOD = with_shapes("fully documented shapes", DATA, _shapes())

CASES = {
    "SHQ001": rule_cases(
        [
            with_shapes("no sh:name", DATA, _shapes(name=False)),
            with_shapes(
                "a directly targeted property shape without sh:name", DATA, _TARGETED + ' ; sh:description "d" .'
            ),
            with_shapes(
                "a property shape with sh:targetNode",
                DATA,
                "ex:T sh:path ex:p ; sh:targetNode ex:i ; sh:description 'd' .",
            ),
        ],
        [
            GOOD,
            with_shapes("a literal sh:property value is not a shape", DATA, _shapes() + ' ex:S sh:property "x" .'),
            with_shapes(
                "a path shape reached only through sh:or has no target of its own",
                DATA,
                'ex:S a sh:NodeShape ; sh:targetClass ex:A ; rdfs:label "S" ; rdfs:comment "c" ; sh:or ( ex:T ) .\n'
                'ex:T sh:path ex:p ; sh:description "d" .',
            ),
            with_shapes(
                "a node shape with a path and a target is not a property shape",
                DATA,
                'ex:T a sh:NodeShape ; sh:path ex:p ; sh:targetClass ex:A ; rdfs:label "T" ; rdfs:comment "c" .',
            ),
            with_shapes(
                "a directly targeted property shape, documented",
                DATA,
                _TARGETED + ' ; sh:name "n" ; sh:description "d" .',
            ),
        ],
    ),
    "SHQ002": rule_cases(
        [
            with_shapes("no sh:description", DATA, _shapes(description=False)),
            with_shapes(
                "a directly targeted property shape without sh:description", DATA, _TARGETED + ' ; sh:name "n" .'
            ),
        ],
        [
            GOOD,
            with_shapes(
                "a directly targeted property shape, documented",
                DATA,
                _TARGETED + ' ; sh:name "n" ; sh:description "d" .',
            ),
        ],
    ),
    "SHQ003": rule_cases(
        [
            with_shapes("constraint without sh:message", DATA, _shapes(message=False)),
            with_shapes(
                "sh:maxLength is a constraint", DATA, "ex:P a sh:PropertyShape ; sh:path ex:p ; sh:maxLength 9 ."
            ),
            with_shapes("sh:closed is a constraint", DATA, "ex:S a sh:NodeShape ; sh:closed true ."),
            with_shapes(
                "sh:nodeKind is a constraint (the widened condition)",
                DATA,
                "ex:S a sh:NodeShape ; sh:nodeKind sh:IRI .",
            ),
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
