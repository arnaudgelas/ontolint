# METRIC calibration: candidate corpus additions

Four more public ontologies that could join the 21-file corpus of
[`metric-calibration.md`](metric-calibration.md) (issue #8). They are listed in
[`metric-candidates.json`](metric-candidates.json), pinned and licensed as the committed corpus is, and
measured with the same harness. **None is part of the corpus yet, none is labelled, and no default
changes.**

| Candidate | Pin | Licence (where verified) | Size |
| --- | --- | --- | --- |
| `dcat3.ttl`, W3C DCAT 3 | checksum only (W3C namespace document, mutable) | CC-BY-4.0, `dcterms:license` in the file | 200,345 bytes |
| `org.ttl`, W3C Organization Ontology | checksum only (namespace document) | PDDL-1.0, `dct:license` in the file | 84,162 bytes |
| `foaf.rdf`, FOAF 0.99 | checksum only (xmlns.com, mutable) | CC-BY-1.0, stated on `xmlns.com/foaf/spec/` (the RDF states none) | 44,209 bytes |
| `uo-base.owl`, Units of measurement ontology | commit `5da8f423c8817986201f27bc26f7f66b2623de40` | CC-BY-4.0, `LICENSE.md` at that commit and the file | 647,751 bytes |

A candidate that is not fetched at a commit is pinned by its SHA-256 alone, like SKOS Core in the corpus: when
its publisher changes it, `fetch` fails and the pin has to be renewed on purpose. A candidate whose licence
could not be verified was left out: the W3C DQV namespace document states none, so it is not listed.

**Labels are blank.** Each entry's `labels` are `unassessed`, and each carries a `suggested` block (an expected
outcome, a one-line reason and a source URL). A suggestion is a prompt for the maintainer. It is not a label,
it is not counted by any script, and no reason in it was checked in the file. Every suggestion here is
"silent": a reviewed, widely reused vocabulary. **There is no known-poor candidate**, so adding these four does
not give METRIC004 to METRIC013 any measurable recall; a known-poor file has to come from the maintainer.

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

<!-- metric_sweep.py: candidates end -->
