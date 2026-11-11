"""The userinfo parser of :mod:`ontolint.redaction`: what it masks, what SEC014 reads from it, and its cost.

One parser decides where a userinfo is, for masking and for SEC014: an authority ends at ``/ ? #`` only, so
a userinfo holding characters an IRI may not hold (white space, ``{ } | ^ ` \\``, a line break that rdflib
reads from an escape) is masked whole, and SEC014 reports it.
"""

from __future__ import annotations

import ast
import io
import sys
import time
from pathlib import Path

import pytest

from ontolint.redaction import (
    REDACTED_USERINFO,
    RedactingStream,
    clip,
    has_userinfo,
    redact_rendered,
    redact_userinfo,
    userinfo_password,
)

MASKED = f"https://{REDACTED_USERINFO}@example.test/x"


@pytest.mark.parametrize(
    "secret",
    ["pw SPACE", "pw{BRACE}", "pw|PIPE", "pw^CARET", "pw`TICK", "pw\\SLASH", 'pw"QUOTE', "pw<LT>", "pw\nLINE", "p@ss"],
)
def test_a_userinfo_is_masked_whatever_its_characters(secret: str) -> None:
    iri = f"https://alice:{secret}@example.test/x"
    assert redact_userinfo(iri) == MASKED
    assert redact_userinfo(f"see {iri} and more") == f"see {MASKED} and more"
    assert userinfo_password(iri) == secret
    assert has_userinfo(iri)


@pytest.mark.parametrize(
    ("text", "masked"),
    [
        # WHATWG reads these as credentials of a special scheme; os.path.normpath makes the first one of "https://".
        ("https:/bob:pw@example.test/x", f"https:/{REDACTED_USERINFO}@example.test/x"),
        ("https:\\\\bob:pw@example.test/x", f"https:\\\\{REDACTED_USERINFO}@example.test/x"),
        ("HTTPS:bob:pw@example.test/x", f"HTTPS:{REDACTED_USERINFO}@example.test/x"),
        ("https:///bob:pw@example.test/x", f"https:///{REDACTED_USERINFO}@example.test/x"),
        ("ws:\n//bob:pw@example.test/x", f"ws:\n//{REDACTED_USERINFO}@example.test/x"),
        ("git+https:\t//bob:pw@example.test/x", f"git+https:\t//{REDACTED_USERINFO}@example.test/x"),
        # A "\\" after "//" or after the run's last "/" is userinfo data, as curl and urlsplit read it (curl sends
        # the user "\\bob"), though WHATWG skips it: the mask covers both readings.
        ("https://\\bob:pw@example.test/x", f"https://{REDACTED_USERINFO}@example.test/x"),
        ("https://\\/bob:pw@example.test/x", f"https://\\/{REDACTED_USERINFO}@example.test/x"),
        ("https://\t\\bob:pw@example.test/x", f"https://\t{REDACTED_USERINFO}@example.test/x"),
        ("https://bob\\x:pw@example.test/x", f"https://{REDACTED_USERINFO}@example.test/x"),
        # A credentialed IRI nested in another one, or in its query, is masked where it stands.
        ("urn:x:https://bob:pw@h/y", f"urn:x:https://{REDACTED_USERINFO}@h/y"),
        ("https://h/r?to=ftp://bob:pw@g/y", f"https://h/r?to=ftp://{REDACTED_USERINFO}@g/y"),
    ],
)
def test_the_lenient_forms_of_an_authority_are_masked(text: str, masked: str) -> None:
    assert redact_userinfo(text) == masked
    assert userinfo_password(text) == "pw"


@pytest.mark.parametrize(
    "text",
    [
        "mailto:bob:pw@example.test",
        "urn:x:a:b@c",
        "git+https:/bob:pw@h/x",  # no authority for a scheme WHATWG does not treat as special
        "xhttps:bob:pw@h/x",
        "https://h/a@b",
        "https://h?q=a@b",
        "https://h#a@b",
        "https://@h/x",
        "https://:@h/x",
        '"x"@en',
        "@prefix ex: <https://h/> .",
    ],
)
def test_text_without_a_userinfo_is_unchanged(text: str) -> None:
    assert redact_userinfo(text) == text
    assert userinfo_password(text) is None


def test_sec014_reads_the_password_of_the_userinfo_that_is_masked() -> None:
    assert userinfo_password("https://alice@example.test/x") is None
    assert userinfo_password("https://alice:@example.test/x") is None
    assert userinfo_password("https://alice%3Apw@example.test/x") is None
    # The last "@" of the authority ends the userinfo, for SEC014 as for the mask: the password is "y".
    assert userinfo_password("https://u@x:y@example.test/x") == "y"
    assert userinfo_password("https://h/x?to=https://u:p@g/") == "p"


def test_a_rendered_report_is_masked_without_crossing_a_token() -> None:
    # The re-mask of a whole report must not swallow the text between a bare IRI and a later "@" (a language tag).
    line = "[INFO] ONT003 https://example.test: Literal 'a'@en; see https://u:p@h/x"
    assert redact_rendered(line) == "[INFO] ONT003 https://example.test: Literal 'a'@en; see https://****@h/x"
    assert redact_userinfo("https://example.test has 'a'@en") == "https://****@en"  # a field is masked broadly
    assert redact_rendered('"focus": "https://u:p@h/x",') == '"focus": "https://****@h/x",'


def test_clip_masks_before_it_cuts() -> None:
    long = "Mirror https://alice:" + "S" * 80 + "@example.test/x"
    assert clip(long, 30) == "Mirror https://****@example.te"
    assert clip(long, 30, "...") == "Mirror https://****@example.te..."
    assert clip("short", 30, "...") == "short"


@pytest.mark.parametrize(
    "text",
    [
        "a" * 200_000 + "://" + "b" * 200_000 + " @",
        "a" * 400_000 + "@",
        "a:" * 200_000 + "@",
        "a://" * 100_000 + " @",
        "https:" * 100_000 + "@",
        "a:" + "\n" * 400_000 + "@",
        "a" * 400_000 + "&#64;",
    ],
    ids=["scheme-then-authority", "scheme-run", "colons", "starts", "special", "line-breaks", "escaped-at"],
)
def test_the_scan_is_linear(text: str) -> None:
    # CodeQL py/polynomial-redos: an unanchored scheme restarted at every letter of a run (7.8 s at 80 k).
    started = time.perf_counter()
    redact_userinfo(text)
    redact_rendered(text)
    has_userinfo(text)
    assert time.perf_counter() - started < 1


def test_the_stream_masks_a_userinfo_split_over_writes() -> None:
    target = io.StringIO()
    stream = RedactingStream(target)
    stream.write("note: https://alice:W1")
    stream.write("SPLIT@example.test/x\n")
    stream.writelines(["https://alice:W2LINES@example.test/x", "\n"])
    stream.buffer.write(b"https://alice:W3BUF@example.test/x\n")
    stream.write("tail https://alice:W4")
    stream.flush()  # a flush does not write half a line
    assert "W4" not in target.getvalue()
    stream.write("TAIL@example.test/x")
    stream.drain()
    assert target.getvalue() == "".join(
        f"{text}\n" for text in (f"note: {MASKED}", MASKED, MASKED, f"tail {MASKED}")
    ).removesuffix("\n")


def test_the_stream_still_answers_what_the_wrapped_stream_answers() -> None:
    stream = RedactingStream(sys.__stdout__ or io.StringIO())
    assert stream.encoding
    assert isinstance(stream.isatty(), bool)


# Slices of lists, hashes and identifiers, which hold no quoted value; any other cut of a value a message quotes
# goes through ``clip``, which masks before it cuts.
_LIST_OR_KEY_SLICES = {
    "_ranked(kinds)[:SHOWN_KINDS]",
    "ranked[:SHOWN_SUBJECTS]",
    "sorted(relative)[:RELATIVE_IMPORTS_SHOWN]",
    "sorted(map(str, iris))[:5]",
    "imports[:MAX_LISTED]",
    "rule_id[:3]",
    "sorted(opaque[namespace])[:EXAMPLE_LIMIT]",
    "sorted(readable[namespace])[:EXAMPLE_LIMIT]",
    "sorted(terms, key=str)[:5]",
    "sorted(map(str, terms))[:5]",
    "hexdigest()[:STABLE_ID_LENGTH]",
}


def test_rules_and_adapters_cut_quoted_values_only_through_clip() -> None:
    # A fixed-length cut of a value can fall inside a userinfo, before the "@" every mask needs.
    package = Path(__file__).resolve().parent.parent / "src" / "ontolint"
    cuts = []
    for path in sorted([*(package / "rules").glob("*.py"), *(package / "adapters").glob("*.py")]):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice)):
                continue
            bound = node.slice.upper
            fixed = isinstance(bound, ast.Constant) or (isinstance(bound, ast.Name) and bound.id.isupper())
            text = ast.unparse(node)
            if node.slice.lower is None and fixed and not any(text.endswith(known) for known in _LIST_OR_KEY_SLICES):
                cuts.append(f"{path.name}:{node.lineno}: {text}")
    assert cuts == []
