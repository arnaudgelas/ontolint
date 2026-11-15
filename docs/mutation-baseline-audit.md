# Mutation baseline audit (issue #19)

This is a **prepared audit, not an approval**. It was written by an AI agent (Claude) on 2026-11-15
from `main` at `e96348d`, to make the maintainer's decision cheap. The policy
(`docs/mutation-policy.md`) requires a reviewer other than the author to approve every pardon;
an agent's reading does not replace that, and neither does this page. Approving the pardons,
starting the hosted run and setting `MUTATION_GATE_MODE=blocking` remain the maintainer's.

## What the issue says and what is true now

| Issue text | State at `e96348d` |
| --- | --- |
| 20 `gremlin: pardon` markers await audit | 14. The 2026-11-13 audit (`docs/mutation-pardons.md`) removed 19 of 31 and two were added (`GraphContext`, the run-level `zip`), 14 remain: 9 `untestable`, 5 `equivalent`. `tests/test_mutation_pardons.py` pins the list. |
| `context.py` is outside the mutation scope | It is inside (commit `978248d`, `paths` in `pyproject.toml`). |
| Survivors deferred: TOOL005 hint, TOOL006, declared prefixes, `_library`, catalog parsing, `_library_origins`, `_file_modules` | Tests exist for them (`tests/test_mutation_older_survivors.py`, commits `6c82032`, `e8c1dde`); see "Survivors" below for the re-run. |
| The 2026-11-10 re-run proves nothing | Still true. No hosted run exists for the current code. |

## Verdicts

`sound`: the reason holds after reading the code. `weak`: the reason holds today, but the
mutant is observable and a test could pin it, or the reason leaves a gap. `testable`: a survivor
that deserves a test. A `sound` verdict on an `untestable` pardon is conditional on its expiry
(issue #71, 2027-02-13) and on the test that kills the mutant outside the run.

### `untestable`: `@dataclass(frozen=True)`, mutant `True` to `False` (9)

The mutant is observable (an instance becomes assignable). It is pardoned only because the
decorator runs at import, so every test covers it and the selected suite exceeds the 30 s mutant
timeout. `test_value_objects_are_frozen` (`tests/test_mutation_pardon_audit.py`) lists all nine
classes and asserts `__dataclass_params__.frozen`, so each mutant fails it in the normal suite.

| # | Location | Class | Verdict | Note |
| --- | --- | --- | --- | --- |
| 1 | `src/ontolint/adapters/shacl.py:554` | `_ValidationJob` | sound | Sent to a worker; immutability is a contract. In the test's list. |
| 2 | `src/ontolint/context.py:55` | `GraphContext` | sound | Cached and shared by every rule. In the list. |
| 3 | `src/ontolint/cli.py:710` | `ImportOptions` | sound | In the list. |
| 4 | `src/ontolint/imports.py:55` | `Catalog` | sound | In the list. |
| 5 | `src/ontolint/imports.py:146` | `Closure` | sound | In the list. |
| 6 | `src/ontolint/loader.py:111` | `ImportChoice` | sound | In the list. |
| 7 | `src/ontolint/loader.py:124` | `ImportShadow` | sound | In the list. |
| 8 | `src/ontolint/loader.py:628` | `_ParseJob` | sound | Sent to a worker. In the list. |
| 9 | `src/ontolint/reporting.py:63` | `Origin` | sound | In the list. |

Caveat for all nine: the "too slow" claim is a property of pytest-gremlins and the suite size, not
of the code, and the pardons count against the 5% limit. They must be renewed or replaced at the
expiry; a hosted run is the first chance to see whether the mutants really time out, so the
maintainer can check the run for errors on these lines.

### `equivalent` (5)

| # | Location | Mutant | Stated reason | Verdict | Reading |
| --- | --- | --- | --- | --- | --- |
| 10 | `src/ontolint/cli.py:1168` | `zip(inputs, graphs, shared, strict=True)`: True to False | `shared` has one entry per input, like `graphs` | sound | `_lint` returns 2 when `_parse_inputs` reports any error (every input appends exactly one graph or one error), so `graphs` has `len(inputs)` entries here. `shared` is `shared_identities(...)`, which returns `[... for _ in inputs]` one tuple per input, or `[()] * len(inputs)`. `strict` is an assertion of an invariant that holds by construction. The same assertion in `shared_identities` (`declarations.py`, outside the scope) stays unpardoned and unmutated. |
| 11 | `src/ontolint/baseline.py:96` | `zip(report.findings, ids, strict=True)`: True to False | `ids` is built from `report.findings` | sound | `ids` is a list comprehension over `report.findings` two lines above; `report` is not touched in between. |
| 12 | `src/ontolint/datasets.py:330` | `zip(triples, of, strict=True)`: True to False | lengths were compared above | sound | The function raises `ValueError` when `len(of) != len(triples)` earlier, and has a test for that message. `strict` never fires. |
| 13 | `src/ontolint/worker.py:108` | `Pipe(duplex=False)`: False to True | parent only reads, worker only writes | sound | A duplex pipe is a socket pair; the parent closes `sender` after `start()`, so EOF on `receiver` still means the worker is gone. Nothing calls `receiver.send` or `sender.recv_bytes`. No caller can see the difference (only the file descriptor kind). |
| 14 | `src/ontolint/worker.py:111` | `Process(..., daemon=True)`: True to False | `_stop` runs in `finally`, so `daemon` matters only if the parent dies | weak | True for every path through the `try`. Two gaps: `sender.close()` runs between `process.start()` and the `try`, and `receiver.close()` runs before `_stop` in the `finally`; if either raised, a non-daemon worker would be left and keep the interpreter from exiting. `daemon` is observable (`process.daemon`), so a test that spies `Process` can pin it. The policy's own rule ("a mutant that changes anything a caller can observe is not equivalent") argues for a test, not a pardon. Not changed here: removing a pardon is a reviewed change of its own. |

## Counts

| Verdict | Count |
| --- | --- |
| sound | 13 |
| weak | 1 (#14) |
| testable | 0 |

Pardoned mutants are 14 of the mutants of the whole scope (about 2 400 in the 0.13.1 local run), far
below the 5% limit.

## Scope: `context.py`

It is in scope. `978248d` added it to `paths` and to the scope paragraph of
`docs/mutation-policy.md`; the mutation run below shows its result. The issue's "decide whether it
belongs" is therefore already decided in the repository; the maintainer only has to keep that
change when approving.

## Survivors the issue lists

Each module was mutated alone with the non-slow suite, as `docs/mutation-policy.md` prescribes:

```bash
uv run pytest -p no:randomly -m 'not slow' --gremlins --no-cov --gremlin-parallel --gremlin-workers=4 \
  --gremlin-targets=src/ontolint/<module>.py --gremlin-report=console,json
```

| Module | Mutants | Zapped | Survived | Error | Pardoned | Score before this change | After |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `imports.py` and `context.py` (one run) | 91 | 87 | 0 | 1 | 3 | 98.9% | unchanged (no change to them) |
| `cli.py` | 190 | 182 | 3 | 3 | 2 | 96.8% | 99.5% (187 zapped, 0 survived, 1 error: `RunPlan`) |

Score is `(zapped + timeout) / (total - pardoned)` as in `mutation_gate.py`. The runs were made on
a machine with a load average of 15 to 37, so some errors are timeouts caused by load.

The issue's survivors (TOOL005 hint, TOOL006, declared prefixes, `_library_origins`,
`_file_modules`, catalog parsing in `imports.py`) are all killed except the `_library` import-root
fallback; the other survivors and errors of `cli.py` are in code added since:

| Where | Mutant | Verdict | Handling |
| --- | --- | --- | --- |
| `cli.py:895` `_library` | `or` to `and` in the import-root fallback | testable | Killed by two tests in `tests/test_pattern_library.py`: by default a member that links to a file elsewhere in the repository is read (the mutant read under the working directory), and an explicit `--import-root` bounds the library (the mutant ignored it). This is the survivor `TODO.md` called an equivalent root fallback: it is not, the root decides which symlinks are refused. |
| `cli.py:1146`, `_lint`, quality baseline refusal | `return TOOL_FAILURE_EXIT` to `None` | testable | Survived because the crash handler of `main` also exits 2, after the same message. Killed by asserting the refusal is the only stderr line. |
| `cli.py:1174`, `_lint`, `return trend` (the snapshot write failure) | to `None` | testable | The same; killed by the same assertion on the unwritable snapshot. |
| `cli.py:700`, `cli.py:703`, `_compare_quality` | `return EXIT_PIPE_CLOSED` and `return TOOL_FAILURE_EXIT` to `None` | testable | Reported as errors (timeouts under load); no test existed for a closed stdout or an unwritable `--output` of `--compare-quality`. Both added and each shown to fail against its mutant. |
| `cli.py:286` `RunPlan` | `frozen=True` to `False` | untestable in a run | An error, like the nine pardoned decorators, but unpardoned and not in `test_value_objects_are_frozen`. See below. |
| `context.py:80` `restrict_to_local=False` | default to `True` | killed outside the run | An error (timeout). `test_graph_context_is_asserted_scope_aware_and_immutable` fails on it when run alone; no change needed. |

The new and strengthened tests were seen to fail against their mutant before the commit (mutants applied by
hand, then reverted). The two commits are test-only.

## What the maintainer should expect from the hosted run

- **Unpardoned `@dataclass(frozen=True)` in the scope.** The pardon table lists nine. About 26
  more frozen decorators sit in scope modules without a pardon (`baseline.py`, `datasets.py`,
  `cli.py` `RunPlan`, `engine.py`, `quality.py`, `loader.py`, `reporting.py`, `adapters/shacl.py`,
  `rules/measurements.py`, `rules/hierarchy_quality.py`). The same mechanism that made the nine
  pardons necessary applies to them: each is likely to be reported as an error, which counts
  against the score. Only `RunPlan` was observed here. The previous local run (53 errors, 95.1%
  overall) already included such errors and passed, but the count grows with every new frozen
  value object. Choices, all the maintainer's: pardon them (more rows, the 5% limit has room: 35
  of about 2 400 is 1.5%), raise `mutant_timeout`, or leave the errors in the score.
- Errors from timeouts depend on the runner; a hosted run is the only evidence for them.
- The job's 120-minute limit is unproven for the current suite (the TODO notes the staleness
  test that runs every rule).

## What this audit does not prove

- It ran only `imports.py`, `context.py` and `cli.py`. It did not run the whole scope, `worker.py`,
  `baseline.py` and `datasets.py` (pardon readings above are by reading the code, not by running
  them), `rules/shacl_authoring.py` (the 40 survivors `TODO.md` names) or `quality.py`.
- It is one agent's reading. The 14 verdicts are the same kind of audit as the 2026-11-13 one,
  by the same kind of reviewer.
- No hosted run was started, no variable was touched.

## Steps that remain with the maintainer

1. Review this page and the 14 pardon rows of `docs/mutation-pardons.md`; record the approval (a
   review of the pull request that carries this page is what the policy asks for). Decide on #14
   (`daemon=True`): accept it, or ask for a test that spies on the `Process` call and drop the
   pardon.
2. Start "Run workflow" (Validation, `main`, advisory). Check that it finishes inside the 120
   minutes and that `mutation_gate.py` passes in blocking mode on its report.
3. Set the repository variable `MUTATION_GATE_MODE=blocking`.
4. Wait for one scheduled Monday run to pass, then close issue #19.
