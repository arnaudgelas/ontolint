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
| [`jena.yml`](../.github/workflows/jena.yml) | `47 6 * * 1` | 15 | The tests that need Java, on Apache Jena 4.10.0 (a pinned Temurin 11, the zip checked against its published SHA-512, each jar against the digests in the tests): `riot` still writes the committed JSON-LD fixtures of `tests/fixtures/java_jsonld` up to the order the writers leave open, and `shacl validate` still does what `tests/fixtures/jena_shacl/cases.json` records for the values behind SHQ008, SHQ011 and SHQ015. | maintainer | nothing | A red checksum step: the archive changed or the download is corrupt; do not unpack it. A red riot test: a fixture no longer equals what Jena writes; regenerate as `tests/fixtures/java_jsonld/README.md` says, or find what changed in the JVM. A red SHACL test: Jena no longer does what the severity decision rests on (`docs/severity-decisions.md`, "Engine checks"); read the case, then decide the rule's severity again. Within the week. |

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

### Switches

A test that is skipped unless an `ONTOLINT_*` switch is set proves nothing until something sets it or runs the same
code. Each switch the suite skips on is here with the scheduled workflow that covers it: sets it, or, for
`ONTOLINT_FUZZ`, runs the same targets by another route (`tests/test_skip_inventory.py` fails when a `skipif`
reads a switch with no row, when a row names a workflow that does not exist, is not on a schedule or does not contain,
outside a comment, the text in the last column, and when a row names no workflow without being a developer tool; it checks
the text, not that the step runs). The platform skips (Windows, POSIX permissions) are guarded by `tests/test_platform_skips.py`; a missing tool (`actionlint`, `docker`, `uv`) is
neither.

| Switch | What it turns on | Workflow | Text the workflow holds |
| --- | --- | --- | --- |
| `ONTOLINT_BENCH` | the large-ontology benchmarks (`tests/benchmarks`) | [`benchmarks.yml`](../.github/workflows/benchmarks.yml) | `ONTOLINT_BENCH` |
| `ONTOLINT_FUZZ` | `test_long_fuzz`, the fuzz targets for 60 s each; `fuzz.yml` runs the same targets through the same driver for longer, not through pytest | [`fuzz.yml`](../.github/workflows/fuzz.yml) | `tests.fuzz.fuzzer` |
| `ONTOLINT_JENA_HOME` | the Jena `riot` round-trip test and the Jena SHACL checks (need Java) | [`jena.yml`](../.github/workflows/jena.yml) | `ONTOLINT_JENA_HOME` |
| `ONTOLINT_ROBOT_IMAGE` | the ROBOT conversion test (needs Docker) | [`validation.yml`](../.github/workflows/validation.yml) | `ONTOLINT_ROBOT_IMAGE` |
| `ONTOLINT_UPDATE_GOLDEN` | regenerating the golden snapshots; a normal run compares them and skips nothing it needs: a developer tool, not a schedule | none | none |

The workflows that run on a push or a pull request (`ci.yml`, `smoke.yml`, `release.yml`) are not listed: they are not
on a timer. The tests that a switch skips are in the table above.
