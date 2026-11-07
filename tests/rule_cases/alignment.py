"""Cases for the graph-local alignment rules ALIGN002-005, 007, 009, 013-015."""

from __future__ import annotations

from rule_harness import rule_cases, ttl

EXT = "@prefix a: <http://a.test/> . @prefix b: <http://b.test/> . @prefix c: <http://c.test/> .\n"

CASES = {
    "ALIGN002": rule_cases(
        [
            ttl("wrong case", EXT + "ex:A skos:exactmatch a:A ."),
            ttl("owl typo", EXT + "ex:A owl:sameas a:A ."),
            ttl("unknown match property", EXT + "ex:A skos:relMatch a:A ."),
            ttl(
                "missing hash in the skos namespace", EXT + "ex:A <http://www.w3.org/2004/02/skos/coreexactMatch> a:A ."
            ),
        ],
        [
            ttl("correct property", EXT + "ex:A skos:exactMatch a:A ."),
            ttl("custom property in another namespace", EXT + "ex:A ex:exactMatch a:A ."),
            ttl("other skos property", "ex:A skos:prefLabel 'A' ; skos:related ex:B ."),
            ttl("mappingRelation", EXT + "ex:A skos:mappingRelation a:A ."),
        ],
    ),
    "ALIGN003": rule_cases(
        [
            ttl(
                "chain with broad",
                EXT + "a:X skos:exactMatch b:Y . b:Y skos:exactMatch c:Z . a:X skos:broadMatch c:Z .",
            ),
            ttl(
                "chain with narrow",
                EXT + "a:X skos:exactMatch b:Y . c:Z skos:exactMatch b:Y . c:Z skos:narrowMatch a:X .",
            ),
        ],
        [
            ttl("direct conflict is SKOS012", EXT + "a:X skos:exactMatch b:Y ; skos:broadMatch b:Y ."),
            ttl("unrelated terms", EXT + "a:X skos:exactMatch b:Y . c:Z skos:broadMatch a:X ."),
            ttl("chain without hierarchy", EXT + "a:X skos:exactMatch b:Y . b:Y skos:exactMatch c:Z ."),
        ],
    ),
    "ALIGN004": rule_cases(
        [
            ttl("mutual broad", EXT + "a:X skos:broadMatch b:Y . b:Y skos:broadMatch a:X ."),
            ttl("broad and narrow same direction", EXT + "a:X skos:broadMatch b:Y ; skos:narrowMatch b:Y ."),
            ttl("related and broad", EXT + "a:X skos:relatedMatch b:Y ; skos:broadMatch b:Y ."),
            ttl("related and inverse narrow", EXT + "b:Y skos:relatedMatch a:X . a:X skos:narrowMatch b:Y ."),
        ],
        [
            ttl("consistent pair", EXT + "a:X skos:broadMatch b:Y . b:Y skos:narrowMatch a:X ."),
            ttl("exact and broad is SKOS012", EXT + "a:X skos:exactMatch b:Y ; skos:broadMatch b:Y ."),
            ttl("related to different term", EXT + "a:X skos:relatedMatch b:Y ; skos:broadMatch c:Z ."),
        ],
    ),
    "ALIGN005": rule_cases(
        [
            ttl("two targets", EXT + "ex:A skos:exactMatch a:One, a:Two ."),
            ttl("two targets in a slash namespace", "ex:A skos:exactMatch <http://s.test/x/1>, <http://s.test/x/2> ."),
        ],
        [
            ttl("one target per namespace", EXT + "ex:A skos:exactMatch a:One, b:One ."),
            ttl(
                "targets are matched to each other",
                EXT + "ex:A skos:exactMatch a:One, a:Two . a:One skos:exactMatch a:Two .",
            ),
            ttl("targets are sameAs", EXT + "ex:A skos:exactMatch a:One, a:Two . a:Two owl:sameAs a:One ."),
            ttl("targets in the source namespace", "ex:A skos:exactMatch ex:B, ex:C ."),
            ttl("closeMatch targets", EXT + "ex:A skos:closeMatch a:One, a:Two ."),
        ],
    ),
    "ALIGN007": rule_cases(
        [
            ttl("one-way exactMatch", "ex:A skos:exactMatch ex:B . ex:B a skos:Concept ."),
            ttl("one-way closeMatch", "ex:A skos:closeMatch ex:B . ex:B skos:prefLabel 'B' ."),
        ],
        [
            ttl("both ways", "ex:A skos:exactMatch ex:B . ex:B skos:exactMatch ex:A ."),
            ttl("target not described here", "ex:A skos:exactMatch ex:B ."),
            ttl("external target", EXT + "ex:A skos:exactMatch a:B ."),
            ttl("broadMatch is not symmetric", "ex:A skos:broadMatch ex:B . ex:B a skos:Concept ."),
            ttl(
                "external source is out of scope",
                "ex:A skos:exactMatch ex:B . ex:B a skos:Concept .",
                base="http://elsewhere.test/",
            ),
        ],
    ),
    "ALIGN009": rule_cases(
        [
            ttl("class to property", EXT + "ex:C a owl:Class . a:p a owl:ObjectProperty . ex:C skos:exactMatch a:p ."),
            ttl(
                "property to class", EXT + "ex:p a owl:DatatypeProperty . a:C a rdfs:Class . ex:p skos:closeMatch a:C ."
            ),
            ttl(
                "equivalentClass to property",
                "ex:C a owl:Class . ex:p a rdf:Property . ex:C owl:equivalentClass ex:p .",
            ),
        ],
        [
            ttl("class to class", "ex:C a owl:Class . ex:D a owl:Class . ex:C owl:equivalentClass ex:D ."),
            ttl(
                "object to datatype property",
                "ex:p a owl:ObjectProperty . ex:q a owl:DatatypeProperty . ex:p skos:closeMatch ex:q .",
            ),
            ttl(
                "punned class and property",
                "ex:C a owl:Class, owl:ObjectProperty . ex:p a owl:ObjectProperty . ex:C skos:exactMatch ex:p .",
            ),
            ttl("undeclared target", "ex:C a owl:Class . ex:C skos:exactMatch ex:p ."),
            ttl("concept to class", "ex:C a owl:Class . ex:k a skos:Concept . ex:k skos:exactMatch ex:C ."),
            ttl("non-mapping predicate", "ex:C a owl:Class . ex:p a owl:ObjectProperty . ex:C rdfs:seeAlso ex:p ."),
        ],
    ),
    "ALIGN013": rule_cases(
        [
            ttl("exact and equivalentClass", "ex:A owl:equivalentClass ex:B ; skos:exactMatch ex:B ."),
            ttl("exact and close", "ex:A skos:exactMatch ex:B . ex:B skos:closeMatch ex:A ."),
            ttl("sameAs and exact reversed", "ex:A owl:sameAs ex:B . ex:B skos:exactMatch ex:A ."),
            ttl("broad and inverse narrow", "ex:A skos:broadMatch ex:B . ex:B skos:narrowMatch ex:A ."),
        ],
        [
            ttl("single predicate both ways", "ex:A skos:exactMatch ex:B . ex:B skos:exactMatch ex:A ."),
            ttl("different pairs", "ex:A skos:exactMatch ex:B . ex:A owl:equivalentClass ex:C ."),
            ttl("broad and narrow in the same orientation", "ex:A skos:broadMatch ex:B . ex:A skos:narrowMatch ex:B ."),
            ttl("broad and narrow of different pairs", "ex:A skos:broadMatch ex:B . ex:C skos:narrowMatch ex:D ."),
        ],
    ),
    "ALIGN014": rule_cases(
        [
            ttl("broadMatch against subclass", "ex:A skos:broadMatch ex:B . ex:B rdfs:subClassOf ex:A ."),
            ttl("narrowMatch against subclass", "ex:A skos:narrowMatch ex:B . ex:A rdfs:subClassOf ex:B ."),
            ttl(
                "through a chain", "ex:A skos:broadMatch ex:C . ex:C rdfs:subClassOf ex:M . ex:M rdfs:subClassOf ex:A ."
            ),
            ttl("subproperty", "ex:p skos:broadMatch ex:q . ex:q rdfs:subPropertyOf ex:p ."),
            ttl("skos broader", "ex:A skos:broadMatch ex:B . ex:B skos:broader ex:A ."),
            ttl("skos narrower", "ex:A skos:broadMatch ex:B . ex:A skos:narrower ex:B ."),
        ],
        [
            ttl("consistent", "ex:A skos:broadMatch ex:B . ex:A rdfs:subClassOf ex:B ."),
            ttl("consistent narrow", "ex:A skos:narrowMatch ex:B . ex:B rdfs:subClassOf ex:A ."),
            ttl(
                "hierarchy cycle", "ex:A skos:broadMatch ex:B . ex:B rdfs:subClassOf ex:A . ex:A rdfs:subClassOf ex:B ."
            ),
            ttl("unrelated hierarchy", "ex:A skos:broadMatch ex:B . ex:C rdfs:subClassOf ex:A ."),
            ttl("exactMatch is not hierarchical", "ex:A skos:exactMatch ex:B . ex:B rdfs:subClassOf ex:A ."),
        ],
    ),
    "ALIGN015": rule_cases(
        [
            ttl("bare mapping set", "ex:M a <https://w3id.org/sssom/MappingSet> ."),
            ttl(
                "http namespace",
                "ex:M a <http://w3id.org/sssom/MappingSet> ; dcterms:creator 'x' ; dcterms:license ex:L .",
            ),
            ttl(
                "no licence", "ex:M a <https://w3id.org/sssom/MappingSet> ; owl:versionInfo '1' ; dcterms:creator 'x' ."
            ),
            ttl(
                "no creator",
                "ex:M a <https://w3id.org/sssom/MappingSet> ; owl:versionInfo '1' ; dcterms:license ex:L .",
            ),
            ttl(
                "no version",
                "ex:M a <https://w3id.org/sssom/MappingSet> ; dcterms:creator 'x' ; dcterms:license ex:L .",
            ),
        ],
        [
            ttl(
                "complete",
                "ex:M a <https://w3id.org/sssom/MappingSet> ; owl:versionInfo '1' ;"
                " dcterms:creator 'x' ; dcterms:license ex:L .",
            ),
            ttl(
                "sssom properties",
                "ex:M a <https://w3id.org/sssom/MappingSet> ; <https://w3id.org/sssom/mapping_set_version> '1' ;"
                " <https://w3id.org/sssom/creator_id> ex:me ; <https://w3id.org/sssom/license> ex:L .",
            ),
            ttl("not a declared mapping set", "ex:O a owl:Ontology ."),
            ttl("outside base", "ex:M a <https://w3id.org/sssom/MappingSet> .", base="http://elsewhere.test/"),
        ],
    ),
}
