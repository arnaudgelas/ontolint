# METRIC calibration

This page is the method, the distributions and the recommendations behind the `METRIC001`-`METRIC013`
defaults (issue #8). **It changes no default, severity, confidence or rule behaviour.** What it adds is
evidence and a harness; every decision below is the maintainer's.

Read it with [`metric-thresholds.md`](metric-thresholds.md) (what each default is and how to override it) and
[`validation/metric-calibration.md`](validation/metric-calibration.md) (the per-file measurements, the proposed
labels and the false-positive counts).

## What this is, and is not

- The corpus is 21 public ontology files, pinned in
  [`validation/metric-corpus.json`](validation/metric-corpus.json): URL, commit (20 files; SKOS Core is the
  W3C namespace document, pinned by checksum only), licence and SHA-256. Nothing is vendored.
- The **labels are proposed, not approved** (`"label_status": "proposed"`). Whether an ontology is known-good
  or known-poor for a rule is the maintainer's judgement; the file records a reason and a basis for each label
  (`checked` in the file, or `presumed` from the file's standing). Most negatives are presumed.
- Every false-positive and false-negative count is conditioned on those labels. They are as good as the labels
  and no better. They are not a measurement of precision, and with one or two known-poor files for
  `METRIC001`-`METRIC003` and none for `METRIC004`-`METRIC013`, recall is not measured for most rules.
- Numbers are for ontolint 0.14.0. `check` reproduced the 0.13.1 results unchanged on 0.14.0 before this
  page's extra measurements were added.

## Method

```sh
uv run python scripts/metric_corpus.py fetch DIR     # download by pin, refuse a changed SHA-256
uv run python scripts/metric_corpus.py measure DIR   # lint, cross-check, rewrite the results and both pages
uv run python scripts/metric_corpus.py check DIR     # fail if the measurements changed
uv run python scripts/metric_corpus.py render        # rewrite the generated tables from the JSON files
```

Each file is linted alone, three times with `--select METRIC`: at the default policy (does the rule fire),
with a forced policy (every limit at the end of its range, so the message prints the value), and with
`--measurements` (the exact numerator and denominator of every figure the rules read,
[measurements.md](measurements.md)). The harness refuses to record a file unless the three agree: the vector
must give the value the forced message printed, and must give, through the rule's own sample gate and limit,
exactly the finding the default run reported. A rule that did not run, a report of another file, a
measurement of another definition version, or a checksum that differs is an error, never a silent figure.
The tests (`tests/test_metric_corpus.py`, `tests/test_metric_calibration.py`) run offline on a tiny fixture and
on the recorded results.

Distributions are over the files that make a comparison for a rule. A file below the rule's sample gate
(10 terms) or with an empty population is *excluded*, not counted as 0. The tables are generated: do not edit
them by hand.

<!-- metric_corpus.py: distributions begin -->
### Distributions

Per rule, over the 21 corpus files that make a comparison (a population at or above the sample
gate of the rule, and for METRIC004 a parent class). `n` is that number, `flagged` how many of the
21 files the default flags, `excluded` the files with no comparison. Quartiles are linear
interpolations (inclusive method) of exact fractions, printed to three decimals; METRIC001 to METRIC003
read the share that is *missing*. METRIC006 and METRIC007 read one measurement.

| Rule | n | flagged | excluded | Default | min | Q1 | median | Q3 | max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| METRIC001 | 16 | 1 | 5 | > 0.500 | 0.000 | 0.000 | 0.000 | 0.000 | 1.000 |
| METRIC002 | 16 | 2 | 5 | > 0.500 | 0.000 | 0.000 | 0.000 | 0.071 | 1.000 |
| METRIC003 | 16 | 2 | 5 | > 0.500 | 0.000 | 0.000 | 0.000 | 0.098 | 1.000 |
| METRIC004 | 14 | 1 | 7 | > 8.000 | 1.625 | 2.047 | 2.856 | 4.290 | 13.571 |
| METRIC005 | 16 | 0 | 5 | > 0.300 | 0.000 | 0.000 | 0.000 | 0.000 | 0.222 |
| METRIC006 | 16 | 3 | 5 | < 0.100 | 0.000 | 0.109 | 0.916 | 1.952 | 4.533 |
| METRIC007 | 16 | 0 | 5 | > 5.000 | 0.000 | 0.109 | 0.916 | 1.952 | 4.533 |
| METRIC008 | 14 | 4 | 7 | > 0.500 | 0.000 | 0.002 | 0.076 | 0.604 | 1.000 |
| METRIC009 | 18 | 3 | 3 | < 0.500 | 0.000 | 0.978 | 1.000 | 1.000 | 1.000 |
| METRIC010 | 17 | 2 | 4 | > 0.500 | 0.000 | 0.000 | 0.025 | 0.112 | 1.000 |
| METRIC011 | 21 | 1 | 0 | > 10 | 0 | 0 | 0 | 0 | 80 |
| METRIC012 | 14 | 0 | 7 | < 4.000 | 10.909 | 16.024 | 21.694 | 24.184 | 42.200 |
| METRIC013 | 21 | 0 | 0 | > 0.600 | 0.000 | 0.000 | 0.000 | 0.018 | 0.423 |

### Limits the labels allow

For each rule, the interval of limits that would give no false positive and no false negative under the
proposed labels, among the files that make a comparison. `[a, b)` means a limit of at least a and below b
for a rule that fires above its limit; `(a, b]` means above a and at most b for one that fires below it;
`none` means a silent and a fire label cross. The first column uses every counted label, including the
presumed silent ones; the second only labels whose reason was checked in the file. The default is inside
the interval only when it is marked yes, decided on the exact bounds and not on the four decimals printed
here. An interval is only as good as the labels.

| Rule | Default | All counted labels | Default inside | Checked labels only | Default inside |
| --- | --- | --- | --- | --- | --- |
| METRIC001 | 0.500 | [0.0000, 1.0000) | yes | [0.0000, 1.0000) | yes |
| METRIC002 | 0.500 | [0.3272, 1.0000) | yes | [0.0971, 1.0000) | yes |
| METRIC003 | 0.500 | [0.1754, 1.0000) | yes | [-inf, 1.0000) | yes |
| METRIC004 | 8.000 | [5.3661, +inf) | yes | [-inf, +inf) | yes |
| METRIC005 | 0.300 | [0.0455, +inf) | yes | [0.0455, +inf) | yes |
| METRIC006 | 0.100 | (-inf, 0.0000] | no | (-inf, 0.0000] | no |
| METRIC007 | 5.000 | [4.5333, +inf) | yes | [-inf, +inf) | yes |
| METRIC008 | 0.500 | [1.0000, +inf) | no | [1.0000, +inf) | no |
| METRIC009 | 0.500 | (-inf, 0.0000] | no | (-inf, 0.0000] | no |
| METRIC010 | 0.500 | [1.0000, +inf) | no | [1.0000, +inf) | no |
| METRIC011 | 10 | [80.0000, +inf) | no | [80.0000, +inf) | no |
| METRIC012 | 4.000 | (-inf, 10.9091] | yes | (-inf, +inf) | yes |
| METRIC013 | 0.600 | [0.2105, +inf) | yes | [-inf, +inf) | yes |
<!-- metric_corpus.py: distributions end -->

## Reading the results

- **METRIC001-METRIC003.** Bimodal: almost every file is at 0 missing, the poor ones at 1.0. The default 0.5 sits
  inside the interval the labels allow, with a wide margin on both sides, except that PATO base misses a
  definition for 0.33 of its classes: a mature OBO ontology 0.17 below the METRIC002 limit.
- **METRIC004, METRIC007, METRIC012, METRIC013.** The default is inside the allowed interval with a margin;
  only METRIC004 flags a file (PAO, 13.6, left unlabelled).
- **METRIC005.** No file is flagged. DCMI Terms was (10 of 22, 0.4545) because its orphans were mostly
  `dcam:rangeIncludes` targets; with CLS001 reading them (issue #66) it is 1 of 22, 0.045 (see "CLS001" below).
- **METRIC006, METRIC008, METRIC009, METRIC010.** The labelled-silent files include some at the extreme
  (0 relations, 1.0 unsigned, 0 tagged, 1.0 foreign), so the only limit with no false positive switches the
  rule off. The cause is a modelling choice the rule does not see (reuse of imported relations, signatures as
  restrictions, an English-only convention, alignment to an upper ontology), not where the limit sits.
- **METRIC011.** One file above 10 imports, an IDS header whose 80 imports are its own modules.

## Recommendations

Each is a recommendation, with its evidence and the alternative. None is applied.

| Rule(s) | Recommendation | Evidence | Alternative |
| --- | --- | --- | --- |
| METRIC001, METRIC002, METRIC003 | Keep 0.5. | Inside the interval, fires only on files labelled poor. | Lower METRIC002 to about 0.4 to catch partly documented files; the corpus cannot show whether that helps, and PATO base is already at 0.33. |
| METRIC004 | Keep 8.0. | One flag, unlabelled; the next highest value is 6.0. | Label PAO's flat catalogue as poor or intended first. |
| METRIC005 | Keep 0.3; settle the cause in CLS001 (below). | One flag, caused by the CLS001 gap. | Raise to 0.5: hides the gap rather than fixing it. |
| METRIC006 | Keep 0.1. | Three flags, two false positives from owned versus imported properties; CCO, IAO and MFTO are just above 0.1. | Count imported relations as used (a scope change, its own issue). |
| METRIC007 | Keep 5.0. | No flags; the maximum is 4.53, margin 0.47. | None needed. |
| METRIC008 | Keep 0.5; treat the false positives as a scope question. | SSN, SKOS and MOMo state signatures as restrictions or inherit them. | Read restrictions and inherited signatures. |
| METRIC009 | Keep 0.5. | Perfectly separates tagged from untagged files; whether untagged is a defect is a policy choice. | Keep it off the `obo` profile, where untagged labels are the convention. |
| METRIC010 | Keep 0.5. | Two false positives, both alignment to an upper ontology. | Do not count BFO or PMD core parents as foreign. |
| METRIC011 | Keep the limit; see "METRIC011" below. | One flag, the IDS header. | Count only imports that are not the model's own modules. |
| METRIC012, METRIC013 | Keep 4.0 and 0.6. | No flags; the nearest silent values are 10.9 and 0.42. | None needed; without a poor example the limit is unvalidated. |

## Open decisions

### METRIC001 and METRIC002: warning severity and the `ci`, `obo`, `fair` profiles

They are warnings, and those three profiles gate on warnings, so a low coverage fails the build. Observed with
`--profile ci`, `obo` and `fair` (identical) on the corpus: exactly two files fail, MOMo food traceability
(`METRIC001`, `METRIC002`, `METRIC003`) and MFTO (`METRIC002`), both labelled poor. No curated file fails.
`--profile strict` fails 12 of the 21 files, the other ten on info-level rules. Risk: PATO base is at 0.33 for METRIC002,
so a mature OBO ontology with more undefined classes could fail the `obo` profile.
*Recommendation:* keep both at warning, because the evidence shows no curated casualty and the profile choice
protects the failing case. *Alternatives:* demote to info (no profile ever fails on coverage), or keep the
severity but state in the `obo` profile that METRIC002 can be overridden. Two flagged files cannot settle it.

### METRIC011: `certain` or `heuristic`

The finding reports confidence `certain` and category `heuristic`. The count of distinct imports is exact; the
limit of 10 is a convention. The only corpus flag (IDS, 80) is labelled a false positive, because the imports
are its own modules. *Recommendation:* keep `certain`, since the confidence describes the count, and document
the limit as a convention. *Alternative:* `heuristic`, which matches every other METRIC rule and the false
positive. The spec says the finding identity is its rule and focus, so a change would not alter baselines, but
it would alter JSON and SARIF output for every METRIC011 finding.

### CLS001 and `dcam:domainIncludes` (also issue #66)

CLS001 read `schema:domainIncludes` and `schema:rangeIncludes` but not the `dcam:` pair, which OWL005 and
OWL006 read. On DCMI Terms it reported 10 of 22 orphans and METRIC005 fired at 0.4545. Only that file in the
corpus uses `dcam:domainIncludes` or `dcam:rangeIncludes` (24 occurrences). A scratch copy with the `dcam`
namespace rewritten to schema.org's predicted one orphan (`BibliographicResource`), 0.045. *Recommendation:* yes,
read both `dcam:` predicates. Issue #66 implements it on that recommendation, pending the maintainer's decision:
CLS001 now reads both, METRIC005 reports 1 of 22 (0.0455) and is silent on DCMI Terms, as predicted, and the
METRIC005 specification is corrected. *Alternative:* revert the change, and METRIC005 stays a known false
positive on DCMI vocabularies.

### Approval of the METRIC specifications

The specification in the `rules/metrics.py` docstring needs approval. Points to settle first: the METRIC005
reading of `dcam:domainIncludes` and `dcam:rangeIncludes` (issue #66, decided as recommended above, to be
confirmed); METRIC004 and METRIC005 being gated on the owned classes while the text says "population";
METRIC011's `certain`. *Recommendation:* approve once #66 is confirmed. The corpus does not confirm or refute
the other specifications.

## What the maintainer has to decide

1. Approve or correct the proposed labels in `metric-corpus.json`, replacing presumed ones with checked ones.
2. Decide the three open labels (METRIC004 and METRIC008 on PAO, METRIC006 on the Rights Ontology).
3. Add a known-poor example for each of METRIC004-METRIC013, or accept that their recall is unmeasured.
4. The four decisions above: severity, METRIC011 confidence, CLS001 and `dcam:`, approval of the specifications.
5. Whether `check` runs at every release (issue #31).

Until 1 and 3, no threshold should change on this corpus.
