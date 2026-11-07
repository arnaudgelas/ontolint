"""Cases for the offline FAIR rules FAIR004, FAIR006, FAIR007, FAIR011 and FAIR017 (opt-in family)."""

from __future__ import annotations

from rule_harness import Case, rule_cases, ttl

ORCID_OK = "https://orcid.org/0000-0002-1825-0097"
ORCID_X = "https://orcid.org/0000-0002-1694-233X"


def _ont(name: str, body: str, iri: str = "https://w3id.org/example/onto") -> Case:
    return ttl(name, f"<{iri}> a owl:Ontology ; {body} .")


def _version(name: str, version: str) -> Case:
    return _ont(name, f"owl:versionIRI <{version}>")


def _person(name: str, value: str) -> Case:
    return ttl(name, f"ex:o a owl:Ontology ; dcterms:creator {value} .")


CASES = {
    "FAIR004": rule_cases(
        [
            _ont("raw github", "rdfs:label 'x'", "https://raw.githubusercontent.com/org/repo/main/o.owl"),
            _ont("github.io", "rdfs:label 'x'", "https://org.github.io/onto"),
            _ont("github.com blob", "rdfs:label 'x'", "https://github.com/org/repo/blob/main/o.owl"),
            _ont("gitlab", "rdfs:label 'x'", "https://gitlab.com/org/repo/-/raw/main/o.owl"),
            _ont("localhost", "rdfs:label 'x'", "http://localhost:8080/onto"),
            _ont("ip address", "rdfs:label 'x'", "http://192.168.0.10/onto"),
            _ont("ipv6 address", "rdfs:label 'x'", "http://[::1]/onto"),
            _ont("local file", "rdfs:label 'x'", "file:///home/me/o.owl"),
            _version("mutable version IRI only", "https://raw.githubusercontent.com/org/repo/v1.0/o.owl"),
        ],
        [
            _ont("w3id", "rdfs:label 'x'"),
            _ont("purl", "rdfs:label 'x'", "http://purl.org/example/onto"),
            _ont("obo purl", "rdfs:label 'x'", "http://purl.obolibrary.org/obo/xyz.owl"),
            _ont("w3.org namespace", "rdfs:label 'x'", "http://www.w3.org/ns/org#"),
            _ont("foaf namespace", "rdfs:label 'x'", "http://xmlns.com/foaf/0.1/"),
            _ont("institutional domain", "rdfs:label 'x'", "https://ontology.example.edu/onto"),
            _ont("look-alike host", "rdfs:label 'x'", "https://notgithub.com/onto"),
            _ont("urn", "rdfs:label 'x'", "urn:example:onto"),
            _version("persistent version", "https://w3id.org/example/onto/1.0"),
            ttl("no ontology header", "ex:A a owl:Class ."),
        ],
    ),
    "FAIR006": rule_cases(
        [
            _ont("plain text", "dcterms:license 'CC BY 4.0'"),
            _ont("url as string", "dcterms:license 'https://creativecommons.org/licenses/by/4.0/'"),
            _ont("typed anyURI", "dcterms:license 'https://creativecommons.org/licenses/by/4.0/'^^xsd:anyURI"),
            _ont("unknown licence iri", "dcterms:license <https://example.org/my-licence>"),
            _ont("cc namespace predicate", "<http://creativecommons.org/ns#license> 'MIT'"),
            _ont("schema.org licence", "<https://schema.org/license> 'MIT'"),
            _ont("look-alike host", "dcterms:license <https://notspdx.org/licenses/MIT>"),
            _ont("lookalike path", "dcterms:license <https://example.org/creativecommons.org/licenses/by/4.0/>"),
        ],
        [
            _ont("cc by", "dcterms:license <https://creativecommons.org/licenses/by/4.0/>"),
            _ont("cc by http", "dcterms:license <http://creativecommons.org/licenses/by/4.0/>"),
            _ont("cc zero", "dcterms:license <https://creativecommons.org/publicdomain/zero/1.0/>"),
            _ont("spdx", "dcterms:license <https://spdx.org/licenses/Apache-2.0>"),
            _ont("osi", "dcterms:license <https://opensource.org/licenses/MIT>"),
            _ont("gnu with www", "dcterms:license <https://www.gnu.org/licenses/gpl-3.0.html>"),
            _ont("open data commons", "dcterms:license <http://www.opendatacommons.org/licenses/pddl/1.0/>"),
            _ont("no licence", "rdfs:label 'x'"),
            _ont("blank licence text", "dcterms:license ' '"),
            _ont("blank node licence", "dcterms:license [ a ex:License ]"),
            ttl("licence on a term is out of scope", "ex:A a owl:Class ; dcterms:license 'MIT' ."),
        ],
    ),
    "FAIR007": rule_cases(
        [
            _version("same as ontology IRI", "https://w3id.org/example/onto"),
            _version("same up to trailing slash", "https://w3id.org/example/onto/"),
            _version("latest", "https://w3id.org/example/onto/latest"),
            _version("master", "https://w3id.org/example/onto/master/o.owl"),
            _version("main", "https://w3id.org/example/onto/main"),
            _version("current uppercase", "https://w3id.org/example/onto/CURRENT"),
            _version("dev", "https://w3id.org/example/onto/dev/o.owl"),
            _version("marker with a digit still floats", "https://w3id.org/example/onto/head/2024"),
            _version("no version token", "https://w3id.org/example/onto/release"),
            _version("only a new non-digit token", "https://w3id.org/example/onto/final.owl"),
        ],
        [
            _version("dated", "https://w3id.org/example/onto/2024-01-31/onto.owl"),
            _version("semantic version", "https://w3id.org/example/onto/1.2.0"),
            _version("v prefix", "https://w3id.org/example/onto/v2"),
            _version("version in the fragment", "https://w3id.org/example/onto#2024"),
            _version("obo release", "http://purl.obolibrary.org/obo/xyz/releases/2024-01-31/xyz.owl"),
            _ont(
                "marker already in the ontology IRI",
                "owl:versionIRI <https://w3id.org/main/onto/2024>",
                "https://w3id.org/main/onto",
            ),
            _ont("no version IRI", "rdfs:label 'x'"),
        ],
    ),
    "FAIR011": rule_cases(
        [
            _person("bad ORCID checksum", f"<{ORCID_OK[:-1]}8>"),
            _person("short ORCID", "<https://orcid.org/0000-0002-1825-009>"),
            _person("ORCID without dashes", "<https://orcid.org/0000000218250097>"),
            _person("lowercase x", "<https://orcid.org/0000-0002-1694-233x>"),
            _person("trailing slash", f"<{ORCID_OK}/>"),
            _person("ORCID literal URL bad checksum", f"'{ORCID_OK[:-1]}8'"),
            _person("bare literal ORCID bad checksum", "'Jane Doe 0000-0002-1825-0098'"),
            _person("orcid host without id", "'see orcid.org/jane'"),
            _person("ROR bad checksum", "<https://ror.org/02mhbdp95>"),
            _person("ROR bad shape", "<https://ror.org/02mhbdp9>"),
            _person("ROR with forbidden letter", "<https://ror.org/02mhbdu94>"),
            _person("ROR literal", "'https://ror.org/02mhbdp95'"),
            ttl("contributor on a term", f"ex:A a owl:Class ; dcterms:contributor <{ORCID_OK[:-1]}8> ."),
            ttl("dc creator", f"ex:o a owl:Ontology ; <http://purl.org/dc/elements/1.1/creator> <{ORCID_OK[:-1]}8> ."),
        ],
        [
            _person("valid ORCID", f"<{ORCID_OK}>"),
            _person("valid ORCID with X", f"<{ORCID_X}>"),
            _person("valid ORCID http and www", "<http://www.orcid.org/0000-0002-1825-0097>"),
            _person("valid ORCID literal", f"'{ORCID_OK}'"),
            _person("valid bare ORCID in text", "'Jane Doe (0000-0002-1825-0097)'"),
            _person("valid ORCID followed by a dot", f"'{ORCID_OK}.'"),
            _person("valid ROR", "<https://ror.org/02mhbdp94>"),
            _person("valid ROR literal", "'https://ror.org/01ggx4157'"),
            _person("plain name", "'Jane Doe'"),
            _person("other identifier IRI", "<https://example.org/people/jane>"),
            _person("blank node", "[ a ex:Person ]"),
            ttl("a number that looks nothing like an ORCID", "ex:o a owl:Ontology ; dcterms:creator '1234-5678' ."),
            ttl("unrelated predicate is ignored", "ex:o a owl:Ontology ; rdfs:comment 'orcid.org/bad' ."),
        ],
    ),
    "FAIR017": rule_cases(
        [
            _ont("deprecated ontology", "owl:deprecated true"),
            ttl(
                "deprecated version node",
                "<https://w3id.org/example/onto> a owl:Ontology ;"
                " owl:versionIRI <https://w3id.org/example/onto/1.0> .\n"
                "<https://w3id.org/example/onto/1.0> owl:deprecated true .",
            ),
            _ont("literal 1 is true", "owl:deprecated '1'^^xsd:boolean"),
            _ont("blank replacement text", "owl:deprecated true ; dcterms:isReplacedBy ' '"),
            ttl(
                "self-referencing predecessor",
                "<https://w3id.org/example/onto> a owl:Ontology ; owl:deprecated true ;"
                " owl:priorVersion <https://w3id.org/example/onto> .",
            ),
        ],
        [
            _ont("replaced by", "owl:deprecated true ; dcterms:isReplacedBy <https://w3id.org/example/new>"),
            _ont(
                "IAO replaced by",
                "owl:deprecated true ; <http://purl.obolibrary.org/obo/IAO_0100001> <https://w3id.org/new>",
            ),
            _ont("replaced by a text", "owl:deprecated true ; dcterms:isReplacedBy 'the 2024 ontology'"),
            _ont("structured replacement node", "owl:deprecated true ; dcterms:isReplacedBy []"),
            _ont("not deprecated", "rdfs:label 'x'"),
            _ont("deprecated false", "owl:deprecated false"),
            _ont("deprecated false-typed", "owl:deprecated '0'^^xsd:boolean"),
            ttl(
                "successor names this ontology as its predecessor",
                "<https://w3id.org/example/onto> a owl:Ontology ; owl:deprecated true .\n"
                "<https://w3id.org/example/new> a owl:Ontology ; owl:priorVersion <https://w3id.org/example/onto> .",
            ),
            ttl(
                "successor replaces this ontology",
                "<https://w3id.org/example/onto> a owl:Ontology ; owl:deprecated true .\n"
                "<https://w3id.org/example/new> a owl:Ontology ; dcterms:replaces <https://w3id.org/example/onto> .",
            ),
            ttl(
                "pointer on the ontology covers a deprecated version",
                "<https://w3id.org/example/onto> a owl:Ontology ; dcterms:isReplacedBy <https://w3id.org/example/new> ;"
                " owl:versionIRI <https://w3id.org/example/onto/1.0> .\n"
                "<https://w3id.org/example/onto/1.0> owl:deprecated true .",
            ),
            ttl("a deprecated term is not an ontology", "ex:A a owl:Class ; owl:deprecated true ."),
        ],
    ),
}
