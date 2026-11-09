"""Cases for DATA003 and DATA004."""

from __future__ import annotations

from rule_harness import rule_cases, ttl

CASES = {
    "DATA003": rule_cases(
        [
            ttl("date with a one-digit day (MOD)", "ex:A a owl:Class ; dcterms:issued '2024-06-2'^^xsd:date ."),
            ttl("a year typed as a date (MOD)", "ex:A a owl:Class ; dcterms:issued '2004'^^xsd:date ."),
            ttl("a word typed as an integer", "ex:p a owl:DatatypeProperty . ex:a ex:p 'many'^^xsd:integer ."),
            ttl("typed rdfs:Literal (food traceability)", "ex:A a owl:Class ; rdfs:comment 'A note.'^^rdfs:Literal ."),
            ttl(
                "inside an axiom annotation",
                "ex:A a owl:Class . [ a owl:Axiom ; owl:annotatedSource ex:A ; owl:annotatedProperty rdfs:label ; "
                "owl:annotatedTarget 'A' ; dcterms:date 'yesterday'^^xsd:dateTime ] .",
            ),
        ],
        [
            ttl("valid values", "ex:A a owl:Class ; dcterms:issued '2024-06-02'^^xsd:date ; ex:n '3'^^xsd:integer ."),
            ttl("plain and language-tagged strings", "ex:A a owl:Class ; rdfs:label 'A' , 'A'@en ."),
            ttl("a datatype RDFLib does not know", "ex:A a owl:Class ; ex:v 'x'^^<https://dt.test/custom> ."),
            ttl("a year typed as a year", "ex:A a owl:Class ; dcterms:issued '2004'^^xsd:gYear ."),
            ttl(
                "an imported vocabulary's literal",
                "<https://example.test/onto> a owl:Ontology . ex:A a owl:Class .\n"
                "<https://other.test/B> a owl:Class ; <https://other.test/n> 'many'^^xsd:integer .",
                base="https://example.test/onto#",
            ),
        ],
    ),
    "DATA004": rule_cases(
        [
            ttl("xsd:anyType range (Tractus-X)", "ex:p a owl:DatatypeProperty ; rdfs:range xsd:anyType ."),
            ttl("xsd:date range", "ex:p a owl:DatatypeProperty ; rdfs:range xsd:date ."),
            ttl(
                "datatype restriction on xsd:gYear",
                "ex:p a owl:DatatypeProperty ; rdfs:range [ a rdfs:Datatype ; owl:onDatatype xsd:gYear ; "
                "owl:withRestrictions ( [ xsd:minInclusive '2000'^^xsd:gYear ] ) ] .",
            ),
            ttl(
                "data restriction filler",
                "ex:p a owl:DatatypeProperty . ex:A a owl:Class ; rdfs:subClassOf "
                "[ a owl:Restriction ; owl:onProperty ex:p ; owl:someValuesFrom xsd:duration ] .",
            ),
            ttl(
                "member of a data range union",
                "ex:p a owl:DatatypeProperty ;\n"
                "    rdfs:range [ a rdfs:Datatype ; owl:unionOf ( xsd:dateTime xsd:time ) ] .",
            ),
        ],
        [
            ttl(
                "OWL 2 datatypes", "ex:p a owl:DatatypeProperty ; rdfs:range xsd:dateTime , xsd:string , xsd:integer ."
            ),
            ttl("rdfs:Literal and rdf:PlainLiteral", "ex:p a owl:DatatypeProperty ; rdfs:range rdfs:Literal ."),
            ttl("a class range", "ex:p a owl:ObjectProperty ; rdfs:range ex:A . ex:A a owl:Class ."),
            ttl(
                "a date-typed annotation value is DATA003's concern",
                "ex:A a owl:Class ; dcterms:issued '2004-01-01'^^xsd:date .",
            ),
            ttl(
                "an imported vocabulary's range",
                "<https://example.test/onto> a owl:Ontology . ex:p a owl:DatatypeProperty ; rdfs:range xsd:string .\n"
                "<https://other.test/q> a owl:DatatypeProperty ; rdfs:range xsd:date .",
                base="https://example.test/onto#",
            ),
        ],
    ),
}
