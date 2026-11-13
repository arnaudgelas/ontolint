"""Properties of userinfo masking: no finding of any rule holds a userinfo, and IRIs differing only in it agree.

The userinfo is drawn at random in every form (``user:password``, a token as the user with a placeholder, an
empty or no password, ``@`` inside the password, percent-encoded octets) and put in the ontology IRI, the
term namespace, an import, a ``rdfs:seeAlso`` object, a restriction's property (a blank node, whose identity
is a hash) and SKOS labels (which messages quote cut to 60 characters) of a small ontology every rule runs
over.  A secret may be long and hold characters no IRI may hold, which rdflib still accepts.
"""

from __future__ import annotations

import re
from dataclasses import fields

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis_strategies import budget
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from ontolint import Linter
from ontolint.models import Finding, plain_evidence
from ontolint.reporting import fingerprint, identity

pytestmark = pytest.mark.slow

LOWER = "abcdefghijklmnopqrstuvwxyz"
# Upper case and digits after a fixed marker: never a substring of the lower-case host, path or any message.
# Up to 100 characters, longer than any quote a message cuts (a GitHub fine-grained token has 93).
secrets = st.text("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", min_size=4, max_size=98).map(lambda s: "QX" + s)
users = st.one_of(secrets, st.sampled_from(["alice", "x-access-token"]))
# Characters an IRI may not hold but rdflib accepts in a term, and the userinfo delimiters RFC 3986 allows.
odd = st.sampled_from(
    [" ", "{", "}", "|", "^", "`", "\\", '"', "<", ">", "\n", "\t", "'", "!", "$", "&", "(", "*", ",", ";", "="]
)
userinfos = st.one_of(
    st.builds(lambda u, p: f"{u}:{p}", users, secrets),
    st.builds(lambda u, p, c, q: f"{u}:{p}{c}{q}", users, secrets, odd, secrets),
    st.builds(lambda t, p: f"{t}:{p}", secrets, st.sampled_from(["x-oauth-basic", "x-access-token", ""])),
    secrets,
    st.builds(lambda u, a, b: f"{u}:{a}@{b}", users, secrets, secrets),
    st.builds(lambda u, p: f"{u}%3A{p}", users, secrets),
    st.builds(lambda u, p: f"{u}:{p}%40", users, secrets),
)
# A nested IRI whose scheme follows a digit or a sign in its run of scheme characters (#55).
schemes = st.sampled_from(["https", "HTTP", "ftp", "x+y.z-1", "urn:x:1https", "urn:x:-ftp"])


def _ontology(scheme: str, userinfo: str) -> Graph:
    base = f"{scheme}://{userinfo}@example.test/onto"
    g = Graph()
    onto = URIRef(base)
    g.add((onto, RDF.type, OWL.Ontology))
    g.add((onto, OWL.imports, URIRef(f"https://{userinfo}@example.test/imported")))
    for name in ("Thing", "thing", "Other"):
        g.add((URIRef(f"{base}#{name}"), RDF.type, OWL.Class))
    g.add((URIRef(f"{base}#Other"), RDFS.subClassOf, URIRef(f"{base}#Thing")))
    g.add((URIRef(f"{base}#Other"), RDFS.seeAlso, URIRef(f"https://{userinfo}@example.test/x")))
    g.add((URIRef(f"{base}#Other"), RDFS.comment, Literal(f"See {base}/doc")))
    restriction = BNode()
    g.add((URIRef(f"{base}#Other"), RDFS.subClassOf, restriction))
    g.add((restriction, RDF.type, OWL.Restriction))
    g.add((restriction, OWL.onProperty, URIRef(f"{base}#prop")))
    concept = URIRef("https://example.test/onto#Concept")
    g.add((concept, RDF.type, SKOS.Concept))
    g.add((concept, SKOS.prefLabel, Literal(f"Mirror {base}/doc", lang="en")))
    g.add((concept, SKOS.altLabel, Literal(f"Mirror {base}/doc", lang="en")))
    g.add((URIRef("https://example.test/onto#Other2"), SKOS.prefLabel, URIRef(f"{base}#Thing")))
    return g


def _texts(finding: Finding) -> list[str]:
    texts = [str(getattr(finding, f.name)) for f in fields(Finding)]
    if finding.evidence is not None:
        texts.append(repr(plain_evidence(finding.evidence)))
    return texts


def _secret_parts(userinfo: str) -> list[str]:
    """The start of each drawn secret inside ``userinfo`` (the marker ``QX`` and four more): a quote cut short
    still holds it."""
    return [secret[:6] for secret in re.findall(r"QX[A-Z0-9]+", userinfo)]


@budget(0.1)
@given(schemes, userinfos)
def test_no_finding_of_any_rule_holds_a_userinfo(scheme: str, userinfo: str) -> None:
    findings = Linter(_ontology(scheme, userinfo)).execute().findings
    assert findings
    for finding in findings:
        for text in _texts(finding):
            for secret in _secret_parts(userinfo):
                assert secret not in text, (finding.rule, text)


@budget(0.1)
@given(schemes, userinfos, secrets)
def test_iris_differing_only_in_their_secrets_give_the_same_findings(scheme: str, userinfo: str, other: str) -> None:
    # The same userinfo form with other secrets: SEC014 fires for both or neither, and nothing else may differ.
    first = Linter(_ontology(scheme, userinfo)).execute().findings
    second = Linter(_ontology(scheme, re.sub(r"QX[A-Z0-9]+", other, userinfo))).execute().findings
    assert [(f.rule, f.focus, f.message) for f in first] == [(f.rule, f.focus, f.message) for f in second]
    assert [fingerprint(f) for f in first] == [fingerprint(f) for f in second]
    assert [identity(f) for f in first] == [identity(f) for f in second]
