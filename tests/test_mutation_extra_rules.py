"""Targeted tests for the SEC004 owner choice (safety rules)."""

from __future__ import annotations

from typing import Any

from rdflib import BNode, Graph, URIRef
from rule_cases.safety import bnode_chain, long_list
from rule_harness import BASE

from ontolint import Linter
from ontolint.models import ExecutionStatus, Finding
from ontolint.rules.support import stable_blank_id


def _run(rule: str, data: Graph, **options: Any) -> list[Finding]:
    result = Linter(data, None, **options).execute([rule])
    assert {x.status for x in result.executions} == {ExecutionStatus.EXECUTED}, result.executions
    return list(result.findings)


def _ex(name: str) -> URIRef:
    return URIRef(BASE + name)


def test_sec004_several_iri_subjects_focus_the_lexically_least_one() -> None:
    for names in (("a", "m", "z"), ("z", "m", "a"), ("m", "z", "a"), ("m", "a", "z")):
        for build in (bnode_chain, long_list):
            data = build(101 if build is bnode_chain else 5001)
            head = next(iter(data.objects(_ex("a"), _ex("p"))))
            data.remove((_ex("a"), _ex("p"), head))
            for name in names:
                data.add((_ex(name), _ex("p"), head))
                data.add((_ex(name), _ex("q"), head))  # same subject twice
            assert [f.focus for f in _run("SEC004", data)] == [str(_ex("a"))]


def test_sec004_blank_subject_referring_to_a_list_head_is_not_its_owner() -> None:
    data = long_list(5001)
    head = next(iter(data.objects(_ex("a"), _ex("p"))))
    data.remove((_ex("a"), _ex("p"), head))
    data.add((BNode("zzz"), _ex("p"), head))
    assert [f.focus for f in _run("SEC004", data)] == [stable_blank_id(data, head)]
