"""A CommonMark reading of a Markdown summary, the oracle of the ``tests/test_*markdown*.py`` files.

markdown-it-py's CommonMark preset with the GFM table rule parses a summary into tokens.  The tests compare the
token stream with the code-span contents set aside (:func:`shape`), list the code spans (:func:`code_spans`),
and check that every token is one the layout uses (:data:`LAYOUT_TOKENS`) and that the text outside code spans
is the renderer's own vocabulary (:func:`vocabulary_breaches`).  markdown-it has no GFM autolinks, mentions or
issue references, so the vocabulary check is what rules out the bait for them outside a code span.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from markdown_it import MarkdownIt
from markdown_it.token import Token

_PARSER = MarkdownIt("commonmark").enable("table")

LAYOUT_TOKENS = frozenset(
    {
        "heading_open",
        "heading_close",
        "paragraph_open",
        "paragraph_close",
        "inline",
        "text",
        "strong_open",
        "strong_close",
        "code_inline",
        "bullet_list_open",
        "bullet_list_close",
        "list_item_open",
        "list_item_close",
        *(f"{part}_{end}" for part in ("table", "thead", "tbody", "tr", "th", "td") for end in ("open", "close")),
    }
)
"""Every token a summary may hold: no link, image, HTML, entity, line break, code block or other list."""

# What GitHub turns into markup in text: HTML and entities, links and images, emphasis, tables, escapes, mentions
# and references (@, #), math ($), emoji shortcodes (:smile:) and the autolinks of GFM.
_OUTSIDE_VOCABULARY = re.compile(r"[@#$&<>\[\]!_~|\\`*]|://|www\.|:\w+:|(?i:https?|wss?|ftp):")


def tokens(markdown: str) -> list[Token]:
    """Every token of ``markdown``, inline tokens followed by their children, in document order."""

    def walk(items: list[Token]) -> Iterator[Token]:
        for token in items:
            yield token
            yield from walk(token.children or [])

    return list(walk(_PARSER.parse(markdown)))


def shape(markdown: str) -> list[tuple[object, ...]]:
    """The token stream of ``markdown`` with what code spans hold set aside: an inline token's source, and a code
    span's content and fence, are left out; everything else, the text outside code spans included, is kept."""
    return [
        (t.type, t.tag, t.nesting, tuple(sorted(t.attrs.items())), t.level)
        + ((t.content, t.markup) if t.type not in ("inline", "code_inline") else ())
        for t in tokens(markdown)
    ]


def _span_content(token: Token) -> str:
    """What a code span shows, as CommonMark reads it.

    CommonMark strips one space from each side of a code span unless it holds spaces only, and a space is U+0020.
    markdown-it-py tests "spaces only" with ``str.strip()``, which also strips U+00A0, U+3000 and the other
    Unicode spaces, so it keeps the padding of a span such as `` ` \\xa0 ` ``; GitHub's renderer strips it, as the
    specification says.  The token's content is corrected to the specification here.
    """
    content = token.content
    if content.startswith(" ") and content.endswith(" ") and content.strip(" ") and not content.strip():
        return content[1:-1]
    return content


def code_spans(markdown: str) -> list[str]:
    """The content of every code span of ``markdown``, in order."""
    return [_span_content(t) for t in tokens(markdown) if t.type == "code_inline"]


def unexpected_tokens(markdown: str) -> list[str]:
    """The tokens of ``markdown`` the layout never writes (a link, an image, HTML, a line break ...)."""
    return [t.type for t in tokens(markdown) if t.type not in LAYOUT_TOKENS]


def vocabulary_breaches(markdown: str) -> list[str]:
    """The text tokens of ``markdown`` outside code spans that hold what a renderer could turn into markup."""
    return [t.content for t in tokens(markdown) if t.type == "text" and _OUTSIDE_VOCABULARY.search(t.content)]
