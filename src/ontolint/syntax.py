"""Recognise an input's syntax from its first bytes, so a file's extension cannot pick the wrong parser.

Published ontologies often carry an extension that does not match their content: Turtle in a ``.owl`` file
(the MODL pattern library), or OWL Functional Syntax, Manchester Syntax or OWL/XML under ``.owl`` (ODK edit
files, Protege exports).  :func:`sniff` returns the RDFLib format for the RDF syntaxes it recognises with
confidence, one of :data:`NON_RDF_SYNTAXES` for the OWL syntaxes RDFLib cannot read, and ``None`` when it is
unsure; the loader then keeps the extension's format, and keeps it too when the content reads in both
(``{}`` is an empty JSON-LD object and an empty TriG default graph).
"""

from __future__ import annotations

import re

SNIFF_BYTES = 4096
"""How much of the input is inspected."""

NON_RDF_SYNTAXES = {
    "owl-functional": "OWL Functional Syntax",
    "owl-manchester": "OWL Manchester Syntax",
    "owl-xml": "OWL/XML",
}
"""OWL serialisations that are not RDF, with the name used in messages."""

FAMILIES = {"xml": "xml", "application/rdf+xml": "xml", "json-ld": "json-ld", "application/ld+json": "json-ld"}
"""The parser family of an RDFLib format; every other format is a text (Turtle-family) syntax."""

_OWL_NAMESPACE = "http://www.w3.org/2002/07/owl#"
_FIRST_ELEMENT = re.compile(r"<(?![?!])(?:[A-Za-z_][\w.-]*:)?([A-Za-z_][\w.-]*)([^>]*)>?", re.S)
_FUNCTIONAL = re.compile(r"(?:Prefix|Ontology|Import|Declaration)\s*\(")
_MANCHESTER = re.compile(r"(?:Prefix|Ontology|Import|Class|ObjectProperty|DataProperty|AnnotationProperty|Individual):")
# A JSON-LD object has a quoted key next (``@`` too: a keyword whose quotes were lost is still meant as JSON-LD).
# ``{}`` reads as JSON-LD here, the commoner meaning; under ``.trig`` or ``.n3`` :func:`choose` keeps the extension.
# A JSON-LD array holds node objects (or nothing); ``[] a ex:K .`` is a Turtle anonymous blank node.
_JSON_LD = re.compile(r'\{\s*(?:["@]|\})|\[\s*(?:\{|\]\s*$)')
# A TriG (or N3) graph block has a term next, past whitespace and comments: an IRI, a blank node, a prefixed
# name, or the ``}`` of an empty block. A comment runs to its newline, so a run of ``#`` splits only one way and
# the match stays linear (CodeQL py/redos).
_GRAPH_BLOCK = re.compile(r"\{(?:\s|#[^\n]*\n)*(?:<|_:|\[|\}|(?:[A-Za-z][\w.-]*)?:)")
GRAPH_BLOCK_FORMATS = ("trig", "n3")
"""Text syntaxes in which ``{`` opens a graph block."""
_TURTLE = re.compile(r"(?:@prefix|@base|(?i:prefix|base)\s)|<[^\s<>\"{}|^`\\]*>|_:|\[|[A-Za-z][\w.-]*:\S")
_OPENINGS = (
    (_JSON_LD, "json-ld"),
    (_GRAPH_BLOCK, "trig"),
    (_FUNCTIONAL, "owl-functional"),
    (_MANCHESTER, "owl-manchester"),
    (_TURTLE, "turtle"),
)
"""How each non-XML syntax opens, tried in order."""


def _head(data: bytes) -> str:
    """The start of ``data`` as text, without a BOM, leading blank lines or ``#`` comment lines."""
    text = data[:SNIFF_BYTES].decode("utf-8", errors="replace").lstrip("﻿")
    lines = text.splitlines()
    while lines and (not lines[0].strip() or lines[0].lstrip().startswith("#")):
        lines.pop(0)
    return "\n".join(lines).lstrip()


def _xml_root(text: str) -> str | None:
    """``xml`` for an RDF/XML document, ``owl-xml`` for OWL/XML, ``None`` for any other XML."""
    body = re.sub(r"<\?.*?\?>|<!--.*?-->|<!DOCTYPE[^\[>]*(?:\[.*?\])?\s*>", "", text, flags=re.S).lstrip()
    match = _FIRST_ELEMENT.match(body)
    if match is None:
        return None
    name, attributes = match.groups()
    if name == "RDF":
        return "xml"
    if name == "Ontology" and _OWL_NAMESPACE in attributes:
        return "owl-xml"
    return None


def sniff(data: bytes) -> str | None:
    """The syntax ``data`` is written in (an RDFLib format or a :data:`NON_RDF_SYNTAXES` key), or ``None``."""
    text = _head(data)
    if text.startswith(("<?xml", "<!DOCTYPE", "<!--")) or re.match(
        r"<(?:[A-Za-z_][\w.-]*:)?(?:RDF|Ontology)[\s>]", text
    ):
        return _xml_root(text)
    return next((syntax for opening, syntax in _OPENINGS if opening.match(text)), None)


def family(fmt: str) -> str:
    """``xml``, ``json-ld`` or ``text`` (Turtle, N-Triples, N3, N-Quads, TriG)."""
    return FAMILIES.get(fmt, "text")


def choose(extension_format: str, data: bytes) -> str:
    """The format to parse ``data`` with: the sniffed one when it is a different family than the extension's.

    Within the text family the extension decides (``.nt``, ``.nq`` and ``.trig`` look like Turtle), as it does
    for content that reads in the extension's syntax too, and an unsure sniff keeps the extension's format.  A
    non-RDF OWL syntax is returned as such for the caller to report.
    """
    sniffed = sniff(data)
    if sniffed is None:
        return extension_format
    if sniffed in NON_RDF_SYNTAXES:
        return sniffed
    if family(sniffed) == family(extension_format):
        return extension_format
    # XML and JSON-LD are tested before the text syntaxes, so the one overlap is a ``{`` that opens both a
    # JSON-LD object and a graph block.
    if extension_format in GRAPH_BLOCK_FORMATS and _GRAPH_BLOCK.match(_head(data)):
        return extension_format
    return sniffed


def html_start(data: bytes) -> int | None:
    """The 1-based line where an HTML page starts inside ``data`` (a saved web page or server error), if any."""
    match = re.search(rb"<!DOCTYPE\s+html|<html[\s>]", data, flags=re.I)
    return None if match is None else data.count(b"\n", 0, match.start()) + 1
