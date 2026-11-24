# Scheduled checks

What runs on a timer, how long it may take, who owns it and what a failure means. Everything here is **advisory**:
none of it is a required status check, and a red scheduled run blocks no merge. A release is blocked by its own gate and
by the reviewer of the release (`docs/releasing.md`), not by these jobs.

| Workflow | Cron (UTC) | Timeout (minutes) | What it checks | Owner | A failure blocks | Triage |
| --- | --- | --- | --- | --- | --- | --- |
| [`fuzz.yml`](../.github/workflows/fuzz.yml) | `43 4 * * 1` | 40 | Mutation-based fuzzing of the loader, the rules, the CLI and the policy parser, a longer budget and a fresh seed per target. | maintainer | nothing | A crasher is a bug: reproduce it with the command in the workflow header, fix it, move the minimised file to `tests/fuzz/regressions/`. Within the week. |
| [`validation.yml`](../.github/workflows/validation.yml) | `17 3 * * 1` | 20, 120 | The ROBOT Docker image build and conversion smoke test; mutation testing (`docs/mutation-policy.md`). | maintainer | nothing; the mutation gate is advisory unless dispatched in `blocking` mode | The ROBOT job: the image or a converter changed. Mutation: new survivors are killed by a test or pardoned (`docs/mutation-pardons.md`). |
| [`corpus.yml`](../.github/workflows/corpus.yml) | `11 5 * * 1` | 45 | The pinned validation corpus against what the repository recorded: findings per rule and file (`scripts/corpus_counts.py check`), the METRIC measurements (`scripts/metric_corpus.py check`) and the SHQ001-SHQ003 scope counts on production shapes (`scripts/shq_scope_count.py check`). | maintainer | nothing; the release owner reviews the same diff at every release (`docs/releasing.md`, step 2) | Read the diff in the job summary or the `corpus-diff-N` artifact. A rule that doubled or a file that now exits 2 needs a cause. A change that is explained is recorded (`record`, `measure`, `count`) in the next commit that touches the rule. An upstream repository that vanished fails `fetch`: the commit is pinned, so it is the hosting that changed. |
| [`benchmarks.yml`](../.github/workflows/benchmarks.yml) | `27 6 * * 1` | 45 | The large-ontology benchmarks (`tests/benchmarks`, `ONTOLINT_BENCH=1`): a peak-memory budget per scenario and the growth of the whole linter between two sizes (a ratio, never seconds). The profile of each scenario is kept as an artifact. | maintainer | nothing | A red ratio test is a complexity regression: profile the scenario with the command in `docs/performance.md`, find the quadratic step, add it to `tests/test_scaling.py`. A red memory budget: profile with `tracemalloc` and fix or re-measure and justify the new budget. Within the week. |

`corpus.yml` is green when nothing moved and red, with the diff, when something did. It needs the network (GitHub and the
hosts of the calibration files) and fetches into the runner's temporary directory; nothing it downloads is committed
(`docs/validation/corpus.md`).

### Reproduce a run

The artifact is optional: the same diff is one command away on any machine with the network.

```bash
uv run python scripts/corpus.py fetch DIR
uv run python scripts/corpus_counts.py check DIR      > rule-counts.md
uv run python scripts/metric_corpus.py check DIR      > metric-corpus.txt
uv run python scripts/shq_scope_count.py fetch DIR_SHQ
uv run python scripts/shq_scope_count.py check DIR_SHQ > shq-scope.txt
```

`corpus.yml` compares with the counts committed in the repository, not with the previous run: after a change that is
explained but not yet recorded, it stays red every week until `record`, `measure` or `count` is committed. A run that
is cancelled or times out still uploads what the checks had written; the job log has the rest.

The workflows that run on a push or a pull request (`ci.yml`, `smoke.yml`, `release.yml`) are not listed: they are not
on a timer. Tests that are skipped unless an `ONTOLINT_*` switch is set (`ONTOLINT_FUZZ`, `ONTOLINT_BENCH`,
`ONTOLINT_JENA_HOME`, `ONTOLINT_ROBOT_IMAGE`) and the check of issue #165 get their rows when the table that
issue #166 asks for covers them; this one holds the scheduled workflows that exist.
