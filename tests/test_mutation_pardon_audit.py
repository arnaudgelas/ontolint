"""Mutants the 2026-11-13 pardon audit unpardoned (docs/mutation-pardons.md), and the tests that kill them."""

from __future__ import annotations

import ast
import dataclasses
import signal
import tomllib
from collections.abc import Iterator
from pathlib import Path

import pytest
from rdflib import Graph, URIRef
from rule_harness import BASE, graph

from ontolint import Linter, cli, context, declarations, imports, loader, models, prof, reporting, worker
from ontolint.adapters import shacl
from ontolint.rules import shacl_quality
from ontolint.source_locations import _iri_end, _skip_string, build_source_index

# Value objects handed between pipeline stages, cached or shared with a worker: their immutability is
# a contract (a stage must not change what another reads), not an accident of the decorator.
FROZEN = [
    context.GraphContext,
    imports.Catalog,
    imports.Closure,
    shacl._ValidationJob,
    models.SharedIdentity,
    loader.ImportChoice,
    loader.ImportShadow,
    loader._ParseJob,
    cli.ImportOptions,
    reporting.Origin,
    prof.Validators,
    declarations.Place,
    declarations.Shared,
    declarations._Facts,
]


@pytest.mark.parametrize("cls", FROZEN, ids=lambda cls: cls.__qualname__)
def test_value_objects_are_frozen(cls: type) -> None:
    assert dataclasses.is_dataclass(cls)
    assert cls.__dataclass_params__.frozen  # type: ignore[attr-defined]


ROOT = Path(__file__).resolve().parents[1]


def _scope_files() -> list[Path]:
    """The files the mutation run covers: ``[tool.pytest-gremlins] paths`` of ``pyproject.toml``."""
    paths = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["pytest-gremlins"]["paths"]
    return sorted(f for p in paths for f in ((ROOT / p).rglob("*.py") if (ROOT / p).is_dir() else [ROOT / p]))


def _dataclasses_in(path: Path) -> list[tuple[str, ast.expr]]:
    """Each ``dataclass`` decorator of ``path`` with its class's qualified name, nested and local classes too."""
    found: list[tuple[str, ast.expr]] = []

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                qualname = prefix + child.name
                found.extend((qualname, d) for d in child.decorator_list if _is_dataclass(d))
                visit(child, qualname + ".")
            elif isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                visit(child, f"{prefix}{child.name}.<locals>.")

    def _is_dataclass(decorator: ast.expr) -> bool:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        return (target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")) == "dataclass"

    visit(ast.parse(path.read_text(encoding="utf-8")), "")
    return found


def _module_name(path: Path) -> str:
    return ".".join(path.relative_to(ROOT / "src").with_suffix("").parts)


def _frozen_by_decorator() -> set[tuple[str, str]]:
    """(module, qualified name) of every ``@dataclass(frozen=True)`` class in the mutation scope."""
    return {
        (_module_name(path), qualname)
        for path in _scope_files()
        for qualname, decorator in _dataclasses_in(path)
        if isinstance(decorator, ast.Call)
        and any(k.arg == "frozen" and getattr(k.value, "value", None) is True for k in decorator.keywords)
    }


def test_every_frozen_dataclass_of_the_mutation_scope_is_listed_in_the_frozen_test() -> None:
    """A ``frozen=True`` decorator the list does not name has a mutant no test kills quickly: in a mutation run it
    selects the whole suite and times out as an error (issues #71, #151, #187).  The list is the registry, so a
    new frozen dataclass is a failing test here until it is added to ``FROZEN``."""
    listed = {(cls.__module__, cls.__qualname__) for cls in FROZEN}
    found = _frozen_by_decorator()

    assert not {q for _, q in found if "<locals>" in q}, "a frozen dataclass defined in a function cannot be listed"
    assert sorted(found - listed) == []
    # The scan reads the scope: one that found nothing would make the check above pass for nothing.
    assert ("ontolint.reporting", "Origin") in found


class _Closed:
    """A pipe whose worker died before it was ready."""

    def poll(self, timeout: float) -> bool:
        raise EOFError


def test_a_pipe_closed_before_ready_is_not_ready() -> None:
    assert worker._ready(_Closed(), 1.0) is False


def test_an_iri_without_its_closing_bracket_has_no_end() -> None:
    assert _iri_end("<https://example.test/a", 1) is None
    assert _iri_end("<a\\", 1) is None


def test_an_unclosed_string_runs_to_the_end_of_the_text() -> None:
    assert _skip_string('"abc', 0) == len('"abc')
    assert _skip_string('"""abc"', 0) == len('"""abc"')


@pytest.fixture
def deadline() -> Iterator[None]:
    """Fail fast (instead of hanging) when a mutant makes a scan non-terminating."""

    def boom(signum: int, frame: object) -> None:
        raise TimeoutError("scan did not terminate")

    old = signal.signal(signal.SIGALRM, boom)
    signal.alarm(5)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def test_adjacent_iris_are_each_located(deadline: None) -> None:
    # Turtle needs no space between terms; scanning an IRI from the ">" before it never advances.
    data = "<https://example.test/a><https://example.test/p><https://example.test/b>.\n"
    parsed = Graph().parse(data=data, format="turtle")
    index = build_source_index(data.encode(), "turtle", "https://example.test/", parsed)
    found = {str(node): (where.line, where.column) for node, where in index.locations.items()}
    assert found == {
        "https://example.test/a": (1, 1),
        "https://example.test/p": (1, 25),
        "https://example.test/b": (1, 49),
    }


def test_a_class_equivalent_to_itself_on_a_cycle_is_not_cls021() -> None:
    # A is its own ancestor on the cycle; `A owl:equivalentClass A` says nothing about a second class.
    turtle = (
        "ex:A a owl:Class ; rdfs:subClassOf ex:B ; owl:equivalentClass ex:A . ex:B a owl:Class ; rdfs:subClassOf ex:A ."
    )
    assert Linter(graph(turtle)).execute(["CLS021"]).findings == ()


def test_a_subject_with_no_shacl_predicate_is_not_a_shape() -> None:
    shapes = graph(
        "@prefix sh: <http://www.w3.org/ns/shacl#> .\n"
        "ex:S a sh:NodeShape ; sh:targetClass ex:A .\n"
        'ex:Doc rdfs:label "documentation" ; ex:p ex:q .'
    )
    assert shacl_quality._shapes(shapes) == [URIRef(BASE + "S")]
