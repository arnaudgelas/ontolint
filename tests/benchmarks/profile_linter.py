"""Profile the full Linter on a synthetic ontology.

Usage: uv run python tests/benchmarks/profile_linter.py {chain,tree,dag,labels} [size] [top]
"""

from __future__ import annotations

import cProfile
import pstats
import sys
import time
import tracemalloc

import synthetic

from ontolint import Linter

DEFAULT_TOP = 25
SCENARIOS = {
    "chain": (synthetic.deep_chain, 900),
    "tree": (synthetic.wide_tree, 20_000),
    "dag": (synthetic.dense_dag, 10_000),
    "labels": (synthetic.many_labels, 50_000),
}


def main(argv: list[str]) -> int:
    name, *rest = [*argv[1:], "labels"][:1] + argv[2:]
    factory, default_size = SCENARIOS[name]
    size = int(rest[0]) if rest else default_size
    top = int(rest[1]) if len(rest) > 1 else DEFAULT_TOP
    graph = factory(size)
    profiler = cProfile.Profile()
    start = time.perf_counter()
    profiler.enable()
    findings = Linter(graph).run()
    profiler.disable()
    print(f"{name} size={size} triples={len(graph)} findings={len(findings)} wall={time.perf_counter() - start:.2f}s")
    pstats.Stats(profiler).sort_stats("cumulative").print_stats(top)
    tracemalloc.start()
    Linter(graph).run()
    print(f"peak tracemalloc during lint: {tracemalloc.get_traced_memory()[1] / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
