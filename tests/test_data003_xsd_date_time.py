"""DATA003 reports a date or time only when XSD 1.1 rejects its lexical form (issue: false positives of RDFLib).

DATA003 asks ``rdflib.Literal.ill_typed``.  For ``xsd:date``, ``xsd:dateTime`` and ``xsd:time`` that answer rejects
lexical forms XSD 1.1 (the datatypes OWL 2 maps, Structural Specification 4) accepts: ``24:00:00`` (``endOfDayFrag``),
the year ``0000`` and a negative year (``yearFrag``) and a year of more than four digits.  A finding says "it is not a
valid xsd:dateTime", so on these forms it states something false.  The forms XSD rejects stay findings.
"""

from __future__ import annotations

from calendar import isleap, monthrange

import pytest
from hypothesis import given
from hypothesis import strategies as st
from rdflib.namespace import XSD
from rule_harness import graph

from ontolint import Linter
from ontolint.rules.literals import _xsd_accepts

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


# --- a model of the lexical space, against the validator (hypothesis) ------------------------------------------------


XSD_DATE, XSD_DATE_TIME = XSD.date, XSD.dateTime

DATE = st.tuples(st.integers(-9999, 99999), st.integers(0, 13), st.integers(0, 32))
ZONE = st.sampled_from(["", "Z", "+14:00", "-14:00", "+05:30", "-00:00", "+14:01", "+15:00", "+1:00", "Z0"])


def _year(year: int) -> str:
    return f"{'-' if year < 0 else ''}{abs(year):04d}"


def _date_is_real(year: int, month: int, day: int) -> bool:
    """A date of the proleptic Gregorian calendar with the astronomical year numbering of XSD 1.1 (0000 = 1 BCE)."""
    if not 1 <= month <= 12:  # noqa: PLR2004
        return False
    february = 2
    days = 29 if month == february and isleap(year) else 28 if month == february else monthrange(2001, month)[1]
    return 1 <= day <= days


@given(DATE, ZONE)
def test_xsd_date_validator_agrees_with_the_calendar(date: tuple[int, int, int], zone: str) -> None:
    year, month, day = date
    lexical = f"{_year(year)}-{month:02d}-{day:02d}{zone}"
    zone_ok = zone in {"", "Z", "+14:00", "-14:00", "+05:30", "-00:00"}
    assert _xsd_accepts(XSD_DATE, lexical) == (_date_is_real(year, month, day) and zone_ok)


CLOCK = st.tuples(
    st.integers(0, 25), st.integers(0, 61), st.integers(0, 61), st.sampled_from(["", ".0", ".5", ".000", "."])
)


@given(DATE, CLOCK, ZONE)
def test_xsd_date_time_validator_agrees_with_the_model(
    date: tuple[int, int, int], clock: tuple[int, int, int, str], zone: str
) -> None:
    year, month, day = date
    hour, minute, second, fraction = clock
    time = f"{hour:02d}:{minute:02d}:{second:02d}{fraction}"
    lexical = f"{_year(year)}-{month:02d}-{day:02d}T{time}{zone}"
    fraction_ok = fraction != "."
    ordinary = hour < 24 and minute < 60 and second < 60  # noqa: PLR2004
    end_of_day = (hour, minute, second) == (24, 0, 0) and fraction in {"", ".0", ".000"}
    zone_ok = zone in {"", "Z", "+14:00", "-14:00", "+05:30", "-00:00"}
    expected = _date_is_real(year, month, day) and fraction_ok and (ordinary or end_of_day) and zone_ok
    assert _xsd_accepts(XSD_DATE_TIME, lexical) == expected
