"""The Jena behaviour behind the severities of SHQ008, SHQ011 and SHQ015, as committed evidence (issue #207).

``tests/fixtures/jena_shacl/cases.json`` records, for each one-property shapes graph, what Apache Jena 4.10.0's
``shacl validate`` does and what ontolint reports.  Without Java the second half is checked; with ``ONTOLINT_JENA_HOME``
set (``jena.yml``, weekly) Jena is run on its verified jars and must still do what is recorded.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from jena_support import run_jena
from rdflib import Graph, Literal
from rdflib.namespace import SH

from ontolint import Linter

FIXTURES = Path(__file__).parent / "fixtures" / "jena_shacl"
RECORD = json.loads((FIXTURES / "cases.json").read_text(encoding="utf-8"))
CASES: list[dict[str, Any]] = RECORD["cases"]
RULES = ["SHQ008", "SHQ011", "SHQ015"]
OUTCOMES = {"conforms", "violations", "error"}


def _ids() -> list[str]:
    return [case["file"].removesuffix(".ttl") for case in CASES]


def test_every_fixture_is_recorded_and_every_record_has_its_fixture() -> None:
    files = sorted(p.name for p in FIXTURES.glob("*.ttl"))

    assert files == sorted(case["file"] for case in CASES)
    assert len(set(files)) == len(files)


def test_each_record_says_what_jena_did_in_a_known_vocabulary() -> None:
    for case in CASES:
        jena = case["jena"]
        assert jena["outcome"] in OUTCOMES, case["file"]
        assert isinstance(jena["exit"], int)
        assert ("message" in jena) == (jena["outcome"] == "error"), case["file"]


def test_the_record_covers_each_rule_and_has_a_control_that_jena_reports_a_violation() -> None:
    reported = {rule for case in CASES for rule, _severity in case["ontolint"]}

    assert reported == set(RULES)
    assert any(case["jena"]["outcome"] == "violations" for case in CASES)


@pytest.mark.parametrize("case", CASES, ids=_ids())
def test_ontolint_reports_what_the_record_says_for_the_same_graph(case: dict[str, Any]) -> None:
    shapes = Graph().parse(FIXTURES / case["file"])
    found = Linter(Graph(), shapes=shapes).execute(RULES)

    assert sorted([f.rule, f.severity] for f in found.findings) == sorted(case["ontolint"])


@pytest.mark.skipif("ONTOLINT_JENA_HOME" not in os.environ, reason="set ONTOLINT_JENA_HOME to an Apache Jena 4.10.0")
@pytest.mark.parametrize("case", CASES, ids=_ids())
def test_jena_still_does_what_the_record_says(case: dict[str, Any]) -> None:
    home = Path(os.environ["ONTOLINT_JENA_HOME"])
    path = str(FIXTURES / case["file"])
    done = run_jena(home, "shacl.shacl", "validate", "--shapes", path, "--data", path, check=False)
    expected = case["jena"]

    assert done.returncode == expected["exit"], done.stderr
    if expected["outcome"] == "error":
        assert done.stdout.strip() == "", "an error writes no report"
        assert expected["message"] in done.stderr
        return
    report = Graph().parse(data=done.stdout, format="turtle")  # the report as RDF, not as Jena's current spacing
    assert (None, SH.conforms, Literal(expected["outcome"] == "conforms")) in report
    assert (None, SH.conforms, Literal(expected["outcome"] != "conforms")) not in report
    assert len(list(report.subjects(SH.resultSeverity, SH.Violation))) == (expected["outcome"] == "violations")
