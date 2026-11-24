# What the Action's second ontolint run costs

The Action (`action/entrypoint.py run`) runs ontolint **twice** on the same files: once for the Markdown summary
(`--format markdown`) and once for the SARIF report (`--format sarif`). Issue #188 asked what that costs and whether the
two runs can disagree, before deciding on #189 (the CLI writes a second report from one run) and #190 (the Action uses it).
This page records the measurement and what follows from it.

## Method

`scripts/measure_action_runs.py` writes its own inputs, builds the two commands with the Action's own `report_command` (it
does not reimplement it) and runs them from the workspace, as the Action does. Each Action invocation is a Markdown run
then a SARIF run. Wall time is the median of five invocations; "one run" is the Markdown run alone. Peak memory is the
largest `ru_maxrss` of any run, read by a wrapper process per run. The reports are hashed: the five Markdown reports must be
byte-identical, and so must the five SARIF reports.

```bash
uv run python scripts/measure_action_runs.py --out action-run-cost.md
```

Measured on an Apple M4 Pro (arm64, macOS), Python 3.13.7, ontolint 0.17.0, 2026-11-24, with nothing else running. A hosted
Linux runner is slower; the shape of the result does not depend on that.

## Result

| Input | One run | The Action's two | Added | Peak memory (one / two) | Reports identical |
| --- | --- | --- | --- | --- | --- |
| 40,000 classes, one file | 11.22 s | 23.37 s | 12.16 s (108 %) | 384 / 388 MiB | yes |
| 30 imports of 500 classes | 3.35 s | 8.09 s | 4.73 s (141 %) | 168 / 237 MiB | yes |
| 20,000 nodes, SHACL | 2.25 s | 4.92 s | 2.66 s (118 %) | 211 / 225 MiB | yes |

The issue's rule (the second run adds more than 30 % or 10 s) holds for: 40,000 classes, one file, 30 imports of 500 classes, 20,000 nodes, SHACL.

Disagreement trial (one Action invocation = a Markdown run then a SARIF run, same budget):

| budget | pairs | Markdown run exits 2 | SARIF run exits 2 | pairs that disagree |
| --- | --- | --- | --- | --- |
| 0.523 s (0.5 x the 1.046 s it just meets) | 10 | 10 | 10 | 0 |
| 0.941 s (0.9 x the 1.046 s it just meets) | 10 | 10 | 10 | 0 |
| 1.046 s (1 x the 1.046 s it just meets) | 10 | 1 | 1 | 2 |
| 1.15 s (1.1 x the 1.046 s it just meets) | 10 | 0 | 0 | 0 |
| 2.091 s (2 x the 1.046 s it just meets) | 10 | 0 | 0 | 0 |


## Reading it

- **The second run costs a whole run.** The Action does the same work twice, so the second run adds 108 to 141 % of the
  first, on every input: 12 s on 40,000 classes, 4.7 s on a 30-file import closure, 2.7 s on a SHACL run of 20,000
  nodes. The issue's rule (more than 30 % or 10 s) holds by percentage on all three and by seconds on the largest. The
  percentage cannot fail: there is no cache between the two processes.
- **Memory does not add up.** The runs are sequential, so the peak is the larger of the two (it rises from 168 to
  237 MiB on the closure because the SARIF run holds the source locations the Markdown run does not need).
- **The reports are deterministic.** The five Markdown reports and the five SARIF reports of each input are byte-identical,
  so two runs cannot disagree on their own (test case 1 of the issue).
- **A validation budget makes them disagree.** With `--max-validation-seconds` at the budget SHACL001 just meets
  (found by bisection), 2 of the 10 invocations ended with one run exiting 2 (the validation timed out: TOOL001) and the other
  exiting 0: the Markdown summary then says the validation failed and the SARIF report of the same job says it did not, or
  the reverse. At half or at double that budget all 10 invocations agree. This is the constructed case of test case 2,
  not a hypothetical: it needs a budget close to the validation time, which a user who sets one on a slow input can reach.

## Decision

**Recommendation: proceed with #189 and #190.** One run that writes both reports removes the second run (12 s on a
40,000-class file, a share of every CI job that uses the Action) and removes the one way the two reports can contradict
each other. The cost is the CLI option of #189 (a second report from the same run) and a smaller Action. If the Action's
inputs are typically small ontologies, the seconds saved are small, but the contradiction is not: it needs no large input.

This page is the measurement; the decision to proceed or to close the epic (#91) is the maintainer's.

## Limits

One machine, one Python, synthetic inputs of the shapes the issue named (a large file, an import closure with `--import-dir`,
a SHACL run with a budget), not a corpus of real ontologies. The Action's install step (a wheel download and an
attestation check) is not in these numbers: it runs once whatever is decided.
