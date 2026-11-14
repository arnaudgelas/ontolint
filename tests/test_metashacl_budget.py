"""Reading a shapes graph's MetaSHACL verdict runs inside the validation budget, and a hostile graph stays cheap (#62).

pySHACL meta-validates the shapes graph (SHACL-SHACL) before it validates any data, and that is the expensive part
of a large or deeply nested shapes graph (4 s for one list of 400 items).  ``--max-validation-seconds`` must bound
it, on the path that reports the failure too: a refactor that moved that work to the parent process, after or
before the worker, would reopen a denial of service that the list caps only narrow.  These tests slow every
``meta_validate`` call that finds the shapes graph ill-formed, in every process (a ``sitecustomize`` on
``PYTHONPATH``, which the ``spawn`` worker inherits), and say what the run does.
"""

# ruff: noqa: S603 -- runs this interpreter with fixed arguments

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.collection import Collection

from ontolint.adapters.shacl import ShapesNotWellFormed

SH = "http://www.w3.org/ns/shacl#"
PREFIXES = "@prefix : <https://e.test/#> .\n@prefix sh: <http://www.w3.org/ns/shacl#> .\n"
DATA = PREFIXES + ":a a :C .\n"
SLOW = 60  # seconds a meta-validation that finds the shapes graph ill-formed takes: far above the budget
DEADLINE = 20  # seconds a run may take before a call outside the worker has certainly happened
BUDGET = "1"
FAILED = 2
SITECUSTOMIZE = f"""
import time
import pyshacl.entrypoints as entrypoints

_real = entrypoints.meta_validate
def _slow(*args, **kwargs):
    result = _real(*args, **kwargs)
    if not result[0]:  # the failure path: wherever it runs, it takes {SLOW} seconds
        time.sleep({SLOW})
    return result
_real(__import__('rdflib').Graph(), inference='none')  # load the SHACL-SHACL graph the wrapper shares
_slow.graph_cache = _real.graph_cache
entrypoints.meta_validate = _slow
"""
# The same wrapper as a ``python -c`` program: run the CLI, then say how much memory it and its worker used.
DRIVER = (
    "import resource, sys; from ontolint.cli import main; code = main(sys.argv[1:]); "
    "print(max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, "
    "resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss), file=sys.stderr); sys.exit(code)"
)
MEGABYTE = 1_000_000 if sys.platform == "darwin" else 1_000  # ru_maxrss: bytes on macOS, kilobytes on Linux
MEMORY_LIMIT = 500 * MEGABYTE


def _list(n: int) -> str:
    return "( " + " ".join(f":v{i}" for i in range(n)) + " )"


def _ill_formed_small() -> Graph:
    return Graph().parse(data=PREFIXES + ":S a sh:NodeShape ; sh:property :N . :N sh:minCount 1 .\n", format="turtle")


def _ill_formed_list_400() -> Graph:
    """The longest list the pre-check lets through, in a shapes graph SHACL-SHACL rejects (a property without path)."""
    shapes = (
        PREFIXES + f":S a sh:NodeShape ; sh:property [ sh:path :p ; sh:in {_list(400)} ] , :N . :N sh:minCount 1 .\n"
    )
    return Graph().parse(data=shapes, format="turtle")


def _ill_formed_nested(depth: int) -> Graph:
    """``sh:or`` nested ``depth`` times around a node shape with a value that is no integer."""
    g = Graph()
    inner = BNode()
    g.add((inner, URIRef(SH + "minCount"), Literal("x")))
    for _ in range(depth):
        outer = BNode()
        Collection(g, head := BNode(), [inner])
        g.add((outer, URIRef(SH + "or"), head))
        inner = outer
    g.add((URIRef("https://e.test/#S"), URIRef(SH + "node"), inner))
    return g


def _run(
    tmp_path: Path, shapes: Graph, *argv: str, slow: bool, deadline: int = DEADLINE
) -> subprocess.CompletedProcess[str]:
    """The CLI in a child process (so the slowdown and the memory are its own), with a deadline of its own."""
    (tmp_path / "data.ttl").write_text(DATA, encoding="utf-8")
    (tmp_path / "shapes.ttl").write_text(
        shapes.serialize(format="nt"), encoding="utf-8"
    )  # flat: Turtle writes nesting recursively
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    if slow:
        hook = tmp_path / "hook"
        hook.mkdir()
        (hook / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")
        env["PYTHONPATH"] = str(hook)
    args = ["data.ttl", "--shapes", "shapes.ttl", "--select", "SHACL001", "--format", "json", *argv]
    return subprocess.run(
        [sys.executable, "-c", DRIVER, *args],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=deadline,  # a call outside the worker sleeps SLOW seconds: the deadline says so
        check=False,
    )


def _detail(done: subprocess.CompletedProcess[str]) -> str:
    (execution,) = [x for f in json.loads(done.stdout)["files"] for x in f["executions"] if x["rule"] == "SHACL001"]
    assert execution["status"] == "failed"
    return str(execution["detail"])


def test_every_meta_validation_of_a_budgeted_run_is_inside_the_budget(tmp_path: Path) -> None:
    """The run ends at its budget, not after ``SLOW`` seconds: no meta-validation of the failure is in the parent."""
    done = _run(tmp_path, _ill_formed_small(), "--max-validation-seconds", BUDGET, slow=True)

    assert done.returncode == FAILED, done.stderr
    assert _detail(done).startswith(
        f"ValidationTimeout: SHACL validation did not finish within the time budget of {BUDGET} seconds"
    )


def test_the_control_slows_the_run_that_has_no_budget(tmp_path: Path) -> None:
    """Without a budget the slowed call is in this process and the deadline of :func:`_run` fires: the hook works."""
    with pytest.raises(subprocess.TimeoutExpired):
        _run(tmp_path, _ill_formed_small(), slow=True, deadline=8)


def test_an_unbudgeted_run_reports_the_failure_in_process(tmp_path: Path) -> None:
    """``--max-validation-seconds`` unset: no worker, the failure is reported all the same (the budget is opt-in)."""
    done = _run(tmp_path, _ill_formed_small(), slow=False)

    assert done.returncode == FAILED, done.stderr
    assert _detail(done) == ShapesNotWellFormed.summary


@pytest.mark.parametrize(
    "shapes", [_ill_formed_list_400, lambda: _ill_formed_nested(1000)], ids=["list-of-400", "or-nested-1000"]
)
def test_a_hostile_shapes_graph_ends_at_the_budget_in_little_memory(
    tmp_path: Path, shapes: type[Graph] | object
) -> None:
    """The worst graphs the pre-check admits take seconds to meta-validate, not minutes, and little memory."""
    done = _run(tmp_path, shapes(), "--max-validation-seconds", "1", slow=False)  # type: ignore[operator]

    assert done.returncode == FAILED, done.stderr
    assert _detail(done).startswith("ValidationTimeout: ")  # each takes 3 s or more to meta-validate: past the budget
    assert int(done.stderr.strip().splitlines()[-1]) < MEMORY_LIMIT
