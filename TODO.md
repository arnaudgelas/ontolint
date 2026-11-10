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

Nothing open: 0.10.2 is released (see "Recently done").

## Recently done

- Unreleased (on `main`, not yet tagged):
  - **SHACL-TIMEOUT** (P1): SHACL validation can be bounded in time and never reaches the
    network. `max_validation_seconds` (and `--max-validation-seconds`; same range and checks as
    `max_parse_seconds`, unset by default, never inherited from it) runs each file's validation
    in a worker process and stops it at the budget: `SHACL001` is `failed` with
    `ValidationTimeout: SHACL validation did not finish within the time budget of <s> seconds
    (max_validation_seconds)`, the report is written, `TOOL001` names the file, exit 2, as for a
    ROBOT timeout. The budget starts once the worker has imported pySHACL and includes decoding
    the graphs there; it covers shapes from `--shapes-from-profile` and imported shape libraries,
    since they join the shapes graph. pySHACL now runs inside `network_disabled()` on both paths:
    any socket or DNS attempt, even one pySHACL swallows, fails the rule (pySHACL refuses
    `SERVICE` only with a regular expression). The worker is built once, as
    `ontolint.worker.run_bounded` (`WorkerTask`: `prepare` before ready, `run` returning one JSON
    object; `WorkerTimeout`, `WorkerGone`, `WorkerFailed`; the JSON graph codec); the parse budget
    runs on it with byte-identical `SEC003` and `INPUT001` messages, and the CQ gate's runner can
    be a third task. The README's "Input safety" lists the bounded phases (sizes always, ROBOT,
    and with a budget parsing and SHACL) and the unbounded one (rule families, measured by
    `tests/test_scaling.py`), `inference="none"` and what `advanced=True` admits.
    Verified: the TODO reproduction (100 `ex:Thing`, about 400 triples, a four-pattern `sh:sparql`
    join; still running after 30 s on 0.10.2) with `--max-parse-seconds 2
    --max-validation-seconds 2` ends in 2.6 s wall clock with exit 2 and a `failed` execution,
    and runs as the regression test (in a subprocess, budget 0.5 s); the SARIF run is
    `executionSuccessful: false` with an `error` notification; two files give two `TOOL001` lines;
    no worker survives. Findings, `details`, `related`, `subject` and `evidence` (`sh:node`
    detail, complex path, ill-typed and non-ASCII literals, a rebound `schema:` prefix, blank
    shapes and foci, the background filter) are equal with and without the budget, and JSON, SARIF
    and text reports are byte-identical with a generous budget; a Hypothesis property checks the
    worker task against `shacl_issues` without a process, and the Finding codec field by field.
    A refused shapes graph starts no worker and reads the same. Golden files, `differential.json`,
    fingerprints and baselines did not move; `docs/rules.md` changed only by the new field in the
    `Policy` reprs; each commit passed Ruff, Pyright and the tests on its own in a clean worktree.
    Targeted mutation run (`worker.py`, `adapters/shacl.py`, `engine.py`): 117 mutants, 108
    killed, 5 pardoned (the moved parse-worker pardons and the frozen validation job), none
    surviving, 3 timeouts and 1 error (not named by the console report).
    Left open: no default budget (turning one on would make today's long but successful runs
    exit 2: the maintainer's call); the worker's memory is not capped (as the parse worker's
    is not); Windows and Linux behaviour of the worker is checked only by `mypy --platform win32`
    until the P2 cross-OS smoke tests exist; a pySHACL `ValidationFailure` (for example its
    `SERVICE` refusal) still reads `RuntimeError: pySHACL returned an unexpected report type`;
    whether POLICY-SILENT should note the key without shapes, where it has no effect.
  - **BASELINE-V2** (P1): baselines match a finding by its identity (rule, focus and a structured
    `Finding.subject`, never the message) as well as by its version 1 fingerprint, so a reworded
    message, a pySHACL upgrade or a measurement that moves keeps an accepted finding accepted and
    its entry not stale. `--write-baseline` writes version 2: the unchanged `fingerprints` list,
    `files` (the run's report paths) and `identities` (per path, identity → fingerprint).
    Identities are matched per report path, or for any path when both runs have one file, so
    one-file and multi-file baselines carry over to each other and a renamed file keeps its
    baseline. Two findings of one file that share an identity are matched by fingerprint only. A
    malformed baseline file exits 2 (`TOOL001 … BaselineError`) instead of matching nothing.
    Every `RuleContext.add` site states its subject (`subject=()` where a rule reports at most once
    per focus); counts, ratios, thresholds and prose are never part of it, so METRIC*, OWL004,
    CLS006, SEC004/SEC005 and SEM001 (subject: the profile) are baselinable through measurement
    changes; SHACL001's subject is `shacl_result_key`; SEC014's is empty, never the password.
    When one message reaches `add` with several subjects, the finding keeps the least, so the
    identity does not depend on the hash seed. Verified: a test rewords every message of every
    positive rule case, the kitchen sink (with its shapes) and each SHACL constraint family, and
    finds nothing new and nothing stale; the same with `--fail-on-stale-baseline` through the CLI,
    for rule findings and for two SHACL001 results sharing one message; a baseline written by
    0.10.2 (`tests/fixtures/baseline_0_10_2.json`) gives exactly the 0.10.2 results, and 0.10.2's
    reader gives the version 1 results on a version 2 file; one-file → multi-file, multi-file →
    one-file, renamed one-file runs and their negatives; ambiguity, staleness and an 11-case
    malformed-file matrix. Subjects are kept unique by an AST contract
    (`tests/test_subject_contract.py`, which names the file and line of an add site lacking
    `subject=`), by a corpus run of every rule case and fixture with all rules, and by a
    Hypothesis property. The reproduction prints
    0 / 0 / 4 of 4 / 0 (was 0 / 4 / 8 / 4); the 0.10.0 ONT005/OWL013 rewording, replayed against
    a version 2 baseline, reopens nothing. Reports, exit codes, `legacy_rules.json` and
    `differential.json` did not move (`git diff tests/golden` is empty across the series), and
    each commit passed Ruff, Pyright, mypy (host and Win32) and the tests on its own in a clean
    worktree.
    Found and fixed with it: `test_properties_datasets.py` split N-Triples with
    `str.splitlines`, which also breaks at U+0085 inside a literal. Targeted mutation run
    (`baseline.py`, `reporting.py`, `rules/runtime.py`): 137 mutants, 131 killed, 1 older pardon,
    2 timeouts (not named by the console report) and 4 survivors, now settled: the two path-free
    boundaries (`len(files) == 1`, `len(reports) == 1` shifted to 0) are killed by a new
    renamed-and-reworded test (each of the four shifts checked by hand to fail a test), and two
    equivalents are pardoned (`zip(strict=True)` over lists built from one another; `<` or `<=`
    when keeping the least subject). The run was not repeated after those changes.
    Left open, under P1 "Baseline identity": release sequencing, the upgrade note to paste at
    release, the lenient version 1 match, SARIF `partialFingerprints`. Messages this release
    changes for an unchanged input: none so far (list each later rule here as it lands).
  - **SHACL-EVIDENCE** (P1): each `SHACL001` finding carries every field of its SHACL validation
    result as JSON `evidence` (after `details`) and SARIF `properties.evidence` (before `graphs`),
    never in text: `focusNode`, `resultPath`, `value`, `sourceShape`, `sourceConstraintComponent`,
    `sourceConstraint`, `detail`, `resultMessage`, `resultSeverity`, each only when the report has
    it. Spellings (README "Optional SHACL validation"): IRIs plain, blank nodes the content-stable
    `_:` id, literals one-line N-Triples, complex paths in SPARQL property-path syntax,
    `(malformed path)` for a cyclic, over-deep (32) or over-large (1,000 nodes) one; `sh:detail`
    nests at most 8 deep.
    `Finding.evidence` is `compare=False`, so identity, fingerprints and baselines ignore it, and
    `adapters.shacl.shacl_result_key` gives BASELINE-V2 its SHACL001 subject. Found and fixed with
    it: pySHACL's result order depends on `PYTHONHASHSEED`, so the adapter now sorts tied findings
    by their evidence. Verified: the two non-integer values of the original reproduction now
    differ in `evidence.value`; a fixture per family (value type, cardinality, property pair,
    logical, SPARQL-based, plus `sh:node` and complex paths) pins the exact evidence, and a test
    checks both ways that every property pySHACL writes on those results reaches JSON and SARIF;
    text output and a `--write-baseline` file are byte-identical before and after;
    `legacy_rules.json` did not move, and in `differential.json` only
    `json_clean_shacl_violation`'s two full-output hashes changed (JSON-tree diff); JSON bytes
    are equal under seeds 1 and 2, which reversed pySHACL's order. Targeted mutation run
    (`adapters/shacl.py`, `models.py`, `reporting.py`): 137 mutants, none surviving, 1 pardoned
    (older), 1 timeout and 5 errors from tests slower than half the mutant timeout. Left open,
    under P1 "SHACL001 evidence": nested `sh:detail` results are still also findings of their
    own (the maintainer's decision), evidence in text output, and SHACL-AF `sh:resultAnnotation`.
  - **DATASET-PROVENANCE** (P0): each finding of a TriG, N-Quads or JSON-LD dataset names the
    graphs its terms come from, as JSON `graphs` (between `path` and `modules`), SARIF
    `properties.graphs` and text `In: graph X` / `In: graphs X, Y`. The loader records, before
    merging, which graphs state each triple (`datasets.GraphIndex`, on `LoadedGraph.graphs` and
    `Module.graphs`, in process and in the parse worker, for every file of a closure); a finding
    names the graphs that describe its focus, else those that mention it, and a collision those of
    every term. Decisions, in the README: a triple in two graphs belongs to both, and SHACL (like
    every rule) validates the union; per-graph validation means splitting the dataset into files.
    The key is `graphs`, not the `graph` this entry asked for, because a term can be in several
    graphs; later items (METRICS-ENGINE, the OPS schema) must not reintroduce a singular key.
    Graph names hold no machine path (a `file:` graph IRI, such as `<rel>`, `<../g>` or `<#g>`, is
    printed relative to the file) and no parser label (a blank graph is named by a digest of its
    triples). Found and fixed with it: JSON-LD named graphs (`@id` with `@graph`) were dropped, as
    TriG's were before 0.10.2, so such a file linted as 0 triples; JSON-LD is now a dataset syntax
    (rdflib's format name `json-ld`).
    Verified: a file with only a default graph reports byte for byte as before
    (`tests/golden/single_graph_reports.json`, generated by the 0.10.2 code, unchanged since, and
    the default-only TriG, N-Quads and JSON-LD twins equal their Turtle twin in all three formats);
    `differential.json` and `legacy_rules.json` did not move; fingerprints and baselines do not
    depend on graphs (a baseline written from TriG equals the Turtle one, and moving a triple to
    another graph keeps it matching; a Hypothesis property checks the findings against the plain
    graph, soundness, completeness and label independence); each commit passed the tests on its
    own in a clean worktree. Targeted mutation runs (`--gremlin-targets`): `datasets.py` and
    `reporting.py`, 132 mutants, all killed but two pardoned equivalents (`zip(strict=True)` after a
    length check, and the older frozen `Origin` in `reporting.py`); `loader.py`, `cli.py`,
    `imports.py` and `datasets.py`, 320 mutants: none survives in the changed code; the 10
    survivors are older code (the TOOL005 hint, `_library_origins`, `_file_modules`, `_library`,
    catalog parsing in `imports.py`), left for the mutation-baseline item, and 4 timed out.
    Left open: TriG has no SARIF regions (see the P1 source-regions item). By design, `(ontology)`
    foci (ONT001, ONT002) name no graph.

- 0.10.2 (`f7f3db4`, tag `v0.10.2`), released 2026-11-10: `main` was pushed with the release
  commit as its head, then the tag. CodeQL (run 42785068415) and CI (42785069613) passed on
  `f7f3db4`, and the release run 42785082184 passed every job: CodeQL gate, tests, build, publish
  (both files on PyPI) and `verify`, whose install step needed one retry and whose attestation
  step none (OK for the wheel and the sdist). Rechecked 2026-11-10 against GitHub and PyPI: `main`
  and `v0.10.2` on the remote both resolve to `f7f3db4`, and PyPI's latest version is 0.10.2.
  It fixes four ways a run could pass, or fail, without the ontology deserving it, each found by
  triaging an external review, reproduced on 0.10.1 and fixed with that reproduction as its
  regression test (against the 0.10.1 code, 9 of the new tests fail; all pass now):
  - SHACL with an ontology background keeps results on foci the linted file mentions as objects
    (`sh:targetObjectsOf`), not only as subjects;
  - shapes a shapes file imports are validated (a shape library joins the shapes graph, with a
    `TOOL009` note; its other triples join the background), where they were used as data;
  - TriG and N-Quads named graphs are merged into the linted graph, where only the default graph
    was read (`max_triples` counts every graph; in process and in the parse worker);
  - verified: each fix commit passed the tests on its own, in a clean worktree, and the gate
    passed at the release commit. Targeted mutation runs of `adapters/robot.py`, `engine.py`,
    `loader.py` and `cli.py` killed every mutant in the code 0.10.2 changes. The rest, all older
    code, is left for the mutation-baseline item in P1: 3 in `robot_convert`'s subprocess call
    (killed by `f9ccf1a`), 3 in the TOOL005 hint (0.8.0), 3 in 0.10.0's `cli.py` code that its
    own mutation run left out (`_library_origins`'s empty result and `_file_modules`'s prefix
    fallback, both equivalent; `_library`'s default import root, which needs a test), and 3 errors
    (two `frozen=True` mutants, one timeout in `engine._not_run`);
  - SEM001 is a verdict only when ROBOT lists profile violations; a missing image, a Docker, Java
    or permission error fails the rule (exit 2) instead of becoming a baselinable finding, and its
    focus is `(ontology)`, not the machine's absolute path. Baseline break for SEM001 entries;
    `legacy_rules.json` re-pinned after its other findings and exit codes were shown unchanged.

- 0.10.1 (`45175d3`, tag `v0.10.1`), released 2026-11-10: the release `verify` job retries its PyPI
  file-list and attestation checks (`7fa251f`), after the 0.10.0 run (42774442860) failed there on
  PyPI's lagging JSON API although its files were sound (checked by hand). That run stays red
  unless someone with admin rights re-runs its failed job; nothing depends on it. Run 42778283292 passed
  every job; its install step needed one retry, the attestation step none, so the new retries are
  proven only by the local run of the step's script with stub `curl`, `uv` and `sleep` (a lagging
  API passes, an extra file or a failing attestation still fails). Same code as 0.10.0.

- 0.10.0 (`d6c45c1`, tag `v0.10.0`), released 2026-11-10: run 42774442860 passed the CodeQL gate,
  tests and build, and published both files; its `verify` job failed on PyPI's lagging JSON API
  (fixed in 0.10.1), and the attestations were verified by hand instead. Its changelog has the upgrade
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

- [ ] **Source regions for TriG.** SARIF results for a `.trig` file have no region:
  `source_locations._TEXT_FORMATS` lists Turtle, N3, N-Triples and N-Quads but not TriG (README
  "Rule execution status"). Found while adding named-graph provenance (2026-11-10), which does not
  need it. Locate terms inside graph blocks too, with a property test like the other formats'.
  *Done when:* a TriG finding has the region of its focus, as its Turtle twin does.

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

- [ ] **SHACL001 evidence: what is left to the maintainer.** The evidence itself is done
  (unreleased, see "Recently done"). Three choices were left out because each changes a contract:
  - *Nested results reported twice.* pySHACL types the `sh:detail` results of a `sh:node`
    violation as `sh:ValidationResult` too, although the report's `sh:result` does not list them,
    so each is a finding of its own as well as an entry
    of its parent's `evidence.detail` (reproduced 2026-11-10: 12 typed results, 11 top-level).
    Dropping the nested ones changes finding counts, stale-baseline lists and `--fail-on` exit
    codes; keep or drop is the maintainer's decision, and the evidence now makes the duplicate
    visible.
  - *Evidence in text output* (a `Value:` line, say): the text format is a protected contract.
  - *SHACL-AF `sh:resultAnnotation`* (with `advanced=True`): such a property would not reach the
    evidence. `tests/test_shacl_evidence.py` fails if pySHACL writes an unmapped property on its
    fixtures, but a shape that declares annotations is not among them.
  *Done when:* each of the three is decided, and a decided change has its fixture.

- [ ] **Baseline identity: what is left to the maintainer.** Version 2 baselines are done
  (unreleased, see "Recently done"). Left open, each a decision rather than code:
  - *Release sequencing.* Baselines written by 0.10.x hold version 1 hashes only, so a message
    fix shipped in the same release as identity v2 still breaks those entries once. Recommended:
    ship v2 in release N, with the upgrade note "regenerate the baseline once", and the message
    fixes (OWL034, OWL036, OWL040, SEC014's focus, METRIC rounding) in N+1. Bundling them, as the
    0.10.0 entry hoped, is the maintainer's call. SEC014's planned focus change breaks both hashes
    by design (the focus is part of the identity); its upgrade note must say so.
  - *The upgrade note* goes into the release's CHANGELOG by hand (docs/releasing.md step 1); the
    text is in the body of the `feat:` commit that matches baselines by identity.
  - *Version 1 acceptance stays lenient.* `--baseline` accepts a finding when either hash is
    recorded, so a new SHACL001 result whose message equals an accepted one's is still accepted
    by its fingerprint. Refusing version 1 matches for paths a version 2 file covers would close
    that, but would also reopen findings whenever a later release refines a rule's subject:
    decide which risk to take.
  - *SARIF `partialFingerprints`* (code scanning merges results without them): left to the
    GITHUB-ACTION item, which has the consumer.
  *Done when:* each is decided, and a decided change has its test.

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
    (SEM001's misclassification and machine-dependent focus: fixed in 0.10.2); SEC014's focus
    repeats the password it reports (RFC 3986 §3.2.1 says not to show it); OWL013 (legacy), OWL034, OWL036 and OWL040 print Python
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

## P1 — quality observability: measurements, not a score

Requested 2026-11-10: publish the measurements behind the METRIC rules as a vector, compare them
across commits and releases, and gate on explicit thresholds; never one health score (rejected
under "Explicitly deferred"). What it builds on: METRIC001-METRIC013 already compute thirteen
aggregates in single passes over `ctx.context`, but a value is visible only as a finding when it
crosses a threshold, so nothing below a threshold is published and no trend can be built from
today's reports. Every item here keeps to these rules:

- a measurement has an ID, a definition version and a population (owned terms only, by the
  ownership rules of 0.8.0; per file, module or named graph). A ratio is published as its numerator
  and denominator, never as the ratio alone;
- a measurement that could not be taken (no reasoner ran, no CQ manifest) is absent with a reason,
  never 0. A threshold on it makes the run incomplete (exit 2); it never passes;
- measurements are deterministic and stay out of the default text output. They change no finding,
  fingerprint or exit code unless a budget is configured.

Order: DATASET-PROVENANCE (P0; done, unreleased: `datasets.GraphIndex` gives every triple's
graphs), then METRICS-ENGINE, then the snapshot (QUALITY-BASELINE and QUALITY-TRENDS), then
QUALITY-BUDGET (P2). DQV-REPORT and MARKDOWN-SUMMARY render the same model and
GITHUB-ACTION ships them. DUPLICATE-ONTOLOGY-ID is independent of the rest and can go first.

- [ ] **METRICS-ENGINE: reusable graph- and term-level measurements.** Move each METRIC rule's
  computation into a named measurement and make the rule a threshold over it. `differential.json`
  and the legacy golden must not move, because the refactor changes no finding. Publish the vector
  in JSON (`measurements`, per file and per module or graph). The first set is all computable
  offline today:
  - label, definition and property-documentation coverage (METRIC001-003). Definitions need the
    transitive subproperty closure (the LEX002 item under P1), or the numbers inherit its false
    negative;
  - the hierarchy-depth distribution, as a histogram rather than only the maximum that
    `--depth-limit` checks;
  - disconnected parts of the asserted hierarchy. Define them as weakly connected components of
    `rdfs:subClassOf` among owned classes with `owl:Thing` excluded; with it, every ontology is one
    component;
  - externally referenced terms (METRIC010's count, by namespace);
  - unresolved imports (SEC007's list, as a count);
  - SHACL target coverage (owned classes some shape targets): the test coverage available without
    CQ.

  Measurements that belong to their gates and are not faked now:
  - unsatisfiable classes (SEM gate). The measurement is "unsatisfiable under reasoner R, version
    V" and is absent without a reasoner. An empty extension in the asserted graph is not
    unsatisfiability, and a class without asserted instances is no defect in a TBox;
  - CQ pass rate and the vocabulary CQs exercise (CQ gate, CQ009);
  - mapping coverage and unreviewed equivalence mappings (ALIGN gate). These need SSSOM review
    status, and counting `skos:*Match` and `owl:equivalentClass` alike would treat a link as a
    logical axiom.

  Term-level values (which terms lack a definition) go into the snapshot, not into the report
  body, so reports stay small. *Done when:* METRIC001-013 read their values from the engine with
  unchanged findings, JSON carries the vector with numerators and denominators, and each
  measurement's population and exclusions are documented in `docs/`.

- [ ] **QUALITY-BASELINE and QUALITY-TRENDS: one snapshot format, two uses.** A snapshot holds:
  - one run's measurement vector;
  - for every coverage measure, the sorted IRIs in its numerator and denominator;
  - the measurement definition versions and the policy that shaped each population.

  A *quality baseline* is a snapshot committed to the repository: the accepted values. It is
  distinct from `--baseline`, which suppresses findings by fingerprint, and gets a different flag
  name so the two never mix. A *trend* compares two snapshot files. ontolint does not walk git
  history; CI keeps the snapshots as artifacts. The comparison must tell a regression from a
  denominator change, which aggregates cannot do: adding 1,000 classes without definitions lowers
  definition coverage while the number of documented classes rises. With the term sets, a coverage
  change splits into four counts, each reported with the ratio delta:
  - terms that lost the property: the real regression;
  - new terms without it: dilution;
  - removed terms;
  - terms that gained it.

  A renamed term counts as one removal plus one new term until COMP's rename detection exists; the
  report says so. Measurements whose definition version or population differs between the two
  snapshots are reported as not comparable, each one separately, never silently diffed. This needs
  no COMP ADR, because it compares measurements, not graphs. *Done when:* a fixture pair with a
  regression, a dilution and a removal is classified correctly, a snapshot round-trips, and an
  incompatible pair is refused measurement by measurement.

- [ ] **DQV-REPORT: the measurements as W3C DQV.** One `dqv:QualityMeasurement` per value, with
  `dqv:isMeasurementOf` a `dqv:Metric`, `dqv:computedOn` the ontology (its version IRI when it has
  one), a typed `dqv:value`, and `prov:wasGeneratedBy` the run (tool and catalogue versions).
  Decide first:
  - the IRIs of ontolint's metric definitions. Use a namespace the project commits to keep, or
    `urn:` if it will host none; a `w3id.org` redirect is a promise to maintain;
  - whether findings are published too, as `dqv:QualityAnnotation`. Start without them.

  The output is deterministic: serialisation is sorted, and a timestamp appears only when
  `SOURCE_DATE_EPOCH` or a flag supplies one. Name the consumer (a DCAT catalogue or FAIR
  assessment that reads DQV) before calling this done. *Done when:* the output parses, lints clean
  with ontolint's own rules, is byte-stable across runs, and the namespace decision is recorded.

- [ ] **MARKDOWN-SUMMARY: a human-readable pull-request summary.** It shows:
  - counts per severity, and new findings against baselined ones;
  - the rules that delivered no verdict, which cause exit 2 (OPS018);
  - with a quality baseline, the measurement deltas split as above;
  - the first findings, with a pointer to the full SARIF.

  Messages quote ontology literals, so the renderer escapes Markdown and HTML (a label must not
  become a link, an image or an `@` mention in a pull request) and caps its size, since GitHub's
  step summary has a size limit. This is the consumer that OPS012's deferral asked for, for
  Markdown only. *Done when:* escaping is property-tested against hostile labels and the output is
  deterministic.

- [ ] **GITHUB-ACTION: a maintained, version-pinned Action.** This replaces the P2 ADR on
  `--format github` by answering its question: SARIF upload for annotations, which workflow
  commands cap, plus MARKDOWN-SUMMARY in `$GITHUB_STEP_SUMMARY`. A native annotation formatter
  comes only if a user without code scanning asks for one. `action.yml` sits at the repository
  root, so `uses: arnaudgelas/ontolint@vX.Y.Z` pins the Action and the ontolint it installs to one
  release: from PyPI, by exact version with hashes, never the latest. Code scanning ignores SARIF
  property bags, so `properties.evidence` does not reach its UI, and results with one message on
  one location may be shown as one (there are no `partialFingerprints`); check both. The `tags`
  ruleset already protects that tag. Decide:
  - whether SARIF upload is the Action's job, which needs `security-events: write`, or the
    caller's;
  - whether the ROBOT image is in scope. It is not at first.

  The release instructions gain a step that proves the Action at the new tag. `src/ontolint/github.py`
  then either serves it or goes (see "Documentation debt"). *Done when:* a workflow in this
  repository uses the Action at the released tag on a fixture, and its SARIF and its summary both
  appear.

- [ ] **DUPLICATE-ONTOLOGY-ID: one ontology IRI declared by two files.** Nothing checks this
  across files. A multi-file run lints each file alone, and `--import-dir` maps an IRI to the first
  file in path order (`imports.index_directory`, `entries.setdefault`) with no note when another
  file declares it too, so which copy is imported depends on file names (read in the code,
  2026-11-10). Report it, with both paths, in four places:
  - across the inputs of one run;
  - within one `--import-dir`;
  - within a closure, when two modules carry one ontology IRI;
  - between the named graphs of a dataset (`datasets.GraphIndex` and `datasets.graph_name`, from
    DATASET-PROVENANCE).

  Report a version IRI shared by files with different content the same way. This needs a set-level
  rule scope, since rules run per file today, and a catalogue row. An identical copy (same content
  hash) is a note, not a warning. *Done when:* each of the four cases has a fixture, and
  `--import-dir` with two candidates names both and says which it chose.

## P2 — platform reliability and useful integration

- [ ] **QUALITY-BUDGET: explicit thresholds over measurements.** The proposed shape, not yet a
  syntax: a `quality_budgets` policy key mapping measurement names to `minimum`/`maximum` (for
  example `definition_coverage: {minimum: 0.95}`, `unresolved_imports: {maximum: 0}`). Two kinds
  of bound:
  - absolute bounds on a measurement;
  - against a quality baseline, bounds on the classified deltas: `lost: 0` for terms losing a
    definition, a minimum coverage among new terms. Never a bound on the raw ratio delta, which a
    denominator change moves.

  Keep one threshold mechanism: METRIC001-013's policy keys become built-in budgets (the old keys
  stay as aliases), not a second, competing setting. There are no default budgets, so the
  metric-calibration item does not block this one. Outcomes:
  - a breach is a finding of one new rule, at its severity, baselinable like any other;
  - a budget on a measurement that was not taken is exit 2, never a pass;
  - an unknown measurement name is a configuration error (GOV020).

  Budgets on `new_unsatisfiable_classes`, `competency_question_pass_rate` and
  `unreviewed_equivalence_mappings` wait for the SEM, CQ and ALIGN gates. *Done when:* the absolute
  and delta bounds each have a passing and a failing fixture, the METRIC aliases leave
  `differential.json` unchanged, and an untaken measurement exits 2.

- [ ] **CTRF-REPORT: a CI test-result format.** This is OPS012 with a consumer: choose CTRF or
  JUnit, not both. The mapping is the design: one test per (file, rule), `passed`, `failed` when it
  has a gating finding, `skipped`, and `other` for a `failed` or `unsupported` execution, so an
  infrastructure failure never reads as a failed test or as a pass. Durations need OPS011's opt-in
  timing. *Done when:* every execution status has a fixture and the report validates against the
  CTRF schema, vendored with its checksum as the SARIF schema is.

- [ ] **Measure the blank-node identities SHACL with a background computes.**
  `engine._shacl_with_background` computes a content-digest identity (`stable_blank_id`) for every
  blank node the linted file mentions, in order to keep results whose foci are usually few. Time it
  on a blank-node-heavy OWL file, where restrictions make up most of a TBox; if it matters, compute
  identities only for the blank foci of the results.

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

- [ ] **OPS006, OPS001, OPS011 and OPS018: version reports before enriching them.** Catalogue
  identity, per-rule counts, optional timing and a fuller explanation of exit code 2 (today the
  failed and unsupported rules are listed, but not why the run as a whole exited 2) are useful only
  with a clear compatibility contract. Publish
  a versioned JSON/SARIF extension policy first; timing must be opt-in and must not perturb default
  deterministic output. JSON's `schema_version` is 1 with no schema behind it: publish a JSON
  Schema for the JSON report (with `measurements` once METRICS-ENGINE lands) and validate every
  report shape against it, as `tests/test_sarif_schema.py` does for SARIF.
  *Done when:* report consumers can identify the catalogue and schema version, obtain deterministic
  per-rule counts, and request timing without changing default output, and every JSON report shape
  validates against the published schema.

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
  sets. An empty expected set is a legitimate answer, and a question with no expectation is CQ007
  (no oracle), never CQ003 (unexpected empty result). Compare answers after normalising literals
  (`"01"^^xsd:integer` and `"1"^^xsd:integer` are one value) and blank nodes; order matters only
  under `ORDER BY`. Queries run as a task of the bounded worker (`ontolint.worker.run_bounded`,
  built for SHACL validation), since rdflib's SPARQL has no timeout of its own. *Gate:* accepted format and at least one public corpus that justifies
  maintaining it.
- [ ] **Reasoner-backed semantics (`SEM*`).** Define supported reasoners/profiles, Docker versus
  local dependency model, reproducibility, timeout/failure behavior, and CI image ownership.
  *Gate:* accepted adapter contract and deterministic container fixtures. Recommended as the first
  bet (2026-11-10, after an external review ranked semantic verification, version comparison and
  competency questions as the three gaps that matter most): it is the cheapest, because the
  isolated ROBOT image, its adapter and the CI job that builds it already exist (`robot reason`
  and `explain` give consistency, unsatisfiable classes and justifications), and it is a
  prerequisite of the others' semantic rules (COMP016, COMP017, ALIGN010). Its adapter contract is
  the SEM001 fix of 0.10.2 generalised: a verdict only from a parsed report, every other outcome
  `failed`, `unsupported` or a timeout. Keep OWL *profile* compliance (SEM001) and *consistency*
  (SEM002, SEM003) as separate rules and say so in the README; a profile pass proves nothing about
  consistency, and ELK (EL only) must not report "consistent" for an ontology outside EL. The
  adapter's acceptance cases, each with its own expected rule and execution status, not just "some
  finding": an unsatisfiable class in an otherwise consistent ontology (SEM003), an inconsistent
  ontology (SEM002), an ontology outside the reasoner's profile (`unsupported`), malformed input,
  a crashed Java process and a timeout (all `failed`). `robot reason` exits non-zero on an
  inconsistent ontology, which is exactly the trap SEM001 fell into before 0.10.2.
- [ ] **Policy packs and domain profiles.** The `obo` and `fair` opt-in families and profiles
  already exist, so this gate covers only what they do not: externally authored, versioned packs.
  Define profile ownership, rule-selection/override
  precedence, versioning, and how a pack is validated without weakening the core policy model.
  Each pack, and each built-in profile, states the kind of ontology it is for (an OWL TBox,
  instance data, a SKOS vocabulary, a SHACL-first graph) and which rules it leaves out as
  inapplicable there, so a SKOS thesaurus is not judged by OWL modelling conventions.
  *Gate:* accepted pack format and two independently useful example profiles.
- [ ] **Mapping and alignment (`ALIGN*`, 4 rules).** They need a mapping registry (SSSOM files or
  similar) as a second input. *Gate:* accepted input format; can share the two-input CLI design
  with `COMP*`, so decide them together. Semantics are relation-specific: `owl:equivalentClass` is
  a logical axiom, `skos:exactMatch` and `skos:closeMatch` are not, and ALIGN010 must not reason
  over SKOS links as if they were equivalences. ALIGN011 (dissimilar labels) stays an advisory
  heuristic, because translated, abbreviated or historical labels differ on legitimate mappings.
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
- **More report formats (OPS012):** do not create JUnit or HTML outputs without an identified
  consumer. JSON and SARIF are the integration contracts to keep sound first. Markdown now has its
  consumer (MARKDOWN-SUMMARY, P1) and a CI test format is CTRF-REPORT (P2), which takes JUnit's
  place.
- **Automatic fixes (`--fix`):** defer until findings carry structured evidence (SHACL001 does,
  unreleased, and every finding names its subject for its baseline identity); only
  round-trip-verified, meaning-preserving edits would ever qualify, and modelling or logical corrections (deleting an
  axiom that causes an inconsistency) never.
- **Editor integration (a language server):** defer until source regions are exact for the
  formats it would serve; today they locate a term's occurrence, not the offending axiom.
- **A single quality score, and AI-generated suggestions presented as checks:** rejected. A score
  hides which dimension failed; generated text is not a deterministic verdict. The quality
  observability items publish the vector of measurements and explicit budgets instead.
- **Bulk implementation of proposed rules:** each needs an approved specification, positive and
  negative fixtures, expected confidence/severity, and an identified backend. A count of proposed
  rules is not a delivery plan.

## Documentation debt to close with the affected work

- [ ] Correct stale source comments: `src/ontolint/github.py` says findings "carry no source
  locations" (false since 0.3.0) and the module has no caller outside its own test until a
  formatter exists. Either make it earn its place in GITHUB-ACTION (P1) or delete it.
- [ ] Keep README, release instructions, policy schema, and report examples in the same change as
  any CLI/report-contract modification. Documentation-only corrections do not need a feature
  release, but behavior changes do.

## Questions retired from remaining-work.md

Each was an open question in the old local backlog and no longer is. Listed so they are not asked
again.

- **External review of 2026-11-10 (written against 0.8.0):** its confirmed defects were fixed in
  0.10.2 or are in P1, its product ranking informs "Decision gates". Claims checked and not taken up:
  the catalog is already read bounded (`imports._catalog_bytes` reads at most `max_bytes + 1`,
  SEC001, since 0.9.0); `--explain RULE`, `--list-rules --format json` and per-rule execution
  status with exit `2` for a failed or unsupported rule already exist, which is the "incomplete
  analysis" signal it asks for (what was missing is that SEM001 bypassed it, fixed in 0.10.2);
  SHACL severities are already kept (`sh:Warning` is `warning`); selecting one rule still runs its
  module and filters, which costs time, not correctness, and is left until profiling says
  otherwise; the process-wide socket block is defence in depth around a single-process CLI, and
  parsing moves to a worker process with `--max-parse-seconds`. Its proposed CLI subcommands and
  evidence model are design input for the COMP ADR and the P1 SHACL item, not tasks of their own.
  Its fuller version (same date and target) was rechecked against 0.10.2 on 2026-11-10. Taken up
  from it: SHACL validation has no time budget (reproduced; P1), named-graph provenance
  (DATASET-PROVENANCE, P0), the single-file and multi-file fingerprint split (BASELINE-V2,
  unreleased), a JSON Schema for the JSON report (OPS item, P2), the blank-node identity
  cost (P2), and acceptance cases for the SEM, CQ, ALIGN and policy-pack gates. Checked and not
  taken up:
  - metamorphic tests exist: `test_properties_lint.py` covers triple order, blank-node labels,
    the base IRI and the hash seed, and worker and in-process parses agree;
  - configuration is validated (OPS008, GOV020), and import cycles terminate;
  - its "rule-quality dashboard" is the corpus-count and metric-calibration items;
  - its "execution manifest" is the per-rule `executions` plus exit 2;
  - a language server, `--fix`, caching and changed-line filtering stay deferred, for the reasons
    under "Explicitly deferred".

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

