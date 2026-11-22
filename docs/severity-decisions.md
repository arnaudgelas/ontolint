# Severity and confidence decisions (issue #63): decision record

**Status: proposed, not yet decided.** The decisions below were prepared by Claude from this record's recommendations. They
become the maintainer's decisions only when the maintainer merges pull request #198, which carries them, and each one is applied
only when its pull request of "Where each decision ships" merges (#199 to #204); until then nothing here is in force, and
`TODO.md` keeps listing the rows as pending. "Decisions taken" records what is proposed, including the three places where it
departs from a recommendation. A row marked "maintainer" is not decided here. The maintainer's approval, the date and the
merge commit of each pull request are the evidence of a decision; the audit item in `TODO.md` drops a row when the pull request
that ships it merges.

## Decisions taken

### The three cross-cutting questions

* **D1, what `certain` means.** A finding is `certain` when its condition is exact: the same graph always yields it, and the
  cited specification gives the matched pattern a fixed meaning or forbids it. It is `heuristic` when the condition rests on a
  convention (a threshold, a naming or locality judgement) or when the specification leaves the outcome to the engine. Whether
  the author may have meant the pattern is the business of the severity, not of the confidence. This keeps OWL004 and OWL007
  (`certain` today, with the same "may be intended" caveat as OWL023 and SHQ016) consistent with the rest.
  *Departures from the recommendations below:* **OWL023 becomes `certain`** (the record recommended keeping `heuristic`: the
  condition is exact and its category is already `deterministic`); **SHQ016 stays `heuristic`**, for a different reason than the
  record's (SHACL leaves validation with recursive shapes undefined, 3.4.3, so the result depends on the engine); **METRIC011
  becomes `heuristic`** (the calibration page recommended keeping `certain`; its limit of 10 is a convention, as for every other
  METRIC rule, and its category is `heuristic`).
* **D2, one rule with two severities: option A.** `RuleContext.add` gains an optional `severity=`; the rule's registered
  severity stays the default shown by `--list-rules` and SARIF `defaultConfiguration` and replaced by `severity_overrides`. Two
  rows need it (SHQ011 and SHQ015); OWL010 and OWL045 are decided for the whole rule, so they do not. Option B would re-identify
  SHQ011's findings for one rule; option C would give up the warning that matches the engines.
* **D3, `tests/golden/legacy_rules.json`.** It stays the pre-0.9 proof, and is re-pinned only for the entries a decision moves
  (OWL009, OWL010, OWL013, OWL014), in the same commit and listed in its message. A new test lists the changed entries and compares
  them with the decision, so an unrelated change cannot hide in the re-pin.

### The rows

All rows are the recommendations of this record, except the departures above and row 18.

| Row | Decision | Ships in |
| --- | --- | --- |
| OWL009, OWL013, OWL014 | error | OWL pull request #199 (closes #178) |
| OWL010, OWL032 | warning (the whole rule) | OWL pull request #199 (closes #178) |
| OWL045 | error (the whole rule; a repeated member is inconsistent or empties a class, see the OWL specification) | OWL pull request #199 (closes #178) |
| OWL038 | keep error | none |
| OWL035 | keep error; the count is the issue "Count OWL035 ... on OWL 1 era ontologies" (v0.18.0) | none |
| OWL041, OWL023 | `certain` | OWL pull request #199 (#180, confidence) |
| OWL004, OWL007 | no change (the TODO proposal is dropped) | none |
| SHQ011 | `\/` and `[]a]` warning, `[[a]` and every other malformed pattern error | SHQ pull request #201 (closes #179) |
| SHQ015 | an unknown letter error, flags without a pattern warning | SHQ pull request #201 (closes #179) |
| SHQ013 | `certain`, keep warning | SHQ pull request #201 (closes #179) |
| SHQ008, SHQ018 | `certain`; SHQ008 derived integer types keep the error | SHQ pull request #201 (closes #179) |
| SHQ016 | keep `heuristic` | none |
| SKOS001, SKOS002 | category `deterministic` | SKOS pull request #202 (#180, category) |
| SHQ003 | keep the widened condition; the docstring states both figures | scope pull request #203 (closes #181) |
| SHQ001, SHQ002 | include directly targeted property shapes | scope pull request #203 (closes #181) |
| SHQ014 on a node that is only loosely a shape | keep the permissive notion (any subject of an `sh:` predicate is judged); stated in the SHQ014 specification and pinned in `tests/test_shq_specification.py` | docs pull request of #138 |
| SKOS001 scope (S14) | deferred: needs a count ("Count the widened SKOS001 scope", v0.18.0) | none |
| METRIC001, METRIC002 | keep warning (no curated file fails; the calibration sweep of #163 does not reopen it) | none |
| METRIC011 | `heuristic`; a catalogue invariant for the METRIC family | METRIC pull request #204 (closes #183) |
| Approval of the specifications | **maintainer**: not decided here | none |

### What the decisions leave open

* The approval of the OWL, METRIC and SHQ specifications (issue #182) is a human review; the pull requests only correct the
  specifications and pin their severity and confidence in tests.
* `category` still disagrees with the finding confidence for OWL004, OWL007, OWL009, OWL010, OWL013, OWL014 (category
  `heuristic`, findings `certain`): a catalogue-wide alignment is a follow-up, not part of #63. Its first step is done
  (issue #180): no `deterministic` rule reports a `heuristic` finding (SKOS011, SKOS015, SKOS017, SKOS019, SKOS020,
  SKOS021, ALIGN015 and DATA003 became `heuristic`; `tests/test_category_confidence.py`). Its second step is done: the 14 rules
  whose `certain` findings rest on a condition the specification forbids or gives a fixed meaning (OWL003, OWL004, OWL007,
  OWL009, OWL010, OWL013, OWL014, CLS003, CLS004, CLS014, CLS019, IRI001, IRI009, LEX014) are `deterministic`, and held so
  by `ALIGNED` in the test. What remains is 16 rules whose category is `heuristic` and whose findings are `certain`:
  those that rest on a convention (IRI006, IRI010, IRI012, IRI016, IRI017, IRI018, LEX001, LEX002, LEX005, LEX011, LEX019,
  LEX025: by D1 their findings would be `heuristic`, which a consumer filtering on confidence would see) and ONT001, ONT003,
  ALIGN002 and LEX013, which this step did not decide. `context-dependent` rules (FAIR, OBO, ALIGN009) are outside the check.
* Counts that need corpora this record does not have: OWL035 and SKOS001's widening. SHQ001, SHQ002 and SHQ003 on production shapes are counted in [`validation/shq-scope.md`](validation/shq-scope.md) (issue #208).
* METRIC001 and METRIC002 rest on two flagged files; the sweep of #163 found no further case (3 true positives, no false positive, on proposed labels).

### Where each decision ships

One pull request per rule family, because every accepted row moves the same goldens (`differential.json`,
`single_graph_reports.json`, `docs/rules*`) and parallel pull requests would conflict: OWL (#178, with OWL041 and OWL023
confidence), the per-finding severity mechanism, SHQ (#179, with SHQ008, SHQ013 and SHQ018 confidence), SKOS (#180's category),
scope (#181) and METRIC (#183).

Everything here was measured on 2026-11-19 with the tree at `4845fec` (the `main` of 0.16.0 development; later commits on `main` touch SHQ012, SHQ014, SHQ023 and the LEX family (LEX003, LEX008 and LEX024 among them) but none of the rows below; the LEX020 warning counted below is not among them; no count was re-run on those commits), Python 3.13.7,
pySHACL 0.40.2 and, for the engine checks, Apache Jena 4.10.0 on Temurin 11. ROBOT, the OWL API and HermiT were not
installed, so no claim here rests on how they behave.

## How to read the evidence

* **Corpus A (ontologies).** The 21 pinned files of `docs/validation/metric-corpus.json`, fetched with
  `uv run python scripts/metric_corpus.py fetch DIR` (checksums verified): BFO 2020, CCO merged, RO core, IAO, PATO base,
  PROV-O, SKOS, SOSA/SSN, schema.org, DCMI Terms, MOD, PAO and others. 1,075 `owl:Restriction` nodes in all. A
  count here is a count on those files only.
* **Corpus B (shapes).** 974 `.ttl` files: the W3C `data-shapes` repository (`gh-pages`, 972 files, archive SHA-256
  `ed53944a2a1abca24230fbc8fb9001b9ef961c2bd7f157721a9bb29fd60b837e`, taken 2026-11-19) and the two DCAT-AP 3.0.1 SHACL files
  (commit `21f43cee5d61aa29e729e2e9193fc697f7b63861`). 930 parse as shapes graphs; 44 are not shapes graphs or not Turtle
  that rdflib reads, and are counted as 0. The W3C files are test cases, many contrived; they say how often a
  construct appears, not how often a real shapes graph is wrong. It is a different corpus from the 1,079 files of PR #46,
  so absolute numbers differ. IDS and GeoSPARQL were not fetched.
* Earlier counts: `docs/validation/coverage-gaps-0.12.0.md` (CCO, BFO, RO, DCAT-AP) found 0 findings for OWL010, OWL032,
  OWL035 and SHQ008/SHQ011.
* **Exit codes.** `ontolint FILE --profile P --format json --fail-on never` was run for `recommended`, `ci`, `obo`, `fair`,
  `strict`, `minimal` on each file of corpus A, and the exit code of every scenario was recomputed from the findings
  (an exit is 1 when a finding reaches the profile's `--fail-on`: `recommended`/`minimal` error, `ci`/`obo`/`fair` warning,
  `strict` info). See "Reproduce".

## Facts that apply to every row

1. **Profiles.** `ci`, `obo`, `fair` fail on warning; `strict` fails on info; `recommended` (the default) and `minimal`
   fail on error. `minimal` selects `ONT IRI DATA SKOS SHACL SEM` only, so **no OWL or SHQ rule runs under `minimal`**
   and no OWL/SHQ row changes its exit code; the SKOS rows run there but only change metadata. SHQ rules run only with
   `--shapes`. So: warning to error changes the exit code of `recommended` and plain `--fail-on error` only (the
   other profiles already fail on a warning); info to warning changes `ci`, `obo`, `fair` and `--fail-on warning`;
   info to error changes those and `recommended`. `strict` never changes.
2. **Baselines are unaffected.** A baseline entry is rule, focus and subject; severity, confidence and category are not
   part of it (`RuleContext.add` documents this). No row below invalidates a baseline, except a new rule ID (SHQ011,
   option B) which re-identifies the findings that move.
3. **A user can pin today's severity.** A policy file `{"severity_overrides": {"OWL013": "warning"}}` (`--config`)
   restores the old severity. Verified on MOD: six rules lowered to `info` by the policy take the run from exit 1 (3 errors,
   73 warnings) to exit 0 (76 infos). Every upgrade note below can say so.
4. **Category versus confidence.** Two different fields carry "how sure": `category` (per rule: the catalogue, `--list-rules`,
   `--explain`, SARIF rule properties) and `confidence` (per finding: JSON, SARIF result properties; `certain` or `heuristic`,
   default `heuristic`). They disagree today for many rules (see "Inconsistencies"). The issue's "confidence" rows mean the
   per-finding value; the SKOS row means the category.
5. **What every accepted row changes in the repository.** Measured by applying every row at once in the working tree and
   running 22 test modules (then discarding): 48 tests failed, in `tests/test_differential.py` (45: every CLI case embeds the rule
   metadata, so `tests/golden/differential.json` changes wherever a rule's severity or category appears, whether or not a
   finding fires), `tests/test_single_graph_reports.py` (`tests/golden/single_graph_reports.json`), `tests/test_rule_docs.py`
   (`docs/rules.md` and `docs/rules/{owl,shq,skos}.md`, regenerated by `uv run python tests/rule_docs_generator.py`),
   `tests/test_mutation_shacl_quality.py` (it pins the SHQ severity table), and `tests/test_registry.py` (only the SKOS
   category: the catalogue `rule_catalogue.csv` exists twice, `data/` and `src/ontolint/data/`). **No rule case under
   `tests/rule_cases/` fails for any severity or confidence change**, so no new positive or negative case is needed by a
   pure re-grading. The per-row split of those 48 failures was not measured (a per-row run takes about 30 minutes on this
   machine): "needs per-row run". Findings that exist in the goldens (so their `severity`/`confidence` fields move):
   OWL004 10, OWL007 5, OWL009 10, OWL010 5, OWL013 5, OWL014 5, OWL023 5, SKOS001 5, SKOS002 10 (all in `differential.json`
   and, but OWL023, in `legacy_rules.json`, which pins the pre-0.9 rules and would also need a decision on whether it
   moves); OWL032, OWL035, OWL038, OWL041, OWL045 and every SHQ row have no finding in a golden.
6. **Commit shape for any accepted batch.** One `fix!:` commit per rule family, with the code, the regenerated goldens and
   docs, and a `BREAKING CHANGE:` trailer, so that `scripts/bump_version.py` lists it under the release's upgrade notes.

## Severity and confidence rows

### Corpus A counts (`recommended` selection, findings per rule)

| Rule | Findings | Files | Confidence seen |
| --- | --- | --- | --- |
| OWL004 | 32 | 4 (MOD, PROV-O, RO core, Tractus-X) | certain 32 |
| OWL007 | 2 | 1 (Tractus-X) | certain 2 |
| OWL009 | 0 | 0 | |
| OWL010 | 0 | 0 | |
| OWL013 | 33 | 1 (MOD) | certain 33 |
| OWL014 | 12 | 1 (MOD) | certain 12 |
| OWL023 | 2 | 2 (MOD, Tractus-X) | heuristic 2 |
| OWL031, OWL032, OWL035, OWL038, OWL041, OWL045 | 0 | 0 | |
| SKOS001, SKOS002 | 0 | 0 | |

Exit codes of corpus A today: `recommended` fails 4 of 21 files, `ci` 18, `obo` 21, `fair` 18, `strict` 21, `minimal` 0.
**Every severity scenario below (OWL009, OWL010, OWL013/014, OWL032, OWL045 raised) flips 0 of 21 files in every profile**: the files
that carry a finding (MOD) already fail for another reason (OWL022 errors, OWL004 and LEX020 warnings). So corpus A cannot
discriminate; it only shows that the changes are rare in well-curated vocabularies. Corpus B (shapes): 0 findings for
SHQ007, SHQ008, SHQ011, SHQ013, SHQ015, SHQ017, SHQ018; SHQ016 2 findings in 1 file; SHQ001 898 / 277 files; SHQ002 906 / 281;
SHQ003 1,244 / 412.

### OWL009: datatype property with an object-property characteristic

* Today: warning, finding confidence `certain`, category `heuristic`. Proposed: error.
* Evidence: 0 findings on corpus A; 10 findings in the kitchen-sink golden. Standard: the module docstring (owl.py, OWL009) cites
  OWL 2 Structural Specification 9.2 and Direct Semantics Table 6: `InverseObjectProperties`, `SymmetricObjectProperty`,
  `TransitiveObjectProperty`, `AsymmetricObjectProperty` and `InverseFunctionalObjectProperty` take object property
  expressions only, so the graph is not OWL 2 DL (not re-read against the W3C text here). The family already grades the
  same class of defect as error: OWL003 (object and data property at once) and OWL016 (data property with a reflexive or
  irreflexive characteristic, "not OWL 2 DL") are errors.
* Effect: `recommended` and `--fail-on error` start failing on such a file; `ci`, `obo`, `fair`, `strict` already fail. 0 of 21 files flip.
* **Recommendation: yes, error. Confidence in the recommendation: high** (the spec argument and the family consistency agree).
  *Needs corpus count* of real files with the defect; none was found.
* Upgrade note: "OWL009 (a datatype property declared inverse of, or symmetric, transitive, asymmetric or inverse functional
  as an object property) is now an error, as OWL003 and OWL016 are: such a graph is not OWL 2 DL. `--fail-on error` runs fail
  on it. Lower it with `severity_overrides` to keep the old result."
* Commit: `fix!: report OWL009 as an error, as the other OWL 2 DL violations are`.

### OWL010: property chain with fewer than two operands

* Today: info, `certain`, category `heuristic`. Proposed: warning or error.
* Evidence: 0 findings on corpus A and on CCO, BFO, RO (coverage-gaps page). The rule reports three kinds: a one-member chain, an
  empty chain, and a non-list (literal, IRI, cyclic). SS 9.2.1 and MAP Table 16 require at least two members. Kinds differ: a
  one-member chain is the analogue of OWL032 (redundant, outside OWL 2 DL), a malformed list the analogue of OWL031 (error).
* Effect: to warning: `ci`, `obo`, `fair`, `--fail-on warning` start failing. To error: also `recommended`.
* **Recommendation: warning, for the whole rule. Confidence: medium-low.** Reason: one severity for three kinds forces the
  compromise; a warning stays quiet for the default gate while no longer being invisible to `ci`. If the maintainer wants the
  empty and malformed kinds at error (as OWL031), that needs the per-finding-severity mechanism described under SHQ011.
  Not verified: how the OWL API or ROBOT react to a one-member chain.
* Upgrade note: "OWL010 is now a warning (was info): a property chain axiom with fewer than two members is not OWL 2. `ci`, `obo`
  and `fair` fail on it."
* Commit: `fix!: report OWL010 as a warning`.

### OWL013 and OWL014: object property asserted with a literal, datatype property asserted with a resource

* Today: warning, `certain`, category `heuristic`. Proposed: error.
* Evidence: the only corpus A hits are in MOD (33 OWL013, 12 OWL014). Read one by one they are true positives under OWL 2 DL:
  `pav:createdWith "Protégé"`, `dcat:contactPoint "Name (email)"`, and `mod:authorProperty` (a datatype property) pointing to
  `pav:importedBy`. 10 and 5 findings are pinned in the goldens. Standard: DS 2.2 (literals are not in the object domain), MAP 3.2.5
  (a datatype property assertion with a resource object maps to no axiom). The family grades the matching OWL040 (literal
  `owl:hasValue` on an object property) as an error.
* Effect: `recommended` and `--fail-on error` start failing on files like MOD. 0 of 21 files flip because MOD already fails.
  Scope note: both rules judge the whole graph, borrowed axioms and imports included, so a user who loads an imported vocabulary
  can see more findings.
* **Recommendation: yes, error. Confidence: medium-high** (spec and family agree; the only observed hits are real defects; the
  cost is on users who knowingly use object properties for string metadata, who can lower the severity).
* Upgrade note: "OWL013 and OWL014 are now errors: a literal object of an object property, or a resource object of a datatype
  property, is not OWL 2 DL. `--fail-on error` and the default profile fail on them."
* Commit: `fix!: report OWL013 and OWL014 as errors`.

### OWL032: single-operand union, intersection or disjoint union

* Today: info, category `deterministic`. Proposed: warning.
* Evidence: 0 findings anywhere. The spec text says "redundant rather than wrong" but also "outside the OWL 2 DL grammar"
  (SS 8.1, 9.1.4). The nearest sibling, OWL033 (a repeated member, harmless), is a warning.
* Effect: `ci`, `obo`, `fair`, `--fail-on warning` start failing.
* **Recommendation: yes, warning. Confidence: medium-low.** Either answer is defensible; warning makes the family uniform
  (OWL010, OWL032, OWL033 all warnings). No data distinguishes them.
* Upgrade note: "OWL032 is now a warning (was info)."
* Commit: `fix!: report OWL032 as a warning`.

### OWL045: malformed `owl:AllDifferent` or `owl:AllDisjointClasses`

* Today: warning, `certain`, category `deterministic`. Proposed: error for a missing or malformed list, "as OWL031".
* Evidence: 0 findings anywhere. The rule reports five kinds: no list, several lists, malformed list, fewer than two members, a
  repeated member. The first four make an OWL 2 parser drop the axiom (MAP section 3.2, as the docstring states), which is why OWL031
  is an error; a repeated member does not. So the proposal as worded is a per-kind severity.
* Effect: `recommended` and `--fail-on error` start failing.
* **Recommendation: error for the whole rule. Confidence: medium.** The repeated-member kind (an error where `DifferentIndividuals(a a)`
  is merely suspicious) is the cost; the per-kind alternative needs the mechanism under SHQ011. Not verified against a real parser.
* Upgrade note: "OWL045 is now an error: an `owl:AllDifferent` or `owl:AllDisjointClasses` axiom that an OWL 2 parser cannot
  read is dropped silently."
* Commit: `fix!: report OWL045 as an error`.

### OWL038: existential restriction on `owl:Nothing`

* Today: error. Options: keep, or warning.
* Evidence: 0 findings. The restriction denotes the empty set, so the class is unsatisfiable (not the ontology inconsistent). The
  family grades that consequence as error elsewhere: OWL024 (unsatisfiable property) and OWL042 (unsatisfiable class) are errors.
* **Recommendation: keep error. Confidence: medium.** Downgrading would single OWL038 out. No count argues either way.
* Upgrade note and commit: none.

### OWL035: restriction without exactly one valid constraint (min and max together)

* Today: error. Proposed: "count on the corpus first".
* Evidence: of 1,075 restrictions in corpus A, **0 carry both a minimum and a maximum cardinality**; 0 findings from the rule. The CCO,
  BFO and RO counts of the coverage-gaps page are 0 too. The idiom is an OWL 1 and Protégé 3 habit, so these OWL 2 era files cannot
  show it. *Needs corpus count* on OWL 1 era ontologies; none was available.
* **Recommendation: keep error and defer; do not choose before the count. Confidence: low.** The MAP argument (every pattern consumes
  one constraint triple) supports error; the real cost is unknown.

### SHQ015: invalid `sh:flags`

* Today: warning, `heuristic`. Proposed: error (XPath raises FORX0001).
* Evidence: 0 findings on corpus B. Engine behaviour, run here: Jena 4.10.0 stops with `ExprEvalException: Unsupported flag in regex
  modifiers: z` (exit 2); pySHACL 0.40.2 ignores the letter and reports conformance. Jena accepts `q`. F&O 3.1 5.6.1 and 5.6.2 make an
  invalid flag FORX0001. The rule also reports `sh:flags` without `sh:pattern`, which is valid SHACL and ignored by engines; that
  kind should stay a warning. So "error" is again a per-kind severity.
* **Recommendation: error for an unknown letter, warning for flags without a pattern, through the mechanism chosen for SHQ011.
  Confidence: medium** (one engine raises, one ignores; the standard is clear).
* Upgrade note: "SHQ015 reports an unknown `sh:flags` letter as an error (an XPath error, FORX0001; Jena refuses the shapes graph);
  `sh:flags` without `sh:pattern` stays a warning."
* Commit: `fix!: report an unknown sh:flags letter as an error`.

### SHQ013: `sh:datatype` and `sh:class` on one shape

* Today: warning, `heuristic`, category `deterministic`. Proposed: error, `certain`, as SHQ007.
* Evidence: 0 findings on corpus B. Run on pySHACL 0.40.2: with a literal value (xsd:string datatype, `sh:class xsd:string` or
  `rdfs:Literal`) it violates; with an IRI value typed as the class it violates; **with no value node it conforms**. So the
  condition is exact (confidence `certain` is justified) but the shape fails only when a value exists, unlike SHQ007 where every
  focus node fails.
* **Recommendation: confidence `certain` (high); severity stays warning (medium).** The difference from SHQ007 is the vacuous case.
* Commit if accepted: `fix!: record SHQ013 findings as certain` (confidence only; if the maintainer also wants error, say so in the note).

### SHQ011: `\/`, `[[a]`, `[]a]` as warning

* Today: error, `heuristic`. Proposed: warning for the three forms.
* Evidence, run here: `\/` and `[]a]` conform in **both** pySHACL and Jena 4.10.0. `[[a]` conforms in pySHACL (Python
  emits a FutureWarning, "Possible nested set") but **Jena fails with `PatternSyntaxException: Unclosed character class`**. So the
  statement in PR #46 and in the SHQ011 docstring that Java engines accept `[[a]` is wrong for the Java regex engine tested. XPath
  rejects all three. 0 findings on corpus B for SHQ011 (an IDS `({)` in PR #46's corpus is a different defect).
* **Recommendation: warning for `\/` and `[]a]`; keep error for `[[a]`. Confidence: medium** (two engines, one version each; TopBraid
  and others not run).
* **Design: two severities in one rule, or a new ID.**
  * *Option A, per-finding severity.* `RuleContext.add` gains an optional `severity=` for the finding; the rule's registered severity
    stays the default (the one `--list-rules` shows and `severity_overrides` replaces). Baselines are unchanged (severity is not in the
    identity), the rule count is unchanged. Cost: `--list-rules`, SARIF `defaultConfiguration.level` and the rule reference show one
    severity for a rule that emits two; a `severity_overrides` entry flattens both; the severity tables in tests and the spec must say
    "error, warning for these forms". Touches `rules/runtime.py`, the report builders, goldens. It would serve SHQ015, OWL010 and OWL045 too.
  * *Option B, new ID* (SHQ028, free: the catalogue ends at SHQ027). `\/` and `[]a]` move to SHQ028 at warning, SHQ011 keeps the rest
    at error. Cost: those findings change identity (a baseline entry for them stops matching: `fix!:` with a baseline note), a catalogue row,
    a spec, fixtures, docs; the "two defects, one pattern" judgement must choose one of two rules per pattern (SHQ011 reports at most one
    finding per pattern today).
  * Recommendation: A if the maintainer wants the mechanism for SHQ015/OWL010/OWL045 as well (three rows need it); B only if SHQ011 is
    the only split. Confidence: medium.
* Upgrade note (A): "SHQ011 reports `\/` and `[]a]` as warnings (accepted by pySHACL and Jena, invalid XPath); the other pattern errors
  stay errors. `--fail-on error` no longer fails on those two forms."
* Commit: `fix!: report the sh:pattern forms that SHACL engines accept as warnings`.

### SHQ008 for a derived integer type

* Today: error. Options: keep, or warning.
* Evidence, run here: pySHACL 0.40.2 **refuses the shapes graph**: `sh:minCount must be a literal with datatype xsd:integer`; Jena 4.10.0
  accepts `"1"^^xsd:int` and even `1.0`. ontolint's own SHACL001 uses pySHACL: with `--select SHACL001` a `sh:minCount
  "1"^^xsd:nonNegativeInteger` shape gives SHQ008 plus `SHACL001 ... does not conform to SHACL-SHACL` and **exit 2**. The premise
  "every engine reads it as 1" (PR #46) is false for pySHACL. 0 findings on corpus B.
* **Recommendation: keep error. Confidence: high.** A warning would hide, behind exit 1 or 0, a graph on which SHACL001 already exits 2
  (with SHACL001 selected; the default selection was not run separately).

### Confidence to `certain`: OWL023, OWL041, SHQ008, SHQ016, SHQ018

* Today: findings are `heuristic` (the default) while categories say `deterministic` for OWL023, OWL041, SHQ008 and SHQ018, and `heuristic` for SHQ016.
  The docstrings call the conditions exact (`owl_axioms.py`: "every finding is certain except OWL023's"; `owl_expressions.py`: except OWL041's;
  `shacl_authoring.py`: SHQ008 and SHQ018 "deterministic, though recorded heuristic"; `shacl_quality.py`: "every finding is recorded heuristic,
  although most conditions are exact").
* Evidence: OWL023 2 findings on corpus A (MOD `foaf:depicts` with two inverses, a real multiple-inverse; Tractus-X). The only golden findings
  are OWL023 (5, `differential.json`). An OWL023 finding is not an error: its spec says "valid OWL; the inverses are entailed equivalent, which
  may be intended", so `certain` would describe the count, not the defect; SHQ016's spec says recursion "may be intended". OWL041, SHQ008 and
  SHQ018 are error-severity and exact.
* **Recommendation: `certain` for OWL041, SHQ008, SHQ018 (high); keep `heuristic` for OWL023 and SHQ016 (medium)**, where the condition is exact
  but whether it is a problem is a judgement, which is what `heuristic` means in the finding model. (METRIC011 took the opposite reading: see
  `docs/metric-calibration.md`.)
* Effect: JSON `confidence` and SARIF property change; no exit code, no baseline.
* Upgrade note: "OWL041, SHQ008 and SHQ018 findings now report confidence `certain`." Commit: `fix!: record OWL041, SHQ008 and SHQ018 findings as certain`
  (the `!` is for consumers who filter on confidence).

### Confidence of OWL004 and OWL007 (TODO.md proposes `heuristic`)

* Checked as the issue asks: every `ctx.add` for OWL004 and OWL007 passes `confidence="certain"` (owl.py, `_domains_and_ranges` and the self-inverse
  site), all 34 findings on corpus A are `certain`, and the docstrings say "Warning, certain: the count is exact ... but the intersection may be
  intended". The TODO proposal is therefore a downgrade, not a correction.
* **Recommendation: no change; delete the TODO proposal. Confidence: medium.** Same reasoning as OWL023 would argue for `heuristic` (the finding may be
  intended); the difference is that the spec and the code are already `certain` and 34 findings are in the wild. If the maintainer prefers a single rule
  for "exact count, may be intended" (OWL004, OWL007, OWL023, SHQ016), either choice is consistent provided all four are the same; today they are not.

### SKOS001, SKOS002: category `deterministic`

* Today: category `heuristic` in the catalogue and `--explain`; every finding is `certain`; the docstring says "Severity error, confidence certain:
  the triples violate integrity condition S14 / S13".
* Evidence: 0 findings on corpus A; 5 and 10 in the goldens. Metadata only: no finding, exit code or baseline changes. Touches
  `rule_catalogue.csv` twice, the `RuleSpec`, `docs/rules/skos.md`, goldens.
* **Recommendation: yes. Confidence: high.** The condition is exactly the integrity condition. Commit: `fix: classify SKOS001 and SKOS002 as deterministic`
  (not breaking; golden and `--list-rules` change).

## Scope questions

### 1. SHQ003 widened condition (+42% on corpus B, +46% on the PR's own corpus)

* On corpus B (930 readable files): the widened condition reports **1,244** findings in 412 files; the 0.12.0 condition (nine parameters, no
  deactivated exclusion; restored in a scratch run by patching the predicate) reports **878** in 290: +366 (+42%) and +122 files. The PR's +1,072
  (+46%) was on its own corpus. Info severity: no exit code or `--fail-on` result changes under any profile (`strict` already fails on any info).
* The widening follows SHACL 2.1.1 and 4.x: a shape with `sh:nodeKind`, `sh:minInclusive` and so on does produce a validation result whose message
  `sh:message` would carry.
* **Recommendation: keep the widened condition. Confidence: medium-high.** Info noise is the only cost, and the narrow subset has no principled
  boundary. Documenting the old set as deliberate would require a reason the specification does not give.
  **Counted on production shapes (issue #208): +28.8% (+902 findings) on 126 files of five repositories, +85% on GeoDCAT-AP alone, and no file changes
  its `strict` result because of it; `sh:nodeKind` carries two thirds of the added shapes. Keep, as above.** See
  [`validation/shq-scope.md`](validation/shq-scope.md).

### 2. SHQ001 and SHQ002: directly targeted property shapes

* Today they judge only property shapes that are values of `sh:property`. On corpus B: 1,259 property shapes are values of `sh:property`; 211 more are
  subjects of `sh:path` or typed `sh:PropertyShape` but not values (an upper bound: some are reached through `sh:node`, `sh:or` or `sh:qualifiedValueShape`, which the
  rule excludes on purpose); **35 of them carry a target of their own, in 33 files, and 33 of those 35 have no `sh:name`**.
  Counting every such shape would add up to 164 SHQ001 findings (info), the 33 targeted ones being the defensible part.
* SHACL 2.3 says any subject of `sh:path` is a property shape; the rule narrows it on purpose (docstring of `shapes.py`: "judge the property shapes a form shows").
  A directly targeted property shape is a stand-alone form field.
* **Recommendation: include directly targeted property shapes; keep excluding those reached only through `sh:or`, `sh:and`, `sh:xone`, `sh:not`,
  `sh:node`, `sh:qualifiedValueShape`. Confidence: low-medium** (35 shapes is a small sample of contrived test files). Info only; no exit change.
  Needs a count on real shapes graphs. **Counted (issue #208): 0 directly targeted property shapes without `sh:property` in 126 shapes files of five production
  repositories (4,826 property shapes), so the widening adds no finding there; the 35 are contrived W3C test cases. Keep.** See
  [`validation/shq-scope.md`](validation/shq-scope.md).

### 3. SKOS001 on any owned resource with a `skos:prefLabel` (S14)

* Corpus A: 68 resources carry a `skos:prefLabel`, 17 are not typed `skos:Concept`; **0 resources of any kind have two prefLabels in one language**.
  So the widening would add 0 findings here and the corpus cannot decide.
* The SKOS Reference states S14 for any resource ("A resource has no more than one value of skos:prefLabel per language tag", quoted from memory, not
  re-read here); the rule reads asserted `skos:Concept` typing only. Widening also changes the rule's blast radius: the finding
  is an error, so a non-concept with two prefLabels (a scheme, an `owl:Class`) would start failing `--fail-on error`.
* **Recommendation: widen, after a count. Confidence: low** (0 hits; the spec argument favours widening, the error severity calls for evidence).
  Alternative: widen and report the non-concept kind as a warning (needs the per-finding mechanism). *Needs corpus count.*

## Approval checklist for the specifications

Each box is the maintainer's. "Found" lists what contradicted spec and behaviour while preparing this page. The SHQ008, SHQ011 and SHQ015 statements and the OWL004/OWL007 TODO proposal named below have since been corrected (commit `docs(rules): correct the SHQ008, SHQ011 and SHQ015 specifications ...`); the severity and confidence rows are fixed by the pull requests of "Where each decision ships".

- [ ] **OWL001-OWL011, OWL013-OWL015, DATA001, DATA002**: `src/ontolint/rules/owl.py`, module docstring, 91 lines.
      Found: OWL004, OWL007, OWL009, OWL010, OWL013, OWL014 say "certain" while their catalogue category is `heuristic`
      (see fact 4); TODO.md proposes `heuristic` for OWL004/OWL007, contradicting the docstring and the code.
- [ ] **OWL012**: `src/ontolint/rules/classes.py` (the module docstring is one line; the OWL012 specification is in `owl.py`'s list, which names it as emitted in `classes.py`).
- [ ] **OWL016-OWL030**: `src/ontolint/rules/owl_axioms.py`, module docstring, 96 lines.
      Found: "Every finding is certain except OWL023's" while the OWL023 category is `deterministic`.
- [ ] **OWL031-OWL045**: `src/ontolint/rules/owl_expressions.py`, module docstring, 135 lines.
      Found: "Every finding is certain except OWL041's" with category `deterministic`. OWL032 and OWL010 are described as outside OWL 2 DL yet info, while OWL016
      and OWL009's "not OWL 2 DL" grades differ (error versus warning): the family has no stated rule for what "not OWL 2 DL" costs (decided by the rows above).
      OWL045's one condition has five kinds of defect of different gravity under one severity.
- [ ] **METRIC001-METRIC013**: `src/ontolint/rules/metrics.py`, module docstring, 115 lines (specifications, `docs/measurements.md`,
      `docs/metric-thresholds.md`). The open points are in `docs/metric-calibration.md`, "Approval of the METRIC specifications": METRIC004 and METRIC005 are gated on owned classes
      while the text says "population"; METRIC011's `certain`; the `dcam:` reading of METRIC005 (issue #66). Not re-audited here.
- [ ] **SHQ001-SHQ006**: `src/ontolint/rules/shapes.py`, 66 lines. Found: SHQ001 and SHQ002 exclude directly targeted property shapes (scope question 2).
- [ ] **SHQ009, 010, 012, 014-016, 022, 023**: `src/ontolint/rules/shacl_quality.py`, 71 lines.
      Found: SHQ015 mixes two defects of different gravity (an XPath error and a no-op); the text "Python- or Java-based engines may accept it" is
      true of Python (verified) and untrue of Jena, which refuses an unknown flag.
- [ ] **SHQ007, 008, 011, 013, 017-021, 024-027**: `src/ontolint/rules/shacl_authoring.py`, 145 lines.
      Found: SHQ011 says a Java engine may accept `[[a]` ("a Java union"): Jena 4.10.0 rejects it (`Unclosed character class`). SHQ008's rationale and PR #46 say
      engines read a derived integer type as its value: pySHACL refuses the shapes graph (SHACL001, exit 2). The module header says "a documented subset of SHQ007-SHQ027".
- [ ] **SKOS001-SKOS006** (not in the issue's list but touched by two rows): `src/ontolint/rules/skos.py`, 23 lines. Found: "confidence certain" with category `heuristic`.

## Decisions asked (fill in)

| # | Row | Recommendation | Decision |
| --- | --- | --- | --- |
| 1 | OWL009 to error | yes (high) | error |
| 2 | OWL010 | warning (medium-low) | warning, whole rule |
| 3 | OWL013, OWL014 to error | yes (medium-high) | error |
| 4 | OWL032 to warning | yes (medium-low) | warning |
| 5 | OWL045 to error | whole rule (medium) | error, whole rule |
| 6 | OWL038 | keep error (medium) | keep error |
| 7 | OWL035 | keep, count first (low) | keep error; count in v0.18.0 |
| 8 | SHQ015 | error for unknown letter (medium) | as recommended, option A |
| 9 | SHQ013 | `certain`, keep warning (high / medium) | as recommended |
| 10 | SHQ011 | warning for `\/`, `[]a]`; mechanism A (medium) | as recommended |
| 11 | SHQ008 derived types | keep error (high) | keep error |
| 12 | OWL023, OWL041, SHQ008, SHQ018, SHQ016 confidence | `certain` for OWL041, SHQ008, SHQ018 only | `certain` for OWL023 too (D1); SHQ016 stays `heuristic` |
| 13 | OWL004, OWL007 confidence | no change (medium) | no change |
| 14 | SKOS001, SKOS002 category | deterministic (high) | deterministic |
| 15 | SHQ003 | keep widened (medium-high) | keep |
| 16 | SHQ001, SHQ002 direct targets | include (low-medium) | include |
| 17 | SKOS001 scope | widen after a count (low) | deferred until the count |
| 18 | Approve the OWL, METRIC, SHQ specifications | after the inconsistencies above are corrected | maintainer; the corrections are in the pull request that precedes this one |
| 19 | METRIC001, METRIC002 severity | keep warning | keep warning |
| 20 | METRIC011 confidence | keep `certain` (calibration page) | `heuristic` (D1) |

## Reproduce

```sh
# corpus A: fetch (checksum-verified), then lint with each profile
uv run python scripts/metric_corpus.py fetch DIR_A
for p in recommended ci obo fair strict minimal; do
  for f in DIR_A/*; do uv run ontolint "$f" --profile "$p" --format json --fail-on never > "OUT/$(basename "$f").$p.json"; done
done
# corpus B: lint each shapes file against a one-triple data file
uv run ontolint placeholder.ttl --shapes FILE --select SHQ001,SHQ002,SHQ003,SHQ007,SHQ008,SHQ011,SHQ013,SHQ015,SHQ016,SHQ017,SHQ018 \
  --format json --fail-on never
```

A scenario's exit code is `max(rank(severity after the change)) >= rank(profile fail-on)` over a file's findings (info 1, warning 2, error 3;
`recommended` and `minimal` 3, `ci`, `obo`, `fair` 2, `strict` 1). Engine checks: pySHACL's `validate` and `apache-jena-4.10.0/bin/shacl validate
--shapes S --data D` on a one-property shape with each `sh:pattern`, `sh:flags` or `sh:minCount` value of the rows above. To measure what a row changes in
the repository, edit the spec's severity (or confidence, or category) in the rule module, run `uv run pytest -n auto --no-cov -W error`, then
`uv run python tests/rule_docs_generator.py`, and discard the edit.

## Limits of this record

* No count exists for real OWL 1 era ontologies (OWL035). Production shapes graphs are counted in [`validation/shq-scope.md`](validation/shq-scope.md): five repositories, which is a sample, not the population.
* The Jena measurements follow from the command above, but no fixture or scheduled job commits them: only pySHACL's behaviour is a test. Reproducing them in CI is a separate issue (with the weekly Jena round-trip check of #165).
* One version of each engine (pySHACL 0.40.2, Jena 4.10.0 on Java 11). Jena 5 needs Java 17 and was not run; TopBraid and the OWL API were not run.
* The per-row file list of an accepted change is the union measured in fact 5, not a per-row split.
