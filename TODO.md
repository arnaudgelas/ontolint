# TODO — delivery roadmap

This is a prioritised delivery plan, not a catalogue of attractive ideas. Its purpose is to make
ontolint safe to run in CI and trustworthy when it reports a result. The rule catalogue remains
[`docs/rules.md`](docs/rules.md) and `src/ontolint/data/rule_catalogue.csv`; do not duplicate its
individual rule backlog here.

**Hotfix** ships on its own, as soon as it is done, and is blocked by nothing else below. `P0`
blocks the feature release after 0.10.0 (0.8.0, 0.9.1 and 0.10.0 shipped, and 0.9.0 was tagged but
not published, while it was still open). `P1` is the next milestone after P0. `P2`
is worthwhile only after the preceding work is complete. “Decision gate” means no implementation starts until the
stated decision is accepted. Re-audit external-service assertions (GitHub settings, Action history
and PyPI state) when starting the item; they do not belong in a permanent source-controlled fact
record.

## Hotfix

Four ways a run can pass, or fail, without the ontology deserving it. Each was reproduced on
2026-11-10 (against 0.10.1, while triaging an external review) and each contradicts the purpose
stated above; ship them together as 0.10.2, each with the reproducing fixture as its regression
test. They change results (findings that were silently lost now appear), so the changelog needs an
upgrade note.

- [ ] **SHACL with an ontology background drops focus nodes that are not subjects of the data.**
  `engine._shacl_with_background` keeps only results whose focus is a subject of the linted graph,
  to hide results about the background's own nodes. A focus selected by `sh:targetObjectsOf` (or
  reached as a value) may never be a subject: `ex:a ex:knows ex:b` with a shape on the objects of
  `ex:knows` requiring `ex:code` reports `ex:b` without `--follow-imports` and nothing with it.
  Keep a result when its focus occurs in the linted graph at all (subject or object, blank nodes by
  their stable identity), and drop only nodes that occur in the background alone.
- [ ] **Shapes imported by the shapes file are used as data, never as shapes.**
  `cli._shapes_background` loads the shapes file's `owl:imports` closure and passes everything but
  the shapes file itself to SHACL as *data*. A shapes file that imports a shape library therefore
  validates with none of the library's shapes, silently: a library shape requiring `ex:name` on
  subjects of `ex:knows` reports nothing. Split the closure: files that declare shapes (typed
  `sh:NodeShape`/`sh:PropertyShape`, or with `sh:path`/targets) join the shapes graph, the rest is the
  ontology background, and say which file went where (a `TOOL` note), since one file can be both.
- [ ] **Named graphs in TriG and N-Quads are dropped.** The loader parses a dataset into one
  `Graph`, which keeps only the default graph: a TriG file whose classes sit in `ex:g1 { … }` loads
  one triple (its header) and reports nothing, although the README lists both formats as read. Lint
  the union of all graphs (what an ontology author means by "this file"), keep each triple's graph
  for source regions and a later per-graph policy, and say in the README that graphs are merged.
  Rejecting datasets with named graphs is the alternative if the union is judged wrong; silently
  linting only the default graph is not.
- [ ] **SEM001 reports ROBOT's own failures as profile violations.** `robot_profile_issues` turns
  every non-zero exit into a `certain` SEM001 finding (exit 1, baselinable). A timeout already
  becomes `failed` and a missing `docker` `unsupported`, but a missing image, a Docker daemon error
  or a permission problem does not: the first Validation run (2026-11-09) reported "/output/
  profile.txt (Permission denied)" as an OWL DL violation. Emit SEM001 only when ROBOT wrote a
  report that `summarise_profile_report` recognises as profile violations; anything else makes the
  rule `failed` with ROBOT's stderr (exit 2). Fixtures: a fake `docker` exiting 125, a Java crash
  without a report, a genuine violation report, a timeout. Move SEM001's focus off the absolute path
  (the ontology IRI, or the report path) at the same time, since both change its fingerprint.

## Recently done

- 0.10.1 (`45175d3`, tag `v0.10.1`), released 2026-11-10: the release `verify` job retries its PyPI
  file-list and attestation checks (`7fa251f`), after the 0.10.0 run (42774442860) failed there on
  PyPI's lagging JSON API although its files were sound (checked by hand). Run 42778283292 passed
  every job; its install step needed one retry, the attestation step none, so the new retries are
  proven only by the local run of the step's script with stub `curl`, `uv` and `sleep` (a lagging
  API passes, an extra file or a failing attestation still fails). Same code as 0.10.0.

- 0.10.0 (`d6c45c1`, tag `v0.10.0`), released 2026-11-10: run 42774442860 passed the CodeQL gate,
  tests and build, and published both files; its `verify` job failed on PyPI's lagging JSON API
  (see "Hotfix"), and the attestations were verified by hand instead. Its changelog has the upgrade
  note below. The gate passed (5663 tests, 99.4% coverage), and a
  targeted mutation run of `modules.py`, `prof.py`, `library.py`, `rules/library.py` and
  `reporting.py` killed every mutant (one equivalent `frozen=True` pardoned):
  - **baseline break, on purpose:** `ONT005` names the provenance that is missing ("Missing
    creator and dcterms:created provenance.", or only the one that is absent) and `OWL013` prints
    the literal in N3 (`"lit"`), not its Python repr. Both change the fingerprints of their
    findings, so baselines holding them must be regenerated. `legacy_rules.json` was re-pinned
    after every legacy view of 0.9.0 was shown equal to the new one up to exactly those two
    substitutions (see the `test_differential.py` docstring). `OWL034`, `OWL036` and `OWL040`
    still print reprs (P1); fixing them breaks baselines again, so do it in this release too if
    possible;
  - `--module-annotation PREDICATE` and `--module-by namespace` (policy `module_annotation`,
    `module_by`) group findings by modules inside one file: `In: module X`, a "Findings by
    module" summary, JSON `modules` and `module_summary`, SARIF `properties.modules`; a collision
    belongs to every term's module (`Finding.related`), fingerprints unchanged. Validation: the
    food-traceability schema groups into its 13 `opla:isNativeTo` modules (findings on its 37
    unannotated terms have none); Tractus-X `ontology.ttl` shows all 13 IRI003 collisions and 5 of
    the 6 LEX004 collisions as cross-module (the sixth is within `behaviour#`, so the earlier count
    of "6 between domains" was wrong);
  - `--shapes-from-profile PROFILE` uses the SHACL validator a W3C PROF profile names, found
    offline (catalog, `--import-dir`, or a file named after the artifact beside the profile) and
    sandboxed (`SEC009`). Validation: MOD's own `profile.ttl` and `validator.ttl` are not valid
    Turtle (undeclared `rdfs:` and `dcatnull:` prefixes) and fail with an INPUT001 naming the file;
    with those two prefixes added, the profile resolves `…/dcat-profile/validator` to
    `validator.ttl` and gives the same 14 `SHACL001` findings on `mod.ttl` as `--shapes`;
  - `--pattern-library DIR` and rules `LIB001`-`LIB003` (opt-in by input, skipped without it;
    catalogue: 302 rows, 247 implemented). Validation on MODL (`modl/modl.owl` with `modl/`): 12
    of the 31 pattern files do not parse with RDFLib (unterminated strings, newlines in literals,
    undeclared prefixes) and are skipped with `TOOL008`; none of the 29 index entries (`Sequence` is
    declared twice) names a pattern by IRI (14 have a same-named pattern, which the message names),
    5 patterns have no entry, and 5 headers name a related pattern that no file declares
    (`…/agent`, twice) or that is in a skipped file (`…/provenance` twice, `…/participantrole`),
    which the message then says.

0.6.0, 0.7.0 and 0.8.0 were released on 2026-11-09, each after the maintainer's approval in the
release run (0.8.0: run 42586191689, all jobs green, 0.8.0 on PyPI). 0.9.0 was tagged the same
day (`98b82f6`) and pushed, but its release run failed at the CodeQL gate before publishing: `main`
was pushed with a commit on top of the tagged one, and CodeQL scans only the head of a push
(`docs/releasing.md` now says so). The same code shipped as 0.9.1 on 2026-11-10 (`18e1343`, run
42769298672, all jobs green, both attestations verified by its `verify` job). Kept only so the next
audit can confirm them, then delete these entries.
Leftovers from each are in the open items below. The 0.4.x and 0.5.x entries were confirmed (all released, release jobs green) and removed;
`CHANGELOG.md` keeps their record.

- 0.9.0 (`98b82f6`, tag `v0.9.0`), tagged but never published; released as 0.9.1:
  - borrowed vocabulary terms are not the ontology's own (`f31e419`): Dublin Core, SKOS, DCAT, IAO
    and the other `WELL_KNOWN_NAMESPACES` declared for OWL 2 DL no longer draw LEX001, LEX002,
    METRIC003, IRI005 or IRI008. A fixture with the pattern gave 16 findings on 0.8.0 and none
    now; the corpus, twelve well-known vocabularies linted on their own and the CCO closure are
    unchanged;
  - SEM001 groups ROBOT's violations by kind and subject; the full report is the finding's new
    `details` field in JSON and SARIF (`7340436`);
  - the release `verify` job checks PyPI holds exactly the built files and verifies each one's
    PEP 740 attestation (`7e65c06`), tried on the published 0.8.0 files and on tampered copies;
  - specifications for every error-severity rule and the whole OWL family (OWL001-OWL045, the
    SKOS errors, ALIGN003, the SHQ errors, SEC014 and the pipeline rules), in each module's
    docstring with cases for each condition and exclusion and corrected catalogue rows
    (`d0325a3` to `627ed47`). Defects fixed on the way: OWL008, OWL011 (the closure axiom it
    recommends: 20 false positives gone on the corpus, nothing else changed), OWL022, OWL024,
    OWL036 (`-0`), SKOS001 (tag case, `xsd:string`), SKOS002, SKOS008, SKOS009 (transitive),
    SKOS016, SHQ011 (`x` and `q` flags), SHQ018 (a crash and numeric promotion), and in the safe
    loader SEC001 (catalog size), SEC009 (symlinked directories) and SEC013 (C resolvers, UDP).
  - the first `validation.yml` run (42611542815, scheduled, 2026-11-09) failed in both jobs, both
    fixed but not yet proven by a hosted run: the ROBOT container runs as the calling user
    (`30e5732`, `bc250fe`), as the image's `nonroot` user could not write `profile.txt` into the
    0700 output directory on Linux (SEM001 "Permission denied"; Docker Desktop hides it); and
    `coverage_timeout = 900` for gremlins (`d1754e9`), since the pre-scan exceeded the 120 s
    default, test selection was disabled, and the run hit the two-hour job timeout at mutant 1446
    of 1696.
  - Turtle that starts with an anonymous blank node (`[] a ex:K .`, as RDFLib writes one) is no
    longer sniffed as a JSON-LD array, which failed to parse (`a02f05b`); found by the round-trip
    property test, whose case is now an explicit `@example`;
  - `--convert-with-robot` (`681af62`) reads OWL Functional, Manchester and OWL/XML files, inputs
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

## P0 — before 0.11.0

- [ ] **Turn Renovate on, and watch its first rebase.** Rechecked 2026-11-10: `.github/renovate.json`
  passes `renovate-config-validator --strict` (Renovate 41), and the repository still has only
  `main`, no pull request and no issue, so the app is not running here; the cause is outside the
  repository (installation scope or the Mend portal), and the maintainer's to check. The release boundary is in place and proven
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
  nothing for tags and can go (approved 2026-11-10; the token used here has no admin right on the
  repository, so remove it in Settings → Rules → `tags`). *Done when:* both are observed once.

## Real-world ontologies — left open by 0.8.0

Everything here comes from linting fifteen public ontologies on 2026-11-09 (sources in the corpus
table at the end of this section). Each item names the files that show it; every fix gets a small
synthetic fixture copying the pattern, and the real repositories are only used for validation runs.
What is done is under "Recently done"; nothing is open here as of 2026-11-10, only the decisions
below.

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
  - ONT005's message changed at the 0.10.0 baseline break (2026-11-10), not at 1.0: pre-1.0
    minor releases may break baselines with an upgrade note.
  - Modules inside one file, PROF profiles and pattern libraries are in scope (2026-11-10) and
    built for 0.10.0 (see "Recently done"). Left for later, only if asked: a
    `library_entry_classes` policy key (the entry classes are inferred today), and linking a
    pattern library whose index names patterns by some other convention than IRI or name.

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
| kastle-lab/modular-ontology-design-library (MODL) | pattern library: index plus 31 pattern ontologies, Turtle in `.owl`, 12 not parseable | syntax sniffing; trailing `#` IRI; library consistency |
| eclipse-tractusx/sldt-ontology-model | merged release of eight domain ontologies, one namespace each | modules by namespace; `xsd:anyType`; SPDX licence |
| FAIR-IMPACT/MOD | metadata vocabulary, PROF profile, SHACL validator (both invalid Turtle) | metadata one hop away; ill-typed literals; profile-discovered shapes |
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

- [ ] **Keep SHACL's evidence in SHACL001.** A finding carries the result message, focus and
  source shape only; the report's `sh:resultPath`, `sh:value`, `sh:sourceConstraintComponent` and
  `sh:resultSeverity` are dropped, so two violations of one shape on one node read alike and a
  fix has to be found by rerunning pySHACL. Put them in the finding (`details` in JSON and SARIF
  today; the message only if a baseline break is accepted, see the next item), with a fixture per
  constraint component family (value type, cardinality, property pair, logical, SPARQL-based).
  *Done when:* every SHACL Core result field present in the report reaches JSON and SARIF.

- [ ] **Decouple baseline identity from message wording.** A fingerprint hashes `(rule, focus,
  message)`, so every message fix is a baseline break: 0.10.0 broke baselines for ONT005 and
  OWL013, and fixing OWL034, OWL036, OWL040 and SEC014 will break them again. Design a version 2
  identity from the rule, the focus and the finding's structured subject (the terms, predicate or
  axiom it is about, which `Finding.related` already starts to carry), never from prose; write it
  next to the version 1 hash in `--write-baseline` and accept either when reading, so existing
  baselines keep working. Decide it before the next message change, not after. *Done when:* a
  message-only change leaves every baseline matching, proven by a test that rewords a message.

- [ ] **Audit the specifications of implemented rules, not only proposed rules.** A rule can be
  implemented, tested, and still be semantically under-specified if it began as a catalogue title;
  roughly 120 of the 244 implemented rules (tranche 1, OWL, METRIC and the leftovers) were
  specified from placeholder titles and never reviewed. The goal as written covers all 244 and will
  not finish: take one family per milestone, starting with error-severity rules and the OWL and
  METRIC families. Done in 0.5.2 for the three rules known to have drifted (IRI015, LEX018 and
  LEX021): their module states each condition, and their catalogue test requirements no longer
  describe the original plans. Specify
  scope, formal condition, exclusions, confidence/severity rationale, and positive and negative
  fixtures; correct documentation or implementation when they disagree.
  *Done when:* each implemented rule has an approved, testable specification and its catalogue,
  user documentation, and fixtures state the same contract.
  Done for 0.9.0: every error-severity rule and the whole OWL family (see "Recently
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
    (SEM001's misclassification and machine-dependent focus moved to "Hotfix"); SEC014's focus repeats the password it reports (RFC
    3986 §3.2.1 says not to show it); OWL013 (legacy), OWL034, OWL036 and OWL040 print Python
    reprs (`rdflib.term.Literal(...)`) instead of N3 (OWL013 fixed in 0.10.0);
  - *False positives found by the 2026-11-10 review:* LEX002 (and every rule using
    `RuleContext.descriptions`) follows `rdfs:subPropertyOf` one step only, so a definition through
    `ex:def2 ⊑ ex:def1 ⊑ skos:definition` is reported missing (reproduced). Take the transitive
    closure, bounded and cycle-safe.
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
  and `release.yml`, because Trusted Publishing creates one. Done in 0.9.1: the release `verify`
  job (`7e65c06`) checks that PyPI holds exactly the built files and verifies each one's
  attestation; the 0.9.1 run printed OK for both files. Still open:
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
  *Done when:* the copyright-holder question has a written answer in the repository.

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
  "Recently done") and on `main` since 2026-11-09. Its re-run on 2026-11-10 (attempt 2) proves
  nothing: a re-run repeats the original commit (`7b08ff8`, 0.8.0), so the ROBOT job failed again
  with the old "/output/profile.txt (Permission denied)". Start a new run with "Run workflow" on
  `main` instead, then have a
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

- [ ] **Record per-rule findings on the validation corpus at every release.** The corpus in
  "Real-world ontologies" is only used by hand, so a release can double one rule's findings on CCO
  unnoticed. Pin each repository's commit, run a fixed command per file, and keep the per-rule
  counts in the repository; a release shows the diff and explains every change (the 0.8.0 and
  0.9.0 entries above did this by hand). This is the cheap half of precision measurement; labelled
  true and false positives remain the metric-calibration item's job. *Done when:* a script
  reproduces the counts from pinned sources and the release instructions require reviewing their
  diff.

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
  corpus and a memory/time budget. The ADR must also fix: an import lock (each import's resolved
  file and checksum, recorded per side), since comparing two versions over different dependency
  closures proves nothing; open-world semantics (a narrower domain adds inferences, it rejects no
  data, so "breaking" is relative to a stated consumer policy); and the change classes reported
  (annotation, vocabulary, asserted axiom, entailed axiom, which needs the SEM backend). A text
  diff that calls every removed triple breaking is not acceptable. Whether two-input commands mean
  subcommands (`ontolint diff`) is part of this ADR; flags on today's command are not.
- [ ] **Competency questions (`CQ*`).** Define query packaging, expected bindings/ASK semantics,
  deterministic result serialisation, and query execution limits. A format already used in
  practice, and a good first candidate: one SPARQL `SELECT ?answer` per `.rq` file, the question in
  a `# CQ:` comment and the expected set of answers in an `# expect: a | b` comment, evaluated
  against the import closure (`--follow-imports`, available since 0.6.0) and compared as
  sets. *Gate:* accepted format and at least one public corpus that justifies maintaining it.
- [ ] **Reasoner-backed semantics (`SEM*`).** Define supported reasoners/profiles, Docker versus
  local dependency model, reproducibility, timeout/failure behavior, and CI image ownership.
  *Gate:* accepted adapter contract and deterministic container fixtures. Recommended as the first
  bet (2026-11-10, after an external review ranked semantic verification, version comparison and
  competency questions as the three gaps that matter most): it is the cheapest, because the
  isolated ROBOT image, its adapter and the CI job that builds it already exist (`robot reason`
  and `explain` give consistency, unsatisfiable classes and justifications), and it is a
  prerequisite of the others' semantic rules (COMP016, COMP017, ALIGN010). Its adapter contract is
  the SEM001 fix in "Hotfix" generalised: a verdict only from a parsed report, every other outcome
  `failed`, `unsupported` or a timeout. Keep OWL *profile* compliance (SEM001) and *consistency*
  (SEM002, SEM003) as separate rules and say so in the README; a profile pass proves nothing about
  consistency, and ELK (EL only) must not report "consistent" for an ontology outside EL.
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
  mocked tests. There is no default-network implementation. The design must cover, with tests:
  one HTTP client for all three families; destinations checked at every connection and redirect
  (no loopback, private, link-local or metadata addresses; DNS rebinding); response size,
  decompression, time and redirect limits; no credentials; and evidence per request (URL, redirect
  chain, status, negotiated type, time), because a DNS or HTTP failure is an observation, not proof
  that an ontology is not FAIR. Registry absence (FAIR005) is not a defect for an internal
  ontology; it belongs in an opt-in profile.
- [ ] **Modular ontologies: finish what stages 1-4 left open.** Stages 1-4 are built (see "Recently
  done"): offline resolution, per-module provenance, closure semantics and SHACL with the ontology
  as background. Left:
  - *Validation on a public corpus:* started on 2026-11-09, see "Real-world ontologies — left open
    by 0.8.0". The import root and ownership (0.8.0) and Functional Syntax (`--convert-with-robot`,
    0.9.0) no longer block it: CCO and EMMO lint as closures, and the automatce edit file with its
    12 imports. What is left is the maintainers' false-positive review below.
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
- **Automatic fixes (`--fix`):** defer until findings carry structured evidence (the SHACL and
  baseline-identity items in P1); only round-trip-verified, meaning-preserving edits would ever
  qualify, and modelling or logical corrections (deleting an axiom that causes an inconsistency)
  never.
- **Editor integration (a language server):** defer until source regions are exact for the
  formats it would serve; today they locate a term's occurrence, not the offending axiom.
- **A single quality score, and AI-generated suggestions presented as checks:** rejected. A score
  hides which dimension failed; generated text is not a deterministic verdict.
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

- **External review of 2026-11-10 (written against 0.8.0):** its confirmed defects are in
  "Hotfix" and P1, its product ranking informs "Decision gates". Claims checked and not taken up:
  the catalog is already read bounded (`imports._catalog_bytes` reads at most `max_bytes + 1`,
  SEC001, since 0.9.0); `--explain RULE`, `--list-rules --format json` and per-rule execution
  status with exit `2` for a failed or unsupported rule already exist, which is the "incomplete
  analysis" signal it asks for (what was missing is that SEM001 bypassed it, now in "Hotfix");
  SHACL severities are already kept (`sh:Warning` is `warning`); selecting one rule still runs its
  module and filters, which costs time, not correctness, and is left until profiling says
  otherwise; the process-wide socket block is defence in depth around a single-process CLI, and
  parsing moves to a worker process with `--max-parse-seconds`. Its proposed CLI subcommands and
  evidence model are design input for the COMP ADR and the P1 SHACL item, not tasks of their own.

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

