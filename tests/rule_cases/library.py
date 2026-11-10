"""Cases for LIB001-LIB003: a pattern-library index (the graph) against its members (``Policy.library``).

The members are built directly; :mod:`tests.test_pattern_library` reads them from files.  The layout
copies MODL: entries are individuals of the index's own ``Pattern`` class, the patterns are ontologies
in another namespace, and categories are individuals of another class.
"""

from __future__ import annotations

from rule_harness import Case, rule_cases, ttl

from ontolint.models import LibraryMember, PatternLibrary
from ontolint.policy import Policy

DOMAIN = "https://example.test/library/"
INDEX = "ex:Pattern a owl:Class . ex:Category a owl:Class . ex:Places a owl:NamedIndividual , ex:Category .\n"
RELATED = "http://ontologydesignpatterns.org/opla-core#hasRelatedPattern"


def _member(name: str, *, title: str = "", refs: tuple[tuple[str, str], ...] = ()) -> LibraryMember:
    iri = DOMAIN + name
    return LibraryMember(
        f"{name}.ttl", f"file:///lib/{name}.ttl", iri, frozenset({iri}), (title,) if title else (), refs
    )


def _library(*members: LibraryMember, unreadable: tuple[str, ...] = ()) -> Policy:
    return Policy(library=PatternLibrary("lib", members, unreadable))


EVENT = _member("event", title="Event Pattern")
PLACE = _member("place", title="Place")


def case(name: str, turtle: str, policy: Policy) -> Case:
    return ttl(name, INDEX + turtle, base="https://example.test/onto#", policy=policy)


CASES = {
    "LIB001": rule_cases(
        [
            case(
                "same name, no IRI link (MODL)",
                "ex:Event a owl:NamedIndividual , ex:Pattern .",
                _library(EVENT),
            ),
            case(
                "an entry of the entry class with no member at all",
                f"ex:Event a ex:Pattern ; rdfs:isDefinedBy <{DOMAIN}event> . ex:Ghost a ex:Pattern .",
                _library(EVENT),
            ),
            case(
                "no member, and an unreadable file in the library",
                f"ex:Event a ex:Pattern ; rdfs:seeAlso <{DOMAIN}event> . ex:Ghost a ex:Pattern .",
                _library(EVENT, unreadable=("broken.ttl",)),
            ),
        ],
        [
            case(
                "linked by rdfs:isDefinedBy",
                f"ex:Event a ex:Pattern ; rdfs:isDefinedBy <{DOMAIN}event> .",
                _library(EVENT),
            ),
            case("the entry is the member", f"<{DOMAIN}event> a ex:Pattern .", _library(EVENT)),
            case(
                "the member's header names the entry",
                "ex:Event a ex:Pattern .",
                _library(_member("event", refs=((RELATED, "https://example.test/onto#Event"),))),
            ),
            case(
                "an individual of another class (a category)",
                f"ex:Event a ex:Pattern ; rdfs:isDefinedBy <{DOMAIN}event> .",
                _library(EVENT),
            ),
            case("no entry class can be inferred", "ex:Thing a ex:Pattern .", _library(EVENT)),
            case(
                "a foreign individual of the entry class is not an entry",
                f"ex:Event a ex:Pattern ; rdfs:isDefinedBy <{DOMAIN}event> . <http://other.test/Ghost> a ex:Pattern .",
                _library(EVENT),
            ),
            case(
                "a class of the index typed with the entry class is not an entry",
                f"ex:Event a ex:Pattern ; rdfs:isDefinedBy <{DOMAIN}event> . ex:Ghost a owl:Class , ex:Pattern .",
                _library(EVENT),
            ),
        ],
    ),
    "LIB002": rule_cases(
        [
            case(
                "a member nothing names",
                f"ex:Event a ex:Pattern ; rdfs:isDefinedBy <{DOMAIN}event> .",
                _library(EVENT, PLACE),
            ),
            case("an index with no entries at all", "", _library(EVENT)),
        ],
        [
            case("every member linked", f"ex:Event a ex:Pattern ; rdfs:isDefinedBy <{DOMAIN}event> .", _library(EVENT)),
            case("a member matched by name only (LIB001 reports it)", "ex:Event a ex:Pattern .", _library(EVENT)),
        ],
    ),
    "LIB003": rule_cases(
        [
            case(
                "a related pattern the library lacks",
                "",
                _library(_member("agentrole", refs=((RELATED, DOMAIN + "agent"),)), EVENT),
            ),
        ],
        [
            case(
                "a related pattern the library has",
                "",
                _library(_member("agentrole", refs=((RELATED, DOMAIN + "event"),)), EVENT),
            ),
            case(
                "a term of a member, not a member",
                "",
                _library(_member("agentrole", refs=((RELATED, DOMAIN + "event#Event"),)), EVENT),
            ),
            case(
                "an IRI outside the library namespace",
                "",
                _library(
                    _member("agentrole", refs=((RELATED, "http://www.ontologydesignpatterns.org/ont/dul/DUL.owl"),)),
                    EVENT,
                ),
            ),
            case(
                "one member: no library namespace",
                "",
                _library(_member("agentrole", refs=((RELATED, DOMAIN + "agent"),))),
            ),
            case(
                "members sharing only the host: no library namespace",
                "",
                Policy(
                    library=PatternLibrary(
                        "lib",
                        (
                            LibraryMember(
                                "a.ttl",
                                "file:///a.ttl",
                                "https://example.test/a",
                                frozenset({"https://example.test/a"}),
                                (),
                                ((RELATED, "https://example.test/zzz"),),
                            ),
                            LibraryMember(
                                "b.ttl",
                                "file:///b.ttl",
                                "https://example.test/b",
                                frozenset({"https://example.test/b"}),
                            ),
                        ),
                    )
                ),
            ),
        ],
    ),
}
