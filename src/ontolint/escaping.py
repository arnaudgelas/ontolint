"""Text that is safe to put on one line, or in one IRI, whatever characters it was read from.

Input text reaches reports, error lines and files ontolint writes: a file name, a module name, an exception message, a
literal.  A line break in it would start a line that reads like a report line, an escape sequence would reach a
terminal, a bidi control would reorder what follows, and a lone surrogate would make a strict UTF-8 write fail.
:func:`one_line` writes each of those characters as an escape, for text; :func:`safe_iri` percent-encodes them, for an
IRI.  Both leave ordinary text, accents, CJK and emoji included, as it is.
"""

from __future__ import annotations

import unicodedata

_ESCAPED_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Zl", "Zp", "Zs"})
"""The Unicode general categories an evidence line escapes (U+0020 excepted): controls, format characters (bidi
controls, zero-width characters), surrogates, private use, and line, paragraph and space separators.  A fixed set,
not :meth:`str.isprintable`, which also refuses unassigned code points (Cn), a set each Unicode version changes."""


def _escape(char: str) -> str:
    """``char`` as an N-Triples escape: ``\\uXXXX`` up to U+FFFF, ``\\UXXXXXXXX`` above, in uppercase hex."""
    code = ord(char)
    return f"\\u{code:04X}" if code <= 0xFFFF else f"\\U{code:08X}"  # noqa: PLR2004 -- the BMP's last code point


def one_line(text: str) -> str:
    """``text`` with each character of :data:`_ESCAPED_CATEGORIES` but a space escaped (:func:`_escape`).

    The line then survives ``str.splitlines`` whole, encodes as strict UTF-8 (a lone surrogate is written as its
    code unit) and shows bidi and zero-width characters.  A literal in N-Triples stays a term that parses back to
    itself, except for a lone surrogate: an escaped high and low surrogate side by side read back as one character.
    """
    if text.isprintable():  # False for every escaped character (C* and Z*, but a space), so nothing to escape
        return text
    return "".join(
        _escape(char) if char != " " and unicodedata.category(char) in _ESCAPED_CATEGORIES else char for char in text
    )


_IRI_FORBIDDEN = frozenset('<>" {}|\\^`')
"""The ASCII characters a Turtle IRIREF and RFC 3987 do not allow (a space and ``\\`` included)."""


def safe_iri(iri: str) -> str:
    """``iri`` with every character of :data:`_ESCAPED_CATEGORIES` and of :data:`_IRI_FORBIDDEN` percent-encoded.

    Each is written as the ``%XX`` of its UTF-8 bytes (a lone surrogate by its three-byte form, so the output stays
    ASCII), which makes the IRI a valid Turtle IRIREF.  An IRI without such a character is returned as it is.
    """
    if not any(c in _IRI_FORBIDDEN or unicodedata.category(c) in _ESCAPED_CATEGORIES for c in iri):
        return iri
    return "".join(
        "".join(f"%{byte:02X}" for byte in c.encode("utf-8", "surrogatepass"))
        if c in _IRI_FORBIDDEN or unicodedata.category(c) in _ESCAPED_CATEGORIES
        else c
        for c in iri
    )
