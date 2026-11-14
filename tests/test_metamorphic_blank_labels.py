"""Metamorphic relation: relabelling the blank nodes of a graph, in the same order, changes no finding at all.

A parser chooses the labels of a graph's blank nodes: Turtle and N-Triples generate them, JSON-LD keeps a
document's own (``_:a``, ``_:2``, ``_:b0``) and an API caller picks any.  Every finding names a blank node by its
content (``_:`` and twelve hex digits), so the findings of a relabelled graph must equal the original ones
exactly: rule, severity, focus, message, suggestion, subject and related terms, compared as they are, not through
:func:`metamorphic_support.norm`, which maps every label and every identity to ``_:B`` and so hid issue #54 (a
label left in a message, or a label ``2`` rewriting a count).

The renaming keeps the order of the labels among themselves and against every IRI of the strategies (all the new
labels sort after ``""`` and before ``h``, as the generators' ``QBNA<n>`` do).  A relabelling that changes that order
may still change a finding: OWL029 focuses the smaller of two nodes asserted in both directions, OWL041 the first
node of an odd cycle in a walk over sorted nodes and OWL043 orders its two operands, each by the text of the
nodes, a defect older than #54 and not fixed with it.  The last test pins OWL029's case, as a strict expected
failure, so that a fix of that order makes it pass and fail the run until the mark goes.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import pytest
from hypothesis import example, given
from hypothesis import strategies as st
from hypothesis_strategies import OWNED, budget, triple_lists
from hypothesis_strategies import build_graph as build
from metamorphic_support import Triple, lint_all
from rdflib import BNode, Literal
from rdflib.namespace import OWL, RDF, RDFS, SKOS
from rdflib.term import Node

from ontolint.models import Finding

pytestmark = pytest.mark.slow

type Exact = tuple[str, str, str, str, str, tuple[str, ...], tuple[str, ...]]

# Letters as a hand-written JSON-LD document has them, digits as some writers number them, ``b<n>`` as rdflib,
# Jena and Jackson write them.
SCHEMES: dict[str, Callable[[int], str]] = {
    "letters": lambda i: "abcdefg"[i % 7] * (1 + i // 7),
    "digits": str,
    "b<n>": lambda i: f"b{i}",
}


def relabel(triples: Sequence[Triple], scheme: Callable[[int], str]) -> list[Triple]:
    """``triples`` with each blank node renamed by ``scheme``, the old and the new labels in the same order."""
    old = sorted({n for t in triples for n in t if isinstance(n, BNode)}, key=str)
    new = sorted((BNode(scheme(i)) for i in range(len(old))), key=str)
    rename: dict[Node, Node] = dict(zip(old, new, strict=True))
    return [(rename.get(s, s), rename.get(p, p), rename.get(o, o)) for s, p, o in triples]


def exact(findings: list[Finding]) -> list[Exact]:
    """Findings compared whole, blank-node identities included."""
    return sorted((f.rule, f.severity, f.focus, f.message, f.suggestion, f.subject, f.related) for f in findings)


A, B = OWNED[0], OWNED[1]
# LEX003 counts two labels; relabelled with digits, the third blank node is ``2`` (main rewrote the count).
TWO_LABELS: list[Triple] = [
    (A, RDF.type, OWL.Class),
    (A, RDFS.label, Literal("x", lang="en")),
    (A, RDFS.label, Literal("y", lang="en")),
    *((BNode(f"QBNA{i}"), RDFS.comment, Literal("c")) for i in range(3)),
]
# SKOS013 quotes a blank skos:altLabel; relabelled with letters it is ``a`` (main left it in the message).
BLANK_ALT_LABEL: list[Triple] = [(B, SKOS.altLabel, BNode("QBNA0")), (BNode("QBNA0"), RDFS.comment, Literal("c"))]


@budget(1)
@example(TWO_LABELS, "digits")
@example(BLANK_ALT_LABEL, "letters")
@given(triple_lists(20), st.sampled_from(sorted(SCHEMES)))
def test_relabelling_the_blank_nodes_in_order_changes_no_finding(triples: list[Triple], scheme: str) -> None:
    """RELATION (blank-node relabelling): the findings of the relabelled graph are the original ones, exactly."""
    assert exact(lint_all(build(relabel(triples, SCHEMES[scheme])))) == exact(lint_all(build(triples)))


def asymmetric_pair(first: str, second: str) -> list[Triple]:
    """Two blank nodes, told apart by a comment, related both ways by an asymmetric property: one OWL029 finding."""
    one, two = BNode(first), BNode(second)
    return [
        (OWNED[5], RDF.type, OWL.AsymmetricProperty),
        (one, OWNED[5], two),
        (two, OWNED[5], one),
        (one, RDFS.comment, Literal("one")),
        (two, RDFS.comment, Literal("two")),
    ]


@pytest.mark.xfail(strict=True, reason="OWL029 focuses the node whose label sorts first, not the one by content")
def test_swapping_two_blank_labels_changes_no_owl029_finding() -> None:
    """RELATION (blank-node relabelling, order reversed): swapping the labels of the two nodes changes no finding."""
    original, swapped = (lint_all(build(asymmetric_pair(*labels))) for labels in (("x", "y"), ("y", "x")))
    assert exact([f for f in swapped if f.rule == "OWL029"]) == exact([f for f in original if f.rule == "OWL029"])
