"""DATA003 reports a date or time only when XSD 1.1 rejects its lexical form (issue: false positives of RDFLib).

DATA003 asks ``rdflib.Literal.ill_typed``.  For ``xsd:date``, ``xsd:dateTime`` and ``xsd:time`` that answer rejects
lexical forms XSD 1.1 (the datatypes OWL 2 maps, Structural Specification 4) accepts: ``24:00:00`` (``endOfDayFrag``),
the year ``0000`` and a negative year (``yearFrag``) and a year of more than four digits.  A finding says "it is not a
valid xsd:dateTime", so on these forms it states something false.  The forms XSD rejects stay findings.
"""

from __future__ import annotations

import pytest
from rule_harness import graph

from ontolint import Linter

VALID = [
    ("dateTime", "2020-01-01T24:00:00"),
    ("dateTime", "2020-01-01T24:00:00Z"),
    ("dateTime", "2020-01-01T24:00:00.000+01:00"),
    ("dateTime", "0000-01-01T00:00:00"),
    ("dateTime", "-0044-03-15T12:00:00Z"),
    ("dateTime", "12020-01-01T00:00:00"),
    ("time", "24:00:00"),
    ("time", "24:00:00.0Z"),
    ("date", "0000-01-01"),
    ("date", "-0001-01-01"),
    ("date", "12020-01-01"),
    ("date", "0000-02-29"),  # year 0000 is a leap year in XSD 1.1
    ("date", "-0004-02-29"),
    ("date", "2000-02-29"),
    ("date", "2020-12-31+14:00"),
]
INVALID = [
    ("dateTime", "2020-01-01T24:00:01"),
    ("dateTime", "2020-01-01T24:01:00"),
    ("dateTime", "2020-01-01T25:00:00"),
    ("dateTime", "2020-02-30T00:00:00"),
    ("dateTime", "2020-13-01T00:00:00"),
    ("dateTime", "20-01-01T00:00:00"),
    ("dateTime", "tomorrow"),
    ("time", "24:00:01"),
    ("time", "23:59:60"),
    ("date", "2021-02-29"),
    ("date", "1900-02-29"),
    ("date", "-0001-02-29"),
    ("date", "2020-00-10"),
    ("date", "2020-1-1"),
    ("date", "01-01-01"),
]


def _messages(datatype: str, lexical: str) -> list[str]:
    data = graph(f'ex:A a owl:Class ; rdfs:label "A" ; ex:p "{lexical}"^^xsd:{datatype} .')
    return [f.message for f in Linter(data).execute(["DATA003"]).findings]


@pytest.mark.parametrize(("datatype", "lexical"), VALID)
def test_a_lexical_form_xsd_1_1_accepts_is_not_reported(datatype: str, lexical: str) -> None:
    assert _messages(datatype, lexical) == []


@pytest.mark.parametrize(("datatype", "lexical"), INVALID)
def test_a_lexical_form_xsd_1_1_rejects_is_still_reported(datatype: str, lexical: str) -> None:
    assert len(_messages(datatype, lexical)) == 1
