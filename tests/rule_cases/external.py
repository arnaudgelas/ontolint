"""Cases for rules emitted by adapters or the CLI front end rather than by a graph rule module."""

from __future__ import annotations

import contextlib
import io
import subprocess
import tempfile
from collections.abc import Callable, Collection
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from rule_harness import graph, probed, rule_cases

from ontolint import main
from ontolint.adapters.robot import robot_profile_issues
from ontolint.adapters.shacl import shacl_issues

ROBOT_REPORT = (
    "OWL 2 DL Profile Report: Ontology and imports closure NOT in profile. The following violations are present:\n"
    "Use of undeclared class: <http://e/C> [SubClassOf(<http://e/A> <http://e/C>)]"
)

FIXTURES = Path(__file__).parents[1] / "fixtures"


def _cli_codes(*argv: str) -> Callable[[], Collection[str]]:
    """Run the CLI and return the rule-id prefixes of the diagnostics it printed to stderr."""

    def run() -> Collection[str]:
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            main(list(argv))
        return {
            line.split(":", 1)[0] for line in err.getvalue().splitlines() if line.startswith(("INPUT001:", "TOOL001:"))
        }

    return run


def _broken_input() -> Collection[str]:
    return _cli_codes(str(FIXTURES / "broken.ttl"))()


def _shacl(data: str, shapes: str) -> Callable[[], Collection[str]]:
    return lambda: {f.rule for f in shacl_issues(graph(data), graph(shapes))}


def _robot(returncode: int) -> Callable[[], Collection[str]]:
    def run() -> Collection[str]:
        def fake(command: list[str], **_kwargs: object) -> SimpleNamespace:
            output = next(v for v in command if v.endswith(":/output")).removesuffix(":/output")
            Path(output, "profile.txt").write_text(
                ROBOT_REPORT,
                encoding="utf-8",
            )
            return SimpleNamespace(returncode=returncode, stderr="", stdout="")

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(subprocess, "run", fake):
            ontology = Path(tmp, "o.owl")
            ontology.write_text("<rdf:RDF/>", encoding="utf-8")
            return {f.rule for f in robot_profile_issues(ontology, "DL", "image", 30)}

    return run


_SHAPES = "ex:S a sh:NodeShape ; sh:targetClass ex:A ; sh:property [ sh:path ex:p ; sh:minCount 1 ] ."

CASES = {
    "SHACL001": rule_cases(
        [probed("constraint violated", _shacl("ex:i a ex:A .", _SHAPES))],
        [probed("data conforms", _shacl("ex:i a ex:A ; ex:p 1 .", _SHAPES))],
    ),
    "SEM001": rule_cases(
        [probed("ROBOT reports a violation", _robot(1))],
        [probed("ROBOT accepts the ontology", _robot(0))],
    ),
    "INPUT001": rule_cases(
        [probed("unparsable RDF", _broken_input)],
        [probed("parsable RDF", _cli_codes(str(FIXTURES / "clean.ttl")))],
    ),
    "TOOL001": rule_cases(
        [probed("unknown selector", _cli_codes(str(FIXTURES / "clean.ttl"), "--select", "NOPE999"))],
        [probed("valid selector", _cli_codes(str(FIXTURES / "clean.ttl"), "--select", "ONT001"))],
    ),
}
