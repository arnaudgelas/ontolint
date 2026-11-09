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

0.6.0 and 0.7.0 were released on 2026-11-09, both after the maintainer's approval in the release
run. Kept only so the
next audit can confirm them, then delete these entries. Leftovers from each are in the open items
below. The 0.4.x and 0.5.x entries were confirmed (all released, release jobs green) and removed;
`CHANGELOG.md` keeps their record.

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

## P0 — before 0.8.0

- [ ] **Turn Renovate on, and watch its first rebase.** The release boundary is in place and proven
  (2026-11-09): the 0.6.0 and 0.7.0 release runs waited at "Publish to PyPI" for the maintainer's
  approval, and on a throwaway tag (`ruleset-probe-2026-11-09`, kept as a record; no `v` prefix, so
  it starts no release) GitHub refused both a force-move ("Cannot update this protected ref") and a
  deletion ("Cannot delete this tag"). The `main` ruleset targets the default branch only, so
  Renovate's own branches are not restricted, and its automerge now squashes
  (`"automergeStrategy": "squash"` in `.github/renovate.json`), which the linear-history rule
  accepts. What is left: Renovate has never run here (no branch, pull request or Dependency
  Dashboard issue), so the Renovate GitHub app is probably not installed. Install it, then watch one
  rebase of a Renovate branch and one automerge. The `tags` ruleset's "linear history" rule means
  nothing for tags and can go. *Done when:* both are observed once.

## 0.8.0 — real-world ontologies

Everything here comes from linting fifteen public ontologies on 2026-11-09 (sources in the corpus
table at the end of this section). Each item names the files that show it; every fix gets a small
synthetic fixture copying the pattern, and the real repositories are only used for validation runs.

- [ ] **Ownership: stop judging vocabularies an ontology only references or merges in.** When the
  ontology IRI owns none of the declared terms, ownership falls back to "every IRI is owned", so
  imported, merged or merely referenced terms are linted as the ontology's own. Measured:
  automatce `automatce.ttl` and `-full` (ODK releases): about 430 of 695 findings are on merged
  PMDco, OBO, DC and SKOS terms, and even `-base` has 142 of 294; CCO linted as a closure: 70
  findings on imported BFO; MFTO: 5 false OWL001 warnings ("declare local classes") on BFO classes;
  ISAAC: 3,778 OWL001 findings, including DUL, schema.org and DBpedia IRIs; SDC's vendored CCO 1.x
  modules: OWL001 on BFO classes. Three changes, in
  `ownership.derive_prefixes` and `Ownership.for_terms`:
  - strip `.ttl`, `.rdf`, `.json`, `.jsonld`, `.ofn` and `.omn` as well as `.owl` from the
    ontology IRI (fixes `https://w3id.org/pmd/automatce.ttl`);
  - generalise the OBO `<dir>/<NAME>_` ID-prefix rule beyond `purl.obolibrary.org`, after removing
    the ODK release suffixes `-full`, `-base`, `-simple`, `-merged`, `-non-classified` (fixes
    `…/automatce/automatce-full.ttl` owning `AUTOMATCE_…`);
  - when derived ownership finds nothing, use the dominant namespace of the declared terms before
    "own everything" (MFTO: 20 of 20 terms; CCO: over 1,900 of about 2,000; ISAAC: FRED's
    `domain.owl#`).
  Default output changes for such files, so it is a minor release. *Done when:* fixtures for each
  pattern own exactly the project's terms, the goldens are reviewed, and re-running the four files
  above leaves no finding on a foreign namespace.

- [ ] **Import root: allow the standard Protégé layout.** CCO's catalogs point at sibling
  directories (`src/cco-merged/catalog-v001.xml` maps to `../cco-modules/*.ttl` and
  `../cco-imports/bfo-core.ttl`), and today both the umbrella and a single module stop with `SEC009
  … outside the import root`. With a wider root (simulated) the closure loads: 12 files, 14,014
  triples, 0.2 s, nothing unresolved. Add `--import-root DIR`, defaulting to the enclosing
  repository (nearest ancestor with `.git`) and otherwise to the catalog's directory; SEC009 still
  refuses anything outside it. Also read the catalog next to each loaded module, as Protégé does:
  EMMO keeps a `catalog-v001.xml` in each directory (`disciplines/`, `disciplines/units/`,
  `foundation/`, `perspectives/`, `reference/`). A catalog entry naming a file that does not exist
  should leave that import unresolved, with a note, instead of failing the run: SDC's catalog still
  maps CCO and BFO to `cco-merged/…` and `imports/ro-import.ttl`, which the repository no longer
  has, and `--follow-imports` stops with `INPUT001: FileNotFoundError`. *Done when:* CCO's umbrella
  and modules, EMMO and SDC lint with `--follow-imports` without a SEC009 or INPUT001, and a
  catalog entry escaping the repository is still refused.

- [ ] **Sniff the syntax instead of trusting the file extension.** The extension decides the
  parser, so a mismatch fails with an unhelpful `INPUT001: … SAXParseException`: MODL's `modl.owl`
  and its 31 pattern files are Turtle under `.owl` (renamed to `.ttl`, `modl.owl` lints fine). Sniff
  Turtle, N-Triples, RDF/XML and JSON-LD from the first bytes when the extension's parser fails,
  and say which syntax was found. *Done when:* a Turtle-in-`.owl` fixture lints, and a file that is
  no RDF syntax still fails with INPUT001.

- [ ] **Recognise OWL Functional, Manchester and OWL/XML syntax instead of failing obscurely.**
  OWL/XML too: SDC's `SDC_v1.owl` starts `<Ontology xmlns="http://www.w3.org/2002/07/owl#"`, and
  the RDF/XML parser reports `Repeat node-elements inside property elements`. ODK edit
  files are usually Functional Syntax with a `.owl` extension (automatce's `src/ontology/
  automatce-edit.owl` starts with `Prefix(` and `Import(<…/components/…>)`). ontolint picks the
  parser from the extension and reports `INPUT001: … SAXParseException: not well-formed (invalid
  token)`; RDFLib cannot read either syntax. Sniff the content, and for these syntaxes fail with a
  clear message (convert with `robot convert`, or lint the `-base.ttl` release). Optionally convert
  offline through the project's ROBOT Docker image, already used by `--owl-profile`. *Done when:*
  a Functional and a Manchester fixture get the clear message, and, if conversion is added, the
  automatce edit file and its 10 components lint as a closure.

- [ ] **Relative `owl:imports` (IDS Information Model).** `Ontology.ttl` imports its 86 class files
  as `<model/…/X.ttl>`. With `--follow-imports` they resolve, but in both modes they also give 80
  SEC008 "unsafe scheme `file:`" findings whose text holds the reader's local path, so output
  differs per checkout and baselines break across machines. Report relative imports once, as a note
  that they depend on where the file is read, show them relative to the file, and keep them out of
  SEC008. Six of the imports are listed twice; say so. *Done when:* a relative-import fixture gives
  identical output from two different directories.

- [ ] **Imports of a published build, without a catalog.** MFTO imports BFO and RO by PURL and EMMO
  domain-mappings imports one EMMO build by URL; neither ships a catalog, and ontolint stays
  offline. Add `--import-dir DIR`: map imports to the files in a folder by the `owl:Ontology` or
  `owl:versionIRI` they declare. Match imports on version IRIs in catalogs too (common in OBO; CCO
  and automatce declare them). When SEC007 lists imports and no catalog was found, say so and point
  at `robot mirror` or a one-off download plus a catalog. *Done when:* MFTO with a folder holding
  BFO and RO resolves its two imports.

- [ ] **Rule defects found on these files.** Each is a bug fix, so it can also ship in a patch:
  - METRIC005 counts a class whose only superclass is external (MFTO: 14 of 18 classes under BFO)
    as an orphan, because its hierarchy keeps local classes only; CLS001 gets it right.
  - IRI001 misses `http:` IRIs with no `//` authority (the rights ontology's
    `http:semanticweb.org/hohfeldiansystem/` and all its terms).
  - ONT005's message ("Missing creator or dcterms:created") does not say which is missing (the
    rights ontology has a creator).
  - Findings on anonymous class expressions name only a blank node: OWL011 (`_:4c37b6c9b56d`,
    food traceability, 36 times) and OWL043 (`_:0c8c85ae1747`, the Software Description Ontology's
    `rdfs:range [ owl:unionOf ( … ) ]`). Name the property and the class that own the expression.
  - LEX002 does not know widely used definition predicates: CCO 1.x defines all 567 classes of
    `ArtifactOntology.ttl` with `…/CommonCoreOntologies/definition`, so SDC's vendored CCO gets
    over 2,000 false "no definition" findings; adding the predicate to
    `extra_definition_predicates` takes `ArtifactOntology.ttl` from 576 findings to 100.
    Recognise the common ones (IAO_0000115, CCO 1.x `definition`), or note once when one
    undeclared predicate whose name contains "definition" sits on most terms, and suggest the key.
  - A parse failure inside HTML (ISAAC: 37 HTTP 500 error pages saved into the Turtle) could say
    "an HTML page starts at line 2194"; and RDFLib's own warnings and a full traceback leak onto
    stderr during parsing (ISAAC, and MOD's ill-typed dates), and should be captured.
  - IRI016 misses an ontology IRI ending in `#` (MODL: `…/modular_ontology_design_library#`):
    Python's URL splitter reports an empty fragment, so the rule sees none.
  - Header rules miss metadata described one hop away: MOD puts all of its metadata on
    `<https://w3id.org/mod#>`, which names the ontology `<https://w3id.org/mod>` through
    `owl:ontologyIRI`, so ONT003-ONT006 and GOV004 report a bare header. Follow `owl:ontologyIRI`
    back to the describing node, or at least say where the metadata is.
  - ONT003 could mention a licence that appears only as an `SPDX-License-Identifier` comment
    (Tractus-X `ontology.ttl`: CC-BY-4.0 in the file header, no `dcterms:license`).

- [ ] **New checks suggested by these files.** Each needs a rule ID, so they ship in a minor
  release:
  - a placeholder ontology IRI (Protégé's `…/untitled-ontology-139`, MFTO);
  - prefixes declared for a vocabulary that is neither used nor imported (the rights ontology
    declares CCO's `AllCoreOntology:` and `ROImport:`);
  - literals typed `rdfs:Literal` (food traceability, 45): believed ill-typed in OWL 2, but check
    the specification before adding a rule;
  - ill-typed literals: no rule reports an invalid lexical form (MOD: `'2024-06-2'^^xsd:date` and
    three `'2004'^^xsd:date` that should be `xsd:gYear`); RDFLib only prints a traceback;
  - ranges that are not OWL 2 datatypes (Tractus-X: `rdfs:range xsd:anyType` five times); today
    only ROBOT's `--owl-profile DL` catches them;
  - decide whether LEX002 should judge individuals by default: 345 of CCO's 346 terms without a
    definition are `owl:NamedIndividual` units.

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
  - *Validation on a public corpus:* started on 2026-11-09, see "0.8.0 — real-world ontologies":
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
  the never-run `validation.yml` workflow remains, and it is covered by the mutation-baseline item.
- **"Which rule group next?":** the question is moot. All 55 proposed rules are blocked by a missing
  backend or input contract (COMP 16, CQ 13, FAIR 13, SEM 7, ALIGN 4, GOV 1, IRI 1), so none can be
  implemented without one of the decision gates above being accepted first. (An earlier version of
  this file claimed the gates covered all of them; ALIGN had no gate until it was added.)
- **Packaged catalogue must equal the source copy:** already enforced by
  `tests/test_registry.py` (byte comparison), which runs in CI and in the release `test` job.
  A separate required check would only duplicate it.

