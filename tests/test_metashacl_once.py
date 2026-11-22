"""The shapes graph is meta-validated once (#97): one SHACL-SHACL run on every path, and the verdict is pySHACL's.

``pyshacl.validate(meta_shacl=True)`` meta-validates the shapes graph and raises with text only, so reading the results
used to take a second run: the failure path cost twice a conforming one.  SHACL001 now calls ``meta_validate``
itself, once, before ``validate(meta_shacl=False)``.  These tests pin that the call happens once, that it judges the
same graphs as ``meta_shacl=True`` does (a differential test over a small corpus, evidence for the pySHACL series
pyproject allows and not a proof for SHACL-AF, imports or later releases), that the private entry point it relies on
is still there, and the support policy: pySHACL is bounded to the verified series, and only a missing or re-signed
``meta_validate`` falls back to ``meta_shacl=True``.
"""

# ruff: noqa: SLF001

from __future__ import annotations

import inspect
import logging
from typing import Any

import pyshacl
import pytest
from pyshacl import entrypoints
from pyshacl.errors import ReportableRuntimeError
from rdflib import Graph

from ontolint.adapters import shacl
from ontolint.adapters.shacl import ShapesNotWellFormed, shacl_issues

PREFIXES = (
    "@prefix : <https://e.test/#> .\n@prefix sh: <http://www.w3.org/ns/shacl#> .\n"
    "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n"
)
DATA = PREFIXES + ":a a :C .\n"
WELL_FORMED = PREFIXES + ":S a sh:NodeShape ; sh:targetClass :C ; sh:property [ sh:path :p ; sh:minCount 1 ] .\n"
ILL_FORMED = PREFIXES + ":S a sh:NodeShape ; sh:property [ sh:minCount 1 ] .\n"
METASHACL_TEXT = "SHACL File does not validate against the SHACL Shapes SHACL (MetaSHACL) file."
CORPUS = {
    "well formed": WELL_FORMED,
    "no path": ILL_FORMED,
    "two paths": PREFIXES + ":S a sh:NodeShape ; sh:property [ sh:path :a, :b ] .\n",
    "string minCount": PREFIXES + ':S a sh:NodeShape ; sh:property [ sh:path :a ; sh:minCount "x" ] .\n',
    "literal targetClass": PREFIXES + ':S a sh:NodeShape ; sh:targetClass "lit" .\n',
    "uniqueLang on a node shape": PREFIXES + ":S a sh:NodeShape ; sh:uniqueLang true .\n",
    "literal severity": PREFIXES + ':S a sh:NodeShape ; sh:severity "high" .\n',
    "nested or": PREFIXES + ':S a sh:NodeShape ; sh:or ( [ sh:minCount "x" ] ) .\n',
    "typed node shape with a path": PREFIXES + ":S a sh:NodeShape ; sh:path :p .\n",
    "no shapes at all": PREFIXES,
}


def _graph(text: str) -> Graph:
    return Graph().parse(data=text, format="turtle")


class _Calls:
    """Counts the calls of ``pyshacl.entrypoints.meta_validate``, whoever makes them (pySHACL's own included)."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.arguments: list[dict[str, Any]] = []
        real = entrypoints.meta_validate

        def spy(shacl_graph: Any, *args: Any, **kwargs: Any) -> Any:
            self.arguments.append(kwargs)
            return real(shacl_graph, *args, **kwargs)

        spy.graph_cache = real.graph_cache  # type: ignore[attr-defined] -- the wrapper shares the SHACL-SHACL graph
        monkeypatch.setattr(entrypoints, "meta_validate", spy)


def _cold_meta_validate(monkeypatch: pytest.MonkeyPatch) -> None:
    """``meta_validate`` as a fresh process has it: pySHACL fills ``graph_cache`` with the SHACL-SHACL graph on the
    first call, so a test that copies the attribute before any call copies the sentinel (the first test of a worker
    did)."""
    undecorated = entrypoints.meta_validate.__wrapped__  # type: ignore[attr-defined]
    cold = entrypoints.with_metashacl_shacl_graph_cache(undecorated)
    monkeypatch.setattr(entrypoints, "meta_validate", cold)


def test_the_spies_do_not_depend_on_an_earlier_test_having_warmed_pyshacls_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Three tests of this module failed when they were the first of a process to reach ``meta_validate`` (pytest-xdist
    decides which test that is), because their wrappers copied the cache's sentinel."""
    _cold_meta_validate(monkeypatch)
    calls = _Calls(monkeypatch)

    with pytest.raises(ShapesNotWellFormed):
        shacl_issues(_graph(DATA), _graph(ILL_FORMED))

    assert len(calls.arguments) == 1


def test_the_signature_spy_does_not_depend_on_a_warm_cache_either(monkeypatch: pytest.MonkeyPatch) -> None:
    _cold_meta_validate(monkeypatch)
    real = entrypoints.meta_validate

    def renamed(*args: Any, **kwargs: Any) -> Any:
        return real(*args, **kwargs)

    renamed.graph_cache = real.graph_cache  # type: ignore[attr-defined]
    renamed.__signature__ = inspect.Signature([inspect.Parameter("graph", inspect.Parameter.POSITIONAL_ONLY)])  # type: ignore[attr-defined]
    monkeypatch.setattr(entrypoints, "meta_validate", renamed)
    seen = _meta_shacl_arguments(monkeypatch)

    shacl_issues(_graph(DATA), _graph(WELL_FORMED))

    assert seen == [True]


def test_an_ill_formed_shapes_graph_is_meta_validated_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _Calls(monkeypatch)

    with pytest.raises(ShapesNotWellFormed):
        shacl_issues(_graph(DATA), _graph(ILL_FORMED))

    assert len(calls.arguments) == 1


def test_a_well_formed_shapes_graph_is_meta_validated_once(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _Calls(monkeypatch)

    shacl_issues(_graph(DATA), _graph(WELL_FORMED))

    assert len(calls.arguments) == 1


def test_the_meta_validation_is_not_asked_of_validate_a_second_time(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}
    real = pyshacl.validate

    def spy(*args: Any, **kwargs: Any) -> Any:
        seen.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(pyshacl, "validate", spy)

    shacl_issues(_graph(DATA), _graph(WELL_FORMED))

    assert seen["meta_shacl"] is False
    assert seen["inference"] == "none"
    assert seen["advanced"] is True


@pytest.mark.parametrize("name", sorted(CORPUS))
def test_the_verdict_is_the_one_of_meta_shacl_true(name: str) -> None:
    """The same shapes graphs are refused and accepted as pySHACL's own ``meta_shacl=True`` does."""
    shapes = _graph(CORPUS[name])
    try:
        pyshacl.validate(
            _graph(DATA), shacl_graph=shapes, inference="none", advanced=True, meta_shacl=True, abort_on_first=False
        )
        refused_by_pyshacl = False
    except ReportableRuntimeError as refusal:
        refused_by_pyshacl = str(refusal).startswith(METASHACL_TEXT)
    except Exception:  # noqa: BLE001 -- a load error is not a MetaSHACL verdict
        refused_by_pyshacl = False
    try:
        shacl_issues(_graph(DATA), _graph(CORPUS[name]))
        refused = False
    except ShapesNotWellFormed as failure:
        refused = failure.summary == ShapesNotWellFormed.summary
    except Exception:  # noqa: BLE001 -- the same
        refused = False

    assert refused is refused_by_pyshacl


def test_an_empty_shapes_graph_does_not_make_the_data_graph_the_shapes_graph() -> None:
    """``shacl_graph or data_graph`` in pySHACL: an empty (falsy) shapes graph used to meta-validate the data."""
    data_that_is_no_shapes_graph = _graph(ILL_FORMED)  # a data graph that SHACL-SHACL would refuse

    assert shacl_issues(data_that_is_no_shapes_graph, Graph()) == []


def test_pyshacls_own_report_is_not_logged_because_it_is_never_asked_for(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="pyshacl-validate")

    with pytest.raises(ShapesNotWellFormed):
        shacl_issues(_graph(DATA), _graph(ILL_FORMED))

    assert [r for r in caplog.records if r.name == "pyshacl-validate"] == []


def test_the_private_prefix_match_and_the_logger_filter_are_gone() -> None:
    assert not hasattr(shacl, "META_SHACL_PREFIX")
    assert not hasattr(shacl, "PYSHACL_LOGGER")
    assert not hasattr(shacl, "_WithoutMetaShaclReport")


# -- the canary: what ontolint takes from pySHACL, beyond its public API ----------------------------------------------


def test_canary_meta_validate_is_still_importable_and_has_the_shape_we_call() -> None:
    """``meta_validate`` is not in ``pyshacl.__all__``: when an upgrade moves or reshapes it, this fails first."""
    from pyshacl.entrypoints import meta_validate  # noqa: PLC0415

    parameters = inspect.signature(meta_validate).parameters
    assert "shacl_graph" in parameters
    assert "inference" in parameters
    assert any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values())  # advanced, abort_on_first
    conforms, report, text = meta_validate(_graph(WELL_FORMED), inference="none", advanced=True, abort_on_first=False)
    assert conforms is True
    assert isinstance(report, Graph)
    assert isinstance(text, str)
    conforms, report, text = meta_validate(_graph(ILL_FORMED), inference="none", advanced=True, abort_on_first=False)
    assert conforms is False
    assert isinstance(report, Graph)
    assert str(text).startswith("Validation Report")


def test_canary_validate_with_meta_shacl_true_still_refuses_with_the_text_the_fallback_relies_on() -> None:
    with pytest.raises(ReportableRuntimeError) as caught:
        pyshacl.validate(_graph(DATA), shacl_graph=_graph(ILL_FORMED), inference="none", meta_shacl=True)
    assert str(caught.value).startswith(METASHACL_TEXT)


# -- the support policy: a bounded dependency, and a narrow fallback ----------------------------------------------


def test_pyshacl_is_bounded_to_the_series_the_private_entry_point_was_verified_on() -> None:
    """``meta_validate`` is private: an open-ended ``pyshacl>=`` would promise support nobody tests."""
    import tomllib  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    root = Path(__file__).resolve().parent.parent
    dependencies = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
    (requirement,) = (d for d in dependencies if d.startswith("pyshacl"))
    assert "<0.41" in requirement.replace(" ", "")


def _meta_shacl_arguments(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    seen: list[Any] = []
    real = pyshacl.validate

    def spy(*args: Any, **kwargs: Any) -> Any:
        seen.append(kwargs["meta_shacl"])
        return real(*args, **kwargs)

    monkeypatch.setattr(pyshacl, "validate", spy)
    return seen


def test_a_missing_meta_validate_falls_back_to_pyshacls_own_meta_shacl(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(sg: Graph) -> None:
        raise ImportError("cannot import name 'meta_validate' from 'pyshacl.entrypoints'")

    monkeypatch.setattr(shacl, "_metashacl_verdict", missing)
    seen = _meta_shacl_arguments(monkeypatch)

    shacl_issues(_graph(DATA), _graph(WELL_FORMED))
    with pytest.raises(ReportableRuntimeError, match="MetaSHACL"):  # pySHACL's own refusal, with its own text
        shacl_issues(_graph(DATA), _graph(ILL_FORMED))

    assert seen == [True, True]


def test_a_meta_validate_whose_signature_changed_falls_back_too(monkeypatch: pytest.MonkeyPatch) -> None:
    real = entrypoints.meta_validate

    def renamed(*args: Any, **kwargs: Any) -> Any:  # pySHACL's own ``validate`` still reaches the real one
        return real(*args, **kwargs)

    renamed.graph_cache = real.graph_cache  # type: ignore[attr-defined]
    renamed.__signature__ = inspect.Signature([inspect.Parameter("graph", inspect.Parameter.POSITIONAL_ONLY)])  # type: ignore[attr-defined]
    monkeypatch.setattr(entrypoints, "meta_validate", renamed)
    seen = _meta_shacl_arguments(monkeypatch)

    shacl_issues(_graph(DATA), _graph(WELL_FORMED))

    assert seen == [True]


def test_any_other_fault_of_meta_validate_is_not_swallowed_by_the_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*args: Any, **kwargs: Any) -> Any:
        raise TypeError("a fault inside pySHACL, not a signature mismatch")

    monkeypatch.setattr(entrypoints, "meta_validate", broken)
    seen = _meta_shacl_arguments(monkeypatch)

    with pytest.raises(TypeError, match="a fault inside pySHACL"):
        shacl_issues(_graph(DATA), _graph(WELL_FORMED))

    assert seen == []
