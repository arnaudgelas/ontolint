"""Validate every shape of SARIF report against the vendored OASIS SARIF 2.1.0 schema.

Consumers (GitHub code scanning, IDE viewers) reject a document that breaks the schema, and the
shapes that break are the unusual ones: no results, many files, notifications for rules that did
not run, findings without a region.  Each case below renders one of those shapes.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from jsonschema.validators import validator_for

from ontolint.cli import main
from ontolint.models import ExecutionStatus, Finding, RuleExecution
from ontolint.reporting import FileReport, Location, RunReport, to_sarif_report

SCHEMA = Path(__file__).parent / "schemas" / "sarif-schema-2.1.0.json"
SCHEMA_SHA256 = "c3b4bb2d6093897483348925aaa73af03b3e3f4bd4ca38cef26dcb4212a2682e"  # see schemas/README.md

FINDING = Finding("ONT001", "warning", "https://example.test/A", "Missing label.", "Add a label.")
BLANK = Finding("ONT001", "warning", "_:b0", "Missing label.", "Add a label.")
OWL = "http://www.w3.org/2002/07/owl#"
SMELLY_TTL = f"<https://example.test/A> a <{OWL}Class> .\n[] a <{OWL}Class> .\n"
CLEAN_TTL = f'<https://example.test/o> a <{OWL}Ontology> ;\n <http://www.w3.org/2000/01/rdf-schema#label> "O"@en .\n'


@pytest.fixture(scope="module")
def validate() -> Callable[[dict[str, Any]], None]:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = validator_for(schema)
    validator.check_schema(schema)
    return validator(schema).validate


def test_the_vendored_schema_is_the_recorded_oasis_file() -> None:
    assert hashlib.sha256(SCHEMA.read_bytes()).hexdigest() == SCHEMA_SHA256


def _run(**files: FileReport) -> RunReport:
    return RunReport(tuple(files.values()))


CONSTRUCTED = {
    "no-files": RunReport(()),
    "no-results": _run(a=FileReport("a.ttl", "file:///a.ttl", ())),
    "result-with-line-and-column": _run(
        a=FileReport("a.ttl", "file:///a.ttl", (FINDING,), locations={FINDING: Location(2, 1)})
    ),
    "result-with-line-only": _run(a=FileReport("a.ttl", "file:///a.ttl", (FINDING,), locations={FINDING: Location(2)})),
    "result-without-region": _run(a=FileReport("a.ttl", "file:///a.ttl", (FINDING,))),
    "blank-node-focus": _run(a=FileReport("a.ttl", "file:///a.ttl", (BLANK,))),
    "every-execution-status": _run(
        a=FileReport(
            "a.ttl",
            "file:///a.ttl",
            (),
            tuple(
                RuleExecution(f"ONT00{i}", status, "" if status is ExecutionStatus.EXECUTED else "because")
                for i, status in enumerate(ExecutionStatus, start=1)
            ),
        )
    ),
    "regions-unavailable": _run(
        a=FileReport("a.ttl", "file:///a.ttl", (FINDING,), location_problem="RuntimeError: locator bug")
    ),
    "several-files": _run(
        a=FileReport("a.ttl", "file:///a.ttl", (FINDING,), locations={FINDING: Location(1, 1)}),
        b=FileReport("b.ttl", "file:///b.ttl", ()),
    ),
}


@pytest.mark.parametrize("report", CONSTRUCTED.values(), ids=CONSTRUCTED.keys())
@pytest.mark.parametrize("exit_status", [None, 0, 2])
def test_every_report_shape_matches_the_schema(
    validate: Callable[[dict[str, Any]], None], report: RunReport, exit_status: int | None
) -> None:
    validate(to_sarif_report(report, exit_status))


def _cli_sarif(tmp_path: Path, *args: str) -> dict[str, Any]:
    out = tmp_path / "report.sarif"
    main([*args, "--format", "sarif", "--fail-on", "never", "--output", str(out)])
    return json.loads(out.read_text(encoding="utf-8"))


def _write(tmp_path: Path, name: str, text: str) -> str:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_cli_output_for_findings_regions_and_blank_nodes_matches_the_schema(
    tmp_path: Path, validate: Callable[[dict[str, Any]], None]
) -> None:
    sarif = _cli_sarif(tmp_path, _write(tmp_path, "a.ttl", SMELLY_TTL))
    assert sarif["runs"][0]["results"]
    validate(sarif)


def test_cli_output_for_a_clean_file_and_several_formats_matches_the_schema(
    tmp_path: Path, validate: Callable[[dict[str, Any]], None]
) -> None:
    jsonld = '{"@id": "https://example.test/B", "@type": "' + OWL + 'Class"}'
    rdfxml = (
        '<?xml version="1.0"?>\n<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
        f'xmlns:owl="{OWL}"><owl:Class rdf:about="https://example.test/C"/></rdf:RDF>\n'
    )
    files = [
        _write(tmp_path, "clean.ttl", CLEAN_TTL),
        _write(tmp_path, "b.jsonld", jsonld),
        _write(tmp_path, "c.rdf", rdfxml),
        _write(tmp_path, "d.nt", f"<https://example.test/D> <{OWL}sameAs> <https://example.test/D> .\n"),
    ]
    sarif = _cli_sarif(tmp_path, *files)
    assert (
        len({r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] for r in sarif["runs"][0]["results"]}) > 1
    )
    validate(sarif)


def test_cli_output_after_a_baseline_and_with_skipped_rules_matches_the_schema(
    tmp_path: Path, validate: Callable[[dict[str, Any]], None]
) -> None:
    source = _write(tmp_path, "a.ttl", SMELLY_TTL)
    baseline = tmp_path / "baseline.json"
    main([source, "--write-baseline", str(baseline), "--fail-on", "never", "--output", str(tmp_path / "x.txt")])
    sarif = _cli_sarif(tmp_path, source, "--baseline", str(baseline), "--ignore", "LEX")
    assert sarif["runs"][0]["results"] == []
    assert sarif["runs"][0]["invocations"][0]["toolExecutionNotifications"]
    validate(sarif)


def test_cli_output_naming_named_graphs_and_modules_matches_the_schema(
    tmp_path: Path, validate: Callable[[dict[str, Any]], None]
) -> None:
    dataset = Path(__file__).parent / "fixtures" / "datasets" / "one_term_two_graphs.trig"
    sarif = _cli_sarif(tmp_path, str(dataset), "--module-by", "namespace")
    assert all(r["properties"]["graphs"] for r in sarif["runs"][0]["results"])
    validate(sarif)
