"""GitHub Actions workflow-command escaping.

The GitHub Action (``action/entrypoint.py``) prints ``::error::`` annotations whose text includes what the
caller supplied, so it escapes that text here.  There is no ``--format github``: workflow commands cap the
annotations per step and job, so findings reach GitHub as SARIF (code scanning) and as the Markdown summary.
"""

from __future__ import annotations

_DATA_ESCAPES = (("%", "%25"), ("\r", "%0D"), ("\n", "%0A"))


def escape_data(text: str) -> str:
    """Escape a workflow-command message (the part after ``::``): ``%``, CR and LF."""
    for char, replacement in _DATA_ESCAPES:  # ``%`` first, so replacements are never re-escaped.
        text = text.replace(char, replacement)
    return text
