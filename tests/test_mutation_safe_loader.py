"""Exact messages, boundaries and helper contracts of the safe loader (written to kill mutants)."""

# ruff: noqa: PLR2004

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

import pytest
from rdflib import Graph

from ontolint import loader
from ontolint.loader import InputRejected, compression_of, dtd_problem, load_graph, network_disabled
from ontolint.paths import resolve_inputs
from ontolint.policy import Policy
from ontolint.rules.safe_loader import SPECS

TTL = "@prefix e: <http://e/> .\ne:a e:p 1, 2, 3 .\n"
DOC = (
    '<?xml version="1.0"?>\n{doctype}<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"'
    ' xmlns:e="http://e/"><rdf:Description rdf:about="http://e/a"><e:p>x</e:p></rdf:Description></rdf:RDF>\n'
)


def reject(tmp_path: Path, name: str, data: str | bytes, policy: Policy | None = None) -> tuple[str, str]:
    path = tmp_path / name
    path.write_bytes(data if isinstance(data, bytes) else data.encode())
    with pytest.raises(InputRejected) as info:
        load_graph(resolve_inputs([name], tmp_path)[0], policy or Policy(), tmp_path)
    return info.value.rule_id, info.value.message


def test_size_message_names_file_size_and_limit(tmp_path: Path) -> None:
    assert reject(tmp_path, "a.ttl", TTL, Policy(max_input_bytes=10)) == (
        "SEC001",
        f"a.ttl is {len(TTL)} bytes, more than the limit of 10 (max_input_bytes)",
    )


def test_triple_message_and_exact_boundary(tmp_path: Path) -> None:
    assert reject(tmp_path, "a.ttl", TTL, Policy(max_triples=2)) == (
        "SEC002",
        "graph has more than 2 triples (max_triples)",
    )
    path = tmp_path / "ok.ttl"
    path.write_text(TTL, encoding="utf-8")
    assert len(load_graph(resolve_inputs(["ok.ttl"], tmp_path)[0], Policy(max_triples=3), tmp_path)) == 3


def _bounded(limit: int) -> tuple[Any, loader._BoundedStore]:  # noqa: SLF001
    from rdflib import Graph  # noqa: PLC0415

    store = loader._BoundedStore(limit)  # noqa: SLF001
    return Graph(store=store), store


def test_bounded_store_counts_distinct_triples_only() -> None:
    from rdflib import Literal, URIRef  # noqa: PLC0415

    graph, _ = _bounded(2)
    s, p = URIRef("http://e/s"), URIRef("http://e/p")
    for value in (1, 1, 1, 2):
        graph.add((s, p, Literal(value)))
    assert len(graph) == 2
    with pytest.raises(InputRejected, match="more than 2 triples"):
        graph.add((s, p, Literal(3)))


def test_bounded_store_bounds_addn_and_other_contexts() -> None:
    from rdflib import Graph, Literal, URIRef  # noqa: PLC0415

    graph, store = _bounded(3)
    s, p = URIRef("http://e/s"), URIRef("http://e/p")
    graph.addN((s, p, Literal(i), graph) for i in range(3))
    assert len(graph) == 3
    other = Graph(store=store, identifier=URIRef("http://e/other"))
    other.add((s, p, Literal(0)))  # the same triple in another context is not a new triple
    with pytest.raises(InputRejected, match="more than 3 triples"):
        other.add((s, p, Literal(99)))
    graph2, _ = _bounded(1)
    with pytest.raises(InputRejected, match="more than 1 triples"):
        graph2.addN([(s, p, Literal(1), graph2), (s, p, Literal(2), graph2)])


def test_bounded_store_limit_can_be_switched_off() -> None:
    from rdflib import Literal, URIRef  # noqa: PLC0415

    graph, store = _bounded(1)
    s, p = URIRef("http://e/s"), URIRef("http://e/p")
    graph.add((s, p, Literal(1)))
    store.limit = None
    graph.add((s, p, Literal(2)))
    assert len(graph) == 2


def test_context_and_network_messages(tmp_path: Path) -> None:
    remote = '{"@context": "http://127.0.0.1:9/c.jsonld", "@id": "http://e/a", "http://e/p": "x"}'
    assert reject(tmp_path, "a.jsonld", remote) == (
        "SEC006",
        "a.jsonld references an external JSON-LD context 'http://127.0.0.1:9/c.jsonld'; refused",
    )


def test_network_message_names_the_first_blocked_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def parse(self: object, *args: object, **kwargs: object) -> None:
        socket.getaddrinfo("example.invalid", 80)

    monkeypatch.setattr(loader.Graph, "parse", parse)
    assert reject(tmp_path, "a.ttl", TTL) == (
        "SEC013",
        "a.ttl tried to use the network (resolve 'example.invalid'); the network is disabled",
    )


def test_parser_failures_are_wrapped_in_one_documented_type(tmp_path: Path) -> None:
    (tmp_path / "bad.ttl").write_text("not turtle", encoding="utf-8")
    with pytest.raises(loader.ParseFailure) as info:
        load_graph(resolve_inputs(["bad.ttl"], tmp_path)[0], Policy(), tmp_path)
    failure = info.value
    assert isinstance(failure, loader.LoadError)
    assert isinstance(failure, ValueError)
    assert not isinstance(failure, InputRejected)
    assert failure.rule_id == "INPUT001"
    assert failure.cause_type == type(failure.__cause__).__name__
    assert failure.detail == str(failure.__cause__)
    assert str(failure) == f"{failure.cause_type}: {failure.detail}"


@pytest.mark.parametrize(
    ("raised", "expected"),
    [
        (RecursionError("maximum recursion depth exceeded"), "input is nested too deeply"),
        (MemoryError(), "input needs more memory"),
        (KeyError("k"), "'k'"),
        (IndexError("list index out of range"), "list index out of range"),
    ],
)
def test_any_internal_parser_exception_becomes_a_parse_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raised: Exception, expected: str
) -> None:
    def parse(self: object, *args: object, **kwargs: object) -> None:
        raise raised

    monkeypatch.setattr(loader.Graph, "parse", parse)
    (tmp_path / "a.ttl").write_text(TTL, encoding="utf-8")
    with pytest.raises(loader.ParseFailure) as info:
        load_graph(resolve_inputs(["a.ttl"], tmp_path)[0], Policy(), tmp_path)
    assert info.value.cause_type == type(raised).__name__
    assert info.value.detail.startswith(expected)
    assert info.value.__cause__ is raised


def test_recursion_limit_is_untouched_by_a_cyclic_jsonld_context(tmp_path: Path) -> None:
    import sys  # noqa: PLC0415

    before = sys.getrecursionlimit()
    (tmp_path / "c.jsonld").write_text('{"a":"b:x","b":"a:y"}', encoding="utf-8")
    try:
        load_graph(resolve_inputs(["c.jsonld"], tmp_path)[0], Policy(), tmp_path)
    except loader.ParseFailure as exc:
        assert exc.cause_type == "RecursionError"
    assert sys.getrecursionlimit() == before


def test_loaded_graph_is_a_plain_graph_with_the_bound_lifted(tmp_path: Path) -> None:
    from rdflib import Literal, URIRef  # noqa: PLC0415

    (tmp_path / "a.ttl").write_text(TTL, encoding="utf-8")
    graph = load_graph(resolve_inputs(["a.ttl"], tmp_path)[0], Policy(max_triples=3), tmp_path)
    assert type(graph) is Graph
    graph.add((URIRef("http://e/x"), URIRef("http://e/p"), Literal("more")))
    assert len(graph) == 4
    clone = Graph()
    for triple in graph:
        clone.add(triple)
    assert len(clone) == 4


@pytest.mark.parametrize("suffix", [".n3", ".nq"])
def test_n3_and_nquads_emit_no_deprecation_warning(tmp_path: Path, suffix: str) -> None:
    import warnings  # noqa: PLC0415

    (tmp_path / f"a{suffix}").write_text("<http://e/a> <http://e/p> <http://e/o> .\n", encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        graph = load_graph(resolve_inputs([f"a{suffix}"], tmp_path)[0], Policy(), tmp_path)
    assert len(graph) == 1


def test_unrelated_deprecation_warnings_are_not_silenced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import warnings  # noqa: PLC0415

    def parse(self: object, *args: object, **kwargs: object) -> None:
        warnings.warn("something else is deprecated", DeprecationWarning, stacklevel=1)

    monkeypatch.setattr(loader.Graph, "parse", parse)
    (tmp_path / "a.ttl").write_text(TTL, encoding="utf-8")
    with warnings.catch_warnings(), pytest.warns(DeprecationWarning, match="something else"):
        load_graph(resolve_inputs(["a.ttl"], tmp_path)[0], Policy(), tmp_path)


def test_n3_input_cannot_bypass_max_triples_and_the_limit_is_exact(tmp_path: Path) -> None:
    lines = [f"<http://e/s{i}> <http://e/p> [ <http://e/q> ( 1 2 ) ] ." for i in range(6)]
    (tmp_path / "f.n3").write_text("\n".join(lines) + "\n", encoding="utf-8")
    item = resolve_inputs(["f.n3"], tmp_path)[0]
    total = len(load_graph(item, Policy(), tmp_path))
    assert len(load_graph(item, Policy(max_triples=total), tmp_path)) == total
    with pytest.raises(InputRejected) as info:
        load_graph(item, Policy(max_triples=total - 1), tmp_path)
    assert (info.value.rule_id, info.value.message) == (
        "SEC002",
        f"graph has more than {total - 1} triples (max_triples)",
    )


def test_guard_messages_and_attempt_log() -> None:
    with network_disabled() as attempts:
        with pytest.raises(Exception, match=r"network access is disabled \(connect \('h', 1\)\)"):
            socket.create_connection(("h", 1))
        with pytest.raises(Exception, match=r"\(resolve 'h'\)"):
            socket.getaddrinfo("h", 1)
    assert attempts.network == ["connect ('h', 1)", "resolve 'h'"]
    assert attempts.contexts == []


def test_guard_blocks_the_jsonld_fetcher_and_records_the_target() -> None:
    with (
        network_disabled() as attempts,
        pytest.raises(loader.RemoteContextRefused, match="external JSON-LD context 'http://x/c'"),
    ):
        loader.jsonld_context.source_to_json(  # pyright: ignore[reportPrivateImportUsage]
            "http://x/c"
        )
    assert attempts.contexts == ["http://x/c"]


@pytest.mark.parametrize(
    ("data", "kind"),
    [
        (b"\x1f\x8b", "gzip"),
        (b"BZh", "bzip2"),
        (b"\xfd7zXZ\x00", "xz"),
        (b"PK\x03\x04", "zip"),
        (b"\x28\xb5\x2f\xfd", "zstd"),
        (b"7z\xbc\xaf\x27\x1c", "7z"),
        (b"@prefix", None),
        (b"", None),
        (b"x\x1f\x8b", None),
    ],
)
def test_compression_of(data: bytes, kind: str | None) -> None:
    assert compression_of(data) == kind


def entity_doc(declaration: str) -> bytes:
    return DOC.format(doctype=f"<!DOCTYPE rdf:RDF [{declaration}]>\n").encode()


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (DOC.format(doctype="").encode(), None),
        (entity_doc('<!ENTITY owl "http://e/owl#">'), None),
        (entity_doc("<!ENTITY owl 'http://e/owl#'>"), None),
        (entity_doc('<!ENTITY x SYSTEM "file:///etc/hostname">'), "declares an external DTD or entity (SYSTEM/PUBLIC)"),
        (entity_doc('<!ENTITY x system "file:///etc/hostname">'), "declares an external DTD or entity (SYSTEM/PUBLIC)"),
        (entity_doc('<!ENTITY % p PUBLIC "-//x" "http://e/x">'), "declares an external DTD or entity (SYSTEM/PUBLIC)"),
        (
            DOC.format(doctype='<!DOCTYPE rdf:RDF SYSTEM "http://e/x.dtd">\n').encode(),
            "declares an external DTD or entity (SYSTEM/PUBLIC)",
        ),
        (
            DOC.format(doctype='<!doctype rdf:RDF PUBLIC "a" "b">\n').encode(),
            "declares an external DTD or entity (SYSTEM/PUBLIC)",
        ),
        (entity_doc('<!-- SYSTEM --><!ENTITY a "b">'), None),
        (entity_doc('<!ENTITY a "it\'s SYSTEM"><!ENTITY b \'say "PUBLIC"\'>'), None),
        (entity_doc('<!ENTITY a "x"><!ENTITY b "&a;">'), "declares entity 'b' that references another entity"),
        (entity_doc("<!ENTITY a 'x'><!ENTITY b '&#65; and &amp;'>"), None),
        (entity_doc('<!ENTITY a "x"><!ENTITY % b "%a;">'), "declares entity 'b' that references another entity"),
        (entity_doc('<!ENTITY a "x &"><!ENTITY b "T & C">'), None),
    ],
)
def test_dtd_problem(data: bytes, expected: str | None) -> None:
    assert dtd_problem(data, 10_000) == expected


def test_dtd_problem_after_nested_brackets_and_expansion_arithmetic() -> None:
    nested = DOC.format(
        doctype='<!DOCTYPE rdf:RDF [<!ELEMENT a (b)><!ENTITY q "[]>"><!ENTITY x SYSTEM "f">]>\n'
    ).encode()
    assert dtd_problem(nested, 10) == "declares an external DTD or entity (SYSTEM/PUBLIC)"
    body = entity_doc('<!ENTITY big "' + "x" * 10 + '">') + b"&big;&big;&big;"
    assert dtd_problem(body, 30) is None
    assert dtd_problem(body, 29) == "uses entities that expand to 30 characters, more than the limit of 29"


@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le", "utf-16-be", "utf-32", "utf-32-le", "utf-32-be"])
def test_dtd_problem_sees_through_wide_encodings(encoding: str) -> None:
    text = DOC.format(doctype='<!DOCTYPE rdf:RDF [<!ENTITY x SYSTEM "f">]>\n')
    assert dtd_problem(text.encode(encoding), 10) == "declares an external DTD or entity (SYSTEM/PUBLIC)"
    assert dtd_problem(DOC.format(doctype="").encode(encoding), 10) is None


def test_path_checks_report_exact_messages(tmp_path: Path) -> None:
    root, outside = tmp_path / "root", tmp_path / "out"
    root.mkdir()
    outside.mkdir()
    (outside / "o.ttl").write_text(TTL, encoding="utf-8")
    (root / "esc.ttl").symlink_to(outside / "o.ttl")
    with pytest.raises(InputRejected) as info:
        load_graph(resolve_inputs(["esc.ttl"], root)[0], Policy(), root)
    target = (outside / "o.ttl").resolve().as_posix()
    assert info.value.rule_id == "SEC009"
    assert info.value.message == f"esc.ttl is a symlink to {target} outside the working dir"
    with pytest.raises(InputRejected) as info:
        load_graph(resolve_inputs(["../out/o.ttl"], root)[0], Policy(), root)
    assert info.value.message == f"{(outside / 'o.ttl').as_posix()} escapes the working directory through '..'"


def test_compressed_and_dtd_messages_through_the_loader(tmp_path: Path) -> None:
    assert reject(tmp_path, "z.ttl", b"\x1f\x8b\x08\x00") == (
        "SEC011",
        "z.ttl is gzip-compressed; compressed input is refused",
    )
    assert reject(tmp_path, "x.owl", entity_doc('<!ENTITY x SYSTEM "f">')) == (
        "SEC010",
        "x.owl declares an external DTD or entity (SYSTEM/PUBLIC)",
    )


def test_dtd_check_applies_to_rdfxml_formats_only(tmp_path: Path) -> None:
    # Turtle that merely mentions SYSTEM in a comment must not be touched by the XML check.
    path = tmp_path / "a.ttl"
    path.write_text("# <!DOCTYPE x SYSTEM 'y'>\n" + TTL, encoding="utf-8")
    assert len(load_graph(resolve_inputs(["a.ttl"], tmp_path)[0], Policy(), tmp_path)) == 3


def test_specs_are_cli_errors_with_distinct_titles() -> None:
    assert [s.rule_id for s in SPECS] == [
        "SEC001",
        "SEC002",
        "SEC003",
        "SEC006",
        "SEC009",
        "SEC010",
        "SEC011",
        "SEC013",
    ]
    sec003 = next(s for s in SPECS if s.rule_id == "SEC003")
    assert sec003.title == "Parsing exceeds the time budget"
    assert "--max-parse-seconds" in sec003.suggestion
    assert all(s.module == "" and s.backend.value == "cli" and s.severity.value == "error" for s in SPECS)
    assert len({s.title for s in SPECS}) == len(SPECS)


def test_policy_loader_limits_in_the_file_and_defaults() -> None:
    assert Policy.from_mapping({}).max_input_bytes == 64 * 1024 * 1024
    assert Policy.from_mapping({}).max_triples == 5_000_000
    assert Policy.from_mapping({"max_triples": 1}).max_triples == 1
    with pytest.raises(ValueError, match="max_input_bytes must be at least 1"):
        Policy.from_mapping({"max_input_bytes": 0})
    with pytest.raises(ValueError, match="max_triples must be an integer"):
        Policy.from_mapping({"max_triples": 2.0})


def test_unterminated_doctype_is_still_inspected() -> None:
    problem = dtd_problem(b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "f">', 10)
    assert problem == "declares an external DTD or entity (SYSTEM/PUBLIC)"
    assert dtd_problem(b"<!DOCTYPE r", 10) is None


def test_file_that_grows_after_the_size_check_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "a.ttl"
    path.write_text(TTL, encoding="utf-8")
    real = loader.os.fstat

    def small(fd: int) -> object:
        info = real(fd)
        return loader.os.stat_result((info.st_mode, info.st_ino, info.st_dev, 1, 0, 0, 0, 0, 0, 0))

    monkeypatch.setattr(loader.os, "fstat", small)
    assert reject(tmp_path, "a.ttl", TTL, Policy(max_input_bytes=10)) == (
        "SEC001",
        "a.ttl grew beyond the limit of 10 bytes (max_input_bytes)",
    )


def test_term_expansion_bound_is_exact_and_restores_the_original(monkeypatch: pytest.MonkeyPatch) -> None:
    from rdflib.plugins.shared.jsonld.context import Context  # noqa: PLC0415

    def countdown(self: Context, source: object, expr: int, prev: object = None) -> int:
        return expr if expr <= 0 else self._rec_expand(source, expr - 1, expr)  # type: ignore[arg-type,return-value]

    monkeypatch.setattr(Context, "_rec_expand", countdown)
    context = Context()
    with loader.term_expansion_bounded(limit=5):
        assert Context._rec_expand is not countdown  # noqa: SLF001
        assert context._rec_expand({}, 4) == 0  # type: ignore[arg-type]  # noqa: SLF001 -- five nested calls: allowed
        with pytest.raises(RecursionError, match="more than 5 levels"):
            context._rec_expand({}, 5)  # type: ignore[arg-type]  # noqa: SLF001 -- six calls: refused
        assert context._rec_expand({}, 4) == 0  # type: ignore[arg-type]  # noqa: SLF001 -- depth was unwound
    assert Context._rec_expand is countdown  # noqa: SLF001


def test_term_expansion_default_limit_and_restoration_after_an_error() -> None:
    from rdflib.plugins.shared.jsonld.context import Context  # noqa: PLC0415

    original = Context._rec_expand  # noqa: SLF001
    assert loader.MAX_TERM_EXPANSION_DEPTH == 64
    with pytest.raises(KeyError), loader.term_expansion_bounded():
        raise KeyError("boom")
    assert Context._rec_expand is original  # noqa: SLF001


def test_cyclic_jsonld_context_fails_fast(tmp_path: Path) -> None:
    import time  # noqa: PLC0415

    long_value = "http://e/" * 2000
    doc = f'{{"@context": {{"a": "b:{long_value}", "b": "a:y"}}, "a": "x"}}'
    (tmp_path / "c.jsonld").write_text(doc, encoding="utf-8")
    started = time.monotonic()
    with pytest.raises(loader.ParseFailure) as info:
        load_graph(resolve_inputs(["c.jsonld"], tmp_path)[0], Policy(), tmp_path)
    assert info.value.cause_type == "RecursionError"
    assert "nested too deeply" in info.value.detail
    assert time.monotonic() - started < 2


def test_ordinary_prefixed_jsonld_terms_still_expand(tmp_path: Path) -> None:
    doc = '{"@context": {"e": "http://e/", "p": "e:p"}, "@id": "e:a", "p": "x"}'
    (tmp_path / "ok.jsonld").write_text(doc, encoding="utf-8")
    graph = load_graph(resolve_inputs(["ok.jsonld"], tmp_path)[0], Policy(), tmp_path)
    assert len(graph) == 1
