"""The SHACL adapter names the missing optional dependency instead of crashing with an ImportError."""

from __future__ import annotations

import sys

import pytest
from rule_harness import graph

from ontolint.adapters.shacl import shacl_issues


def test_missing_pyshacl_is_a_clear_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "pyshacl", None)  # `import pyshacl` now raises ImportError

    with pytest.raises(RuntimeError, match=r"pySHACL is needed for --shapes: pip install pyshacl") as info:
        shacl_issues(graph(), graph())

    assert info.value.__suppress_context__  # the user sees the advice, not an import traceback
