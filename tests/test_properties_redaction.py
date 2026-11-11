"""Properties of ``redact_password``, which SEC014 uses for its focus (RFC 3986 section 3.2.1)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis_strategies import budget
from rdflib import Graph, URIRef
from rdflib.namespace import RDF

from ontolint import Linter
from ontolint.rules.support import REDACTED_PASSWORD, redact_password

pytestmark = pytest.mark.slow

LOWER = "abcdefghijklmnopqrstuvwxyz"
schemes = st.builds(lambda a, b: a + b, st.sampled_from(LOWER), st.text(LOWER + "0123456789+.-", max_size=6))
users = st.text(LOWER + "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._~-", max_size=8)
# Upper case and digits only: never a substring of the lower-case host and path, so a leak is visible.
passwords = st.text("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", min_size=1, max_size=12)
rests = st.text(LOWER + "./", max_size=16)


def _sec014_foci(iri: str) -> list[str]:
    data = Graph()
    data.add((URIRef(iri), RDF.type, URIRef("https://example.test/onto#T")))
    return [f.focus for f in Linter(data).execute(["SEC014"]).findings]


@budget()
@given(schemes, users, passwords, rests)
def test_the_password_is_masked_and_nothing_else_changes(scheme: str, user: str, password: str, rest: str) -> None:
    iri = f"{scheme}://{user}:{password}@h{rest}"
    masked = redact_password(iri)
    assert f":{password}@" not in masked
    assert masked == f"{scheme}://{user}:{REDACTED_PASSWORD}@h{rest}"
    assert redact_password(masked) == masked
    assert masked.replace(f":{REDACTED_PASSWORD}@", f":{password}@", 1) == iri
    assert _sec014_foci(iri) == [masked]
    assert _sec014_foci(masked) == [masked]


@budget()
@given(schemes, users, rests)
def test_an_iri_without_a_password_is_unchanged(scheme: str, user: str, rest: str) -> None:
    for iri in (f"{scheme}://h{rest}", f"{scheme}://{user}@h{rest}", f"{scheme}://{user}:@h{rest}"):
        assert redact_password(iri) == iri
        assert _sec014_foci(iri) == []
