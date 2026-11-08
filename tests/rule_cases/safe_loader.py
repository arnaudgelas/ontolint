"""Cases for the safe-loader rules (SEC001, SEC002, SEC003, SEC006, SEC009, SEC010, SEC011, SEC013, SEC015).

Each probe writes the input to a temporary directory, runs the CLI there and returns the rule ids it
printed to stderr.
"""

from __future__ import annotations

import contextlib
import gzip
import io
import os
import socket
import tempfile
from collections.abc import Callable, Collection
from pathlib import Path
from unittest import mock

from rdflib import Graph
from rule_harness import probed, rule_cases

from ontolint import main

TTL = "@prefix e: <http://e/> .\ne:a e:p 1, 2, 3, 4 .\n"
JSONLD_REMOTE = '{"@context": "http://127.0.0.1:9/ctx.jsonld", "@id": "http://e/a", "http://e/p": "x"}'
JSONLD_INLINE = '{"@context": {"p": "http://e/p"}, "@id": "http://e/a", "p": "x"}'
RDFXML = (
    '<?xml version="1.0"?>\n{doctype}<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"'
    ' xmlns:e="http://e/"><rdf:Description rdf:about="http://e/a"><e:p>x</e:p></rdf:Description></rdf:RDF>\n'
)


def _closure_codes(*options: str) -> Collection[str]:
    """Probe: an umbrella (2 triples) importing a module (3 triples) through a file IRI, with ``--follow-imports``.

    Each file is within ``--max-triples 4``; the closure of 5 triples is not.
    """
    err = io.StringIO()
    with tempfile.TemporaryDirectory() as tmp, contextlib.chdir(tmp):
        module = Path(tmp, "module.ttl").resolve()
        module.write_text(
            "<https://e.test/m> a <http://www.w3.org/2002/07/owl#Ontology> ."
            " <https://e.test/a> a <https://e.test/K> . <https://e.test/b> a <https://e.test/K> ."
        )
        Path("umbrella.ttl").write_text(
            "<https://e.test/u> a <http://www.w3.org/2002/07/owl#Ontology> ;"
            f" <http://www.w3.org/2002/07/owl#imports> <{module.as_uri()}> ."
        )
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            main(["umbrella.ttl", "--follow-imports", "--select", "ONT001", *options])
    return {line.split(":", 1)[0] for line in err.getvalue().splitlines() if line[:3] in {"SEC", "INP"}}


def cli_codes(
    name: str, content: bytes | str, *options: str, link_to: str | None = None, argument: str | None = None
) -> Callable[[], Collection[str]]:
    """Probe: lint ``name`` (or a symlink to ``link_to``) from a scratch directory; return printed SEC/INPUT ids."""

    def run() -> Collection[str]:
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.chdir(tmp):
            work = Path("work")
            work.mkdir()
            os.chdir(work)
            if link_to is None:
                Path(name).write_bytes(content if isinstance(content, bytes) else content.encode())
            else:
                Path(name).symlink_to(link_to)
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                main([argument or name, "--select", "ONT001", *options])
        return {line.split(":", 1)[0] for line in err.getvalue().splitlines() if line[:3] in {"SEC", "INP"}}

    return run


def _big_turtle() -> str:
    """About 125k triples: seconds of parsing, far beyond a 50 ms budget on any machine."""
    rows = [f'e:s{i} e:p "v{i}" ; e:q e:o{i % 50} ; e:r {i} ; e:t [ e:u "x" ] .' for i in range(25000)]
    return "@prefix e: <http://e/> .\n" + "\n".join(rows) + "\n"


def _outside_symlink() -> Collection[str]:
    with tempfile.TemporaryDirectory() as outside:
        target = Path(outside) / "secret.ttl"
        target.write_text(TTL, encoding="utf-8")
        return cli_codes("link.ttl", "", link_to=str(target))()


def _inside_symlink() -> Collection[str]:
    err = io.StringIO()
    with tempfile.TemporaryDirectory() as tmp, contextlib.chdir(tmp):
        Path("real.ttl").write_text(TTL, encoding="utf-8")
        Path("link.ttl").symlink_to("real.ttl")
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            main(["link.ttl", "--select", "ONT001"])
    return {line.split(":", 1)[0] for line in err.getvalue().splitlines() if line[:3] in {"SEC", "INP"}}


def _network_attempt(swallow: bool) -> Collection[str]:
    """A parser that dials out (and optionally hides the failure) must still produce SEC013."""

    def parse(self: object, *args: object, **kwargs: object) -> None:
        try:
            socket.create_connection(("127.0.0.1", 9))
        except Exception:
            if not swallow:
                raise

    with mock.patch.object(Graph, "parse", parse):
        return cli_codes("a.ttl", TTL)()


CASES = {
    "SEC001": rule_cases(
        [probed("one byte over the limit", cli_codes("a.ttl", TTL, "--max-input-bytes", str(len(TTL) - 1)))],
        [probed("exactly at the limit", cli_codes("a.ttl", TTL, "--max-input-bytes", str(len(TTL))))],
    ),
    "SEC002": rule_cases(
        [probed("four triples with a limit of three", cli_codes("a.ttl", TTL, "--max-triples", "3"))],
        [probed("four triples with a limit of four", cli_codes("a.ttl", TTL, "--max-triples", "4"))],
    ),
    "SEC003": rule_cases(
        [
            probed(
                "125k triples with a 50 ms budget",
                cli_codes("a.ttl", _big_turtle(), "--max-parse-seconds", "0.05"),
            )
        ],
        [
            probed("small input with a generous budget", cli_codes("a.ttl", TTL, "--max-parse-seconds", "120")),
            probed("no budget configured", cli_codes("a.ttl", TTL)),
        ],
    ),
    "SEC006": rule_cases(
        [probed("remote @context", cli_codes("a.jsonld", JSONLD_REMOTE))],
        [probed("inline @context", cli_codes("a.jsonld", JSONLD_INLINE))],
    ),
    "SEC009": rule_cases(
        [
            probed("symlink leaving the directory", _outside_symlink),
            probed("relative path climbing out", cli_codes("a.ttl", TTL, argument="../work/../../a.ttl")),
        ],
        [
            probed("symlink inside the directory", _inside_symlink),
            probed("relative path staying inside", cli_codes("a.ttl", TTL, argument="../work/a.ttl")),
        ],
    ),
    "SEC010": rule_cases(
        [
            probed(
                "external entity",
                cli_codes(
                    "a.rdf",
                    RDFXML.format(doctype='<!DOCTYPE rdf:RDF [<!ENTITY x SYSTEM "file:///etc/hostname">]>\n'),
                ),
            ),
            probed(
                "external DTD",
                cli_codes("a.owl", RDFXML.format(doctype='<!DOCTYPE rdf:RDF PUBLIC "-//X//EN" "http://e/x.dtd">\n')),
            ),
        ],
        [
            probed("no DOCTYPE", cli_codes("a.rdf", RDFXML.format(doctype=""))),
            probed(
                "internal entity only",
                cli_codes("a.rdf", RDFXML.format(doctype='<!DOCTYPE rdf:RDF [<!ENTITY owl "http://e/owl#">]>\n')),
            ),
        ],
    ),
    "SEC011": rule_cases(
        [probed("gzip input", cli_codes("a.ttl.gz", gzip.compress(TTL.encode())))],
        [probed("plain input", cli_codes("a.ttl", TTL))],
    ),
    "SEC015": rule_cases(
        [probed("closure above max_triples", lambda: _closure_codes("--max-triples", "4"))],
        [probed("closure within max_triples", lambda: _closure_codes("--max-triples", "5"))],
    ),
    "SEC013": rule_cases(
        [
            probed("parser dials out", lambda: _network_attempt(False)),
            probed("failure is swallowed", lambda: _network_attempt(True)),
        ],
        [probed("ordinary parse", cli_codes("a.ttl", TTL))],
    ),
}
