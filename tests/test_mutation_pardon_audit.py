"""Mutants the 2026-11-13 pardon audit unpardoned (docs/mutation-pardons.md), and the tests that kill them."""

from __future__ import annotations

import dataclasses
import signal
from collections.abc import Iterator

import pytest
from rdflib import Graph, URIRef
from rule_harness import BASE, graph

from ontolint import Linter, cli, declarations, imports, loader, models, prof, reporting, worker
from ontolint.adapters import shacl
from ontolint.rules import shacl_quality
from ontolint.source_locations import _iri_end, _skip_string, build_source_index

# Value objects handed between pipeline stages, cached or shared with a worker: their immutability is
# a contract (a stage must not change what another reads), not an accident of the decorator.
FROZEN = [
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
