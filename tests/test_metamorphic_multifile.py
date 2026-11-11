"""Metamorphic relations of multi-file runs: files are linted independently and the argument order is irrelevant.

README "Several files": each file is linted alone with the same options, results are aggregated, files are ordered
by report path regardless of argument order, and a file's baseline identities do not depend on the other files
(only the version 1 fingerprints hash the report path in a multi-file run).
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

import pytest
from hypothesis import assume, given
from hypothesis_strategies import budget, roundtrip_triple_lists
from hypothesis_strategies import build_graph as build
from metamorphic_support import cli_json, serialisable, workdir

pytestmark = pytest.mark.slow


def without_path(findings: list[dict[str, Any]], path: str) -> list[dict[str, Any]]:
    """The report's findings for ``path`` with the (identical) ``path`` field removed."""
    return [{k: v for k, v in f.items() if k != "path"} for f in findings if f["path"] == path]


@budget(0.25)
@given(roundtrip_triple_lists(), roundtrip_triple_lists())
def test_a_multi_file_run_gives_each_file_the_findings_of_its_own_run(first: list, second: list) -> None:
    """RELATION (file independence): linting ``a.ttl`` and ``b.ttl`` in one run gives, per file, the findings,
    summary and baseline identities of linting each alone; the exit code is the worse of the two; the fingerprints
    differ only because a multi-file run hashes the report path (README "Several files")."""
    graphs = [build(serialisable(first)), build(serialisable(second))]
    assume(all(len(g) for g in graphs))

    with workdir() as root:
        for name, graph in zip(("a.ttl", "b.ttl"), graphs, strict=True):
            (root / name).write_text(graph.serialize(format="turtle"), encoding="utf-8")
        code_a, alone_a = cli_json("a.ttl", "--write-baseline", "alone_a.json")
        code_b, alone_b = cli_json("b.ttl", "--write-baseline", "alone_b.json")
        code, together = cli_json("a.ttl", "b.ttl", "--write-baseline", "together.json")
        base_a, base_b, base = (
            json.loads((root / f"{name}.json").read_text(encoding="utf-8"))
            for name in ("alone_a", "alone_b", "together")
        )

    assert {code_a, code_b, code} <= {0, 1}
    assert code == max(code_a, code_b)
    assert without_path(together["findings"], "a.ttl") == without_path(alone_a["findings"], "a.ttl")
    assert without_path(together["findings"], "b.ttl") == without_path(alone_b["findings"], "b.ttl")
    totals = Counter(alone_a["summary"]) + Counter(alone_b["summary"])
    assert together["summary"] == dict(totals)

    assert base["files"] == ["a.ttl", "b.ttl"]
    for name, alone in (("a.ttl", base_a), ("b.ttl", base_b)):
        assert set(base["identities"].get(name, {})) == set(alone["identities"].get(name, {})), name
    for alone in (base_a, base_b):
        assert set(base["fingerprints"]).isdisjoint(alone["fingerprints"])  # The path is part of the v1 hash.


@budget(0.25)
@given(roundtrip_triple_lists(), roundtrip_triple_lists())
def test_the_order_of_the_files_on_the_command_line_changes_nothing(first: list, second: list) -> None:
    """RELATION (argument order invariance): ``a.ttl b.ttl`` and ``b.ttl a.ttl`` give the same report, byte for
    byte as JSON, since files are ordered by report path."""
    graphs = [build(serialisable(first)), build(serialisable(second))]
    assume(all(len(g) for g in graphs))

    with workdir() as root:
        for name, graph in zip(("a.ttl", "b.ttl"), graphs, strict=True):
            (root / name).write_text(graph.serialize(format="turtle"), encoding="utf-8")
        code_ab, forward = cli_json("a.ttl", "b.ttl")
        code_ba, backward = cli_json("b.ttl", "a.ttl")

    assert code_ba == code_ab
    assert backward == forward
