"""Test ordering for mutation runs."""

from __future__ import annotations

import pytest

# Run first: it kills the mutants of the ``@dataclass(frozen=True)`` decorators (docs/mutation-pardons.md).
FIRST = "test_value_objects_are_frozen"


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Put the frozen-dataclass test ahead of the rest of the suite.

    A class decorator runs when its module is imported, before any test, so coverage ties it to no
    single test and pytest-gremlins runs the whole suite for its mutant, in collection order, and
    stops at the first failure. Without this, ``test_value_objects_are_frozen`` runs after most of
    the suite and the mutant times out first. The run is unchanged otherwise: the order of the
    rest is kept, and a passing suite passes in any order.
    """
    items.sort(key=lambda item: getattr(item, "originalname", item.name) != FIRST)
