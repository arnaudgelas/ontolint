# TODO — delivery roadmap

This is a prioritised delivery plan, not a catalogue of attractive ideas. Its purpose is to make
ontolint safe to run in CI and trustworthy when it reports a result. The rule catalogue remains
[`docs/rules.md`](docs/rules.md) and `src/ontolint/data/rule_catalogue.csv`; do not duplicate its
individual rule backlog here.

**Hotfix** ships on its own, as soon as it is done, and is blocked by nothing else below. `P0`
blocks the next feature release (0.9.0; 0.8.0 shipped while it was still open). `P1` is the next
milestone after P0. `P2` is worthwhile
only after the preceding work is complete. “Decision gate” means no implementation starts until the
stated decision is accepted. Re-audit external-service assertions (GitHub settings, Action history
and PyPI state) when starting the item; they do not belong in a permanent source-controlled fact
record.

## Recently done

0.6.0, 0.7.0 and 0.8.0 were released on 2026-11-09, each after the maintainer's approval in the
release run (0.8.0: run 42586191689, all jobs green, 0.8.0 on PyPI). Kept only so the
next audit can confirm them, then delete these entries. Leftovers from each are in the open items
below. The 0.4.x and 0.5.x entries were confirmed (all released, release jobs green) and removed;
`CHANGELOG.md` keeps their record.

- Unreleased, on `main` for 0.9.0:
  - borrowed vocabulary terms are not the ontology's own (`deed446`): Dublin Core, SKOS, DCAT, IAO
    and the other `WELL_KNOWN_NAMESPACES` declared for OWL 2 DL no longer draw LEX001, LEX002,
    METRIC003, IRI005 or IRI008. A fixture with the pattern gave 16 findings on 0.8.0 and none
    now; the corpus, twelve well-known vocabularies linted on their own and the CCO closure are
    unchanged;
  - SEM001 groups ROBOT's violations by kind and subject; the full report is the finding's new
    `details` field in JSON and SARIF (`fd65893`);
  - the release `verify` job checks PyPI holds exactly the built files and verifies each one's
    PEP 740 attestation (`07099e5`), tried on the published 0.8.0 files and on tampered copies;
  - specifications for every error-severity rule and the whole OWL family (OWL001-OWL045, the
    SKOS errors, ALIGN003, the SHQ errors, SEC014 and the pipeline rules), in each module's
    docstring with cases for each condition and exclusion and corrected catalogue rows
    (`28a39cf` to `19291b4`). Defects fixed on the way: OWL008, OWL011 (the closure axiom it
    recommends: 20 false positives gone on the corpus, nothing else changed), OWL022, OWL024,
    OWL036 (`-0`), SKOS001 (tag case, `xsd:string`), SKOS002, SKOS008, SKOS009 (transitive),
    SKOS016, SHQ011 (`x` and `q` flags), SHQ018 (a crash and numeric promotion), and in the safe
    loader SEC001 (catalog size), SEC009 (symlinked directories) and SEC013 (C resolvers, UDP).
  - the first `validation.yml` run (42611542815, scheduled, 2026-11-09) failed in both jobs, both
    fixed but not yet proven by a hosted run: the ROBOT container runs as the calling user
    (`634e06f`, `7d2ad74`), as the image's `nonroot` user could not write `profile.txt` into the
    0700 output directory on Linux (SEM001 "Permission denied"; Docker Desktop hides it); and
    `coverage_timeout = 900` for gremlins (`e906c7c`), since the pre-scan exceeded the 120 s
    default, test selection was disabled, and the run hit the two-hour job timeout at mutant 1446
    of 1696.
  - Turtle that starts with an anonymous blank node (`[] a ex:K .`, as RDFLib writes one) is no
    longer sniffed as a JSON-LD array, which failed to parse (`9aebf0b`); found by the round-trip
    property test, whose case is now an explicit `@example`;
  - `--convert-with-robot` (`62e9c2c`) reads OWL Functional, Manchester and OWL/XML files, inputs
    and imports, by converting each to Turtle with the ROBOT image, alone, read-only, offline, with
    its imports stubbed through a generated catalog and the sniffed syntax named (without one, OWL
    API falls back to its OBO parser and accepts almost anything). The automatce edit file and its
    12 imports (10 components, 2 import modules) lint as a closure in 7 s: 109 findings in 8 of the
    13 files, nothing unresolved, and the closure holds every triple of ROBOT's own `merge` (the 61
    extra triples are the modules' headers, which `merge` drops). A Manchester file that relies on
    an import's declarations fails with an `INPUT001` saying so. The Validation workflow runs the
    conversion against the real image. `--owl-profile DL` on the edit file passes too (ROBOT reads
    the `catalog-v001.xml` beside it);
  - `--import-dir` with BFO, verified (2026-11-09): MFTO with BFO `classes-only.owl` (matched by
    its version IRI) and RO `core.owl` in one folder resolves both, 37 findings, none on BFO or RO
    terms; with RO alone, 38, the extra one SEC007 naming BFO.
- 0.8.0 (`7b08ff8`, tag `v0.8.0`), released. From
  linting fifteen public ontologies:
  - ownership judges only an ontology's own terms (`a6eef83`): file extensions and ODK release
    suffixes are stripped from the ontology IRI, the `<dir>/<NAME>_` ID prefix applies beyond OBO,
    and the dominant namespace is used before "own everything". automatce-full: 695 → 114
    findings, none foreign; CCO's closure has no finding on BFO;
  - the import root is the enclosing repository, and each module's own catalog is read (`eb77492`);
    a catalog entry naming a missing file leaves the import unresolved with a TOOL004 note. CCO,
    EMMO and SDC lint with `--follow-imports` without SEC009 or INPUT001;
  - the input syntax is sniffed (`ccebe3f`): Turtle in `.owl` (MODL) lints; OWL Functional,
    Manchester and OWL/XML fail with a clear message; a parse failure says where an embedded
    HTML page starts (ISAAC: line 2194);
  - relative `owl:imports` are one GOV002 note, shown relative to the file and kept out of SEC008
    (`0efba7a`); IDS: 84 → 5 findings, and no local path in the output;
  - `--import-dir DIR` maps imports to local copies by ontology or version IRI, and catalogs match
    version IRIs (`be8ea61`);
  - rule defects (`191c9cd`, `ddbcdf5`, `6ed9131`): METRIC005 external superclasses, IRI001
    `http:` without a host, OWL011/OWL043 named foci, LEX002 knows CCO 1.x definitions and
    subproperties of definition predicates (SDC's `ArtifactOntology.ttl`: 576 → 21 findings) and
    TOOL005 suggests unknown ones, header metadata via `owl:ontologyIRI` (MOD), the SPDX licence
    hint (Tractus-X), RDFLib's stderr silenced;
  - new rules (`7395d9f`): DATA003 ill-typed literals and `rdfs:Literal`-typed values, DATA004
    datatypes outside the OWL 2 map (`xsd:anyType`, `xsd:date`), IRI018 Protégé placeholder IRIs,
    IRI019 declared prefixes no IRI uses. Catalogue: 299 rows, 244 implemented.
- 0.7.0 (`872e79c`, `283dc4e`, `9e4c28f`, `8c15b1d`), released: modular stages
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

## P0 — before 0.9.0

- [ ] **Turn Renovate on, and watch its first rebase.** The release boundary is in place and proven
  (2026-11-09): the 0.6.0 and 0.7.0 release runs waited at "Publish to PyPI" for the maintainer's
  approval, and on a throwaway tag (`ruleset-probe-2026-11-09`, kept as a record; no `v` prefix, so
  it starts no release) GitHub refused both a force-move ("Cannot update this protected ref") and a
  deletion ("Cannot delete this tag"). The `main` ruleset targets the default branch only, so
  Renovate's own branches are not restricted, and its automerge now squashes
  (`"automergeStrategy": "squash"` in `.github/renovate.json`), which the linear-history rule
  accepts. What is left: Renovate has never run here (no branch, pull request or Dependency
  Dashboard issue), so the Renovate GitHub app is probably not installed. The maintainer enabled
  the app on 2026-11-09; two hours later there was still no branch, pull request or dashboard
  issue, so check that the installation includes this repository ("Only select repositories")
  and that it is enabled in the Mend developer portal. Rechecked later on 2026-11-09: still only
  `main`, no pull request and no dashboard issue; a token without app scope cannot list the
  installations, so this check is the maintainer's. Then watch one
  rebase of a Renovate branch and one automerge. The `tags` ruleset's "linear history" rule means
  nothing for tags and can go. *Done when:* both are observed once.

## Real-world ontologies — left open by 0.8.0

Everything here comes from linting fifteen public ontologies on 2026-11-09 (sources in the corpus
table at the end of this section). Each item names the files that show it; every fix gets a small
synthetic fixture copying the pattern, and the real repositories are only used for validation runs.
What is done is under "Recently done"; what is left is optional or waits on a decision.

- [ ] **ONT005 says which provenance is missing, at the next legacy-contract break.** Its message
  ("Missing creator or dcterms:created provenance.") is one of the 63 legacy rules whose findings
  `test_legacy_rules_unchanged_linter` keeps byte-identical, because baseline fingerprints include
  the message. Change it ("Missing a creator and dcterms:created provenance.", or only the missing
  one) together with any other legacy message change, with an upgrade note.

- Decided, recorded here so the next audit does not reopen them:
  - IRI016 on an ontology IRI ending in `#` (MODL) is not a defect: the rule's cases deliberately
    accept the empty fragment, and hash-terminated ontology IRIs are common.
  - LEX002 keeps judging individuals. The legacy golden asserts it (`populated`: two individuals),
    so changing the default would break the legacy contract. ROBOT's `missing_definition` checks
    only classes and properties, which is the precedent to cite if the default changes at 1.0; until
    then, CCO-style unit individuals can be baselined.
  - A literal typed `rdfs:Literal` is ill-typed in OWL 2 DL: the Structural Specification
    (Sections 4 and 5.7) gives `rdfs:Literal` no lexical space while requiring every literal's
    lexical form to be in its datatype's. Reported by DATA003.

- [ ] **Modules without imports: group findings by annotation or namespace, optional.** Two
  layouts keep modules inside one file. MOMo marks them by annotation (the food-traceability schema
  uses `opla:isNativeTo "Container"` on 37 of 78 terms; MODL's pattern files use
  `opla-core:isNativeTo`). Merged releases keep one namespace per source module (Tractus-X
  `ontology.ttl` merges eight domain ontologies, `…/ontology/behaviour#`, `…/bill-of-material#`,
  …). An option such as `--module-annotation opla:isNativeTo` or `--module-by namespace` could group
  findings by module, reusing the stage 2 provenance (`In: module Container`), and present
  cross-module collisions (Tractus-X: 13 IRI003 local-name and 6 LEX004 label collisions between
  domains) as such. Only if someone asks.

- [ ] **Profiles and pattern libraries, decide whether they are in scope.** Two more multi-file
  shapes, both linked by metadata rather than `owl:imports`: a W3C PROF profile names its SHACL
  validator (MOD's `profile.ttl`: `prof:hasArtifact …/dcat-profile/validator` with
  `prof:hasRole role:validator`), so `--shapes` could be discovered from it; and a pattern library
  indexes its pattern ontologies (MODL's `modl.owl` describes 31 patterns as individuals under
  `…/purl/purl/…#`, while the pattern files declare `…/purl/domain/…` ontology IRIs, so the index
  cannot refer to them by IRI, a consistency check could say so). Decide before building either.

Validation corpus (public; licences per repository):

| Source | Layout | Shows |
| --- | --- | --- |
| CommonCoreOntology/CommonCoreOntologies | umbrella, 11 modules, BFO, two catalogs with `../` | import root; ownership in a closure |
| emmo-repo/EMMO | a catalog per directory, versioned module IRIs | per-directory catalogs |
| materialdigital/automatce | ODK: `-full`, `-base` and main releases; `src/ontology` edit file, components, imports, catalog | ownership of release artifacts; Functional Syntax |
| International-Data-Spaces-Association/InformationModel | header file importing 86 files by relative IRI | relative imports, SEC008 paths |
| neilotte/moralpsych (MFTO, rights ontology) | PURL imports without catalog; placeholder IRI; `http:` without `//` | `--import-dir`; rule defects |
| emmo-repo/domain-mappings | one import of a published build | `--import-dir` |
| StenDoipanni/ISAAC | headerless FRED knowledge graph with embedded HTML errors | ownership; parse diagnostics |
| Data-Semantics-Laboratory/Modular-Ontology-Modeling-for-Food-Supply-Chains | MOMo modules by OPLa annotation | module annotations |
| kastle-lab/modular-ontology-design-library (MODL) | pattern library: index plus 31 pattern ontologies, Turtle in `.owl` | syntax sniffing; trailing `#` IRI; library consistency |
| eclipse-tractusx/sldt-ontology-model | merged release of eight domain ontologies, one namespace each | modules by namespace; `xsd:anyType`; SPDX licence |
| FAIR-IMPACT/MOD | metadata vocabulary, PROF profile, SHACL validator | metadata one hop away; ill-typed literals; profile-discovered shapes |
| hbabaie1/Sustainable-Development-and-Climate-SDC-ontology | OWL/XML ontology on a vendored CCO 1.x copy, one flat catalog with stale entries | OWL/XML; stale catalog; definition predicates |
| KnowledgeCaptureAndDiscovery/SoftwareDescriptionOntology | single curated file, versioned `release/1.9.0/` | control case: 8 findings, ownership right |

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
  Done for 0.9.0 (unreleased): every error-severity rule and the whole OWL family (see "Recently
  done"); the specifications await the maintainer's approval. Next: the METRIC family. Left open
  by that review:
  - *Severity and confidence, the maintainer's decision* (changing either moves baselines and
    `--fail-on` results): OWL009 warning → error, and OWL010 info → warning or error (both
    describe graphs outside OWL 2 DL); OWL013/OWL014 → error; OWL032 info → warning; OWL045's
    missing or malformed list → error like OWL031; OWL038 error or warning; confidence `certain`
    for OWL023, OWL041, SHQ008 and SHQ018 (exact checks still on the default `heuristic`, which
    changes `differential.json`); OWL004/OWL007 `heuristic`; category `deterministic` for SKOS001
    and SKOS002; SKOS001 on any owned resource with a `skos:prefLabel`, not only concepts (S14).
  - *Defects that change an exit code, a focus or a message:* an unwritable `--output` raises a
    traceback and exits 1 instead of TOOL001 and exit 2 (`cli.py` `main`, README "Exit codes");
    SEM001 reports a failed image pull or a ROBOT crash as a profile violation (exit 1,
    baselinable) instead of a failed rule (exit 2); SEM001's focus is the absolute file path, so
    its fingerprint depends on the machine; SEC014's focus repeats the password it reports (RFC
    3986 §3.2.1 says not to show it); OWL013 (legacy), OWL034, OWL036 and OWL040 print Python
    reprs (`rdflib.term.Literal(...)`) instead of N3.
  - *Policy that silently does nothing:* `--ignore`, `--select` and `severity_overrides` accept the
    pipeline rules (SEC001-SEC015, INPUT001, TOOL001) and have no effect; reject them or say so.
    A file in an `--import-dir` that the safe loader refuses is skipped without a note.
  - *Coverage gaps, now stated as exclusions with negative cases* (each needs a new message):
    OWL010 empty or malformed chain; OWL019 non-simplicity through sub-properties, inverses and
    equivalents (needs a closure; no rule checks non-simple properties in cardinalities,
    `owl:hasSelf` or disjointness); OWL032/OWL033 on `owl:disjointUnionOf`; OWL034 with both
    `owl:onProperty` and `owl:onProperties`; OWL035/OWL036 with several constraints, `hasSelf`
    other than true, or both `onClass` and `onDataRange`; OWL037 unqualified max 0 against a
    qualified min; OWL040 `rdf:langString` and `owl:real`; SHQ008 derived integer datatypes
    (SHACL requires `xsd:integer`); SHQ011 invalid flag letters and XSD-invalid patterns Python
    accepts; no rule for a non-integer `sh:minLength`/`sh:maxLength`; ALIGN003 `relatedMatch` in
    an exactMatch chain (S46); `skos:related` plus `skos:broadMatch` on one pair (S27 via S41).
  - *Documentation:* `docs/rules.md` shows only each rule's first positive and negative case, so
    the new cases and the specifications are visible only in the source. Render the module
    specifications (or all cases) in the generator.

- [ ] **Close the remaining legal and provenance gaps.** Done in 0.5.0: `SECURITY.md` points
  reporters at GitHub private vulnerability reporting and states the supported versions. Checked:
  every PyPI release (0.1.0 to 0.6.0) already carries a PEP 740 attestation naming this repository
  and `release.yml`, because Trusted Publishing creates one. Still open:
  - the copyright holder for the Apache-2.0 notice (`pyproject.toml` names the author; `LICENSE`
    names nobody, and there is no `NOTICE` file). The maintainer's decision, not code;
  - the crosswalk question is answered (2026-11-09, `data/README.md`): neither catalogue states a
    licence for its text (OOPS!'s software is Apache-2.0, OntoInk's code MIT); the crosswalks
    reuse only identifiers and, for OntoSniff, one-to-three-word smell names; the OOPS! titles are
    ontolint's own paraphrases, and no description is copied. `data/README.md` now gives the sources,
    what is reused and the citations each project asks for. Also checked then: tests hold
    third-party IRIs only, no copied definitions; no dependency is copyleft beyond file-level
    MPL-2.0 (certifi, pathspec, hypothesis); the ROBOT jar is downloaded at image build with a
    pinned checksum, never committed. `logo.png` was added by the maintainer (`84045cc`); its
    origin is not recorded;
  - verifying the attestation in the release `verify` job: done for 0.9.0 (`07099e5`);
    it is proven by the next release run.
  *Done when:* the copyright-holder question has a written answer in the repository, and a release run
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
  whether it belongs in it. There are 20 `gremlin: pardon` markers for a reviewer to audit. The
  first hosted run (42611542815) timed out before writing a report; its causes are fixed (see
  "Recently done"), so push them and run the validation workflow manually again, then have a
  reviewer other than the change author audit
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
  - *Validation on a public corpus:* started on 2026-11-09, see "Real-world ontologies — left open by 0.8.0":
    CCO, EMMO and automatce are blocked by the import root, ownership and Functional Syntax items
    there; the closure itself loaded correctly once the root was widened.
  - *Memory:* each module's source index keeps its graph alive, so a closure holds its triples
    twice. Bounded by `max_triples`, but measure a large closure and drop the per-module graphs if
    it matters.
  - *A per-module header policy:* modules inherit the root's metadata; a project that wants each
    module to carry its own license or version has to lint the modules one by one. Add a policy key
    only if someone asks.
  - *CQ (competency questions):* the decision gate above can now build on the closure.
  *Done when:* CCO, EMMO and the automatce source lint as closures with no finding their
  maintainers would call a false positive, and the memory measurement is either fine or fixed.

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
  `validation.yml` first ran on 2026-11-09 and failed; its rerun is covered by the
  mutation-baseline item.
- **"Which rule group next?":** the question is moot. All 55 proposed rules are blocked by a missing
  backend or input contract (COMP 16, CQ 13, FAIR 13, SEM 7, ALIGN 4, GOV 1, IRI 1), so none can be
  implemented without one of the decision gates above being accepted first. (An earlier version of
  this file claimed the gates covered all of them; ALIGN had no gate until it was added.)
- **Packaged catalogue must equal the source copy:** already enforced by
  `tests/test_registry.py` (byte comparison), which runs in CI and in the release `test` job.
  A separate required check would only duplicate it.

