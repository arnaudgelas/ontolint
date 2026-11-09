"""Cases for IRI004-IRI006, IRI008-IRI014, IRI016 and IRI017."""

from __future__ import annotations

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF
from rule_harness import built, rule_cases, ttl

from ontolint.policy import Policy


def _terms(*iris: str, kind: URIRef = OWL.Class) -> Graph:
    g = Graph()
    for iri in iris:
        g.add((URIRef(iri), RDF.type, kind))
    return g


def _ontology_and_terms(ontology: str, *iris: str) -> Graph:
    g = _terms(*iris)
    g.add((URIRef(ontology), RDF.type, OWL.Ontology))
    return g


def _many(n: int) -> Graph:
    return _terms(*(f"https://example.test/onto/t{i}" for i in range(n)))


CASES = {
    "IRI004": rule_cases(
        [built("terms elsewhere", lambda: _ontology_and_terms("https://a.test/onto", "https://b.test/ns#A"))],
        [
            built(
                "terms under ontology IRI", lambda: _ontology_and_terms("https://a.test/onto", "https://a.test/onto#A")
            ),
            built("hash ontology IRI", lambda: _ontology_and_terms("https://a.test/onto#", "https://a.test/onto#A")),
            built(
                "relative ontology IRI is IRI001's concern",
                lambda: _ontology_and_terms("onto.rdf", "https://b.test/ns#A"),
            ),
            built(
                "OBO PURL ontology with ID-style terms",
                lambda: _ontology_and_terms(
                    "http://purl.obolibrary.org/obo/x.owl", "http://purl.obolibrary.org/obo/X_1"
                ),
            ),
            built("no terms", lambda: _ontology_and_terms("https://a.test/onto")),
            built(
                "two ontologies are ambiguous",
                lambda: (
                    _ontology_and_terms("https://a.test/o1", "https://b.test/ns#A")
                    + _ontology_and_terms("https://a.test/o2")
                ),
            ),
        ],
    ),
    "IRI005": rule_cases(
        [built("hash and slash", lambda: _terms("https://a.test/ns#A", "https://a.test/ns/B"))],
        [
            built("all hash", lambda: _terms("https://a.test/ns#A", "https://a.test/ns#B")),
            built("all slash", lambda: _terms("https://a.test/ns/A", "https://a.test/ns/B")),
            built(
                "OBO subset annotation properties next to OBO IDs",
                lambda: _ontology_and_terms(
                    "http://purl.obolibrary.org/obo/x.owl",
                    "http://purl.obolibrary.org/obo/x#slim",
                    "http://purl.obolibrary.org/obo/X_0000001",
                ),
            ),
            built("namespace-only IRIs are ignored", lambda: _terms("https://a.test/ns#A", "https://a.test/other/")),
        ],
    ),
    "IRI006": rule_cases(
        [built("query string", lambda: _terms("https://a.test/term?id=1"))],
        [ttl("plain", "ex:A a owl:Class ."), built("2000 clean terms (scale)", lambda: _many(2000))],
    ),
    "IRI008": rule_cases(
        [built("http and https", lambda: _terms("http://a.test/A", "https://a.test/B"))],
        [
            built("https only", lambda: _terms("https://a.test/A", "https://a.test/B")),
            built("urn and http", lambda: _terms("urn:x:A", "http://a.test/B")),
        ],
    ),
    "IRI009": rule_cases(
        [
            built("angle bracket and brace", lambda: _terms("https://a.test/A{b}")),
            built("caret", lambda: _terms("https://a.test/A^B")),
        ],
        [ttl("plain", "ex:A a owl:Class .")],
    ),
    "IRI010": rule_cases(
        [
            built("ends in hash", lambda: _terms("https://a.test/ns#")),
            built("ends in slash", lambda: _terms("https://a.test/ns/")),
        ],
        [ttl("plain", "ex:A a owl:Class .")],
    ),
    "IRI011": rule_cases(
        [built("percent escape", lambda: _terms("https://a.test/ns#my%20term"))],
        [
            built("percent outside local name", lambda: _terms("https://a.test/a%20b/ns#term")),
            built("lone percent", lambda: _terms("https://a.test/ns#100%")),
        ],
    ),
    "IRI012": rule_cases(
        [
            built("localhost", lambda: _terms("http://localhost:8080/ns#A")),
            built("loopback", lambda: _terms("http://127.0.0.1/ns#A")),
        ],
        [
            ttl("example host", "ex:A a owl:Class ."),
            built("localhost in path only", lambda: _terms("https://a.test/localhost/A")),
        ],
    ),
    "IRI013": rule_cases(
        [
            built("v1 segment", lambda: _terms("https://a.test/v1/A")),
            built("dotted version", lambda: _terms("https://a.test/1.2.0/A")),
            built("dated", lambda: _terms("https://a.test/2024-05-01/A")),
        ],
        [
            built("plain", lambda: _terms("https://a.test/onto/A")),
            built("year only is not a version", lambda: _terms("https://a.test/2024/A")),
            built("version-like word", lambda: _terms("https://a.test/vocab/A")),
        ],
    ),
    "IRI014": rule_cases(
        [
            built("trailing underscore", lambda: _terms("https://a.test/ns#A_")),
            built("leading hyphen", lambda: _terms("https://a.test/ns#-A")),
            built("double underscore", lambda: _terms("https://a.test/ns#a__b")),
        ],
        [
            built("single separators", lambda: _terms("https://a.test/ns#a_b-c")),
            built("empty local name is IRI010", lambda: _terms("https://a.test/ns#")),
        ],
    ),
    "IRI016": rule_cases(
        [
            built("fragment", lambda: _terms("https://a.test/o#v1", kind=OWL.Ontology)),
            built("query", lambda: _terms("https://a.test/o?x=1", kind=OWL.Ontology)),
        ],
        [
            built("clean", lambda: _terms("https://a.test/o", kind=OWL.Ontology)),
            built("trailing hash is empty fragment", lambda: _terms("https://a.test/o#", kind=OWL.Ontology)),
            built("fragment on a term is fine", lambda: _terms("https://a.test/o#A")),
        ],
    ),
    "IRI017": rule_cases(
        [ttl("ontology IRI is also a class", "<https://example.test/onto> a owl:Ontology, owl:Class .")],
        [
            ttl("ontology only", "<https://example.test/onto> a owl:Ontology ."),
            ttl("class under ontology", "<https://example.test/onto> a owl:Ontology . ex:A a owl:Class ."),
        ],
    ),
    "IRI018": rule_cases(
        [
            ttl(
                "Protege untitled ontology (MFTO)",
                "<http://www.semanticweb.org/someone/ontologies/2018/8/untitled-ontology-139> a owl:Ontology .",
            ),
            ttl(
                "Protege default base, renamed",
                "<http://www.semanticweb.org/someone/ontologies/2018/8/moral> a owl:Ontology .",
            ),
        ],
        [
            ttl("a permanent IRI", "<https://w3id.org/moral> a owl:Ontology ."),
            ttl("untitled is only a word", "<https://example.test/untitled-ontology> a owl:Ontology ."),
            ttl(
                "an imported module's header",
                "<https://example.test/onto> a owl:Ontology ; owl:imports "
                "<http://www.semanticweb.org/someone/ontologies/2018/8/untitled-ontology-1> .\n"
                "<http://www.semanticweb.org/someone/ontologies/2018/8/untitled-ontology-1> a owl:Ontology .",
                policy=Policy(
                    imported_ontologies=frozenset(
                        {"http://www.semanticweb.org/someone/ontologies/2018/8/untitled-ontology-1"}
                    )
                ),
            ),
        ],
    ),
    "IRI019": rule_cases(
        [
            ttl(
                "a CCO prefix nothing uses (rights ontology)",
                "@prefix AllCoreOntology: "
                "<http://www.ontologyrepository.com/CommonCoreOntologies/Mid/AllCoreOntology#> .\n"
                "ex:A a owl:Class .",
            ),
        ],
        [
            ttl("every prefix used", "ex:A a owl:Class ."),
            ttl(
                "a prefix used only as a datatype",
                "@prefix dt: <https://dt.test/> . ex:A a owl:Class ; ex:v 'x'^^dt:custom .",
            ),
            ttl(
                "the prefix names the ontology",
                "@prefix o: <https://example.test/o#> . <https://example.test/o> a owl:Ontology . ex:A a owl:Class .",
            ),
            ttl("RDFLib's own default prefixes", "ex:A a owl:Class ."),
        ],
    ),
}
