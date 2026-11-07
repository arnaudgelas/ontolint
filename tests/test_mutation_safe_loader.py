"""Exact messages, boundaries and helper contracts of the safe loader (written to kill mutants)."""

# ruff: noqa: PLR2004

from __future__ import annotations

import socket
from pathlib import Path

import pytest

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


def test_bounded_graph_counts_distinct_triples_only() -> None:
    graph = loader._BoundedGraph(2)  # noqa: SLF001
    from rdflib import Literal, URIRef  # noqa: PLC0415

    s, p = URIRef("http://e/s"), URIRef("http://e/p")
    graph.add((s, p, Literal(1)))
    graph.add((s, p, Literal(1)))
    graph.add((s, p, Literal(1)))
    graph.add((s, p, Literal(2)))
    assert len(graph) == 2
    with pytest.raises(InputRejected, match="more than 2 triples"):
        graph.add((s, p, Literal(3)))


def test_context_and_network_messages(tmp_path: Path) -> None:
    remote = '{"@context": "http://127.0.0.1:9/c.jsonld", "@id": "http://e/a", "http://e/p": "x"}'
    assert reject(tmp_path, "a.jsonld", remote) == (
        "SEC006",
        "a.jsonld references an external JSON-LD context 'http://127.0.0.1:9/c.jsonld'; refused",
    )


def test_network_message_names_the_first_blocked_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def parse(self: object, *args: object, **kwargs: object) -> None:
        socket.getaddrinfo("example.invalid", 80)

    monkeypatch.setattr(loader._BoundedGraph, "parse", parse)  # noqa: SLF001
    assert reject(tmp_path, "a.ttl", TTL) == (
        "SEC013",
        "a.ttl tried to use the network (resolve 'example.invalid'); the network is disabled",
    )


def test_non_network_failures_propagate_unchanged(tmp_path: Path) -> None:
    (tmp_path / "bad.ttl").write_text("not turtle", encoding="utf-8")
    with pytest.raises(Exception) as info:  # noqa: PT011 -- the concrete rdflib type is not part of the contract
        load_graph(resolve_inputs(["bad.ttl"], tmp_path)[0], Policy(), tmp_path)
    assert not isinstance(info.value, InputRejected)


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
    assert [s.rule_id for s in SPECS] == ["SEC001", "SEC002", "SEC006", "SEC009", "SEC010", "SEC011", "SEC013"]
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
