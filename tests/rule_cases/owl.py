"""Cases for OWL001-OWL011, OWL013-OWL015, DATA001 and DATA002.

Each condition of a rule's specification (module docstring of :mod:`ontolint.rules.owl`) has a
positive case and each exclusion a negative case.
"""

from __future__ import annotations

from rule_harness import rule_cases, ttl

BASE = "https://example.test/onto#"
FOREIGN = "https://other.example.test/vocab#"

CASES = {
    "OWL001": rule_cases(
        [
            ttl("undeclared superclass", "ex:A a owl:Class ; rdfs:subClassOf ex:Undeclared ."),
            ttl("undeclared subclass", "ex:Undeclared rdfs:subClassOf ex:A . ex:A a owl:Class ."),
            ttl(
                "declared only as a property",
                "ex:p a owl:ObjectProperty ; rdfs:subClassOf ex:A . ex:A a owl:Class .",
            ),
        ],
        [
            ttl("declared superclass", "ex:A a owl:Class ; rdfs:subClassOf ex:B . ex:B a owl:Class ."),
            ttl("declared rdfs:Class", "ex:A a rdfs:Class ; rdfs:subClassOf ex:B . ex:B a rdfs:Class ."),
            ttl("owl:Thing is exempt", "ex:A a owl:Class ; rdfs:subClassOf owl:Thing ."),
            ttl("owl:Nothing is exempt", "owl:Nothing rdfs:subClassOf ex:A . ex:A a owl:Class ."),
            ttl(
                "anonymous superclass",
                "ex:A a owl:Class ; rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:p ; "
                "owl:someValuesFrom ex:A ] . ex:p a owl:ObjectProperty .",
            ),
            ttl("foreign superclass", f"ex:A a owl:Class ; rdfs:subClassOf <{FOREIGN}Agent> .", base=BASE),
        ],
    ),
    "OWL002": rule_cases(
        [
            ttl("domain on an undeclared property", "ex:p rdfs:domain ex:A . ex:A a owl:Class ."),
            ttl("range on an undeclared property", "ex:p rdfs:range ex:A . ex:A a owl:Class ."),
            ttl(
                "typed only by a characteristic",
                "ex:p a owl:TransitiveProperty ; rdfs:domain ex:A . ex:A a owl:Class .",
            ),
        ],
        [
            ttl("declared property", "ex:p a owl:ObjectProperty ; rdfs:domain ex:A . ex:A a owl:Class ."),
            ttl("declared rdf:Property", "ex:p a rdf:Property ; rdfs:range ex:A . ex:A a owl:Class ."),
            ttl("foreign property", f"<{FOREIGN}p> rdfs:domain ex:A . ex:A a owl:Class .", base=BASE),
        ],
    ),
    "OWL003": rule_cases(
        [
            ttl("object and datatype property", "ex:p a owl:ObjectProperty, owl:DatatypeProperty ."),
            ttl(
                "foreign property typed both",
                f"<{FOREIGN}p> a owl:ObjectProperty, owl:DatatypeProperty .",
                base=BASE,
            ),
        ],
        [
            ttl("object property only", "ex:p a owl:ObjectProperty ."),
            ttl("datatype property only", "ex:p a owl:DatatypeProperty ."),
            ttl("object and annotation property (OWL030)", "ex:p a owl:ObjectProperty, owl:AnnotationProperty ."),
        ],
    ),
    "OWL004": rule_cases(
        [
            ttl("two domains", "ex:p a owl:ObjectProperty ; rdfs:domain ex:A, ex:B ."),
            ttl("two ranges", "ex:p a owl:ObjectProperty ; rdfs:range ex:A, ex:B ."),
            ttl(
                "a named and an anonymous domain",
                "ex:p a owl:ObjectProperty ; rdfs:domain ex:A, [ owl:unionOf ( ex:B ex:C ) ] .",
            ),
        ],
        [
            ttl("single domain and range", "ex:p a owl:ObjectProperty ; rdfs:domain ex:A ; rdfs:range ex:B ."),
            ttl("one union domain", "ex:p a owl:ObjectProperty ; rdfs:domain [ owl:unionOf ( ex:A ex:B ) ] ."),
            ttl("undeclared property (OWL002)", "ex:p rdfs:domain ex:A, ex:B ."),
            ttl(
                "foreign property",
                f"<{FOREIGN}p> a owl:ObjectProperty ; rdfs:domain ex:A, ex:B .",
                base=BASE,
            ),
        ],
    ),
    "OWL005": rule_cases(
        [
            ttl("no domain", "ex:p a owl:ObjectProperty ."),
            ttl("datatype property without domain", "ex:d a owl:DatatypeProperty ."),
            ttl("rdf:Property without domain", "ex:p a rdf:Property ."),
            ttl(
                "annotation property also typed object property",
                "ex:p a owl:AnnotationProperty, owl:ObjectProperty .",
            ),
        ],
        [
            ttl("domain asserted", "ex:p a owl:ObjectProperty ; rdfs:domain ex:A ."),
            ttl("schema:domainIncludes", "ex:p a rdf:Property ; <https://schema.org/domainIncludes> ex:A ."),
            ttl("dcam:domainIncludes", "ex:p a rdf:Property ; <http://purl.org/dc/dcam/domainIncludes> ex:A ."),
            ttl("deprecated property", "ex:p a owl:ObjectProperty ; owl:deprecated true ."),
            ttl("annotation property", "ex:p a owl:AnnotationProperty ."),
            ttl("foreign property", f"<{FOREIGN}p> a owl:ObjectProperty .", base=BASE),
        ],
    ),
    "OWL006": rule_cases(
        [
            ttl("no range", "ex:p a owl:ObjectProperty ."),
            ttl("datatype property without range", "ex:d a owl:DatatypeProperty ."),
            ttl("rdf:Property without range", "ex:p a rdf:Property ."),
        ],
        [
            ttl("range asserted", "ex:p a owl:ObjectProperty ; rdfs:range ex:A ."),
            ttl("schema:rangeIncludes", "ex:p a rdf:Property ; <http://schema.org/rangeIncludes> ex:A ."),
            ttl("dcam:rangeIncludes", "ex:p a rdf:Property ; <http://purl.org/dc/dcam/rangeIncludes> ex:A ."),
            ttl("deprecated property", 'ex:p a owl:ObjectProperty ; owl:deprecated "true"^^xsd:boolean .'),
            ttl("annotation property", "ex:p a owl:AnnotationProperty ."),
            ttl("foreign property", f"<{FOREIGN}p> a owl:ObjectProperty .", base=BASE),
        ],
    ),
    "OWL007": rule_cases(
        [
            ttl("inverse of itself", "ex:p a owl:ObjectProperty ; owl:inverseOf ex:p ."),
            ttl("undeclared property inverse of itself", "ex:p owl:inverseOf ex:p ."),
        ],
        [
            ttl(
                "inverse of another property",
                "ex:p a owl:ObjectProperty ; owl:inverseOf ex:q . ex:q a owl:ObjectProperty .",
            ),
            ttl("symmetric property", "ex:p a owl:ObjectProperty, owl:SymmetricProperty ."),
        ],
    ),
    "OWL008": rule_cases(
        [
            ttl(
                "symmetric with inverse",
                "ex:p a owl:ObjectProperty, owl:SymmetricProperty ; owl:inverseOf ex:q . ex:q a owl:ObjectProperty .",
            ),
            ttl(
                "symmetric named as the inverse",
                "ex:q a owl:ObjectProperty ; owl:inverseOf ex:p . ex:p a owl:ObjectProperty, owl:SymmetricProperty .",
            ),
        ],
        [
            ttl("inverse only", "ex:p a owl:ObjectProperty ; owl:inverseOf ex:q . ex:q a owl:ObjectProperty."),
            ttl("symmetric only", "ex:p a owl:ObjectProperty, owl:SymmetricProperty ."),
            ttl(
                "symmetric and inverse of itself (OWL007)",
                "ex:p a owl:ObjectProperty, owl:SymmetricProperty ; owl:inverseOf ex:p .",
            ),
        ],
    ),
    "OWL009": rule_cases(
        [
            ttl(
                "inverse of a datatype property",
                "ex:d a owl:DatatypeProperty ; owl:inverseOf ex:o . ex:o a owl:ObjectProperty .",
            ),
            ttl(
                "datatype property named as the inverse",
                "ex:o a owl:ObjectProperty ; owl:inverseOf ex:d . ex:d a owl:DatatypeProperty .",
            ),
            ttl("transitive datatype property", "ex:d a owl:DatatypeProperty, owl:TransitiveProperty ."),
            ttl("symmetric datatype property", "ex:d a owl:DatatypeProperty, owl:SymmetricProperty ."),
            ttl("asymmetric datatype property", "ex:d a owl:DatatypeProperty, owl:AsymmetricProperty ."),
            ttl(
                "inverse-functional datatype property",
                "ex:d a owl:DatatypeProperty, owl:InverseFunctionalProperty .",
            ),
        ],
        [
            ttl("transitive object property", "ex:o a owl:ObjectProperty, owl:TransitiveProperty ."),
            ttl("functional datatype property", "ex:d a owl:DatatypeProperty, owl:FunctionalProperty ."),
            ttl("reflexive datatype property (OWL016)", "ex:d a owl:DatatypeProperty, owl:ReflexiveProperty ."),
            ttl(
                "inverse between object properties",
                "ex:o a owl:ObjectProperty ; owl:inverseOf ex:q . ex:q a owl:ObjectProperty .",
            ),
        ],
    ),
    "OWL010": rule_cases(
        [
            ttl("one-operand chain", "ex:p a owl:ObjectProperty ; owl:propertyChainAxiom ( ex:q ) ."),
            ttl("one-operand chain on an undeclared property", "ex:p owl:propertyChainAxiom ( ex:q ) ."),
        ],
        [
            ttl("two-operand chain", "ex:p a owl:ObjectProperty ; owl:propertyChainAxiom ( ex:q ex:r ) ."),
            ttl(
                "malformed list (not an RDF list)",
                "ex:p a owl:ObjectProperty ; owl:propertyChainAxiom _:l . _:l rdf:first ex:q .",
            ),
        ],
    ),
    "OWL011": rule_cases(
        [
            ttl(
                "allValuesFrom alone (blank-node focus)",
                "[] a owl:Restriction ; owl:onProperty ex:p ; owl:allValuesFrom ex:A .",
            ),
            ttl(
                "superclass restriction of a named class",
                "ex:A a owl:Class ; rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:p ; "
                "owl:allValuesFrom ex:B ] .",
            ),
            ttl(
                "general class axiom",
                "[ a owl:Restriction ; owl:onProperty ex:p ; owl:allValuesFrom ex:B ] rdfs:subClassOf ex:A .",
            ),
            ttl(
                "existence on another property",
                "ex:A a owl:Class ; rdfs:subClassOf "
                "[ a owl:Restriction ; owl:onProperty ex:p ; owl:allValuesFrom ex:B ] , "
                "[ a owl:Restriction ; owl:onProperty ex:q ; owl:someValuesFrom ex:B ] .",
            ),
            ttl(
                "minimum cardinality 0 is no existence",
                "ex:A a owl:Class ; rdfs:subClassOf "
                "[ a owl:Restriction ; owl:onProperty ex:p ; owl:allValuesFrom ex:B ] , "
                '[ a owl:Restriction ; owl:onProperty ex:p ; owl:minCardinality "0"^^xsd:nonNegativeInteger ] .',
            ),
        ],
        [
            ttl(
                "with someValuesFrom",
                "[] a owl:Restriction ; owl:onProperty ex:p ; owl:allValuesFrom ex:A ; owl:someValuesFrom ex:A .",
            ),
            ttl(
                "closure axiom: someValuesFrom on the same class",
                "ex:A a owl:Class ; rdfs:subClassOf "
                "[ a owl:Restriction ; owl:onProperty ex:p ; owl:allValuesFrom ex:B ] , "
                "[ a owl:Restriction ; owl:onProperty ex:p ; owl:someValuesFrom ex:B ] .",
            ),
            ttl(
                "minimum cardinality 1 on the same class",
                "ex:A a owl:Class ; rdfs:subClassOf "
                "[ a owl:Restriction ; owl:onProperty ex:p ; owl:allValuesFrom ex:B ] , "
                '[ a owl:Restriction ; owl:onProperty ex:p ; owl:minCardinality "1"^^xsd:nonNegativeInteger ] .',
            ),
            ttl(
                "hasValue in the same intersection",
                "ex:A a owl:Class ; owl:equivalentClass [ owl:intersectionOf ( ex:C "
                "[ a owl:Restriction ; owl:onProperty ex:p ; owl:allValuesFrom ex:B ] "
                "[ a owl:Restriction ; owl:onProperty ex:p ; owl:hasValue ex:b ] ) ] .",
            ),
            ttl("datatype filler", "[] a owl:Restriction ; owl:onProperty ex:p ; owl:allValuesFrom xsd:integer ."),
            ttl(
                "declared datatype filler",
                "ex:D a rdfs:Datatype . [] a owl:Restriction ; owl:onProperty ex:p ; owl:allValuesFrom ex:D .",
            ),
            ttl(
                "datatype restriction filler",
                "[] a owl:Restriction ; owl:onProperty ex:p ; owl:allValuesFrom "
                "[ a rdfs:Datatype ; owl:onDatatype xsd:integer ; owl:withRestrictions ( [ xsd:minInclusive 0 ] ) ] .",
            ),
            ttl(
                "datatype property",
                "ex:d a owl:DatatypeProperty . [] a owl:Restriction ; owl:onProperty ex:d ; owl:allValuesFrom ex:A .",
            ),
            ttl(
                "axiom of a foreign class",
                f"<{FOREIGN}A> rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:p ; owl:allValuesFrom ex:B ] .",
                base=BASE,
            ),
        ],
    ),
    "OWL013": rule_cases(
        [
            ttl("object property with literal value", 'ex:p a owl:ObjectProperty . ex:i ex:p "text" .'),
            ttl(
                "foreign object property with a typed literal",
                f'<{FOREIGN}p> a owl:ObjectProperty . ex:i <{FOREIGN}p> "1"^^xsd:integer .',
                base=BASE,
            ),
        ],
        [
            ttl("object property with resource value", "ex:p a owl:ObjectProperty . ex:i ex:p ex:j ."),
            ttl("object property with blank-node value", "ex:p a owl:ObjectProperty . ex:i ex:p [] ."),
            ttl("undeclared predicate with literal", 'ex:i ex:p "text" .'),
        ],
    ),
    "OWL014": rule_cases(
        [
            ttl("datatype property with resource value", "ex:d a owl:DatatypeProperty . ex:i ex:d ex:j ."),
            ttl("datatype property with blank-node value", "ex:d a owl:DatatypeProperty . ex:i ex:d [] ."),
        ],
        [
            ttl("datatype property with literal value", 'ex:d a owl:DatatypeProperty . ex:i ex:d "text" .'),
            ttl("undeclared predicate with resource", "ex:i ex:d ex:j ."),
        ],
    ),
    "OWL015": rule_cases(
        [
            ttl("undeclared local predicate", "ex:i ex:q ex:j .", base=BASE),
            ttl(
                "typed only by a characteristic",
                "ex:q a owl:TransitiveProperty . ex:i ex:q ex:j .",
                base=BASE,
            ),
        ],
        [
            ttl("declared predicate", "ex:q a owl:ObjectProperty . ex:i ex:q ex:j .", base=BASE),
            ttl("declared annotation property", 'ex:q a owl:AnnotationProperty . ex:i ex:q "x" .', base=BASE),
            ttl("no base namespace configured", "ex:i ex:q ex:j ."),
            ttl("foreign predicate", "ex:i <https://other.example.test/q> ex:j .", base=BASE),
            ttl("built-in predicate", 'ex:i rdfs:label "i" .', base=BASE),
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
