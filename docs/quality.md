# Quality snapshots, baselines and trends

A *quality snapshot* is a file that records one run's [measurements](measurements.md) with the term sets
behind the coverage measures. It has two uses, and one comparison serves both:

- a **quality baseline** is a snapshot committed to the repository: the accepted values. A run is compared
  with it (`--quality-baseline`).
- a **trend** compares two snapshot files (`--compare-quality OLD NEW`). ontolint reads no git history: CI
  keeps the snapshots as artifacts, and a trend is two of them.

This is not `--baseline`, which suppresses findings by fingerprint (README "Policy and baselines").
Nothing here changes a finding, a fingerprint or an exit code, and a run without these options reports
exactly what it did.

> **This is not a quality gate.** `--quality-baseline` and `--compare-quality` report; they exit `0`
> whatever they find, so committing a quality baseline does not protect a branch: a run that loses
> definition coverage still passes CI. The only quality gate today is the
> findings of the METRIC rules (their absolute thresholds, [metric-thresholds.md](metric-thresholds.md),
> and `--fail-on`): they judge one run, not a change from the baseline. A gate on the
> comparison itself (a budget on regressions, dilution or removals) is QUALITY-BUDGET (issue #26); it needs
> decisions this format does not take (removed terms, dilution, measurements that are not comparable,
> definition-version changes), so it is not part of this feature.

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
a code span, at most 20 measurements. `--quality-baseline` takes `--format json` or `markdown` only.

Exit codes: a comparison exits `0` whatever it finds, by design: it is not a gate (see the top of this page;
a threshold is QUALITY-BUDGET's job, issue #26). An unreadable or invalid snapshot, or one that cannot be written, exits `2`
(`TOOL001: quality snapshot FILE cannot be used: ...`).

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
  measurement. The ontology header (its IRI, hence ownership when `--base` is absent) is not in the policy;
  an ownership change shows in the term sets, but not in a measurement that has none.
- Only coverage measures have term sets. The other ratios are compared by their parts; their `by_namespace`
  split is not compared.
- One ontology file per snapshot; several files are several snapshots.
- The size of a snapshot is that of its IRIs: every coverage measure lists its denominator again.
