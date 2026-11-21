# METRIC calibration: candidate corpus additions

Ten more public ontologies that could join the 21-file corpus of
[`metric-calibration.md`](metric-calibration.md) (issues #8 and #152). They are listed in
[`metric-candidates.json`](metric-candidates.json), pinned and licensed as the committed corpus is, and
measured with the same harness. **None is part of the corpus yet, none is labelled, and no default
changes.**

| Candidate | Pin | Licence (where verified) | Why it is here |
| --- | --- | --- | --- |
| `dcat3.ttl`, W3C DCAT 3 | Internet Archive snapshot 2024-11-07, same SHA-256 as the namespace document | CC-BY-4.0, `dcterms:license` in the file | a reviewed Recommendation, suggested silent |
| `org.ttl`, W3C Organization Ontology | Internet Archive snapshot 2026-07-17 | PDDL-1.0, `dct:license` in the file | suggested silent |
| `foaf.rdf`, FOAF 0.99 | Internet Archive snapshot 2014-01-15 | CC-BY-1.0, stated on `xmlns.com/foaf/spec/` | suggested silent |
| `uo-base.owl`, Units of measurement ontology | commit `5da8f423c8817986201f27bc26f7f66b2623de40` | CC-BY-4.0, `LICENSE.md` and the file | suggested silent |
| `ids-vcard-20140522.ttl` | commit `a9b79eab4f` of the IDS Information Model | the original's (W3C), check before approving | fires METRIC004 (10.40) and METRIC008 (0.57) |
| `ids-dctype-20120614.ttl` | the same commit | the original's (DCMI, CC-BY), check | fires METRIC005 (0.75) and METRIC006 |
| `ids-ma-ont-20120209.ttl` | the same commit | the original's (W3C), check | fires METRIC001 and METRIC007 (6.07) |
| `brick-ref-schema.ttl` | commit `3fdb57060a` of Brick | BSD-3-Clause (repository), the file states none | fires METRIC008 (0.75) and METRIC009 |
| `gaia-x-openlabel.owl.ttl` | commit `f35d7c37d1` of the Gaia-X 4 PLC-AAD ontology management base | EPL-2.0 (repository), derives from a third-party standard, check | fires METRIC006 (0 properties for 243 classes) |
| `geodcat-ap-930.ttl` | commit `7e7d6a82f4` of GeoDCAT-AP | CC-BY-4.0, `dc:license` in the file | fires METRIC010 (1.00) and METRIC013 (0.83) |

**No candidate is pinned by a mutable document any more** (issue #152). The three namespace documents are fetched from the
Internet Archive snapshot whose bytes have the SHA-256 recorded, so the bytes can be reproduced after the publisher changes
the live file; `fetch` still refuses a different checksum. SKOS Core, in the corpus, has no snapshot with its bytes (six snapshots
of its `.rdf` URL and twelve of its namespace URL were compared on 2026-11-21) and stays pinned by checksum only, which its manifest
entry says. A candidate whose licence could not be verified was left out: the W3C DQV namespace document states none.

**Labels are blank.** Each entry's `labels` are `unassessed`, and each carries a `suggested` block (an outcome, a one-line reason
and a source URL). A suggestion is a prompt for the maintainer; it is not a label, no script counts it, and no reason in it was
checked in the file. **A firing is not a judgement of poor quality**: the six new candidates were found by running the rules over
the files of five public repositories, so each one fires at least one rule, and the earlier corpus showed that most such firings
are a modelling choice the rule does not see (a taxonomy of twelve unrelated types, a code list over foreign concepts). They are
nominees for the maintainer's `fire` label, with `suggested.expect` left `unknown`. **METRIC012 has no candidate**: no file of those
repositories averages fewer than four words per definition, so its recall stays unmeasured until one is found.

```sh
uv run python scripts/metric_sweep.py fetch-candidates DIR      # network; refuses a changed checksum
uv run python scripts/metric_sweep.py measure-candidates DIR    # lint; rewrites metric-candidates-results.json and the table below
```

To adopt a candidate, copy its entry into `metric-corpus.json` with the maintainer's labels (drop `suggested`),
then run `scripts/metric_corpus.py measure DIR`.

Measured values per rule (the number after `METRIC`), at the recorded ontolint version; a star marks a default
that flags the file, a dash a rule that makes no comparison (population below the sample gate, or empty). These
are measurements, not outcomes: a flag is not a false positive until a label says so. DCAT 3 and ORG each own
only 9 classes, below the sample gate of 10, so the class rules make no comparison on them: they add little.

<!-- metric_sweep.py: candidates begin -->

| Candidate | 001 | 002 | 003 | 004 | 005 | 006 | 007 | 008 | 009 | 010 | 011 | 012 | 013 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dcat3.ttl | - | - | 0 | - | - | - | - | 0.2432 | 1 | 0.2619 | 3 | - | 0.2361 |
| org.ttl | - | - | 0 | - | - | - | - | 0 | 1 | 0.209 | 0 | - | 0.1579 |
| foaf.rdf | 0 | 0 | 0 | 2.667 | 0.1538 | 4.692 | 4.692 | 0.08333 | 0* | 0.05263 | 0 | 4.923 | 0 |
| uo-base.owl | 0 | 0.2892 | - | 2.368 | 0 | 0* | 0 | - | 0.01568* | 0 | 0 | 19.76 | 0 |
| ids-vcard-20140522.ttl | 0 | 0.4839 | 0 | 10.4* | 0 | 1.355 | 1.355 | 0.5714* | 1 | 0 | 0 | 10.06 | 0 |
| ids-dctype-20120614.ttl | 0 | 0 | - | 2 | 0.75* | 0* | 0 | - | 1 | - | 0 | 23.67 | 0 |
| ids-ma-ont-20120209.ttl | 1* | 0 | 0.2471 | 2 | 0 | 6.071 | 6.071* | 0.4706 | - | 0 | 1 | 16 | 0 |
| brick-ref-schema.ttl | - | - | 0.08333 | - | - | - | - | 0.75* | 0* | - | 1 | - | 0.04167 |
| gaia-x-openlabel.owl.ttl | 0.004115 | 0.004115 | - | 3.766 | 0 | 0* | 0 | - | 1 | 0 | 0 | 11.55 | 0 |
| geodcat-ap-930.ttl | - | - | 0 | - | - | - | - | 0 | 1 | 1* | 0 | - | 0.8276* |

<!-- metric_sweep.py: candidates end -->
