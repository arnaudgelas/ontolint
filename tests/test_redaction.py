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
from timing_support import LINEAR_SCAN_SECONDS

from ontolint.redaction import (
    REDACTED_USERINFO,
    RedactingStream,
    clip,
    has_userinfo,
    redact_rendered,
    redact_userinfo,
    userinfo_password,
    userinfo_without_password,
    withheld_parser_message,
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
        # A run of scheme characters without a letter holds no scheme; one with a letter needs its authority.
        "123://bob:pw@h/x",
        "x1https:bob:pw@h/x",
        "1mailto:bob:pw@example.test",
        "1urn:x:a:b@c",
        "-https://h/a@b",
        "1https://@h/x",
        "1git+https:/bob:pw@h/x",
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


@pytest.mark.parametrize(
    "text",
    [
        "https://alice@example.test/x",
        "https://ghp_abcdefghijklmnopqrstuvwxyz0123456789@github.com/o/r",
        "ssh://git@github.com/o/r.git",
        "https://alice:@example.test/x",  # an empty password
        "https://alice%3Apw@example.test/x",  # an encoded colon is data of the user name
        "https://u@x@example.test/x",
        "https:/alice@example.test/x",
        "https:alice@example.test/x",
        "https://example.test/r?to=https://alice@g/",
        "https://h/r?to=https://alice@g/&b=https://u:pw@j/",  # a password elsewhere does not hide it
    ],
)
def test_sec016_reads_a_userinfo_without_a_password(text: str) -> None:
    assert userinfo_without_password(text)


@pytest.mark.parametrize(
    "text",
    [
        "https://alice:pw@example.test/x",
        "https://:pw@example.test/x",
        "https://u@x:y@example.test/x",  # the password is "y"
        "https://@example.test/x",
        "https://:@example.test/x",
        "https://::@example.test/x",
        "https://example.test/a@b",
        "https://example.test/?q=a@b",
        "https://example.test/#a@b",
        "mailto:alice@example.test",
        "urn:x:a@b",
        "file:///a@b",
        "git+https:/alice@example.test/x",
        "x1https:alice@example.test/x",
        "",
    ],
)
def test_sec016_does_not_read_these(text: str) -> None:
    assert not userinfo_without_password(text)


def test_every_masked_userinfo_is_a_password_or_a_user_name_only() -> None:
    # SEC014 and SEC016 together cover what the mask hides, and a userinfo is in one of them.
    for text in ("https://a:b@h/", "https://a@h/", "https://a:@h/", "https://h/", "https://:@h/", "https://:b@h/"):
        masked = redact_userinfo(text) != text
        assert masked == (userinfo_password(text) is not None or userinfo_without_password(text)), text
        assert not (userinfo_password(text) is not None and userinfo_without_password(text)), text


def test_a_userinfo_already_spelled_as_the_mask_is_still_a_user_name() -> None:
    assert userinfo_without_password(f"https://{REDACTED_USERINFO}@h/x")


def test_a_rendered_report_is_masked_without_crossing_a_token() -> None:
    # The re-mask of a whole report must not swallow the text between a bare IRI and a later "@" (a language tag).
    line = "[INFO] ONT003 https://example.test: Literal 'a'@en; see https://u:p@h/x"
    assert redact_rendered(line) == "[INFO] ONT003 https://example.test: Literal 'a'@en; see https://****@h/x"
    assert redact_userinfo("https://example.test has 'a'@en") == "https://****@en"  # a field is masked broadly
    assert redact_rendered('"focus": "https://u:p@h/x",') == '"focus": "https://****@h/x",'


@pytest.mark.parametrize(
    ("text", "masked"),
    [
        # The first authority runs to the second's "/", so the second starts inside it (PR #50 review).
        (
            "See https://public.test and https://alice:QXSECRET@private.test/x",
            f"See https://public.test and {MASKED.replace('example', 'private')}",
        ),
        ("https://u:p@h https://v:QXSECRET@g/x", f"https://{REDACTED_USERINFO}@h https://{REDACTED_USERINFO}@g/x"),
        ("https://h\nhttps://alice:QXSECRET@g/x", f"https://h\nhttps://{REDACTED_USERINFO}@g/x"),
    ],
)
def test_an_authority_inside_another_is_read(text: str, masked: str) -> None:
    assert redact_userinfo(text) == masked
    assert has_userinfo(text)
    assert userinfo_password(text) is not None
    assert "QXSECRET" not in redact_rendered(text)


@pytest.mark.parametrize(
    ("text", "masked"),
    [
        # A scheme starts at the first letter of its run: a reader takes it after a list number or a bullet (#55).
        ("0https://bob:pw@h/x", f"0https://{REDACTED_USERINFO}@h/x"),
        ("1https://bob:pw@h/x", f"1https://{REDACTED_USERINFO}@h/x"),
        (".https://bob:pw@h/x", f".https://{REDACTED_USERINFO}@h/x"),
        ("-https://bob:pw@h/x", f"-https://{REDACTED_USERINFO}@h/x"),
        ("+https://bob:pw@h/x", f"+https://{REDACTED_USERINFO}@h/x"),
        ("see -.+1https://bob:pw@h/x", f"see -.+1https://{REDACTED_USERINFO}@h/x"),
        ("1HTTPS:bob:pw@h/x", f"1HTTPS:{REDACTED_USERINFO}@h/x"),
        ("2ws:\n//bob:pw@h/x", f"2ws:\n//{REDACTED_USERINFO}@h/x"),
        ("9git+https://bob:pw@h/x", f"9git+https://{REDACTED_USERINFO}@h/x"),
        ("1x.y://bob:pw@h/x", f"1x.y://{REDACTED_USERINFO}@h/x"),
        ("urn:x:1https://bob:pw@h/y", f"urn:x:1https://{REDACTED_USERINFO}@h/y"),
        ("https://h/r?next=-https://bob:pw@g/y", f"https://h/r?next=-https://{REDACTED_USERINFO}@g/y"),
        ("https://h/p/1.https://bob:pw@g/y", f"https://h/p/1.https://{REDACTED_USERINFO}@g/y"),
    ],
)
def test_a_scheme_after_a_digit_or_a_sign_is_read(text: str, masked: str) -> None:
    assert redact_userinfo(text) == masked
    assert redact_rendered(text) == masked
    assert has_userinfo(text)
    assert userinfo_password(text) == "pw"


def test_a_scheme_is_read_from_the_first_letter_of_its_run() -> None:
    # The digits and signs that start a run are no part of its scheme; those after its first letter are.
    assert redact_userinfo("x1https://bob:pw@h/x") == f"x1https://{REDACTED_USERINFO}@h/x"
    assert userinfo_password("1https:bob:pw@h/x") == "pw"  # the special scheme https
    assert userinfo_password("x1https:bob:pw@h/x") is None  # the scheme x1https, which is not special
    # No URL parser reads this as a URL, but a reader may: the over-masking of free text (module specification).
    assert redact_userinfo("1http:a@b") == f"1http:{REDACTED_USERINFO}@b"


def test_a_parser_message_near_a_scheme_after_a_digit_is_withheld() -> None:
    source = b"<1https://alice:s3cret@example.test/x> a ; ; ] .\n"
    detail = "at line 1 of <>:\nBad syntax (expected directive or statement) at ^ in:\n'lice:s3cret@exa'"
    assert withheld_parser_message(detail, source).startswith("at line 1; the parser's message is withheld")
    assert withheld_parser_message(detail, b"<https://example.test/x> a ; ; ] .\n") == detail
    # Spelled with a Turtle escape or an XML character reference, it is still a userinfo.
    assert has_userinfo("<\\u002Dhttps://alice:s3cret@example.test/x>")
    assert has_userinfo('rdf:about="&#49;https://alice:s3cret@example.test/x"')


def test_an_authority_inside_a_userinfo_is_masked_with_it() -> None:
    # "http:b" starts an authority inside the userinfo "a http:b:pw": one mask covers both, up to the last "@".
    assert redact_userinfo("https://a http:b:pw@h/x") == f"https://{REDACTED_USERINFO}@h/x"
    assert userinfo_password("https://a http:b:pw@h/x") == "b:pw"


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
        "https://h " + "http:a " * 50_000 + "@",
        "https://h " + "a://b " * 50_000 + "@",
        "1" * 400_000 + "@",
        "-.+1" * 100_000 + "://@",
        "1a://" * 100_000 + " @",
        "1a:" + "\n" * 400_000 + "@",
        "https://h " + "1http:a " * 50_000 + "@",
    ],
    ids=[
        "scheme-then-authority",
        "scheme-run",
        "colons",
        "starts",
        "special",
        "line-breaks",
        "escaped-at",
        "nested-special",
        "nested-generic",
        "digit-run",
        "sign-run",
        "prefixed-starts",
        "prefixed-line-breaks",
        "nested-prefixed",
    ],
)
def test_the_scan_is_linear(text: str) -> None:
    # CodeQL py/polynomial-redos: an unanchored scheme restarted at every letter of a run (7.8 s at 80 k), or
    # one read after the digits and signs that start a run, restarted at each of them.
    started = time.perf_counter()
    redact_userinfo(text)
    redact_rendered(text)
    has_userinfo(text)
    userinfo_password(text)
    userinfo_without_password(text)
    assert time.perf_counter() - started < LINEAR_SCAN_SECONDS


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


def test_the_stream_masks_a_userinfo_with_a_line_break() -> None:
    # print() writes the text, then its "\n": the userinfo's own line break must not end what is written (PR #50).
    target = io.StringIO()
    stream = RedactingStream(target)
    print("https://alice:LineSecret\nTailSecret@example.test/x", file=stream)
    stream.write("https:\n")  # a special scheme whose slashes come in the next write
    stream.write("//alice:SplitSecret@example.test/x\n")
    stream.write("git+https:")  # a scheme that the next write gives an authority
    stream.write("//alice:GitSecret@example.test/x\n")
    stream.drain()
    output = target.getvalue()
    assert not {"LineSecret", "TailSecret", "SplitSecret", "GitSecret"} & set(output.replace("\n", " ").split())
    assert output == redact_userinfo(
        "https://alice:LineSecret\nTailSecret@example.test/x\n"
        "https:\n//alice:SplitSecret@example.test/x\n"
        "git+https://alice:GitSecret@example.test/x\n"
    )
    assert "Secret" not in output


@pytest.mark.parametrize("lead", ["1", ".", "+", "-"])
def test_the_stream_holds_a_scheme_after_a_digit_or_a_sign(lead: str) -> None:
    # The scheme at the end of a write is read as an authority reads it, from the first letter of its run.
    target = io.StringIO()
    stream = RedactingStream(target)
    stream.write(f"{lead}git+https:\n")
    assert target.getvalue() == ""
    stream.write("//alice:GitSecret@example.test/x\n")
    stream.drain()
    assert target.getvalue() == f"{lead}git+https:\n//{REDACTED_USERINFO}@example.test/x\n"


def test_the_stream_writes_a_line_as_soon_as_no_authority_is_open() -> None:
    target = io.StringIO()
    stream = RedactingStream(target)
    stream.write("plain line\nsee https://example.test/x\n")
    assert target.getvalue() == "plain line\nsee https://example.test/x\n"
    # An authority with no "/ ? #" yet may still be given a userinfo by a later line: it is held, the line before
    # it is written.
    stream.write("before\nsee https://example.test\n")
    assert target.getvalue().endswith("x\nbefore\n")
    stream.write("and alice:pw@host/x\nafter\n")
    assert target.getvalue().endswith(f"before\nsee https://{REDACTED_USERINFO}@host/x\nafter\n")


def test_the_stream_holds_lines_behind_an_open_authority_in_linear_time() -> None:
    target = io.StringIO()
    stream = RedactingStream(target)
    started = time.perf_counter()
    stream.write("see https://example.test\n")
    for _ in range(100_000):
        stream.write("a note without an end of authority\n")
    assert target.getvalue() == ""
    stream.write("/x\n")  # the authority ends: everything held is written
    assert time.perf_counter() - started < LINEAR_SCAN_SECONDS
    assert target.getvalue().startswith("see https://example.test\na note") and target.getvalue().endswith("/x\n")


@pytest.mark.parametrize(
    "text",
    ["a" * 400_000 + "@", "1" * 400_000 + "@", "-.+1" * 100_000 + "a:"],
    ids=["scheme-run", "digit-run", "sign-tail"],
)
def test_the_stream_scan_is_linear(text: str) -> None:
    # The stream looks for a scheme at the end of what it holds: anchored like an authority, it never restarts
    # inside a run of scheme characters.
    target = io.StringIO()
    stream = RedactingStream(target)
    started = time.perf_counter()
    stream.write(text)
    stream.drain()
    assert time.perf_counter() - started < LINEAR_SCAN_SECONDS
    assert target.getvalue() == text


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
    "items[:MAX_LISTED]",
    "found[:MAX_LISTED]",
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
