"""Blank nodes in findings: what two interchangeable nodes and a relabelled graph do (#124, #132, #126, #134).

A finding names a blank node by ``stable_blank_id`` (its nearest named owner, the predicates that refer to it and its
reachable content), never by the label a parser chose.  Two consequences are pinned here.

* Nodes with the same identity that a rule reports on in the same words are one finding, as before, and the message
  says so (``reported once for N blank nodes with the same content``), so that two wrong values are not read as one
  (#124).  The count is part of the message only: the focus, the subject and so the baseline identity do not change.
* A rule that orders or picks among blank nodes orders them by identity, as OWL041 does since #108, so that the
  finding is the same in every serialisation and under every labelling of the graph (#126).
"""

# ruff: noqa: PLR2004

from __future__ import annotations

import re
import warnings
from itertools import permutations

import pytest
from rdflib import BNode, Dataset, Graph, Literal, URIRef
from rdflib.compare import isomorphic
from rdflib.term import Node

from ontolint import Linter
from ontolint.models import Finding
from ontolint.reporting import identity

PREFIXES = (
    "@prefix ex: <https://e/> .\n@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
)
ONCE = re.compile(r"\(reported once for (\d+) blank nodes with the same content\)")


def _graph(text: str) -> Graph:
    return Graph().parse(data=PREFIXES + text, format="turtle")


def _findings(graph: Graph, rule: str) -> list[Finding]:
    return list(Linter(graph).execute([rule]).findings)


def _exact(findings: list[Finding]) -> list[tuple[str, str, str, str, tuple[str, ...], tuple[str, ...]]]:
    return sorted((f.rule, f.severity, f.focus, f.message, f.subject, f.related) for f in findings)


# -- #124: isomorphic blank nodes are one finding, and the message says how many --------------------------------------

TWO_VALUES = "ex:d a owl:DatatypeProperty .\nex:i ex:d [ ex:p 'x' ], [ ex:p 'x' ] .\n"
THREE_VALUES = "ex:d a owl:DatatypeProperty .\nex:i ex:d [ ex:p 'x' ], [ ex:p 'x' ], [ ex:p 'x' ] .\n"
ONE_VALUE = "ex:d a owl:DatatypeProperty .\nex:i ex:d [ ex:p 'x' ] .\n"
TWO_DIFFERENT = "ex:d a owl:DatatypeProperty .\nex:i ex:d [ ex:p 'x' ], [ ex:p 'y' ] .\n"


def test_two_isomorphic_blank_values_are_one_finding_that_says_there_are_two() -> None:
    (finding,) = _findings(_graph(TWO_VALUES), "OWL014")

    assert ONCE.search(finding.message)
    assert ONCE.search(finding.message).group(1) == "2"  # type: ignore[union-attr]


def test_the_count_follows_the_number_of_nodes() -> None:
    (finding,) = _findings(_graph(THREE_VALUES), "OWL014")

    assert ONCE.search(finding.message).group(1) == "3"  # type: ignore[union-attr]


def test_one_blank_value_keeps_the_message_it_always_had() -> None:
    (finding,) = _findings(_graph(ONE_VALUE), "OWL014")

    assert ONCE.search(finding.message) is None
    assert finding.message.endswith(".")


def test_blank_values_with_different_content_stay_two_findings() -> None:
    findings = _findings(_graph(TWO_DIFFERENT), "OWL014")

    assert len(findings) == 2
    assert not any(ONCE.search(f.message) for f in findings)


def test_the_count_changes_neither_the_focus_nor_the_baseline_identity() -> None:
    """A baseline written when the two nodes were one finding still matches: only the message gains the count."""
    (one,) = _findings(_graph(ONE_VALUE), "OWL014")
    (two,) = _findings(_graph(TWO_VALUES), "OWL014")

    assert (two.focus, two.subject) == (one.focus, one.subject)
    assert identity(two) == identity(one)


def test_the_same_node_reported_twice_is_not_counted_twice() -> None:
    """A rule may reach one node by two paths: that is one occurrence, not two."""
    graph = _graph(ONE_VALUE)
    ctx = Linter(graph).rule_context
    node = next(o for _s, _p, o in graph if isinstance(o, BNode))

    for _ in range(2):
        ctx.add("OWL014", URIRef("https://e/i"), f"Datatype property points to resource _:{node}.", subject=(node,))

    (finding,) = ctx.findings
    assert ONCE.search(finding.message) is None


def test_the_count_does_not_depend_on_the_labels() -> None:
    graph = _graph(THREE_VALUES)
    labels = sorted({n for t in graph for n in t if isinstance(n, BNode)}, key=str)
    seen = set()
    for order in permutations(range(len(labels))):
        rename: dict[Node, Node] = {old: BNode(f"n{order[i]}") for i, old in enumerate(labels)}
        relabelled = Graph()
        for s, p, o in graph:
            relabelled.add((rename.get(s, s), p, rename.get(o, o)))
        seen.add(tuple(_exact(_findings(relabelled, "OWL014"))))

    assert len(seen) == 1


# -- #126: a rule that picks among blank nodes picks by identity ------------------------------------------------------

ASYMMETRIC = (
    "ex:p a owl:AsymmetricProperty .\n"
    "_:{one} ex:p _:{two} . _:{two} ex:p _:{one} .\n"
    "_:{one} rdfs:comment 'one' . _:{two} rdfs:comment 'two' .\n"
)
COMPLEMENTARY = (
    "ex:C owl:unionOf ( _:{one} _:{two} ) .\n"
    "_:{one} a owl:Class ; owl:complementOf _:{two} ; rdfs:comment 'one' .\n"
    "_:{two} a owl:Class ; rdfs:comment 'two' .\n"
)


def _labelled(template: str, one: str, two: str) -> Graph:
    """``template`` with its node commented ``'one'`` labelled ``one`` and the node commented ``'two'`` ``two``.

    A Turtle parser chooses the labels itself (``_:x`` in the text is not the label), so the nodes are renamed after
    the parse, found by their comment.
    """
    graph = _graph(template.format(one="x", two="y"))
    by_comment: dict[str, Node] = {
        str(o): s for s, o in graph.subject_objects(URIRef("http://www.w3.org/2000/01/rdf-schema#comment"))
    }
    rename: dict[Node, Node] = {by_comment["one"]: BNode(one), by_comment["two"]: BNode(two)}
    out = Graph()
    for s, p, o in graph:
        out.add((rename.get(s, s), p, rename.get(o, o)))
    return out


@pytest.mark.parametrize(("rule", "template"), [("OWL029", ASYMMETRIC), ("OWL043", COMPLEMENTARY)])
def test_swapping_the_labels_of_two_blank_nodes_changes_no_finding(rule: str, template: str) -> None:
    """RELATION (label permutation): the node that is picked or named first is the same whatever each is called."""
    first = _exact(_findings(_labelled(template, "a", "b"), rule))
    swapped = _exact(_findings(_labelled(template, "b", "a"), rule))

    assert first
    assert swapped == first


@pytest.mark.parametrize(("rule", "template"), [("OWL029", ASYMMETRIC), ("OWL043", COMPLEMENTARY)])
@pytest.mark.parametrize("fmt", ["xml", "nt", "json-ld", "turtle", "trig", "nquads"])
def test_every_serialisation_of_the_graph_gives_the_same_findings(rule: str, template: str, fmt: str) -> None:
    graph = _graph(template.format(one="x", two="y"))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)  # rdflib's JSON-LD parser uses its own deprecated class
        source = Dataset() if fmt in {"trig", "nquads"} else Graph()  # these two writers need a context-aware store
        for triple in graph:
            source.add(triple)
        reloaded = Graph().parse(data=source.serialize(format=fmt), format=fmt)
    if not isomorphic(reloaded, graph):
        pytest.skip(f"rdflib's {fmt} writer drops a blank node that only blank nodes refer to: not a linter matter")

    assert _exact(_findings(reloaded, rule)) == _exact(_findings(graph, rule))


def test_asymmetric_pairs_of_iris_are_still_reported_on_the_smaller_one() -> None:
    graph = _graph("ex:p a owl:AsymmetricProperty . ex:b ex:p ex:a . ex:a ex:p ex:b .")

    (finding,) = _findings(graph, "OWL029")

    assert finding.focus == "https://e/a"
    assert "https://e/b" in finding.message


def test_complementary_operands_that_are_iris_keep_their_lexical_order() -> None:
    graph = _graph("ex:C owl:unionOf ( ex:B ex:A ) . ex:A owl:complementOf ex:B .")

    (finding,) = _findings(graph, "OWL043")

    assert "operands https://e/A and https://e/B" in finding.message


def test_two_interchangeable_blank_nodes_in_an_asymmetric_pair_give_one_finding() -> None:
    graph = _graph("ex:p a owl:AsymmetricProperty . _:x ex:p _:y . _:y ex:p _:x .")

    assert len(_findings(graph, "OWL029")) == 1


def test_a_literal_object_of_an_asymmetric_property_is_ignored() -> None:
    graph = Graph()
    graph.add(
        (
            URIRef("https://e/p"),
            URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
            URIRef("http://www.w3.org/2002/07/owl#AsymmetricProperty"),
        )
    )
    graph.add((URIRef("https://e/a"), URIRef("https://e/p"), Literal("x")))

    assert not _findings(graph, "OWL029")
