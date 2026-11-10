"""Named graphs of TriG, N-Quads and JSON-LD datasets: which graphs state each triple (DATASET-PROVENANCE)."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urljoin

import pytest
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.graph import DATASET_DEFAULT_GRAPH_ID
from rdflib.namespace import OWL, RDF, RDFS
from rdflib.plugins.stores.memory import Memory

from ontolint import loader
from ontolint.datasets import (
    DEFAULT_GRAPH,
    EMPTY_INDEX,
    GraphIndex,
    build_graph_index,
    decode_index,
    encode_index,
    graph_name,
    relative_reference,
)
from ontolint.loader import LoadedGraph, ParseFailure, load_document, load_graph, loaded_graph
from ontolint.paths import resolve_inputs
from ontolint.policy import Policy

E = "http://example.org/"
G1, G2 = f"{E}g1", f"{E}g2"
HEADER = (
    "@prefix e: <http://example.org/> .\n@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n<http://example.org/o> a owl:Ontology .\n"
)
TWO_GRAPHS = HEADER + 'e:g1 { e:A a owl:Class . e:B a owl:Class . }\ne:g2 { e:A a owl:Class ; rdfs:label "A" . }\n'
WORKER = [None, 30.0]  # in process, and in the time-bounded parse worker


def _load(tmp_path: Path, name: str, text: str, seconds: float | None = None) -> LoadedGraph:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    (item,) = resolve_inputs([str(path)], tmp_path)
    return load_document(item, Policy(max_parse_seconds=seconds), tmp_path)


def _graphs(loaded: LoadedGraph, s: str, p: URIRef, o: URIRef | Literal) -> tuple[str, ...]:
    return loaded.graphs.triples[(URIRef(s), p, o)]


# --- the index the loader records ---------------------------------------------------------------------------


@pytest.mark.parametrize("seconds", WORKER)
def test_each_triple_names_the_graphs_that_state_it(tmp_path: Path, seconds: float | None) -> None:
    loaded = _load(tmp_path, "a.trig", TWO_GRAPHS, seconds)
    assert _graphs(loaded, f"{E}A", RDF.type, OWL.Class) == (G1, G2)  # a triple in two graphs belongs to both
    assert _graphs(loaded, f"{E}B", RDF.type, OWL.Class) == (G1,)
    assert _graphs(loaded, f"{E}A", RDFS.label, Literal("A")) == (G2,)
    assert _graphs(loaded, f"{E}o", RDF.type, OWL.Ontology) == (DEFAULT_GRAPH,)
    assert loaded.graphs.names == (DEFAULT_GRAPH, G1, G2)
    assert set(loaded.graphs.triples) == set(loaded.graph)  # the linted union, every triple indexed


def test_the_worker_records_the_same_index_as_the_parent(tmp_path: Path) -> None:
    text = TWO_GRAPHS + "_:b { [] a owl:Restriction . }\n"
    assert _load(tmp_path, "a.trig", text, 30.0).graphs.names == _load(tmp_path, "a.trig", text).graphs.names
    in_process = _load(tmp_path, "b.trig", TWO_GRAPHS)
    assert _load(tmp_path, "b.trig", TWO_GRAPHS, 30.0).graphs == in_process.graphs


@pytest.mark.parametrize("seconds", WORKER)
def test_nquads_name_their_graphs(tmp_path: Path, seconds: float | None) -> None:
    quads = (
        f"<{E}A> <{RDF.type}> <{OWL.Class}> .\n<{E}A> <{RDF.type}> <{OWL.Class}> <{G1}> .\n"
        f"<{E}B> <{RDF.type}> <{OWL.Class}> <{G1}> .\n"
    )
    loaded = _load(tmp_path, "a.nq", quads, seconds)
    assert _graphs(loaded, f"{E}A", RDF.type, OWL.Class) == (DEFAULT_GRAPH, G1)
    assert _graphs(loaded, f"{E}B", RDF.type, OWL.Class) == (G1,)


@pytest.mark.parametrize("seconds", WORKER)
def test_jsonld_named_graphs_are_indexed(tmp_path: Path, seconds: float | None) -> None:
    jsonld = (
        '{"@context": {"e": "http://example.org/", "owl": "http://www.w3.org/2002/07/owl#"}, "@id": "e:g1",'
        ' "@graph": [{"@id": "e:A", "@type": "owl:Class"}]}'
    )
    loaded = _load(tmp_path, "a.jsonld", jsonld, seconds)
    assert _graphs(loaded, f"{E}A", RDF.type, OWL.Class) == (G1,)


DEFAULT_ONLY = {
    "a.trig": HEADER + '{ e:A a owl:Class . }\ne:A rdfs:label "A" .\n',
    "a.nq": f"<{E}A> <{RDF.type}> <{OWL.Class}> .\n",
    "a.jsonld": '{"@context": {"e": "http://example.org/"}, "@graph": [{"@id": "e:A", "@type": "e:K"}]}',
    "a.ttl": HEADER + "e:A a owl:Class .\n",
}


@pytest.mark.parametrize("seconds", WORKER)
@pytest.mark.parametrize("name", sorted(DEFAULT_ONLY))
def test_a_file_with_only_a_default_graph_has_an_empty_index(tmp_path: Path, name: str, seconds: float | None) -> None:
    loaded = _load(tmp_path, name, DEFAULT_ONLY[name], seconds)
    assert len(loaded.graph) > 0
    assert loaded.graphs == GraphIndex()
    assert loaded.graphs.names == ()


# --- graph names --------------------------------------------------------------------------------------------


def test_a_relative_graph_iri_is_named_as_written(tmp_path: Path) -> None:
    loaded = _load(tmp_path, "a.trig", HEADER + "<rel> { e:A a owl:Class . }\n<./> { e:B a owl:Class . }\n")
    assert loaded.graphs.names == (DEFAULT_GRAPH, "./", "rel")
    assert str(tmp_path.name) not in "".join(loaded.graphs.names)


def test_a_relative_graph_iri_is_named_alike_in_the_worker(tmp_path: Path) -> None:
    loaded = _load(tmp_path, "a.trig", HEADER + "<sub/rel> { e:A a owl:Class . }\n", 30.0)
    assert loaded.graphs.names == (DEFAULT_GRAPH, "sub/rel")


def test_a_graph_iri_above_the_files_directory_is_named_as_written(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    text = HEADER + "<../up> { e:A a owl:Class . }\n<#frag> { e:B a owl:Class . }\n<../> { e:C a owl:Class . }\n"
    loaded = _load(tmp_path, "sub/a.trig", text)
    assert set(loaded.graphs.names) == {DEFAULT_GRAPH, "#frag", "../", "../up"}


BASE = "file:///w/sub/a.trig"


@pytest.mark.parametrize(
    ("iri", "reference"),
    [
        ("file:///w/sub/rel", "rel"),
        ("file:///w/sub/x/y", "x/y"),
        ("file:///w/sub/", "./"),
        ("file:///w/sub/a.trig", "a.trig"),
        ("file:///w/sub/a.trig#frag", "#frag"),
        ("file:///w/sub/a.trig?q", "?q"),
        ("file:///w/sub/b.trig#frag", "b.trig#frag"),
        ("file:///w/up", "../up"),
        ("file:///w/sub", "../sub"),
        ("file:///w/", "../"),
        ("file:///w/other/g", "../other/g"),
        ("file:///", "../../"),
        ("file:///?a/../b", "../../?a/../b"),  # a query is no path: its dot segments stay
        ("file:///etc/g", "../../etc/g"),
        ("file:///w/sub/a:b", "./a:b"),
    ],
)
def test_a_file_graph_iri_is_named_relative_to_the_file(iri: str, reference: str) -> None:
    assert relative_reference(iri, BASE) == reference
    assert urljoin(BASE, reference) == iri  # the name resolves back to the graph's IRI


@pytest.mark.parametrize(
    "iri",
    [
        "http://example.org/g",
        "urn:x:g",
        "file://host/w/sub/g",
        "file:/w/sub/g",
        "file:///w/./g",
        "file:///w/../g",
        "file:///w/sub//g",
        "file://",
    ],
)
def test_only_a_resolvable_file_iri_on_the_same_host_is_shortened(iri: str) -> None:
    assert relative_reference(iri, BASE) is None
    assert graph_name(URIRef(iri), [], BASE) == iri


def test_a_blank_graph_is_named_by_its_content_not_its_label(tmp_path: Path) -> None:
    body = " { e:A a owl:Class . [] a owl:Restriction . }\n"
    x = _load(tmp_path, "x.trig", HEADER + "_:x" + body).graphs.names
    y = _load(tmp_path, "y.trig", HEADER + "_:y" + body).graphs.names
    other = _load(tmp_path, "z.trig", HEADER + "_:x { e:B a owl:Class . }\n").graphs.names
    assert x == y
    (name,) = (n for n in x if n != DEFAULT_GRAPH)
    assert name.startswith("_:")
    assert len(name) == len("_:") + 12
    assert x != other


def test_an_empty_named_graph_has_no_name(tmp_path: Path) -> None:
    loaded = _load(tmp_path, "a.trig", TWO_GRAPHS + "e:g3 { }\n")
    assert f"{E}g3" not in loaded.graphs.names
    assert _load(tmp_path, "b.trig", HEADER + "e:g3 { }\n").graphs == EMPTY_INDEX


def test_rdflibs_dataset_default_identifier_is_the_default_graph() -> None:
    store = Memory()
    default = Graph(store=store, identifier=DATASET_DEFAULT_GRAPH_ID)
    named = Graph(store=store, identifier=URIRef(G1))
    default.add((URIRef(f"{E}A"), RDF.type, OWL.Class))
    assert build_graph_index(store, BNode(), "file:///w/") == EMPTY_INDEX
    named.add((URIRef(f"{E}B"), RDF.type, OWL.Class))
    index = build_graph_index(store, BNode(), "file:///w/")
    assert index.triples[(URIRef(f"{E}A"), RDF.type, OWL.Class)] == (DEFAULT_GRAPH,)


# --- the worker's reply -------------------------------------------------------------------------------------


def test_a_reply_without_named_graphs_is_unchanged() -> None:
    graph = Graph(bind_namespaces="none")
    graph.add((URIRef(f"{E}a"), URIRef(f"{E}p"), Literal("x")))
    pinned = (
        b'{"triples":[[["u","http://example.org/a"],["u","http://example.org/p"],["l","x",null,null]]],"namespaces":[]}'
    )
    assert loader._encode_graph(graph) == pinned  # noqa: SLF001
    assert loader._encode_graph(graph, EMPTY_INDEX) == pinned  # noqa: SLF001


def test_a_reply_carries_the_index_over_blank_nodes() -> None:
    blank = BNode("b1")
    triples = [(URIRef(f"{E}A"), RDF.type, OWL.Class), (blank, RDF.type, OWL.Restriction)]
    graph = Graph()
    for triple in triples:
        graph.add(triple)
    index = GraphIndex({triples[0]: (DEFAULT_GRAPH, G1), triples[1]: (G2,)})
    decoded_graph, decoded = loader._decode_document(json.loads(loader._encode_graph(graph, index)))  # noqa: SLF001
    assert decoded == index
    assert set(decoded_graph) == set(graph)


def test_an_index_round_trips_and_skips_unindexed_triples() -> None:
    triples = [(URIRef(f"{E}A"), RDF.type, OWL.Class), (URIRef(f"{E}B"), RDF.type, OWL.Class)]
    index = GraphIndex({triples[1]: (G1, G2)})
    payload = encode_index(index, triples)
    assert payload == {"names": [G1, G2], "of": [[], [0, 1]]}
    assert decode_index(payload, triples) == index
    assert decode_index(None, triples) == EMPTY_INDEX


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"names": "g1", "of": [[]]},
        {"names": [1], "of": [[]]},
        {"names": ["g1"], "of": "x"},
        {"names": ["g1"], "of": []},
        {"names": ["g1"], "of": [0]},
        {"names": ["g1"], "of": [[1]]},
        {"names": ["g1"], "of": [[-1]]},
        {"names": ["g1"], "of": [["0"]]},
    ],
)
def test_a_malformed_index_is_a_worker_error(payload: object) -> None:
    triples = [(URIRef(f"{E}A"), RDF.type, OWL.Class)]
    with pytest.raises(ValueError, match="graph"):
        decode_index(payload, triples)
    reply = {
        "triples": [[["u", f"{E}A"], ["u", str(RDF.type)], ["u", str(OWL.Class)]]],
        "namespaces": [],
        "graphs": payload,
    }
    with pytest.raises(ParseFailure, match="malformed graph index"):
        loader._decode_document(reply)  # noqa: SLF001


# --- where the index travels --------------------------------------------------------------------------------


def test_load_graph_keeps_the_index_for_loaded_graph(tmp_path: Path) -> None:
    path = tmp_path / "a.trig"
    path.write_text(TWO_GRAPHS, encoding="utf-8")
    (item,) = resolve_inputs([str(path)], tmp_path)
    assert loaded_graph(load_graph(item, Policy(), tmp_path)).graphs.names == (DEFAULT_GRAPH, G1, G2)
    assert loaded_graph(Graph()).graphs == EMPTY_INDEX


def test_every_file_of_an_import_closure_keeps_its_own_index(tmp_path: Path) -> None:
    from ontolint.imports import load_closure  # noqa: PLC0415 -- only this test needs the closure loader

    root = tmp_path / "root.trig"
    root.write_text(
        HEADER + "<http://example.org/o> owl:imports <module.trig> .\ne:gr { e:R a owl:Class . }\n", encoding="utf-8"
    )
    (tmp_path / "module.trig").write_text(
        HEADER.replace("example.org/o>", "example.org/m>") + "e:gm { e:M a owl:Class . }\n", encoding="utf-8"
    )
    (item,) = resolve_inputs([str(root)], tmp_path)
    document = load_document(item, Policy(), tmp_path)
    closure = load_closure(document, root, Policy(), None, item, import_root=tmp_path)
    root_module, module = closure.loaded.modules
    assert root_module.graphs.names == (DEFAULT_GRAPH, f"{E}gr")
    assert module.graphs.names == (DEFAULT_GRAPH, f"{E}gm")
    assert closure.loaded.graphs == document.graphs
