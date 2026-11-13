# Mutation pardons

A pardon (`# gremlin: pardon[<reason>] <justification>`) removes mutants from the score of a
mutation run (`docs/mutation-policy.md`). This page lists every active pardon, with the mutant it
removes and why that mutant cannot be killed. `tests/test_mutation_pardons.py` fails when the source
and this table disagree, so a pardon cannot be added, moved or widened without changing this page,
and the pull request that changes it is where the reviewer approves it.

## Rules

pytest-gremlins applies a pragma to a whole line: an inline pragma pardons its own line, and a
pragma on a comment line pardons the line below. Every mutant on that line is pardoned, whichever
one the justification is about. So:

- A pardoned line carries exactly one mutant. Put the equivalent expression on a line of its own;
  the other mutants of the statement then still run.
- A pragma sits in a module of the mutation scope (`paths` in `pyproject.toml`). Outside it, it
  pardons nothing today and would pardon without review once the module enters the scope.
- A pragma pardons a mutant. Code inserted between a comment-line pragma and its line moves the
  pardon onto the inserted line, where it may pardon nothing.
- Prefer a test to a pardon. A mutant that changes anything a caller can observe (a value, an
  exception, a message, a hash) is not equivalent, even when no current caller looks.

## Active pardons

The test compares the module, the pardoned line (stripped of indentation; a decorator followed
by the line it decorates) and the mutant with the source.

| Module | Pardoned line | Mutant | Why it cannot be killed in a run |
| --- | --- | --- | --- |
| `src/ontolint/adapters/shacl.py` | `@dataclass(frozen=True) class _ValidationJob:` | boolean: True to False | Untestable in a run, killed outside it (see below). |
| `src/ontolint/context.py` | `@dataclass(frozen=True) class GraphContext:` | boolean: True to False | Untestable in a run, killed outside it (see below). |
| `src/ontolint/cli.py` | `rows = zip(inputs, graphs, shared, strict=True)` | boolean: True to False | `graphs` has one graph per input (any input that fails to parse ends the run with exit 2 before this line), and `shared` is either `shared_identities(inputs, ...)`, one tuple per input, or `[()] * len(inputs)`, so `strict` never fires. |
| `src/ontolint/cli.py` | `@dataclass(frozen=True) class ImportOptions:` | boolean: True to False | Untestable in a run, killed outside it (see below). |
| `src/ontolint/imports.py` | `@dataclass(frozen=True) class Catalog:` | boolean: True to False | Untestable in a run, killed outside it (see below). |
| `src/ontolint/imports.py` | `@dataclass(frozen=True) class Closure:` | boolean: True to False | Untestable in a run, killed outside it (see below). |
| `src/ontolint/loader.py` | `@dataclass(frozen=True) class ImportChoice:` | boolean: True to False | Untestable in a run, killed outside it (see below). |
| `src/ontolint/loader.py` | `@dataclass(frozen=True) class ImportShadow:` | boolean: True to False | Untestable in a run, killed outside it (see below). |
| `src/ontolint/loader.py` | `@dataclass(frozen=True) class _ParseJob:` | boolean: True to False | Untestable in a run, killed outside it (see below). |
| `src/ontolint/reporting.py` | `@dataclass(frozen=True) class Origin:` | boolean: True to False | Untestable in a run, killed outside it (see below). |
| `src/ontolint/baseline.py` | `pairs = zip(report.findings, ids, strict=True)` | boolean: True to False | `ids` is built from `report.findings` on the line above, so both have the same length and `strict` never fires. |
| `src/ontolint/datasets.py` | `for triple, positions in zip(triples, cast(list[object], of), strict=True):` | boolean: True to False | The function raises `ValueError` above when `of` and `triples` differ in length, so `strict` never fires. |
| `src/ontolint/worker.py` | `receiver, sender = context.Pipe(duplex=False)` | boolean: False to True | The parent only reads `receiver` and the worker only writes `sender`; a duplex pipe offers a direction nothing uses. |
| `src/ontolint/worker.py` | `process = context.Process(target=_worker_main, args=(sender, task, rdflib_level), daemon=True)` | boolean: True to False | `run_bounded` stops and reaps the worker in `finally`, so `daemon` only matters when the parent dies, which a test of the parent cannot observe. |

A class decorator runs when its module is imported, so every test covers its mutant. pytest-gremlins
then selects the whole suite, whose unmutated run exceeds the 30 s mutant timeout, and reports
the mutant as an error that counts against the score, however fast a test would kill it.
`test_value_objects_are_frozen` in `tests/test_mutation_pardon_audit.py` kills each of these in
the normal suite (`frozen` is a contract of these values: they are handed between stages, cached
or sent to a worker). A frozen decorator without a pardon shows up as such an error; pardon it the
same way only together with a row here and that test.

## Audits

- 2026-11-13 (issue #19): all 31 pragmas of `main` at 0.13.1 were read against their lines, and
  every mutant they covered was applied by hand and run against the non-slow suite. 19 were
  removed: 9 whose mutants change results and are now killed, 4 whose line was rewritten to hold
  no mutant (`min`, `sorted`, a set intersection, two `if`s), 5 on `frozen=True` outside the
  mutation scope, where they pardoned nothing, and 1 that was wrong: `override=False` in
  `imports.py` changed the prefixes of a merged import closure, a bug fixed in the same change.
  The 8 `frozen=True` pragmas in scope stay, re-justified as above and backed by a test. The
  `baseline.py` pragma now covers only its `strict=True`, and the `daemon=True` pragma, which had
  drifted onto a line inserted above it, is back on its line. The audit was made by an AI agent
  (Claude), not by a human reviewer other than the author; the approval the policy requires is
  the maintainer's review of that pull request. The same change added two: the `frozen=True` of
  `GraphContext`, when `context.py` entered the scope, and the run-level `zip` of `cli.py`.
