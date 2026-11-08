"""DATA001's value-space check: every XSD integer type at its bounds and one past them."""

from __future__ import annotations

import pytest
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import XSD

from ontolint.adapters.shacl import _name
from ontolint.rules.owl import _in_value_space

BOUNDS = {
    XSD.nonNegativeInteger: (0, None),
    XSD.positiveInteger: (1, None),
    XSD.nonPositiveInteger: (None, 0),
    XSD.negativeInteger: (None, -1),
    XSD.long: (-(2**63), 2**63 - 1),
    XSD.int: (-(2**31), 2**31 - 1),
    XSD.short: (-(2**15), 2**15 - 1),
    XSD.byte: (-(2**7), 2**7 - 1),
    XSD.unsignedLong: (0, 2**64 - 1),
    XSD.unsignedInt: (0, 2**32 - 1),
    XSD.unsignedShort: (0, 2**16 - 1),
    XSD.unsignedByte: (0, 2**8 - 1),
}
CASES = [
    (datatype, value, inside)
    for datatype, (low, high) in BOUNDS.items()
    for bound, step in ((low, -1), (high, 1))
    if bound is not None
    for value, inside in ((bound, True), (bound + step, False))
]


@pytest.mark.parametrize(("datatype", "value", "inside"), CASES, ids=[f"{d.split('#')[1]}={v}" for d, v, _ in CASES])
def test_integer_bounds_are_exact(datatype: URIRef, value: int, inside: bool) -> None:
    assert _in_value_space(Literal(str(value), datatype=XSD.integer), datatype) is inside


def test_any_integer_fits_xsd_integer_and_xsd_decimal() -> None:
    for datatype in (XSD.integer, XSD.decimal):
        assert _in_value_space(Literal(str(10**30), datatype=XSD.integer), datatype) is True


@pytest.mark.parametrize(
    ("value", "datatype"),
    [
        (Literal("1.5", datatype=XSD.decimal), XSD.integer),  # not an integer-typed value
        (Literal("abc", datatype=XSD.integer), XSD.positiveInteger),  # ill-typed lexical form
        (Literal("1", datatype=XSD.integer), XSD.string),  # not a numeric range
    ],
)
def test_other_pairs_are_not_in_the_value_space(value: Literal, datatype: URIRef) -> None:
    assert _in_value_space(value, datatype) is False


def test_a_missing_report_node_is_named_unknown() -> None:
    assert _name(Graph(), None) == "(unknown)"
    assert _name(Graph(), BNode()).startswith("_:")
