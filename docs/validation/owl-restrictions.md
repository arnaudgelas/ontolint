# OWL035 on OWL 1 era files

Issue #196 asked how often the OWL 1 and Protege 3 idiom "one restriction with both a minimum and a maximum cardinality" occurs,
because OWL035 reports a restriction with more than one constraint as an error ([`../severity-decisions.md`](../severity-decisions.md),
"OWL035"). The OWL 2 era files of corpus A (1,075 restrictions) had none, which cannot decide it. **This page changes no rule, severity or default.**

## Method

Three public repositories whose test data is OWL 1 era RDF, pinned by commit and licence in
[`owl-restrictions-corpus.json`](owl-restrictions-corpus.json): Apache Jena's core test data (the W3C OWL 1 test cases among
them), the OWL API's contract resources and Pellet's test data. Only the listed directories are checked out, and nothing is vendored:

```sh
uv run python scripts/owl_restriction_count.py fetch DIR    # checks each repository out at its commit, refuses another
uv run python scripts/owl_restriction_count.py count DIR    # parses every RDF file, rewrites the results and this table
uv run python scripts/owl_restriction_count.py check DIR    # fails when the counts differ from the recorded results
```

Every `.owl`, `.rdf`, `.xml`, `.ttl`, `.n3` and `.nt` file of at most 5 MiB is parsed with rdflib; the ones it cannot read (OWL/XML,
functional syntax, RDF/XML with a malformed literal) are counted as not parsed, and a file named like RDF that the size cap or a link
leaves out is listed as skipped (the results name it), so none is dropped. The script counts the restrictions
(nodes typed `owl:Restriction`, the nodes OWL035 visits) independently of the rule and checks the rule against its own count: the rule
reports "more than one constraint" for some restriction exactly when one has several constraint triples, and never for more than there are.
The second table keeps the files that use no OWL 2 vocabulary (qualified cardinalities, `owl:hasSelf`, `owl:NamedIndividual`, property
chains and so on), so an OWL 1 only reading does not depend on the repository's date. The results are of one ontolint and one rdflib version
([`owl-restrictions-results.json`](owl-restrictions-results.json) records both, and `check` names them when it fails). `check` itself runs offline on the checkouts, but reproducing it means first fetching
the three external pinned repositories (`fetch`), so it is not part of the mandatory CI.

## Results

<!-- owl_restriction_count.py: begin -->

### All files

| Repository | RDF files parsed (not parsed, skipped) | Files with a restriction | Restrictions | Several constraints | Minimum and maximum together | Min and max as two restrictions of one intersection | OWL035 findings |
| --- | --- | --- | --- | --- | --- | --- | --- |
| jena-core-testing | 1940 (198, 0) | 272 | 3529 | 1 | 0 | 13 | 6 |
| owlapi-contract | 100 (14, 0) | 34 | 514 | 0 | 0 | 0 | 0 |
| pellet-tests | 1408 (20, 1) | 265 | 4215 | 0 | 0 | 6 | 4 |
| **all** | 3448 (232, 1) | 571 | 8258 | 1 | 0 | 19 | 10 |

### Files that use no OWL 2 vocabulary

| Repository | RDF files parsed (not parsed, skipped) | Files with a restriction | Restrictions | Several constraints | Minimum and maximum together | Min and max as two restrictions of one intersection | OWL035 findings |
| --- | --- | --- | --- | --- | --- | --- | --- |
| jena-core-testing | 1940 (198, 0) | 272 | 3529 | 1 | 0 | 13 | 6 |
| owlapi-contract | 100 (14, 0) | 24 | 438 | 0 | 0 | 0 | 0 |
| pellet-tests | 1408 (20, 1) | 245 | 3895 | 0 | 0 | 6 | 3 |
| **all** | 3448 (232, 1) | 541 | 7862 | 1 | 0 | 19 | 9 |

<!-- owl_restriction_count.py: end -->

## Reading

* **The idiom does not occur in this corpus.** 0 of 8,258 restrictions (0 of 7,862 in files with no OWL 2 vocabulary) carry a minimum
  and a maximum cardinality together. The corpus is tool test data and not a random sample, so this is the absence of a counterexample
  here and not an estimate of how often people write the idiom: no rate is derived from it.
* **The same bounds do occur as two restrictions.** 19 `owl:intersectionOf` lists hold a minimum and a maximum restriction on one
  property, the form OWL035 accepts. That shows the two-restriction form is used; it does not show that a tool rewrote a
  one-restriction spelling, or that each pair was meant as the idiom.
* **The ten OWL035 findings are not the idiom.** Seven are in files named `bad...` (the W3C negative tests `I3.2/bad001` to `bad003`, in
  Jena and in Pellet, and a Jena bug report, `reasoners/bugs/bad-intersection.owl`): a restriction with no constraint. One more is a
  restriction with no constraint in a test of cardinality (`wg/cardinality/conclusions005-mod.rdf`). One is the only restriction with
  several constraint triples, a node typed both `owl:Class` and `owl:Restriction` in a cardinality test case
  (`wg/description-logic/premises905.rdf`). One is an `owl:hasSelf` value of false in an OWL 2 file (`OWL2Primer.owl`).

## Limits

* The corpus is the test data of three tools, not a sample of ontologies people publish. It contains genuine OWL 1 files (the W3C test
  cases, wine, food) and deliberately malformed ones, so the count of findings is not a rate on real ontologies.
* Protege 3 ontologies as published were not counted: no repository with a stated licence and a pinned commit was found. BioPAX
  has no licence file, and SWEET is OWL 2 era with no `maxCardinality`.
* 232 of the 3,680 RDF files within the size cap were not parsed (6.3%), mostly formats rdflib does not read, and one file over the
  cap was not read (`vicodi.ttl` in Pellet's test data, 23 MB). A file in such a format that held the idiom is not counted, and 3,680
  is not the number of RDF documents in the three repositories.
* The era of a file is judged by its vocabulary, not by a date. A file that uses no OWL 2 term may still have been written for OWL 2.
* The results are not checked weekly: run `check` by hand when a rule or the manifest changes.
