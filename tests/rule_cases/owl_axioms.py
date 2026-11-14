"""Cases for OWL016-OWL030 (property characteristics and axiom conflicts)."""

from __future__ import annotations

from rule_harness import rule_cases, ttl

# One member more than the AllDisjoint* group limit (200): such a group is not read at all.
OVERSIZED_MEMBERS = " ".join(f"ex:m{i}" for i in range(201))

CASES = {
    "OWL016": rule_cases(
        [
            ttl("reflexive datatype property", "ex:d a owl:DatatypeProperty, owl:ReflexiveProperty ."),
            ttl("irreflexive datatype property", "ex:d a owl:DatatypeProperty, owl:IrreflexiveProperty ."),
        ],
        [
            ttl("reflexive object property", "ex:o a owl:ObjectProperty, owl:ReflexiveProperty ."),
            ttl("plain datatype property", "ex:d a owl:DatatypeProperty ."),
            ttl("symmetric datatype property is OWL009's", "ex:d a owl:DatatypeProperty, owl:SymmetricProperty ."),
        ],
    ),
    "OWL017": rule_cases(
        [
            ttl(
                "symmetric and asymmetric", "ex:p a owl:ObjectProperty, owl:SymmetricProperty, owl:AsymmetricProperty ."
            ),
            ttl("no kind declaration needed", "ex:p a owl:SymmetricProperty, owl:AsymmetricProperty ."),
        ],
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
            ttl(
                "transitive inverse-functional",
                "ex:p a owl:ObjectProperty, owl:TransitiveProperty, owl:InverseFunctionalProperty .",
            ),
            ttl("transitive asymmetric", "ex:p a owl:ObjectProperty, owl:TransitiveProperty, owl:AsymmetricProperty ."),
            ttl(
                "chain-defined functional",
                "ex:p a owl:FunctionalProperty ; owl:propertyChainAxiom ( ex:q ex:r ex:s ) .",
            ),
            # SS 11.1: non-simplicity flows from a composite property to every property it reaches through ->*.
            ttl(
                "functional super-property of a transitive property",
                "ex:q a owl:TransitiveProperty ; rdfs:subPropertyOf ex:p . ex:p a owl:FunctionalProperty .",
            ),
            ttl(
                "asymmetric property two sub-property steps above a transitive one",
                "ex:t a owl:TransitiveProperty ; rdfs:subPropertyOf ex:m . ex:m rdfs:subPropertyOf ex:p ."
                " ex:p a owl:AsymmetricProperty .",
            ),
            ttl(
                "inverse-functional inverse of a transitive property",
                "ex:t a owl:TransitiveProperty ; owl:inverseOf ex:p . ex:p a owl:InverseFunctionalProperty .",
            ),
            ttl(
                "functional property whose inverse is a sub-property's inverse",
                "ex:t a owl:TransitiveProperty . ex:p owl:inverseOf ex:t . ex:q a owl:FunctionalProperty ."
                " ex:p rdfs:subPropertyOf ex:q .",
            ),
            ttl(
                "irreflexive equivalent of a chain-defined property",
                "ex:c owl:propertyChainAxiom ( ex:a ex:b ) ; owl:equivalentProperty ex:p ."
                " ex:p a owl:IrreflexiveProperty .",
            ),
            ttl(
                "super-property of a transitive inverse expression (INV rule)",
                "ex:t a owl:TransitiveProperty ; rdfs:subPropertyOf [ owl:inverseOf ex:p ] ."
                " ex:p a owl:FunctionalProperty .",
            ),
            ttl(
                "property whose inverse expression is transitive",
                "[ owl:inverseOf ex:p ] a owl:TransitiveProperty . ex:p a owl:FunctionalProperty .",
            ),
            ttl(
                "property equivalent to the top object property",
                "ex:p owl:equivalentProperty owl:topObjectProperty ; a owl:FunctionalProperty .",
            ),
            # SS 11.2: cardinality restrictions, owl:hasSelf and disjointness take simple properties only.
            ttl(
                "max cardinality on a transitive property",
                "ex:t a owl:ObjectProperty, owl:TransitiveProperty . ex:A rdfs:subClassOf [ a owl:Restriction ;"
                " owl:onProperty ex:t ; owl:maxCardinality 1 ] .",
            ),
            ttl(
                "qualified min cardinality on a super-property of a transitive property",
                "ex:t a owl:TransitiveProperty ; rdfs:subPropertyOf ex:p . [ a owl:Restriction ; owl:onProperty ex:p ;"
                " owl:minQualifiedCardinality 2 ; owl:onClass ex:A ] .",
            ),
            ttl(
                "hasSelf on a chain-defined property",
                "ex:c owl:propertyChainAxiom ( ex:a ex:b ) . [ a owl:Restriction ; owl:onProperty ex:c ;"
                " owl:hasSelf true ] .",
            ),
            ttl(
                "cardinality on the inverse of a transitive property",
                "ex:t a owl:TransitiveProperty . [ a owl:Restriction ; owl:onProperty [ owl:inverseOf ex:t ] ;"
                " owl:cardinality 1 ] .",
            ),
            ttl(
                "transitive property declared disjoint",
                "ex:t a owl:TransitiveProperty ; owl:propertyDisjointWith ex:q .",
            ),
            ttl(
                "simple property declared disjoint with a transitive one",
                "ex:q owl:propertyDisjointWith ex:t . ex:t a owl:TransitiveProperty .",
            ),
            ttl(
                "chain-defined member of owl:AllDisjointProperties",
                "ex:c owl:propertyChainAxiom ( ex:a ex:b ) ."
                " [ a owl:AllDisjointProperties ; owl:members ( ex:p ex:c ) ] .",
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
            ttl(
                "transitive symmetric", "ex:p a owl:TransitiveProperty, owl:SymmetricProperty, owl:ReflexiveProperty ."
            ),
            ttl(
                "malformed chain list is skipped",
                "ex:p a owl:FunctionalProperty ; owl:propertyChainAxiom ex:q .",
            ),
            # Non-simplicity flows upwards only: a sub-property of a transitive property may be simple.
            ttl(
                "functional sub-property of a transitive property",
                "ex:p a owl:FunctionalProperty ; rdfs:subPropertyOf ex:t . ex:t a owl:TransitiveProperty .",
            ),
            ttl(
                "sub-property cycle without a composite member",
                "ex:p rdfs:subPropertyOf ex:q . ex:q rdfs:subPropertyOf ex:p ; a owl:FunctionalProperty .",
            ),
            ttl(
                "super-property of a one-operand chain",
                "ex:c owl:propertyChainAxiom ( ex:a ) ; rdfs:subPropertyOf ex:p . ex:p a owl:FunctionalProperty .",
            ),
            ttl(
                "functional datatype super-property is OWL021's",
                "ex:t a owl:TransitiveProperty ; rdfs:subPropertyOf ex:d . ex:d a owl:DatatypeProperty,"
                " owl:FunctionalProperty .",
            ),
            ttl(
                "existential restriction on a transitive property",
                "ex:t a owl:TransitiveProperty . [ a owl:Restriction ; owl:onProperty ex:t ;"
                " owl:someValuesFrom ex:A ] .",
            ),
            ttl(
                "cardinality on a simple sub-property of a transitive property",
                "ex:p rdfs:subPropertyOf ex:t . ex:t a owl:TransitiveProperty . [ a owl:Restriction ;"
                " owl:onProperty ex:p ; owl:maxCardinality 1 ] .",
            ),
            ttl(
                "cardinality on a datatype property",
                "ex:t a owl:TransitiveProperty ; rdfs:subPropertyOf ex:d . ex:d a owl:DatatypeProperty ."
                " [ a owl:Restriction ; owl:onProperty ex:d ; owl:maxCardinality 1 ] .",
            ),
            ttl(
                "qualified data cardinality is a data restriction",
                "ex:t a owl:TransitiveProperty . [ a owl:Restriction ; owl:onProperty ex:t ;"
                " owl:maxQualifiedCardinality 1 ; owl:onDataRange xsd:string ] .",
            ),
            ttl(
                "untyped restriction-shaped node is not judged",
                "ex:t a owl:TransitiveProperty . [ owl:onProperty ex:t ; owl:maxCardinality 1 ] .",
            ),
            ttl("simple properties declared disjoint", "ex:p owl:propertyDisjointWith ex:q ."),
            ttl(
                "simple members of owl:AllDisjointProperties",
                "ex:t a owl:TransitiveProperty . [ a owl:AllDisjointProperties ; owl:members ( ex:p ex:q ) ] .",
            ),
            ttl(
                "characteristic on an anonymous inverse expression is not judged",
                "ex:t a owl:TransitiveProperty ; rdfs:subPropertyOf ex:p . [ owl:inverseOf ex:p ] a"
                " owl:FunctionalProperty .",
            ),
        ],
    ),
    "OWL020": rule_cases(
        [
            ttl(
                "three-property cycle",
                "ex:a rdfs:subPropertyOf ex:b . ex:b rdfs:subPropertyOf ex:c . ex:c rdfs:subPropertyOf ex:a .",
            ),
            ttl("two-property cycle", "ex:a rdfs:subPropertyOf ex:b . ex:b rdfs:subPropertyOf ex:a ."),
        ],
        [
            ttl("acyclic chain", "ex:a rdfs:subPropertyOf ex:b . ex:b rdfs:subPropertyOf ex:c ."),
            ttl(
                "diamond",
                "ex:a rdfs:subPropertyOf ex:b, ex:c . ex:b rdfs:subPropertyOf ex:d . ex:c rdfs:subPropertyOf ex:d .",
            ),
            ttl("self sub-property is not a cycle finding", "ex:a rdfs:subPropertyOf ex:a ."),
            ttl("cycle through a blank node", "ex:a rdfs:subPropertyOf _:x . _:x rdfs:subPropertyOf ex:a ."),
            ttl(
                "equivalence is not a sub-property edge",
                "ex:a rdfs:subPropertyOf ex:b . ex:b owl:equivalentProperty ex:a .",
            ),
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
            ttl(
                "datatype sub-property of object property",
                "ex:d a owl:DatatypeProperty ; rdfs:subPropertyOf ex:o . ex:o a owl:ObjectProperty .",
            ),
            ttl(
                "object sub-property of a blank datatype property",
                "ex:o a owl:ObjectProperty ; rdfs:subPropertyOf [ a owl:DatatypeProperty ] .",
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
            ttl("untyped source", "ex:x rdfs:subPropertyOf ex:d . ex:d a owl:DatatypeProperty ."),
            ttl(
                "characteristic is not a kind",
                "ex:t a owl:TransitiveProperty ; rdfs:subPropertyOf ex:d . ex:d a owl:DatatypeProperty .",
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
            ttl("object property with owl:real range", "ex:o a owl:ObjectProperty ; rdfs:range owl:real ."),
            ttl(
                "object property with rdf:PlainLiteral range",
                "ex:o a owl:ObjectProperty ; rdfs:range rdf:PlainLiteral .",
            ),
            ttl("object property with rdf:JSON range", "ex:o a owl:ObjectProperty ; rdfs:range rdf:JSON ."),
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
            ttl("object property with blank range", "ex:o a owl:ObjectProperty ; rdfs:range [ a rdfs:Datatype ] ."),
            ttl(
                "range punned class and datatype is left to OWL030",
                "ex:o a owl:ObjectProperty ; rdfs:range ex:T . ex:d a owl:DatatypeProperty ; rdfs:range ex:T .\n"
                "ex:T a owl:Class, rdfs:Datatype .",
            ),
            ttl("datatype property with untyped range", "ex:d a owl:DatatypeProperty ; rdfs:range ex:C ."),
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
            ttl("self inverse does not count (OWL007)", "ex:p owl:inverseOf ex:p, ex:q ."),
            ttl("blank inverse does not count", "ex:p owl:inverseOf ex:q, [ owl:inverseOf ex:r ] ."),
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
            ttl("disjoint super-property", "ex:p owl:propertyDisjointWith ex:q . ex:q rdfs:subPropertyOf ex:p ."),
            ttl(
                "repeated member of all disjoint properties",
                "[] a owl:AllDisjointProperties ; owl:members ( ex:p ex:q ex:p ) .",
            ),
            ttl(
                "all disjoint properties with equivalent members",
                "[] a owl:AllDisjointProperties ; owl:members ( ex:p ex:q ex:r ) . ex:q owl:equivalentProperty ex:r .",
            ),
            ttl(
                "disjoint blank sub-property",
                "ex:p owl:propertyDisjointWith _:q ; rdfs:subPropertyOf _:q . _:q a owl:ObjectProperty .",
            ),
        ],
        [
            ttl("unrelated disjoint properties", "ex:p owl:propertyDisjointWith ex:q ."),
            ttl(
                "disjoint with a super-property's sibling",
                "ex:p owl:propertyDisjointWith ex:q ; rdfs:subPropertyOf ex:r .",
            ),
            ttl("malformed members list", "[] a owl:AllDisjointProperties ; owl:members ex:p ."),
            ttl(
                "all disjoint properties without a relation",
                "[] a owl:AllDisjointProperties ; owl:members ( ex:p ex:q ex:r ) . ex:p rdfs:subPropertyOf ex:s .",
            ),
            ttl(
                "disjoint with the bottom object property",
                "ex:p owl:propertyDisjointWith owl:bottomObjectProperty ;"
                " rdfs:subPropertyOf owl:bottomObjectProperty .",
            ),
            ttl(
                "bottom data property disjoint with itself",
                "owl:bottomDataProperty owl:propertyDisjointWith owl:bottomDataProperty .",
            ),
            ttl(
                "group over 200 members is not read",
                f"[] a owl:AllDisjointProperties ; owl:members ( {OVERSIZED_MEMBERS} ) ."
                " ex:m0 rdfs:subPropertyOf ex:m1 .",
            ),
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
            ttl("equivalence stated in reverse", "ex:A owl:disjointWith ex:B . ex:B owl:equivalentClass ex:A ."),
            ttl(
                "repeated member of all disjoint classes (also OWL045)",
                "[] a owl:AllDisjointClasses ; owl:members ( ex:A ex:B ex:A ) .",
            ),
            ttl(
                "group of exactly 200 members is read",
                "[] a owl:AllDisjointClasses ; owl:members ( "
                + " ".join(f"ex:m{i}" for i in range(200))
                + " ) . ex:m0 rdfs:subClassOf ex:m199 .",
            ),
            ttl(
                "disjoint with a blank superclass",
                "ex:A a owl:Class ; owl:disjointWith _:c ; rdfs:subClassOf _:c . _:c owl:complementOf ex:Z .",
            ),
        ],
        [
            ttl("unrelated disjoint classes", "ex:A owl:disjointWith ex:B ."),
            ttl("siblings", "ex:A rdfs:subClassOf ex:P ; owl:disjointWith ex:B . ex:B rdfs:subClassOf ex:P ."),
            ttl("disjoint with owl:Nothing", "ex:A owl:disjointWith owl:Nothing ; rdfs:subClassOf owl:Nothing ."),
            ttl(
                "malformed members list", "[] a owl:AllDisjointClasses ; owl:members ex:A . ex:A rdfs:subClassOf ex:B ."
            ),
            ttl(
                "group over 200 members is not read",
                f"[] a owl:AllDisjointClasses ; owl:members ( {OVERSIZED_MEMBERS} ) . ex:m0 rdfs:subClassOf ex:m1 .",
            ),
            # Subsumption is not closed: A is disjoint with B and only indirectly a subclass of it.
            ttl(
                "indirect subclass",
                "ex:A owl:disjointWith ex:B ; rdfs:subClassOf ex:M . ex:M rdfs:subClassOf ex:B .",
            ),
            # The boundary with OWL043: an unsatisfiable class *expression* is OWL043's, not an axiom conflict.
            ttl(
                "intersection of disjoint classes (OWL043)",
                "ex:A owl:disjointWith ex:B . ex:C owl:intersectionOf ( ex:A ex:B ) .",
            ),
        ],
    ),
    "OWL026": rule_cases(
        [
            ttl("same and different", "ex:a owl:sameAs ex:b ; owl:differentFrom ex:b ."),
            ttl("reversed same", "ex:a owl:differentFrom ex:b . ex:b owl:sameAs ex:a ."),
            ttl("different from itself", "ex:a owl:differentFrom ex:a ."),
            ttl(
                "same as and different from a blank node", "ex:a owl:sameAs _:b ; owl:differentFrom _:b . _:b ex:p 1 ."
            ),
        ],
        [
            ttl("same only", "ex:a owl:sameAs ex:b ."),
            ttl("different only", "ex:a owl:differentFrom ex:b ."),
            ttl("same with a third individual", "ex:a owl:sameAs ex:b ; owl:differentFrom ex:c ."),
            ttl(
                "sameAs chain is OWL044's",
                "ex:a owl:sameAs ex:b . ex:b owl:sameAs ex:c . ex:a owl:differentFrom ex:c .",
            ),
            ttl(
                "all different with same members is OWL044's",
                "ex:a owl:sameAs ex:b . [] a owl:AllDifferent ; owl:distinctMembers ( ex:a ex:b ) .",
            ),
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
            # RDFLib normalises a parsed integer's lexical form, so "01" and "1" are one term.
            ttl(
                "negated integer with another lexical form",
                'ex:a ex:p "1"^^xsd:integer . [] a owl:NegativePropertyAssertion ; owl:sourceIndividual ex:a ;'
                ' owl:assertionProperty ex:p ; owl:targetValue "01"^^xsd:integer .',
            ),
            ttl(
                "negated assertion on a blank individual that is asserted",
                "ex:a ex:p _:b . _:b ex:q 1 . [] a owl:NegativePropertyAssertion ; owl:sourceIndividual ex:a ;"
                " owl:assertionProperty ex:p ; owl:targetIndividual _:b .",
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
            ttl(
                "different property",
                "ex:a ex:q ex:b . [] a owl:NegativePropertyAssertion ; owl:sourceIndividual ex:a ;"
                " owl:assertionProperty ex:p ; owl:targetIndividual ex:b .",
            ),
            # Literals are compared as (RDFLib-normalised) RDF terms, not as values across datatypes.
            ttl(
                "equal value in another datatype",
                'ex:a ex:p "1"^^xsd:integer . [] a owl:NegativePropertyAssertion ; owl:sourceIndividual ex:a ;'
                ' owl:assertionProperty ex:p ; owl:targetValue "1.0"^^xsd:decimal .',
            ),
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
            ttl(
                "reflexive use of a sub-property is not inherited",
                "ex:p a owl:IrreflexiveProperty . ex:q rdfs:subPropertyOf ex:p . ex:a ex:q ex:a .",
            ),
        ],
    ),
    "OWL029": rule_cases(
        [
            ttl("both directions", "ex:p a owl:AsymmetricProperty . ex:a ex:p ex:b . ex:b ex:p ex:a ."),
            ttl("self assertion", "ex:p a owl:AsymmetricProperty . ex:a ex:p ex:a ."),
            ttl("both directions between blank nodes", "ex:p a owl:AsymmetricProperty . _:a ex:p _:b . _:b ex:p _:a ."),
        ],
        [
            ttl("one direction", "ex:p a owl:AsymmetricProperty . ex:a ex:p ex:b ."),
            ttl(
                "both directions on an ordinary property",
                "ex:p a owl:ObjectProperty . ex:a ex:p ex:b . ex:b ex:p ex:a .",
            ),
            ttl("literal value", 'ex:p a owl:AsymmetricProperty . ex:a ex:p "x" .'),
            ttl(
                "reverse direction on another property",
                "ex:p a owl:AsymmetricProperty . ex:a ex:p ex:b . ex:b ex:q ex:a .",
            ),
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
            ttl("object and datatype property is OWL003's", "ex:p a owl:ObjectProperty, owl:DatatypeProperty ."),
            ttl("class and rdfs:Class is not a datatype", "ex:T a owl:Class, rdfs:Class ."),
        ],
    ),
}
