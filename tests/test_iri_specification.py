"""The IRI family specification (see the ``identifiers``, ``iri_quality`` and ``iri_lexical_extras`` docstrings).

One section per rule: each pins a condition, an exclusion, a boundary or a known gap of the rule's specification,
with the standard it rests on.  RFC 3986 is the URI generic syntax (2005), RFC 3987 its IRI extension (2005).
A comment that says *gap* pins what the rule does today although the cited standard, or the rule's own title,
would let it do more or less: it is a documented limit, to be revisited by a decision, not a defect.

Relative IRIs: every parser ontolint reads a file with resolves a relative reference against the document
(RFC 3986 section 5), so a term of a loaded file is absolute whatever the file wrote.  ``--base`` is an ownership
prefix (``Linter(base=...)``), never a resolution base.  The userinfo section pins what the IRI rules print of an IRI
with a userinfo (RFC 3986 section 3.2.1): ``redaction.py`` is the specification, the SEC rules its other readers.
"""

from __future__ import annotations

import csv
from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF
from rule_harness import graph

from ontolint import Linter

NS = "https://example.test/onto#"
OBO = "http://purl.obolibrary.org/obo/"
CATALOGUE = Path(__file__).resolve().parent.parent / "data" / "rule_catalogue.csv"


def _built(iris: tuple[str, ...] = (), onts: tuple[str, ...] = (), kind: URIRef = OWL.Class) -> Graph:
    g = Graph()
    for iri in iris:
        g.add((URIRef(iri), RDF.type, kind))
    for iri in onts:
        g.add((URIRef(iri), RDF.type, OWL.Ontology))
    return g


def _findings(rule: str, g: Graph, **options: object) -> list[tuple[str, str]]:
    result = Linter(g, **options).execute([rule])  # type: ignore[arg-type]
    return sorted((f.focus, f.message) for f in result.findings)


def _foci(
    rule: str,
    iris: tuple[str, ...] = (),
    onts: tuple[str, ...] = (),
    kind: URIRef = OWL.Class,
    **options: object,
) -> list[str]:
    return [focus for focus, _ in _findings(rule, _built(iris, onts, kind), **options)]


def _ttl(rule: str, turtle: str, **options: object) -> list[str]:
    return [focus.removeprefix(NS) for focus, _ in _findings(rule, graph(turtle), **options)]


# --- IRI001 (RFC 3986 4.3 absolute-URI, 3987 2.2: no space in an IRI) ----------------------------------


def test_iri001_whitespace_or_no_scheme() -> None:
    assert _foci("IRI001", ("rel/x",)) == ["rel/x"]
    assert _foci("IRI001", ("https://a.test/a b",)) == ["https://a.test/a b"]
    # str.isspace: a tab, a no-break space and an ideographic space are whitespace too.
    for blank in ("\t", " ", "　"):
        assert _foci("IRI001", (f"https://a.test/a{blank}b",)) != []
    # A scheme starts with a letter (RFC 3986 3.1).
    assert _foci("IRI001", ("1a:b",)) == ["1a:b"]


def test_iri001_two_messages_for_two_conditions() -> None:
    assert _findings("IRI001", _built(("rel/x",))) == [("rel/x", "IRI contains whitespace or is not absolute.")]
    assert _findings("IRI001", _built(("http:example.org/x",))) == [
        ("http:example.org/x", "http: IRI has no '//' host, so it cannot be dereferenced.")
    ]


def test_iri001_http_without_host() -> None:
    assert _foci("IRI001", ("http:///x",)) == ["http:///x"]
    assert _foci("IRI001", ("HTTPS:///x",)) == ["HTTPS:///x"]
    # Exclusions: other schemes have no host rule, and a URN is absolute.
    assert _foci("IRI001", ("urn:x:a", "file:///x", "mailto:a@b.test")) == []
    # Gap: an empty host with a port (RFC 3986 3.2.2 allows an empty reg-name, which no http client can use)
    # is not reported, because the authority is not empty.
    assert _foci("IRI001", ("http://:80/x",)) == []


def test_iri001_judges_ontology_iris_too() -> None:
    assert _foci("IRI001", onts=("rel",)) == ["rel"]
    assert _foci("IRI001", onts=("https://a.test/o",)) == []


def test_iri001_a_relative_reference_in_a_file_is_resolved_before_the_rule_runs() -> None:
    # RFC 3986 5: the parser resolves "<rel>" against the document, so the term is absolute (a file: IRI here).
    assert _ttl("IRI001", "<rel> a owl:Class . <> a owl:Ontology .") == []
    assert _ttl("IRI001", "@base <https://a.test/d/> . <rel> a owl:Class .") == []


def test_iri001_base_selects_terms_and_does_not_resolve() -> None:
    # A relative IRI that only a hand-built graph can hold stays relative whatever --base says.
    assert _foci("IRI001", ("rel/x",), base="rel/") == ["rel/x"]
    # --base is an ownership prefix: a term outside it is not judged.
    assert _foci("IRI001", ("rel/x",), base="https://other.test/") == []


def test_iri001_does_not_report_what_iri009_reports() -> None:
    # RFC 3987 2.2 excludes the space too; IRI009 deliberately leaves it to IRI001.
    assert _foci("IRI009", ("https://a.test/a b",)) == []
    assert _foci("IRI009", ("https://a.test/a b{",)) == ["https://a.test/a b{"]


# --- IRI002 -------------------------------------------------------------------------------------------


def test_iri002_extension_of_the_path() -> None:
    for ontology in ("https://a.test/o.owl", "https://a.test/o.OWL", "https://a.test/o.ttl", "https://a.test/o.rdfxml"):
        assert _foci("IRI002", onts=(ontology,)) == [ontology]
    assert _foci("IRI002", onts=("https://a.test/o.n3", "https://a.test/o.rdf")) != []


def test_iri002_reads_the_path_and_ignores_query_and_fragment() -> None:
    assert _foci("IRI002", onts=("https://a.test/o.owl?x=1",)) == ["https://a.test/o.owl?x=1"]
    assert _foci("IRI002", onts=("https://a.test/o.owl#",)) == ["https://a.test/o.owl#"]
    assert _foci("IRI002", onts=("https://a.test/o.owl#x",)) == ["https://a.test/o.owl#x"]
    assert _foci("IRI002", onts=("https://a.test/o.owl/",)) == []


def test_iri002_known_extensions_only() -> None:
    # Gap: ownership strips .jsonld, .json, .ofn, .omn, .owx, .obo and .nt too (ontolint.ownership.FILE_EXTENSIONS);
    # IRI002 names only owl, ttl, n3, rdf and rdfxml.
    assert _foci("IRI002", onts=("https://a.test/o.jsonld", "https://a.test/o.nt", "https://a.test/o.obo")) == []


def test_iri002_obo_purls_and_terms_are_exempt() -> None:
    assert _foci("IRI002", onts=(OBO + "x.owl",)) == []
    assert _foci("IRI002", ("https://a.test/o.owl",)) == []


# --- IRI003 -------------------------------------------------------------------------------------------


def test_iri003_same_local_name_in_two_namespaces() -> None:
    found = _findings("IRI003", _built(("https://a.test/A", "https://b.test/A")))
    assert found == [("https://a.test/A", "Local-name collision across IRIs: https://a.test/A, https://b.test/A")]


def test_iri003_compares_case_folded_names() -> None:
    assert _foci("IRI003", ("https://a.test/A", "https://b.test/a")) == ["https://a.test/A"]
    # Hash and slash namespaces are namespaces alike.
    assert _foci("IRI003", ("https://a.test/ns#A", "https://a.test/ns/A")) == ["https://a.test/ns#A"]


def test_iri003_gap_the_title_says_across_namespaces_but_one_namespace_collides_on_case() -> None:
    assert _foci("IRI003", ("https://a.test/A", "https://a.test/a")) == ["https://a.test/A"]


def test_iri003_gap_two_empty_local_names_collide() -> None:
    # The empty name is IRI010's concern; it still counts as a name here.
    assert _foci("IRI003", ("https://a.test/", "https://b.test/")) == ["https://a.test/"]


def test_iri003_exclusions() -> None:
    assert _foci("IRI003", ("https://a.test/A", "https://b.test/B")) == []
    # A class and a property sharing a name are ordinary style; so are a class and a concept.
    g = _built(("https://a.test/A",)) + _built(("https://b.test/A",), kind=OWL.ObjectProperty)
    assert _findings("IRI003", g) == []
    assert _ttl("IRI003", "ex:Agent a owl:Class . ex:agent a skos:Concept .") == []
    # A deprecated term leaves the comparison; an ontology IRI is no term.
    assert _ttl("IRI003", "ex:A a owl:Class ; owl:deprecated true . <https://b.test/A> a owl:Class .") == []
    assert _foci("IRI003", ("https://a.test/A",), onts=("https://b.test/A",)) == []


def test_iri003_one_finding_names_at_most_five_iris() -> None:
    iris = tuple(f"https://{c}.test/A" for c in "abcdefg")
    ((focus, message),) = _findings("IRI003", _built(iris))
    assert focus == "https://a.test/A"
    assert message == "Local-name collision across IRIs: " + ", ".join(iris[:5])


# --- IRI004 -------------------------------------------------------------------------------------------


def test_iri004_no_term_under_the_ontology_iri() -> None:
    assert _foci("IRI004", ("https://b.test/A",), ("https://a.test/o",)) == ["https://a.test/o"]
    # One term under it is enough.
    assert _foci("IRI004", ("https://b.test/A", "https://a.test/o#X"), ("https://a.test/o",)) == []


def test_iri004_the_ontology_iri_is_a_namespace_prefix_up_to_its_trailing_separator() -> None:
    assert _foci("IRI004", ("https://a.test/o/A",), ("https://a.test/o/",)) == []
    assert _foci("IRI004", ("https://a.test/o/X",), ("https://a.test/o#",)) == []
    # Plain string prefix: "ontology/A" starts with "o" (the rule does not test a separator after it).
    assert _foci("IRI004", ("https://a.test/ontology/A",), ("https://a.test/o",)) == []
    assert _foci("IRI004", ("http://a.test/o#X",), ("https://a.test/o",)) == ["https://a.test/o"]


def test_iri004_gap_an_extension_or_query_is_not_stripped() -> None:
    # Ownership derives the namespace "https://a.test/o#" from "o.owl" (ontolint.ownership.derive_prefixes), but
    # IRI004 compares with the whole IRI: the term that ownership owns is reported as unrelated.  A convention,
    # not a standard: RFC 3987 relates no IRI to another by a prefix.
    assert _foci("IRI004", ("https://a.test/o#X",), ("https://a.test/o.owl",)) == ["https://a.test/o.owl"]
    assert _foci("IRI004", ("https://a.test/o/X",), ("https://a.test/o?x=1",)) == ["https://a.test/o?x=1"]


def test_iri004_exclusions() -> None:
    assert _foci("IRI004", (), ("https://a.test/o",)) == []  # no term
    two = _built(("https://b.test/A",), ("https://a.test/o1", "https://a.test/o2"))
    assert _findings("IRI004", two) == []  # two ontologies: ambiguous
    assert _foci("IRI004", ("https://b.test/A",), (OBO + "x.owl",)) == []  # OBO has its own scheme
    assert _foci("IRI004", ("https://a.test/o#X",), ("rel",)) == []  # not absolute: IRI001's concern


def test_iri004_base_decides_which_terms_exist() -> None:
    assert _foci("IRI004", ("https://b.test/A",), ("https://a.test/o",), base="https://b.test/") == ["https://a.test/o"]
    assert _foci("IRI004", ("https://a.test/o#X",), ("https://a.test/o#",), base="https://zz.test/") == []


# --- IRI005 -------------------------------------------------------------------------------------------


def test_iri005_hash_and_slash_terms_together() -> None:
    found = _findings("IRI005", _built(("https://a.test/ns#A", "https://a.test/B")))
    assert found == [
        ("(vocabulary)", "1 hash-style and 1 slash-style term IRIs, e.g. https://a.test/ns#A and https://a.test/B.")
    ]


def test_iri005_exclusions_and_boundaries() -> None:
    assert _foci("IRI005", ("https://a.test/ns#A", "https://a.test/ns#B")) == []
    # An IRI with no local name is not counted, and a URN with no "#" is slash-style.
    assert _foci("IRI005", ("https://a.test/ns#", "https://a.test/B")) == []
    assert _foci("IRI005", ("urn:x:a", "https://a.test/ns#A")) == [
        "(vocabulary)"
    ]  # a URN has no "#": it counts as slash-style
    assert _foci("IRI005", ("https://a.test/ns#A", "https://b.test/B"), base="https://a.test/") == []
    # Slim annotation IRIs of an OBO ontology are exempt; the exemption needs an OBO ontology IRI.
    obo = _built((OBO + "x#slim", OBO + "X_1"), (OBO + "x.owl",))
    assert _findings("IRI005", obo) == []
    assert _foci("IRI005", (OBO + "x#slim", OBO + "X_1")) == ["(vocabulary)"]


# --- IRI006 (RFC 3986 3.4: the query follows the first "?" and ends at "#") ----------------------------


def test_iri006_query_of_a_term_iri() -> None:
    assert _foci("IRI006", ("https://a.test/term?id=1",)) == ["https://a.test/term?id=1"]
    # RFC 3986 3.4: the query may be empty; the rule reports it as a query.
    assert _foci("IRI006", ("https://a.test/x?",)) == ["https://a.test/x?"]
    assert _foci("IRI006", ("https://a.test/x?a#b",)) == ["https://a.test/x?a#b"]


def test_iri006_gap_a_question_mark_in_a_fragment_is_no_query_but_is_reported() -> None:
    # RFC 3986 3.5 lets a fragment hold "?": "#a?b" has no query.  The rule tests "?" in the whole IRI.
    assert _foci("IRI006", ("https://a.test/x#a?b",)) == ["https://a.test/x#a?b"]


def test_iri006_exclusions() -> None:
    assert _ttl("IRI006", "ex:A a owl:Class .") == []
    assert _foci("IRI006", (), ("https://a.test/o?x=1",)) == []  # an ontology IRI is IRI016's
    assert _foci("IRI006", ("https://a.test/o?x=1#A",), base="https://zz.test/") == []


# --- IRI007: network dependent, issue #38 ----------------------------------------------------------------


def test_iri007_stays_proposed() -> None:
    with CATALOGUE.open(newline="", encoding="utf-8") as handle:
        row = next(r for r in csv.DictReader(handle) if r["rule_id"] == "IRI007")
    assert row["status"] == "proposed"
    assert _foci("IRI001", ("https://a.test/A",)) == []  # nothing here dereferences an IRI


# --- IRI008 ----------------------------------------------------------------------------------------------


def test_iri008_http_and_https_terms() -> None:
    found = _findings("IRI008", _built(("http://a.test/A", "https://b.test/B")))
    assert found == [("(vocabulary)", "Terms mix http and https IRIs.")]
    assert _foci("IRI008", ("HTTP://a.test/A", "https://b.test/B")) == ["(vocabulary)"]
    # The same name in both schemes is two terms.
    assert _foci("IRI008", ("http://a.test/A", "https://a.test/A")) == ["(vocabulary)"]


def test_iri008_exclusions_and_boundaries() -> None:
    assert _foci("IRI008", ("https://a.test/A", "https://a.test/B")) == []
    assert _foci("IRI008", ("urn:x:A", "http://a.test/B")) == []
    assert _foci("IRI008", ("http://a.test/", "https://b.test/B")) == []  # no local name: not counted
    assert _foci("IRI008", ("http://a.test/A", "https://a.test/A"), base="https://a.test/") == []


# --- IRI009 (RFC 3987 2.2 and RFC 3986 2.2: the characters an IRI may not hold) -----------------------


def test_iri009_each_character_of_the_set() -> None:
    for character in '<>"{}|\\^`':
        iri = f"https://a.test/a{character}b"
        assert _foci("IRI009", (iri,)) == [iri], character


def test_iri009_gaps() -> None:
    # Gap: RFC 3986 2.1 says "%" is only the start of a percent-encoded octet; a lone "%" is no IRI.  Nothing reports it
    # (IRI011 reads only well-formed escapes).
    assert _foci("IRI009", ("https://a.test/100%", "https://a.test/ns#%zz")) == []
    assert _foci("IRI011", ("https://a.test/ns#%zz", "https://a.test/ns#%")) == []
    # Gap: a control character, and a character outside ucschar (RFC 3987 2.2), are not in the set.
    assert _foci("IRI009", ("https://a.test/a\x01", "https://a.test/a￾b")) == []
    # A non-ASCII letter is what an IRI exists for (RFC 3987 2.2 ucschar).
    assert _foci("IRI009", ("https://a.test/é",)) == []
    # Gap: the title says "IRI", the scope is the term: an ontology IRI is not read.
    assert _foci("IRI009", (), ("https://a.test/o{",)) == []


def test_iri009_base_and_reporting() -> None:
    assert _foci("IRI009", ('https://a.test/a"b',), base="https://zz.test/") == []
    assert _findings("IRI009", _built(("https://a.test/a`",))) == [
        ("https://a.test/a`", "IRI contains characters that are not allowed in IRIs.")
    ]


# --- IRI010 -----------------------------------------------------------------------------------------------


def test_iri010_the_iri_ends_in_a_separator() -> None:
    for iri in ("https://a.test/ns#", "https://a.test/ns/", "https://a.test/a/#", "https://a.test/ns#A/"):
        assert _foci("IRI010", (iri,)) == [iri]


def test_iri010_gaps_the_local_name_is_the_text_after_the_last_slash_or_hash() -> None:
    # Gap: with no path the authority is the "local name" (RFC 3986 3.2 puts it in the authority); with a URN the
    # separator is ":" and is not read.
    assert _foci("IRI010", ("https://a.test", "urn:x:", "urn:x")) == []
    assert _foci("IRI010", ("https://a.test/ns#/",)) == ["https://a.test/ns#/"]


def test_iri010_the_boundary_one_character_name_is_a_name() -> None:
    assert _foci("IRI010", ("https://a.test/ns#A", "https://a.test/a")) == []


# --- IRI011 (RFC 3986 2.1) --------------------------------------------------------------------------------


def test_iri011_a_percent_escape_in_the_local_name() -> None:
    for iri in (
        "https://a.test/ns#a%20b",
        "https://a.test/ns#b%C3%A9",
        "https://a.test/ns/x%41",
        "https://a.test/ns/a%2fb",
    ):
        assert _foci("IRI011", (iri,)) == [iri]


def test_iri011_exclusions() -> None:
    # An escape in the namespace is not in the local name; a "%" that is not followed by two hex digits is no escape.
    assert _foci("IRI011", ("https://a.test/a%20b/c", "https://a.test/a%20b/ns#term")) == []
    assert _foci("IRI011", ("https://a.test/ns#100%",)) == []
    # Gap: an unreserved character written as an escape (RFC 3986 2.3: "%41" is "A") is reported like any other.
    assert _foci("IRI011", ("https://a.test/ns/%41",)) == ["https://a.test/ns/%41"]


# --- IRI012 (RFC 3986 3.2.2 host; loopback is RFC 6761 "localhost" and the 127/8 and ::1 addresses) -------------


def test_iri012_three_loopback_spellings() -> None:
    for iri in (
        "http://localhost:8080/ns#A",
        "http://LOCALHOST/x",
        "http://127.0.0.1/x",
        "http://[::1]/x",
        "http://[::1]:80/x",
    ):
        assert _foci("IRI012", (iri,)) == [iri]


def test_iri012_gaps_other_loopback_forms_are_not_read() -> None:
    # Gap: RFC 6761 6.3 reserves "localhost." and every name under ".localhost"; 127.0.0.0/8 is all loopback;
    # "[0:0:0:0:0:0:0:1]" is "::1".  The rule compares the host with three strings.
    others = (
        "http://localhost./x",
        "http://foo.localhost/x",
        "http://127.0.0.2/x",
        "http://127.1/x",
        "http://[0:0:0:0:0:0:0:1]/x",
    )
    assert _foci("IRI012", others) == []
    assert _foci("IRI012", ("http://0.0.0.0/x",)) == []


def test_iri012_exclusions() -> None:
    assert _foci("IRI012", ("https://a.test/localhost/A", "urn:localhost")) == []
    # The host is read after the userinfo: "localhost@evil" names evil.test.
    assert _foci("IRI012", ("http://localhost@a.test/x",)) == []


# --- IRI013 -------------------------------------------------------------------------------------------------


def test_iri013_a_version_segment_of_the_path() -> None:
    for iri in (
        "https://a.test/v1/A",
        "https://a.test/V2/A",
        "https://a.test/v1.2.3/A",
        "https://a.test/1.2.0/A",
        "https://a.test/2024-05/A",
        "https://a.test/2024-05-01/A",
        "https://a.test/ns/v1",
    ):
        assert len(_foci("IRI013", (iri,))) == 1, iri


def test_iri013_one_finding_per_namespace_focused_on_it() -> None:
    found = _findings("IRI013", _built(("https://a.test/v1/A", "https://a.test/v1/B")))
    assert [focus for focus, _ in found] == ["https://a.test/v1/"]
    assert found[0][1].startswith("2 term IRIs in this namespace embed a version or date segment")
    assert _foci("IRI013", ("https://a.test/v1/ns#A",)) == ["https://a.test/v1/ns#"]


def test_iri013_boundaries_and_gaps() -> None:
    # A year alone, a loosely written date and the word "vocab" are not versions.
    assert _foci("IRI013", ("https://a.test/2024/A", "https://a.test/2024-5-1/A", "https://a.test/vocab/A")) == []
    # Gap: a version in the fragment is not read (only the path is split).
    assert _foci("IRI013", ("https://a.test/ns#v1", "https://a.test/x/A#v1.0")) == []
    # Gap: a local name that looks like a version ("ns/1.0") is a term name, and is reported as an embedded version.
    assert _foci("IRI013", ("https://a.test/ns/1.0",)) == ["https://a.test/ns/"]


# --- IRI014 ---------------------------------------------------------------------------------------------------


def test_iri014_leading_trailing_and_repeated_separators() -> None:
    for iri in (
        "https://a.test/ns#_A",
        "https://a.test/ns#-A",
        "https://a.test/ns#A_",
        "https://a.test/ns#A-",
        "https://a.test/ns#a__b",
        "https://a.test/ns#A--b",
    ):
        assert _foci("IRI014", (iri,)) == [iri]


def test_iri014_exclusions_and_gaps() -> None:
    assert _foci("IRI014", ("https://a.test/ns#a_b-c", "https://a.test/ns#")) == []
    # "repeated" means one character twice: "_-" is not, and "." and ":" are not separators.
    assert _foci("IRI014", ("https://a.test/ns#a_-b", "https://a.test/ns#a..b", "https://a.test/ns#.a")) == []


# --- IRI015 (convention: no standard speaks of local-name schemes) ----------------------------------------


def test_iri015_opaque_and_readable_names_in_one_namespace() -> None:
    assert _ttl("IRI015", "ex:Person a owl:Class . ex:T0001234 a owl:Class .") == [""]
    assert _ttl("IRI015", "ex:hasPart a owl:ObjectProperty . ex:BFO_0000001 a owl:Class .") == [""]


def test_iri015_the_classes_of_names() -> None:
    # Opaque: up to eight letters, an optional separator, three or more digits.  Readable: letters, "_" and "-", three
    # lower-case letters in a row.  The rest is not classified: "ab12" (two digits), "ABC" (no lower case),
    # "abcdefghi123" (a nine-letter prefix) and a name with a digit after a letter run.
    unclassified = ("ab12", "ABC", "abcdefghi123", "a1b2c3")
    for name in unclassified:
        assert _ttl("IRI015", f"ex:{name} a owl:Class . ex:T0001234 a owl:Class .") == [], name
    for name in ("T0001234", "BFO_0000001", "abcdefgh-0001", "a123"):
        assert _ttl("IRI015", f"ex:{name} a owl:Class . ex:hasPart a owl:Class .") == [""], name


def test_iri015_the_ten_percent_boundary() -> None:
    def mix(readable: int, opaque: int) -> str:
        lines = [f"ex:name{chr(97 + i // 26)}{chr(97 + i % 26)}x a owl:Class ." for i in range(readable)]
        return " ".join(lines + [f"ex:T{1000 + i} a owl:Class ." for i in range(opaque)])

    assert _ttl("IRI015", mix(9, 1)) == [""]  # exactly 10%
    assert _ttl("IRI015", mix(10, 1)) == []  # 1 in 11
    assert _ttl("IRI015", mix(1, 9)) == [""]


def test_iri015_exclusions() -> None:
    assert _ttl("IRI015", "ex:Person a owl:Class . ex:hasPart a owl:ObjectProperty .") == []
    assert _foci("IRI015", ("https://a.test/Person", "https://b.test/T0001234")) == []
    # An unowned term is not grouped.
    assert _foci("IRI015", ("https://a.test/Person", "https://a.test/T0001234"), base="https://zz.test/") == []


def test_iri015_one_finding_per_namespace_with_three_examples() -> None:
    iris = tuple(f"https://a.test/T000{i}" for i in range(5)) + ("https://a.test/Person",)
    ((focus, message),) = _findings("IRI015", _built(iris))
    assert focus == "https://a.test/"
    assert message == (
        "Namespace mixes 5 opaque local names (e.g. T0000, T0001, T0002) and 1 readable ones (e.g. Person)."
    )


# --- IRI016 (RFC 3986 3.4 and 3.5) -----------------------------------------------------------------------


def test_iri016_a_query_or_fragment_in_an_ontology_iri() -> None:
    assert _foci("IRI016", onts=("https://a.test/o#v1",)) == ["https://a.test/o#v1"]
    assert _foci("IRI016", onts=("https://a.test/o?x=1",)) == ["https://a.test/o?x=1"]


def test_iri016_boundary_an_empty_fragment_is_accepted_by_design() -> None:
    # TODO.md: a '#'-terminated ontology IRI is common; the rule's cases accept the empty fragment.
    assert _foci("IRI016", onts=("https://a.test/o#",)) == []
    assert _foci("IRI016", ("https://a.test/o#A",)) == []  # a term may have a fragment
    # Gap: the empty query is not accepted by design, only never seen: "o?" is a query by RFC 3986 3.4 and passes
    # here although IRI006 reports it on a term.
    assert _foci("IRI016", onts=("https://a.test/o?",)) == []


# --- IRI017 ---------------------------------------------------------------------------------------------------


def test_iri017_the_ontology_iri_is_also_a_term() -> None:
    assert _ttl("IRI017", "<https://example.test/onto> a owl:Ontology, owl:Class .") == ["https://example.test/onto"]
    assert _foci("IRI017", ("https://a.test/o",), ("https://a.test/o",)) == ["https://a.test/o"]
    assert _foci("IRI017", ("https://a.test/o",), ("https://a.test/o",), kind=OWL.NamedIndividual) == [
        "https://a.test/o"
    ]


def test_iri017_exclusions_and_boundaries() -> None:
    assert _foci("IRI017", ("https://a.test/o#A",), ("https://a.test/o",)) == []
    assert _foci("IRI017", onts=("https://a.test/o",)) == []
    # skos:ConceptScheme is one of the kinds: a scheme that is also the ontology header is reported.
    assert _ttl("IRI017", "<https://a.test/o> a owl:Ontology, skos:ConceptScheme .") == ["https://a.test/o"]


# --- IRI018 -------------------------------------------------------------------------------------------------


def test_iri018_the_untitled_placeholder_and_the_default_base() -> None:
    base = "http://www.semanticweb.org/x/ontologies/"
    for ontology in (base + "2018/8/untitled-ontology-1", base + "2018/8/untitled-ontology-1/", base + "foo"):
        assert _foci("IRI018", onts=(ontology,)) == [ontology]
    # https is read the same.
    assert _foci("IRI018", onts=("https://www.semanticweb.org/x/ontologies/foo",)) != []


def test_iri018_two_messages() -> None:
    base = "http://www.semanticweb.org/x/ontologies/"
    (a,) = _findings("IRI018", _built(onts=(base + "untitled-ontology-3",)))
    (b,) = _findings("IRI018", _built(onts=(base + "moral",)))
    assert a[1] == "Ontology IRI is Protege's untitled-ontology placeholder."
    assert b[1].startswith("Ontology IRI is under Protege's default")


def test_iri018_boundaries_and_gaps() -> None:
    base = "http://www.semanticweb.org/x/ontologies/"
    # "#" and ".owl" after the placeholder fall to the second message: the untitled pattern needs "-<n>" at the end.
    (found,) = _findings("IRI018", _built(onts=(base + "2018/untitled-ontology-1#",)))
    assert found[1].startswith("Ontology IRI is under Protege's default")
    assert _foci("IRI018", onts=(base + "untitled-ontology-1.owl",)) != []
    # Exclusions: the word alone, a path without a user segment, a permanent IRI.
    assert (
        _foci("IRI018", onts=("https://example.test/untitled-ontology", "http://www.semanticweb.org/ontologies/foo"))
        == []
    )
    assert _foci("IRI018", onts=("https://w3id.org/moral",)) == []
    # Gap: the host is compared case-sensitively (RFC 3986 3.2.2: case-insensitive); a userinfo hides it.
    assert (
        _foci(
            "IRI018",
            onts=("http://WWW.semanticweb.org/x/ontologies/foo", "http://u:p@www.semanticweb.org/x/ontologies/foo"),
        )
        == []
    )
    # Gap: the untitled pattern is anywhere in the IRI, so a userinfo in the path is not told apart.
    assert _foci("IRI018", onts=("http://www.semanticweb.org/u:p@x/ontologies/untitled-ontology-1",)) != []
    # A term under the default base is not reported: only ontology IRIs are.
    assert _foci("IRI018", (base + "foo#A",)) == []


# --- IRI019 -----------------------------------------------------------------------------------------------------


def test_iri019_a_prefix_no_iri_uses() -> None:
    found = _findings("IRI019", graph("@prefix z: <https://z.test/> . ex:A a owl:Class ."))
    assert found == [("https://z.test/", "Prefix z: is declared for <https://z.test/>, but no IRI uses it.")]


def test_iri019_what_counts_as_a_use() -> None:
    # An IRI under the namespace, the namespace itself, a datatype, and the ontology IRI the namespace names.
    uses = (
        "ex:A a owl:Class ; ex:p <https://z.test/sub/X> .",
        "ex:A a owl:Class ; ex:p <https://z.test/> .",
        "ex:A a owl:Class ; ex:p 'x'^^<https://z.test/dt> .",
        "<https://z.test> a owl:Ontology . ex:A a owl:Class .",
    )
    for turtle in uses:
        assert _ttl("IRI019", f"@prefix z: <https://z.test/> . {turtle}") == [], turtle
    # Exclusion: the prefixes editors write in every file are never reported.
    assert _ttl("IRI019", "ex:A a owl:Class .") == []


def test_iri019_a_graph_binds_one_prefix_per_namespace() -> None:
    # Without the file's own declarations (Policy.source.declared_prefixes) the prefixes are the graph's bindings,
    # and rdflib keeps one prefix per namespace: the later declaration wins.
    found = _findings(
        "IRI019", graph("@prefix y: <https://z.test/> . @prefix z: <https://z.test/> . ex:A a owl:Class .")
    )
    assert [message.split(" ")[1] for _, message in found] == ["z:"]


# --- the userinfo (RFC 3986 3.2.1) and the redaction that SEC014 and SEC016 share -----------------------------


def test_userinfo_is_masked_in_every_focus_and_message_the_iri_rules_print() -> None:
    secret = ("https://alice:s3cret@a.test/", "s3cret")

    def printed(rule: str, g: Graph) -> str:
        return "\n".join(f"{focus} {message}" for focus, message in _findings(rule, g))

    cases = {
        "IRI006": _built(("https://alice:s3cret@a.test/x?q=1",)),
        "IRI009": _built(("https://alice:s3cret@a.test/a{b}",)),
        "IRI010": _built((secret[0],)),
        "IRI011": _built((secret[0] + "a%20b",)),
        "IRI012": _built(("http://alice:s3cret@localhost/x",)),
        "IRI014": _built((secret[0] + "_a",)),
        "IRI013": _built((secret[0] + "v1/A",)),
        "IRI001": _built(("http://alice:s3cret@/x",)),
        "IRI003": _built((secret[0] + "A", "https://b.test/A")),
        "IRI005": _built((secret[0] + "ns#A", secret[0] + "B")),
        "IRI008": _built(("http://alice:s3cret@a.test/A", "https://b.test/B")),
        "IRI004": _built(("https://alice:s3cret@b.test/A",), ("https://a.test/o",)),
        "IRI016": _built(onts=("https://alice:s3cret@a.test/o#v",)),
        "IRI017": _built(("https://alice:s3cret@a.test/o",), ("https://alice:s3cret@a.test/o",)),
        "IRI018": _built(onts=("http://alice:s3cret@www.semanticweb.org/x/untitled-ontology-1",)),
    }
    for rule, g in cases.items():
        text = printed(rule, g)
        assert "s3cret" not in text and "alice" not in text, (rule, text)


def test_userinfo_is_masked_in_iri015_and_iri019() -> None:
    iris = ("https://alice:s3cret@a.test/T0001", "https://alice:s3cret@a.test/Person")
    text = "\n".join(f"{f} {m}" for f, m in _findings("IRI015", _built(iris)))
    assert "s3cret" not in text and "alice" not in text
    text = "\n".join(
        f"{f} {m}" for f, m in _findings("IRI019", graph("@prefix z: <https://u:s3cret@z.test/> . ex:A a owl:Class ."))
    )
    assert "s3cret" not in text and "https://****@z.test/" in text


def test_iris_that_differ_only_in_their_userinfo_give_one_finding() -> None:
    # redaction.py, "Identity": one masked focus, one finding, whatever the credential.
    found = _findings("IRI010", _built(("https://alice:one@a.test/ns#", "https://bob:two@a.test/ns#")))
    assert [focus for focus, _ in found] == ["https://****@a.test/ns#"]


def test_userinfo_is_not_the_host_of_iri012() -> None:
    assert _foci("IRI012", ("http://localhost:pw@a.test/x",)) == []
    assert _foci("IRI012", ("http://u:p@localhost/x",)) == ["http://****@localhost/x"]
