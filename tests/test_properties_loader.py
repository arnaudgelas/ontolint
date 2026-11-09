"""Properties of the safe loader: robustness on arbitrary bytes, exact limits and serialisation round trips."""

from __future__ import annotations

import contextlib
import multiprocessing
import socket
import sys
import tempfile
import warnings
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest import mock
from urllib.parse import urlsplit

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st
from hypothesis_strategies import PROFILE, budget, roundtrip_triple_lists
from hypothesis_strategies import build_graph as build
from rdflib import BNode, Graph, URIRef
from rdflib.compare import isomorphic
from rdflib.namespace import RDF

from ontolint.loader import InputRejected, LoadError, ParseFailure, load_graph
from ontolint.paths import resolve_inputs
from ontolint.policy import Policy

pytestmark = pytest.mark.slow

# What load_graph documents it may raise: InputRejected for refused input and ParseFailure for every parser error.
EXTENSIONS = (".ttl", ".nt", ".rdf", ".owl", ".xml", ".jsonld", ".json", ".n3", ".trig", ".nq", ".trix", ".txt", "")
SEEDS = (
    b"@prefix e: <http://e/> .\ne:a e:p 1, 2 ; e:q [ e:r e:b ] .\n",
    b'<http://e/a> <http://e/p> "x"@en .\n',
    b'{"@context": "http://127.0.0.1:9/ctx.jsonld", "@id": "http://e/a", "http://e/p": "x"}',
    b'{"@id": "http://e/a", "http://e/p": [{"@value": "x"}]}',
    b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "x"><!ENTITY b "&a;&a;">]><rdf:RDF xmlns:rdf='
    b'"http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:e="http://e/"><rdf:Description rdf:about="http://e/a">'
    b"<e:p>&b;</e:p></rdf:Description></rdf:RDF>",
    b'<?xml version="1.0"?><!DOCTYPE r SYSTEM "http://127.0.0.1:9/x.dtd"><r/>',
    b"\x1f\x8b\x08\x00garbage",
    b"PK\x03\x04junk",
    b"\xff\xfe<\x00r\x00/\x00>\x00",
)


@st.composite
def mutated_seed(draw: st.DrawFn) -> bytes:
    """A known-interesting document with a few random byte edits."""
    data = bytearray(draw(st.sampled_from(SEEDS)))
    for _ in range(draw(st.integers(0, 4))):
        position = draw(st.integers(0, len(data)))
        match draw(st.sampled_from(("insert", "delete", "flip"))):
            case "insert":
                data[position:position] = draw(st.binary(max_size=4))
            case "delete":
                del data[position : position + draw(st.integers(1, 4))]
            case _:
                if position < len(data):
                    data[position] ^= draw(st.integers(1, 255))
    return bytes(data)


documents = st.one_of(st.binary(max_size=200), mutated_seed(), st.text(max_size=120).map(str.encode))


@contextlib.contextmanager
def socket_watch() -> Generator[list[str]]:
    """Record (and refuse) every connection attempt that reaches the real socket layer."""
    seen: list[str] = []

    def connect(self: socket.socket, address: object, /) -> None:
        seen.append(f"connect {address!r}")
        raise ConnectionRefusedError(address)

    def create_connection(address: object, *args: object, **kwargs: object) -> socket.socket:
        seen.append(f"create_connection {address!r}")
        raise ConnectionRefusedError(address)

    def getaddrinfo(host: object, *args: object, **kwargs: object) -> list[Any]:
        seen.append(f"getaddrinfo {host!r}")
        raise socket.gaierror(host)

    saved = (socket.socket.connect, socket.create_connection, socket.getaddrinfo)
    socket.socket.connect, socket.create_connection, socket.getaddrinfo = connect, create_connection, getaddrinfo  # type: ignore[method-assign,assignment]
    try:
        yield seen
    finally:
        socket.socket.connect, socket.create_connection, socket.getaddrinfo = saved  # type: ignore[method-assign]


def load_bytes(data: bytes, suffix: str, policy: Policy | None = None) -> Graph:
    """Write ``data`` to a fresh file named ``input<suffix>`` and load it through the safe loader."""
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        path = root / f"input{suffix}"
        path.write_bytes(data)
        return load_graph(resolve_inputs([path.name], root)[0], policy or Policy(), root)


# --- robustness --------------------------------------------------------------------------------------


@budget(2)
@given(documents, st.sampled_from(EXTENSIONS))
def test_load_graph_returns_a_graph_or_a_documented_error_and_never_uses_the_network(data: bytes, suffix: str) -> None:
    """INVARIANT: arbitrary bytes under any extension give a Graph, InputRejected or ParseFailure; no socket."""
    with socket_watch() as attempts, warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        try:
            graph = load_bytes(data, suffix)
        except InputRejected as error:
            assert error.rule_id.startswith("SEC")
            assert error.message
        except ParseFailure as error:
            assert error.rule_id == "INPUT001"
            assert error.cause_type
            assert isinstance(error.__cause__, Exception)
        except LoadError:  # pragma: no cover - no other LoadError exists
            raise
        else:
            assert isinstance(graph, Graph)
    assert not attempts


@pytest.mark.parametrize(
    ("data", "suffix"),
    [
        pytest.param(b'"\x00', ".ttl", id="ttl-AssertionError"),
        pytest.param(b"1", ".json", id="jsonld-UnboundLocalError"),
        pytest.param(b"?]", ".n3", id="n3-bare-Exception"),
        pytest.param(b"?\x1aFf\x0e", "", id="extensionless-AttributeError"),
        pytest.param(
            b'{"@context":{"a":"b:x","b":"a:y","c":{"@id":"c:z"}},"a":{"b":{"a":{"b":"deep"}}}}',
            ".jsonld",
            id="cyclic-context-RecursionError",
        ),
    ],
)
def test_parser_failures_are_reported_as_one_documented_error_type(data: bytes, suffix: str) -> None:
    """Malformed input must raise ParseFailure (INPUT001), chaining the parser's own exception."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with pytest.raises(ParseFailure) as info:
            load_bytes(data, suffix)

    assert info.value.rule_id == "INPUT001"
    assert info.value.cause_type == type(info.value.__cause__).__name__


def test_the_minimised_cyclic_context_is_rejected_cleanly() -> None:
    """The fuzzer's self-referential JSON-LD context (a RecursionError in rdflib) is a ParseFailure."""
    limit = sys.getrecursionlimit()
    data = b'{"@context":{"":"","":"","c":{"@id":"c:z"},"":"","":{"":{"":""}}},"":""}'
    with pytest.raises(ParseFailure) as info:
        load_bytes(data, ".jsonld")

    assert info.value.cause_type == "RecursionError"
    assert sys.getrecursionlimit() == limit


@pytest.mark.parametrize("suffix", [".n3", ".nq"])
def test_loading_n3_and_nquads_emits_no_warnings(suffix: str) -> None:
    """The loader silences rdflib's deprecation warnings for every format it loads."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        graph = load_bytes(BASE_DOC, suffix)

    assert len(graph) == 1


@budget(1)
@given(st.sampled_from(SEEDS[6:8]), st.binary(max_size=30), st.sampled_from(EXTENSIONS))
def test_compressed_input_is_always_refused_before_parsing(magic: bytes, tail: bytes, suffix: str) -> None:
    """INVARIANT: data that starts with a compression signature is rejected (SEC011), whatever the extension."""
    with pytest.raises(InputRejected) as info:
        load_bytes(magic + tail, suffix)

    assert info.value.rule_id == "SEC011"


# --- limits ------------------------------------------------------------------------------------------

BASE_DOC = b"<http://e/a> <http://e/p> <http://e/o> .\n"


@budget(1)
@given(st.integers(0, 2000))
def test_max_input_bytes_is_exact(extra: int) -> None:
    """INVARIANT: a file of exactly max_input_bytes loads; one byte more is rejected with SEC001."""
    data = BASE_DOC + b"\n" * extra
    size = len(data)

    assert len(load_bytes(data, ".nt", Policy(max_input_bytes=size))) == 1
    with pytest.raises(InputRejected) as info:
        load_bytes(data, ".nt", Policy(max_input_bytes=size - 1))
    assert info.value.rule_id == "SEC001"
    assert len(load_bytes(data, ".nt", Policy(max_input_bytes=size + 1))) == 1


@budget(1)
@given(st.integers(2, 40), st.integers(0, 5))
def test_max_triples_is_exact_and_duplicates_do_not_count(count: int, duplicates: int) -> None:
    """INVARIANT: exactly max_triples distinct triples load; one more is rejected with SEC002; repeats are free."""
    lines = [f"<http://e/s{i}> <http://e/p> <http://e/o> .\n" for i in range(count)]
    data = "".join(lines + lines[:duplicates]).encode()

    assert len(load_bytes(data, ".nt", Policy(max_triples=count))) == count
    assert len(load_bytes(data, ".nt", Policy(max_triples=count + 1))) == count
    with pytest.raises(InputRejected) as info:
        load_bytes(data, ".nt", Policy(max_triples=count - 1))
    assert info.value.rule_id == "SEC002"


def parsable_iri(term: object) -> bool:
    """True for blank nodes, literals and IRIs that ``urllib`` can split (rdflib's RDF/XML parser needs that)."""
    if not isinstance(term, URIRef):
        return True
    try:
        urlsplit(str(term))
    except ValueError:
        return False
    return True


# --- round trips -------------------------------------------------------------------------------------

FORMATS = {"turtle": ".ttl", "nt": ".nt", "xml": ".rdf", "json-ld": ".jsonld"}


@budget(1)
@given(roundtrip_triple_lists(), st.sampled_from(sorted(FORMATS)))
# RDFLib writes this graph as ``[] a <…#Custom> .``, which the syntax sniffer once took for a JSON-LD array.
@example([(BNode("b"), RDF.type, URIRef("https://other.example/ns#Custom"))], "turtle")
def test_serialising_and_reloading_preserves_the_graph(triples: list, fmt: str) -> None:
    """INVARIANT: a graph serialised to turtle, n-triples, RDF/XML or JSON-LD reloads to an isomorphic graph."""
    # rdflib's serialisers mangle malformed rdf:first/rdf:rest structures (cycles, branching) and the JSON-LD one
    # drops blank-node self-loops; those are rdflib limitations, so the round trip uses list-free, loop-free graphs.
    triples = [t for t in triples if t[1] not in (RDF.first, RDF.rest) and t[0] != t[2]]
    triples = [t for t in triples if all(parsable_iri(term) for term in t)]  # '://]' is no URL for urlsplit
    if fmt == "json-ld":  # ... and it loses blank-node cycles, so keep blank nodes out of blank-node chains.
        triples = [t for t in triples if not (isinstance(t[0], BNode) and isinstance(t[2], BNode))]
    graph = build(triples)
    text = graph.serialize(format=fmt)

    reloaded = load_bytes(text.encode("utf-8"), FORMATS[fmt])

    assert len(reloaded) == len(graph)
    assert isomorphic(reloaded, graph)


# --- time budget -------------------------------------------------------------------------------------


def test_the_time_budget_is_off_by_default() -> None:
    """INVARIANT: without max_parse_seconds the parse stays in this process (no worker is ever started)."""
    assert Policy().max_parse_seconds is None
    with mock.patch.object(multiprocessing, "get_context", side_effect=AssertionError("worker used")):
        assert len(load_bytes(BASE_DOC, ".nt")) == 1


@settings(PROFILE, max_examples=8, deadline=None)
@given(roundtrip_triple_lists(), st.sampled_from(["nt", "turtle"]))
def test_worker_and_in_process_parses_give_identical_graphs(triples: list, fmt: str) -> None:
    """INVARIANT: a parse under a time budget returns exactly the triples of the in-process parse."""
    triples = [t for t in triples if all(parsable_iri(term) for term in t)]
    text = build(triples).serialize(format=fmt).encode("utf-8")
    suffix = {"nt": ".nt", "turtle": ".ttl"}[fmt]

    direct = load_bytes(text, suffix)
    budgeted = load_bytes(text, suffix, Policy(max_parse_seconds=120))

    assert len(budgeted) == len(direct)
    assert isomorphic(budgeted, direct)
    assert dict(budgeted.namespaces()) == dict(direct.namespaces())
