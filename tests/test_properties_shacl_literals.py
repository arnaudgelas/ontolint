"""Properties of SHACL001's literal evidence: every literal is one N-Triples term that parses back to itself."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis_strategies import budget
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import XSD

from ontolint.adapters.shacl import ntriples_literal

pytestmark = pytest.mark.slow

EX = "https://example.test/"
# Every character N-Triples escapes or rdflib treats specially, then any other (no surrogates: not UTF-8).
lexical = st.text(st.one_of(st.sampled_from("\"\\\n\r\t'\x00\x0b é名"), st.characters(exclude_categories=["Cs"])))
literals = st.one_of(
    lexical.map(Literal),
    st.tuples(lexical, st.sampled_from(["en", "fr-BE", "zh-Hant"])).map(lambda t: Literal(t[0], lang=t[1])),
    st.tuples(lexical, st.sampled_from([XSD.string, XSD.integer, URIRef(f"{EX}dt")])).map(
        lambda t: Literal(t[0], datatype=t[1])
    ),
)


@budget(2)
@given(literals)
def test_a_literal_is_one_ntriples_term_that_parses_back(literal: Literal) -> None:
    term = ntriples_literal(literal)
    assert "\n" not in term
    assert "\r" not in term
    (parsed,) = Graph().parse(data=f"<{EX}s> <{EX}p> {term} .\n", format="nt").objects()
    assert parsed == literal
    assert str(parsed) == str(literal)


@budget(2)
@given(literals.filter(lambda literal: "\n" not in str(literal)))
def test_a_single_line_literal_is_spelled_as_before(literal: Literal) -> None:
    # Before N-Triples, the evidence used rdflib's ``n3()``, which already agrees on a single line.
    assert ntriples_literal(literal) == literal.n3()
