# SARIF `partialFingerprints`: the observation and the decision

`--sarif-fingerprints` (README, "SARIF `partialFingerprints`") writes `ontolintIdentity/v2` and, for shared identities,
`ontolintFingerprint/v1` on every SARIF result. GitHub code scanning documents only `primaryLocationLineHash`, so whether it
uses these keys to match alerts across uploads is unknown until an upload shows it (issue #149). The flag therefore stays
**opt-in in 0.17.0** (issue #191); this page says how to observe, how to read the result, and what each reading decides.

## Why it stays opt-in until observed

Turning the flag on changes the fingerprint of every alert that exists, so the next upload closes the old alerts and opens new
ones once. That cost is certain; the benefit (alerts that survive a re-serialization, and results that share a rule and a line
staying apart) depends on GitHub honouring keys it does not document. A default that may do nothing for its users and reopens
their alerts is not worth shipping on an assumption, and an observation costs one manual run.

## Observe

`.github/workflows/observe-sarif-fingerprints.yml` is a manual workflow, never a check. Run it from a **throwaway branch** of
a repository with code scanning enabled (the alerts belong to that ref and to categories `ontolint-observe-*`; the last
steps close them with empty reports):

```bash
git switch -c observe-sarif-fingerprints && git push -u origin HEAD
gh workflow run observe-sarif-fingerprints.yml --ref observe-sarif-fingerprints
gh run watch
```

Every upload is a job of its own (`plain`, `fp`, `reserialized`, `pair`), chained with `needs`, because
`github/codeql-action/upload-sarif` accepts **one upload per category per job** ("only one run of the codeql/analyze or
codeql/upload-sarif actions is allowed per job per tool/category"): the experiment re-uploads to the `fp` category to see whether
its alerts stay, and closes each category it opened, which no single job can do. The last job, `cleanup`, closes the three
categories with empty reports. It runs after a failed job too (`!cancelled()` is a status check, so no implicit `success()` applies)
and is skipped only when the run is cancelled or `cleanup` is `false`. After a cancellation, close the alerts by hand: upload an
empty SARIF report (`runs[0].results: []`) once per category (`ontolint-observe-plain`, `ontolint-observe-fp`,
`ontolint-observe-pair`), or re-run the workflow from the same branch with `cleanup` left on.

The first run (run 45125513939, 2026-11-23) failed twice before it observed anything: the Action cannot run twice in one job
(`uv venv` refused the environments the first use left in `$RUNNER_TEMP`; fixed in the Action), and the closing upload to a category
already uploaded to in the same job was refused (fixed by this layout). It left the alerts of the `plain` category open on the
branch it ran from; a run of this workflow from that branch, once the branch carries the fix, closes them.

It lints `tests/fixtures/kitchen_sink.ttl` with the Action of the checkout (which installs the release its `pyproject.toml`
names, so that release must carry the flag: 0.16.0 and every later release do), uploads four SARIF reports, queries the alerts API after each and
writes a table to the job summary, with the reports and the alert lists kept as an artifact for 30 days:

| Upload | Category | What it answers |
| --- | --- | --- |
| the file, no flag | `ontolint-observe-plain` | how many alerts GitHub makes from 138 results on its own |
| the file, with the flag | `ontolint-observe-fp` | whether the alert count follows the results or the identities |
| the same graph re-serialized, same path and category | `ontolint-observe-fp` | whether the alerts stay the same alerts (numbers) or are closed and reopened |
| two files with one rule, focus, subject and message | `ontolint-observe-pair` | whether identical fingerprints with different artifact URIs stay two alerts |

The summary also counts the results that have no region (ONT002, LEX007 and SEC007 in the fixture: 3) and the open alerts for
those rules, which is the answer to whether a result without a location becomes an alert at all.

## Read it

| Observation | Meaning | Decision |
| --- | --- | --- |
| the re-serialized upload keeps the alert numbers and fixes none; the pair stays two alerts | GitHub honours the custom keys | make the flag the default in the next minor release, with an upgrade note (every alert reopens once), the Action input defaulting to `true`, and an escape hatch (`--no-sarif-fingerprints`, `sarif-fingerprints: "false"`) that restores today's bytes; the `sarif_default`, `sarif_shapes` and `multi_file_sarif` goldens change in the same commit |
| the re-serialized upload fixes and reopens alerts | GitHub ignores the custom keys | write `primaryLocationLineHash` (identity plus an occurrence index) instead, observe again, and only then consider a default |
| the pair becomes one alert | identical fingerprints collapse | keep `ontolintFingerprint/v1` out of the shared case or add the occurrence index; observe again |
| results without a region have no alerts | expected: code scanning needs a location | document it; no change |

## Result

One run observed it: [run 46123087281](https://github.com/arnaudgelas/ontolint/actions/runs/46123087281), dispatched on
2026-11-28 from the branch `observe-sarif-fingerprints` at commit `26ddd42`, every job green. The kitchen sink gave 138 results,
3 of them without a region (ONT002, LEX007, SEC007). The job summary, and the reports and alert lists kept as the run's
artifact, say (a category is that of an alert's most recent instance):

| Observation | Value |
| --- | --- |
| alerts already open when the run started | 138 (numbers 4 to 141, created 2026-11-23 by the failed first run: 135 last seen in `ontolint-observe-plain`, 3 in `ontolint-observe-fp`) |
| open alerts, category `ontolint-observe-plain` (no flag) | 135 |
| open alerts, category `ontolint-observe-fp`, after the first upload | 138 (the numbers 4 to 141: none new) |
| open alerts, category `ontolint-observe-fp`, after the re-serialized upload | 138 |
| of those, numbers that were also in `ontolint-observe-fp` after the first upload | 3 (31, 109, 138: the three results without a region) |
| of those, new alerts | 135 (numbers 142 to 276) |
| alerts still open after the re-serialized upload, last seen in `ontolint-observe-plain` | 135 (the numbers 4 to 141 except 31, 109 and 138) |
| alerts listed as fixed after the re-serialized upload | 0 |
| open alerts, category `ontolint-observe-pair` (15 results in two files) | 15 |

What it shows, each point read from those lists:

* **GitHub did not use `ontolintIdentity/v2` to match alerts.** The two reports carry the same 138 identities, yet 135 of the 138
  alerts of the re-serialized upload are new alerts. The three that kept their numbers are the results without a region, whose
  location (line 1) did not move. This is the second row of the table in "Read it": write `primaryLocationLineHash` instead,
  observe again, and only then consider a default. The flag stays **opt-in**. The report carries no `primaryLocationLineHash`;
  the alerts were matched on a value GitHub computed itself (the upload prints "Adding fingerprints to SARIF file"), which this
  run did not read back.
* **The 135 alerts the re-serialized upload did not match are still open**, with their latest instance in the `plain` category, which
  that run did not upload again. That is why none was listed as fixed. The alerts of the two categories are therefore not
  independent: one alert can hold an instance of each, and a category's count is not the number of alerts that upload created.
* **The first upload with the flag did not reopen anything**: its 138 alerts are the 138 that were already open, with their numbers,
  including the 135 an upload without the flag had made. In this run the flag changed no alert number, but the upload went to another
  category than the alerts' last instance; adopting the flag in one category of an existing repository was **not** observed, so the
  README's "the next upload closes the old alerts and opens new ones once" is neither confirmed nor refuted here.
* **A result without a region is not in the 135 alerts of the upload without the flag, and is one of the 138 of the upload with it**
  (alerts 31, 109 and 138, at line 1): the fourth row of the table expected no alert, and the flag changes that. The alerts existed
  before the run, so this reads the categories of the alerts, not what one upload alone creates.
* **Identical fingerprints in two files stayed two alerts** (15 results, 15 alerts), so the third row does not apply.

Not shown: the run did not try a result that moves inside its file without a re-serialization, two results of one rule on one
line, or a sibling finding added or removed (the experiments 1, 5 and 6 of the matrix on issue #149), and it started from alerts a
previous run had left open, so it does not isolate what one upload does to an empty branch.

The outcome is recorded on issue #149 with the run's URL. Until a run that writes `primaryLocationLineHash` shows alerts that
stay, the answer to "should it be the default?" is no.
