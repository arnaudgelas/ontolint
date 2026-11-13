# METRIC calibration corpus (ontolint 0.13.1)

The `METRIC001`-`METRIC013` defaults are first estimates ([`docs/metric-thresholds.md`](../metric-thresholds.md)).
This page measures them on 21 pinned, licensed public files and counts false positives and false
negatives under labels that say, for each file and rule, whether the rule *should* fire (issue #8).

**The labels are proposed, not approved.** They were written by the author of this page, with the
measurements in view, from what each file's own documentation says it intends. Until the maintainer
approves them (`"label_status": "approved"` in the manifest), the counts below are a hypothesis about
precision, not a measurement of it.

**Result, under the proposed labels: no false negative, and no false positive for METRIC001, METRIC002
and METRIC003, the two warnings among them included. Every false positive (12 in all) comes from a
modelling choice the rule does not see, not from where its limit sits:** for five of the six rules
concerned, only a limit that switches the rule off would remove them. METRIC005's one false positive
would go with a limit above 0.45, but its cause is CLS001 not reading `dcam:rangeIncludes`. No
default is changed here; the choices are in "For the maintainer" below.

## Corpus

[`metric-corpus.json`](metric-corpus.json) names every file by URL, commit, path, licence and
SHA-256. No corpus file is committed. Twenty files are fixed by a commit in their URL; SKOS Core
is the W3C namespace document and is fixed by its checksum only. The corpus mixes:

- *known-good*: W3C and DCMI Recommendations (SOSA, SSN, PROV-O, SKOS, DCMI Terms), OBO Foundry
  ontologies (RO core, IAO, PATO base), BFO 2020, CCO 2.2, schema.org 30.1 and curated domain
  models (Software Description Ontology, MOD, Tractus-X, IDS, AutomaTCE);
- *known-poor*, for some rules only: research ontologies from the 2026-11-09 corpus (TODO.md,
  "Real-world ontologies") whose files show the gap on reading: the MOMo food-traceability schema
  (no label, no definition, no property documentation), MFTO (no definition) and the Personality
  Assessment Ontology (no property documentation); and the Hohfeldian Rights Ontology, labelled
  only where its file is unambiguous.

There is no known-poor example for METRIC004, METRIC005 and METRIC007 to METRIC013: no file is
labelled `fire` for them, so their recall is not measured here, only their false-positive rate.

## Method

```sh
uv run python scripts/metric_corpus.py fetch DIR     # download, refuse a changed checksum
uv run python scripts/metric_corpus.py measure DIR   # lint, rewrite the results and this page's tables
uv run python scripts/metric_corpus.py check DIR     # fail if the measurements changed
```

ontolint 0.13.1 (`f584f01`), Python 3.13.7, rdflib 7.6.0, from the locked environment, on
2026-11-13. Every file is linted alone, without `--follow-imports`, twice with `--select METRIC`:

- with the default policy, which decides whether a rule fires as shipped (**bold** below);
- with a *forced* policy (every limit at the end of its range, `metric_min_sample` 1), so that every
  rule with a non-empty population reports, and its message gives the value. A rule silent under
  the forced policy measured the boundary or had an empty population, which the run cannot tell
  apart: `0` (no member has the property), `no parent`, `no class`, `none untagged`, `no definition`.
  METRIC007 reads the ratio METRIC006 reports.

Every run exits 0 and executes all 13 rules. The results are in
[`metric-corpus-results.json`](metric-corpus-results.json); `check` reproduced them byte for byte.

## Results

<!-- metric_corpus.py: begin -->
### Measurements

Each cell is the forced measurement; **bold** means the rule fires at its default. The label is
in brackets: `F` expected to fire, `S` expected silent, `?` unlabelled or left open. A cell whose
outcome contradicts its label is marked FP or FN.

| File | METRIC001 | METRIC002 | METRIC003 | METRIC004 | METRIC005 | METRIC006 | METRIC007 | METRIC008 | METRIC009 | METRIC010 | METRIC011 | METRIC012 | METRIC013 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `bfo-2020-core.ttl` | 0 [S] | 0 [S] | 0 [S] | 2.19 over 16 [S] | 0 [S] | 40 / 36 [S] | 40 / 36 [S] | 0 [S] | none untagged [S] | 0 [S] | 0 [S] | 28.06 over 36 [S] | 0 [S] |
| `ro-core.owl` | 0 [S] | 0 [S] | 2 / 25 [S] | no parent [S] | 0 [S] | no class [S] | no class [S] | 10 / 24 [S] | none untagged [S] | 0 [S] | 0 [S] | no definition [S] | 16 / 76 [S] |
| `cco-merged.ttl` | 0 [S] | 0 [S] | 1 / 172 [S] | 3.30 over 382 [S] | 0 [S] | 148 / 1400 [S] | 148 / 1400 [S] | 1 / 148 [S] | none untagged [S] | 303 / 1667 [S] | 0 [S] | 21.59 over 1400 [S] | 1 / 2020 [S] |
| `iao.owl` | 0 [S] | 13 / 210 [S] | 10 / 57 [S] | 4.07 over 45 [S] | 0 [S] | 23 / 210 [S] | 23 / 210 [S] | 6 / 23 [S] | 255 / 267 [S] | 16 / 230 [S] | 0 [S] | 24.69 over 197 [S] | 16 / 457 [S] |
| `pato-base.owl` | 0 [S] | 959 / 2931 [S] | 0 [S] | 4.36 over 521 [S] | 0 [S] | **0 / 2931** [S FP] | 0 / 2931 [S] | 0 [S] | **0 / 2847** [S FP] | 0 [S] | 0 [S] | 19.33 over 1972 [S] | 0 [S] |
| `sosa.ttl` | 0 [S] | 0 [S] | 0 [S] | no parent [S] | 0 [S] | 23 / 13 [S] | 23 / 13 [S] | 0 [S] | none untagged [S] | 0 [S] | 0 [S] | 31.69 over 13 [S] | 1 / 55 [S] |
| `ssn.ttl` | 0 [S] | 0 [S] | 0 [S] | no parent [S] | 0 [S] | 15 / 6 [S] | 15 / 6 [S] | **15 / 15** [S FP] | none untagged [S] | 0 [S] | 1 [S] | 19.50 over 6 [S] | 10 / 81 [S] |
| `prov-o.ttl` | 0 [S] | 0 [S] | 10 / 65 [S] | 3.11 over 9 [S] | 0 [S] | 50 / 30 [S] | 50 / 30 [S] | 1 / 50 [S] | **1 / 80** [S FP] | 0 [S] | 0 [S] | 42.20 over 30 [S] | 0 [S] |
| `skos-core.rdf` | 0 [S] | 0 [S] | 0 [S] | 1.00 over 1 [S] | 0 [S] | 18 / 4 [S] | 18 / 4 [S] | **12 / 18** [S FP] | none untagged [S] | 0 [S] | 0 [S] | 10.00 over 4 [S] | 0 [S] |
| `schemaorg-30.1.ttl` | 0 [S] | 0 [S] | 0 [S] | 5.37 over 183 [S] | 0 [S] | 1538 / 939 [S] | 1538 / 939 [S] | 0 [S] | **7 / 2477** [S FP] | 10 / 992 [S] | 0 [S] | 22.19 over 939 [S] | 0 [S] |
| `sdo-1.9.0.ttl` | 0 [S] | 0 [S] | 0 [S] | 1.62 over 8 [S] | 0 [S] | 103 / 25 [S] | 103 / 25 [S] | 1 / 103 [S] | 125 / 128 [S] | 8 / 139 [S] | 0 [S] | 21.80 over 25 [S] | 0 [S] |
| `mod.ttl` | 0 [S] | 0 [S] | 0 [S] | 2.00 over 2 [S] | 0 [S] | 68 / 15 [S] | 68 / 15 [S] | 9 / 68 [S] | none untagged [S] | 8 / 104 [S] | 0 [S] | 14.80 over 15 [S] | 0 [S] |
| `automatce-base.ttl` | 0 [S] | 0 [S] | 0 [S] | 1.70 over 27 [S] | 0 [S] | **11 / 309** [S FP] | 11 / 309 [S] | 0 [S] | none untagged [S] | **271 / 331** [S FP] | 0 [S] | 16.94 over 309 [S] | 0 [S] |
| `mfto.ttl` | 0 [S] | **18 / 18** [F] | 2 / 2 [?] | no parent [?] | 4 / 18 [?] | 2 / 18 [?] | 2 / 18 [?] | 2 / 2 [?] | none untagged [?] | **14 / 14** [S FP] | 2 [?] | no definition [?] | 0 [?] |
| `rights-ontology.ttl` | 0 [S] | 0 [S] | 0 [?] | 2.50 over 4 [?] | 1 / 12 [?] | **0 / 12** [?] | 0 / 12 [?] | 0 [?] | none untagged [?] | 0 [?] | 0 [?] | 22.67 over 12 [?] | 0 [?] |
| `pao.owl` | 0 [S] | 10 / 103 [S] | **13 / 13** [F] | **13.57 over 7** [?] | 0 [?] | 13 / 103 [?] | 13 / 103 [?] | **10 / 13** [?] | none untagged [?] | 12 / 107 [?] | 2 [?] | 12.11 over 93 [?] | 0 [?] |
| `ids-ontology.ttl` | 0 [S] | 0 [S] | 0 [S] | no parent [S] | 0 [S] | no class [S] | no class [S] | 0 [S] | none untagged [S] | 0 [S] | **80** [S FP] | no definition [S] | 2 / 16 [S] |
| `tractusx-ontology.ttl` | 0 [S] | 0 [S] | 2 / 156 [S] | 2.60 over 10 [S] | 0 [S] | 139 / 32 [S] | 139 / 32 [S] | 0 [S] | 183 / 186 [S] | 6 / 236 [S] | 0 [S] | 15.72 over 32 [S] | 0 [S] |
| `tractusx-taxonomy.ttl` | 0 [S] | 0 [S] | 0 [S] | no parent [S] | 0 [S] | no class [S] | no class [S] | 0 [S] | none untagged [S] | 0 [S] | 0 [S] | no definition [S] | 0 [S] |
| `food-traceability.ttl` | **43 / 43** [F] | **43 / 43** [F] | **31 / 31** [F] | 6.00 over 3 [?] | 0 [?] | 31 / 43 [?] | 31 / 43 [?] | **31 / 31** [S FP] | none untagged [?] | 0 [?] | 0 [?] | no definition [?] | 58 / 137 [?] |
| `dcterms.ttl` | 0 [S] | 0 [S] | 0 [S] | 2.00 over 4 [S] | **10 / 22** [S FP] | 55 / 22 [S] | 55 / 22 [S] | 0 [S] | none untagged [S] | 3 / 11 [S] | 0 [S] | 10.91 over 22 [S] | 0 [S] |

### Outcomes under the proposed labels

| Rule | Fires (of 21) | True positive | False positive | True negative | False negative | Unlabelled |
| --- | --- | --- | --- | --- | --- | --- |
| METRIC001 | 1 | 1 | 0 | 20 | 0 | 0 |
| METRIC002 | 2 | 2 | 0 | 19 | 0 | 0 |
| METRIC003 | 2 | 2 | 0 | 17 | 0 | 2 |
| METRIC004 | 1 | 0 | 0 | 17 | 0 | 4 |
| METRIC005 | 1 | 0 | 1 | 16 | 0 | 4 |
| METRIC006 | 3 | 0 | 2 | 15 | 0 | 4 |
| METRIC007 | 0 | 0 | 0 | 17 | 0 | 4 |
| METRIC008 | 4 | 0 | 3 | 15 | 0 | 3 |
| METRIC009 | 3 | 0 | 3 | 14 | 0 | 4 |
| METRIC010 | 2 | 0 | 2 | 16 | 0 | 3 |
| METRIC011 | 1 | 0 | 1 | 16 | 0 | 4 |
| METRIC012 | 0 | 0 | 0 | 17 | 0 | 4 |
| METRIC013 | 0 | 0 | 0 | 17 | 0 | 4 |

### The proposed labels

| File | Rules | Label | Why |
| --- | --- | --- | --- |
| `bfo-2020-core.ttl` | all | silent | ISO/IEC 21838-2 upper ontology. Curated and widely reused; no aggregate quality problem is known for it. |
| `ro-core.owl` | all | silent | An OBO Foundry ontology, curated and widely reused; no aggregate quality problem is known for it. |
| `cco-merged.ttl` | all | silent | Curated and widely reused; no aggregate quality problem is known for it. |
| `iao.owl` | all | silent | An OBO Foundry ontology, curated and widely reused; no aggregate quality problem is known for it. |
| `pato-base.owl` | every other rule | silent | An OBO Foundry ontology, curated and widely reused; no aggregate quality problem is known for it. |
| `pato-base.owl` | METRIC006 | silent | A quality taxonomy by design: its relations come from RO, so it owns none. |
| `pato-base.owl` | METRIC009 | silent | Untagged labels are the OBO convention. An English-only vocabulary whose untagged labels are a deliberate convention, not a defect. |
| `sosa.ttl` | all | silent | A W3C Recommendation vocabulary, reviewed and widely reused; no aggregate quality problem is known for it. |
| `ssn.ttl` | every other rule | silent | A W3C Recommendation vocabulary, reviewed and widely reused; no aggregate quality problem is known for it. |
| `ssn.ttl` | METRIC008 | silent | SSN states its signatures as class restrictions instead of global domains and ranges, by design. |
| `prov-o.ttl` | every other rule | silent | A W3C Recommendation vocabulary, reviewed and widely reused; no aggregate quality problem is known for it. |
| `prov-o.ttl` | METRIC009 | silent | An English-only vocabulary whose untagged labels are a deliberate convention, not a defect. |
| `skos-core.rdf` | every other rule | silent | A W3C Recommendation vocabulary, reviewed and widely reused; no aggregate quality problem is known for it. |
| `skos-core.rdf` | METRIC008 | silent | The SKOS Reference leaves domains and ranges open on purpose; sub-properties inherit them from skos:semanticRelation. |
| `schemaorg-30.1.ttl` | every other rule | silent | Curated and widely reused; no aggregate quality problem is known for it. |
| `schemaorg-30.1.ttl` | METRIC009 | silent | An English-only vocabulary whose untagged labels are a deliberate convention, not a defect. |
| `sdo-1.9.0.ttl` | all | silent | Curated and widely reused; no aggregate quality problem is known for it. |
| `mod.ttl` | all | silent | Curated and widely reused; no aggregate quality problem is known for it. |
| `automatce-base.ttl` | every other rule | silent | Curated and widely reused; no aggregate quality problem is known for it. |
| `automatce-base.ttl` | METRIC006 | silent | An ODK base release: its relations are imported from PMD core and RO, not owned. |
| `automatce-base.ttl` | METRIC010 | silent | An application ontology that extends PMD core and BFO by subclassing: reuse by design. |
| `mfto.ttl` | METRIC001 | silent | Every class is labelled. |
| `mfto.ttl` | METRIC002 | fire | No class has a definition (18 of 18). |
| `mfto.ttl` | METRIC010 | silent | Every class sits under a BFO class: alignment to an upper ontology is the intended reuse. |
| `rights-ontology.ttl` | METRIC001 | silent | Every class is labelled. |
| `rights-ontology.ttl` | METRIC002 | silent | Every class is defined. |
| `rights-ontology.ttl` | METRIC006 | unknown | Twelve classes and no relation: a taxonomy of Hohfeld's incidents may be intended, or unfinished. |
| `pao.owl` | METRIC001 | silent | Every class is labelled. |
| `pao.owl` | METRIC002 | silent | Most classes are defined (93 of 103). |
| `pao.owl` | METRIC003 | fire | None of its 13 owned properties is documented. |
| `pao.owl` | METRIC004 | unknown | 50 named questionnaires under one parent: a catalogue may be flat on purpose, or want grouping by construct. |
| `pao.owl` | METRIC008 | unknown | 10 of its 13 owned object and datatype properties have no signature, in a small research ontology: unfinished or deliberately open. |
| `ids-ontology.ttl` | every other rule | silent | Curated and widely reused; no aggregate quality problem is known for it. |
| `ids-ontology.ttl` | METRIC011 | silent | The 80 imports are the model's own modules, by relative IRI: a modular header, not 80 dependencies. |
| `tractusx-ontology.ttl` | all | silent | Curated and widely reused; no aggregate quality problem is known for it. |
| `tractusx-taxonomy.ttl` | all | silent | A SKOS taxonomy: no class or property, so no METRIC rule has anything to judge. |
| `food-traceability.ttl` | METRIC001 | fire | No class has a label: a diagram export that was never annotated. |
| `food-traceability.ttl` | METRIC002 | fire | No class has a definition. |
| `food-traceability.ttl` | METRIC003 | fire | No property is documented. |
| `food-traceability.ttl` | METRIC008 | silent | MOMo states its signatures as scoped restrictions (109 of them) instead of global domains and ranges, by design. |
| `dcterms.ttl` | every other rule | silent | A DCMI Recommendation. Curated and widely reused; no aggregate quality problem is known for it. |
| `dcterms.ttl` | METRIC005 | silent | 9 of the 10 classes CLS001 calls orphans are targets of dcam:rangeIncludes, which CLS001 does not read: connected, not orphans. |
<!-- metric_corpus.py: end -->

## Reading the false positives

| Rule | Files | Why the rule fires | Would another default help? |
| --- | --- | --- | --- |
| METRIC005 | DCMI Terms (10 of 22, 0.45) | 9 of the 10 classes CLS001 calls orphans are targets of `dcam:rangeIncludes`, which CLS001 does not read (OWL005 and OWL006 do). | Only a limit above 0.45; the gap is in CLS001, see "For the maintainer". |
| METRIC006 | PATO base (0 / 2931), AutomaTCE base (11 / 309) | Both own no or few relations because they reuse RO and PMD core: the rule counts owned properties only. | No: 0 fires at any limit above 0, and CCO (0.106), IAO (0.110) and MFTO (0.111) sit just above 0.1. |
| METRIC008 | SSN (15 / 15), SKOS (12 / 18), MOMo food traceability (31 / 31) | SSN and MOMo state signatures as class restrictions (73 and 109); SKOS gives them to `skos:semanticRelation`, which its sub-properties inherit. The rule reads neither. | No: two of the three are at 1.0, which only the limit 1.0 (the rule off) leaves silent. |
| METRIC009 | PATO base (0.00), schema.org (0.003), PROV-O (0.013) | English-only vocabularies with untagged labels, the OBO and W3C convention. | No: every tagged file is above 0.95 and every untagged one below 0.02. The rule separates the two conventions perfectly; the question is whether untagged is a defect. |
| METRIC010 | AutomaTCE base (271 / 331), MFTO (14 / 14) | Both place their classes under BFO or PMD core classes: alignment to an upper ontology, which the rule counts as foreign. | No: MFTO is at 1.0, which only the limit 1.0 (the rule off) leaves silent; every other file is at most 0.27. |
| METRIC011 | IDS header (80 imports) | Its 86 `owl:imports` (80 distinct IRIs) all name the model's own modules by relative IRI; only `--follow-imports` subtracts resolved imports. | No limit below 80 that a modular header would not cross. |

METRIC004's only finding (PAO, 13.57: 50 questionnaires under one parent) is left unlabelled: a
catalogue may be flat on purpose. METRIC006 on the Rights Ontology (0 relations for 12 classes) and
METRIC008 on PAO (10 of 13) are left unlabelled for the same reason.

## Margins

The closest silent value to each default, and the closest firing one, where the corpus has them.
A value below the sample gate (`metric_min_sample`, 10 terms) is left out.

| Rule | Default | Closest silent | Closest firing |
| --- | --- | --- | --- |
| METRIC001 | > 0.5 | 0, every other file | 1.0, food traceability |
| METRIC002 | > 0.5 | 0.33, PATO base | 1.0, MFTO and food traceability |
| METRIC003 | > 0.5 | 0.18, IAO | 1.0, PAO and food traceability |
| METRIC004 | > 8.0 | 6.0, food traceability | 13.57, PAO |
| METRIC005 | > 0.3 | 0.22, MFTO | 0.45, DCMI Terms |
| METRIC006 | < 0.1 | 0.106, CCO | 0.036, AutomaTCE base |
| METRIC007 | > 5.0 | 4.53, MOD | none |
| METRIC008 | > 0.5 | 0.42, RO core | 0.67, SKOS |
| METRIC009 | < 0.5 | 0.955, IAO | 0.013, PROV-O |
| METRIC010 | > 0.5 | 0.27, DCMI Terms | 0.82, AutomaTCE base |
| METRIC011 | > 10 | 2, MFTO and PAO | 80, IDS header |
| METRIC012 | < 4.0 | 10.0, SKOS | none |
| METRIC013 | > 0.6 | 0.42, food traceability | none |

## For the maintainer

1. **Approve or correct the labels** in `metric-corpus.json`, then set `"label_status": "approved"`
   and run `render`. A changed label changes only the counts, never a measurement.
2. **Decide the open labels**: METRIC004 on PAO, METRIC006 on the Rights Ontology, METRIC008 on PAO.
3. **No default is changed here.** The corpus supports METRIC001, METRIC002 and METRIC003 as they
   are. For the six rules with false positives, a limit cannot fix the cause; each would need a
   scope change (reading restrictions, `dcam:` or inherited signatures, upper-ontology alignment,
   own-module imports), a product decision for its own issue.
4. **Known-poor files are missing** for METRIC004, METRIC005 and METRIC007 to METRIC013. Recall
   needs one per rule; a synthetic fixture shows a boundary, not a real ontology.
