"""The subject contract: every rule says what its findings are about, so identity never needs the message.

A baseline matches a finding by its rule, focus and subject (``Finding.subject``), not by its message, so a
rule that could report two problems about one focus and leaves them the same subject would let one baselined
problem hide the other. Three layers keep that from happening:

* statically, every ``ctx.add`` in ``src/ontolint/rules`` passes ``subject=`` when its message is computed,
  its rule code is not a literal, or its rule code has more than one add site (``subject=()`` is the explicit
  statement "at most one finding per focus");
* on the corpus (every graph case of ``tests/rule_cases`` and every Turtle fixture, all rules selected), no
  two findings of one run share a rule, focus and subject;
* the same over random graphs (Hypothesis).
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis_strategies import budget, roundtrip_triple_lists
from hypothesis_strategies import build_graph as build
from rdflib import Graph
from rule_cases import load_cases
from rule_harness import graph

from ontolint import Linter
from ontolint.models import Finding
from ontolint.rules.registry import default_registry

ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "src" / "ontolint" / "rules"
FIXTURES = ROOT / "tests" / "fixtures"
ALL_RULES = [spec.rule_id for spec in default_registry().all()]


# --- static: every add site states its subject -------------------------------------------------------


def _add_calls(tree: ast.AST) -> Iterator[ast.Call]:
    """``ctx.add(code, focus, message, ...)``: the only ``add`` with three positional arguments in the rules."""
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr == "add" and len(node.args) >= 3:  # noqa: PLR2004 -- code, focus, message
            yield node


def subject_violations(sources: dict[str, str]) -> list[str]:
    """``file:line`` of every add site that must pass ``subject=`` and does not, with the reason."""
    calls = [(name, call) for name, text in sorted(sources.items()) for call in _add_calls(ast.parse(text))]
    sites = Counter(c.args[0].value for _name, c in calls if isinstance(c.args[0], ast.Constant))
    problems: list[str] = []
    for name, call in calls:
        if any(keyword.arg == "subject" for keyword in call.keywords):
            continue
        code, message = call.args[0], call.args[2]
        if not isinstance(code, ast.Constant):
            reason = "its rule code is computed"
        elif not (isinstance(message, ast.Constant) and isinstance(message.value, str)):
            reason = "its message is computed"
        elif sites[code.value] > 1:
            reason = f"{code.value!s} has {sites[code.value]} add sites"
        else:
            continue
        problems.append(f"{name}:{call.lineno}: pass subject= ({reason})")
    return problems


def _rule_sources() -> dict[str, str]:
    return {path.name: path.read_text(encoding="utf-8") for path in sorted(RULES.glob("*.py"))}


def test_every_add_site_that_needs_a_subject_states_one() -> None:
    assert subject_violations(_rule_sources()) == []


def test_the_contract_finds_the_add_sites_of_the_rules() -> None:
    calls = [call for text in _rule_sources().values() for call in _add_calls(ast.parse(text))]
    assert len(calls) > 200  # noqa: PLR2004 -- a broken walker would pass vacuously
    assert all(any(k.arg == "subject" for k in c.keywords) for c in calls if not isinstance(c.args[2], ast.Constant))


@pytest.mark.parametrize(
    ("source", "reason"),
    [
        ('def run(ctx):\n    ctx.add("X001", f, f"m {x}")\n', "its message is computed"),
        ('def run(ctx):\n    ctx.add(code, f, "m")\n', "its rule code is computed"),
        ('def run(ctx):\n    ctx.add("X001", f, "m")\n    ctx.add("X001", g, "n", subject=())\n', "X001 has 2"),
    ],
)
def test_the_contract_names_the_file_line_and_reason(source: str, reason: str) -> None:
    (problem,) = subject_violations({"x.py": source})
    assert problem.startswith("x.py:2: pass subject=")
    assert reason in problem


def test_the_contract_accepts_an_explicit_subject_and_a_lone_constant_message() -> None:
    lone = 'def run(ctx):\n    ctx.add("X001", f, "m")\n    ctx.add("X002", f, f"{m}", subject=())\n'
    assert subject_violations({"x.py": lone}) == []


def test_removing_one_subject_from_a_rule_module_is_caught_with_its_line() -> None:
    source = (RULES / "obo.py").read_text(encoding="utf-8")
    edited = re.sub(r",?\s*subject=\(OWL\.versionIRI, version\),?", "", source, count=1)
    assert edited != source
    (problem,) = subject_violations({"obo.py": edited})
    assert problem.startswith("obo.py:")
    assert problem.endswith("(its message is computed)")


# --- run time: no two findings of one run share an identity -------------------------------------------


def _shared(findings: tuple[Finding, ...]) -> list[tuple[str, str, tuple[str, ...]]]:
    identities = Counter((f.rule, f.focus, f.subject) for f in findings)
    return sorted(key for key, count in identities.items() if count > 1)


def _corpus() -> Iterator[tuple[str, Graph, Graph | None, dict[str, object]]]:
    for rule_id, cases in sorted(load_cases().items()):
        for case in (*cases.positive, *cases.negative):
            if case.probe is not None:
                continue
            data = case.build() if case.build is not None else graph(case.turtle)
            shapes = graph(case.shapes) if case.shapes is not None else None
            yield f"{rule_id}:{case.name}", data, shapes, dict(case.options)
    for path in sorted(FIXTURES.rglob("*.ttl")):
        try:
            yield str(path.relative_to(ROOT)), Graph().parse(path, format="turtle"), None, {}
        except Exception:  # noqa: BLE001,S112 -- fixtures of malformed input are not graphs to lint
            continue


@pytest.mark.slow
def test_no_two_findings_of_a_corpus_run_share_rule_focus_and_subject() -> None:
    shared: dict[str, list[tuple[str, str, tuple[str, ...]]]] = {}
    runs = 0
    for label, data, shapes, options in _corpus():
        try:
            findings = Linter(data, shapes, **options).execute(ALL_RULES).findings  # type: ignore[arg-type]
        except Exception:  # noqa: BLE001,S112 -- hostile cases are checked for crashes elsewhere
            continue
        runs += 1
        if found := _shared(findings):
            shared[label] = found
    assert runs > 1000  # noqa: PLR2004 -- the corpus was found and linted
    assert shared == {}


@pytest.mark.slow
@budget(0.3)
@given(roundtrip_triple_lists())
def test_no_two_findings_of_a_random_graph_share_rule_focus_and_subject(triples: list) -> None:
    findings = Linter(build(triples)).execute(ALL_RULES).findings
    assert _shared(findings) == []
