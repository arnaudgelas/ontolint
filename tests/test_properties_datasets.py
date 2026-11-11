"""Properties of named-graph provenance: it is presentation only, sound, complete and label-free.

Random graphs from :mod:`hypothesis_strategies` are spread over the default graph, two named graphs and a
blank-node graph, written as TriG and as N-Quads, and linted next to the same triples written as one
plain graph (Turtle, N-Triples).
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable, Generator
from contextlib import contextmanager, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from hypothesis_strategies import PROFILE, budget, roundtrip_triple_lists
from rdflib import BNode, Graph, URIRef
from rdflib.compare import isomorphic
from rdflib.namespace import OWL, RDF
from rdflib.term import Node

from ontolint import main
from ontolint.datasets import DEFAULT_GRAPH, GraphIndex
from ontolint.loader import load_document
from ontolint.models import RuleScope
from ontolint.paths import resolve_inputs
from ontolint.policy import Policy
from ontolint.rules.specs import RULE_SPECS
from ontolint.rules.support import stable_blank_id

pytestmark = pytest.mark.slow

Triple = tuple[Node, Node, Node]
GRAPHS: tuple[URIRef | BNode | None, ...] = (
    None,
    URIRef("https://g.test/g1"),
    URIRef("https://g.test/g2"),
    BNode("G3"),
)
PLAIN = {"trig": ("turtle", "ttl"), "nquads": ("nt", "nt")}
EXTENSIONS = {"trig": "trig", "nquads": "nq"}
COLLISIONS = frozenset({"IRI003", "LEX004"})  # the rules whose findings name other terms too
# The set-level rules compare the graphs of a dataset with each other, so they are where graphs are not only
# presentation: they are checked against the triples below, and left out of the comparison with the plain graph.
SET_LEVEL = frozenset(spec.rule_id for spec in RULE_SPECS if spec.scope is RuleScope.SET)


@st.composite
def spread_triples(draw: st.DrawFn) -> list[tuple[Triple, frozenset[URIRef | BNode | None]]]:
    """Distinct triples, each assigned to a non-empty set of graphs (``None`` is the default graph)."""
    triples = list(dict.fromkeys(draw(roundtrip_triple_lists())))
    assume(triples)
    return [(t, frozenset(draw(st.sets(st.sampled_from(GRAPHS), min_size=1)))) for t in triples]


def _relabel(node: Any) -> Any:
    return BNode(f"{node}x") if isinstance(node, BNode) else node


def _lines(triples: list[Triple]) -> list[str]:
    graph = Graph()
    for triple in triples:
        graph.add(triple)
    # Split on newlines only: str.splitlines also breaks at U+0085 and other separators a literal may hold.
    return [line for line in graph.serialize(format="nt").split("\n") if line]


def _dataset(spread: list[tuple[Triple, frozenset[URIRef | BNode | None]]], fmt: str, relabel: bool = False) -> str:
    """The dataset as TriG or N-Quads, built from N-Triples lines (blank labels are document-wide in both)."""
    text: list[str] = []
    for name in GRAPHS:
        triples = [tuple(_relabel(n) for n in t) if relabel else t for t, graphs in spread if name in graphs]
        if not triples:
            continue
        lines = _lines(triples)  # type: ignore[arg-type]
        graph = "" if name is None else (_relabel(name) if relabel else name).n3()
        if fmt == "nquads":
            text.extend(f"{line[: -len(' .')]} {graph} ." if graph else line for line in lines)
        else:
            text.extend([f"{graph} {{", *lines, "}"] if graph else lines)
    return "\n".join(text) + "\n"


@contextmanager
def _directory() -> Generator[Path]:
    with tempfile.TemporaryDirectory() as name:
        yield Path(name).resolve()


def _lint(path: Path, *args: str) -> dict[str, Any]:
    out = StringIO()
    with redirect_stdout(out):
        main([str(path), "--format", "json", "--fail-on", "never", *args])
    report: dict[str, Any] = json.loads(out.getvalue().replace(path.name, "<file>"))
    return report


def _key(finding: dict[str, Any]) -> tuple[str, str, str, str]:
    return finding["rule"], finding["focus"], finding["message"], finding["severity"]


def _texts(graph: Graph) -> Callable[[Node], str]:
    """The text a finding uses for a node (an IRI, or a blank node's stable identity)."""
    return lambda node: stable_blank_id(graph, node) if isinstance(node, BNode) else str(node)


def _check_attribution(report: dict[str, Any], graph: Graph, index: GraphIndex) -> None:
    text = _texts(graph)
    for finding in report["findings"]:
        names = finding.get("graphs", [])
        assert set(names) <= set(index.names)
        terms = {finding["focus"]}
        if finding["rule"] in COLLISIONS:  # their other terms (Finding.related) are not in the report
            continue
        for name in names:  # sound: each named graph states a triple about one of the finding's terms
            assert any(name in graphs and terms & {text(n) for n in triple} for triple, graphs in index.triples.items())
        described = {n for (s, _p, _o), graphs in index.triples.items() if str(s) == finding["focus"] for n in graphs}
        if not finding["focus"].startswith("_:"):  # complete: every graph describing an IRI focus is named
            assert described <= set(names)


def _shared_headers(spread: list[tuple[Triple, frozenset[URIRef | BNode | None]]]) -> tuple[set[str], set[str]]:
    """What ONT007 or ONT008 report for the graphs of one dataset, which are independent documents: each version
    IRI that two graphs give a declared ontology, and each ontology IRI that two graphs declare without giving it
    a version IRI (two versions of one ontology may coexist)."""
    typed = {s for (s, p, o), _graphs in spread if p == RDF.type and o == OWL.Ontology and isinstance(s, URIRef)}
    declaring: dict[URIRef, set[URIRef | BNode | None]] = {}
    versioning: dict[URIRef, set[URIRef | BNode | None]] = {}
    stating: dict[str, set[URIRef | BNode | None]] = {}
    for (s, p, o), graphs in spread:
        if p == RDF.type and o == OWL.Ontology and isinstance(s, URIRef):
            declaring.setdefault(s, set()).update(graphs)
        if p == OWL.versionIRI and s in typed and isinstance(o, URIRef) and isinstance(s, URIRef):
            versioning.setdefault(s, set()).update(graphs)
            stating.setdefault(str(o), set()).update(graphs)
    ontologies = {str(s) for s, graphs in declaring.items() if len(graphs - versioning.get(s, set())) > 1}
    return ontologies, {version for version, graphs in stating.items() if len(graphs) > 1}


@budget(0.25, floor=20)
@given(spread_triples(), st.sampled_from(sorted(PLAIN)))
def test_graphs_are_presentation_only_sound_and_complete(
    spread: list[tuple[Triple, frozenset[URIRef | BNode | None]]], fmt: str
) -> None:
    plain_format, plain_extension = PLAIN[fmt]
    with _directory() as directory:
        dataset_path = directory / f"a.{EXTENSIONS[fmt]}"
        dataset_path.write_text(_dataset(spread, fmt), encoding="utf-8")
        plain = Graph()
        for triple, _graphs in spread:
            plain.add(triple)
        plain_path = directory / f"plain.{plain_extension}"
        plain_text = plain.serialize(format=plain_format)
        plain_path.write_text(plain_text, encoding="utf-8")
        # rdflib's Turtle writer folds a partial list node (an rdf:first with no rdf:rest) into a collection,
        # drops its other triples and relabels blank nodes, so the file is not the graph under test.
        assume(isomorphic(Graph().parse(data=plain_text, format=plain_format), plain))
        relabelled_path = directory / f"b.{EXTENSIONS[fmt]}"
        relabelled_path.write_text(_dataset(spread, fmt, relabel=True), encoding="utf-8")

        report = _lint(dataset_path)
        plain_report = _lint(plain_path)
        # Provenance is presentation only: the same findings (so the same fingerprints) as the plain graph,
        # except the set-level rules, which only a dataset can raise.
        assert sorted(_key(f) for f in report["findings"] if f["rule"] not in SET_LEVEL) == sorted(
            map(_key, plain_report["findings"])
        )
        assert not any(f["rule"] in SET_LEVEL for f in plain_report["findings"])
        ontologies, versions = _shared_headers(spread)
        shared = [f for f in report["findings"] if f["rule"] in SET_LEVEL]
        assert {f["focus"] for f in shared if f["message"].startswith("Ontology IRI")} == ontologies
        assert {f["focus"] for f in shared if f["message"].startswith("Version IRI")} == versions
        # Graph names are label-free: relabelling every blank node, graph names included, changes nothing.
        assert _lint(relabelled_path) == report
        (item,) = resolve_inputs([str(dataset_path)], directory)
        loaded = load_document(item, Policy(), directory)
        _check_attribution(report, loaded.graph, loaded.graphs)
        if any(name is not None for _t, graphs in spread for name in graphs):
            assert loaded.graphs.names
        else:
            assert loaded.graphs == GraphIndex()
            assert all("graphs" not in f for f in report["findings"])
        assert all(n == DEFAULT_GRAPH or n.startswith(("https://g.test/", "_:")) for n in loaded.graphs.names)


@settings(PROFILE, max_examples=4, deadline=None)
@given(spread_triples())
def test_the_worker_reports_the_same_graphs(spread: list[tuple[Triple, frozenset[URIRef | BNode | None]]]) -> None:
    with _directory() as directory:
        path = directory / "a.trig"
        path.write_text(_dataset(spread, "trig"), encoding="utf-8")
        assert _lint(path, "--max-parse-seconds", "30") == _lint(path)
