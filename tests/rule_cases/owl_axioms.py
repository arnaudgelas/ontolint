"""Cases for OWL016-OWL030 (property characteristics and axiom conflicts)."""

from __future__ import annotations

from rule_harness import rule_cases, ttl

CASES = {
    "OWL016": rule_cases(
        [
            ttl("reflexive datatype property", "ex:d a owl:DatatypeProperty, owl:ReflexiveProperty ."),
            ttl("irreflexive datatype property", "ex:d a owl:DatatypeProperty, owl:IrreflexiveProperty ."),
        ],
        [
            ttl("reflexive object property", "ex:o a owl:ObjectProperty, owl:ReflexiveProperty ."),
            ttl("plain datatype property", "ex:d a owl:DatatypeProperty ."),
        ],
    ),
    "OWL017": rule_cases(
        [ttl("symmetric and asymmetric", "ex:p a owl:ObjectProperty, owl:SymmetricProperty, owl:AsymmetricProperty .")],
        [
            ttl("symmetric only", "ex:p a owl:ObjectProperty, owl:SymmetricProperty ."),
            ttl("asymmetric only", "ex:p a owl:ObjectProperty, owl:AsymmetricProperty ."),
        ],
    ),
    "OWL018": rule_cases(
        [
            ttl(
                "reflexive and irreflexive",
                "ex:p a owl:ObjectProperty, owl:ReflexiveProperty, owl:IrreflexiveProperty .",
            ),
            ttl(
                "reflexive and asymmetric", "ex:p a owl:ObjectProperty, owl:ReflexiveProperty, owl:AsymmetricProperty ."
            ),
        ],
        [
            ttl("reflexive and symmetric", "ex:p a owl:ObjectProperty, owl:ReflexiveProperty, owl:SymmetricProperty ."),
            ttl(
                "irreflexive and asymmetric",
                "ex:p a owl:ObjectProperty, owl:IrreflexiveProperty, owl:AsymmetricProperty .",
            ),
        ],
    ),
    "OWL019": rule_cases(
        [
            ttl("transitive functional", "ex:p a owl:ObjectProperty, owl:TransitiveProperty, owl:FunctionalProperty ."),
            ttl(
                "chain-defined irreflexive",
                "ex:p a owl:ObjectProperty, owl:IrreflexiveProperty ; owl:propertyChainAxiom ( ex:q ex:r ) .",
            ),
        ],
        [
            ttl("transitive alone", "ex:p a owl:ObjectProperty, owl:TransitiveProperty ."),
            ttl("functional alone", "ex:p a owl:ObjectProperty, owl:FunctionalProperty ."),
            ttl(
                "one-operand chain is not non-simple",
                "ex:p a owl:ObjectProperty, owl:FunctionalProperty ; owl:propertyChainAxiom ( ex:q ) .",
            ),
            ttl("chain with functional target absent", "ex:p owl:propertyChainAxiom ( ex:q ex:r ) ."),
        ],
    ),
    "OWL020": rule_cases(
        [
            ttl(
                "three-property cycle",
                "ex:a rdfs:subPropertyOf ex:b . ex:b rdfs:subPropertyOf ex:c . ex:c rdfs:subPropertyOf ex:a .",
            )
        ],
        [
            ttl("acyclic chain", "ex:a rdfs:subPropertyOf ex:b . ex:b rdfs:subPropertyOf ex:c ."),
            ttl(
                "diamond",
                "ex:a rdfs:subPropertyOf ex:b, ex:c . ex:b rdfs:subPropertyOf ex:d . ex:c rdfs:subPropertyOf ex:d .",
            ),
            ttl("self sub-property is not a cycle finding", "ex:a rdfs:subPropertyOf ex:a ."),
        ],
    ),
    "OWL021": rule_cases(
        [
            ttl(
                "object sub-property of datatype property",
                "ex:o a owl:ObjectProperty ; rdfs:subPropertyOf ex:d . ex:d a owl:DatatypeProperty .",
            ),
            ttl(
                "equivalent across kinds",
                "ex:o a owl:ObjectProperty ; owl:equivalentProperty ex:d . ex:d a owl:DatatypeProperty .",
            ),
        ],
        [
            ttl("same kind", "ex:o a owl:ObjectProperty ; rdfs:subPropertyOf ex:p . ex:p a owl:ObjectProperty ."),
            ttl("untyped target", "ex:o a owl:ObjectProperty ; rdfs:subPropertyOf ex:d ."),
            ttl(
                "target typed both kinds is left to OWL003",
                "ex:o a owl:ObjectProperty ; rdfs:subPropertyOf ex:d .\n"
                "ex:d a owl:DatatypeProperty, owl:ObjectProperty .",
            ),
        ],
    ),
    "OWL022": rule_cases(
        [
            ttl("object property with xsd range", "ex:o a owl:ObjectProperty ; rdfs:range xsd:string ."),
            ttl("object property with rdfs:Literal range", "ex:o a owl:ObjectProperty ; rdfs:range rdfs:Literal ."),
            ttl(
                "object property with declared datatype",
                "ex:o a owl:ObjectProperty ; rdfs:range ex:T . ex:T a rdfs:Datatype .",
            ),
            ttl(
                "datatype property with class range",
                "ex:d a owl:DatatypeProperty ; rdfs:range ex:C . ex:C a owl:Class .",
            ),
            ttl("datatype property with owl:Thing range", "ex:d a owl:DatatypeProperty ; rdfs:range owl:Thing ."),
        ],
        [
            ttl("object property with class range", "ex:o a owl:ObjectProperty ; rdfs:range ex:C . ex:C a owl:Class ."),
            ttl("datatype property with xsd range", "ex:d a owl:DatatypeProperty ; rdfs:range xsd:string ."),
            ttl("untyped property", "ex:p rdfs:range xsd:string ."),
            ttl(
                "property typed both kinds is left to OWL003",
                "ex:p a owl:ObjectProperty, owl:DatatypeProperty ; rdfs:range xsd:string .",
            ),
            ttl("datatype property with blank range", "ex:d a owl:DatatypeProperty ; rdfs:range [ a rdfs:Datatype ] ."),
        ],
    ),
    "OWL023": rule_cases(
        [
            ttl("two inverses", "ex:p owl:inverseOf ex:q, ex:r ."),
            ttl("inverses in both directions", "ex:p owl:inverseOf ex:q . ex:r owl:inverseOf ex:p ."),
        ],
        [
            ttl("single inverse", "ex:p owl:inverseOf ex:q ."),
            ttl("same inverse stated both ways", "ex:p owl:inverseOf ex:q . ex:q owl:inverseOf ex:p ."),
        ],
    ),
    "OWL024": rule_cases(
        [
            ttl(
                "disjoint with itself",
                "ex:p propertyDisjointPlaceholder ex:p .".replace(
                    "propertyDisjointPlaceholder", "owl:propertyDisjointWith"
                ),
            ),
            ttl("disjoint sub-property", "ex:p owl:propertyDisjointWith ex:q ; rdfs:subPropertyOf ex:q ."),
            ttl(
                "disjoint equivalent property",
                "ex:q owl:equivalentProperty ex:p . ex:p owl:propertyDisjointWith ex:q .",
            ),
            ttl(
                "all disjoint properties with equivalent members",
                "[] a owl:AllDisjointProperties ; owl:members ( ex:p ex:q ex:r ) . ex:q owl:equivalentProperty ex:r .",
            ),
        ],
        [
            ttl("unrelated disjoint properties", "ex:p owl:propertyDisjointWith ex:q ."),
            ttl(
                "disjoint with a super-property's sibling",
                "ex:p owl:propertyDisjointWith ex:q ; rdfs:subPropertyOf ex:r .",
            ),
            ttl("malformed members list", "[] a owl:AllDisjointProperties ; owl:members ex:p ."),
        ],
    ),
    "OWL025": rule_cases(
        [
            ttl("disjoint with itself", "ex:A a owl:Class ; owl:disjointWith ex:A ."),
            ttl(
                "disjoint with its superclass",
                "ex:A a owl:Class ; rdfs:subClassOf ex:B ; owl:disjointWith ex:B . ex:B a owl:Class .",
            ),
            ttl("disjoint with its equivalent", "ex:A owl:equivalentClass ex:B ; owl:disjointWith ex:B ."),
            ttl(
                "all disjoint classes with a subclass pair",
                "[] a owl:AllDisjointClasses ; owl:members ( ex:A ex:B ) . ex:B rdfs:subClassOf ex:A .",
            ),
        ],
        [
            ttl("unrelated disjoint classes", "ex:A owl:disjointWith ex:B ."),
            ttl("siblings", "ex:A rdfs:subClassOf ex:P ; owl:disjointWith ex:B . ex:B rdfs:subClassOf ex:P ."),
            ttl("disjoint with owl:Nothing", "ex:A owl:disjointWith owl:Nothing ; rdfs:subClassOf owl:Nothing ."),
        ],
    ),
    "OWL026": rule_cases(
        [
            ttl("same and different", "ex:a owl:sameAs ex:b ; owl:differentFrom ex:b ."),
            ttl("reversed same", "ex:a owl:differentFrom ex:b . ex:b owl:sameAs ex:a ."),
            ttl("different from itself", "ex:a owl:differentFrom ex:a ."),
        ],
        [
            ttl("same only", "ex:a owl:sameAs ex:b ."),
            ttl("different only", "ex:a owl:differentFrom ex:b ."),
            ttl("same with a third individual", "ex:a owl:sameAs ex:b ; owl:differentFrom ex:c ."),
        ],
    ),
    "OWL027": rule_cases(
        [
            ttl(
                "negated individual assertion that is asserted",
                "ex:a ex:p ex:b . [] a owl:NegativePropertyAssertion ; owl:sourceIndividual ex:a ;"
                " owl:assertionProperty ex:p ; owl:targetIndividual ex:b .",
            ),
            ttl(
                "negated value assertion that is asserted",
                'ex:a ex:p "v" . [] a owl:NegativePropertyAssertion ; owl:sourceIndividual ex:a ;'
                ' owl:assertionProperty ex:p ; owl:targetValue "v" .',
            ),
        ],
        [
            ttl(
                "negated assertion that is absent",
                "ex:a ex:p ex:c . [] a owl:NegativePropertyAssertion ; owl:sourceIndividual ex:a ;"
                " owl:assertionProperty ex:p ; owl:targetIndividual ex:b .",
            ),
            ttl(
                "different literal",
                'ex:a ex:p "v" . [] a owl:NegativePropertyAssertion ; owl:sourceIndividual ex:a ;'
                ' owl:assertionProperty ex:p ; owl:targetValue "w" .',
            ),
            ttl("incomplete negative assertion", "[] a owl:NegativePropertyAssertion ; owl:sourceIndividual ex:a ."),
        ],
    ),
    "OWL028": rule_cases(
        [
            ttl(
                "irreflexive property used reflexively",
                "ex:p a owl:ObjectProperty, owl:IrreflexiveProperty . ex:a ex:p ex:a .",
            )
        ],
        [
            ttl(
                "irreflexive property between distinct individuals", "ex:p a owl:IrreflexiveProperty . ex:a ex:p ex:b ."
            ),
            ttl("reflexive use of an ordinary property", "ex:p a owl:ObjectProperty . ex:a ex:p ex:a ."),
        ],
    ),
    "OWL029": rule_cases(
        [
            ttl("both directions", "ex:p a owl:AsymmetricProperty . ex:a ex:p ex:b . ex:b ex:p ex:a ."),
            ttl("self assertion", "ex:p a owl:AsymmetricProperty . ex:a ex:p ex:a ."),
        ],
        [
            ttl("one direction", "ex:p a owl:AsymmetricProperty . ex:a ex:p ex:b ."),
            ttl(
                "both directions on an ordinary property",
                "ex:p a owl:ObjectProperty . ex:a ex:p ex:b . ex:b ex:p ex:a .",
            ),
            ttl("literal value", 'ex:p a owl:AsymmetricProperty . ex:a ex:p "x" .'),
        ],
    ),
    "OWL030": rule_cases(
        [
            ttl("class and datatype", "ex:T a owl:Class, rdfs:Datatype ."),
            ttl("annotation and object property", "ex:p a owl:AnnotationProperty, owl:ObjectProperty ."),
            ttl("annotation and datatype property", "ex:p a owl:AnnotationProperty, owl:DatatypeProperty ."),
        ],
        [
            ttl("class and object property punning is legal", "ex:X a owl:Class, owl:ObjectProperty ."),
            ttl("class and individual punning is legal", "ex:X a owl:Class, owl:NamedIndividual ."),
            ttl("plain annotation property", "ex:p a owl:AnnotationProperty ."),
        ],
    ),
}
