# Quality budgets

A *quality budget* is an explicit bound the policy file puts on a [measurement](measurements.md). A
run whose value is outside the bound reports one `METRIC014` finding. There is no default budget: a
policy without `quality_budgets` runs none, so nothing here changes a run that does not ask for it.

```json
{
  "quality_budgets": {
    "unresolved_imports": {"maximum": 0},
    "class_definition_coverage": {"minimum": 0.95}
  }
}
```

```bash
ontolint onto.ttl --config policy.json
# [ERROR  ] METRIC014 https://example.org/onto: class_definition_coverage is 0.18 (6 of 33), below the minimum 0.95.
```

This is **proposed syntax**: the key and its shape are the maintainer's to confirm (issue #26). Only
absolute bounds are read today; see "Not read yet".

## The key

`quality_budgets` maps the `id` of a measurement ([catalogue](measurements.md#catalogue)) to an object
with a `minimum`, a `maximum` or both.

| Rule | Why |
| --- | --- |
| each bound is a finite number of at least 0; a boolean, a string and `null` are refused | the policy validates like every METRIC key |
| `minimum` must not exceed `maximum`; equal bounds pin a value | a contradictory budget is breached by every value |
| an object with neither bound, or with another key, is refused | a typo (`minimun`) must not become a budget that never fires |
| the name is a measurement of the catalogue that has one value: a ratio or a count, not the histogram `class_depth` | a bound needs a value |
| a count's bounds are integers | `unresolved_imports` of 0.5 is a typo |
| a coverage measure's bounds are at most 1 (`class_label_coverage`, `class_definition_coverage`, `property_documentation_coverage`, `orphan_classes`, `unsigned_properties`, `label_language_coverage`, `cyclic_classes`, `shacl_class_target_coverage`) | 95 for 0.95 is a typo, not a budget that never fires |

A malformed budget, an unknown name or a bound a measurement cannot hold is a policy error: `GOV020:
policy file rejected: quality_budgets.<name>...` on standard error and exit `2`, before any input is
read, as for an unknown rule in `ignored_rules`. The name is checked against the catalogue at that
point, because the policy sits below the rules; `Linter(policy=...)` checks it when the rule runs.

## What a bound says

- The value of a ratio is its numerator over its denominator (a mean, the sum over the count), as
  `--measurements` publishes them, and the value of a count is the count. The value is the share the
  measurement counts: `class_definition_coverage` is 0.18 when 6 of 33 classes have a definition, so a
  budget that wants definitions is a `minimum`; `orphan_classes` counts the orphans, so a budget on
  orphans is a `maximum`.
- Bounds are **inclusive**. A value equal to its `minimum` or `maximum` is within the budget; the
  finding is for a value strictly below a minimum or strictly above a maximum. This is the comparison
  of the METRIC rules, whose limits are inclusive in the same sense ("a value equal to its limit never
  fires"); both go through one function, `ontolint.rules.bounds.breached`.
- A ratio over an empty population has no value: it breaches nothing. A policy that wants "there is a
  class" says so with another rule.
- There is no `metric_min_sample` gate. That gate keeps heuristic limits quiet on fixtures and stubs;
  a budget is the policy's own limit, and a project that writes `minimum: 0.95` for a three-class
  ontology means it.
- Only the bound a value breaches is reported: a value cannot breach both.

## The finding

One finding of `METRIC014` for each bound breached:

- **Message:** `<measurement> is <value> (<numerator> of <denominator>), below the minimum <limit>.`
  (`above the maximum` for a maximum; a count prints its value only). The value and the limit print
  with 2 decimals, or as many more, up to 6, as it takes to tell them apart.
- **Focus:** the lexically first ontology IRI of the graph, else `urn:ontolint:graph`, as every METRIC
  finding.
- **Identity (baseline):** the rule, the focus and the pair *(measurement, side)*. The value and the
  limit are not in it, so a measurement that moves, or a budget that is loosened and still breached,
  stays accepted by `--baseline`; a new budget, and the other side of the same measurement, are new
  findings.
- **Severity:** error, so it gates under every profile's `--fail-on`; `severity_overrides` lowers it.
  **Confidence:** certain; **category:** deterministic. The value is exact and the limit is the
  policy's own, so the finding is a fact the policy declared a failure, not a heuristic. (The METRIC
  rules whose limits are conventions stay `heuristic`.)
- It is a rule of the `METRIC` family, in the module `budgets`, so `--select METRIC014`, `--ignore`
  and `ignored_rules` act on it, and `--profile minimal`, which runs no METRIC rule, does not run it.
  A run that selects it away does not evaluate the budgets, and says so with `TOOL002: warning: the policy
  sets quality_budgets, but METRIC014 is not selected for this run` on standard error (the exit status
  is not changed).

## A measurement that was not taken

A budget is read before it is compared: if its measurement was not taken, there is no value to bound.
The rule fails, as every METRIC rule fails for a measurement it needs: `TOOL001: rule METRIC014 failed
for <file>: ...: MeasurementUnavailable: <id>: <reason>`, exit `2` even with `--fail-on never`, and the
report is still written. That covers a measurement that does not apply (the SHACL coverage without
`--shapes`) and one whose computation raised. Every budget is read before any is compared, so a failed
run reports no partial `METRIC014` verdict; the other METRIC rules keep their findings, because the rule
is its own module. A budget never passes on a value it could not read.

## The METRIC keys are built-in budgets

Each `metric_max_*` and `metric_min_*` key bounds one measurement from one side, which is what a budget
is. The table (`ontolint.rules.bounds.BUILT_IN`, pinned by `tests/test_quality_budgets.py` against the
rules, the policy and the measurement catalogue) names the measurement, the side and what the bound is
over. The keys stay as they are: they also carry the `metric_min_sample` gate and the METRIC message,
and nothing about them changes, so `tests/golden/differential.json` records no METRIC finding that
moved.

| Policy key | Rule | Measurement | Bound | Over | Gate |
| --- | --- | --- | --- | --- | --- |
| `metric_max_unlabelled_ratio` | METRIC001 | `class_label_coverage` | maximum | classes without it (denominator minus numerator, over denominator) | denominator |
| `metric_max_undefined_ratio` | METRIC002 | `class_definition_coverage` | maximum | classes without it | denominator |
| `metric_max_undocumented_property_ratio` | METRIC003 | `property_documentation_coverage` | maximum | properties without it | denominator |
| `metric_max_mean_fanout` | METRIC004 | `class_fanout` | maximum | the mean | owned classes |
| `metric_max_orphan_ratio` | METRIC005 | `orphan_classes` | maximum | the share | owned classes |
| `metric_min_property_class_ratio` | METRIC006 | `relation_properties_per_class` | minimum | the ratio | denominator |
| `metric_max_property_class_ratio` | METRIC007 | `relation_properties_per_class` | maximum | the ratio | denominator |
| `metric_max_unsigned_property_ratio` | METRIC008 | `unsigned_properties` | maximum | the share | denominator |
| `metric_min_language_coverage` | METRIC009 | `label_language_coverage` | minimum | the share | denominator |
| `metric_max_foreign_reference_ratio` | METRIC010 | `foreign_references` | maximum | the share | denominator |
| `metric_max_imports` | METRIC011 | `unresolved_imports` | maximum | the count | none |
| `metric_min_definition_words` | METRIC012 | `definition_length` | minimum | the mean | denominator |
| `metric_max_blank_node_ratio` | METRIC013 | `blank_subjects` | maximum | the share | denominator |

A budget and the key over the same value agree on every boundary where the quantity is the value
itself (`orphan_classes`, `unsigned_properties`, `blank_subjects`, `foreign_references`,
`label_language_coverage`, the means, `unresolved_imports`): the tests compare them on a file at and
around the value. Three keys bound the share a measurement *lacks* (METRIC001-METRIC003), which a
budget cannot write exactly: `class_label_coverage` with a `minimum` of 0.5 and `metric_max_unlabelled_ratio`
of 0.5 say the same thing, but a float written as `1 - limit` is not the float a rule would divide, so
the two are not promised to agree to the last digit. A budget on a measurement a METRIC rule also reads
is another finding, not a replacement of that rule: set the key to change the METRIC limit, and a budget
to add a gate.

## Not read yet

- **Bounds over the classified change against a quality baseline** ([quality.md](quality.md)): the
  counts of `regressed`, `diluted` and `removed` terms, and the coverage among new terms
  (`added_good` against `diluted`). The comparison is made after the rules ran, in the report, so
  findings from it need a design of their own (where they join the report, how a measurement that is not
  comparable behaves, how `--quality-baseline` is required). A `delta` key is refused with the other
  unknown keys, so no budget is silently not enforced. Never a bound on the raw ratio delta, which
  cannot tell a regression from a change of population.
- **Budgets on `new_unsatisfiable_classes`, `competency_question_pass_rate` and
  `unreviewed_equivalence_mappings`:** those measurements do not exist until the SEM, CQ and ALIGN gates
  do, and a name that is not in the catalogue is refused.
- **`--profile` and `--select`:** a run that does not select `METRIC014` evaluates no budget, without a
  notice.
