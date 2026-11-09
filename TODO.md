# TODO — delivery roadmap

This is a prioritised delivery plan, not a catalogue of attractive ideas. Its purpose is to make
ontolint safe to run in CI and trustworthy when it reports a result. The rule catalogue remains
[`docs/rules.md`](docs/rules.md) and `src/ontolint/data/rule_catalogue.csv`; do not duplicate its
individual rule backlog here.

**Hotfix** ships on its own, as soon as it is done, and is blocked by nothing else below. `P0`
blocks the next feature release (0.8.0). `P1` is the next milestone after P0. `P2` is worthwhile
only after the preceding work is complete. “Decision gate” means no implementation starts until the
stated decision is accepted. Re-audit external-service assertions (GitHub settings, Action history
and PyPI state) when starting the item; they do not belong in a permanent source-controlled fact
record.

## Recently done

0.6.0 was released on 2026-11-09, the first release that waited for the maintainer's approval;
0.7.0 was tagged the same day and its release run is waiting for that approval. Kept only so the
next audit can confirm them, then delete these entries. Leftovers from each are in the open items
below. The 0.4.x and 0.5.x entries were confirmed (all released, release jobs green) and removed;
`CHANGELOG.md` keeps their record.

- 0.7.0 (`872e79c`, `283dc4e`, `9e4c28f`, `8c15b1d`), awaiting release approval: modular stages
  2-4. Closure findings name the declaring module (JSON `path`, SARIF artifact and region,
  text `In:`); header rules judge the root ontology only and ownership derives from its IRI;
  METRIC011 ignores local modules; a shapes file that imports the ontology supplies it as SHACL-only
  background. On a real fixture suite every declared outcome matches (13 of 13, 11 of 11 planted
  violations; valid and warnings-only fixtures pass).
- 0.6.0 (`0e5a2aa`, `a4e08f9`): modular stage 1, released.
  `--follow-imports` and `--catalog` load the `owl:imports` closure from local files (catalog `uri`,
  `group` with `xml:base`, `rewriteURI`, `file:` IRIs), never the network; sandboxed (SEC009),
  bounded by `max_import_depth`, `max_imported_files` and `max_triples` (new SEC015); SEC007 lists
  only unresolved imports and ONT002 ignores imported headers. Synthetic corpus in
  `tests/fixtures/modular/`; on a real 12-module ontology the closure equals a direct catalog merge
  and ROBOT's merge up to OWL API normalisation; targeted mutation run kills every mutant.

## P0 — before 0.8.0

- [ ] **Prove the last two parts of the release boundary.** Set up by the maintainer on 2026-11-08:
  the `pypi` environment accepts `v*.*.*` tags only and requires the maintainer's review; the
  `tags` ruleset (all tags) blocks deletion, update and force-push; the `main` ruleset (default
  branch only) blocks deletion and force-push and requires linear history. Proven: the 0.6.0
  release run paused at "Publish to PyPI" until the maintainer approved it. Still unproven, and
  best done deliberately by the maintainer: that a force-push of a `v*` tag is rejected (try it on
  a throwaway tag, not a release), and that Renovate can still rebase its own branches. The
  `tags` ruleset's "linear history" rule means nothing for tags and can go.
  *Done when:* both are observed once.

## P1 — reporting, policy and supply-chain correctness

- [ ] **Source regions: confirm one real-world JSON-LD layout.** Everything else in this item is
  done (0.5.0 and 0.5.2): property tests check that every region spells its node in all four
  formats and that JSON-LD layout (whitespace, decoy duplicate keys) never changes the findings.
  Still unverified: that Java's Jackson pretty-printer writes `"key" : value`. Confirm it with a
  Jena or jsonld-java export and keep that file as a fixture. Needs a Java JSON-LD tool, which the
  development machine does not have.

- [ ] **Calibrate metric thresholds before treating them as universal policy.** Existing `METRIC*`
  ratio defaults are first estimates, even where configuration already exists. Assemble a small,
  licensed corpus of ontologies with known-good and known-poor outcomes; measure false positives and
  false negatives before changing defaults or exposing additional knobs.
  *Done when:* every metric threshold records its rationale, corpus results, and override behavior;
  any changed default has regression fixtures demonstrating the intended boundary.

- [ ] **Audit the specifications of implemented rules, not only proposed rules.** A rule can be
  implemented, tested, and still be semantically under-specified if it began as a catalogue title;
  roughly 120 of the 239 implemented rules (tranche 1, OWL, METRIC and the leftovers) were
  specified from placeholder titles and never reviewed. The goal as written covers all 239 and will
  not finish: take one family per milestone, starting with error-severity rules and the OWL and
  METRIC families. Done in 0.5.2 for the three rules known to have drifted (IRI015, LEX018 and
  LEX021): their module states each condition, and their catalogue test requirements no longer
  describe the original plans. Specify
  scope, formal condition, exclusions, confidence/severity rationale, and positive and negative
  fixtures; correct documentation or implementation when they disagree.
  *Done when:* each implemented rule has an approved, testable specification and its catalogue,
  user documentation, and fixtures state the same contract.

- [ ] **Close the remaining legal and provenance gaps.** Done in 0.5.0: `SECURITY.md` points
  reporters at GitHub private vulnerability reporting and states the supported versions. Checked:
  every PyPI release (0.1.0 to 0.6.0) already carries a PEP 740 attestation naming this repository
  and `release.yml`, because Trusted Publishing creates one. Still open:
  - the copyright holder for the Apache-2.0 notice (`pyproject.toml` names the author; `LICENSE`
    names nobody) and the licence and attribution terms of the OOPS! and OntoSniff catalogues that
    `data/*_crosswalk.csv` reference. Both are the maintainer's decisions, not code;
  - verifying the attestation in the release `verify` job, for example with `pypi-attestations
    verify pypi`. Not added yet, because it could not be tried locally first.
  *Done when:* both legal questions have a written answer in the repository, and a release run
  fails if the published files' attestations do not verify.

- [ ] **Approve a current mutation baseline before making it blocking.** Existing mutation-policy
  thresholds and pardon-review rules are useful only if a clean GitHub run establishes that the
  current suite meets them. The last *full* triage predates 0.4.0. Every in-scope module changed
  since then had a targeted run for 0.5.2 (`cli.py`, `reporting.py`, `source_locations.py`,
  `adapters/shacl.py` and the `owl`, `owl_expressions`, `hierarchy_quality`, `metrics` and
  `class_heuristics` rules): 596 mutants, 97% killed on the first pass, the survivors then killed by
  new tests; and the modules changed for 0.6.0 and 0.7.0 (`imports.py`, `engine.py`, `cli.py`,
  `reporting.py`, `rules/metrics.py`, `rules/metadata.py`) had their own targeted runs, all
  survivors killed. `context.py`, changed in 0.5.1 and 0.7.0, is outside the mutation scope; decide
  whether it belongs in it. There are 20 `gremlin: pardon` markers for a reviewer to audit. Run the
  scheduled validation workflow manually first, have a reviewer other than the change author audit
  every active pardon, then change the repository variable. *Done when:* a current hosted run meets
  all thresholds, reviewer approval is recorded for every pardon, and `MUTATION_GATE_MODE=blocking`
  has survived at least one scheduled run.

## P2 — platform reliability and useful integration

- [ ] **Run a deliberately small cross-platform smoke suite on Windows and macOS.** A Win32 mypy
  pass does not exercise multiprocessing, path handling, file permissions, or CLI encoding. Do not
  multiply the full expensive matrix until a smoke suite gives it value.
  *Done when:* pull requests run parsing, timeout-worker, CLI, and packaging smoke tests on Linux,
  Windows, and macOS; platform-specific tests are explicitly marked rather than silently skipped.

- [ ] **Schedule the tests deliberately excluded from the fast suite.** Fuzz targets and benchmarks
  are guarded by environment switches; they are not evidence if never run. Add a scheduled/manual
  workflow with sensible time budgets and retained artifacts. Keep performance assertions stable
  enough for hosted runners; assert scaling ratios, as `tests/test_scaling.py` does since 0.5.0,
  not absolute seconds. The benchmarks sat skipped while two quadratics shipped.
  *Done when:* the slow/fuzz/benchmark suites have named cadence, timeout, owner, and failure
  policy; every remaining skip is either platform-impossible or linked to that scheduled work.

- [ ] **Decide the GitHub integration before implementing `--format github`.** GitHub workflow
  annotations are capped, whereas SARIF upload offers richer code-scanning UX. Write a short ADR
  comparing a native annotation formatter, documented SARIF upload, and both; choose one supported
  path and its authentication/upload responsibility.
  *Done when:* the ADR is accepted and, if a formatter is chosen, end-to-end escaping and annotation
  limit tests exist.

- [ ] **OPS006, OPS001, OPS011 and OPS018: version reports before enriching them.** Catalogue
  identity, per-rule counts, optional timing and a fuller explanation of exit code 2 (today the
  failed and unsupported rules are listed, but not why the run as a whole exited 2) are useful only
  with a clear compatibility contract. Publish
  a versioned JSON/SARIF extension policy first; timing must be opt-in and must not perturb default
  deterministic output.
  *Done when:* report consumers can identify the catalogue and schema version, obtain deterministic
  per-rule counts, and request timing without changing default output.

## Decision gates — choose one product bet; do not start all of them

The following are different products with incompatible input contracts and operational costs. An ADR
must choose one next capability based on target users and a real fixture corpus. No rule family
moves from `proposed` merely because it has an attractive title.

- [ ] **Version comparison (`COMP*`).** Define a two-input CLI, graph identity/version semantics,
  blank-node treatment, and compatibility policy. *Gate:* accepted ADR plus a representative pair
  corpus and a memory/time budget.
- [ ] **Competency questions (`CQ*`).** Define query packaging, expected bindings/ASK semantics,
  deterministic result serialisation, and query execution limits. A format already used in
  practice, and a good first candidate: one SPARQL `SELECT ?answer` per `.rq` file, the question in
  a `# CQ:` comment and the expected set of answers in an `# expect: a | b` comment, evaluated
  against the import closure (`--follow-imports`, available since 0.6.0) and compared as
  sets. *Gate:* accepted format and at least one public corpus that justifies maintaining it.
- [ ] **Reasoner-backed semantics (`SEM*`).** Define supported reasoners/profiles, Docker versus
  local dependency model, reproducibility, timeout/failure behavior, and CI image ownership.
  *Gate:* accepted adapter contract and deterministic container fixtures.
- [ ] **Policy packs and domain profiles.** The `obo` and `fair` opt-in families and profiles
  already exist, so this gate covers only what they do not: externally authored, versioned packs.
  Define profile ownership, rule-selection/override
  precedence, versioning, and how a pack is validated without weakening the core policy model.
  *Gate:* accepted pack format and two independently useful example profiles.
- [ ] **Mapping and alignment (`ALIGN*`, 4 rules).** They need a mapping registry (SSSOM files or
  similar) as a second input. *Gate:* accepted input format; can share the two-input CLI design
  with `COMP*`, so decide them together.
- [ ] **Network-dependent FAIR/IRI/GOV checks (`FAIR*`, `IRI007`, `GOV018`).** This conflicts with
  the present offline-first threat model. *Gate:* either a decision to reject it permanently, or an
  accepted opt-in isolated resolver design with allowlists, cache/privacy policy, and deterministic
  mocked tests. There is no default-network implementation.
- [ ] **Modular ontologies: finish what stages 1-4 left open.** Stages 1-4 are built (see "Recently
  done"): offline resolution, per-module provenance, closure semantics and SHACL with the ontology
  as background. Left:
  - *Validation on a public corpus:* one ODK-based OBO repository (catalog plus `imports/` modules)
    linted with `--follow-imports`, with no finding its maintainers' CI would call a false positive.
    So far checked on one private 12-module ontology and the synthetic corpus only.
  - *Memory:* each module's source index keeps its graph alive, so a closure holds its triples
    twice. Bounded by `max_triples`, but measure a large closure and drop the per-module graphs if
    it matters.
  - *A per-module header policy:* modules inherit the root's metadata; a project that wants each
    module to carry its own license or version has to lint the modules one by one. Add a policy key
    only if someone asks.
  - *CQ (competency questions):* the decision gate above can now build on the closure.
  *Done when:* the public-corpus check is recorded and the memory measurement is either fine or
  fixed.

## Explicitly deferred

- **Result caching (OPS017):** do not add indexes or cache invalidation until profiling shows a
  repeated-CI workload where parsing/linting dominates and a cache key/invalidation strategy is
  demonstrably safe.
- **Changed-lines filtering and inline suppressions (OPS014–OPS016):** defer until baseline hygiene
  is complete and a source-region accuracy contract is stable; otherwise they hide findings using
  unreliable location data.
- **More report formats (OPS012):** do not create JUnit/Markdown/HTML outputs without an identified
  consumer. JSON and SARIF are the integration contracts to keep sound first.
- **Bulk implementation of proposed rules:** each needs an approved specification, positive and
  negative fixtures, expected confidence/severity, and an identified backend. A count of proposed
  rules is not a delivery plan.

## Documentation debt to close with the affected work

- [ ] Correct stale source comments: `src/ontolint/github.py` says findings "carry no source
  locations" (false since 0.3.0) and the module has no caller outside its own test until a
  formatter exists. Either make it earn its place via the GitHub-integration ADR or delete it.
- [ ] Keep README, release instructions, policy schema, and report examples in the same change as
  any CLI/report-contract modification. Documentation-only corrections do not need a feature
  release, but behavior changes do.

## Questions retired from remaining-work.md

Each was an open question in the old local backlog and no longer is. Listed so they are not asked
again.

- **Exit code 2 with `--fail-on never`:** decided and documented in the README exit-code table.
- **License choice:** Apache-2.0. Only the copyright-holder attribution and the OOPS!/OntoSniff
  crosswalk terms remain, and both are in the legal item under P1.
- **Source locations / "custom parser or second pass":** decided and shipped (second pass over the
  source text). Its crash was fixed in 0.4.1, its wrong regions and quadratic cost in 0.5.0; what
  remains is the source-region item under P1.
- **CodeQL failure on `6e8ec3e` (HTTP 504 fetching the bundle):** transient; CodeQL is green on
  later commits. The AI security scan on the same commit failed the same way. It is GitHub-managed
  and, as of 2026-11-08, has run on no commit since, so releases gate on CodeQL only (the
  `codeql` job in `release.yml`), never on the AI scan.
- **Pull request / remote / first GitHub run:** a remote exists and CI and release have run; only
  the never-run `validation.yml` workflow remains, and it is covered by the mutation-baseline item.
- **"Which rule group next?":** the question is moot. All 55 proposed rules are blocked by a missing
  backend or input contract (COMP 16, CQ 13, FAIR 13, SEM 7, ALIGN 4, GOV 1, IRI 1), so none can be
  implemented without one of the decision gates above being accepted first. (An earlier version of
  this file claimed the gates covered all of them; ALIGN had no gate until it was added.)
- **Packaged catalogue must equal the source copy:** already enforced by
  `tests/test_registry.py` (byte comparison), which runs in CI and in the release `test` job.
  A separate required check would only duplicate it.

