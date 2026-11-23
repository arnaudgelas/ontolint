# Report compatibility policy

What may change in a JSON or SARIF document ontolint writes, in which release, and what a consumer may rely on.
Issue #170; the schemas it constrains are #171 and #172, the first enrichments #173 to #175.

ontolint is Alpha (0.x). This policy is what a consumer can pin against **now**; before 1.0 a breaking change needs a
version bump and a named changelog entry, and is never silent.

## The documents and their versions

| Document | Written by | Version key | Now | Read by ontolint? |
| --- | --- | --- | --- | --- |
| Lint report (`lint`) | `--format json` | `schema_version` | `1` | no |
| Rule listing (`rules-list`) | `--list-rules --format json` | `schema_version` | `1` | no |
| Rule detail (`rule-explain`) | `--explain RULE --format json` | `schema_version` | `1` | no |
| Quality snapshot (`quality-snapshot`) | `--write-quality-snapshot` | `format` (`ontolint-quality-snapshot`) and `version` | `1` | yes, `--quality-baseline` and `--compare-quality`: **closed**, refuses a version or a key it does not know |
| Baseline file (`baseline`) | `--write-baseline` | `version` | `2` | yes, `--baseline`: reads any version, ignores sections it does not know |
| SARIF report (`sarif`) | `--format sarif` | SARIF's own `version` (`2.1.0`); ontolint's additions are in `properties` | n/a | no |

The version keys differ for historical reasons and are **not renamed** (a rename is a breaking change). DQV output
(`--write-dqv`, Turtle) and the text and Markdown reports are not JSON documents and are outside this policy; the text and Markdown reports are
for people and may change in any release.

## What is additive (no version bump, any minor release)

For the lint report, the rule listing, the rule detail, the `quality_comparison` object inside a lint report, and the `properties`
of a SARIF report:

1. **A new key** in an object, or a new section.
2. **A new value of an open enumeration** (below).
3. **A key that appears only under an option or a condition** ("present only with `--measurements`", "present only when a
   baseline was read"): the report of a run that does not ask for it keeps its historical shape, byte for byte.

Every addition is **named** in the changelog under the document's name (the rows of the ledger below are copied there at release), keeps the
default output deterministic (the same input gives the same bytes), and is covered by the schema of the document (#171, #172).

**Consumers must ignore keys they do not know**, and a value of an open enumeration they do not know. The shipped schemas leave objects
open (`additionalProperties` is not `false`) for exactly this reason.

### Closed and open enumerations

| Enumeration | Where | Values | Adding a value |
| --- | --- | --- | --- |
| severity | `findings[].severity`, `rules[].severity`, `default_severity`, `summary` keys | `error`, `warning`, `info` | **breaking** (closed) |
| confidence | `findings[].confidence` | `certain`, `heuristic` | **breaking** (closed) |
| execution status | `executions[].status`, `execution_summary` keys | `executed`, `skipped`, `unsupported`, `failed` | **breaking** (closed) |
| rule category | `rules[].category` | as the catalogue says | additive (open) |
| backend, scope, requires, family | `rules[]` | as the catalogue says | additive (open) |

A consumer that switches on a closed enumeration may treat an unknown value as an error; on an open one it must not.

## What is breaking (version bump, changelog "Breaking changes")

- Removing or renaming a key.
- Changing the **type** of a key, or its **meaning or unit** (a ratio that becomes a percentage, a count that starts to include something).
- Changing a **documented ordering**. The documented orderings are: the findings of one file are sorted by severity (`error`, `warning`,
  `info`), then rule id, then focus, then message; the files and executions keep the order of the arguments and of the engine; lists the
  documentation calls "sorted" are sorted (`stale_fingerprints`, the quality snapshot's term lists).
- Adding a value to a closed enumeration, or removing a value from any enumeration.
- Making a key that a consumer may rely on to be present optional.
- For a document ontolint **reads**: any change to the quality snapshot (its reader is closed: it refuses a key it does not know), and a change
  to the baseline that an older ontolint would read wrongly (a section it must not ignore).

A breaking change increments the document's version key in the same release. It needs either the deprecation window below or a changelog entry
that says why the window was impossible.

## Deprecation

A key to be removed or renamed is **kept beside its replacement for at least one minor release** and named in the changelog as deprecated in
that release; it is removed in a later minor release, named again. A change of type or meaning has no window: it is a new key plus a
deprecation of the old one.

## SARIF

SARIF 2.1.0 fields keep their standard meaning: ontolint never changes the meaning of a standard field. It extends the report only
through property bags (`run.properties`, `result.properties`, `reportingDescriptor.properties`, `invocation.properties`,
`notification.properties`) and `partialFingerprints`. Names already in use (`details`, `evidence`, `graphs`, `modules`, `category`,
`backend`, `scope`, `executionSummary`, `status`, `results`) keep their names and meanings. **A new property name starts with `ontolint`**
(for example a future `ontolintCatalogue`), so it can never collide with a property name SARIF or a consumer reserves. Fingerprint keys carry a version in their
name (`ontolintIdentity/v2`, `ontolintFingerprint/v1`): a changed meaning is a new name with a new version, and the old one is deprecated as above.
A new `ontolint*` property is additive; the report still validates against the SARIF 2.1.0 schema (`tests/test_sarif_schema.py`).

## Frozen samples and the checks

`tests/fixtures/reports/0.16.0/` holds real 0.16.0 outputs, generated from the `v0.16.0` tag (`manifest.json` records each command): the lint report in
eleven shapes (default, clean, empty ontology, `--measurements`, `--quality-baseline`, `--baseline` with stale entries, `--shapes`, a failed
rule (exit 2), several files, module grouping, a profile), the rule listing, the rule detail, a quality snapshot, a baseline file and two SARIF reports. They are never regenerated from newer code; a missing shape gets a new sample from its own tag.
The SARIF `partialFingerprints` keys are not sampled yet (both SARIF samples are generated without `--sarif-fingerprints`), so nothing here protects them until a sample is added.
`tests/test_report_compatibility.py` runs the same commands with the current code and requires that:

1. **every key path and type of a sample is still there** (nothing removed, renamed or retyped; keys that hold data, such as the severity
   names under `summary` or the hashes under a baseline's `identities`, are compared as `{*}`);
2. **every key path the current output adds is listed in the ledger below**, so an addition cannot ship without being named;
3. the samples, the manifest and the ledger agree, and this page is linked from the README.

The same samples also validate against the shipped JSON Schema of the lint report, `ontolint/schemas/lint-report.v1.schema.json`
(`tests/test_report_schema.py`, issue #171); the schemas of the other documents are issue #172.

### Ledger: additions since the 0.16.0 samples

One row per added key path; copy the rows into the changelog under the document's name at release. The keys of 0.17.0 are the same as 0.16.0's.

| Document | Key path | Added in |
| --- | --- | --- |
