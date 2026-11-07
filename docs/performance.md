# Performance profile

Reproduce: `uv run python tests/benchmarks/profile_linter.py {chain|tree|dag|labels} SIZE [TOP]`
and `ONTOLINT_BENCH=1 uv run pytest tests/benchmarks --no-cov`.
Numbers: Python 3.13, Apple-silicon laptop, in-memory rdflib graph, graph construction excluded,
measured on the commit `1f4698e` code (cProfile roughly doubles wall time).

| Scenario | Size | Before (`1f4698e`) | After | Peak tracemalloc (after) |
|---|---|---|---|---|
| Deep chain | 400 / 5k classes | 0.03 s (500) / `RecursionError` past ~1k | 0.01 s / 0.13 s | - |
| Deep chain | 100k classes (400k triples) | `RecursionError` | 8.8 s profiled, ~4.5 s of it in lexical/rdflib | 245 MB |
| Wide tree (fan-out 10) | 20k classes (80k triples) | ~1.0 s | 0.62 s | 52 MB |
| Dense DAG (5 parents) | 2k classes (16k triples) | 2.9 s | 0.09 s | - |
| Dense DAG (5 parents) | 4k classes (32k triples) | 8.5 s (24.6 s profiled) | 0.24 s (0.53 s profiled) | 21 MB |
| SKOS vocabulary | 50k concepts (350k triples) | 2.1 s | 2.1 s (unchanged) | 75 MB |

## Findings and fixes

1. **Recursion limit (fixed).** CLS005 raised `RecursionError` beyond roughly 500-1000 classes.
   It now uses the iterative `ontolint.graph.hierarchy_depths` (hypothesis-verified against the
   recursive original; `tests/test_differential.py` golden unchanged). 100k-deep chains lint.
2. **Quadratic CLS004 (fixed).** One BFS per asserted edge (20k BFS runs, 85M `URIRef.__eq__`
   calls, 98% of dense-DAG time). Replaced by `graph.transitively_redundant_edges`: per-component
   reachability bitsets over the SCC condensation (built only for nodes reachable from classes
   with more than one superclass, so trees and chains cost nothing); edges whose source sits on a
   cycle keep the per-edge search. A hypothesis test (`tests/test_graph_algorithms.py`) keeps the
   old per-edge BFS as the reference and checks identical edge sets, cycles and self-loops
   included. Dense DAG 4k: 8.5 s to 0.24 s (35x), growth now roughly linear.
3. **Quadratic CLS007 (fixed).** The chain walk from every class is now memoised
   (`_chain_lengths`, same cycle semantics, checked against the legacy walk by a hypothesis
   test). It was invisible below ~5k depth; a 5k chain now lints in 0.13 s.
4. **Tree (20k classes).** Remaining time is flat: `lexical` 0.5 s (260k `Graph.triples` calls),
   `GraphContext.build` 0.3 s, `classes` 0.29 s. No single hotspot.
5. **50k-term vocabulary / 100k chain.** Remaining cost is rdflib `triples()` dispatch:
   `skos` 2.2 s, context build 1.4 s, `lexical` 1.2 s of 4.2 s profiled (1.3M `triples` calls,
   650k `Graph.objects`). In the 100k chain, `lexical` is 2.9 s of 7.2 s (1.3M `triples` calls).

## Cache-index conclusion

- Justified: none. After the algorithmic fixes every scenario finishes in a few seconds
  (the 100k-class chain in ~9 s) and the fresh profiles show no repeated-lookup hotspot above
  rdflib's own cost.
- Weak candidate (only if vocabularies of 100k+ terms matter): a `(subject, predicate) -> objects`
  index in `GraphContext` for SKOS/label predicates would remove ~1.3M rdflib `triples()` calls
  (about 40-45% of profiled time in the labels scenario). Measure again after wiring before adding.
- Not justified: further indexes for class hierarchy facts (already indexed once in `context.py`).
- CLS004 was an algorithmic problem, fixed without any index.

## Enabling the `benchmark` marker (pyproject.toml change, not applied)

```toml
[tool.pytest.ini_options]
markers = ["benchmark: opt-in large-ontology resource-budget benchmarks (ONTOLINT_BENCH=1)"]
# and add `--ignore=tests/benchmarks` to addopts if benchmarks should never be collected by default
```
Currently the benchmarks are gated only by `ONTOLINT_BENCH=1` through `skipif` (skipped otherwise).
