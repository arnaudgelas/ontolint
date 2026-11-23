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

The closing steps run after a failed step too (`!cancelled()` is a status check, so no implicit `success()` applies); they
are skipped only when the run is cancelled or `cleanup` is `false`. After a cancellation, close the alerts by hand: upload an
empty SARIF report (`runs[0].results: []`) once per category (`ontolint-observe-plain`, `ontolint-observe-fp`,
`ontolint-observe-pair`), or re-run the workflow from the same branch with `cleanup` left on.

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

Record the outcome as a comment on issue #149 with the run's URL, and apply the decision of the table in a pull request that
closes issue #191's follow-up. Until then the answer to "should it be the default?" is no.
