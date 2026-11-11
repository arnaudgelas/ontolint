"""Metamorphic relation: writing the same graph in another RDF syntax never changes the findings."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st
from hypothesis_strategies import budget, roundtrip_triple_lists
from hypothesis_strategies import build_graph as build
from metamorphic_support import cli_json, document_keys, keys, lint_all, serialisable, workdir
from rdflib import Dataset, Graph
from rdflib.compare import isomorphic

from ontolint.loader import load_graph
from ontolint.paths import resolve_inputs
from ontolint.policy import Policy

pytestmark = pytest.mark.slow

# The graphs have no named graph, so the quad syntaxes (TriG, N-Quads) carry them in the default graph.
FORMATS = {"turtle": ".ttl", "nt": ".nt", "xml": ".rdf", "json-ld": ".jsonld", "trig": ".trig", "nquads": ".nq"}
QUAD_FORMATS = ("trig", "nquads")
MUST_ROUND_TRIP = ("turtle", "nt")
OTHER_FORMATS = tuple(f for f in FORMATS if f != "turtle")


def write(graph: Graph, root: Path, fmt: str) -> Path:
    """Serialise ``graph`` into ``root`` as ``graph.<suffix>`` and return the path."""
    path = root / f"graph{FORMATS[fmt]}"
    source: Graph = graph
    if fmt in QUAD_FORMATS:  # rdflib writes quads only from a context-aware store.
        source = Dataset()
        for triple in graph:
            source.default_graph.add(triple)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)  # rdflib's own quad writers use deprecated Dataset API.
        text = source.serialize(format=fmt)
    if fmt == "trig":
        # A prefix line keeps the syntax sniffer from reading a leading ``{`` as JSON-LD; see the xfail test below.
        text = "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n" + text
    path.write_text(text, encoding="utf-8")
    return path


def load(path: Path, root: Path) -> Graph:
    """Read ``path`` through the real loader, as the CLI does."""
    return load_graph(resolve_inputs([path.name], root)[0], Policy(), root)


@budget(1)
@given(roundtrip_triple_lists())
def test_findings_are_the_same_for_every_serialisation_through_the_loader(triples: list) -> None:
    """RELATION (serialisation invariance): the graph read back from Turtle, N-Triples, RDF/XML, JSON-LD, TriG
    and N-Quads yields the findings of the original graph: same rule, severity, focus and message."""
    graph = build(serialisable(triples))
    assume(len(graph))
    expected = keys(lint_all(graph))
    compared = []

    with workdir() as root:
        for fmt in FORMATS:
            reloaded = load(write(graph, root, fmt), root)
            if not isomorphic(reloaded, graph):
                # A writer or parser limitation of rdflib (it is not a linter matter), so this syntax is skipped;
                # Turtle and N-Triples must always round trip, or the example is not a usable graph at all.
                assume(fmt not in MUST_ROUND_TRIP)
                continue
            compared.append(fmt)
            assert keys(lint_all(reloaded)) == expected, fmt

    assert set(MUST_ROUND_TRIP) <= set(compared)


@budget(0.5)
@given(roundtrip_triple_lists(), st.sampled_from(OTHER_FORMATS))
def test_the_cli_reports_the_same_findings_for_every_serialisation(triples: list, fmt: str) -> None:
    """RELATION (serialisation invariance, CLI): ``--format json`` on a Turtle file and on the same graph in
    another syntax agree on exit code and findings, modulo the report ``path``."""
    graph = build(serialisable(triples))
    assume(len(graph))

    with workdir() as root:
        turtle = write(graph, root, "turtle")
        other = write(graph, root, fmt)
        assume(isomorphic(load(other, root), graph))  # rdflib could not round trip this graph in this syntax.
        code, reference = cli_json(turtle.name)
        other_code, document = cli_json(other.name)

    assert other_code == code
    assert document_keys(document) == document_keys(reference), fmt
    assert document["summary"] == reference["summary"]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "REAL DEFECT: ontolint.syntax.sniff reads any text that starts with '{' as JSON-LD, so a TriG file whose "
        "default graph is the unlabelled block '{ ... }' (what rdflib's TriG writer emits when no prefix is used) "
        "fails with INPUT001 instead of loading.  Reproduction: a file x.trig holding "
        "'{ <https://example.test/onto#A> a <https://example.test/onto#B> . }' ; ontolint x.trig exits 2."
    ),
)
def test_trig_default_graph_block_loads_like_the_same_triple_in_turtle() -> None:
    """RELATION (serialisation invariance, TriG): ``{ s p o . }`` is TriG for the default graph, so it gives the
    findings of the equivalent Turtle triple."""
    turtle = "<https://example.test/onto#A> a <https://example.test/onto#B> .\n"
    trig = "{ " + turtle + "}\n"

    with workdir() as root:
        (root / "x.ttl").write_text(turtle, encoding="utf-8")
        (root / "x.trig").write_text(trig, encoding="utf-8")
        assert keys(lint_all(load(root / "x.trig", root))) == keys(lint_all(load(root / "x.ttl", root)))
