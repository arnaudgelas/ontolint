"""SHACL validation runs with the network disabled, as parsing does (README "Input safety")."""

# ruff: noqa: PLR2004

from __future__ import annotations

import socket
import sys
from importlib.machinery import ModuleSpec
from types import ModuleType

import pytest
from rdflib import Graph

from ontolint import engine
from ontolint.adapters.shacl import ShapesRejected, shacl_issues
from ontolint.models import ExecutionStatus
from ontolint.policy import Policy

DIALLED = "RuntimeError: SHACL validation tried to use the network (connect ('127.0.0.1', 9)); the network is disabled"


def _stub(validate: object) -> ModuleType:
    """A stand-in ``pyshacl`` module (with a spec, so the engine sees pySHACL as installed)."""
    module = ModuleType("pyshacl")
    module.__spec__ = ModuleSpec("pyshacl", None)
    module.validate = validate  # type: ignore[attr-defined]
    return module


def _dialling_validate(*, swallow: bool) -> ModuleType:
    def validate(*_args: object, **_kwargs: object) -> tuple[bool, Graph, None]:
        try:
            socket.create_connection(("127.0.0.1", 9))
        except Exception:
            if not swallow:
                raise
        return True, Graph(), None

    return _stub(validate)


def _shacl001(policy: Policy) -> tuple[ExecutionStatus, str | None]:
    ctx = engine.build_context(Graph(), Graph(), policy)
    (execution,) = engine.execute(ctx, ["SHACL001"]).executions
    return execution.status, execution.detail


@pytest.mark.parametrize("swallow", [True, False], ids=["swallowed", "raised"])
def test_validation_that_dials_out_fails_the_rule(monkeypatch: pytest.MonkeyPatch, swallow: bool) -> None:
    original = socket.socket.connect, socket.create_connection, socket.getaddrinfo
    monkeypatch.setitem(sys.modules, "pyshacl", _dialling_validate(swallow=swallow))
    assert _shacl001(Policy()) == (ExecutionStatus.FAILED, DIALLED)
    assert (socket.socket.connect, socket.create_connection, socket.getaddrinfo) == original


def test_the_guard_is_raised_even_when_pyshacl_reports_conformance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "pyshacl", _dialling_validate(swallow=True))
    with pytest.raises(RuntimeError, match=r"tried to use the network \(connect \('127\.0\.0\.1', 9\)\)"):
        shacl_issues(Graph(), Graph())


def test_name_resolution_is_blocked_too(monkeypatch: pytest.MonkeyPatch) -> None:
    def validate(*_args: object, **_kwargs: object) -> tuple[bool, Graph, None]:
        socket.getaddrinfo("example.org", 80)
        return True, Graph(), None  # pragma: no cover - the guard raises first

    monkeypatch.setitem(sys.modules, "pyshacl", _stub(validate))
    with pytest.raises(RuntimeError) as info:
        shacl_issues(Graph(), Graph())
    assert str(info.value) == (
        "SHACL validation tried to use the network (resolve 'example.org'); the network is disabled"
    )


def test_validation_without_network_use_is_unchanged() -> None:
    assert shacl_issues(Graph(), Graph()) == []


def test_a_refusal_raised_inside_validation_is_passed_on_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    def validate(*_args: object, **_kwargs: object) -> tuple[bool, Graph, None]:
        raise ShapesRejected("shapes graph is odd")

    monkeypatch.setitem(sys.modules, "pyshacl", _stub(validate))
    with pytest.raises(ShapesRejected) as info:
        shacl_issues(Graph(), Graph())
    assert str(info.value) == "shapes graph is odd"
