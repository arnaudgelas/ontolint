"""Test ordering for mutation runs."""

from __future__ import annotations

import pytest

# Run first: they kill the mutants of the ``@dataclass(frozen=True)`` decorators and of the ``compare=False`` fields.
# Every test covers those lines, so a mutation run reaches the killers before its timeout only if they come first
# (docs/mutation-pardons.md).
FIRST = frozenset({"test_value_objects_are_frozen", "test_a_compare_false_field_does_not_take_part_in_equality"})


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Put the frozen-dataclass tests ahead of the rest of the suite.

    A class decorator runs when its module is imported, before any test, so coverage ties it to no
    single test and pytest-gremlins runs the whole suite for its mutant, in collection order, and
    stops at the first failure. Without this, those tests run after most of
    the suite and the mutant times out first. The run is unchanged otherwise: the order of the
    rest is kept, and a passing suite passes in any order.
    """
    items.sort(key=lambda item: getattr(item, "originalname", item.name) not in FIRST)
