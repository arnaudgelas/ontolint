"""Userinfo in output: no finding, report, baseline hash, stream or name ontolint writes holds an IRI's userinfo.

An IRI's authority may start with a *userinfo*, the part between ``scheme://`` and ``@``
(``https://alice:s3cret@example.test/x``, RFC 3986 section 3.2.1).  The part after its first ``:`` is a
password, and the part before it is a user name, or a token: GitHub, GitLab and Bitbucket accept a token
sent as the user name (``https://<token>:x-oauth-basic@github.com/...``, ``https://<token>@github.com/...``).
This module is the single place that decides where a userinfo is, for SEC014 (:func:`userinfo_password`)
and for what ontolint may write (:func:`redact_userinfo`).

**Specification.**

* *Where a userinfo is.*  The parser reads an authority by its structure, never by the characters an IRI may
  hold, because rdflib accepts IRIs with white space, ``{ } | ^ ` \\``, quotes or a line break (RDF/XML and
  JSON-LD as written, Turtle from a ``UCHAR`` escape) and a URL parser sends such a userinfo as a credential.
  An authority starts after a scheme (a letter, then letters, digits, ``+``, ``.`` or ``-``, not preceded
  by one of those) and its ``:``, then ``//``; for the schemes WHATWG calls special (``http``, ``https``,
  ``ws``, ``wss``, ``ftp``, any case) after ``:`` and its run of ``/`` and ``\\``, as a WHATWG parser
  reads ``https:/u:p@h``, ``https:\\\\u:p@h`` and ``https:u:p@h``; but a ``\\`` after the run's last ``/``
  belongs to the userinfo, as curl and ``urlsplit`` read ``https://\\a:pw@h`` (the user ``\\a``), so the
  mask covers what either reading sends.  A tab or line break may stand between the ``:`` and the
  slashes, or right after them (WHATWG removes them).  The authority runs to the first
  ``/``, ``?`` or ``#``, or the end of the text, and its userinfo up to its *last* ``@``: a URL parser
  reads ``https://u:p@ss@host`` as the password ``p@ss``.  A percent-encoded ``%40`` or ``%3A`` is data of
  the userinfo.  Not a userinfo: one that is empty or only colons (``https://@host``, ``https://:@host``),
  an ``@`` after the authority (``https://host/a@b``, ``?q=a@b``, ``#a@b``), a scheme without an
  authority (``mailto:user@host``, ``urn:x:a@b``, ``git+https:/u:p@h``).  An IRI nested in another
  (``urn:x:https://u:p@h``, ``https://h/?to=https://u:p@g``) has its own authority.
* *SEC014.*  A text embeds a password when one of its userinfos has a non-empty part after its first
  ``:`` (:func:`userinfo_password`); the mask hides it whatever SEC014 decides.
* *What is masked.*  The whole userinfo, user name included, is replaced by :data:`REDACTED_USERINFO`
  (``https://****@example.test/x``).  RFC 3986 says not to render what follows the first ``:``; the user
  name is masked too because a token sent as the user name cannot be told from a name, whatever stands
  after its ``:`` (a placeholder such as ``x-oauth-basic`` or ``x-access-token``, any other string, an
  empty password, or nothing).  The cost is a user name that is not printed, which the SARIF region and
  the source still show; the alternative is a published credential.
* *Free text.*  A message or a note has no IRI delimiters, so its authority also runs to ``/ ? #``: a bare
  IRI followed, before any ``/ ? #``, by an ``@`` (``https://h has 'a'@en``) is masked up to it.  That
  over-masking is cosmetic and is the price of masking ``https://alice:pw SPACE@h`` whole.  A rendered
  report is masked again (:func:`redact_rendered`) with an authority that also stops at white space and
  at the delimiters of the report formats (``" < > \\``), because its fields were masked one by one
  already and a broad mask there would join a bare IRI with the next field.
* *Masking before cutting.*  A message that quotes the start of a long value masks it first (:func:`clip`):
  a userinfo cut before its ``@`` can no longer be found.
* *The result.*  ``*`` is a userinfo sub-delimiter, so a masked IRI is still an IRI with the same
  scheme, host, port, path, query and fragment.  Masking is idempotent (``****`` masks to itself) and
  leaves a text without a userinfo unchanged, character for character.  The scan is linear in the text.
* *Identity.*  Masking happens where a finding is formed (:class:`ontolint.models.Finding`, and
  ``RuleContext.add`` before it removes duplicates), before any fingerprint is computed, and the content
  hash of a blank node or a blank graph reads masked IRIs and literals: IRIs that differ only in their
  userinfo give one focus, one finding, one version 1 fingerprint, one version 2 identity and one
  blank-node identity, and no output holds a hash over a secret, which would let anyone test guesses of it
  offline.  So a baseline cannot tell one credential from another: a credential that replaces a baselined
  one at the same masked IRI is not reported again (README, "Security").
* *Channels.*  Every finding field that is rendered or hashed (focus, message, suggestion, details,
  related terms, subject and evidence), the detail of a rule's execution record, the named graphs of a
  dataset and the modules of ``--module-by namespace`` and ``--module-annotation`` (formed from masked
  text), the report written to stdout or ``--output`` and everything written to stderr while the
  command line runs (:class:`RedactingStream`), in the process and in its bounded workers.  A parser
  message about an input that holds a userinfo is withheld (:func:`withheld_parser_message`): it quotes
  a window of the source that may start or stop inside a userinfo, where no scheme says it is one.
"""

from __future__ import annotations

import codecs
import re
from collections.abc import Iterable, Iterator
from typing import Any, TextIO

REDACTED_USERINFO = "****"
"""What replaces a userinfo.  Named "redacted" so that CodeQL's sensitive-data heuristic, which takes a name with
"password", "secret", "token" or "credential" for a secret, does not take the mask for one when it reaches the
SHA-256 of a fingerprint (py/weak-sensitive-data-hashing)."""

_AUTHORITY = re.compile(
    r"(?<![A-Za-z0-9+.\-])"
    r"(?:(?i:https?|wss?|ftp):(?P<run>[/\\\t\n\r]*)"
    r"|[A-Za-z][A-Za-z0-9+.\-]*:[\t\n\r]*/[\t\n\r]*/)"
)
"""Where an authority starts: after a special scheme's ``:`` and its slashes, or after ``scheme://``.

The look-behind anchors a scheme at the start of its run of scheme characters, so the search never restarts
inside one: the scan is linear (CodeQL py/polynomial-redos)."""

_TO_END = re.compile(r"[^/?#]*")
"""The rest of an authority: up to the first ``/``, ``?`` or ``#``."""

_TO_DELIMITER = re.compile(r"[^/?#\s\"<>\\{}|^`]*")
"""The rest of an authority in a rendered report: also up to white space and the formats' delimiters."""

_ESCAPE = re.compile(r"\\u([0-9A-Fa-f]{4})|\\U([0-9A-Fa-f]{8})|&#[xX]([0-9A-Fa-f]{1,8});|&#([0-9]{1,10});")
"""A Turtle, N-Triples or JSON ``\\u``/``\\U`` escape, or an XML character reference."""

_LINE = re.compile(r"\bline (\d+)")


def _userinfos(text: str, rest: re.Pattern[str] = _TO_END) -> Iterator[tuple[int, int]]:
    """The ``(start, end)`` of each userinfo of ``text`` that holds data, in order; see the module specification."""
    position = 0
    while (start := _AUTHORITY.search(text, position)) is not None:
        begin = start.end()
        # A rendered report's authority stops at "\\" (an escape there), so it starts after the whole run.
        if start.group("run") is not None and rest is _TO_END:
            begin = _special_userinfo_start(text, start.start("run"), begin)
        end = rest.match(text, begin).end()  # type: ignore[union-attr]  # a starred class always matches
        at = text.rfind("@", begin, end)
        if at > begin and text[begin:at].strip(":"):
            yield begin, at
        position = end


def _special_userinfo_start(text: str, run: int, after: int) -> int:
    """Where the userinfo of a special scheme starts, given its run of slashes ``text[run:after]``.

    It is the union of two readings.  A WHATWG parser skips every ``/`` and ``\\`` of the run, but curl and
    Python's ``urlsplit`` read the authority from just after ``//`` and take a ``\\`` there for userinfo data
    (curl sends ``\\a:pw`` as the credentials of ``https://\\a:pw@h``).  So the userinfo starts after the
    run's last ``/`` when it has one, else after the whole run (``https:\\\\u:p@h``), then after any tab or
    line break (WHATWG removes them).  The cost is bounded by the run, which the scan steps past.
    """
    slash = text.rfind("/", run, after)
    begin = after if slash < 0 else slash + 1
    while begin < after and text[begin] in "\t\n\r":
        begin += 1
    return begin


def _masked(text: str, rest: re.Pattern[str]) -> str:
    if "@" not in text:  # the fast path: almost every term and message
        return text
    pieces: list[str] = []
    done = 0
    for begin, end in _userinfos(text, rest):
        pieces += (text[done:begin], REDACTED_USERINFO)
        done = end
    return "".join(pieces) + text[done:] if pieces else text


def redact_userinfo(text: str) -> str:
    """``text`` with every IRI userinfo replaced by :data:`REDACTED_USERINFO`; see the module specification."""
    return _masked(text, _TO_END)


def redact_rendered(text: str) -> str:
    """A rendered report masked again: an authority there also ends at white space and ``" < > \\`` and the like."""
    return _masked(text, _TO_DELIMITER)


def userinfo_password(text: str) -> str | None:
    """The first password of ``text``: the non-empty part after the first ``:`` of a userinfo, else ``None``.

    This is SEC014's test, on the same userinfos the mask hides.
    """
    for begin, end in _userinfos(text):
        password = text[begin:end].partition(":")[2]
        if password:
            return password
    return None


def clip(text: str, limit: int, ellipsis: str = "") -> str:
    """``text`` masked, then cut to ``limit`` characters followed by ``ellipsis`` when it was longer.

    Every message that quotes the start of a value uses it: a userinfo cut before its ``@`` is not found by
    any mask afterwards.
    """
    masked = redact_userinfo(text)
    return masked if len(masked) <= limit else masked[:limit] + ellipsis


def has_userinfo(text: str) -> bool:
    """Whether ``text`` holds an IRI userinfo, also when it is spelled with Turtle, JSON or XML escapes."""
    return next(_userinfos(_ESCAPE.sub(_unescaped, text)), None) is not None


def _unescaped(match: re.Match[str]) -> str:
    code = int(match.group(1) or match.group(2) or match.group(3) or "0", 16) or int(match.group(4) or "0")
    return chr(code) if code <= 0x10FFFF else match.group(0)  # noqa: PLR2004 -- the last code point


def withheld_parser_message(detail: str, source: bytes) -> str:
    """``detail``, a parser's message about ``source``, or a stand-in for it when ``source`` holds a userinfo.

    rdflib's Turtle error quotes up to 60 bytes either side of the error, and its N-Triples error the rest
    of the line: a window that may begin or end inside a userinfo (``lice:s3cr``), where no scheme marks it.
    So the message of an input with a userinfo is withheld, keeping only the line number it names.
    """
    if not has_userinfo(source.decode("utf-8", errors="replace")):
        return detail
    line = _LINE.search(detail)
    where = f"at line {line.group(1)}; " if line else ""
    return f"{where}the parser's message is withheld because the input holds an IRI userinfo, which it may quote"


class RedactingStream:
    """A text stream that writes through to ``stream`` with every userinfo masked (:func:`redact_userinfo`).

    The command line and its bounded workers write stderr through one, so a note, a refusal, a traceback or a
    library's warning that quotes an IRI cannot print a secret.  Text is held until a line ends, so a userinfo
    written in several calls is masked whole; :meth:`drain` writes a last line that has no line break.  Bytes
    written to :attr:`buffer` are decoded and masked the same way.  Everything else (``fileno``, ``encoding``
    ...) is the wrapped stream's: a write to the file descriptor itself is not masked.
    """

    def __init__(self, stream: TextIO) -> None:
        self.stream = stream
        self._pending = ""
        self.buffer = _RedactingBuffer(self)

    def write(self, text: str) -> int:
        self._pending += text
        head, newline, tail = self._pending.rpartition("\n")
        if newline:
            self._pending = tail
            self.stream.write(redact_userinfo(head + newline))
        return len(text)

    def writelines(self, lines: Iterable[str]) -> None:
        for line in lines:
            self.write(line)

    def drain(self) -> None:
        """Write the text held back for want of a line break, masked."""
        if self._pending:
            pending, self._pending = self._pending, ""
            self.stream.write(redact_userinfo(pending))

    def flush(self) -> None:
        """Flush the wrapped stream; a line without its break is still held (see :meth:`drain`)."""
        self.stream.flush()

    def __getattr__(self, name: str) -> Any:  # noqa: ANN401 -- whatever the wrapped stream holds
        return getattr(self.stream, name)


class _RedactingBuffer:
    """The binary side of a :class:`RedactingStream`: bytes are decoded as its encoding, then written as text."""

    def __init__(self, owner: RedactingStream) -> None:
        self._owner = owner
        encoding = getattr(owner.stream, "encoding", None) or "utf-8"
        self._decoder = codecs.getincrementaldecoder(encoding)(errors="replace")

    def write(self, data: bytes) -> int:
        self._owner.write(self._decoder.decode(bytes(data)))
        return len(data)

    def flush(self) -> None:
        self._owner.flush()
