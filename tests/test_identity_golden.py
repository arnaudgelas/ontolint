"""The baseline identity of every positive rule case, pinned so that a change to a rule's subject is seen in review.

A baseline accepts a finding by its identity (:func:`ontolint.reporting.identity`: rule, focus and subject) or by its
version 1 fingerprint (rule, focus and message).  A release that refines a rule's subject (the subject of one finding
gains a part, or one finding becomes two) changes identities, so only the fingerprint can still accept those
findings, and any message change shipped with it, or a finding split in two, reopens them (issue #10).  So
``tests/golden/identities.json`` records, for every positive rule case that runs on a graph (the cases of
``tests/rule_cases``, each run with its own rule and the case's options), the rule, focus, subject and identity of
each finding, sorted, together with ``IDENTITY_TAG``.

SHACL001's rule cases are probes of the adapter, which no graph case covers, so its subjects are pinned by the
cases of ``SHACL_CASES`` instead, each run through :class:`ontolint.Linter` with SHACL001 alone: one per constraint
family of ``tests/test_shacl_evidence.py`` (value type, cardinality, property pair, logical and SPARQL-based, the
last with ``sh:message`` and a named ``sh:sourceConstraint``), two values of one shape with one ``sh:message``, a
blank property shape and a nested ``sh:node`` result.  Probe cases of the other adapters (SEM001, INPUT001,
TOOL001) and of the CLI front end run outside the graph rules and are not pinned here.

Regenerate it with ``ONTOLINT_UPDATE_GOLDEN=1 uv run pytest tests/test_identity_golden.py``; the tests then compare
the computed identities with the file they have just written.  A new case only needs regenerating.  A changed or
removed entry of an existing case changes the identity of a finding that some baseline accepts: say why in a
"Deliberate identity change" paragraph at the end of this docstring, and give the release an upgrade note that
names the rule.  A pySHACL or rdflib upgrade that changes a SHACL001 subject fails here for the same reason.

The kitchen sink is left out: it changes with every rule, and ``tests/golden/differential.json`` already pins its
fingerprints.  That no two findings of one run share an identity is ``tests/test_subject_contract.py``'s concern.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest
from rdflib import Graph
from rule_cases import load_cases
from rule_harness import graph
from test_shacl_evidence import FAMILIES, NODE_SHAPES, ON_T, PROPERTY, _graphs

from ontolint import Linter
from ontolint.reporting import IDENTITY_TAG, identity

GOLDEN = Path(__file__).parent / "golden" / "identities.json"
UPDATE = os.environ.get("ONTOLINT_UPDATE_GOLDEN") == "1"

type Row = tuple[str, str, tuple[str, ...], str]
type Inputs = tuple[Graph, Graph | None, Mapping[str, Any]]

SHACL_CASES: dict[str, tuple[str, str]] = {family: (data, shapes) for family, (data, shapes, _) in FAMILIES.items()}
SHACL_CASES |= {
    "two values of one shape with one sh:message": (
        'ex:a a ex:T ; ex:age "x", "y" .',
        f'{PROPERTY}age ; sh:datatype xsd:integer ; sh:message "age must be an integer" .',
    ),
    "a blank property shape": ("ex:a a ex:T .", f"{ON_T} sh:property [ sh:path ex:name ; sh:minCount 1 ] ."),
    "a nested sh:node result": ("ex:a a ex:T ; ex:knows ex:b .", NODE_SHAPES),
}


def _graph_cases() -> dict[str, tuple[str, Callable[[], Inputs]]]:
    """Every positive case that runs on a graph, then each of ``SHACL_CASES``, keyed ``RULE:case name``."""
    cases: dict[str, tuple[str, Callable[[], Inputs]]] = {}

    def add(rule_id: str, name: str, inputs: Callable[[], Inputs]) -> None:
        key = f"{rule_id}:{name}"
        assert key not in cases, f"two positive cases of {rule_id} are named {name!r}"
        cases[key] = (rule_id, inputs)

    for rule_id, rule_cases in sorted(load_cases().items()):
        for case in rule_cases.positive:
            if case.probe is None:
                add(
                    rule_id,
                    case.name,
                    lambda case=case: (
                        case.build() if case.build is not None else graph(case.turtle),
                        graph(case.shapes) if case.shapes is not None else None,
                        case.options,
                    ),
                )
    for name, (data, shapes) in SHACL_CASES.items():
        add("SHACL001", name, lambda data=data, shapes=shapes: (*_graphs(data, shapes), {}))
    return cases


CASES = _graph_cases()


def _identities(rule_id: str, inputs: Callable[[], Inputs]) -> list[list[Any]]:
    """``[rule, focus, [subject parts], identity]`` of each finding of a case run with ``rule_id`` alone, sorted."""
    data, shapes, options = inputs()
    findings = Linter(data, shapes, **options).execute([rule_id]).findings
    assert findings, f"{rule_id} found nothing: a positive case must give at least one finding"
    rows: list[Row] = sorted((f.rule, f.focus, f.subject, identity(f)) for f in findings)
    return [[rule, focus, list(subject), ident] for rule, focus, subject, ident in rows]


def _compute() -> dict[str, Any]:
    return {"identity_tag": IDENTITY_TAG, "cases": {key: _identities(*CASES[key]) for key in CASES}}


def _text(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=1, ensure_ascii=False, sort_keys=True) + "\n"


@pytest.fixture(scope="module")
def golden() -> dict[str, Any]:
    """The golden file; under ``ONTOLINT_UPDATE_GOLDEN=1`` first rewritten from the current rules."""
    if UPDATE:
        computed = _compute()
        partial = GOLDEN.with_name(f"{GOLDEN.name}.{os.getpid()}")  # each xdist worker writes the same bytes
        partial.write_text(_text(computed), encoding="utf-8", newline="\n")
        partial.replace(GOLDEN)
        assert json.loads(GOLDEN.read_text(encoding="utf-8")) == computed
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


@pytest.mark.parametrize("key", sorted(CASES))
def test_each_positive_case_keeps_its_identities(key: str, golden: dict[str, Any]) -> None:
    assert _identities(*CASES[key]) == golden["cases"].get(key), (
        f"{key}: identities moved; if deliberate, regenerate with ONTOLINT_UPDATE_GOLDEN=1 and document it"
    )


def test_the_golden_holds_every_positive_case_and_the_identity_tag(golden: dict[str, Any]) -> None:
    assert golden["identity_tag"] == IDENTITY_TAG
    assert sorted(golden["cases"]) == sorted(CASES), "cases changed: regenerate with ONTOLINT_UPDATE_GOLDEN=1"


def test_the_golden_file_is_written_canonically(golden: dict[str, Any]) -> None:
    """Sorted keys, one-space indentation, UTF-8 without escapes and one trailing newline, so diffs stay small."""
    assert GOLDEN.read_bytes().decode("utf-8") == _text(golden)
