"""Cases for SKOS007-SKOS021."""

from __future__ import annotations

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import RDF, SKOS
from rule_harness import BASE, built, rule_cases, ttl

A = "ex:a skos:inScheme ex:s ; skos:prefLabel"
CS = "a skos:Concept ; skos:inScheme"
AC = "ex:a a skos:Concept ; skos:inScheme ex:s ; skos:prefLabel"
OTHER = "@prefix o: <http://other.test/> .\n"
EXT = "@prefix a: <http://a.test/> . @prefix b: <http://b.test/> . @prefix c: <http://c.test/> .\n"
SCHEME = "ex:s a skos:ConceptScheme ; skos:hasTopConcept ex:top . ex:top a skos:Concept ; skos:inScheme ex:s ."


def _literal_relations() -> Graph:
    g = Graph()
    g.add((URIRef("https://example.test/onto#c"), SKOS.broader, Literal("x")))
    g.add((BNode(), SKOS.related, Literal("y")))
    return g


def _hostile_labels() -> Graph:
    g = Graph()
    c = URIRef("https://example.test/onto#c")
    g.add((c, RDF.type, SKOS.Concept))
    g.add((c, SKOS.prefLabel, BNode()))
    g.add((c, SKOS.prefLabel, Literal(" " * 100_000)))
    return g


CASES = {
    "SKOS007": rule_cases(
        [ttl("concept and scheme", "ex:x a skos:Concept, skos:ConceptScheme .")],
        [
            ttl("only a concept", "ex:x a skos:Concept ."),
            ttl(
                "scheme subclass is not entailed",
                "ex:Sub rdfs:subClassOf skos:ConceptScheme . ex:x a skos:Concept, ex:Sub .",
            ),
            ttl("blank node", "[] a skos:Concept, skos:ConceptScheme ."),
            ttl("not owned", OTHER + "o:x a skos:Concept, skos:ConceptScheme .", base=BASE),
        ],
    ),
    "SKOS008": rule_cases(
        [
            ttl("collection and concept", "ex:x a skos:Collection, skos:Concept ."),
            ttl("collection and scheme", "ex:x a skos:Collection, skos:ConceptScheme ."),
            ttl("ordered collection and concept", "ex:x a skos:OrderedCollection, skos:Concept ."),
        ],
        [
            ttl("plain collection", "ex:x a skos:Collection ; skos:member ex:c . ex:c a skos:Concept ."),
            ttl("blank node", "[] a skos:Collection, skos:Concept ."),
            ttl("not owned", OTHER + "o:x a skos:Collection, skos:Concept .", base=BASE),
        ],
    ),
    "SKOS009": rule_cases(
        [
            ttl("related and broader", "ex:a skos:related ex:b ; skos:broader ex:b ."),
            ttl("related and inverse narrower", "ex:a skos:related ex:b . ex:b skos:narrower ex:a ."),
            ttl(
                "related to a grandparent", "ex:a skos:broader ex:b . ex:b skos:broader ex:c . ex:a skos:related ex:c ."
            ),
            ttl(
                "related to a grandchild, mixed predicates",
                "ex:c skos:related ex:a . ex:a skos:broaderTransitive ex:b . ex:c skos:narrower ex:b .",
            ),
            ttl("related and narrowerTransitive", "ex:a skos:related ex:b ; skos:narrowerTransitive ex:b ."),
            # S41 puts the mapping properties under broader, narrower and related, so S27 applies to them.
            ttl("related and broadMatch", "ex:a skos:related ex:b ; skos:broadMatch ex:b ."),
            ttl("related and inverse narrowMatch", "ex:a skos:related ex:b . ex:b skos:narrowMatch ex:a ."),
            ttl(
                "related to an ancestor through broader then broadMatch",
                "ex:a skos:broader ex:b . ex:b skos:broadMatch ex:c . ex:a skos:related ex:c .",
            ),
            ttl("relatedMatch and broader", "ex:a skos:relatedMatch ex:b ; skos:broader ex:b ."),
            ttl(
                "relatedMatch to an ancestor through broadMatch",
                "ex:a skos:broadMatch ex:b . ex:b skos:broader ex:c . ex:c skos:relatedMatch ex:a .",
            ),
        ],
        [
            ttl("related only", "ex:a skos:related ex:b . ex:c skos:broader ex:b ."),
            ttl("siblings", "ex:a skos:broader ex:p . ex:b skos:broader ex:p . ex:a skos:related ex:b ."),
            ttl(
                "relatedMatch and a direct broadMatch is ALIGN004's",
                "ex:a skos:relatedMatch ex:b ; skos:broadMatch ex:b .",
            ),
            ttl(
                "relatedMatch and a direct inverse narrowMatch is ALIGN004's",
                "ex:a skos:relatedMatch ex:b . ex:b skos:narrowMatch ex:a .",
            ),
            ttl(
                "broadMatch siblings",
                "ex:a skos:broadMatch ex:p . ex:b skos:broadMatch ex:p . ex:a skos:related ex:b .",
            ),
            ttl("closeMatch is not hierarchical", "ex:a skos:related ex:b ; skos:closeMatch ex:b ."),
            ttl("self related is SKOS010", "ex:a skos:related ex:a ; skos:broader ex:a ."),
            ttl("not owned", OTHER + "o:a skos:related o:b ; skos:broader o:b .", base=BASE),
        ],
    ),
    "SKOS010": rule_cases(
        [ttl("self related", "ex:a a skos:Concept ; skos:related ex:a .")],
        [ttl("related to another", "ex:a a skos:Concept ; skos:related ex:b .")],
    ),
    "SKOS011": rule_cases(
        [
            ttl(
                "exactMatch inside a scheme",
                "ex:a skos:inScheme ex:s ; skos:exactMatch ex:b . ex:b skos:inScheme ex:s .",
            )
        ],
        [
            ttl(
                "exactMatch across schemes",
                "ex:a skos:inScheme ex:s ; skos:exactMatch ex:b . ex:b skos:inScheme ex:t .",
            ),
            ttl("scheme unknown", "ex:a skos:exactMatch ex:b ."),
        ],
    ),
    "SKOS012": rule_cases(
        [
            ttl("exact and broad", "ex:a skos:exactMatch ex:b ; skos:broadMatch ex:b ."),
            ttl("exact and inverse related", "ex:a skos:exactMatch ex:b . ex:b skos:relatedMatch ex:a ."),
            ttl("exact and narrow", "ex:a skos:exactMatch ex:b ; skos:narrowMatch ex:b ."),
            ttl("inverse exact and broad", "ex:b skos:exactMatch ex:a . ex:a skos:broadMatch ex:b ."),
        ],
        [
            ttl("exact and close", "ex:a skos:exactMatch ex:b ; skos:closeMatch ex:b ."),
            ttl("exact and mappingRelation", "ex:a skos:exactMatch ex:b ; skos:mappingRelation ex:b ."),
            ttl(
                "chain conflict is ALIGN003",
                "ex:a skos:exactMatch ex:b . ex:b skos:exactMatch ex:c . ex:a skos:broadMatch ex:c .",
            ),
            ttl("not owned", EXT + "a:x skos:exactMatch b:y ; skos:broadMatch b:y .", base=BASE),
        ],
    ),
    "SKOS013": rule_cases(
        [
            ttl("integer label", "ex:c a skos:Concept ; skos:prefLabel 42 ."),
            ttl("IRI label", "ex:c a skos:Concept ; skos:altLabel ex:other ."),
            ttl("custom datatype", 'ex:c skos:hiddenLabel "x"^^ex:custom .'),
        ],
        [ttl("string labels", 'ex:c skos:prefLabel "a"@en, "b"^^xsd:string ; skos:altLabel "c" .')],
    ),
    "SKOS014": rule_cases(
        [
            ttl("padded label", 'ex:c skos:prefLabel " a "@en .'),
            ttl("empty label", 'ex:c skos:altLabel "" .'),
            built("whitespace-only huge label", _hostile_labels),
        ],
        [ttl("clean label", 'ex:c skos:prefLabel "a b"@en .')],
    ),
    "SKOS015": rule_cases(
        [ttl("scheme without top", "ex:s a skos:ConceptScheme . ex:c skos:inScheme ex:s .")],
        [
            ttl("scheme with top", SCHEME),
            ttl("empty scheme", "ex:s a skos:ConceptScheme ."),
            ttl("topConceptOf", "ex:s a skos:ConceptScheme . ex:c skos:topConceptOf ex:s ."),
        ],
    ),
    "SKOS016": rule_cases(
        [
            ttl("literal broader", 'ex:c skos:broader "parent" .'),
            ttl("literal inScheme", 'ex:c skos:inScheme "scheme" .'),
            built("literal relations", _literal_relations),
            ttl("literal exactMatch", 'ex:c skos:exactMatch "x" .'),
            ttl("literal semanticRelation", 'ex:c skos:semanticRelation "x" .'),
            ttl("literal mappingRelation", 'ex:c skos:mappingRelation "x" .'),
            ttl("literal topConceptOf", 'ex:c skos:topConceptOf "scheme" .'),
        ],
        [
            ttl("IRI values", "ex:c skos:broader ex:p ; skos:inScheme ex:s ."),
            ttl("blank-node subject", '[] skos:broader "x" .'),
            ttl("member is not checked", 'ex:k a skos:Collection ; skos:member "x" .'),
            ttl("not owned", OTHER + 'o:c skos:broader "x" .', base=BASE),
        ],
    ),
    "SKOS017": rule_cases(
        [ttl("dangling broader", "ex:c a skos:Concept ; skos:broader ex:missing .")],
        [
            ttl("described target", "ex:c skos:broader ex:p . ex:p a skos:Concept ."),
            ttl(
                "external target", "ex:c skos:exactMatch <http://elsewhere.test/x> .", base="https://example.test/onto#"
            ),
        ],
    ),
    "SKOS018": rule_cases(
        [ttl("shortcut", "ex:a skos:broader ex:b, ex:c . ex:b skos:broader ex:c .")],
        [
            ttl("chain", "ex:a skos:broader ex:b . ex:b skos:broader ex:c ."),
            ttl("two-cycle", "ex:a skos:broader ex:b . ex:b skos:broader ex:a ."),
            ttl("diamond", "ex:a skos:broader ex:b, ex:c . ex:b skos:broader ex:d . ex:c skos:broader ex:d ."),
        ],
    ),
    "SKOS019": rule_cases(
        [
            ttl("cross-scheme broader", "ex:a skos:inScheme ex:s ; skos:broader ex:b . ex:b skos:inScheme ex:t ."),
            ttl("cross-scheme narrower", "ex:b skos:inScheme ex:t ; skos:narrower ex:a . ex:a skos:inScheme ex:s ."),
        ],
        [
            ttl("same scheme", "ex:a skos:inScheme ex:s ; skos:broader ex:b . ex:b skos:inScheme ex:s ."),
            ttl(
                "shared among several", "ex:a skos:inScheme ex:s, ex:t ; skos:broader ex:b . ex:b skos:inScheme ex:t ."
            ),
            ttl("scheme unknown", "ex:a skos:broader ex:b ."),
        ],
    ),
    "SKOS020": rule_cases(
        [
            ttl(
                "duplicate notation",
                f'ex:a {CS} ex:s ; skos:notation "1" . ex:b {CS} ex:s ; skos:notation "1" .',
            )
        ],
        [
            ttl(
                "distinct notation",
                f'ex:a {CS} ex:s ; skos:notation "1" . ex:b {CS} ex:s ; skos:notation "2" .',
            ),
            ttl(
                "different schemes",
                f'ex:a {CS} ex:s ; skos:notation "1" . ex:b {CS} ex:t ; skos:notation "1" .',
            ),
            ttl("no scheme", 'ex:a skos:notation "1" . ex:b skos:notation "1" .'),
            ttl(
                "collection shares the notation",
                f'ex:a {CS} ex:s ; skos:notation "1" . '
                'ex:b a skos:Collection ; skos:inScheme ex:s ; skos:notation "1" .',
            ),
        ],
    ),
    "SKOS021": rule_cases(
        [
            ttl(
                "duplicate prefLabel",
                AC + f' "Cat"@en . ex:b {CS} ex:s ; skos:prefLabel "cat"@EN .',
            )
        ],
        [
            ttl(
                "different languages",
                AC + f' "Cat"@en . ex:b {CS} ex:s ; skos:prefLabel "Cat"@fr .',
            ),
            ttl(
                "different schemes",
                AC + f' "Cat"@en . ex:b {CS} ex:t ; skos:prefLabel "Cat"@en .',
            ),
            ttl(
                "collection shares the label",
                AC + ' "Cat"@en . ex:b a skos:Collection ; skos:inScheme ex:s ; skos:prefLabel "Cat"@en .',
            ),
            ttl(
                "deprecated concept shares the label",
                AC + ' "Cat"@en . ex:b a skos:Concept ; owl:deprecated true ; skos:inScheme ex:s ; '
                'skos:prefLabel "Cat"@en .',
            ),
            ttl(
                "empty labels",
                f'ex:a {CS} ex:s ; skos:prefLabel ""@en . ex:b {CS} ex:s ; skos:prefLabel ""@en .',
            ),
        ],
    ),
}
