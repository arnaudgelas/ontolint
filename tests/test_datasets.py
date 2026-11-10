"""Named graphs of TriG, N-Quads and JSON-LD datasets: which graphs state each triple (DATASET-PROVENANCE)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any
from unittest import mock
from urllib.parse import urljoin

import pytest
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.graph import DATASET_DEFAULT_GRAPH_ID
from rdflib.namespace import OWL, RDF, RDFS
from rdflib.plugins.stores.memory import Memory

from ontolint import loader, main
from ontolint.datasets import (
    DEFAULT_GRAPH,
    EMPTY_INDEX,
    GraphIndex,
    build_graph_index,
    decode_index,
    encode_index,
    finding_graphs,
    graph_name,
    relative_reference,
)
from ontolint.loader import LoadedGraph, ParseFailure, load_document, load_graph, loaded_graph
from ontolint.models import Finding
from ontolint.paths import resolve_inputs
from ontolint.policy import Policy
from ontolint.rules.support import stable_blank_id

FIXTURES = Path(__file__).parent / "fixtures" / "datasets"

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


# --- which graphs a finding names ---------------------------------------------------------------------------

A, B, C = (URIRef(f"{E}{name}") for name in "ABC")


def _finding(focus: str, *related: str, rule: str = "LEX002") -> Finding:
    return Finding(rule, "info", focus, "m", "s", related=related)


def test_a_term_is_where_it_is_described_before_where_it_is_used() -> None:
    index = GraphIndex(
        {(A, RDF.type, OWL.Class): (G1,), (B, RDFS.subClassOf, A): (G2,), (B, RDFS.subClassOf, C): (G2,)}
    )
    used, described, undeclared = _finding(str(A)), _finding(str(B)), _finding(str(C))
    graphs = finding_graphs(Graph(), index, [used, described, undeclared])
    assert graphs == {used: (G1,), described: (G2,), undeclared: (G2,)}  # C is only used: where it is mentioned


def test_a_finding_about_several_terms_names_the_graphs_of_all_of_them() -> None:
    index = GraphIndex({(A, RDF.type, OWL.Class): (G1,), (B, RDF.type, OWL.Class): (DEFAULT_GRAPH, G2)})
    collision = _finding(str(A), str(B), rule="IRI003")
    assert finding_graphs(Graph(), index, [collision]) == {collision: (DEFAULT_GRAPH, G1, G2)}


def test_the_default_graph_is_named_first() -> None:
    index = GraphIndex({(A, RDF.type, OWL.Class): ("!bang", DEFAULT_GRAPH, "&amp")})
    finding = _finding(str(A))
    assert finding_graphs(Graph(), index, [finding]) == {finding: (DEFAULT_GRAPH, "!bang", "&amp")}


def test_a_focus_that_is_no_node_of_the_file_names_no_graph() -> None:
    index = GraphIndex({(A, RDFS.label, Literal("x")): (G1,)})
    findings = [_finding("(ontology)"), _finding("x"), _finding(f"{E}Unknown"), _finding("_:000000000000")]
    assert finding_graphs(Graph(), index, findings) == {}


def test_a_blank_focus_is_matched_by_its_stable_identity() -> None:
    restriction = BNode()
    graph = Graph()
    graph.add((restriction, RDF.type, OWL.Restriction))
    graph.add((restriction, OWL.onProperty, A))
    index = GraphIndex({(restriction, RDF.type, OWL.Restriction): (G1,), (restriction, OWL.onProperty, A): (G1,)})
    finding = _finding(stable_blank_id(graph, restriction), rule="OWL001")
    assert finding_graphs(graph, index, [finding]) == {finding: (G1,)}


def test_blank_identities_are_computed_only_when_a_dataset_finding_needs_one() -> None:
    blank = BNode()
    index = GraphIndex({(blank, RDF.type, OWL.Restriction): (G1,), (A, RDF.type, OWL.Class): (G1,)})
    with mock.patch("ontolint.datasets.stable_blank_id", side_effect=AssertionError("computed")) as computed:
        assert finding_graphs(Graph(), EMPTY_INDEX, [_finding("_:000000000000")]) == {}
        assert finding_graphs(Graph(), index, [_finding(str(A))]) == {_finding(str(A)): (G1,)}
    computed.assert_not_called()


# --- reports: the Done-when case in every format --------------------------------------------------------------

THING, OTHER, ONTO = f"{E}Thing", f"{E}Other", f"{E}onto"
BOTH = ["http://example.org/g1", "http://example.org/g2"]


def _run(tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str, *args: str) -> str:
    target = tmp_path / name
    if not target.exists():
        shutil.copy(FIXTURES / name, target)
    main([str(target), "--fail-on", "never", *args])
    return capsys.readouterr().out


def _json(tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str, *args: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = json.loads(_run(tmp_path, capsys, name, "--format", "json", *args))["findings"]
    return findings


@pytest.mark.parametrize("seconds", ["", "30"])
def test_findings_name_their_graphs_in_json(tmp_path: Path, capsys: pytest.CaptureFixture[str], seconds: str) -> None:
    budget = ["--max-parse-seconds", seconds] if seconds else []
    findings = _json(tmp_path, capsys, "one_term_two_graphs.trig", *budget)
    graphs = {(f["rule"], f["focus"]): f.get("graphs") for f in findings}
    assert graphs[("LEX002", THING)] == BOTH
    assert graphs[("CLS001", THING)] == BOTH
    assert graphs[("LEX002", OTHER)] == ["http://example.org/g1"]
    assert graphs[("ONT003", ONTO)] == [DEFAULT_GRAPH]
    assert all(f["graphs"] for f in findings)
    assert list(findings[0]) == [*Finding("r", "info", "f", "m", "s").to_dict(), "path", "graphs"]


@pytest.mark.parametrize("seconds", ["", "30"])
def test_sarif_results_carry_the_same_graphs(tmp_path: Path, capsys: pytest.CaptureFixture[str], seconds: str) -> None:
    budget = ["--max-parse-seconds", seconds] if seconds else []
    findings = _json(tmp_path, capsys, "one_term_two_graphs.trig", *budget)
    sarif = json.loads(_run(tmp_path, capsys, "one_term_two_graphs.trig", "--format", "sarif", *budget))
    results = sarif["runs"][0]["results"]
    assert [r["properties"]["graphs"] for r in results] == [f["graphs"] for f in findings]


@pytest.mark.parametrize("seconds", ["", "30"])
def test_text_names_the_graphs_under_the_fix(tmp_path: Path, capsys: pytest.CaptureFixture[str], seconds: str) -> None:
    budget = ["--max-parse-seconds", seconds] if seconds else []
    lines = _run(tmp_path, capsys, "one_term_two_graphs.trig", *budget).splitlines()
    for rule in ("CLS001", "LEX002"):
        at = lines.index(next(line for line in lines if f"{rule} {THING}:" in line))
        assert lines[at + 1].startswith("    Fix: ")
        assert lines[at + 2] == "    In: graphs http://example.org/g1, http://example.org/g2"
    at = lines.index(next(line for line in lines if f"LEX002 {OTHER}:" in line))
    assert lines[at + 2] == "    In: graph http://example.org/g1"


def test_an_ontology_finding_without_a_node_names_no_graph(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "a.trig").write_text(
        HEADER.replace("<http://example.org/o> a owl:Ontology .\n", "") + "e:g1 { e:A a owl:Class . }\n",
        encoding="utf-8",
    )
    findings = _json(tmp_path, capsys, "a.trig")
    ontology = [f for f in findings if f["focus"] == "(ontology)"]
    assert ontology
    assert all("graphs" not in f for f in ontology)
    assert all(f["graphs"] == ["http://example.org/g1"] for f in findings if f["focus"] == f"{E}A")


def test_nquads_and_jsonld_findings_name_their_graphs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "a.nq").write_text(
        f"<{E}A> <{RDF.type}> <{OWL.Class}> .\n<{E}A> <{RDF.type}> <{OWL.Class}> <{G1}> .\n", encoding="utf-8"
    )
    (tmp_path / "b.jsonld").write_text(
        '{"@context": {"e": "http://example.org/", "owl": "http://www.w3.org/2002/07/owl#"}, "@id": "e:g1",'
        ' "@graph": [{"@id": "e:A", "@type": "owl:Class"}]}',
        encoding="utf-8",
    )
    nquads = [f["graphs"] for f in _json(tmp_path, capsys, "a.nq", "--select", "LEX001")]
    jsonld = [f["graphs"] for f in _json(tmp_path, capsys, "b.jsonld", "--select", "LEX001")]
    assert nquads == [[DEFAULT_GRAPH, G1]]
    assert jsonld == [[G1]]


def test_graph_names_hold_no_machine_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "a.trig").write_text(HEADER + "<rel> { e:A a owl:Class . }\n", encoding="utf-8")
    for fmt in ("text", "json", "sarif"):
        out = _run(tmp_path, capsys, "a.trig", "--format", fmt, "--select", "LEX001")
        assert '"rel"' in out or "In: graph rel" in out
        assert str(tmp_path) not in out.replace(f"{tmp_path}/a.trig", "").replace((tmp_path / "a.trig").as_uri(), "")


def test_a_graph_above_the_files_directory_holds_no_machine_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.trig").write_text(HEADER + "<../g> { e:A a owl:Class . }\n", encoding="utf-8")
    file = tmp_path / "sub" / "a.trig"
    for fmt in ("text", "json", "sarif"):
        out = _run(tmp_path, capsys, "sub/a.trig", "--format", fmt, "--select", "LEX001")
        assert '"../g"' in out or "In: graph ../g" in out
        assert str(tmp_path) not in out.replace(str(file), "").replace(file.as_uri(), "")


def test_relabelling_a_blank_graph_changes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    body = " { e:A a owl:Class . [] a owl:Restriction ; owl:onProperty e:p . }\n"
    (tmp_path / "x.trig").write_text(HEADER + "_:x" + body, encoding="utf-8")
    (tmp_path / "y.trig").write_text(HEADER + "_:y" + body, encoding="utf-8")
    x = _run(tmp_path, capsys, "x.trig", "--format", "json")
    y = _run(tmp_path, capsys, "y.trig", "--format", "json")
    assert x.replace("x.trig", "y.trig") == y
    assert '"_:' in x


def test_graphs_come_before_modules(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    findings = _json(tmp_path, capsys, "one_term_two_graphs.trig", "--module-by", "namespace")
    other = next(f for f in findings if f["focus"] == OTHER)
    assert list(other)[-3:] == ["path", "graphs", "modules"]
    text = _run(tmp_path, capsys, "one_term_two_graphs.trig", "--module-by", "namespace")
    assert "    In: graph http://example.org/g1, module http://example.org/" in text.splitlines()
    sarif = json.loads(
        _run(tmp_path, capsys, "one_term_two_graphs.trig", "--module-by", "namespace", "--format", "sarif")
    )
    assert list(sarif["runs"][0]["results"][0]["properties"]) == ["graphs", "modules"]


def test_an_imported_dataset_names_its_graphs_after_its_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "root.ttl").write_text(
        HEADER + "<http://example.org/o> owl:imports <module.trig> .\ne:R a owl:Class .\n", encoding="utf-8"
    )
    (tmp_path / "module.trig").write_text(
        HEADER.replace("example.org/o>", "example.org/m>") + "e:gm { e:M a owl:Class . }\n", encoding="utf-8"
    )
    findings = _json(tmp_path, capsys, "root.ttl", "--follow-imports", "--select", "LEX001")
    by_focus = {f["focus"]: f for f in findings}
    assert Path(by_focus[f"{E}M"]["path"]).name == "module.trig"
    assert by_focus[f"{E}M"]["graphs"] == [f"{E}gm"]
    assert "graphs" not in by_focus[f"{E}R"]
    text = _run(tmp_path, capsys, "root.ttl", "--follow-imports", "--select", "LEX001").splitlines()
    at = text.index(next(line for line in text if f"LEX001 {E}M:" in line))
    assert text[at + 2].endswith("module.trig, graph http://example.org/gm")


def test_moving_a_triple_to_another_graph_keeps_the_baseline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    trig = tmp_path / "a.trig"
    shutil.copy(FIXTURES / "one_term_two_graphs.trig", trig)
    turtle = tmp_path / "a.ttl"  # the same triples, as one Turtle graph
    union = load_graph(resolve_inputs([str(trig)], tmp_path)[0], Policy(), tmp_path)
    turtle.write_text(union.serialize(format="turtle"), encoding="utf-8")
    main([str(trig), "--fail-on", "never", "--write-baseline", str(tmp_path / "trig.json")])
    main([str(turtle), "--fail-on", "never", "--write-baseline", str(tmp_path / "ttl.json")])
    capsys.readouterr()
    baseline = json.loads((tmp_path / "trig.json").read_text(encoding="utf-8"))
    flat = json.loads((tmp_path / "ttl.json").read_text(encoding="utf-8"))
    # The same entries; only the report path the identities are filed under differs.
    assert baseline["fingerprints"] == flat["fingerprints"]
    assert list(baseline["identities"].values()) == list(flat["identities"].values())
    assert list(baseline["identities"]) == baseline["files"] == [str(trig)]
    trig.write_text(trig.read_text(encoding="utf-8").replace("ex:g2 {", "ex:g3 {"), encoding="utf-8")
    out = _run(tmp_path, capsys, "a.trig", "--baseline", str(tmp_path / "trig.json"))
    assert out.startswith("Ontology linter: 0 finding(s)")
    assert "Baseline:" not in out


# --- SHACL validates the union of a dataset's graphs ----------------------------------------------------------

SHAPES = (
    "@prefix sh: <http://www.w3.org/ns/shacl#> .\n@prefix e: <http://example.org/> .\n"
    "e:PersonShape a sh:NodeShape ; sh:targetClass e:Person ;\n"
    "    sh:property [ sh:path e:knows ; sh:class e:Person ] .\n"
)
PEOPLE = HEADER + "e:g1 { e:bob a e:Person . }\ne:g2 { e:alice a e:Person ; e:knows e:bob . }\n"


def _shacl(tmp_path: Path, capsys: pytest.CaptureFixture[str], data: str) -> list[dict[str, Any]]:
    pytest.importorskip("pyshacl")
    (tmp_path / "shapes.ttl").write_text(SHAPES, encoding="utf-8")
    (tmp_path / "people.trig").write_text(data, encoding="utf-8")
    findings = _json(tmp_path, capsys, "people.trig", "--shapes", str(tmp_path / "shapes.ttl"), "--select", "SHACL001")
    return findings


def test_shacl_validates_the_union_of_the_graphs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # e:bob is typed in e:g1 and referenced from e:g2: valid in the union, a violation in e:g2 alone.
    assert _shacl(tmp_path, capsys, PEOPLE) == []


def test_a_shacl_finding_names_the_graphs_of_its_focus(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (violation,) = _shacl(tmp_path, capsys, PEOPLE.replace("e:knows e:bob .", "e:knows e:bob , e:rock ."))
    assert violation["focus"] == f"{E}alice"
    assert violation["graphs"] == [f"{E}g2"]
