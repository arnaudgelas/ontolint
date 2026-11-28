# SKOS001 on non-concept preferred labels

SKOS integrity condition S14 ("a resource has no more than one value of `skos:prefLabel` per language tag") binds any resource.
SKOS001 reads only owned resources typed `skos:Concept`, so a scheme, a collection or an `owl:Class` with two preferred labels in one
language is not reported. Issue #181 (question 3) left open whether to widen the rule, and issue #195 asked what a widened rule would
report on real vocabularies, because the finding is an error and a widening would start to fail `--fail-on error` for files that pass
today. The metric corpus could not say: of its 68 labelled resources 17 are not concepts and none has two labels in one language.
**This page changes no rule, severity or default.**

## Method

13 public SKOS vocabularies (the data and test data of vocabulary tools, published thesauri and one set of OWL ontologies), pinned by
commit and licence in [`skos-preflabel-corpus.json`](skos-preflabel-corpus.json). Nothing is vendored:

```sh
uv run python scripts/skos_preflabel_count.py fetch DIR    # checks each repository out at its commit, refuses another
uv run python scripts/skos_preflabel_count.py count DIR    # parses every RDF file, rewrites the results and this table
uv run python scripts/skos_preflabel_count.py check DIR    # fails when the counts differ from the recorded results
```

A *labelled resource* is a subject of at least one literal `skos:prefLabel`. Each is given the first kind its asserted types name
(concept, scheme, collection, class, other, untyped), and a *pair* is a (resource, language) with more than one preferred label,
languages compared as SKOS001 compares them. The count reads every concept, the rule only the owned ones, so the rule's findings
(checked on every file) are at most the concept pairs. The reading of RDF files is that of the OWL035 count
([`owl-restrictions.md`](owl-restrictions.md)); the results are of one ontolint and one rdflib version, which `check` names when it
fails. [`tests/fixtures/skos_nonconcept_preflabels.ttl`](../../tests/fixtures/skos_nonconcept_preflabels.ttl) holds one pair of each
kind, which no real vocabulary does, and `tests/test_skos_preflabel_count.py` pins what the rule reports on it today and what a
widened rule would add (six pairs), so the decision flips a test on purpose. `check` itself runs offline on the checkouts, but reproducing it means first fetching the
13 external pinned repositories (`fetch`), so it is not part of the mandatory CI.

## Results

<!-- skos_preflabel_count.py: begin -->

### Per repository

| Repository | RDF files parsed (not parsed, skipped) | Files with a preferred label | Labelled concepts | Labelled non-concepts | Concept pairs with several labels in one language | SKOS001 findings today | Non-concept pairs a widened rule adds | Files that would newly fail |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| skosify | 4 (1, 0) | 3 | 18 | 0 | 0 | 0 | 0 | 0 |
| skohub-vocabs | 11 (0, 0) | 9 | 707 | 4 | 0 | 0 | 0 | 0 |
| skos-play | 11 (27, 0) | 7 | 9645 | 105 | 2 | 2 | 0 | 0 |
| ga-vocabs | 49 (0, 0) | 46 | 2129 | 46 | 0 | 0 | 0 | 0 |
| voc4cat | 618 (0, 0) | 617 | 610 | 7 | 0 | 0 | 0 | 0 |
| tate-skos | 1 (0, 0) | 1 | 2409 | 1 | 0 | 0 | 0 | 0 |
| universalevidence-interventions | 2 (0, 0) | 1 | 2784 | 0 | 0 | 0 | 0 | 0 |
| universalevidence-conditions-outcomes | 3 (0, 0) | 2 | 7130 | 3 | 0 | 0 | 0 | 0 |
| togaf-content-metamodel | 3 (0, 0) | 1 | 43 | 1 | 0 | 0 | 0 | 0 |
| vocprez | 1 (0, 0) | 1 | 235 | 1 | 0 | 0 | 0 | 0 |
| skosprovider | 3 (0, 0) | 3 | 46 | 9 | 0 | 0 | 0 | 0 |
| vocview | 4 (3, 0) | 2 | 5 | 2 | 0 | 0 | 0 | 0 |
| sweet | 234 (3, 0) | 1 | 0 | 1 | 0 | 0 | 0 | 0 |
| **all** | 944 (34, 0) | 694 | 25761 | 180 | 2 | 2 | 0 | 0 |

### By kind of resource, all repositories

| Kind of resource | Labelled resources | (Resource, language) pairs with several preferred labels |
| --- | --- | --- |
| concept | 25761 | 2 |
| scheme | 68 | 0 |
| collection | 108 | 0 |
| class | 1 | 0 |
| other | 2 | 0 |
| untyped | 1 | 0 |

<!-- skos_preflabel_count.py: end -->

## Reading

* **A widened rule would add no finding here.** Of 25,941 resources with a preferred label, 180 are not typed `skos:Concept` (68
  schemes, 108 collections, 1 class, 2 of another type, 1 untyped) and none has two labels in one language: no file of the 694 with a
  preferred label would newly fail. The two pairs that exist belong to concepts (in SKOS Play's examples), which SKOS001 already reports.
* **The widened population is small.** Non-concepts are 0.7% of the labelled resources, and a single `owl:Class` carries a
  preferred label (in SWEET). The cost of widening, measured here, is zero findings and zero newly failing files; its benefit, a
  report on a defect the specification names, is not measured by this count, which finds no instance of it.
* **No rate is derived.** The vocabularies are the ones whose repositories could be found with a stated licence, not a random sample
  of published SKOS. The count says that this corpus holds no counterexample.

## Limits

* The OWL-style case (`owl:Class` or `rdfs:Class` resources labelled with `skos:prefLabel`, as in OBO-flavoured files) is covered by
  one resource. A vocabulary written by hand in an ontology editor is where a second label is most likely, and it is the least
  represented here.
* 34 of the 978 RDF files within the size cap were not parsed (the formats rdflib does not read), and no file was over the cap. A
  vocabulary in such a format that held a pair is not counted. 978 is not the number of RDF documents in the repositories.
* SKOS-XL (`skosxl:prefLabel`) and sub-properties of `skos:prefLabel` are not counted; neither does SKOS001 read them.
* Five repositories hold 93% of the labelled resources (SKOS Play's examples alone 38%, then the two Universal Evidence thesauri,
  tate-skos and the Geoscience Australia vocabularies), so the zero is mostly the zero of those five.
* The results are not checked weekly: run `check` by hand when the rule, the manifest or rdflib changes.
