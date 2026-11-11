# METRIC thresholds

The `METRIC001`-`METRIC013` rules each measure one ontology-wide figure (a ratio, a mean or a
count) and compare it with a threshold. A run reports at most one finding per rule, on the
ontology, and never a score. Every default below is a **first estimate**, chosen when the rules
were written; none has been calibrated against a labelled corpus yet (see "What is not known").
The conditions, populations and exclusions of each rule are in the specification at the top of
[`src/ontolint/rules/metrics.py`](../src/ontolint/rules/metrics.py).

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
- Comparisons are strict, so a value equal to its limit never fires, and a rule needs a
  population of at least `metric_min_sample` terms (`METRIC011` has no such gate).
- The Python API does not validate a `Policy` built directly; only `Policy.from_mapping` (used
  for `--config`) does.

## Thresholds

| Key | Rules | Default | Fires when | Population gate | Why this default |
| --- | --- | --- | --- | --- | --- |
| `metric_min_sample` | all but METRIC011 | 10 | population below it: silent | the gate itself | Below ten terms one term moves a ratio by more than ten points, and fixtures and stubs should never fire. |
| `metric_max_unlabelled_ratio` | METRIC001 | 0.5 | share of classes LEX001 reports above it | classes | LEX001 already reports each missing label; the aggregate speaks only when missing labels are the norm. |
| `metric_max_undefined_ratio` | METRIC002 | 0.5 | share of classes without a definition above it | classes | The same reasoning for definitions. |
| `metric_max_undocumented_property_ratio` | METRIC003 | 0.5 | share of properties without documentation above it | properties | The same reasoning for properties. |
| `metric_max_mean_fanout` | METRIC004 | 8.0 | mean direct subclasses per parent above it | classes | A flat list of more than about 7 plus or minus 2 siblings is hard to browse; CLS011 judges a single class at 50. |
| `metric_max_orphan_ratio` | METRIC005 | 0.3 | share of classes CLS001 reports above it | classes | Curated ontologies are mostly connected; the highest value measured offline after the fix is 0.45 (dcterms, whose `dcam:domainIncludes` CLS001 does not read). |
| `metric_min_property_class_ratio` | METRIC006 | 0.1 | relation properties per class below it | classes | Below one relation per ten classes the ontology is a taxonomy, which may be intended. |
| `metric_max_property_class_ratio` | METRIC007 | 5.0 | relation properties per class above it | classes | Offline values on 19 files ran up to 4.9; far above that, properties are probably proliferating. |
| `metric_max_unsigned_property_ratio` | METRIC008 | 0.5 | share of object and datatype properties OWL005 and OWL006 both report above it | properties | A signature is optional in RDFS; the rule speaks only when open signatures are the norm. |
| `metric_min_language_coverage` | METRIC009 | 0.5 | share of labelled terms with a language-tagged label below it | labelled terms | An untagged label works but cannot be localised; half is the point where tagging is the exception. |
| `metric_max_foreign_reference_ratio` | METRIC010 | 0.5 | share of structural references to foreign namespaces above it | references | Past half, the ontology is mostly a thin layer over other vocabularies. |
| `metric_max_imports` | METRIC011 | 10 | distinct `owl:imports` above it | none | A convention: more than ten imports make loading and reasoning heavy and the dependencies hard to review. |
| `metric_min_definition_words` | METRIC012 | 4.0 | mean words of the longest definition below it | defined classes | The shortest genus-differentia sentence ("An X that Y") has about four words. |
| `metric_max_blank_node_ratio` | METRIC013 | 0.6 | share of non-structural subjects that are blank above it | subjects | Beyond structure (axioms, restrictions, lists, shapes), blank subjects are mostly anonymous individuals. |

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

- The copies are unpinned and unlabelled. The figures describe value distributions and which rules
  fire; they say nothing about precision or recall. Calibrating the defaults needs a licensed,
  pinned corpus with known-good and known-poor ontologies, which is still open (TODO.md,
  "Calibrate metric thresholds").
- `METRIC010` does not count reuse of another OBO ontology as foreign, because all OBO terms share
  one namespace. Counting it is a product question.
- CLS001 ignores `dcam:domainIncludes` and `dcam:rangeIncludes`, so `METRIC005` inherits that gap
  (dcterms keeps 10 of 22 orphans).
- `METRIC001` and `METRIC002` are warnings, so with uncalibrated thresholds they fail the `ci`,
  `obo` and `fair` profiles.
