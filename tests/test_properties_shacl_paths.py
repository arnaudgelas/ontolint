"""Properties of SHACL001's ``resultPath`` evidence: every well-formed path is spelled, no report hangs or crashes."""

from __future__ import annotations

from collections.abc import Callable

import pyshacl
import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis_strategies import budget
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.extras.shacl import build_shacl_path
from rdflib.namespace import RDF, SH
from rdflib.paths import AlternativePath, InvPath, MulPath, Path, SequencePath
from rdflib.term import Node

from ontolint.adapters.shacl import MALFORMED_PATH, shacl_issues

pytestmark = pytest.mark.slow

EX = "https://example.test/"
predicates = st.sampled_from([URIRef(f"{EX}{name}") for name in ("p", "q", "r", "名前")])
paths: st.SearchStrategy[URIRef | Path] = st.recursive(
    predicates,
    lambda inner: st.one_of(
        inner.map(InvPath),
        st.lists(inner, min_size=2, max_size=3).map(lambda items: SequencePath(*items)),
        st.lists(inner, min_size=2, max_size=3).map(lambda items: AlternativePath(*items)),
        inner.map(lambda item: MulPath(item, "*")),
        inner.map(lambda item: MulPath(item, "+")),
        inner.map(lambda item: MulPath(item, "?")),
    ),
    max_leaves=8,
)
LINKS = (SH.inversePath, SH.alternativePath, SH.zeroOrMorePath, SH.oneOrMorePath, SH.zeroOrOnePath, RDF.first, RDF.rest)
NODES = tuple(BNode(f"n{i}") for i in range(5))
graph_nodes: st.SearchStrategy[Node] = st.one_of(st.sampled_from(NODES), predicates, st.just(RDF.nil))
structures = st.lists(st.tuples(st.sampled_from(NODES), st.sampled_from(LINKS), graph_nodes), max_size=12)


def _fake_validate(report: Graph) -> Callable[..., tuple[bool, Graph, str]]:
    def validate(*args: object, **kwargs: object) -> tuple[bool, Graph, str]:
        return False, report, ""

    return validate


def _result_path(report: Graph, path: Node) -> str:
    result = BNode()
    report.add((result, RDF.type, SH.ValidationResult))
    report.add((result, SH.focusNode, URIRef(f"{EX}a")))
    report.add((result, SH.resultMessage, Literal("Bad")))
    report.add((result, SH.resultPath, path))
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(pyshacl, "validate", _fake_validate(report))
        (finding,) = shacl_issues(Graph(), Graph())
    assert finding.evidence is not None
    text = finding.evidence["resultPath"]
    assert isinstance(text, str)
    return text


@budget(0.5)
@given(paths)
def test_every_well_formed_path_is_spelled_as_rdflib_spells_it(path: URIRef | Path) -> None:
    """INVARIANT: a SHACL path written from any property path reads back as that path in SPARQL syntax."""
    report = Graph()
    node, _graph = build_shacl_path(path, report)
    expected = str(path) if isinstance(path, URIRef) else path.n3()
    assert _result_path(report, node) == expected


@budget(0.5)
@given(structures, st.sampled_from(NODES))
def test_any_path_structure_is_spelled_or_called_malformed_without_failing(
    triples: list[tuple[BNode, URIRef, Node]], start: BNode
) -> None:
    """INVARIANT: cycles, shared parts and broken lists in a report end in a spelling or the malformed marker."""
    report = Graph()
    for triple in triples:
        report.add(triple)
    text = _result_path(report, start)
    assert text == MALFORMED_PATH or text.startswith(("<", "^", "("))
