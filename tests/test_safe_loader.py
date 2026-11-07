"""Safe loader: the network is never used, limits hold, unsafe inputs are reported (not crashed on)."""

# ruff: noqa: PLR2004

from __future__ import annotations

import os
import socket
import stat
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from rdflib import Graph, URIRef

from ontolint import main
from ontolint.loader import InputRejected, load_graph, network_disabled
from ontolint.paths import InputFile, resolve_inputs
from ontolint.policy import DEFAULT_MAX_INPUT_BYTES, DEFAULT_MAX_TRIPLES, Policy

FIXTURES = Path(__file__).parent / "fixtures"
TTL = "@prefix e: <http://e/> .\ne:a e:p 1, 2, 3 .\n"
REMOTE = '{"@context": "http://127.0.0.1:9/ctx.jsonld", "@id": "http://e/a", "http://e/p": "x"}'
RDFXML = (
    '<?xml version="1.0" encoding="{enc}"?>\n{doctype}<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"'
    ' xmlns:e="http://e/"><rdf:Description rdf:about="http://e/a"><e:p>&{entity};</e:p></rdf:Description></rdf:RDF>\n'
)


def item(path: Path, root: Path) -> InputFile:
    return resolve_inputs([path.name], root)[0]


def load(tmp_path: Path, name: str, data: bytes | str, policy: Policy | None = None) -> Graph:
    path = tmp_path / name
    path.write_bytes(data if isinstance(data, bytes) else data.encode())
    return load_graph(item(path, tmp_path), policy or Policy(), tmp_path)


def rejected(tmp_path: Path, name: str, data: bytes | str, policy: Policy | None = None) -> InputRejected:
    with pytest.raises(InputRejected) as info:
        load(tmp_path, name, data, policy)
    return info.value


@pytest.fixture
def no_sockets(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record (and refuse) every connection that reaches the real socket layer, i.e. that escaped the guard."""
    seen: list[str] = []

    def connect(self: socket.socket, address: object, /) -> None:
        seen.append(f"connect {address!r}")
        raise ConnectionRefusedError(address)

    def create_connection(address: object, *args: object, **kwargs: object) -> socket.socket:
        seen.append(f"create_connection {address!r}")
        raise ConnectionRefusedError(address)

    def getaddrinfo(host: object, *args: object, **kwargs: object) -> list[object]:
        seen.append(f"getaddrinfo {host!r}")
        raise socket.gaierror(host)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "create_connection", create_connection)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    return seen


def test_remote_jsonld_context_makes_no_connection(tmp_path: Path, no_sockets: list[str]) -> None:
    error = rejected(tmp_path, "r.jsonld", REMOTE)
    assert error.rule_id == "SEC006"
    assert no_sockets == []


@pytest.mark.filterwarnings("ignore:ConjunctiveGraph is deprecated")
def test_remote_context_without_the_guard_would_have_connected(
    tmp_path: Path, no_sockets: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Proves the fixture detects the original bug: rdflib alone dials out for the context."""
    (tmp_path / "r.jsonld").write_text(REMOTE, encoding="utf-8")
    with pytest.raises(Exception, match="urlopen error"):
        Graph().parse(tmp_path / "r.jsonld")
    assert no_sockets


def test_remote_context_through_the_cli_is_reported_not_crashed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], no_sockets: list[str]
) -> None:
    (tmp_path / "r.jsonld").write_text(REMOTE, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main(["r.jsonld"]) == 2
    assert capsys.readouterr().err.startswith("SEC006: ")
    assert no_sockets == []


def test_relative_and_local_file_contexts_are_refused_too(tmp_path: Path) -> None:
    (tmp_path / "ctx.jsonld").write_text('{"@context": {"p": "http://e/p"}}', encoding="utf-8")
    assert (
        rejected(tmp_path, "a.jsonld", '{"@context": "ctx.jsonld", "@id": "http://e/a", "p": "x"}').rule_id == "SEC006"
    )


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("a.ttl", TTL),
        ("a.nt", "<http://e/a> <http://e/p> <http://e/b> .\n"),
        ("a.jsonld", '{"@context": {"p": "http://e/p"}, "@id": "http://e/a", "p": "x"}'),
        ("a.rdf", RDFXML.format(enc="UTF-8", doctype="", entity="amp")),
        ("noextension", TTL),
    ],
)
def test_ordinary_files_still_parse(tmp_path: Path, name: str, data: str) -> None:
    assert len(load(tmp_path, name, data)) >= 1


def test_relative_iris_resolve_against_the_file_uri(tmp_path: Path) -> None:
    graph = load(tmp_path, "a.ttl", "<a> <p> <b> .")
    assert (
        URIRef((tmp_path / "a").as_uri()),
        URIRef((tmp_path / "p").as_uri()),
        URIRef((tmp_path / "b").as_uri()),
    ) in graph


def test_guard_restores_the_originals_even_after_an_error() -> None:
    before = (socket.socket.connect, socket.socket.connect_ex, socket.create_connection, socket.getaddrinfo)
    with pytest.raises(RuntimeError), network_disabled():
        raise RuntimeError("boom")
    after = (socket.socket.connect, socket.socket.connect_ex, socket.create_connection, socket.getaddrinfo)
    assert after == before


def _dial(method: str) -> object:
    with socket.socket() as sock:
        return getattr(sock, method)(("127.0.0.1", 9))


def test_guard_blocks_and_records_every_network_primitive() -> None:
    with network_disabled() as attempts:
        for call in (
            lambda: socket.create_connection(("127.0.0.1", 9)),
            lambda: socket.getaddrinfo("example.invalid", 80),
            lambda: _dial("connect"),
            lambda: _dial("connect_ex"),
        ):
            with pytest.raises(Exception, match="network access is disabled"):
                call()
    assert len(attempts.network) == 4


def test_policy_limits_have_safe_defaults_and_validation() -> None:
    assert (Policy().max_input_bytes, Policy().max_triples) == (DEFAULT_MAX_INPUT_BYTES, DEFAULT_MAX_TRIPLES)
    assert Policy.from_mapping({"max_input_bytes": 5, "max_triples": 7}).max_triples == 7
    for name in ("max_input_bytes", "max_triples"):
        for bad in (0, -1, 1.5, "9", True):
            with pytest.raises(ValueError, match=name):
                Policy.from_mapping({name: bad})


def test_cli_options_override_the_policy_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "a.ttl").write_text(TTL, encoding="utf-8")
    (tmp_path / "p.json").write_text('{"max_triples": 1}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main(["a.ttl", "--config", "p.json"]) == 2
    assert capsys.readouterr().err.startswith("SEC002: ")
    assert main(["a.ttl", "--config", "p.json", "--max-triples", "3", "--select", "ONT001"]) in (0, 1)


def test_multiple_inputs_name_the_offending_file_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "a.ttl").write_text(TTL, encoding="utf-8")
    (tmp_path / "b.ttl").write_text(TTL * 5, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main(["a.ttl", "b.ttl", "--max-input-bytes", str(len(TTL))]) == 2
    assert capsys.readouterr().err.splitlines() == [
        f"SEC001: b.ttl is {len(TTL * 5)} bytes, more than the limit of {len(TTL)} (max_input_bytes)"
    ]


def test_shapes_file_is_loaded_safely_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], no_sockets: list[str]
) -> None:
    (tmp_path / "a.ttl").write_text(TTL, encoding="utf-8")
    (tmp_path / "s.jsonld").write_text(REMOTE, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main(["a.ttl", "--shapes", "s.jsonld"]) == 2
    assert capsys.readouterr().err.startswith("SEC006: ")
    assert no_sockets == []


# --- RDF/XML DTDs and entities -----------------------------------------------------------------


def test_rdflib_does_not_resolve_external_entities_but_we_refuse_them_anyway(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("SECRET", encoding="utf-8")
    doc = RDFXML.format(
        enc="UTF-8", doctype=f'<!DOCTYPE rdf:RDF [<!ENTITY x SYSTEM "{secret.as_uri()}">]>\n', entity="x"
    )
    (tmp_path / "a.rdf").write_text(doc, encoding="utf-8")
    leaked = [str(o) for _, _, o in Graph().parse(tmp_path / "a.rdf")]
    assert "SECRET" not in leaked  # rdflib itself is safe; ontolint additionally refuses the declaration
    assert rejected(tmp_path, "b.rdf", doc).rule_id == "SEC010"


@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le", "utf-16-be", "utf-32", "utf-32-le", "utf-32-be"])
def test_wide_encodings_cannot_hide_a_doctype(tmp_path: Path, encoding: str) -> None:
    doc = RDFXML.format(
        enc="UTF-8", doctype='<!DOCTYPE rdf:RDF [<!ENTITY x SYSTEM "file:///etc/hostname">]>\n', entity="x"
    )
    assert rejected(tmp_path, "a.rdf", doc.encode(encoding)).rule_id == "SEC010"


def test_internal_entities_comments_and_quoted_words_are_accepted(tmp_path: Path) -> None:
    doctype = (
        "<!-- SYSTEM and PUBLIC in a comment -->\n"
        '<!DOCTYPE rdf:RDF [\n <!ENTITY owl "http://www.w3.org/2002/07/owl#">\n <!ENTITY note "a SYSTEM value">\n]>\n'
    )
    assert len(load(tmp_path, "a.rdf", RDFXML.format(enc="UTF-8", doctype=doctype, entity="note"))) == 1


def test_billion_laughs_is_refused_before_parsing(tmp_path: Path) -> None:
    entities = '<!ENTITY a0 "xxxxxxxxxx">' + "".join(f'<!ENTITY a{i} "{f"&a{i - 1};" * 8}">' for i in range(1, 9))
    doc = RDFXML.format(enc="UTF-8", doctype=f"<!DOCTYPE rdf:RDF [{entities}]>\n", entity="a8")
    error = rejected(tmp_path, "a.rdf", doc)
    assert (error.rule_id, error.message) == ("SEC010", "a.rdf declares entity 'a1' that references another entity")


def test_flat_entity_amplification_is_bounded_by_the_input_limit(tmp_path: Path) -> None:
    doctype = f'<!DOCTYPE rdf:RDF [<!ENTITY big "{"x" * 100}">]>\n'
    doc = RDFXML.format(enc="UTF-8", doctype=doctype, entity="big") + "&big;" * 10
    assert rejected(tmp_path, "a.rdf", doc, Policy(max_input_bytes=1000)).message.startswith(
        "a.rdf uses entities that expand to 1100"
    )
    assert rejected(tmp_path, "b.rdf", doc, Policy(max_input_bytes=1099)).rule_id == "SEC010"


# --- compression, size, triples, paths ---------------------------------------------------------


@pytest.mark.parametrize(
    ("magic", "kind"),
    [
        (b"\x1f\x8b\x08", "gzip"),
        (b"BZh9", "bzip2"),
        (b"\xfd7zXZ\x00", "xz"),
        (b"PK\x03\x04", "zip"),
        (b"\x28\xb5\x2f\xfd", "zstd"),
        (b"7z\xbc\xaf\x27\x1c", "7z"),
    ],
)
def test_compressed_input_is_refused_by_content_not_name(tmp_path: Path, magic: bytes, kind: str) -> None:
    error = rejected(tmp_path, "innocent.ttl", magic + b"\x00" * 20)
    assert (error.rule_id, error.message) == (
        "SEC011",
        f"innocent.ttl is {kind}-compressed; compressed input is refused",
    )


def test_size_limit_boundary(tmp_path: Path) -> None:
    assert len(load(tmp_path, "a.ttl", TTL, Policy(max_input_bytes=len(TTL)))) == 3
    assert rejected(tmp_path, "a.ttl", TTL, Policy(max_input_bytes=len(TTL) - 1)).rule_id == "SEC001"


def test_triple_limit_boundary_and_duplicates_do_not_count(tmp_path: Path) -> None:
    assert len(load(tmp_path, "a.ttl", TTL, Policy(max_triples=3))) == 3
    assert rejected(tmp_path, "a.ttl", TTL, Policy(max_triples=2)).rule_id == "SEC002"
    duplicates = "@prefix e: <http://e/> .\n" + "e:a e:p 1 .\n" * 10
    assert len(load(tmp_path, "d.ttl", duplicates, Policy(max_triples=1))) == 1


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX FIFOs")
def test_fifo_is_refused_without_blocking(tmp_path: Path) -> None:
    fifo = tmp_path / "pipe.ttl"
    os.mkfifo(fifo)
    assert stat.S_ISFIFO(fifo.stat().st_mode)
    with pytest.raises(InputRejected) as info:
        load_graph(item(fifo, tmp_path), Policy(), tmp_path)
    assert (info.value.rule_id, info.value.message) == (
        "SEC009",
        "pipe.ttl is not a regular file (device, pipe or socket)",
    )


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_symlink_escape_and_traversal(tmp_path: Path) -> None:
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "o.ttl").write_text(TTL, encoding="utf-8")
    (root / "ok.ttl").write_text(TTL, encoding="utf-8")
    (root / "inside.ttl").symlink_to("ok.ttl")
    (root / "escape.ttl").symlink_to(outside / "o.ttl")
    assert len(load_graph(resolve_inputs(["inside.ttl"], root)[0], Policy(), root)) == 3
    with pytest.raises(InputRejected, match="symlink to .*o.ttl outside the working dir"):
        load_graph(resolve_inputs(["escape.ttl"], root)[0], Policy(), root)
    traversal = resolve_inputs(["../outside/o.ttl"], root)[0]
    assert traversal.escapes_root
    with pytest.raises(InputRejected, match="escapes the working directory through '..'"):
        load_graph(traversal, Policy(), root)
    assert not resolve_inputs([str(outside / "o.ttl")], root)[0].escapes_root  # explicit absolute path is trusted


def test_missing_file_is_an_ordinary_oserror_for_input001(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_graph(item(tmp_path / "nope.ttl", tmp_path), Policy(), tmp_path)


def test_parse_errors_stay_input001(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "bad.ttl").write_text("this is not turtle", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main(["bad.ttl"]) == 2
    assert capsys.readouterr().err.startswith("INPUT001: RDF input parsing failed: ")


def test_parse_errors_name_the_file_when_several_are_given_and_keep_the_original_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "a.ttl").write_text(TTL, encoding="utf-8")
    (tmp_path / "bad.ttl").write_text("this is not turtle", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main(["a.ttl", "bad.ttl"]) == 2
    line = capsys.readouterr().err.splitlines()[0]
    assert line.startswith("INPUT001: RDF input parsing failed for bad.ttl: BadSyntax: ")
    assert "ParseFailure" not in line


def test_unparseable_shapes_are_input001_not_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "a.ttl").write_text(TTL, encoding="utf-8")
    (tmp_path / "s.ttl").write_text("this is not turtle", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main(["a.ttl", "--shapes", "s.ttl"]) == 2
    line = capsys.readouterr().err.splitlines()[0]
    assert line.startswith("INPUT001: RDF input parsing failed: BadSyntax: ")


def test_shapes_validation_works_with_a_tight_max_triples(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ontology = (FIXTURES / "clean.ttl").read_text(encoding="utf-8")
    shapes = (FIXTURES / "clean_shapes.ttl").read_text(encoding="utf-8")
    (tmp_path / "a.ttl").write_text(ontology, encoding="utf-8")
    (tmp_path / "s.ttl").write_text(shapes, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    limit = max(len(load_graph(item(tmp_path / n, tmp_path), Policy(), tmp_path)) for n in ("a.ttl", "s.ttl"))
    for max_triples in (limit, limit + 1):
        assert main(["a.ttl", "--shapes", "s.ttl", "--select", "SHACL001", "--max-triples", str(max_triples)]) in (0, 1)
        assert "triples" not in capsys.readouterr().err
    assert main(["a.ttl", "--shapes", "s.ttl", "--max-triples", str(limit - 1)]) == 2
    assert capsys.readouterr().err.startswith("SEC002: ")


@pytest.mark.parametrize("option", ["--max-input-bytes", "--max-triples"])
@pytest.mark.parametrize(
    ("value", "message"), [("0", "got 0"), ("-1", "got -1"), ("x", "got 'x'"), ("1.5", "got '1.5'")]
)
def test_cli_loader_limits_must_be_positive_integers(
    capsys: pytest.CaptureFixture[str], option: str, value: str, message: str
) -> None:
    with pytest.raises(SystemExit) as info:
        main(["a.ttl", option, value])
    assert info.value.code == 2
    err = capsys.readouterr().err
    assert f"argument {option}: must be a positive integer" in err
    assert message in err


@pytest.mark.parametrize("option", ["--max-input-bytes", "--max-triples"])
def test_cli_loader_limit_of_one_is_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, option: str) -> None:
    (tmp_path / "a.ttl").write_text("<http://e/a> <http://e/p> <http://e/o> .\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    limit = "41" if option == "--max-input-bytes" else "1"
    assert main(["a.ttl", option, limit, "--select", "ONT001"]) in (0, 1)


def limit_kwargs(name: str, value: object) -> dict[str, Any]:
    return {name: value}


def test_policy_constructor_validates_loader_limits_too() -> None:
    for name in ("max_input_bytes", "max_triples"):
        assert getattr(Policy(**limit_kwargs(name, 1)), name) == 1
        for bad in (0, -1, 1.5, "9", True):
            with pytest.raises(ValueError, match=f"{name} must be"):
                Policy(**limit_kwargs(name, bad))
    with pytest.raises(ValueError, match="max_triples must be at least 1"):
        replace(Policy(), max_triples=0)
    with pytest.raises(ValueError, match="max_input_bytes must be an integer"):
        Policy(max_input_bytes=2.0)  # type: ignore[arg-type]
