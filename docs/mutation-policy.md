# Mutation testing policy

Mutation testing measures whether the tests detect deliberate faults. This
policy defines what is mutated, the minimum scores, how survivors are handled,
and when the gate blocks. It is enforced by `.github/scripts/mutation_gate.py`
in `.github/workflows/validation.yml`.

## Tooling and command

```bash
uv run pytest -p no:randomly -m 'not slow' --gremlins --no-cov --gremlin-parallel --gremlin-cache
```

`-p no:randomly` keeps the test order fixed: the normal suite shuffles it (pytest-randomly), and a
mutation run should be repeatable.

On a large suite the coverage pre-scan can exceed its default 120 s limit, which
disables coverage-guided test selection: every mutant then runs the whole suite, and
the scheduled run does not finish within the job's two-hour timeout. `pyproject.toml`
therefore sets `coverage_timeout = 900`; raise it if the warning
`coverage pre-scan exceeded` appears in `mutation.log`.

The command excludes the tests marked `slow` (the Hypothesis property tests and the
fuzz tests). They exercise every rule, so gremlins would select them for almost every
mutant and a run would take hours instead of minutes. They still run in the normal
suite (`uv run pytest`) and in the scheduled fuzz job.

One test that exercises every rule is not marked `slow`, on purpose:
`tests/test_rule_docs.py::test_rule_reference_is_current` builds the rule
reference, which runs the linter on each of the 778 flagged graph cases, and
fails when a mutant changes a message any of them reports. The build takes
about 7 s on an idle laptop (0.3 s when it ran one case per rule), most of it
in the scale cases of CLS014, CLS021, CLS025 and SEC004. gremlins selects the
test for nearly every mutant of `rules/`, but it runs a mutant's tests most
specific first (those covering the fewest lines) and stops at the first
failure, so this broad test runs only when no narrower one kills the mutant:
chiefly for survivors. If the scheduled job nears its timeout, check its share
with `--durations` before marking it `slow`, since that would give up the
messages it pins.

Do not run any other pytest session in the same checkout while a mutation run is in
progress. The run pre-scans coverage into the repository-root `.coverage` (statement
data), and a concurrent `pytest -n auto` writes branch-coverage worker files that
cannot be combined with it, which aborts that session with `coverage.exceptions.DataError:
Can't combine branch coverage data with statement data`. If it happens, stop both runs,
delete `.coverage` and `.coverage.*`, and start again.

CI adds `--gremlin-report=console,json,html --gremlin-max-pardons-pct=5
--gremlin-audit-pardons`. Reports are written to `coverage/gremlins/`
(`gremlins.json`, HTML) and uploaded as the `mutation-reports` artifact.

pytest-gremlins 1.13.x has no minimum-score option. It does provide
`--strict-pardons`, `--max-pardons` and `--gremlin-max-pardons-pct` for
suppression limits. Score thresholds are therefore enforced by
`mutation_gate.py`, which reads `gremlins.json` and applies the same formula as
the library: `(zapped + timeout) / (total - pardoned)`. Survived and errored
mutants count against the score.

## Operators

The operator set in `[tool.pytest-gremlins]` is the policy set. The gate fails
if a report contains an operator outside this table.

| Operator | Mutations | Minimum score |
| --- | --- | --- |
| comparison | `<`, `<=`, `>`, `>=`, `==`, `!=` swaps | 85% |
| arithmetic | `+ - * / // % **` swaps | 85% |
| boolean | `and`/`or`, `True`/`False`, `not x` removal | 90% |
| boundary | constants shifted by +/-1 in comparisons | 80% |
| return | return values replaced by `None`, empty or negated | 80% |
| **Overall** | all of the above | **85%** |

Boolean has the highest bar because it was the original gate and guards rule
logic. Boundary and return mutants produce more equivalent mutants and have the
lowest bar. Raise a threshold only after two consecutive scheduled runs exceed
it by 5 points; lowering one requires the waiver process below.

## Scope

In scope: the engine, linter, CLI, loader, the cached graph facts every rule reads (`context.py`), the bounded worker (`worker.py`), import closure, reporting, the quality snapshot (`quality.py`), source locations, `adapters/` and `rules/`
(the `paths` setting in `pyproject.toml`). Out of scope: tests, `docker/`,
`.github/`, and modules not listed in `paths`. Adding a source module
to `paths` is a policy change: it enters in advisory mode until it meets the
thresholds in a scheduled run, then becomes blocking. `paths` must be updated in the
same change that moves logic, so that scope never silently shrinks.

## Survivor triage and waivers

Every survivor or errored mutant listed in the gate output must be resolved
within the next two scheduled runs by one of:

1. Kill it: add or strengthen a test (preferred).
2. Remove dead code that makes the mutant equivalent.
3. Pardon it with a gremlins pragma carrying a reason and justification,
   on a line that holds only that mutant, with a row in `docs/mutation-pardons.md`
   (`tests/test_mutation_pardons.py` enforces both). A reviewer other than
   the author must approve the pragma in the PR. Two reasons are allowed:
   - `equivalent`: an equivalent mutant, or an unobservable side effect;
   - `untestable`: an observable mutant that the run cannot execute in time. This
     is a tool limitation, not an equivalence, so it is allowed only for a
     `@dataclass(frozen=True)` decorator (it runs at import, so every test covers
     it and the selected suite exceeds the mutant timeout), only when a test of
     the normal suite kills the mutant (`test_value_objects_are_frozen`), and only
     until the expiry and remediation plan of issue #71 (the next quarterly audit,
     2027-02-13). By then the mutant runs in a mutation run, or a reviewed PR
     renews the pardon with what was tried.
4. Waive a threshold temporarily: open an issue naming the operator, current
   score, owner and expiry date (at most 30 days) and link it in the PR that
   lowers the constant in `mutation_gate.py`.

Pardons are limited to 5% of mutants (`--gremlin-max-pardons-pct=5`). Run
`uv run pytest -m 'not slow' --gremlins --gremlin-audit-pardons` to list active pardons;
review them quarterly. `docs/mutation-pardons.md` lists them with their mutants and
records each audit.

## Blocking versus advisory

| Context | Mode |
| --- | --- |
| Pull requests | Not run (kept out of the fast path). |
| Weekly schedule | Advisory by default; blocking when the repository variable `MUTATION_GATE_MODE` is `blocking`. |
| Manual dispatch | Chosen by the `mutation_mode` input. |

Advisory mode reports violations as warnings and still uploads artifacts.
Blocking mode fails the job on any threshold violation, an out-of-policy
operator, a missing report, or a non-zero pytest exit status. Set
`MUTATION_GATE_MODE=blocking` once a baseline run meets every threshold; the
first scheduled runs establish that baseline, which is why the default is
advisory. A release must not be cut while the latest scheduled run is red in
blocking mode.
