"""Helpers shared by the ``tests/test_metamorphic_*.py`` files.

A metamorphic test applies a transformation whose effect on the output is known (none, a renaming, a subset)
and asserts exactly that relation, so it needs no oracle for the findings themselves.  The helpers here lint
graphs and files the way the relations compare them: by ``(rule, severity, focus, message)``, never by report
path, source region or blank-node spelling.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
from collections.abc import Generator, Iterable, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from hypothesis_strategies import RULE_IDS, canonical
from rdflib import Graph, URIRef
from rdflib.namespace import RDF

from ontolint import main
from ontolint.engine import build_context, execute
from ontolint.models import ExecutionStatus, Finding, RuleScope
from ontolint.policy import Policy
from ontolint.rules.specs import RULE_SPECS

type Key = tuple[str, str, str, str]
type Triple = tuple[Any, Any, Any]

# Blank-node foci are content-stable ids (``_:`` and twelve hex digits), so they depend on the IRIs around them.
CONTENT_ID = re.compile(r"_:[0-9a-f]{12}")

SET_LEVEL = tuple(sorted(spec.rule_id for spec in RULE_SPECS if spec.scope is RuleScope.SET))
"""The rules that compare the documents of a run with each other (ONT007, ONT008)."""
INDEPENDENT = ("--ignore", ",".join(SET_LEVEL))
"""CLI arguments that leave the set-level rules out: the relations of file independence hold without them."""


def norm(text: str) -> str:
    """Blank-node blind form of ``text``: hand-made labels and content-stable ids both become ``_:B``."""
    return CONTENT_ID.sub("_:B", canonical(text))


def keys(findings: Iterable[Finding]) -> list[Key]:
    """Order-independent comparison form of findings: sorted ``(rule, severity, focus, message)``."""
    return sorted((f.rule, f.severity, norm(f.focus), norm(f.message)) for f in findings)


def lint_all(graph: Graph, policy: Policy | None = None) -> list[Finding]:
    """Run every rule (opt-in families included) on ``graph`` and return the findings; no rule may fail."""
    result = execute(build_context(graph, None, policy or Policy()), RULE_IDS)
    assert not result.with_status(ExecutionStatus.FAILED), result.with_status(ExecutionStatus.FAILED)
    return list(result.findings)


def document_keys(document: dict[str, Any], path: str | None = None) -> list[Key]:
    """``keys`` of a ``--format json`` report's findings, optionally only those of the report path ``path``."""
    return sorted(
        (f["rule"], f["severity"], norm(f["focus"]), norm(f["message"]))
        for f in document["findings"]
        if path is None or f["path"] == path
    )


@contextlib.contextmanager
def workdir() -> Generator[Path]:
    """A fresh temporary directory that is also the working directory (report paths are relative to it)."""
    with tempfile.TemporaryDirectory() as folder:
        previous = Path.cwd()
        os.chdir(folder)
        try:
            yield Path(folder).resolve()
        finally:
            os.chdir(previous)


def cli(*argv: str, fmt: str = "json") -> tuple[int, str]:
    """Run the real CLI in the working directory with ``--format fmt`` and return its exit code and report text."""
    out = f"report.{fmt}"
    code = main([*argv, "--format", fmt, "--output", out])
    return code, Path(out).read_text(encoding="utf-8")


def cli_json(*argv: str) -> tuple[int, dict[str, Any]]:
    """Run the real CLI with ``--format json`` and return the exit code and the parsed report."""
    code, text = cli(*argv)
    return code, json.loads(text)


def parsable_iri(term: object) -> bool:
    """True for anything but an IRI that ``urllib`` cannot split (rdflib's RDF/XML parser needs that)."""
    if not isinstance(term, URIRef):
        return True
    try:
        urlsplit(str(term))
    except ValueError:
        return False
    return True


def serialisable(triples: Sequence[Triple]) -> list[Triple]:
    """Drop what rdflib's writers are known to mangle, leaving a graph the loader should read back unchanged.

    rdflib's serialisers rewrite malformed ``rdf:first``/``rdf:rest`` structures and drop blank-node self-loops;
    ``urlsplit`` rejects some IRIs.  Those are rdflib limitations (see ``test_properties_loader``), not defects
    of the linter, so such triples are removed up front.  Remaining writer losses are caught by the isomorphism
    check of each test.
    """
    return [
        t for t in triples if t[1] not in (RDF.first, RDF.rest) and t[0] != t[2] and all(parsable_iri(n) for n in t)
    ]
