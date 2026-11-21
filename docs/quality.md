# Quality snapshots, baselines and trends

A *quality snapshot* is a file that records one run's [measurements](measurements.md) with the term sets
behind the coverage measures. It has two uses, and one comparison serves both:

- a **quality baseline** is a snapshot committed to the repository: the accepted values. A run is compared
  with it (`--quality-baseline`).
- a **trend** compares two snapshot files (`--compare-quality OLD NEW`). ontolint reads no git history: CI
  keeps the snapshots as artifacts, and a trend is two of them.

This is not `--baseline`, which suppresses findings by fingerprint (README "Policy and baselines").
Nothing here changes a finding or a fingerprint, and a run without these options reports exactly what it
did. The exit code is unchanged too, unless a measurement could not be computed: the run then exits 2
([measurements](measurements.md), "Failure").

> **`--quality-baseline` and `--compare-quality` report; a `delta` budget gates.** The two options exit `0`
> whatever they find (a measurement that could not be computed exits `2`, see below), so committing a quality baseline
> does not by itself protect a branch. The gate on the comparison is a `delta` bound of `quality_budgets`
> ([quality-budgets.md](quality-budgets.md), `METRIC014`): the policy says how many terms may regress, dilute or
> disappear and how many of the new terms must be fine, and `--fail-on` and `--baseline` apply to a breach like to any
> finding. "Failing a run on a regression" below records the decisions behind it (issue #98).

```bash
ontolint onto.ttl --write-quality-snapshot quality.json          # take a snapshot (commit it, or keep it in CI)
ontolint onto.ttl --format json --quality-baseline quality.json  # the run against the accepted values
ontolint onto.ttl --format markdown --quality-baseline quality.json   # the same, in the pull-request summary
ontolint --compare-quality last-week.json today.json             # a trend: two snapshots, nothing is linted
```

## Why term sets

An aggregate cannot tell a regression from a change of population. Adding 1,000 classes without a
definition lowers the definition coverage while the number of documented classes rises. With the IRIs in
the numerator and the denominator of each coverage measure, a coverage change splits into counts that do
tell them apart.

## The comparison

For a coverage measure, each term of either population is classified. A term is *fine* when it has the
property the measure counts (`better: higher`: it is in the numerator) or does not have the defect the
measure counts (`better: lower`: it is not in the numerator).

| Part | Terms that are |
| --- | --- |
| `regressed` | in both populations, fine before and not now: the real regression |
| `diluted` | new, and not fine: the ratio falls while no existing term changed |
| `removed` | in the old population only (fine or not) |
| `improved` | in both populations, not fine before and fine now |
| `added_good` | new, and fine |

`added_good` is not one of the four counts the roadmap names; without it the parts do not add up to the
numerator's change, so it is reported beside them. Each part has a count and, in JSON, its sorted IRIs. Each
compared ratio also has the `before` and `after` parts and the ratio `delta`.

- The delta is `after - before` of the two ratios, exact (a fraction of integers), rounded half to even to
  four places and written as a signed decimal text, `"-0.2667"`, `"+0.5000"`, `"0.0000"`. It is `null` when
  a population is empty (a ratio of 0 over 0 has no value). No float is ever printed.
- A count's delta is the difference, an integer. A histogram has no delta, only `changed`.
- A **rename** counts as one removal plus one new term, until COMP's rename detection exists. Every
  comparison says so in its `notes`.
- A measurement without term sets (`class_fanout`, `relation_properties_per_class`, `definition_length`,
  `foreign_references`, `blank_subjects`, the counts and the histograms) is compared by its parts only.

### Not comparable

A measurement is reported as `not_comparable`, with its reasons and nothing else, and is never diffed, when
any of these holds. Each one is judged on its own; one refusal does not hide the other measurements.

- `definition version 1 -> 2`, `kind ratio -> count`, `population a -> b`: what is counted changed.
- `numerator reading higher -> lower`, or `term sets are in the old snapshot only`: the term sets differ in
  meaning or in availability.
- `not taken in the old snapshot: <reason>` (and for the new one): a measurement that could not be taken,
  such as the SHACL class-target coverage without `--shapes`. Absent on both sides is not comparable either.
- `measured in the new snapshot only` or `... old ...`: the catalogues differ (another ontolint release).
- `policy differs: base, imports`: the policy that shaped the populations differs (see "policy" below). This
  refuses every measurement, because no policy field is known to leave one measurement alone.

## The comparison file (`--compare-quality`, `--quality-baseline`)

`--format json` prints (or, with `--quality-baseline`, adds as `quality_comparison` to the run's report):

```json
{
  "format": "ontolint-quality-comparison",
  "version": 1,
  "notes": ["A renamed term counts as one removal and one new term: ..."],
  "measurements": [
    {
      "id": "class_definition_coverage", "status": "compared", "definition_version": 1,
      "kind": "ratio", "population": "owned_classes",
      "before": {"numerator": 3, "denominator": 5}, "after": {"numerator": 2, "denominator": 6},
      "delta": "-0.2667",
      "coverage": {
        "better": "higher",
        "regressed": 1, "diluted": 3, "removed": 2, "improved": 1, "added_good": 0,
        "terms": {"regressed": ["https://example.test/q#B"], "diluted": [], "removed": [],
                  "improved": [], "added_good": []}
      }
    },
    {"id": "class_depth", "status": "not_comparable", "reasons": ["definition version 1 -> 2"]}
  ]
}
```

A count has `before`/`after` of `{"value": n}` and an integer `delta`; a histogram has `{"buckets": [...]}`
and `changed`. Measurements are listed in the old snapshot's order, then those only the new one has.
`--format text` (the default of `--compare-quality`) prints one line per measurement and its split;
`--format markdown` writes a section of the pull-request summary (README "Run the linter"), whose lines show
the four counts, `new and fine`, and the delta, or `not comparable` with the reasons, every id and reason in
a code span, at most 20 measurements. `--quality-baseline` takes `--format json` or `markdown`, and any format when the
policy has a `delta` budget, which gates on the comparison instead of showing it.

Exit codes: a comparison exits `0` whatever it finds, by design: a threshold is a `delta` budget's job (see the top of
this page). An unreadable or invalid snapshot, or one that cannot be written, exits `2`
(`TOOL001: quality snapshot FILE cannot be used: ...`), and so does a run in which a measurement could not be
computed (`TOOL001: measurement <id> failed for <file>: ...`; the snapshot is still written, with that
measurement absent, and must not be committed as the accepted values).

## Failing a run on a regression

A committed quality baseline protects a branch when the policy sets a `delta` budget (the syntax, the messages and the
fixtures are in [quality-budgets.md](quality-budgets.md), "Delta budgets"):

```json
{"quality_budgets": {"class_definition_coverage": {"delta": {"regressed": {"maximum": 0}, "new_terms": {"minimum": 0.8}}}}}
```

```bash
ontolint onto.ttl --config policy.json --quality-baseline quality.json    # exit 1 when a term lost its definition
```

Issue #98 asked for the policy of that gate. Each choice below is the one implemented, with the alternative that was
not taken.

1. **A budget, not a flag.** There is no `--fail-on-quality-regression`. A second mechanism beside `quality_budgets`
   would contradict QUALITY-BUDGET's one threshold mechanism, and a flag cannot say how many terms may regress. A breach
   is a `METRIC014` finding, so `--fail-on`, `--baseline`, `--select`, `severity_overrides` and every report format
   already apply.
2. **`regressed`: a maximum count, no default.** `{"regressed": {"maximum": 0}}` fails at any regression; without the
   key nothing is bounded. A term that was fine and is not is the real loss, but a project may accept a known number.
3. **`diluted`: a maximum count, or a minimum share of the new terms that are fine (`new_terms`).** Neither is a default,
   because failing on every defective new term stops an ontology under construction from growing, and ignoring them lets
   coverage fall unseen. The share is `added_good / (added_good + diluted)`; with no new term it has no value and breaches
   nothing, like a ratio over an empty population.
4. **`removed`: a maximum count, no default, never inferred.** Deleting a defective term raises coverage, and a
   deprecation is a deliberate removal, so a removal is not a failure unless the policy bounds it. A rename is one removal
   and one new term, so a `removed` bound cannot tell it apart; the absolute bounds still hold the coverage.
5. **A measurement that cannot be compared is exit `2`, never a pass.** That covers a definition version, kind or
   population that changed, a policy that differs (`--base`, extra predicates, the import closure) and a measurement
   not taken in either snapshot. The message names the reasons and says to write a new baseline with
   `--write-quality-snapshot`. The cost is stated: a new import, or an ontolint release that bumps a definition version,
   fails every build that has a delta budget on that measurement until the baseline is regenerated and reviewed. That is
   the same rule as for an untaken absolute budget, and the alternative (a pass) would let a gate go quiet unseen.
6. **Masked terms: a gate may rely on the counts.** The comparison counts a term's bad IRIs, so a regression is never
   hidden, and a swap of one bad IRI for another under one masked text is not a regression it can see (see "The snapshot
   file"); no measure with masked terms can show a gain it did not make.
7. **Exit code `1`, as a finding.** A breach is an error finding of `METRIC014`, gated by `--fail-on` (default `error`),
   suppressed by `--baseline`, lowered by `severity_overrides`. `2` is for what could not be judged (5, and a delta budget
   with no `--quality-baseline`, which is `GOV020` before any input is read).
8. **Updating the accepted baseline is a reviewed commit.** There is no command beyond `--write-quality-snapshot FILE`:
   the maintainer who accepts a worse state, or a new definition version, commits the new snapshot in the pull request
   that changes the bar, so the change is in the diff. A baseline that moves on every run would gate nothing.

## The snapshot file (version 1)

UTF-8 JSON, indented by two spaces with one IRI per line, ending in a newline, so a committed snapshot gives
readable diffs. It is deterministic: the same ontology and policy give the same bytes (no timestamp, path,
tool version or host). `--write-quality-snapshot` is for one ontology file (a closure under
`--follow-imports` counts as that file); it writes the snapshot whatever the exit code and the format.

```json
{
  "format": "ontolint-quality-snapshot",
  "version": 1,
  "policy": {
    "base": null,
    "extra_label_predicates": [],
    "extra_definition_predicates": [],
    "imports": []
  },
  "measurements": [
    {
      "id": "class_definition_coverage", "definition_version": 1, "kind": "ratio",
      "population": "owned_classes", "numerator": 3, "denominator": 5,
      "better": "higher",
      "numerator_terms": ["https://example.test/q#A", "https://example.test/q#B", "https://example.test/q#C"],
      "denominator_terms": ["https://example.test/q#A", "..."]
    },
    {"id": "unresolved_imports", "definition_version": 1, "kind": "count", "population": "graph", "value": 1},
    {"id": "shacl_class_target_coverage", "definition_version": 1, "kind": "ratio",
     "population": "owned_classes", "reason": "no SHACL shapes graph was supplied"}
  ]
}
```

- `format` is `ontolint-quality-snapshot`; `version` is `1`. **A change to what the file means or holds
  increments the version, and a reader refuses a version it does not read.** A reader refuses every key it
  does not know, so no snapshot is read loosely.
- `measurements` is every measurement of the catalogue, in its order, each as `--measurements` publishes it
  (`id`, `definition_version`, `kind`, `population`, then the value fields of its kind, or `reason` when it
  could not be taken), plus, for a **coverage measure**, three keys that come together: `better`
  (`higher` or `lower`: whether more of the numerator is an improvement), `numerator_terms` and
  `denominator_terms`. Both lists are sorted, hold each IRI once (a masked text once per IRI it stands
  for, see below), and the numerator is within the denominator; `numerator` and `denominator` are their lengths. The coverage measures are the eight with a
  `better` in `rules/measurements.py` (`SPECS`): the label, definition, property-documentation, language,
  orphan, unsigned-property, cycle and SHACL coverage ones.
- `policy` is what besides the graph shaped the populations: `base` (`--base`), `extra_label_predicates`,
  `extra_definition_predicates` (sorted) and `imports` (the sorted IRIs of the imports the run resolved to
  files, the import closure). It does not hold thresholds, the rule selection or a profile: no measurement
  depends on them.
- No IRI userinfo is written: IRIs, the policy and reasons are masked (the `SEC014` and `SEC016` notes in the README). The
  `numerator` and `denominator` are the engine's counts, taken before masking, so they equal what
  `--measurements` publishes. Distinct IRIs that differ only in their userinfo (`https://a:x@h/T` and
  `https://b:y@h/T`) are written as the same masked text (`https://****@h/T`), once for each IRI: a masked
  text may therefore repeat in a list, an unmasked one never, and a count is the length of its list.
  In the comparison such a text is one term whose badness is the number of its IRIs that are in the bad
  state: it is `regressed` when that number rises, `improved` when it falls, `diluted` or `added_good` when it
  is new. A swap of one bad IRI for another under the same masked text is not seen, and the term does not
  say which of its IRIs changed. The comparison therefore never hides a loss, and never shows a gain it did
  not measure.
- A file read back is validated in full: types, counts equal to the list lengths, sorted lists, the subset
  rule (as multisets), one entry per id. `dumps(loads(text)) == text` for every file ontolint writes.

The snapshot holds the file's whole vector and no partitions (`measurement_partitions`).

## Limitations

- A snapshot compares by IRI; there is no rename detection (COMP). A renamed term is a removal and a new term.
- The policy comparison is all-or-nothing, and it includes the import closure: a new import refuses every
  measurement (a `delta` budget then exits 2 until a new baseline is written). The ontology header (its IRI, hence ownership when `--base` is absent) is not in the policy;
  an ownership change shows in the term sets, but not in a measurement that has none.
- Only coverage measures have term sets. The other ratios are compared by their parts; their `by_namespace`
  split is not compared.
- One ontology file per snapshot; several files are several snapshots.
- The size of a snapshot is that of its IRIs: every coverage measure lists its denominator again.
