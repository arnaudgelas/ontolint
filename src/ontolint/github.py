"""GitHub Actions workflow-command escaping.

``--format github`` annotations are intentionally not offered yet: an annotation needs a
file *and line*, and findings carry no source locations.  The escaping rules live here so
the future formatter cannot get them wrong.
"""

from __future__ import annotations

_DATA_ESCAPES = (("%", "%25"), ("\r", "%0D"), ("\n", "%0A"))
_PROPERTY_ESCAPES = (*_DATA_ESCAPES, (":", "%3A"), (",", "%2C"))


def _escape(text: str, table: tuple[tuple[str, str], ...]) -> str:
    for char, replacement in table:  # ``%`` first, so replacements are never re-escaped.
        text = text.replace(char, replacement)
    return text


def escape_data(text: str) -> str:
    """Escape a workflow-command message (the part after ``::``): ``%``, CR and LF."""
    return _escape(text, _DATA_ESCAPES)


def escape_property(text: str) -> str:
    """Escape a workflow-command property value (``file=``, ``title=``): also ``:`` and ``,``."""
    return _escape(text, _PROPERTY_ESCAPES)
