"""Properties of source regions: they spell the node they locate, and JSON-LD layout never changes a result.

The locator degrades to "no regions" on any internal error (so a bug there cannot fail a lint), which also
means a bug would be silent.  These properties look for it explicitly: every region must point at text that
names its node, and :attr:`SourceIndex.problem` must stay ``None`` for valid input in any layout.
"""

from __future__ import annotations

import html
import json
import random
import re
import tempfile
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urljoin

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st
from hypothesis_strategies import BASE, budget, roundtrip_triple_lists
from rdflib import BNode, Graph, Literal
from rdflib.term import Node

from ontolint.cli import main
from ontolint.loader import ParseFailure, load_document
from ontolint.paths import resolve_inputs
from ontolint.policy import Policy
from ontolint.source_locations import SourceIndex

pytestmark = pytest.mark.slow

SUFFIXES = {"turtle": "ttl", "nt": "nt", "xml": "rdf", "json-ld": "jsonld"}
_PREFIXED = re.compile(
    r"(?P<prefix>[A-Za-z][A-Za-z0-9_-]*|):(?P<local>(?:\\.|[^\s<>\"{}|^`\\;,.])*(?:\.(?:\\.|[^\s<>\"{}|^`\\;,.])+)*)"
)
_XML_REFERENCE = re.compile(r'rdf:(?:about|resource)="([^"]*)"')


def _serialise(graph: Graph, fmt: str) -> str:
    """Serialise, skipping graphs RDFLib itself cannot write (its JSON-LD writer recurses on cyclic lists)."""
    try:
        return graph.serialize(format=fmt)
    except RecursionError:
        assume(False)
        raise  # pragma: no cover -- assume() has already stopped the example


def _index(text: str, suffix: str) -> tuple[SourceIndex, Graph, str]:
    """Load ``text``; inputs RDFLib cannot read back (``s://]`` in RDF/XML) are not the locator's to judge."""
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / f"a.{suffix}").write_text(text, encoding="utf-8")
        item = resolve_inputs([f"a.{suffix}"], root)[0]
        try:
            document = load_document(item, Policy(), root)
        except ParseFailure:
            assume(False)
            raise  # pragma: no cover -- assume() has already stopped the example
        index = document.source_index
        _ = index.locations  # computed while the file still exists
        return index, document.graph, item.path.as_uri()


def _offset(text: str, line: int, column: int) -> int:
    return sum(len(row) + 1 for row in text.split("\n")[: line - 1]) + column - 1


class _Document(NamedTuple):
    text: str
    fmt: str
    graph: Graph  # as parsed, for the prefix bindings
    public_id: str


def _spells(doc: _Document, at: int, node: Node) -> bool:
    """Whether ``doc.text`` names ``node`` at ``at``, the way ``doc.fmt`` writes a node reference."""
    text, fmt, graph, public_id = doc
    if fmt == "xml":  # an element start whose rdf:about or rdf:resource is the node
        tag = text[at : text.index(">", at) + 1]
        return any(urljoin(public_id, html.unescape(value)) == str(node) for value in _XML_REFERENCE.findall(tag))
    if fmt == "json-ld":  # a JSON string holding the node's IRI
        value, _end = json.JSONDecoder().raw_decode(text, at)
        return isinstance(value, str) and urljoin(public_id, value) == str(node)
    if text.startswith("<", at):
        return urljoin(public_id, text[at + 1 : text.index(">", at)]) == str(node)
    if text.startswith("_:", at):
        return isinstance(node, BNode) and text[at + 2 :].startswith(str(node))
    match = _PREFIXED.match(text, at)
    namespaces = {prefix or "": str(namespace) for prefix, namespace in graph.namespaces()}
    return bool(match) and namespaces.get(match["prefix"], "\0") + re.sub(r"\\(.)", r"\1", match["local"]) == str(node)


@budget(0.3)
@given(roundtrip_triple_lists(), st.sampled_from(sorted(SUFFIXES)))
def test_every_region_points_at_text_that_spells_its_node(triples: list, fmt: str) -> None:
    graph = Graph()
    graph.bind("ex", BASE)
    for triple in triples:
        graph.add(triple)
    text = _serialise(graph, fmt)
    index, parsed, public_id = _index(text, SUFFIXES[fmt])
    assert index.problem is None
    for node, location in index.locations.items():
        assert location.column is not None
        at = _offset(text, location.line, location.column)
        assert _spells(_Document(text, fmt, parsed, public_id), at, node), (fmt, node, location, text[at : at + 60])


def _relayout(value: object, rnd: random.Random) -> str:
    """Write ``value`` as JSON with random whitespace and, in some objects, a duplicate key of another type.

    The duplicate comes first, so the last occurrence (the one JSON parsers keep) is unchanged and the
    document still describes the same graph.
    """

    def gap() -> str:
        return rnd.choice(["", " ", "\n", "\t", "  \n "])

    if isinstance(value, dict):
        members = [f"{gap()}{json.dumps(k)}{gap()}:{gap()}{_relayout(v, rnd)}{gap()}" for k, v in value.items()]
        if value and rnd.random() < 0.5:  # noqa: PLR2004 -- half the objects get a decoy
            key = rnd.choice(list(value))
            members.insert(0, f"{gap()}{json.dumps(key)}{gap()}:{gap()}0{gap()}")
        return "{" + ",".join(members) + gap() + "}"
    if isinstance(value, list):
        return "[" + ",".join(f"{gap()}{_relayout(v, rnd)}{gap()}" for v in value) + gap() + "]"
    return json.dumps(value)


def _findings(text: str, tmp: Path) -> list[dict[str, object]]:
    source, out = tmp / "a.jsonld", tmp / "report.json"
    source.write_text(text, encoding="utf-8")
    main([str(source), "--format", "json", "--fail-on", "never", "--output", str(out)])
    findings = json.loads(out.read_text(encoding="utf-8"))["findings"]
    return [{k: v for k, v in f.items() if k != "path"} for f in findings]


@budget(0.2)
@given(roundtrip_triple_lists(), st.randoms(use_true_random=False))
def test_json_ld_layout_never_changes_the_result(triples: list, rnd: random.Random) -> None:
    graph = Graph()
    for triple in triples:
        if not (isinstance(triple[2], Literal) and triple[2].language):  # keep the compact form simple
            graph.add(triple)
    compact = _serialise(graph, "json-ld")
    relaid = _relayout(json.loads(compact), rnd)
    index, _parsed, _public_id = _index(relaid, "jsonld")
    assert index.problem is None
    with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
        assert _findings(relaid, Path(first)) == _findings(compact, Path(second))


def test_the_decoy_keeps_the_graph() -> None:
    document = {"@id": "https://example.test/a", "https://example.test/p": [{"@id": "https://example.test/b"}]}
    relaid = _relayout(document, random.Random(3))  # noqa: S311 -- a fixed layout, not a secret
    _index_a, first, _id_a = _index(json.dumps(document), "jsonld")
    _index_b, second, _id_b = _index(relaid, "jsonld")
    assert relaid != json.dumps(document)
    assert set(second) == set(first)
