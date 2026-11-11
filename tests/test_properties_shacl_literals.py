"""Properties of the one-line literal spelling of SHACL001's evidence and of rule messages (``term_text``).

Every literal is one N-Triples term that parses back to itself.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis_strategies import budget
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import XSD

from ontolint.rules.support import ntriples_literal, term_text

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


@budget()
@given(literals, st.text(st.characters(codec="ascii", categories=("L", "N")), min_size=1, max_size=12))
def test_a_message_term_is_the_literal_spelling_a_bare_iri_or_a_blank_label(literal: Literal, name: str) -> None:
    # Rule messages (OWL034, OWL036, OWL040, ...) print terms with term_text: one line, Turtle, never a repr.
    term = term_text(literal)
    assert term == ntriples_literal(literal)
    (parsed,) = Graph().parse(data=f"<{EX}s> <{EX}p> {term} .\n", format="turtle").objects()
    assert isinstance(parsed, Literal)
    assert (parsed, parsed.language, parsed.datatype) == (literal, literal.language, literal.datatype)
    assert term_text(URIRef(EX + name)) == EX + name
    assert term_text(BNode(name)) == f"_:{name}"
