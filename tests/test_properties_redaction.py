"""Properties of the userinfo parser: ``redact_userinfo`` masks what SEC014 reads (``userinfo_password``)."""

from __future__ import annotations

import io
from urllib.parse import urlsplit

import pytest
from hypothesis import example, given
from hypothesis import strategies as st
from hypothesis_strategies import budget
from rdflib import Graph, URIRef
from rdflib.namespace import RDF

from ontolint import Linter
from ontolint.redaction import (  # noqa: PLC2701 -- _ESCAPE is how has_userinfo decodes, which a property names.
    _ESCAPE,
    REDACTED_USERINFO,
    RedactingStream,
    has_userinfo,
    redact_rendered,
    redact_userinfo,
    userinfo_password,
)

pytestmark = pytest.mark.slow

LOWER = "abcdefghijklmnopqrstuvwxyz"
SPECIAL_SCHEMES = frozenset({"http", "https", "ws", "wss", "ftp"})
schemes = st.builds(lambda a, b: a + b, st.sampled_from(LOWER), st.text(LOWER + "0123456789+.-", max_size=6))
users = st.text(LOWER + "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._~-%", max_size=8)
# Every userinfo character, ``@`` and ``:`` included: masking reaches the last ``@`` before the path.
passwords = st.text("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@:!$&'()*+,;=", min_size=1, max_size=12).filter(
    lambda p: any(c.isalnum() for c in p)
)
rests = st.text(LOWER + "./?#=@:", max_size=16).map(lambda r: "/" + r if r else r)
# Digits and signs too: a run of scheme characters may start with them, before its scheme (#55).
texts = st.text(LOWER + "0123456789+-" + " ./:@#?<>\"'\\\n{}|", max_size=40)
# Any userinfo an authority can hold: every character but "/ ? #", white space and line breaks included.
any_userinfo = st.text(
    st.characters(blacklist_characters="/?#", blacklist_categories=("Cs",)), min_size=1, max_size=100
)


def _sec014_foci(iri: str) -> list[str]:
    data = Graph()
    data.add((URIRef(iri), RDF.type, URIRef("https://example.test/onto#T")))
    return [f.focus for f in Linter(data).execute(["SEC014"]).findings]


@budget()
@given(schemes, users, passwords, rests)
def test_the_userinfo_is_masked_and_nothing_else_changes(scheme: str, user: str, password: str, rest: str) -> None:
    iri = f"{scheme}://{user}:{password}@h{rest}"
    masked = redact_userinfo(iri)
    assert masked == f"{scheme}://{REDACTED_USERINFO}@h{rest}"
    assert redact_userinfo(masked) == masked
    parts, original = urlsplit(masked), urlsplit(f"{scheme}://h{rest}")
    assert (parts.scheme, parts.hostname, parts.path, parts.query, parts.fragment) == (
        original.scheme,
        original.hostname,
        original.path,
        original.query,
        original.fragment,
    )
    assert parts.username == REDACTED_USERINFO
    # SEC014 reports the IRI exactly when its own test finds a password, and its focus is the same mask.
    assert _sec014_foci(iri) == ([masked] if userinfo_password(iri) else [])


@budget()
@given(schemes, users, rests)
@example("ws", "0", "")
def test_an_iri_without_a_userinfo_is_unchanged(scheme: str, user: str, rest: str) -> None:
    for iri in (f"{scheme}://h{rest}", f"{scheme}://@h{rest}", f"{scheme}://:@h{rest}"):
        assert redact_userinfo(iri) == iri
    # Without "//" only a scheme WHATWG calls special has an authority: it reads ws:0@h as the user "0".
    iri = f"{scheme}:{user}@h"
    special = scheme in SPECIAL_SCHEMES and user
    assert redact_userinfo(iri) == (f"{scheme}:{REDACTED_USERINFO}@h" if special else iri)


@budget()
@given(texts)
def test_masking_any_text_is_idempotent(text: str) -> None:
    once = redact_userinfo(text)
    assert redact_userinfo(once) == once
    assert ("@" in text) or once == text


@budget()
@given(any_userinfo, rests)
# A "\\" after "//" is userinfo data: curl sends "\\" as the user of https://\\@h (CI run 43167659261).
@example("\\", "")
@example("\\a:pw", "")
@example("a\\b:pw", "")
@example("a:p\\w", "")
@example("\\\\", "")
@example("\\:", "")
@example("\t\\", "")
@example("\t\n:", "")
@example("\r\\:x", "")
@example("a\tb:p\nw", "")
@example("\n", "/x")
def test_any_userinfo_is_masked_whole_and_sec014_reads_its_password(userinfo: str, rest: str) -> None:
    iri = f"https://{userinfo}@h{rest}"
    # A tab or line break right after the slashes is no data (WHATWG removes it): it stays, unmasked.
    data = userinfo.lstrip("\t\n\r")
    lead = userinfo[: len(userinfo) - len(data)]
    password = data.partition(":")[2]
    if not data.strip(":"):  # no data: nothing to mask
        assert redact_userinfo(iri) == iri
        return
    masked = f"https://{lead}{REDACTED_USERINFO}@h{rest}"
    assert redact_userinfo(iri) == masked
    assert userinfo_password(iri) == (password or None)
    assert _sec014_foci(iri) == ([masked] if password else [])


@budget()
@given(texts)
def test_a_rendered_report_is_masked_less_than_a_field(text: str) -> None:
    # The re-mask of a rendered report never reaches further than the mask of a field: it only ends sooner.
    rendered = redact_rendered(text)
    assert redact_rendered(rendered) == rendered
    assert redact_userinfo(rendered) == redact_userinfo(text)


@budget()
@given(texts, st.sampled_from(["", " ", "\n", "\t", " and "]), schemes, users, rests)
@example("https://public.test", " and ", "https", "alice", "/x")
@example("https://u:p@h", " ", "https", "v", "")
# Digits and signs right before the scheme start its run: the scheme is still read (#55).
@example("1", "", "https", "alice", "/x")
@example(".", "", "ws", "alice", "/x")
@example("v1.", "", "https", "alice", "/x")
@example("-", "", "git+https", "alice", "/x")
# An escape the text leaves open takes the scheme's first letters: has_userinfo decodes U+ABCD, then "://".
@example("\\u", "", "abcd", "alice", "/x")
def test_a_credential_after_any_text_is_masked(text: str, separator: str, scheme: str, user: str, rest: str) -> None:
    # Whatever authority the text before it opens, the IRI's own authority is read too (PR #50 review).
    whole = f"{text}{separator}{scheme}://{user}:QXSECRET@h{rest}"
    assert "QXSECRET" not in redact_userinfo(whole)
    assert "QXSECRET" not in redact_rendered(whole)
    assert userinfo_password(whole) is not None
    # has_userinfo reads the text its escapes spell, where an escape across the join leaves no scheme.
    start = len(text) + len(separator)
    if not any(escape.start() < start < escape.end() for escape in _ESCAPE.finditer(whole)):
        assert has_userinfo(whole)


@budget()
@given(st.text("0123456789+.-", min_size=1, max_size=4), texts)
@example("1", "https://u:p@h/x")
@example("-", "git+https://u:p@h/x")
@example(".", "ws:u:p@h")
def test_digits_and_signs_before_a_text_change_nothing_in_its_mask(lead: str, text: str) -> None:
    # They start the text's first run of scheme characters, or are a run of their own: no part of a scheme.
    assert redact_userinfo(lead + text) == lead + redact_userinfo(text)
    assert redact_rendered(lead + text) == lead + redact_rendered(text)
    assert userinfo_password(lead + text) == userinfo_password(text)
    assert has_userinfo(lead + text) == has_userinfo(text)


fragments = st.lists(
    st.sampled_from(
        ["https:", "git+https:", "ftp:", "//", "/", "\\", "u:p", "@", "h", " ", "\n", "\t", "?", "#", "1", "-"]
    ),
    max_size=16,
).map("".join)


@budget()
@given(fragments, st.lists(st.integers(min_value=0, max_value=40), max_size=6))
@example("https://alice:Line\nTail@h/x\n", [19])  # a write ends at the userinfo's line break
@example("1git+https:\n//u:p@h\n", [12])  # a write ends after a scheme whose run starts with a digit (#55)
def test_the_stream_writes_the_mask_of_all_its_text_however_it_is_split(text: str, cuts: list[int]) -> None:
    target = io.StringIO()
    stream = RedactingStream(target)
    bounds = [0, *sorted(min(cut, len(text)) for cut in cuts), len(text)]
    for begin, end in zip(bounds, bounds[1:], strict=False):
        stream.write(text[begin:end])
        stream.write("")
    stream.drain()
    assert target.getvalue() == redact_userinfo(text)
