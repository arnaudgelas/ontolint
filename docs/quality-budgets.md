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

The syntax and the behaviours below are the decisions of issue #153 ("Decisions", at the end of this page). A budget
can also bound a change against a quality baseline: see "Delta budgets".

## The key

`quality_budgets` maps the `id` of a measurement ([catalogue](measurements.md#catalogue)) to an object
with a `minimum`, a `maximum` or both.

| Rule | Why |
| --- | --- |
| each bound is a finite number of at least 0; a boolean, a string and `null` are refused | the policy validates like every METRIC key |
| `minimum` must not exceed `maximum`; equal bounds pin a value | a contradictory budget is breached by every value |
| an object with neither bound nor `delta`, or with another key, is refused | a typo (`minimun`) must not become a budget that never fires |
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
- **Identity (baseline):** the rule, the focus and the pair *(measurement, side)* (for a `delta` bound, *(measurement, delta key)*). The value and the
  limit are not in it, so a measurement that moves, a budget that is loosened and still breached, and a
  budget that is *tightened* and still breached all stay accepted by `--baseline`; a new budget, and the
  other side of the same measurement, are new findings. A baseline therefore hides a breached budget
  whatever its limit becomes: fix the value or change the budget instead of baselining a gate you set
  yourself (see "Decisions", 3).
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

## Delta budgets

A `delta` bounds the *classified change* of a coverage measure against a quality baseline
([quality.md](quality.md)), never the raw ratio delta, which cannot tell a regression from a change of population:

```json
{
  "quality_budgets": {
    "class_definition_coverage": {
      "minimum": 0.9,
      "delta": {"regressed": {"maximum": 0}, "diluted": {"maximum": 5}, "removed": {"maximum": 2}, "new_terms": {"minimum": 0.8}}
    }
  }
}
```

```bash
ontolint onto.ttl --config policy.json --quality-baseline quality.json
# [ERROR  ] METRIC014 https://example.org/onto: class_definition_coverage: 1 term got worse since the quality baseline, above the maximum 0.
```

| Key | Bound | Counts |
| --- | --- | --- |
| `regressed` | `{"maximum": n}`, a whole number of at least 0 | terms fine before and not now |
| `diluted` | `{"maximum": n}` | new terms that are not fine |
| `removed` | `{"maximum": n}` | terms in the baseline and not in the run |
| `new_terms` | `{"minimum": s}`, a number from 0 to 1 | `added_good / (added_good + diluted)`: the share of new terms that are fine; no value, so no breach, when there are no new terms |

- Bounds are inclusive, as for the absolute ones. A `delta` with no key, an unknown key (`lost`), a key that is not
  `{"maximum": n}` (`{"minimum": n}` for `new_terms`), a negative or fractional count or a share above 1 is `GOV020`.
- A `delta` is for a *coverage measure*, the eight with `better` in the [catalogue](measurements.md#catalogue): only
  they have terms. On a count, a histogram or another ratio it is `GOV020`. A budget may have a `delta` alone, or beside
  `minimum` and `maximum`; each bound is judged on its own.
- The finding is one of `METRIC014`, at its severity (error, certain, deterministic), so selection, `--ignore`,
  `severity_overrides`, `--baseline` and `--fail-on` apply and it renders in text, JSON, SARIF and Markdown. The message
  is `<measurement>: <n> term(s) got worse | <n> new term(s) is/are not fine | <n> term(s) was/were removed since the
  quality baseline, above the maximum <limit>.` or `<measurement>: the share of new terms that are fine is <s> (<n> of
  <m>) since the quality baseline, below the minimum <limit>.` Its identity is the rule, the focus, the measurement and
  the delta key (`delta:regressed`), never the counts.
- **`--quality-baseline FILE` is required.** A policy with a `delta` budget and no baseline is `GOV020: policy file
  rejected: quality_budgets.<measurement>.delta needs --quality-baseline FILE`, exit `2` before any input is read.
  With a delta budget the baseline gates, so it is accepted with every `--format`; without one it still needs `json` or
  `markdown`, which are the formats that show the comparison. JSON and Markdown keep showing it.
- **A change that cannot be judged is exit `2`, never a pass** (`TOOL001: rule METRIC014 failed ...: <measurement>:
  cannot be compared with the quality baseline (<reasons>); write a new one with --write-quality-snapshot`, the report
  still written): a definition version, kind or population that changed, a policy that differs (`--base`, extra
  predicates, the import closure), or a measurement not taken in either snapshot. Every budget, absolute and delta, is
  read before any is compared, so a failed run reports no partial verdict. The rationale and the cost (a new import
  fails the build until the baseline is regenerated) are in [quality.md](quality.md), "Failing a run on a regression".
- A rename is a removal and a new term (`RENAME_NOTE`): a delta budget cannot tell it apart.
- **It is bypassed like every budget**: a run that does not select `METRIC014` checks no delta budget, and only `TOOL002` says so.
  A CI job that relies on the gate follows "Using a budget as a CI gate" below.
- The Python API: `Linter` has no baseline of its own. A caller that sets a `delta` budget must set
  `linter.rule_context.quality_comparison = ontolint.quality.compare(old, new)`; without it the rule fails as above.

## Not read yet

- **Budgets on `new_unsatisfiable_classes`, `competency_question_pass_rate` and
  `unreviewed_equivalence_mappings`:** those measurements do not exist until the SEM, CQ and ALIGN gates
  do, and a name that is not in the catalogue is refused.
- **A budget that applies to some inputs only:** a budget on a measurement that does not apply (the SHACL
  coverage without `--shapes`) is exit `2`, so a policy shared by repositories with and without shapes needs one
  policy file for each. A budget that names the inputs it applies to is not designed; open an issue with a case
  if one arises.

## Decisions

Issue #153 asked for four choices left open by the first slice. Each is recorded with the alternative that was
not taken; none changes behaviour, because the first slice already implemented the chosen one, and each is pinned by
a test (`tests/test_quality_budgets.py`).

1. **Syntax: keep.** `quality_budgets` maps a catalogue measurement `id` to `minimum` and `maximum`, inclusive, with
   no sample gate. The key is the measurement's own name, which `--measurements`, the quality snapshot and DQV
   already publish, so a budget, a snapshot and a report name one thing. Renaming a key after a release would be a
   policy-version change, so the names of the catalogue are the contract (`docs/measurements.md`).
2. **Selection: warn, do not force and do not reject.** A run that drops `METRIC014` (`--profile minimal`,
   `--select`, `--ignore`, `ignored_rules`) says `TOOL002` on standard error and checks no budget; the exit status is
   not changed. *Forcing the rule on* would make `--select LEX` run a METRIC rule, which contradicts what a
   selection says. *Rejecting with exit 2* would break a developer's `--select OWL001` run against the shared CI
   policy, for a gate that is not that run's business. The risk is a CI job that drops the rule by accident and
   reads no stderr: a job that gates on budgets runs the default selection or names `METRIC014`, and the notice is
   there for the one that does not.
3. **Baseline identity: keep rule, focus, measurement and side, without the limit.** This is the identity of every
   METRIC finding and of the baseline contract (issue #7). *Putting the limit in the identity* would turn a
   tightened budget into a new finding, which is what a reviewer wants, but it changes the contract for one rule
   and makes a loosened budget a stale entry plus a new one. The cost is stated above: a baseline hides a breached
   budget whatever its limit. A budget is a limit the project sets for itself, so the remedy for a breach is to fix
   the value or edit the budget, not to baseline it.
4. **A measurement that was not taken: exit 2, also when it does not apply.** Skipping with a note would let a gate
   pass on a value it never read, and a budget the policy declares for an input that cannot carry it is a
   configuration the run cannot honour. The report is still written, and the other METRIC rules keep their findings.

### Using a budget as a CI gate

The decisions above leave two ways to bypass a gate, by design, so a job that relies on budgets has obligations:

- **Run the default selection.** No `--profile minimal`, `--select` or `--ignore` that drops `METRIC014`, and no `ignored_rules`
  entry for it. Treat the notice as observable: it is the only sign that the gate did not run.

  ```bash
  ontolint onto.ttl --config policy.json 2> stderr.txt || status=$?
  ! grep -q "METRIC014 is not selected" stderr.txt || { echo "the budget gate did not run"; exit 1; }
  exit "${status:-0}"
  ```

- **Review a baseline update as a change of the gate.** An accepted `--baseline` entry for `METRIC014` hides a breach whatever the
  limit becomes (decision 3), so a pull request that adds one, or that loosens `quality_budgets`, is the place to ask why.

A selection that cannot drop the rule on its own is a follow-up, not part of these decisions.
