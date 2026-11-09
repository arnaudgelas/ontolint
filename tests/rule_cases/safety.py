"""Cases for SEC004, SEC005, SEC008, SEC012 and SEC014 (graph-local security hygiene)."""

from __future__ import annotations

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import RDF
from rule_harness import BASE, built, rule_cases, ttl


def bnode_chain(depth: int) -> Graph:
    """``ex:a ex:p _:b1 . _:b1 ex:p _:b2 ...`` with ``depth`` nested blank nodes."""
    g = Graph()
    previous: URIRef | BNode = URIRef(BASE + "a")
    for _ in range(depth):
        node = BNode()
        g.add((previous, URIRef(BASE + "p"), node))
        previous = node
    return g


def long_list(length: int) -> Graph:
    g = Graph()
    head: URIRef | BNode = RDF.nil
    for i in range(length):
        node = BNode()
        g.add((node, RDF.first, Literal(i)))
        g.add((node, RDF.rest, head))
        head = node
    g.add((URIRef(BASE + "a"), URIRef(BASE + "p"), head))
    return g


def literal_graph(value: str) -> Graph:
    g = Graph()
    g.add((URIRef(BASE + "a"), URIRef(BASE + "p"), Literal(value)))
    return g


def iri_graph(iri: str) -> Graph:
    g = Graph()
    g.add((URIRef(iri), RDF.type, URIRef(BASE + "T")))
    return g


CASES = {
    "SEC004": rule_cases(
        [
            built("101 nested blank nodes", lambda: bnode_chain(101)),
            built("list of 5001 members", lambda: long_list(5001)),
        ],
        [
            built("100 nested blank nodes", lambda: bnode_chain(100)),
            built("list of 5000 members", lambda: long_list(5000)),
            ttl("small list", "ex:a ex:p ( 1 2 3 ) ."),
            ttl("blank-node cycle", "_:a ex:p _:b . _:b ex:p _:a ."),
        ],
    ),
    "SEC005": rule_cases(
        [built("literal of 100001 characters", lambda: literal_graph("x" * 100_001))],
        [
            built("literal of 100000 characters", lambda: literal_graph("x" * 100_000)),
            ttl("short literal", 'ex:a rdfs:label "A" .'),
        ],
    ),
    "SEC008": rule_cases(
        [
            ttl("file IRI", "ex:a ex:p <file:///etc/passwd> ."),
            ttl("javascript IRI", "ex:a ex:p <javascript:alert(1)> ."),
            ttl("data IRI in subject", "<data:text/plain;base64,AAAA> a owl:Class ."),
            ttl("ftp IRI uppercase", "ex:a ex:p <FTP://example.test/x> ."),
            built("obfuscated scheme", lambda: iri_graph("java\tscript:alert(1)")),
            built("leading space", lambda: iri_graph(" javascript:alert(1)")),
        ],
        [
            ttl("https IRI", "ex:a ex:p <https://example.test/x> ."),
            ttl("urn IRI", "ex:a ex:p <urn:isbn:0451450523> ."),
            ttl("unsafe word in path", "ex:a ex:p <https://example.test/file:/x> ."),
            built("relative IRI", lambda: iri_graph("relative/file:x")),
        ],
    ),
    "SEC012": rule_cases(
        [
            ttl("bidi override in label", 'ex:a rdfs:label "abc\\u202Edef" .'),
            ttl("bidi isolate in label", 'ex:a rdfs:label "abc\\u2066def" .'),
            ttl("NUL in label", 'ex:a rdfs:label "abc\\u0000def" .'),
            ttl("escape in label", 'ex:a rdfs:label "abc\\u001Bdef" .'),
            ttl("C1 control in label", 'ex:a rdfs:label "abc\\u0085def" .'),
            built("bidi in IRI", lambda: iri_graph(BASE + "a\u202eb")),
            built("tab in IRI", lambda: iri_graph(BASE + "a\tb")),
        ],
        [
            ttl("plain label", 'ex:a rdfs:label "abc" .'),
            ttl("tab and newline in literal", 'ex:a rdfs:comment "a\\tb\\nc\\rd" .'),
            ttl("right-to-left text", 'ex:a rdfs:label "שלום مرحبا" .'),
            ttl("directional mark", 'ex:a rdfs:label "abc\\u200Fdef" .'),
            ttl("last bidi code point not isolate", 'ex:a rdfs:label "abc\\u206Adef" .'),
        ],
    ),
    "SEC014": rule_cases(
        [
            ttl("user and password", "ex:a ex:p <https://alice:secret@example.test/x> ."),
            ttl("subject IRI", "<https://bob:pw@example.test/> a owl:Class ."),
            ttl("predicate IRI", "ex:a <https://bob:pw@example.test/p> ex:b ."),
            ttl("empty user name", "ex:a ex:p <https://:fake-pw@example.test/x> ."),
            ttl("upper-case scheme", "ex:a ex:p <HTTP://alice:fake-pw@example.test/x> ."),
            ttl("other scheme", "ex:a ex:p <ftp://alice:fake-pw@example.test/file> ."),
            ttl("colon inside the password", "ex:a ex:p <https://alice:fake:pw@example.test/x> ."),
            ttl("with a port", "ex:a ex:p <https://alice:fake-pw@example.test:8443/x> ."),
        ],
        [
            ttl("user without password", "ex:a ex:p <https://alice@example.test/x> ."),
            ttl("token as user name", "ex:a ex:p <https://fake-token@example.test/x> ."),
            ttl("empty password", "ex:a ex:p <https://alice:@example.test/x> ."),
            ttl("percent-encoded colon", "ex:a ex:p <https://alice%3Afake@example.test/x> ."),
            ttl("at sign in path", "ex:a ex:p <https://example.test/a:b@c> ."),
            ttl("at sign in query", "ex:a ex:p <https://example.test/x?u=a:b@c> ."),
            ttl("mailto", "ex:a ex:p <mailto:a:b@example.test> ."),
            ttl("empty authority", "ex:a ex:p <file:///a:b@c> ."),
            ttl("plain", "ex:a ex:p <https://example.test:8080/x> ."),
            ttl("anyURI literal is not an IRI", 'ex:a ex:p "https://alice:fake-pw@example.test/"^^xsd:anyURI .'),
        ],
    ),
}
