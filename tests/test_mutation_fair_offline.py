"""Targeted tests pinning exact messages, boundaries and both operands of every FAIR offline condition."""

from __future__ import annotations

import pytest
from rdflib import Graph
from rule_harness import graph

from ontolint import Linter
from ontolint.models import ExecutionStatus, Finding
from ontolint.rules.fair_offline import orcid_checksum, orcid_problem, ror_checksum, ror_problem

ONT = "https://w3id.org/example/onto"
ORCID = "https://orcid.org/0000-0002-1825-0097"
PAIR = 2
HEAD = "@prefix pav: <http://purl.org/pav/> .\n"


def _run(rule: str, data: Graph) -> list[Finding]:
    result = Linter(data, None).execute([rule])
    assert {x.status for x in result.executions} == {ExecutionStatus.EXECUTED}, result.executions
    return list(result.findings)


def _messages(rule: str, turtle: str) -> list[str]:
    return [f.message for f in _run(rule, graph(HEAD + turtle))]


def _ont(body: str, iri: str = ONT) -> str:
    return f"<{iri}> a owl:Ontology ; {body} ."


# --- FAIR004 ---------------------------------------------------------------------------------


def test_fair004_message_focus_severity_and_confidence() -> None:
    found = _run("FAIR004", graph(_ont("rdfs:label 'x'", "https://raw.githubusercontent.com/o/r/main/o.owl")))
    assert [(f.focus, f.message, f.severity, f.confidence) for f in found] == [
        (
            "https://raw.githubusercontent.com/o/r/main/o.owl",
            "Ontology IRI https://raw.githubusercontent.com/o/r/main/o.owl is on the mutable host "
            "raw.githubusercontent.com, not a persistent identifier.",
            "warning",
            "certain",
        )
    ]


def test_fair004_version_iri_is_checked_and_reported_on_the_ontology() -> None:
    found = _run("FAIR004", graph(_ont("owl:versionIRI <https://github.com/o/r/releases/o.owl>")))
    assert [(f.focus, f.message) for f in found] == [
        (
            ONT,
            "Version IRI https://github.com/o/r/releases/o.owl is on the mutable host github.com, "
            "not a persistent identifier.",
        )
    ]


@pytest.mark.parametrize(
    ("iri", "reason"),
    [
        ("file:///tmp/o.owl", "a local file"),
        ("FILE:///tmp/o.owl", "a local file"),
        ("http://10.0.0.1/o", "a bare IP address"),
        ("http://[2001:db8::1]/o", "a bare IP address"),
        ("http://localhost/o", "the mutable host localhost"),
        ("http://LOCALHOST:3000/o", "the mutable host localhost"),
        ("https://org.github.io/o", "the mutable host org.github.io"),
        ("https://org.gitlab.io/o", "the mutable host org.gitlab.io"),
        ("https://bitbucket.org/o", "the mutable host bitbucket.org"),
        ("https://drive.google.com/o", "the mutable host drive.google.com"),
        ("https://www.dropbox.com/o", "the mutable host www.dropbox.com"),
        ("https://gist.githubusercontent.com/o", "the mutable host gist.githubusercontent.com"),
    ],
)
def test_fair004_each_mutable_reason(iri: str, reason: str) -> None:
    assert _messages("FAIR004", _ont("rdfs:label 'x'", iri)) == [
        f"Ontology IRI {iri} is on {reason}, not a persistent identifier."
    ]


@pytest.mark.parametrize(
    "iri",
    [
        "https://notgithub.com/o",
        "https://github.com.example.org/o",
        "https://example.org/github.com",
        "http://1.example.org/o",
        "urn:x:y",
        "https://github.io.example/o",
    ],
)
def test_fair004_only_exact_hosts_and_subdomains_match(iri: str) -> None:
    assert _messages("FAIR004", _ont("rdfs:label 'x'", iri)) == []


def test_fair004_reports_ontology_and_version_independently() -> None:
    found = _messages("FAIR004", _ont("owl:versionIRI <http://localhost/v1>", "http://localhost/o"))
    assert len(found) == PAIR and found[0].startswith("Ontology IRI") and found[1].startswith("Version IRI")


# --- FAIR006 ---------------------------------------------------------------------------------


def test_fair006_literal_message_severity_and_quote_truncation() -> None:
    found = _run("FAIR006", graph(_ont("dcterms:license 'CC BY'")))
    assert [(f.focus, f.message, f.severity, f.confidence) for f in found] == [
        (ONT, "Licence 'CC BY' is a text literal, not a licence IRI.", "info", "certain")
    ]
    long = "x" * 80
    assert _messages("FAIR006", _ont(f"dcterms:license '{long}'")) == [
        f"Licence {long!r} is a text literal, not a licence IRI."
    ]
    assert _messages("FAIR006", _ont(f"dcterms:license '{long}y'")) == [
        f"Licence '{long}...' is a text literal, not a licence IRI."
    ]  # fmt: skip


def test_fair006_unknown_iri_message_and_confidence() -> None:
    found = _run("FAIR006", graph(_ont("dcterms:license <https://example.org/l>")))
    assert [(f.message, f.confidence) for f in found] == [
        ("Licence IRI https://example.org/l is outside the well-known licence families.", "heuristic")
    ]


@pytest.mark.parametrize(
    "iri",
    [
        "https://spdx.org/licenses/MIT",
        "http://spdx.org/licenses/MIT",
        "https://creativecommons.org/licenses/by/4.0/",
        "https://CreativeCommons.org/Licenses/by/4.0/",
        "https://www.creativecommons.org/licenses/by/4.0/",
        "https://creativecommons.org/publicdomain/zero/1.0/",
        "https://opensource.org/licenses/MIT",
        "https://opensource.org/license/mit",
        "https://www.gnu.org/licenses/gpl-3.0.html",
        "https://www.gnu.org/copyleft/gpl.html",
        "https://www.apache.org/licenses/LICENSE-2.0",
        "https://www.mozilla.org/MPL/2.0/",
        "https://www.w3.org/Consortium/Legal/2015/doc-license",
        "http://opendatacommons.org/licenses/by/1.0/",
        "http://www.opendefinition.org/licenses/cc-by",
        "http://purl.org/NET/rdflicense/MIT",
        "http://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        "https://www.eclipse.org/legal/epl-2.0/",
    ],
)
def test_fair006_each_known_family_is_accepted(iri: str) -> None:
    assert _messages("FAIR006", _ont(f"dcterms:license <{iri}>")) == []


@pytest.mark.parametrize(
    "iri",
    [
        "ftp://spdx.org/licenses/MIT",
        "https://spdx.org/license/MIT",
        "https://spdx.org/",
        "https://creativecommons.org/about",
        "https://x.example/spdx.org/licenses/MIT",
        "urn:license:mit",
        "https://creativecommons.org.example/licenses/by/4.0/",
    ],
)
def test_fair006_near_misses_are_flagged(iri: str) -> None:
    assert len(_messages("FAIR006", _ont(f"dcterms:license <{iri}>"))) == 1


@pytest.mark.parametrize(
    "predicate",
    [
        "dcterms:license",
        "<http://creativecommons.org/ns#license>",
        "<http://schema.org/license>",
        "<https://schema.org/license>",
        "<http://www.w3.org/1999/xhtml/vocab#license>",
    ],
)
def test_fair006_each_licence_predicate(predicate: str) -> None:
    assert len(_messages("FAIR006", _ont(f"{predicate} 'MIT'"))) == 1


def test_fair006_blank_literal_blank_node_and_other_predicates_are_silent() -> None:
    assert _messages("FAIR006", _ont("dcterms:license ' ', []; dcterms:rights 'free text'")) == []


def test_fair006_checks_every_value_and_only_ontologies() -> None:
    both = _messages("FAIR006", _ont("dcterms:license 'a', <https://example.org/b>"))
    assert len(both) == PAIR
    assert _messages("FAIR006", "ex:A a owl:Class ; dcterms:license 'MIT' .") == []


# --- FAIR007 ---------------------------------------------------------------------------------


def _version(version: str, iri: str = ONT) -> list[str]:
    return _messages("FAIR007", _ont(f"owl:versionIRI <{version}>", iri))


def test_fair007_equal_iri_message_focus_and_severity() -> None:
    found = _run("FAIR007", graph(_ont(f"owl:versionIRI <{ONT}>")))
    assert [(f.focus, f.message, f.severity, f.confidence) for f in found] == [
        (
            ONT,
            f"Version IRI {ONT} is the same as the ontology IRI, so it does not identify one release.",
            "warning",
            "certain",
        )
    ]


@pytest.mark.parametrize("version", [ONT + "/", ONT + "#", ONT + "//", ONT + "#/"])
def test_fair007_trailing_separators_are_ignored_when_comparing(version: str) -> None:
    assert "same as the ontology IRI" in _version(version)[0]


def test_fair007_marker_message_picks_the_first_marker_alphabetically() -> None:
    assert _version(ONT + "/main/latest") == [
        f"Version IRI {ONT}/main/latest contains the floating marker 'latest', which is not tied to one release."
    ]


@pytest.mark.parametrize(
    "marker",
    ["latest", "master", "main", "current", "head", "dev", "develop", "trunk", "snapshot", "nightly", "unstable"],
)
def test_fair007_every_marker_is_recognised_in_path_query_and_fragment(marker: str) -> None:
    for tail in (f"/{marker}", f"?v={marker}", f"#{marker}", f"/{marker.upper()}/o.owl", f"/x-{marker}-2024"):
        found = _version(ONT + tail)
        assert found and "floating marker" in found[0], tail


def test_fair007_marker_inside_a_longer_token_is_not_a_marker() -> None:
    assert _version(ONT + "/mainline-2024") == []
    assert _version(ONT + "/devices-1") == []


def test_fair007_marker_present_in_the_ontology_iri_is_not_new() -> None:
    assert _version("https://w3id.org/main/onto/2024", "https://w3id.org/main/onto") == []


def test_fair007_digit_requirement_uses_only_new_tokens() -> None:
    # the ontology IRI itself carries a digit, the version adds nothing numeric
    assert "no version or date token" in _version("https://w3id.org/o2/onto/final", "https://w3id.org/o2/onto")[0]
    assert _version("https://w3id.org/o2/onto/final1", "https://w3id.org/o2/onto") == []


def test_fair007_no_token_message() -> None:
    assert _version(ONT + "/release") == [
        f"Version IRI {ONT}/release has no version or date token that distinguishes it from the ontology IRI."
    ]


def test_fair007_host_is_not_part_of_the_tokens() -> None:
    assert len(_version("https://v2.example.org/onto")) == 1  # digit only in the host
    assert _version("https://v2.example.org/onto/3") == []


def test_fair007_literal_and_missing_version_iri_are_silent() -> None:
    assert _messages("FAIR007", _ont("owl:versionIRI 'latest'")) == []
    assert _messages("FAIR007", _ont("rdfs:label 'x'")) == []


def test_fair007_each_version_iri_is_judged() -> None:
    found = _messages("FAIR007", _ont(f"owl:versionIRI <{ONT}/latest>, <{ONT}/1.0>"))
    assert len(found) == 1 and "latest" in found[0]


# --- FAIR011 ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("digits", "check"),
    [
        ("000000021825009", "7"),
        ("000000021694233", "X"),
        ("000000015109370", "0"),
        ("000000000000000", "1"),
        ("000000000000001", "X"),
        ("000000000000010", "8"),
        ("000000000000100", "4"),
    ],
)
def test_orcid_checksum_known_values(digits: str, check: str) -> None:
    assert orcid_checksum(digits) == check


def test_orcid_checksum_covers_all_remainders_including_x_and_zero() -> None:
    seen = {orcid_checksum(f"{n:015d}") for n in range(200)}
    assert seen == set("0123456789X")


def test_orcid_problem_messages() -> None:
    assert orcid_problem("0000-0002-1825-0097") is None
    assert orcid_problem("0000-0002-1694-233X") is None
    assert orcid_problem("0000-0002-1825-0098") == "fails the ISO 7064 mod 11-2 checksum"
    assert orcid_problem("0000-0002-1694-2330") == "fails the ISO 7064 mod 11-2 checksum"
    for bad in (
        "",
        "0000-0002-1825-009",
        "0000-0002-1825-00977",
        "0000000218250097",
        "0000-0002-1694-233x",
        "A000-0002-1825-0097",
    ):
        assert orcid_problem(bad) == "is not of the form dddd-dddd-dddd-dddX", bad


@pytest.mark.parametrize(
    "ror", ["02mhbdp94", "05dxps055", "01ggx4157", "03vek6s52", "042nb2s44", "00f54p054", "013meh722", "052gg0110"]
)
def test_ror_problem_accepts_real_identifiers(ror: str) -> None:
    assert ror_problem(ror) is None
    assert ror_checksum(ror[1:7]) == ror[7:]


def test_ror_problem_rejects_wrong_checksum_and_shape() -> None:
    assert ror_problem("02mhbdp95") == "fails the ROR checksum"
    assert ror_problem("02mhbdp00") == "fails the ROR checksum"
    for bad in (
        "",
        "12mhbdp94",
        "02mhbdp9",
        "02mhbdp944",
        "02mhbdi94",
        "02mhbdl94",
        "02mhbdo94",
        "02mhbdu94",
        "02MHBDP94",
        "02mhbdp9a",
    ):
        assert ror_problem(bad) == "is not of the form 0 + six base-32 characters + two digits", bad


def test_ror_checksum_is_zero_padded() -> None:
    assert ror_checksum("000000") == "98" and ror_checksum("00000g") == "50"  # 98 - (16 * 100 % 97) = 50
    assert ror_checksum("000001") == "95" and ror_checksum("00000z") == "05"


def test_fair011_orcid_message_focus_and_severity() -> None:
    found = _run("FAIR011", graph(f"ex:o a owl:Ontology ; dcterms:creator <{ORCID[:-1]}8> ."))
    assert [(f.focus, f.message, f.severity, f.confidence) for f in found] == [
        (
            "https://example.test/onto#o",
            f"ORCID iD in '{ORCID[:-1]}8' fails the ISO 7064 mod 11-2 checksum.",
            "warning",
            "certain",
        )
    ]


def test_fair011_ror_message() -> None:
    assert _messages("FAIR011", "ex:o dcterms:contributor <https://ror.org/02mhbdp95> .") == [
        "ROR identifier in 'https://ror.org/02mhbdp95' fails the ROR checksum."
    ]


@pytest.mark.parametrize(
    "predicate",
    [
        "dcterms:creator",
        "dcterms:contributor",
        "<http://purl.org/dc/elements/1.1/creator>",
        "<http://purl.org/dc/elements/1.1/contributor>",
        "<http://www.w3.org/ns/prov#wasAttributedTo>",
        "pav:createdBy",
        "pav:authoredBy",
        "pav:contributedBy",
        "pav:curatedBy",
        "<http://schema.org/author>",
        "<https://schema.org/creator>",
        "<https://schema.org/contributor>",
    ],
)
def test_fair011_each_person_predicate(predicate: str) -> None:
    assert len(_messages("FAIR011", f"ex:o {predicate} <{ORCID[:-1]}8> .")) == 1


def test_fair011_unrelated_predicate_is_silent() -> None:
    assert _messages("FAIR011", f"ex:o rdfs:seeAlso <{ORCID[:-1]}8> .") == []


@pytest.mark.parametrize("scheme", ["http", "https"])
@pytest.mark.parametrize("host", ["orcid.org", "www.orcid.org"])
def test_fair011_orcid_url_forms_are_all_checked(scheme: str, host: str) -> None:
    assert _messages("FAIR011", f"ex:o dcterms:creator <{scheme}://{host}/0000-0002-1825-0097> .") == []
    assert len(_messages("FAIR011", f"ex:o dcterms:creator <{scheme}://{host}/0000-0002-1825-0098> .")) == 1


@pytest.mark.parametrize("scheme", ["http", "https"])
@pytest.mark.parametrize("host", ["ror.org", "www.ror.org"])
def test_fair011_ror_url_forms_are_all_checked(scheme: str, host: str) -> None:
    assert _messages("FAIR011", f"ex:o dcterms:creator <{scheme}://{host}/02mhbdp94> .") == []
    assert len(_messages("FAIR011", f"ex:o dcterms:creator <{scheme}://{host}/02mhbdp95> .")) == 1


def test_fair011_other_hosts_are_not_checked() -> None:
    assert (
        _messages(
            "FAIR011", "ex:o dcterms:creator <https://sandbox.orcid.org/bad>, <https://example.org/orcid.org/bad> ."
        )
        == []
    )
    assert _messages("FAIR011", "ex:o dcterms:creator <ftp://orcid.org/bad>, <https://notror.org/x> .") == []


def test_fair011_literal_forms() -> None:
    assert _messages("FAIR011", f"ex:o dcterms:creator 'Jane, {ORCID}, Dr' .") == []
    assert _messages("FAIR011", f"ex:o dcterms:creator '({ORCID})' .") == []
    assert _messages("FAIR011", f"ex:o dcterms:creator '{ORCID}.' .") == []
    assert len(_messages("FAIR011", "ex:o dcterms:creator 'ORCID: 0000-0002-1825-0098' .")) == 1
    assert len(_messages("FAIR011", "ex:o dcterms:creator 'https://ORCID.org/0000-0002-1825-0098' .")) == 1
    assert len(_messages("FAIR011", "ex:o dcterms:creator 'ror.org/02mhbdp95' .")) == 1


def test_fair011_a_url_in_a_literal_is_not_reported_twice_as_a_bare_id() -> None:
    assert _messages("FAIR011", "ex:o dcterms:creator 'https://orcid.org/0000-0002-1825-0098' .") == [
        "ORCID iD in 'https://orcid.org/0000-0002-1825-0098' fails the ISO 7064 mod 11-2 checksum."
    ]


def test_fair011_bare_id_boundaries() -> None:
    assert _messages("FAIR011", "ex:o dcterms:creator '10000-0002-1825-0098' .") == []  # longer digit run
    assert _messages("FAIR011", "ex:o dcterms:creator '0000-0002-1825-00981' .") == []
    assert _messages("FAIR011", "ex:o dcterms:creator '0000-0002-1825-0098-1' .") == []
    assert len(_messages("FAIR011", "ex:o dcterms:creator '0000-0002-1825-0098' .")) == 1
    assert len(_messages("FAIR011", "ex:o dcterms:creator 'id=0000-0002-1694-233x' .")) == 1


def test_fair011_blank_nodes_and_numbers_are_ignored() -> None:
    assert _messages("FAIR011", "ex:o dcterms:creator [ a ex:P ], 42 .") == []


def test_fair011_identical_value_on_two_predicates_is_reported_per_predicate_once() -> None:
    found = _messages("FAIR011", f"ex:o dcterms:creator <{ORCID[:-1]}8> ; dcterms:contributor <{ORCID[:-1]}8> .")
    assert len(found) == 1  # same focus and message: de-duplicated


# --- FAIR017 ---------------------------------------------------------------------------------


def test_fair017_message_focus_and_severity() -> None:
    found = _run("FAIR017", graph(_ont("owl:deprecated true")))
    assert [(f.focus, f.message, f.severity, f.confidence) for f in found] == [
        (ONT, "Deprecated ontology has no successor (dcterms:isReplacedBy or obo:IAO_0100001).", "warning", "certain")
    ]


def test_fair017_deprecated_version_node_is_the_focus() -> None:
    turtle = _ont(f"owl:versionIRI <{ONT}/1.0>") + f"\n<{ONT}/1.0> owl:deprecated true ."
    assert [f.focus for f in _run("FAIR017", graph(turtle))] == [f"{ONT}/1.0"]


def test_fair017_both_ontology_and_version_are_reported_without_pointer() -> None:
    turtle = _ont(f"owl:deprecated true ; owl:versionIRI <{ONT}/1.0>") + f"\n<{ONT}/1.0> owl:deprecated true ."
    assert sorted(f.focus for f in _run("FAIR017", graph(turtle))) == [ONT, f"{ONT}/1.0"]


@pytest.mark.parametrize(
    "pointer",
    [
        "dcterms:isReplacedBy <https://w3id.org/new>",
        "<http://purl.obolibrary.org/obo/IAO_0100001> <https://w3id.org/new>",
        "pav:hasCurrentVersion <https://w3id.org/new>",
        "dcterms:isReplacedBy 'the new one'",
        "dcterms:isReplacedBy []",
    ],
)
def test_fair017_each_successor_pointer(pointer: str) -> None:
    assert _messages("FAIR017", _ont(f"owl:deprecated true ; {pointer}")) == []


def test_fair017_blank_literal_pointer_does_not_count() -> None:
    assert len(_messages("FAIR017", _ont("owl:deprecated true ; dcterms:isReplacedBy ''"))) == 1


@pytest.mark.parametrize("predicate", ["dcterms:replaces", "owl:priorVersion"])
def test_fair017_incoming_predecessor_link_is_a_pointer(predicate: str) -> None:
    turtle = _ont("owl:deprecated true") + f"\n<https://w3id.org/new> {predicate} <{ONT}> ."
    assert _messages("FAIR017", turtle) == []


def test_fair017_self_link_is_not_a_pointer_but_outgoing_predecessor_is_not_either() -> None:
    assert len(_messages("FAIR017", _ont(f"owl:deprecated true ; dcterms:replaces <{ONT}>"))) == 1
    assert len(_messages("FAIR017", _ont("owl:deprecated true ; owl:priorVersion <https://w3id.org/old>"))) == 1


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("true", 1),
        ("'true'", 1),
        ("'TRUE'", 1),
        ("' true '", 1),
        ("'1'^^xsd:boolean", 1),
        ("false", 0),
        ("'0'^^xsd:boolean", 0),
        ("'1'", 0),
        ("1", 0),
        ("'yes'", 0),
    ],
)
def test_fair017_truthiness(value: str, expected: int) -> None:
    assert len(_messages("FAIR017", _ont(f"owl:deprecated {value}"))) == expected


def test_fair017_non_ontology_deprecations_are_out_of_scope() -> None:
    assert _messages("FAIR017", "ex:A a owl:Class ; owl:deprecated true .") == []
