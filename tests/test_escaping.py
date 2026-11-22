"""``ontolint.escaping``: text on one line and IRIs a Turtle file can hold, from any input (#136)."""

from __future__ import annotations

import pytest

from ontolint import escaping, reporting


def test_the_report_and_the_dqv_file_share_one_renderer() -> None:
    assert reporting.one_line is escaping.one_line


@pytest.mark.parametrize(
    "iri",
    ["https://example.test/q", "https://example.test/q/café#本体?x=1&y=%20", "urn:ontolint:metric:a:1:value", ""],
)
def test_an_iri_without_a_forbidden_character_is_returned_as_it_is(iri: str) -> None:
    assert escaping.safe_iri(iri) is iri


@pytest.mark.parametrize(
    ("char", "encoded"),
    [
        (" ", "%20"),
        ("<", "%3C"),
        (">", "%3E"),
        ('"', "%22"),
        ("{", "%7B"),
        ("}", "%7D"),
        ("|", "%7C"),
        ("\\", "%5C"),
        ("^", "%5E"),
        ("`", "%60"),
        ("\x00", "%00"),
        ("\x1b", "%1B"),
        ("\n", "%0A"),
        ("\x7f", "%7F"),
        ("\x85", "%C2%85"),
        (chr(0x202E), "%E2%80%AE"),
        (chr(0x2028), "%E2%80%A8"),
        (chr(0xE000), "%EE%80%80"),
        (chr(0xD800), "%ED%A0%80"),
        (chr(0xE0001), "%F3%A0%80%81"),
    ],
)
def test_each_forbidden_character_is_percent_encoded_by_its_utf8_bytes(char: str, encoded: str) -> None:
    assert escaping.safe_iri(f"https://e.test/a{char}b") == f"https://e.test/a{encoded}b"


def test_the_result_is_ascii_for_what_it_changed_and_idempotent() -> None:
    once = escaping.safe_iri("https://e.test/a\x1b b\u202e")

    assert escaping.safe_iri(once) == once
    assert once.isascii()
