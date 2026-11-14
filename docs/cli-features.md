# Command-line and report features

The original roadmap listed 18 `OPS` entries in the rule catalogue. They describe how the tool
runs and reports, not defects in an ontology, so they are not lint rules and no longer appear in
`data/rule_catalogue.csv`. This page tracks them as features instead.

Status values: **exists** (implemented and tested), **partial** (some of it exists), **TODO**.

| ID | Feature | Status | Notes |
| --- | --- | --- | --- |
| OPS001 | Run summary with counts per severity and per rule | partial | JSON and SARIF carry per-severity and execution summaries; per-rule counts are not reported. |
| OPS002 | Baseline file that suppresses known findings | exists | `--write-baseline` and `--baseline`. A finding is matched by its identity (rule, focus, subject) under its report path or by its version 1 fingerprint (rule, focus, message), so a reworded message stays baselined and one-file and multi-file baselines carry over; a fingerprint that a version 2 file pairs with an identity accepts a finding only in place of an accepted one that is gone (README "Policy and baselines"). |
| OPS003 | Report baseline entries that no longer match any finding | exists | Reported in text, JSON (`baseline.stale_fingerprints`) and SARIF; `--fail-on-stale-baseline` exits 1. An entry is stale when neither its fingerprint nor its identity matched. Entries of rules not selected in the run count as stale. |
| OPS004 | Fail only on new findings | exists | Findings in the baseline do not gate the exit code. |
| OPS005 | SARIF output with complete rule metadata | exists | `--format sarif`; every report shape is validated against the vendored OASIS SARIF 2.1.0 schema in the tests. |
| OPS006 | Record tool and catalogue versions in reports | partial | SARIF records the tool version; the catalogue version is not recorded. |
| OPS007 | Deterministic output across runs | exists | Covered by the differential golden tests. |
| OPS008 | Validate the configuration file and report unknown keys | exists | Known keys are validated; unknown keys are reported by `GOV020` and an unsupported `policy_version` is rejected (exit 2). |
| OPS009 | Report ignores or severity overrides that name unknown rules | exists | Unknown `--select`/`--ignore` selectors are errors (`TOOL001`), and so are selectors that name only pipeline rules (the safe-loader refusals, `INPUT001`, `TOOL001`), which no selection changes; unknown or pipeline-rule IDs in the policy file's `ignored_rules` or `severity_overrides` are rejected with `GOV020` (exit 2). |
| OPS010 | Report a run that exceeds its time or resource budget | partial | `--max-parse-seconds` and the size limits reject an input (`SEC003`, `SEC001`, `SEC002`); `--max-validation-seconds` stops SHACL validation (a `failed` `SHACL001`, exit `2`); the rule families have no time budget. |
| OPS011 | Per-rule timing in the report | TODO | |
| OPS012 | Additional report formats (JUnit, Markdown, HTML) | partial | `text`, `json`, `sarif` and `markdown` exist. `markdown` is a summary of the run for a pull request, not a parsing contract (README "Pull-request summary (Markdown)"). JUnit and HTML are not planned without a consumer; CTRF-REPORT takes JUnit's place (TODO.md). |
| OPS013 | Aggregated report across several files | exists | Several inputs are linted independently and reported with per-file totals. |
| OPS014 | Lint only files or lines changed in a git diff | TODO | |
| OPS015 | Inline suppression with a mandatory reason | TODO | Needs a way to attach a suppression to an RDF term. |
| OPS016 | Suppressions that expire after a date | TODO | Depends on OPS015. |
| OPS017 | Result cache keyed by graph content | TODO | |
| OPS018 | Explain the reasons behind exit code 2 | partial | Failed and unsupported rules are listed in the report with their detail. The Markdown summary says that the run exits `2` because N rule runs delivered no verdict, and lists the first 20 of them; the JSON and SARIF reports do not state the reason for the exit code as a whole. |
