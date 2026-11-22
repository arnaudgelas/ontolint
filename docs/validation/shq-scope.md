# SHQ001, SHQ002 and SHQ003 on production shapes graphs

Issue #208 asked whether the scope changes of issue #63 are noisy on real shapes graphs: SHQ001 and SHQ002 judge the
property shapes that have a target of their own (a stand-alone form field), and SHQ003 keeps its widened condition
([`../severity-decisions.md`](../severity-decisions.md), "Scope questions"). The W3C test suites measured them on contrived
files only. **This page changes no rule, severity or default.**

## Method

Five public repositories, pinned by commit and licence in [`shq-scope-corpus.json`](shq-scope-corpus.json): Brick
(building metadata), the Gaia-X 4 PLC-AAD ontology management base (automotive data spaces), the IDS Information Model (data
spaces), QUDT (units) and GeoDCAT-AP (geospatial metadata). Every `.ttl` file with a shape in it is counted, 126 in all. Nothing
is vendored:

```sh
uv run python scripts/shq_scope_count.py fetch DIR    # checks each repository out at its commit, refuses another
uv run python scripts/shq_scope_count.py count DIR    # lints every shapes file, rewrites the results and this table
uv run python scripts/shq_scope_count.py check DIR    # fails when the counts differ from the recorded results
```

Each file is a `--shapes` graph against an empty data graph. The script counts the new scope apart from the rule and checks it
against the rule's findings, so a figure is the rule's. The results are of one ontolint version
([`shq-scope-results.json`](shq-scope-results.json) records it); `check` needs the network and the checkouts, so it is not in the mandatory CI: [`../releasing.md`](../releasing.md) runs it at every release and the weekly corpus job between releases ([`../ci-schedule.md`](../ci-schedule.md)).

## Results

<!-- shq_scope_count.py: begin -->

### SHQ001 and SHQ002

| Repository | Shapes files | Node shapes | Property shapes judged before | Targeted only (new) | SHQ001 | of which new | SHQ002 | of which new |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| brick | 10 | 786 | 841 | 0 | 686 | 0 | 786 | 0 |
| gaia-x4plc-aad-omb | 23 | 300 | 1777 | 0 | 509 | 0 | 202 | 0 |
| ids-information-model | 60 | 135 | 300 | 0 | 299 | 0 | 299 | 0 |
| qudt | 30 | 338 | 587 | 0 | 581 | 0 | 587 | 0 |
| geodcat-ap | 3 | 112 | 1321 | 0 | 27 | 0 | 27 | 0 |
| **all** | 126 | 1671 | 4826 | 0 | 2102 | 0 | 1901 | 0 |

### SHQ003

*Per shape* is SHQ003's findings over the node and property shapes.

| Repository | SHQ003 (wide) | SHQ003 (0.12.0 set) | Added by the widening | Per shape | Files the widening alone fails under `strict` |
| --- | --- | --- | --- | --- | --- |
| brick | 543 | 533 | +10 (1.9%) | 33.4% | 0 of 10 |
| gaia-x4plc-aad-omb | 1533 | 1325 | +208 (15.7%) | 73.8% | 0 of 23 |
| ids-information-model | 56 | 55 | +1 (1.8%) | 12.9% | 0 of 60 |
| qudt | 581 | 505 | +76 (15.0%) | 62.8% | 0 of 30 |
| geodcat-ap | 1321 | 714 | +607 (85.0%) | 92.2% | 0 of 3 |
| **all** | 4034 | 3132 | +902 (28.8%) | 62.1% | 0 of 126 |

### What the widening adds

A shape counts for each widened parameter it carries.

| Parameter | Shapes it adds a finding for |
| --- | --- |
| `sh:nodeKind` | 636 |
| `sh:closed` | 151 |
| `sh:or` | 117 |
| `sh:hasValue` | 31 |
| `sh:qualifiedValueShape` | 16 |
| `sh:disjoint` | 8 |
| `sh:xone` | 3 |

<!-- shq_scope_count.py: end -->

## Reading them

- **SHQ001 and SHQ002: the widening adds nothing here.** Of 4,826 property shapes (`sh:PropertyShape`, or a value of
  `sh:property`), none of the five repositories has a property shape that is reached by a target of its own and not through
  `sh:property`: the new column is 0. The 35 such shapes of the W3C corpus are test cases. Production shapes graphs attach
  their property shapes to a node shape, which is what the rule judged already. The findings that exist (2,102 for SHQ001,
  1,901 for SHQ002) are those of the old scope: most shapes in Brick, QUDT and IDS have no `sh:name` or `sh:description`.
- **SHQ003: the widening is real and is info.** It adds +902 findings (+28.8% over the nine parameters of 0.12.0), against
  +42% on the W3C corpus; GeoDCAT-AP alone is +85%, because its generated property shapes carry `sh:nodeKind` and little else.
  `sh:nodeKind` is the parameter of two thirds of the added shapes (636 of 962 parameter occurrences; a shape counts for each
  widened parameter it carries). The rule is info, so no exit code changes under `recommended`, `ci`, `obo`, `fair`, and none
  under `strict` either: no file of the 126 has the widening as its only SHQ finding, because each has another one.
- **Decision (issue #208): keep both, ship nothing behind a profile.** The first has no cost in production, the second only
  info findings that SHACL 4.x justifies (a `sh:nodeKind` constraint produces a validation result, 2.1.5 copies a shape's
  `sh:message` into it). If the noise matters to a project, `severity_overrides` or `--ignore SHQ003` is the lever; dropping
  `sh:nodeKind` from the widened list is the one change that would remove most of it, and it is not taken because the
  specification names no principled boundary.

## Limits

- Five repositories are a sample: public vocabulary and data-space models, picked for their licence and their shapes, not drawn
  at random. An application profile with stand-alone targeted property shapes may differ. A repository that does is the case
  that would reopen the first point; the script counts it from one manifest line.
- The counts are of the shapes the script parses as Turtle; a shapes graph in another syntax, or a file over 5 MiB, is not counted.
- *Per shape* mixes node and property shapes, and a finding is one per shape: two blank-node property shapes of one parent and one
  content are one finding (the rule names a blank node by its content), so the rule's count can be below the number of shapes.
- `check` needs the network and the checkouts, so it is not mandatory CI; running it at release is the corpus check of #169, which a
  follow-up issue extends to this corpus. Until then the counts are a snapshot, and the page says which ontolint version made them.
- A repository that publishes several releases of one shapes graph (GeoDCAT-AP has three) is counted once per file.
