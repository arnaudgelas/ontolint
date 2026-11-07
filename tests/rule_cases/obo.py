"""Cases for OBO001-OBO012 (opt-in OBO Foundry convention rules)."""

from __future__ import annotations

from rule_harness import Case, rule_cases, ttl

HEAD = """\
@prefix obo: <http://purl.obolibrary.org/obo/> .
@prefix oio: <http://www.geneontology.org/formats/oboInOwl#> .
"""
DEF = 'obo:IAO_0000115 "A thing."'
AXIOM = (
    "[] a owl:Axiom ; owl:annotatedSource ex:A ; owl:annotatedProperty {prop} ;"
    ' owl:annotatedTarget "{target}" ; {annotation} .'
)
VERSION = "<http://purl.obolibrary.org/obo/{id}/releases/{date}/{file}>"


def _ttl(name: str, body: str) -> Case:
    return ttl(name, HEAD + body)


def _axiom(annotation: str, *, prop: str = "obo:IAO_0000115", target: str = "A thing.") -> str:
    return AXIOM.format(prop=prop, target=target, annotation=annotation)


def _header(version: str) -> str:
    return f"<http://purl.obolibrary.org/obo/xyz.owl> a owl:Ontology ; owl:versionIRI {version} ."


CASES = {
    "OBO001": rule_cases(
        [
            _ttl("letters in the number", "obo:XYZ_12a a owl:Class ."),
            _ttl("no prefix separator", "obo:xyz a owl:Class ."),
            _ttl("no number", "obo:XYZ_ a owl:Class ."),
            _ttl("hash local name", "<http://purl.obolibrary.org/obo/uberon#part_of> a owl:ObjectProperty ."),
            _ttl("bad individual", "obo:thing a owl:NamedIndividual ."),
        ],
        [
            _ttl("canonical identifier", "obo:XYZ_0000001 a owl:Class ."),
            _ttl("short number", "obo:XYZ_1 a owl:Class ."),
            _ttl("alphanumeric prefix", "obo:NCBITaxon_9606 a owl:Class ."),
            _ttl("sub-prefix", "obo:NCBITaxon_Union_0000001 a owl:Class ."),
            _ttl("foreign namespace is out of scope", "ex:Thing a owl:Class ."),
            _ttl("ontology IRI is not a term", "obo:xyz.owl a owl:Ontology ."),
        ],
    ),
    "OBO002": rule_cases(
        [
            _ttl("no title", 'ex:o a owl:Ontology ; dcterms:description "d" ; dcterms:license ex:L .'),
            _ttl("no description", 'ex:o a owl:Ontology ; dcterms:title "t" ; dcterms:license ex:L .'),
            _ttl("no license", 'ex:o a owl:Ontology ; dcterms:title "t" ; dcterms:description "d" .'),
            _ttl(
                "blank title",
                'ex:o a owl:Ontology ; dcterms:title " " ; dcterms:description "d" ; dcterms:license ex:L .',
            ),
            _ttl("bare header", "ex:o a owl:Ontology ."),
        ],
        [
            _ttl(
                "complete header",
                'ex:o a owl:Ontology ; dcterms:title "t" ; dcterms:description "d" ; dcterms:license ex:L .',
            ),
            _ttl(
                "Dublin Core elements",
                'ex:o a owl:Ontology ; <http://purl.org/dc/elements/1.1/title> "t" ;'
                ' <http://purl.org/dc/elements/1.1/description> "d" ; dcterms:license ex:L .',
            ),
            _ttl("no ontology header at all", "ex:A a owl:Class ."),
        ],
    ),
    "OBO003": rule_cases(
        [
            _ttl("class without definition", "ex:A a owl:Class ."),
            _ttl("blank definition", 'ex:A a owl:Class ; obo:IAO_0000115 "  " .'),
            _ttl("rdfs:comment is not a definition", 'ex:A a owl:Class ; rdfs:comment "A thing." .'),
            _ttl("object property without definition", "ex:p a owl:ObjectProperty ."),
            _ttl("false deprecated flag", 'ex:A a owl:Class ; owl:deprecated "false"^^xsd:boolean .'),
        ],
        [
            _ttl("defined class", f"ex:A a owl:Class ; {DEF} ."),
            _ttl("defined property", 'ex:p a owl:DatatypeProperty ; obo:IAO_0000115 "A relation." .'),
            _ttl("obsolete class needs no definition", 'ex:A a owl:Class ; owl:deprecated "true"^^xsd:boolean .'),
            _ttl("annotation properties are out of scope", "ex:a a owl:AnnotationProperty ."),
        ],
    ),
    "OBO004": rule_cases(
        [
            _ttl("class without label", "ex:A a owl:Class ."),
            _ttl("blank label", 'ex:A a owl:Class ; rdfs:label " " .'),
            _ttl("property without label", "ex:p a owl:ObjectProperty ."),
            _ttl("shared label", 'ex:A a owl:Class ; rdfs:label "cell" . ex:B a owl:Class ; rdfs:label "cell" .'),
            _ttl(
                "class and property share a label",
                'ex:A a owl:Class ; rdfs:label "cell" . ex:p a owl:ObjectProperty ; rdfs:label "cell" .',
            ),
        ],
        [
            _ttl("unique labels", 'ex:A a owl:Class ; rdfs:label "a" . ex:B a owl:Class ; rdfs:label "b" .'),
            _ttl(
                "same text in different languages",
                'ex:A a owl:Class ; rdfs:label "cell"@en . ex:B a owl:Class ; rdfs:label "cell"@fr .',
            ),
            _ttl("one term with two labels", 'ex:A a owl:Class ; rdfs:label "a", "b" .'),
            _ttl("annotation property needs no label", "ex:a a owl:AnnotationProperty ."),
        ],
    ),
    "OBO005": rule_cases(
        [
            _ttl("ad hoc part of", 'ex:partOf a owl:ObjectProperty ; rdfs:label "part of" .'),
            _ttl("case and spacing are ignored", 'ex:p a owl:ObjectProperty ; rdfs:label "Develops  FROM" .'),
            _ttl(
                "unrelated sub-property does not count",
                'ex:p a owl:ObjectProperty ; rdfs:label "has part" ; rdfs:subPropertyOf ex:q .',
            ),
            _ttl(
                "sub-property of the wrong relation",
                'ex:p a owl:ObjectProperty ; rdfs:label "has part" ; rdfs:subPropertyOf obo:BFO_0000050 .',
            ),
        ],
        [
            _ttl(
                "sub-property of the RO relation",
                'ex:p a owl:ObjectProperty ; rdfs:label "part of" ; rdfs:subPropertyOf obo:BFO_0000050 .',
            ),
            _ttl(
                "equivalent to the RO relation",
                'ex:p a owl:ObjectProperty ; rdfs:label "part of" ; owl:equivalentProperty obo:BFO_0000050 .',
            ),
            _ttl(
                "RO relation declares the equivalence",
                'ex:p a owl:ObjectProperty ; rdfs:label "part of" . obo:BFO_0000050 owl:equivalentProperty ex:p .',
            ),
            _ttl("the RO relation itself", 'obo:BFO_0000050 a owl:ObjectProperty ; rdfs:label "part of" .'),
            _ttl("datatype property is out of scope", 'ex:p a owl:DatatypeProperty ; rdfs:label "part of" .'),
            _ttl("different label", 'ex:p a owl:ObjectProperty ; rdfs:label "is component of" .'),
            _ttl(
                "obsolete property",
                'ex:p a owl:ObjectProperty ; rdfs:label "part of" ; owl:deprecated "true"^^xsd:boolean .',
            ),
        ],
    ),
    "OBO006": rule_cases(
        [
            _ttl("definition without source", f"ex:A a owl:Class ; {DEF} ."),
            _ttl(
                "axiom annotation about another definition",
                f"ex:A a owl:Class ; {DEF} . " + _axiom('oio:hasDbXref "PMID:1"', target="Another."),
            ),
            _ttl(
                "axiom without provenance",
                f"ex:A a owl:Class ; {DEF} . " + _axiom('rdfs:comment "x"'),
            ),
            _ttl(
                "xref on an axiom about another property",
                f"ex:A a owl:Class ; {DEF} . " + _axiom('oio:hasDbXref "PMID:1"', prop="rdfs:comment"),
            ),
            _ttl(
                "second definition lacks a source",
                'ex:A a owl:Class ; obo:IAO_0000115 "One.", "Two." . '
                + _axiom('oio:hasDbXref "PMID:1"', target="One."),
            ),
        ],
        [
            _ttl(
                "definition axiom with xref",
                f"ex:A a owl:Class ; {DEF} . " + _axiom('oio:hasDbXref "PMID:1"'),
            ),
            _ttl(
                "definition axiom with dcterms:source",
                f"ex:A a owl:Class ; {DEF} . " + _axiom('dcterms:source "x"'),
            ),
            _ttl("term-level definition source", f'ex:A a owl:Class ; {DEF} ; obo:IAO_0000119 "x" .'),
            _ttl("no definition is OBO003's business", "ex:A a owl:Class ."),
            _ttl("obsolete term", f'ex:A a owl:Class ; {DEF} ; owl:deprecated "true"^^xsd:boolean .'),
        ],
    ),
    "OBO007": rule_cases(
        [
            _ttl("obsolete class bare", 'ex:A a owl:Class ; owl:deprecated "true"^^xsd:boolean .'),
            _ttl("plain true literal", 'ex:A a owl:Class ; owl:deprecated "true" .'),
            _ttl("lexical 1", 'ex:A a owl:Class ; owl:deprecated "1"^^xsd:boolean .'),
            _ttl("blank reason", 'ex:A a owl:Class ; owl:deprecated true ; obo:IAO_0000231 " " .'),
            _ttl("obsolete property", "ex:p a owl:ObjectProperty ; owl:deprecated true ."),
            _ttl("undeclared obsolete term", "ex:A owl:deprecated true ."),
        ],
        [
            _ttl("with reason", "ex:A a owl:Class ; owl:deprecated true ; obo:IAO_0000231 obo:OMO_0000001 ."),
            _ttl("with replacement", "ex:A a owl:Class ; owl:deprecated true ; obo:IAO_0100001 ex:B ."),
            _ttl("with consider", 'ex:A a owl:Class ; owl:deprecated true ; oio:consider "ex:B" .'),
            _ttl("not obsolete", "ex:A a owl:Class ."),
            _ttl("deprecated false", 'ex:A a owl:Class ; owl:deprecated "false"^^xsd:boolean .'),
            _ttl("plain 1 is not a boolean", 'ex:A a owl:Class ; owl:deprecated "1" .'),
        ],
    ),
    "OBO008": rule_cases(
        [
            _ttl("class with no parent", "ex:A a owl:Class ."),
            _ttl(
                "parent chain ends at a declared root", "ex:A a owl:Class ; rdfs:subClassOf ex:B . ex:B a owl:Class ."
            ),
            _ttl("under owl:Thing only", "ex:A a owl:Class ; rdfs:subClassOf owl:Thing ."),
            _ttl("only restriction parents", "ex:A a owl:Class ; rdfs:subClassOf [ a owl:Restriction ] ."),
            _ttl(
                "subclass cycle without BFO",
                "ex:A a owl:Class ; rdfs:subClassOf ex:B . ex:B a owl:Class ; rdfs:subClassOf ex:A .",
            ),
            _ttl(
                "BFO-like IRI in another namespace",
                "ex:A a owl:Class ; rdfs:subClassOf obo:BFX_0000001 . obo:BFX_0000001 a owl:Class .",
            ),
        ],
        [
            _ttl("direct BFO parent", "ex:A a owl:Class ; rdfs:subClassOf obo:BFO_0000002 ."),
            _ttl(
                "transitive BFO parent",
                "ex:A a owl:Class ; rdfs:subClassOf ex:B . ex:B a owl:Class ; rdfs:subClassOf ex:C ."
                " ex:C a owl:Class ; rdfs:subClassOf obo:BFO_0000001 .",
            ),
            _ttl(
                "BFO genus of a defined class",
                "ex:A a owl:Class ; owl:equivalentClass"
                " [ owl:intersectionOf ( obo:BFO_0000004 [ a owl:Restriction ] ) ] .",
            ),
            _ttl("equivalent to a BFO class", "ex:A a owl:Class ; owl:equivalentClass obo:BFO_0000002 ."),
            _ttl("BFO class equivalent to the class", "obo:BFO_0000002 owl:equivalentClass ex:A . ex:A a owl:Class ."),
            _ttl("parent declared elsewhere (imported)", "ex:A a owl:Class ; rdfs:subClassOf obo:CL_0000000 ."),
            _ttl(
                "chain leaves the graph",
                "ex:A a owl:Class ; rdfs:subClassOf ex:B . ex:B a owl:Class ; rdfs:subClassOf obo:CL_0000000 .",
            ),
            _ttl("obsolete class", "ex:A a owl:Class ; owl:deprecated true ."),
            _ttl("the BFO class itself", "obo:BFO_0000001 a owl:Class ."),
            _ttl("properties are out of scope", "ex:p a owl:ObjectProperty ."),
        ],
    ),
    "OBO009": rule_cases(
        [
            _ttl("oboInOwl:hasSynonym", 'ex:A oio:hasSynonym "alias" .'),
            _ttl("skos:altLabel", 'ex:A skos:altLabel "alias" .'),
        ],
        [
            _ttl("exact", 'ex:A oio:hasExactSynonym "alias" .'),
            _ttl("broad", 'ex:A oio:hasBroadSynonym "alias" .'),
            _ttl("narrow", 'ex:A oio:hasNarrowSynonym "alias" .'),
            _ttl("related", 'ex:A oio:hasRelatedSynonym "alias" .'),
            _ttl("blank synonym", 'ex:A oio:hasSynonym " " .'),
            _ttl("non-literal synonym", "ex:A skos:altLabel ex:B ."),
        ],
    ),
    "OBO010": rule_cases(
        [
            _ttl("whole ontology", "ex:o a owl:Ontology ; owl:imports obo:uberon.owl ."),
            _ttl(
                "released whole ontology",
                "ex:o a owl:Ontology ;"
                " owl:imports " + VERSION.format(id="uberon", date="2020-01-01", file="uberon.owl") + " .",
            ),
        ],
        [
            _ttl(
                "ODK module",
                "ex:o a owl:Ontology ; owl:imports <http://purl.obolibrary.org/obo/uberon/imports/ro_import.owl> .",
            ),
            _ttl(
                "released other file",
                "ex:o a owl:Ontology ;"
                " owl:imports " + VERSION.format(id="uberon", date="2020-01-01", file="uberon-base.owl") + " .",
            ),
            _ttl("non-OBO import", "ex:o a owl:Ontology ; owl:imports <https://example.org/other.owl> ."),
            _ttl("no imports", "ex:o a owl:Ontology ."),
            _ttl("literal import", 'ex:o a owl:Ontology ; owl:imports "http://purl.obolibrary.org/obo/uberon.owl" .'),
        ],
    ),
    "OBO011": rule_cases(
        [
            _ttl("non-OBO ontology IRI", "ex:o a owl:Ontology ."),
            _ttl("missing .owl", "obo:xyz a owl:Ontology ."),
            _ttl("upper-case id", "obo:XYZ.owl a owl:Ontology ."),
            _ttl("empty id", "<http://purl.obolibrary.org/obo/.owl> a owl:Ontology ."),
            _ttl("version IRI without releases", _header("<http://purl.obolibrary.org/obo/xyz/2020-01-01/xyz.owl>")),
            _ttl("version IRI with a bad date", _header(VERSION.format(id="xyz", date="2020-1-1", file="xyz.owl"))),
            _ttl(
                "version IRI of another ontology",
                _header(VERSION.format(id="abc", date="2020-01-01", file="abc.owl")),
            ),
            _ttl("version IRI that is not an OBO PURL", _header("<http://example.org/v/1>")),
            _ttl(
                "version IRI for a non-OBO ontology",
                "ex:o a owl:Ontology ; owl:versionIRI <http://example.org/v/1> .",
            ),
        ],
        [
            _ttl("plain ontology", "obo:xyz.owl a owl:Ontology ."),
            _ttl("id with digits and underscore", "obo:xyz_2.owl a owl:Ontology ."),
            _ttl("sub-ontology", "<http://purl.obolibrary.org/obo/xyz/imports/ro_import.owl> a owl:Ontology ."),
            _ttl("released version", _header(VERSION.format(id="xyz", date="2020-01-01", file="xyz.owl"))),
            _ttl(
                "released version of a sub-ontology",
                "<http://purl.obolibrary.org/obo/xyz/extensions/xyz-plus.owl> a owl:Ontology ; owl:versionIRI "
                + VERSION.format(id="xyz", date="2020-01-01", file="extensions/xyz-plus.owl")
                + " .",
            ),
            _ttl("no ontology", "ex:A a owl:Class ."),
        ],
    ),
    "OBO012": rule_cases(
        [
            _ttl("leading whitespace", 'ex:A a owl:Class ; rdfs:label " cell" .'),
            _ttl("trailing whitespace", 'ex:A a owl:Class ; rdfs:label "cell " .'),
            _ttl("repeated whitespace", 'ex:A a owl:Class ; rdfs:label "cell  membrane" .'),
            _ttl("underscore", 'ex:A a owl:Class ; rdfs:label "cell_membrane" .'),
            _ttl("initial capital", 'ex:A a owl:Class ; rdfs:label "Cell membrane" .'),
            _ttl("initial capital with English tag", 'ex:A a owl:Class ; rdfs:label "Cell"@en-GB .'),
            _ttl("property label", 'ex:p a owl:ObjectProperty ; rdfs:label "Part of" .'),
            _ttl("capital after leading space", 'ex:A a owl:Class ; rdfs:label " Cell" .'),
        ],
        [
            _ttl("lowercase", 'ex:A a owl:Class ; rdfs:label "cell membrane" .'),
            _ttl("acronym first", 'ex:A a owl:Class ; rdfs:label "DNA binding" .'),
            _ttl("single letter", 'ex:A a owl:Class ; rdfs:label "T cell" .'),
            _ttl("capital in another language", 'ex:A a owl:Class ; rdfs:label "Cellule"@fr .'),
            _ttl("English-looking tag prefix only", 'ex:A a owl:Class ; rdfs:label "Cell"@enx .'),
            _ttl("hyphen is fine", 'ex:A a owl:Class ; rdfs:label "t-cell receptor" .'),
            _ttl("blank labels are OBO004's business", 'ex:A a owl:Class ; rdfs:label " " .'),
            _ttl("annotation properties are out of scope", 'ex:a a owl:AnnotationProperty ; rdfs:label "A_b" .'),
        ],
    ),
}
