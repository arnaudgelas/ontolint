"""Literal and datatype rules: DATA003 (ill-typed literal) and DATA004 (datatype outside the OWL 2 map).

OWL 2 (Structural Specification, Section 5.7) requires the lexical form of every literal in an OWL 2 DL
ontology to belong to the lexical space of its datatype, and (Section 5.2) every datatype to be
``rdfs:Literal``, a member of the OWL 2 datatype map (Section 4), or a datatype the ontology defines.
``rdfs:Literal`` itself has no lexical space, so no literal can be typed with it.

DATA003 asks RDFLib whether a lexical form is valid (``Literal.ill_typed``), and RDFLib's answer differs from XSD 1.1 in
both directions (it accepts ``"1_0"^^xsd:integer`` and ``"inf"^^xsd:double``), so its findings are ``heuristic`` and its
category is too.  Where it rejects what XSD 1.1 accepts for ``xsd:date``, ``xsd:dateTime`` and ``xsd:time``
(``24:00:00``, the year ``0000``, a negative or a five-digit year), the rule does not report it; it adds no finding
RDFLib does not make.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING

from rdflib import Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD
from rdflib.term import Node

from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity
from ontolint.redaction import clip

from .support import owning_term, value_text

if TYPE_CHECKING:
    from .runtime import RuleContext


SPECS: tuple[RuleSpec, ...] = (
    RuleSpec(
        "DATA003",
        "DATA",
        "Literal whose lexical form is not valid for its datatype",
        Severity.WARNING,
        "Correct the value or its datatype ('2004'^^xsd:gYear, not xsd:date); type plain text as xsd:string.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "literals",
    ),
    RuleSpec(
        "DATA004",
        "DATA",
        "Datatype outside the OWL 2 datatype map",
        Severity.WARNING,
        "Use a datatype of the OWL 2 datatype map (xsd:dateTime rather than xsd:date), or rdfs:Literal.",
        "deterministic",
        RuleBackend.RDFLIB,
        RuleScope.AXIOM,
        "literals",
    ),
)

XSD_NAMESPACE = str(XSD)  # RDFLib's XSD namespace is closed and warns about xsd:anyType
OWL2_XSD_DATATYPES = frozenset(
    URIRef(XSD_NAMESPACE + name)
    for name in (
        "decimal",
        "integer",
        "nonNegativeInteger",
        "nonPositiveInteger",
        "positiveInteger",
        "negativeInteger",
        "long",
        "int",
        "short",
        "byte",
        "unsignedLong",
        "unsignedInt",
        "unsignedShort",
        "unsignedByte",
        "double",
        "float",
        "string",
        "normalizedString",
        "token",
        "language",
        "Name",
        "NCName",
        "NMTOKEN",
        "boolean",
        "hexBinary",
        "base64Binary",
        "anyURI",
        "dateTime",
        "dateTimeStamp",
    )
)
"""The XML Schema datatypes of the OWL 2 datatype map (Structural Specification, Section 4)."""

NOT_DATATYPES = frozenset(URIRef(XSD_NAMESPACE + name) for name in ("anyType", "anySimpleType"))
"""XML Schema's ur-types: not datatypes at all, so no OWL tool can interpret them."""

DATE_TYPES = frozenset(
    URIRef(XSD_NAMESPACE + n) for n in ("date", "time", "gYear", "gYearMonth", "gMonth", "gDay", "gMonthDay")
)

# Where an IRI is used as a datatype: property ranges, datatype restrictions, data ranges and their operands.
DATATYPE_POSITIONS = frozenset(
    {
        RDFS.range,
        OWL.onDatatype,
        OWL.someValuesFrom,
        OWL.allValuesFrom,
        OWL.onDataRange,
        OWL.datatypeComplementOf,
        OWL.equivalentClass,
        RDF.first,
    }
)
LEXICAL_FORM_SHOWN = 40
"""How much of an ill-typed lexical form a message quotes."""


def run(ctx: RuleContext) -> None:
    """Run DATA003 and DATA004."""
    _ill_typed(ctx)
    _unmapped_datatypes(ctx)


def _curie(iri: Node) -> str:
    for prefix, namespace in (("xsd", XSD), ("rdfs", RDFS), ("rdf", RDF), ("owl", OWL)):
        if str(iri).startswith(str(namespace)):
            return f"{prefix}:{str(iri).removeprefix(str(namespace))}"
    return str(iri)


def _foreign(ctx: RuleContext, node: Node) -> bool:
    """An IRI of a vocabulary the file only merges in (its literals are not the author's to fix)."""
    return isinstance(node, URIRef) and not ctx.local(node)


def _sorted[T: Node](triples: Iterable[tuple[Node, Node, T]]) -> list[tuple[Node, Node, T]]:
    return sorted(triples, key=lambda t: (str(t[0]), str(t[1]), str(t[2])))


_YEAR = r"(-?(?:[1-9][0-9]{3,}|0[0-9]{3}))"
_DATE = _YEAR + r"-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])"
_TIME = r"(?:(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]+)?|24:00:00(?:\.0+)?)"
_ZONE = r"(?:Z|[+-](?:0[0-9]|1[0-3]):[0-5][0-9]|[+-]14:00)?"
_XSD_TEMPORAL = {
    XSD.date: re.compile(_DATE + _ZONE),
    XSD.dateTime: re.compile(_DATE + "T" + _TIME + _ZONE),
    XSD.time: re.compile(_TIME + _ZONE),
}
"""The lexical spaces of XSD 1.1 (Part 2, 3.3.7 to 3.3.9) for the three datatypes RDFLib rejects too much of: it reads
them into Python ``datetime`` objects, whose years run from 1 to 9999 and whose hours stop at 23."""
_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_LEAP_DAYS = (31, 29, *_DAYS[2:])


def _xsd_accepts(datatype: Node, lexical: str) -> bool:
    """Whether XSD 1.1 accepts ``lexical`` as an ``xsd:date``, ``xsd:dateTime`` or ``xsd:time``."""
    pattern = _XSD_TEMPORAL.get(datatype) if isinstance(datatype, URIRef) else None
    # whiteSpace is collapse for these atomic datatypes (Part 2, 4.3.6): XML whitespace around the form is dropped
    match = pattern.fullmatch(lexical.strip(" \t\n\r")) if pattern else None
    if not match:
        return False
    if datatype == XSD.time:
        return True
    year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)  # year 0000 is a leap year, as in XSD 1.1
    return day <= (_LEAP_DAYS if leap else _DAYS)[month - 1]


def _ill_typed(ctx: RuleContext) -> None:
    g = ctx.g
    typed = (
        (s, p, o)
        for s, p, o in g
        if isinstance(o, Literal) and o.datatype is not None and (o.datatype == RDFS.Literal or o.ill_typed)
    )
    for s, p, o in _sorted(typed):
        datatype = _curie(o.datatype or RDFS.Literal)
        if o.datatype == RDFS.Literal:
            problem = "rdfs:Literal has no lexical forms in OWL 2, so no literal can be typed with it"
        else:
            problem = f"it is not a valid {datatype}"
        if _xsd_accepts(o.datatype or RDFS.Literal, str(o)):
            continue
        owner = owning_term(g, s)
        if _foreign(ctx, owner):
            continue
        shown = clip(str(o), LEXICAL_FORM_SHOWN, "...")
        message = f"Value {shown!r} of {value_text(p)} is typed {datatype}, but {problem}."
        ctx.add("DATA003", owner, message, subject=(p, o))


def _unmapped_datatypes(ctx: RuleContext) -> None:
    g = ctx.g
    unmapped = (
        (s, p, o)
        for p in DATATYPE_POSITIONS
        for s, o in g.subject_objects(p)
        if isinstance(o, URIRef) and str(o).startswith(str(XSD)) and o not in OWL2_XSD_DATATYPES
    )
    for s, p, o in _sorted(unmapped):
        owner = owning_term(g, s)
        if _foreign(ctx, owner):
            continue
        if o in NOT_DATATYPES:
            reason = "is XML Schema's ur-type, not a datatype; use rdfs:Literal for any value"
        elif o in DATE_TYPES:
            reason = "is not in the OWL 2 datatype map, so OWL 2 DL tools reject it; xsd:dateTime is"
        else:
            reason = "is not in the OWL 2 datatype map, so OWL 2 DL tools reject it"
        ctx.add("DATA004", owner, f"{_curie(o)} (used as {_curie(p)}) {reason}.", confidence="certain", subject=(o, p))
