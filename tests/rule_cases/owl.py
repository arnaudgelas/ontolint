"""Cases for OWL001-OWL011, OWL013-OWL015, DATA001 and DATA002."""

from __future__ import annotations

from rule_harness import rule_cases, ttl

CASES = {
    "OWL001": rule_cases(
        [ttl("undeclared superclass", "ex:A a owl:Class ; rdfs:subClassOf ex:Undeclared .")],
        [
            ttl("declared superclass", "ex:A a owl:Class ; rdfs:subClassOf ex:B . ex:B a owl:Class ."),
            ttl("owl:Thing is exempt", "ex:A a owl:Class ; rdfs:subClassOf owl:Thing ."),
        ],
    ),
    "OWL002": rule_cases(
        [ttl("domain on an undeclared property", "ex:p rdfs:domain ex:A . ex:A a owl:Class .")],
        [ttl("declared property", "ex:p a owl:ObjectProperty ; rdfs:domain ex:A . ex:A a owl:Class .")],
    ),
    "OWL003": rule_cases(
        [ttl("object and datatype property", "ex:p a owl:ObjectProperty, owl:DatatypeProperty .")],
        [ttl("object property only", "ex:p a owl:ObjectProperty .")],
    ),
    "OWL004": rule_cases(
        [
            ttl("two domains", "ex:p a owl:ObjectProperty ; rdfs:domain ex:A, ex:B ."),
            ttl("two ranges", "ex:p a owl:ObjectProperty ; rdfs:range ex:A, ex:B ."),
        ],
        [ttl("single domain and range", "ex:p a owl:ObjectProperty ; rdfs:domain ex:A ; rdfs:range ex:B .")],
    ),
    "OWL005": rule_cases(
        [ttl("no domain", "ex:p a owl:ObjectProperty .")],
        [ttl("domain asserted", "ex:p a owl:ObjectProperty ; rdfs:domain ex:A .")],
    ),
    "OWL006": rule_cases(
        [ttl("no range", "ex:p a owl:ObjectProperty .")],
        [ttl("range asserted", "ex:p a owl:ObjectProperty ; rdfs:range ex:A .")],
    ),
    "OWL007": rule_cases(
        [ttl("inverse of itself", "ex:p a owl:ObjectProperty ; owl:inverseOf ex:p .")],
        [
            ttl(
                "inverse of another property",
                "ex:p a owl:ObjectProperty ; owl:inverseOf ex:q . ex:q a owl:ObjectProperty .",
            )
        ],
    ),
    "OWL008": rule_cases(
        [
            ttl(
                "symmetric with inverse",
                "ex:p a owl:ObjectProperty, owl:SymmetricProperty ; owl:inverseOf ex:q . ex:q a owl:ObjectProperty .",
            )
        ],
        [
            ttl("inverse only", "ex:p a owl:ObjectProperty ; owl:inverseOf ex:q . ex:q a owl:ObjectProperty."),
            ttl("symmetric only", "ex:p a owl:ObjectProperty, owl:SymmetricProperty ."),
        ],
    ),
    "OWL009": rule_cases(
        [
            ttl(
                "inverse of a datatype property",
                "ex:d a owl:DatatypeProperty ; owl:inverseOf ex:o . ex:o a owl:ObjectProperty .",
            ),
            ttl("transitive datatype property", "ex:d a owl:DatatypeProperty, owl:TransitiveProperty ."),
        ],
        [ttl("transitive object property", "ex:o a owl:ObjectProperty, owl:TransitiveProperty .")],
    ),
    "OWL010": rule_cases(
        [ttl("one-operand chain", "ex:p a owl:ObjectProperty ; owl:propertyChainAxiom ( ex:q ) .")],
        [ttl("two-operand chain", "ex:p a owl:ObjectProperty ; owl:propertyChainAxiom ( ex:q ex:r ) .")],
    ),
    "OWL011": rule_cases(
        [
            ttl(
                "allValuesFrom alone (blank-node focus)",
                "[] a owl:Restriction ; owl:onProperty ex:p ; owl:allValuesFrom ex:A .",
            )
        ],
        [
            ttl(
                "with someValuesFrom",
                "[] a owl:Restriction ; owl:onProperty ex:p ; owl:allValuesFrom ex:A ; owl:someValuesFrom ex:A .",
            )
        ],
    ),
    "OWL013": rule_cases(
        [ttl("object property with literal value", 'ex:p a owl:ObjectProperty . ex:i ex:p "text" .')],
        [ttl("object property with resource value", "ex:p a owl:ObjectProperty . ex:i ex:p ex:j .")],
    ),
    "OWL014": rule_cases(
        [ttl("datatype property with resource value", "ex:d a owl:DatatypeProperty . ex:i ex:d ex:j .")],
        [ttl("datatype property with literal value", 'ex:d a owl:DatatypeProperty . ex:i ex:d "text" .')],
    ),
    "OWL015": rule_cases(
        [ttl("undeclared local predicate", "ex:i ex:q ex:j .", base="https://example.test/onto#")],
        [
            ttl(
                "declared predicate", "ex:q a owl:ObjectProperty . ex:i ex:q ex:j .", base="https://example.test/onto#"
            ),
            ttl("no base namespace configured", "ex:i ex:q ex:j ."),
            ttl("foreign predicate", "ex:i <https://other.test/q> ex:j .", base="https://example.test/onto#"),
        ],
    ),
    "DATA001": rule_cases(
        [
            ttl(
                "string where xsd:integer is the range",
                'ex:d a owl:DatatypeProperty ; rdfs:range xsd:integer . ex:i ex:d "x" .',
            ),
            *(
                ttl(
                    f"{value} is outside xsd:{range_}",
                    f"ex:d a owl:DatatypeProperty ; rdfs:range xsd:{range_} . ex:i ex:d {value} .",
                )
                for range_, value in (
                    ("positiveInteger", "0"),
                    ("nonNegativeInteger", "-1"),
                    ("negativeInteger", "0"),
                    ("byte", "128"),
                    ("byte", "-129"),
                    ("unsignedByte", "256"),
                    ("int", "2147483648"),
                    ("integer", "1.5"),
                    ("positiveInteger", '"abc"^^xsd:integer'),
                )
            ),
        ],
        [
            ttl(
                "matching datatype",
                'ex:d a owl:DatatypeProperty ; rdfs:range xsd:integer . ex:i ex:d "1"^^xsd:integer .',
            ),
            ttl(
                "plain literal for xsd:string", 'ex:d a owl:DatatypeProperty ; rdfs:range xsd:string . ex:i ex:d "x" .'
            ),
            # A Turtle number is xsd:integer; it fits a narrower integer range by value (OWL 2 value spaces).
            *(
                ttl(
                    f"{value} fits xsd:{range_}",
                    f"ex:d a owl:DatatypeProperty ; rdfs:range xsd:{range_} . ex:i ex:d {value} .",
                )
                for range_, value in (
                    ("positiveInteger", "1"),
                    ("nonNegativeInteger", "0"),
                    ("nonPositiveInteger", "0"),
                    ("negativeInteger", "-1"),
                    ("byte", "127"),
                    ("byte", "-128"),
                    ("unsignedByte", "255"),
                    ("int", "2147483647"),
                    ("long", "-9223372036854775808"),
                    ("unsignedLong", "18446744073709551615"),
                    ("decimal", "7"),
                )
            ),
        ],
    ),
    "DATA002": rule_cases(
        [
            ttl(
                "usage implies a disjoint domain",
                "ex:p a owl:ObjectProperty ; rdfs:domain ex:A . ex:A owl:disjointWith ex:B . ex:i a ex:B ; ex:p ex:j .",
            )
        ],
        [ttl("no disjointness axiom", "ex:p a owl:ObjectProperty ; rdfs:domain ex:A . ex:i a ex:B ; ex:p ex:j .")],
    ),
}
