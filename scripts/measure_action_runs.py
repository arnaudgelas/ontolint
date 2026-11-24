"""Measure what the Action's second ontolint run costs (issue #188).

The Action (``action/entrypoint.py run``) runs ontolint twice on the same files: once for the Markdown summary and once
for the SARIF report.  This script builds the very two commands the Action runs (``report_command``), on synthetic
inputs it writes itself, and reports:

* the wall time and the peak memory of one run and of the Action's two, over several repetitions (the median);
* whether the reports of the repetitions are byte-identical (they should be, except for a run a time budget limits);
* with a SHACL validation budget (``--max-validation-seconds``) set near the validation time, how often the Markdown run
  and the SARIF run of one Action invocation disagree about whether SHACL001 failed.

It prints Markdown.  ``docs/action-run-cost.md`` records a run and what was decided from it.

    uv run python scripts/measure_action_runs.py [--classes N] [--imports N] [--nodes N] [--repetitions N] [--out FILE]
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PREFIXES = (
    "@prefix ex: <https://measure.example/onto#> .\n@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n@prefix sh: <http://www.w3.org/ns/shacl#> .\n"
    "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n\n"
)
# The child reports its own peak: ru_maxrss of children is the maximum over all of them, so one wrapper per run.
WRAPPER = (
    "import resource, subprocess, sys\n"
    "code = subprocess.run(sys.argv[1:], check=False).returncode\n"
    "peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss\n"
    "print(peak, file=sys.stderr)\n"
    "sys.exit(code)\n"
)
KIB = 1024
MIB = 1024 * 1024
SLOW_SECONDS = 10.0  # the issue's rule: proceed when the second run adds more than this on a realistic input
SLOW_PERCENT = 30.0  # ... or more than this share of the first


def _entrypoint() -> object:
    spec = importlib.util.spec_from_file_location("action_entrypoint", ROOT / "action" / "entrypoint.py")
    if spec is None or spec.loader is None:
        raise SystemExit("action/entrypoint.py cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules["action_entrypoint"] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class Scenario:
    name: str
    files: list[str]
    extra: list[str] = field(default_factory=list[str])
    note: str = ""


@dataclass(frozen=True)
class Run:
    wall: float
    peak_bytes: int
    exit: int
    reports: dict[str, bytes]


def large_file(directory: Path, classes: int) -> Scenario:
    """One Turtle file of ``classes`` classes in a tree of fan-out 10, each labelled and defined."""
    lines = [PREFIXES, "<https://measure.example/onto> a owl:Ontology .\n"]
    for i in range(classes):
        lines.append(f'ex:C{i} a owl:Class ; rdfs:label "Class {i}"@en ; rdfs:comment "Definition of class {i}."@en')
        lines.append(f" ; rdfs:subClassOf ex:C{(i - 1) // 10} .\n" if i else " .\n")
    (directory / "large.ttl").write_text("".join(lines), encoding="utf-8")
    return Scenario(f"{classes:,} classes, one file", ["large.ttl"])


def import_closure(directory: Path, files: int, classes: int) -> Scenario:
    """A root that imports ``files`` files of ``classes`` classes each, found with ``--import-dir``."""
    imports = directory / "imports"
    imports.mkdir()
    iris = [f"https://measure.example/part{i}" for i in range(files)]
    for i, iri in enumerate(iris):
        body = [PREFIXES, f"<{iri}> a owl:Ontology .\n"]
        body += [f'<{iri}#C{j}> a owl:Class ; rdfs:label "Part {i} class {j}"@en .\n' for j in range(classes)]
        (imports / f"part{i}.ttl").write_text("".join(body), encoding="utf-8")
    root = [PREFIXES, "<https://measure.example/root> a owl:Ontology ;\n"]
    root.append(" ;\n".join(f"    owl:imports <{iri}>" for iri in iris) + " .\n")
    (directory / "root.ttl").write_text("".join(root), encoding="utf-8")
    return Scenario(f"{files} imports of {classes:,} classes", ["root.ttl"], ["--import-dir", "imports"])


def shacl_run(directory: Path, nodes: int, budget: float | None) -> Scenario:
    """``nodes`` data nodes checked against a pattern shape with ``--shapes``, with an optional validation budget."""
    data = [PREFIXES, "<https://measure.example/data> a owl:Ontology .\n"]
    data += [f'ex:N{i} a ex:Thing ; rdfs:label "Node {i}"@en ; ex:code "code-{i}" .\n' for i in range(nodes)]
    (directory / "data.ttl").write_text("".join(data), encoding="utf-8")
    shapes = (
        PREFIXES + "ex:ThingShape a sh:NodeShape ; sh:targetClass ex:Thing ;\n"
        '    sh:property [ sh:path ex:code ; sh:pattern "^code-[0-9]+$" ; sh:minCount 1 ] .\n'
    )
    (directory / "shapes.ttl").write_text(shapes, encoding="utf-8")
    extra = ["--shapes", "shapes.ttl"] + (["--max-validation-seconds", str(budget)] if budget is not None else [])
    return Scenario(
        f"{nodes:,} nodes, SHACL" + (f", budget {budget:g} s" if budget is not None else ""), ["data.ttl"], extra
    )


def commands(entry: object, scenario: Scenario, directory: Path) -> dict[str, list[str]]:
    """The two commands of the Action for ``scenario``: the Markdown summary and the SARIF report."""
    settings = entry.Settings(  # type: ignore[attr-defined]
        workspace=directory,
        files=scenario.files,
        extra=scenario.extra,
        fail_on="never",
        sarif_file=directory / "out" / "ontolint.sarif",
        summary=True,
        step_summary=None,
        github_output=None,
        runner_temp=None,
    )
    base = [sys.executable, "-m", "ontolint"]
    return {
        "markdown": entry.report_command(base, settings, "markdown", directory / "out" / "summary.md"),  # type: ignore[attr-defined]
        "sarif": entry.report_command(base, settings, "sarif", directory / "out" / "ontolint.sarif"),  # type: ignore[attr-defined]
    }


def run_one(argv: Sequence[str], directory: Path, output: Path) -> Run:
    """Run one ontolint command from ``directory``; its wall time, peak memory, exit status and report."""
    output.unlink(missing_ok=True)
    started = time.perf_counter()
    done = subprocess.run(  # noqa: S603 -- our own interpreter and arguments built from our own files
        [sys.executable, "-c", WRAPPER, *argv],
        cwd=directory,
        capture_output=True,
        text=True,
        check=False,
    )
    wall = time.perf_counter() - started
    peak = int(done.stderr.strip().splitlines()[-1]) if done.stderr.strip() else 0
    peak_bytes = peak if sys.platform == "darwin" else peak * KIB  # macOS counts bytes, Linux kibibytes
    reports = {output.name: output.read_bytes()} if output.exists() else {}
    return Run(wall, peak_bytes, done.returncode, reports)


def action_pair(entry: object, scenario: Scenario, directory: Path) -> tuple[Run, Run]:
    """What one Action invocation does: the Markdown run, then the SARIF run."""
    (directory / "out").mkdir(exist_ok=True)
    both = commands(entry, scenario, directory)
    markdown = run_one(both["markdown"], directory, directory / "out" / "summary.md")
    sarif = run_one(both["sarif"], directory, directory / "out" / "ontolint.sarif")
    return markdown, sarif


def digest(run: Run) -> str:
    return hashlib.sha256(b"".join(run.reports[name] for name in sorted(run.reports))).hexdigest()[:12]


@dataclass(frozen=True)
class Cost:
    scenario: str
    one_wall: float
    two_wall: float
    one_peak: int
    two_peak: int
    identical: bool

    @property
    def added(self) -> float:
        return self.two_wall - self.one_wall

    @property
    def percent(self) -> float:
        return 100.0 * self.added / self.one_wall if self.one_wall else 0.0


def measure(entry: object, scenario: Scenario, directory: Path, repetitions: int) -> Cost:
    pairs = [action_pair(entry, scenario, directory) for _ in range(repetitions)]
    firsts = [markdown for markdown, _ in pairs]
    sarifs = [sarif for _, sarif in pairs]
    return Cost(
        scenario.name,
        statistics.median(r.wall for r in firsts),
        statistics.median(m.wall + s.wall for m, s in pairs),
        max(r.peak_bytes for r in firsts),
        max(max(m.peak_bytes, s.peak_bytes) for m, s in pairs),
        len({digest(r) for r in firsts}) == 1 and len({digest(r) for r in sarifs}) == 1,
    )


TOOL_FAILURE = 2  # ontolint exits 2 when a requested rule did not deliver a verdict (SHACL001 timing out included)


def threshold(entry: object, directory: Path, nodes: int, steps: int = 7) -> float:
    """The validation budget that SHACL001 just meets, by bisection between a budget it fails and one it meets."""
    (directory / "out").mkdir(exist_ok=True)
    low, high = 0.05, 120.0
    for _ in range(steps):
        middle = (low * high) ** 0.5  # geometric: budgets span orders of magnitude
        scenario = shacl_run(directory, nodes, round(middle, 3))
        sarif = commands(entry, scenario, directory)["sarif"]
        failed = run_one(sarif, directory, directory / "out" / "ontolint.sarif").exit == TOOL_FAILURE
        low, high = (middle, high) if failed else (low, middle)
    return high


def disagreement(entry: object, directory: Path, nodes: int, pairs: int) -> list[str]:
    """Run the SHACL scenario with a budget below, at and above the one SHACL001 just meets; count disagreements."""
    edge = threshold(entry, directory, nodes)
    rows = [
        "| budget | pairs | Markdown run exits 2 | SARIF run exits 2 | pairs that disagree |",
        "| --- | --- | --- | --- | --- |",
    ]
    for factor in (0.5, 0.9, 1.0, 1.1, 2.0):
        budget = max(round(edge * factor, 3), 0.05)
        scenario = shacl_run(directory, nodes, budget)
        said = [action_pair(entry, scenario, directory) for _ in range(pairs)]
        in_markdown = sum(m.exit == TOOL_FAILURE for m, _ in said)
        in_sarif = sum(s.exit == TOOL_FAILURE for _, s in said)
        differ = sum(m.exit != s.exit for m, s in said)
        label = f"{budget:g} s ({factor:g} x the {edge:.3f} s it just meets)"
        rows.append(f"| {label} | {pairs} | {in_markdown} | {in_sarif} | {differ} |")
    return rows


def render(costs: list[Cost], extra: list[str]) -> str:
    out = [
        "| Input | One run | The Action's two | Added | Peak memory (one / two) | Reports identical |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for c in costs:
        out.append(
            f"| {c.scenario} | {c.one_wall:.2f} s | {c.two_wall:.2f} s | {c.added:.2f} s ({c.percent:.0f} %) "
            f"| {c.one_peak / MIB:.0f} / {c.two_peak / MIB:.0f} MiB | {'yes' if c.identical else 'NO'} |"
        )
    rule = [c.scenario for c in costs if c.added > SLOW_SECONDS or c.percent > SLOW_PERCENT]
    out += [
        "",
        f"The issue's rule (the second run adds more than {SLOW_PERCENT:g} % or {SLOW_SECONDS:g} s) holds for: "
        + (", ".join(rule) if rule else "no input")
        + ".",
        "",
        *extra,
    ]
    return "\n".join(out)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--classes", type=int, default=40_000, help="classes of the large single file")
    parser.add_argument("--imports", type=int, default=30, help="files of the import closure")
    parser.add_argument("--per-import", type=int, default=500, help="classes in each imported file")
    parser.add_argument("--nodes", type=int, default=20_000, help="data nodes of the SHACL run")
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--pairs", type=int, default=10, help="Action invocations per budget in the disagreement trial")
    parser.add_argument("--out", type=Path, help="write the Markdown here as well")
    args = parser.parse_args(argv)
    entry = _entrypoint()
    work = Path(tempfile.mkdtemp(prefix="ontolint-measure-"))
    try:
        costs = []
        for name, build in (
            ("large", lambda d: large_file(d, args.classes)),
            ("imports", lambda d: import_closure(d, args.imports, args.per_import)),
            ("shacl", lambda d: shacl_run(d, args.nodes, None)),
        ):
            directory = work / name
            directory.mkdir()
            costs.append(measure(entry, build(directory), directory, args.repetitions))
        trial = work / "budget"
        trial.mkdir()
        text = render(
            costs,
            [
                "Disagreement trial (one Action invocation = a Markdown run then a SARIF run, same budget):",
                "",
                *disagreement(entry, trial, args.nodes, args.pairs),
            ],
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(text)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
