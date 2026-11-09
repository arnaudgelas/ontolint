"""Cases for OWL031-OWL045 (class expressions, restrictions, individuals)."""

from __future__ import annotations

from rule_harness import rule_cases, ttl

R = "[] a owl:Restriction ; owl:onProperty ex:p ;"
OP = "ex:p a owl:ObjectProperty . ex:DP a owl:DatatypeProperty ."
CLASSES = "ex:A a owl:Class . ex:B a owl:Class ."

CASES = {
    "OWL031": rule_cases(
        [
            ttl("empty union", "ex:C owl:unionOf () ."),
            ttl("empty oneOf", "ex:C owl:oneOf rdf:nil ."),
            ttl("union points to a literal", 'ex:C owl:unionOf "ex:A ex:B" .'),
            ttl("union points to a class", "ex:C owl:unionOf ex:A ."),
            ttl("cyclic list", "ex:C owl:intersectionOf _:l . _:l rdf:first ex:A ; rdf:rest _:l ."),
            ttl("list node without rest", "ex:C owl:unionOf _:l . _:l rdf:first ex:A ."),
            ttl("empty disjointUnionOf", "ex:C owl:disjointUnionOf () ."),
        ],
        [
            ttl("union of two", "ex:C owl:unionOf ( ex:A ex:B ) ."),
            ttl("oneOf individuals", "ex:C owl:oneOf ( ex:i ex:j ) ."),
        ],
    ),
    "OWL032": rule_cases(
        [
            ttl("one-operand union", "ex:C owl:unionOf ( ex:A ) ."),
            ttl("one-operand intersection", "ex:C owl:intersectionOf ( ex:A ) ."),
        ],
        [
            ttl("two operands", "ex:C owl:intersectionOf ( ex:A ex:B ) ."),
            ttl("single-member oneOf is fine", "ex:C owl:oneOf ( ex:i ) ."),
            ttl("malformed list is OWL031 only", "ex:C owl:unionOf _:l . _:l rdf:first ex:A ."),
        ],
    ),
    "OWL033": rule_cases(
        [
            ttl("duplicate union member", "ex:C owl:unionOf ( ex:A ex:B ex:A ) ."),
            ttl("duplicate oneOf individual", "ex:C owl:oneOf ( ex:i ex:i ) ."),
        ],
        [
            ttl("distinct members", "ex:C owl:unionOf ( ex:A ex:B ) ."),
            ttl("distinct anonymous members", "ex:C owl:unionOf ( [ a owl:Class ] [ a owl:Class ] ) ."),
        ],
    ),
    "OWL034": rule_cases(
        [
            ttl("no onProperty", "[] a owl:Restriction ; owl:someValuesFrom ex:A ."),
            ttl("two onProperty", "[] a owl:Restriction ; owl:onProperty ex:p, ex:q ; owl:someValuesFrom ex:A ."),
            ttl("literal onProperty", '[] a owl:Restriction ; owl:onProperty "p" ; owl:someValuesFrom ex:A .'),
        ],
        [
            ttl("one onProperty", f"{R} owl:someValuesFrom ex:A ."),
            ttl("onProperties", "[] a owl:Restriction ; owl:onProperties ( ex:d1 ex:d2 ) ; owl:allValuesFrom ex:R ."),
        ],
    ),
    "OWL035": rule_cases(
        [
            ttl("bare restriction", f"{R} a owl:Restriction ."),
            ttl("only onClass", f"{R} owl:onClass ex:A ."),
        ],
        [
            ttl("someValuesFrom", f"{R} owl:someValuesFrom ex:A ."),
            ttl("hasSelf", f'{R} owl:hasSelf "true"^^xsd:boolean .'),
            ttl("cardinality", f'{R} owl:minCardinality "1"^^xsd:nonNegativeInteger .'),
        ],
    ),
    "OWL036": rule_cases(
        [
            ttl("negative cardinality", f'{R} owl:minCardinality "-1"^^xsd:integer .'),
            ttl("decimal cardinality", f'{R} owl:cardinality "1.5"^^xsd:decimal .'),
            ttl("resource cardinality", f"{R} owl:maxCardinality ex:two ."),
            ttl("word cardinality", f'{R} owl:maxCardinality "two" .'),
            ttl("qualified without class", f'{R} owl:minQualifiedCardinality "1"^^xsd:nonNegativeInteger .'),
        ],
        [
            ttl("valid cardinality", f'{R} owl:minCardinality "2"^^xsd:nonNegativeInteger .'),
            ttl("plain integer literal", f"{R} owl:maxCardinality 3 ."),
            ttl(
                "qualified with class",
                f'{R} owl:minQualifiedCardinality "1"^^xsd:nonNegativeInteger ; owl:onClass ex:A .',
            ),
            ttl("qualified with data range", f"{R} owl:maxQualifiedCardinality 1 ; owl:onDataRange xsd:string ."),
            # xsd:nonNegativeInteger allows a sign: "+" always, "-" only before a zero.
            ttl("negative zero", f'{R} owl:maxCardinality "-0" .'),
            ttl("explicit plus sign", f'{R} owl:minCardinality "+2" .'),
        ],
    ),
    "OWL037": rule_cases(
        [
            ttl("min above max", f"{R} owl:minCardinality 3 ; owl:maxCardinality 2 ."),
            ttl("exact below min", f"{R} owl:cardinality 1 ; owl:minCardinality 2 ."),
            ttl("exact conflicting", f"{R} owl:cardinality 1 ; owl:cardinality 2 ."),
            ttl(
                "qualified min above max",
                f"{R} owl:onClass ex:A ; owl:minQualifiedCardinality 5 ; owl:maxQualifiedCardinality 1 .",
            ),
        ],
        [
            ttl("min equals max", f"{R} owl:minCardinality 2 ; owl:maxCardinality 2 ."),
            ttl("min below max", f"{R} owl:minCardinality 1 ; owl:maxCardinality 4 ."),
            ttl("invalid values are not compared", f'{R} owl:minCardinality "x" ; owl:maxCardinality 0 .'),
            ttl(
                "qualified min and unqualified max are different groups",
                f"{R} owl:onClass ex:A ; owl:minCardinality 1 ; owl:maxQualifiedCardinality 0 .",
            ),
        ],
    ),
    "OWL038": rule_cases(
        [
            ttl("someValuesFrom Nothing", f"{R} owl:someValuesFrom owl:Nothing ."),
            ttl("min 1 on Nothing", f"{R} owl:onClass owl:Nothing ; owl:minQualifiedCardinality 1 ."),
            ttl("exact 2 on Nothing", f"{R} owl:onClass owl:Nothing ; owl:qualifiedCardinality 2 ."),
        ],
        [
            ttl("allValuesFrom Nothing is satisfiable", f"{R} owl:allValuesFrom owl:Nothing ."),
            ttl("min 0 on Nothing", f"{R} owl:onClass owl:Nothing ; owl:minQualifiedCardinality 0 ."),
            ttl("max on Nothing", f"{R} owl:onClass owl:Nothing ; owl:maxQualifiedCardinality 3 ."),
            ttl("someValuesFrom Thing", f"{R} owl:someValuesFrom owl:Thing ."),
        ],
    ),
    "OWL039": rule_cases(
        [
            ttl("allValuesFrom Thing", f"{R} owl:allValuesFrom owl:Thing ."),
            ttl("min cardinality 0", f"{R} owl:minCardinality 0 ."),
            ttl("qualified min 0", f"{R} owl:onClass ex:A ; owl:minQualifiedCardinality 0 ."),
            ttl("min cardinality written -0", f'{R} owl:minCardinality "-0" .'),
        ],
        [
            ttl("allValuesFrom a class", f"{R} owl:allValuesFrom ex:A ."),
            ttl("min cardinality 1", f"{R} owl:minCardinality 1 ."),
            ttl("max cardinality 0", f"{R} owl:maxCardinality 0 ."),
        ],
    ),
    "OWL040": rule_cases(
        [
            ttl(
                "literal hasValue on object property",
                f'{OP} [] a owl:Restriction ; owl:onProperty ex:p ; owl:hasValue "x" .',
            ),
            ttl(
                "datatype filler on object property",
                f"{OP} [] a owl:Restriction ; owl:onProperty ex:p ; owl:someValuesFrom xsd:string .",
            ),
            ttl(
                "resource hasValue on datatype property",
                f"{OP} [] a owl:Restriction ; owl:onProperty ex:DP ; owl:hasValue ex:i .",
            ),
            ttl(
                "class filler on datatype property",
                f"{OP} {CLASSES} [] a owl:Restriction ; owl:onProperty ex:DP ; owl:allValuesFrom ex:A .",
            ),
            ttl(
                "owl:Thing filler on datatype property",
                f"{OP} [] a owl:Restriction ; owl:onProperty ex:DP ; owl:someValuesFrom owl:Thing .",
            ),
            ttl(
                "onDataRange on object property",
                f"{OP} {R} owl:onDataRange xsd:string ; owl:minQualifiedCardinality 1 .",
            ),
        ],
        [
            ttl(
                "class filler on object property",
                f"{OP} {CLASSES} [] a owl:Restriction ; owl:onProperty ex:p ; owl:someValuesFrom ex:A .",
            ),
            ttl(
                "literal hasValue on datatype property",
                f'{OP} [] a owl:Restriction ; owl:onProperty ex:DP ; owl:hasValue "x" .',
            ),
            ttl(
                "datatype filler on datatype property",
                f"{OP} [] a owl:Restriction ; owl:onProperty ex:DP ; owl:someValuesFrom xsd:integer .",
            ),
            ttl(
                "undeclared property is not judged",
                f"{CLASSES} [] a owl:Restriction ; owl:onProperty ex:u ; owl:hasValue ex:i .",
            ),
            ttl(
                "property typed as both is not judged",
                '[] a owl:Restriction ; owl:onProperty ex:both ; owl:hasValue "x" .\n'
                "ex:both a owl:ObjectProperty, owl:DatatypeProperty .",
            ),
            ttl(
                "custom datatype filler on datatype property",
                f"{OP} ex:Dt a rdfs:Datatype .\n"
                "[] a owl:Restriction ; owl:onProperty ex:DP ; owl:someValuesFrom ex:Dt .",
            ),
        ],
    ),
    "OWL041": rule_cases(
        [
            ttl("self complement", "ex:A owl:complementOf ex:A ."),
            ttl(
                "three-cycle", "ex:A owl:complementOf ex:B . ex:B owl:complementOf ex:C . ex:C owl:complementOf ex:A ."
            ),
            ttl("anonymous self complement", "_:x owl:complementOf _:x ."),
        ],
        [
            ttl("two-cycle is consistent", "ex:A owl:complementOf ex:B . ex:B owl:complementOf ex:A ."),
            ttl("single complement", "ex:A owl:complementOf ex:B ."),
            ttl(
                "four-cycle is consistent",
                "ex:A owl:complementOf ex:B . ex:B owl:complementOf ex:C .\n"
                "ex:C owl:complementOf ex:D . ex:D owl:complementOf ex:A .",
            ),
            ttl("literal operand", 'ex:A owl:complementOf "x" .'),
        ],
    ),
    "OWL042": rule_cases(
        [
            ttl("subclass of own complement", f"{CLASSES} ex:A rdfs:subClassOf [ owl:complementOf ex:A ] ."),
            ttl("equivalent to own complement", f"{CLASSES} ex:A owl:equivalentClass [ owl:complementOf ex:A ] ."),
            ttl("named complement", "ex:A rdfs:subClassOf ex:N . ex:N owl:complementOf ex:A ."),
        ],
        [
            ttl("subclass of another complement", f"{CLASSES} ex:A rdfs:subClassOf [ owl:complementOf ex:B ] ."),
            ttl("complement subclass of the class", f"{CLASSES} [ owl:complementOf ex:A ] rdfs:subClassOf ex:A ."),
        ],
    ),
    "OWL043": rule_cases(
        [
            ttl("intersection with complement", "ex:C owl:intersectionOf ( ex:A [ owl:complementOf ex:A ] ) ."),
            ttl("union with complement", "_:n owl:complementOf ex:A . ex:C owl:unionOf ( ex:A _:n ) ."),
            ttl(
                "intersection of disjoint classes",
                "ex:A owl:disjointWith ex:B . ex:C owl:intersectionOf ( ex:A ex:B ) .",
            ),
            ttl("intersection with Nothing", "ex:C owl:intersectionOf ( ex:A owl:Nothing ) ."),
            ttl("union with Thing", "ex:C owl:unionOf ( ex:A owl:Thing ) ."),
        ],
        [
            ttl("union of disjoint classes is fine", "ex:A owl:disjointWith ex:B . ex:C owl:unionOf ( ex:A ex:B ) ."),
            ttl("intersection with Thing is fine", "ex:C owl:intersectionOf ( ex:A owl:Thing ) ."),
            ttl("union with Nothing is fine", "ex:C owl:unionOf ( ex:A owl:Nothing ) ."),
            ttl("complement of an unrelated class", "ex:C owl:intersectionOf ( ex:A [ owl:complementOf ex:B ] ) ."),
            # The boundary with OWL025: disjoint classes linked by a subclass or equivalence *axiom* are OWL025's.
            ttl("disjoint with its superclass (OWL025)", "ex:A owl:disjointWith ex:B ; rdfs:subClassOf ex:B ."),
            ttl("disjoint with its equivalent (OWL025)", "ex:A owl:disjointWith ex:B ; owl:equivalentClass ex:B ."),
        ],
    ),
    "OWL044": rule_cases(
        [
            ttl("transitive same", "ex:a owl:sameAs ex:b . ex:b owl:sameAs ex:c . ex:a owl:differentFrom ex:c ."),
            ttl(
                "same through a shared individual",
                "ex:a owl:sameAs ex:m . ex:b owl:sameAs ex:m . ex:a owl:differentFrom ex:b .",
            ),
            ttl(
                "AllDifferent with same members",
                "ex:a owl:sameAs ex:b . [] a owl:AllDifferent ; owl:members ( ex:a ex:b ex:c ) .",
            ),
        ],
        [
            ttl("same only", "ex:a owl:sameAs ex:b ."),
            ttl("different only", "ex:a owl:differentFrom ex:b ."),
            ttl("unrelated", "ex:a owl:sameAs ex:b . ex:c owl:differentFrom ex:a ."),
            # Direct conflicts are OWL026's, so one defect is not reported twice.
            ttl("direct same and different", "ex:a owl:sameAs ex:b ; owl:differentFrom ex:b ."),
            ttl("direct reversed same", "ex:b owl:sameAs ex:a . ex:a owl:differentFrom ex:b ."),
            ttl("different from self", "ex:a owl:differentFrom ex:a ."),
            ttl("literal object", 'ex:a owl:sameAs "x" ; owl:differentFrom "x" .'),
            ttl(
                "AllDifferent distinct",
                "ex:a owl:sameAs ex:b . [] a owl:AllDifferent ; owl:distinctMembers ( ex:a ex:c ) .",
            ),
        ],
    ),
    "OWL045": rule_cases(
        [
            ttl("AllDifferent without list", "[] a owl:AllDifferent ."),
            ttl("AllDifferent one member", "[] a owl:AllDifferent ; owl:members ( ex:a ) ."),
            ttl("AllDifferent duplicate", "[] a owl:AllDifferent ; owl:distinctMembers ( ex:a ex:b ex:a ) ."),
            ttl("AllDifferent malformed", "[] a owl:AllDifferent ; owl:members _:l . _:l rdf:first ex:a ."),
            ttl(
                "AllDifferent two lists",
                "[] a owl:AllDifferent ; owl:members ( ex:a ex:b ) ; owl:distinctMembers ( ex:c ex:d ) .",
            ),
            ttl("AllDisjointClasses empty", "[] a owl:AllDisjointClasses ; owl:members () ."),
            ttl("AllDisjointClasses duplicate", "[] a owl:AllDisjointClasses ; owl:members ( ex:A ex:A ) ."),
            ttl("AllDifferent members literal", '[] a owl:AllDifferent ; owl:members "x" .'),
        ],
        [
            ttl("AllDifferent fine", "[] a owl:AllDifferent ; owl:distinctMembers ( ex:a ex:b ) ."),
            ttl("AllDisjointClasses fine", "[] a owl:AllDisjointClasses ; owl:members ( ex:A ex:B ex:C ) ."),
            ttl("untyped members", "[] owl:members ( ex:a ) ."),
        ],
    ),
}
