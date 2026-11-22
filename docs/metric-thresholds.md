# METRIC thresholds

The `METRIC001`-`METRIC013` rules each measure one ontology-wide figure (a ratio, a mean or a
count) and compare it with a threshold. A run reports at most one finding per rule, on the
ontology, and never a score. Every default below is a **first estimate**, chosen when the rules
were written, and none is calibrated. Each was measured once, on ontolint 0.13.1, on a pinned,
licensed corpus of 21 files, under labels that are approved, not independent of the measurements, and mostly presumed
([`validation/metric-calibration.md`](validation/metric-calibration.md)). The "Corpus" column gives
those preliminary observations; they are not rerun by CI or at release.
The conditions, populations and exclusions of each rule are in the specification at the top of
[`src/ontolint/rules/metrics.py`](../src/ontolint/rules/metrics.py).
Each rule reads a measurement, which `--format json --measurements` publishes below the threshold
too ([measurements.md](measurements.md)).

## Overriding

- Thresholds are set only by keys of the `--config` JSON policy (see "Policy and baselines" in the
  README). There are no command-line flags, and no profile sets them.
- Every key is validated: a ratio must be a number in [0, 1], a quantity a finite number of at
  least 0, `metric_max_imports` a non-negative integer and `metric_min_sample` an integer of at
  least 1. `metric_min_property_class_ratio` must not exceed `metric_max_property_class_ratio`.
  An invalid value gives `TOOL001: configuration failed: ValueError: ...` and exit code 2.
- `--ignore METRIC005` or `ignored_rules` switches a rule off, and `severity_overrides` changes
  its severity.
- `--profile minimal` runs no METRIC rule. The `ci`, `obo` and `fair` profiles gate on warnings,
  so `METRIC001` and `METRIC002` (warnings) can fail them; `strict` gates on every finding.
- Comparisons are strict, so a value equal to its limit never fires, and a rule needs at least
  `metric_min_sample` items of the quantity in the "Population gate" column below (classes, properties,
  references, labelled terms, subjects: not always terms; `METRIC011` has no such gate). The gate counts
  that quantity, which can differ from the one the value is taken over: `METRIC004` gates on owned classes
  and averages over parents, so at the default limits its gate never decides.
- Each key is one bound on one measurement from one side, a *built-in budget*; `quality_budgets` puts
  further, explicit bounds on any measurement and reports a breach as `METRIC014`
  ([quality-budgets.md](quality-budgets.md), which tabulates the keys as budgets). The keys are unchanged.
- The Python API does not validate a `Policy` built directly; only `Policy.from_mapping` (used
  for `--config`) does.

## Thresholds

*Every figure in the "Corpus notes" column and in the evidence table below comes from the 21-file pinned corpus of
[`validation/metric-corpus.json`](validation/metric-corpus.json), measured with ontolint 0.17.0 and re-checked on 2026-11-22
(`scripts/metric_corpus.py check` exits 0; `tests/test_metric_corpus.py` compares the notes with the recorded results).
The six local copies of the last section are unpinned and say so.*

| Key | Rules | Default | Fires when | Population gate | Why this default | Corpus notes (21 files, approved labels) |
| --- | --- | --- | --- | --- | --- | --- |
| `metric_min_sample` | all but METRIC011 | 10 | gated quantity below it: silent | the gate itself | Below ten terms one term moves a ratio by more than ten points, and fixtures and stubs should never fire. | keeps METRIC003 and METRIC008 silent on MFTO (2 properties, both at 1.0) |
| `metric_max_unlabelled_ratio` | METRIC001 | 0.5 | share of classes LEX001 reports above it | classes | LEX001 already reports each missing label; the aggregate speaks only when missing labels are the norm. | 1 fires: 1 TP, 0 FP, 0 FN |
| `metric_max_undefined_ratio` | METRIC002 | 0.5 | share of classes without a definition above it | classes | The same reasoning as METRIC001 for definitions: a few undefined classes are a per-term matter, and the aggregate speaks only when most classes lack one. | 2 fire: 2 TP, 0 FP, 0 FN |
| `metric_max_undocumented_property_ratio` | METRIC003 | 0.5 | share of properties without documentation above it | properties | The same reasoning as METRIC001 for properties: a few undocumented properties are a per-term matter, and the aggregate speaks only when most lack documentation. | 2 fire: 2 TP, 0 FP, 0 FN |
| `metric_max_mean_fanout` | METRIC004 | 8.0 | mean direct subclasses per parent above it | classes | A flat list of more than about 7 plus or minus 2 siblings is hard to browse; CLS011 judges a single class at 50. | 1 fires: 1 FP (PAO: a flat catalogue of 50 questionnaires) |
| `metric_max_orphan_ratio` | METRIC005 | 0.3 | share of classes CLS001 reports above it | classes | Curated ontologies are mostly connected; the highest value on the pinned corpus is 0.22 (MFTO); DCMI Terms is 0.045 now that CLS001 reads `dcam:domainIncludes` and `dcam:rangeIncludes`. | 0 fire |
| `metric_min_property_class_ratio` | METRIC006 | 0.1 | relation properties per class below it | classes | Below one relation per ten classes the ontology is a taxonomy, which may be intended. | 3 fire: 3 FP (PATO base, AutomaTCE, Rights Ontology) |
| `metric_max_property_class_ratio` | METRIC007 | 5.0 | relation properties per class above it | classes | Values on the pinned corpus run up to 4.53 (MOD); far above that, properties are probably proliferating. | 0 fire; highest 4.53 (MOD) |
| `metric_max_unsigned_property_ratio` | METRIC008 | 0.5 | share of object and datatype properties OWL005 and OWL006 both report above it | properties | A signature is optional in RDFS; the rule speaks only when open signatures are the norm. | 4 fire: 1 TP (PAO), 3 FP (SSN, SKOS, MOMo) |
| `metric_min_language_coverage` | METRIC009 | 0.5 | share of labelled terms with a language-tagged label below it | labelled terms | An untagged label works but cannot be localised; half is the point where tagging is the exception. | 3 fire: 3 FP (PATO base, schema.org, PROV-O) |
| `metric_max_foreign_reference_ratio` | METRIC010 | 0.5 | share of structural references to foreign namespaces above it | references | Past half, the ontology is mostly a thin layer over other vocabularies. | 2 fire: 2 FP (AutomaTCE, MFTO) |
| `metric_max_imports` | METRIC011 | 10 | distinct `owl:imports` above it | none | A convention: more than ten imports make loading and reasoning heavy and the dependencies hard to review. | 1 fires: 1 FP (IDS header, own modules) |
| `metric_min_definition_words` | METRIC012 | 4.0 | mean words of the longest definition below it | defined classes | The shortest genus-differentia sentence ("An X that Y") has about four words. | 0 fire; lowest 10.0 (SKOS) |
| `metric_max_blank_node_ratio` | METRIC013 | 0.6 | share of non-structural subjects that are blank above it | subjects | Beyond structure (axioms, restrictions, lists, shapes), blank subjects are mostly anonymous individuals. | 0 fire; highest 0.42 |

Since 0.13.0 a label or definition predicate includes the predicates below it through
`rdfs:subPropertyOf` and `owl:equivalentProperty` (README, "Scope and limitations"), so
`METRIC001` and `METRIC009` count labels under a sub-property of `rdfs:label` or `skos:prefLabel`,
and `METRIC002`, `METRIC003` and `METRIC012` definitions under an equivalent of a definition
predicate. `METRIC001` still counts exactly the classes `LEX001` reports. The thresholds did not
change.

## Evidence per threshold

For each shipped limit, what the corpus says under the approved labels, generated by
`scripts/metric_sweep.py render` from the recorded measurements and the manifest's labels (no network). *Compared* is the
number of the 21 files that make a comparison (a population at or above the sample gate), *Flagged* how many of them the
default flags; *TP*, *FP*, *FN* and *TN* count the labelled files among them (a fire label that is flagged is a true
positive, a silent label that is flagged a false positive); *Recall* is `TP / fire labels`. How the counts move with
the limit is in [`validation/metric-sweep.md`](validation/metric-sweep.md), and `calibrate` prints them per limit.

**A rule is `unmeasured` while no label expects a fire** (nothing says what it should catch, so its recall has no value
and having no false positive proves nothing), or no label expects a silence (its precision has none). It is reported
so, never as a rate of zero false positives. The counts rest on approved labels (issue #152), 211 of 273 of them presumed (see "What is
not known"), and **no default changes on this evidence**: a limit changes only on labels redone independently of the
measurements and a sweep that says so, with boundary fixtures (below, at and above the limit) and an upgrade
note.

<!-- metric_sweep.py: evidence begin -->

| Rule | Key | Default | Compared | Flagged | Fire labels | Silent labels | TP | FP | FN | TN | Recall | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| METRIC001 | `metric_max_unlabelled_ratio` | 0.5000 | 16 | 1 | 1 | 15 | 1 | 0 | 0 | 15 | 1/1 | measured |
| METRIC002 | `metric_max_undefined_ratio` | 0.5000 | 16 | 2 | 2 | 14 | 2 | 0 | 0 | 14 | 2/2 | measured |
| METRIC003 | `metric_max_undocumented_property_ratio` | 0.5000 | 16 | 2 | 2 | 14 | 2 | 0 | 0 | 14 | 2/2 | measured |
| METRIC004 | `metric_max_mean_fanout` | 8.0000 | 14 | 1 | 0 | 14 | 0 | 1 | 0 | 13 | unmeasured | unmeasured: no label expects a fire, so recall has no value |
| METRIC005 | `metric_max_orphan_ratio` | 0.3000 | 16 | 0 | 0 | 15 | 0 | 0 | 0 | 15 | unmeasured | unmeasured: no label expects a fire, so recall has no value |
| METRIC006 | `metric_min_property_class_ratio` | 0.1000 | 16 | 3 | 0 | 15 | 0 | 3 | 0 | 12 | unmeasured | unmeasured: no label expects a fire, so recall has no value |
| METRIC007 | `metric_max_property_class_ratio` | 5.0000 | 16 | 0 | 0 | 16 | 0 | 0 | 0 | 16 | unmeasured | unmeasured: no label expects a fire, so recall has no value |
| METRIC008 | `metric_max_unsigned_property_ratio` | 0.5000 | 14 | 4 | 1 | 13 | 1 | 3 | 0 | 10 | 1/1 | measured |
| METRIC009 | `metric_min_language_coverage` | 0.5000 | 18 | 3 | 0 | 18 | 0 | 3 | 0 | 15 | unmeasured | unmeasured: no label expects a fire, so recall has no value |
| METRIC010 | `metric_max_foreign_reference_ratio` | 0.5000 | 17 | 2 | 0 | 17 | 0 | 2 | 0 | 15 | unmeasured | unmeasured: no label expects a fire, so recall has no value |
| METRIC011 | `metric_max_imports` | 10 | 21 | 1 | 0 | 21 | 0 | 1 | 0 | 20 | unmeasured | unmeasured: no label expects a fire, so recall has no value |
| METRIC012 | `metric_min_definition_words` | 4.0000 | 14 | 0 | 0 | 14 | 0 | 0 | 0 | 14 | unmeasured | unmeasured: no label expects a fire, so recall has no value |
| METRIC013 | `metric_max_blank_node_ratio` | 0.6000 | 21 | 0 | 0 | 21 | 0 | 0 | 0 | 21 | unmeasured | unmeasured: no label expects a fire, so recall has no value |

<!-- metric_sweep.py: evidence end -->

## Measurements

Descriptive figures from six local, unpinned copies of public ontologies, each measured with every
threshold forced to report. Each cell is the value the rule would print (the numerator and the
whole, or the mean) and a star marks a default that fires. "Before" is the code at the start of the
METRIC specification work, "after" the code that describes these rules.

| File | Rule | Before | After |
| --- | --- | --- | --- |
| BFO | METRIC006 (relation properties / classes) | 2 / 35 (fires) | 0 / 35 (fires) |
| RO | METRIC008 (unsigned / properties) | 12 / 24 | 10 / 24 |
| SKOS | METRIC006 | 28 / 4 | 18 / 4 |
| SKOS | METRIC008 | 12 / 18 (fires) | 12 / 18 (fires) |
| automatce | METRIC006 | 11 / 309 (fires) | 11 / 309 (fires) |
| automatce | METRIC010 | 271 / 331 (fires) | 271 / 331 (fires) |

Every other METRIC value of those files is the same before and after. An earlier measurement of
19 files (schema.org, Tractus-X, FOAF, PROV-O and others) was not repeated for this page. Two
figures from it are recorded here as historical and unverified, because their files are not kept:
METRIC005 on a food-traceability schema was 22 of 43 orphans before and none after, and METRIC010 on
Tractus-X was 34 of 236 references before and 6 after.

## What is not known

- The six copies above are unpinned and unlabelled. The pinned corpus
  ([`validation/metric-calibration.md`](validation/metric-calibration.md)) replaces them as evidence,
  but its labels are approved, written with the measurements in view, and 211 of its 273 (file, rule) labels are presumed
  from a file's standing rather than checked in it. Its counts are preliminary observations under
  those labels, not a measurement of precision. Under them, METRIC001, METRIC002 and METRIC003 have
  no false positive, and no false negative among their few labelled cases (1 or 2 true positives
  each). Every false positive of the other rules (13 in all) rests on a checked label and comes from a
  modelling choice the rule does not see; they fall on six rules. For these rules only a limit that switches the rule off on
  this corpus (above every value it holds, or at zero for a minimum) would remove them, and for METRIC008 no
  limit is consistent with the labels. METRIC005's twelfth, DCMI Terms, was the CLS001 gap and went with the fix
  for issue #66. No default has changed, and none should change on this corpus alone: that needs
  labels redone independently of the measurements (issue #8) and measurements rerun at release (`check` does, issue #169).
- The corpus has no known-poor file for METRIC004 to METRIC013 but one, PAO for METRIC008, so their recall is not
  measured, and METRIC008's is a single case.
- How the files flagged move as each limit moves is in [`validation/metric-sweep.md`](validation/metric-sweep.md); ten
  candidate files (six of them firing nominees), with blank labels, are in [`validation/metric-candidates.md`](validation/metric-candidates.md).
  The procedure that turns the maintainer's labels into false-positive and false-negative counts per limit is in
  [`metric-calibration.md`](metric-calibration.md), "What the maintainer has to decide".
- The corpus is a snapshot of 0.13.1: `scripts/metric_corpus.py check` runs at every release and weekly
  (issue #169), so a later change that leaves it stale is reported, not silent.
- `METRIC010` does not count reuse of another OBO ontology as foreign, because all OBO terms share
  one namespace. Counting it is a product question.
- `METRIC001` and `METRIC002` are warnings, so they fail the `ci`, `obo` and `fair` profiles. On the
  corpus they fire only on the files labelled poor, never on a curated one, which is consistent
  with their limits but too little evidence to confirm them.
