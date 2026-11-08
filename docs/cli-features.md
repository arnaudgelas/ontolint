# Command-line and report features

The original roadmap listed 18 `OPS` entries in the rule catalogue. They describe how the tool
runs and reports, not defects in an ontology, so they are not lint rules and no longer appear in
`data/rule_catalogue.csv`. This page tracks them as features instead.

Status values: **exists** (implemented and tested), **partial** (some of it exists), **TODO**.

| ID | Feature | Status | Notes |
| --- | --- | --- | --- |
| OPS001 | Run summary with counts per severity and per rule | partial | JSON and SARIF carry per-severity and execution summaries; per-rule counts are not reported. |
| OPS002 | Baseline file that suppresses known findings | exists | `--write-baseline` and `--baseline`. |
| OPS003 | Report baseline entries that no longer match any finding | TODO | Stale fingerprints stay in the file silently. |
| OPS004 | Fail only on new findings | exists | Findings in the baseline do not gate the exit code. |
| OPS005 | SARIF output with complete rule metadata | partial | `--format sarif` exists; it is not validated against the SARIF schema. |
| OPS006 | Record tool and catalogue versions in reports | partial | SARIF records the tool version; the catalogue version is not recorded. |
| OPS007 | Deterministic output across runs | exists | Covered by the differential golden tests. |
| OPS008 | Validate the configuration file and report unknown keys | exists | Known keys are validated; unknown keys are reported by `GOV020` and an unsupported `policy_version` is rejected (exit 2). |
| OPS009 | Report ignores or severity overrides that name unknown rules | partial | Unknown `--select`/`--ignore` selectors are errors; `ignored_rules` in the policy file is not checked. |
| OPS010 | Report a run that exceeds its time or resource budget | partial | `--max-parse-seconds` and the size limits reject an input (`SEC003`, `SEC001`, `SEC002`); the lint phase has no time budget. |
| OPS011 | Per-rule timing in the report | TODO | |
| OPS012 | Additional report formats (JUnit, Markdown, HTML) | TODO | `text`, `json` and `sarif` exist. |
| OPS013 | Aggregated report across several files | exists | Several inputs are linted independently and reported with per-file totals. |
| OPS014 | Lint only files or lines changed in a git diff | TODO | |
| OPS015 | Inline suppression with a mandatory reason | TODO | Needs a way to attach a suppression to an RDF term. |
| OPS016 | Suppressions that expire after a date | TODO | Depends on OPS015. |
| OPS017 | Result cache keyed by graph content | TODO | |
| OPS018 | Explain the reasons behind exit code 2 | partial | Failed and unsupported rules are listed in the report with their detail. |
