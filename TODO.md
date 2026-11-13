# TODO — delivery roadmap

This is a prioritised delivery plan, not a catalogue of attractive ideas. Its purpose is to make
ontolint safe to run in CI and trustworthy when it reports a result. The rule catalogue remains
[`docs/rules.md`](docs/rules.md) and `src/ontolint/data/rule_catalogue.csv`; do not duplicate its
individual rule backlog here.

**Hotfix** ships on its own, as soon as it is done, and is blocked by nothing else below. `P0`
blocks the feature release after 0.11.0 (which shipped with the Renovate item open, see it). `P1` is the next milestone after P0. `P2`
is worthwhile only after the preceding work is complete. “Decision gate” means no implementation starts until the
stated decision is accepted. Re-audit external-service assertions (GitHub settings, Action history
and PyPI state) when starting the item; they do not belong in a permanent source-controlled fact
record.

## Hotfix

Nothing open: 0.11.0 is released (see "Recently done").

## Recently done

- Unreleased (after 0.13.1):
  - **LEGAL-PROVENANCE** (P1; issue 18): the maintainer's answers are written down. `NOTICE` names
    the copyright holder (Copyright 2026 Arnaud Gelas, the `pyproject.toml` author; 2026 is the
    first commit's year) and ships with `LICENSE` in the sdist and in the wheel's
    `dist-info/licenses/` (`license-files`, pinned by `tests/test_cli_install.py`). `LICENSE` stays
    the verbatim licence text, as the ASF does, so its appendix placeholder is not filled in. The
    README's License section records the logo's origin: an AI image generator (which one is not
    recorded), added by the maintainer in `84045cc`; it does not ship in either distribution.
    Checked again: no vendored third-party code, so `NOTICE` carries no attributions (the
    crosswalks' sources, answered on 2026-11-09, stay in `data/README.md`: identifiers and short
    smell names only, no copied text; no dependency is copyleft beyond file-level MPL-2.0; the
    ROBOT jar is downloaded at image build with a pinned checksum).
  - **JACKSON-LAYOUT** (P1; issue #7): source regions are confirmed on JSON-LD that a Java tool
    wrote. `tests/fixtures/java_jsonld/` holds `pets.ttl` and its two exports by Apache Jena 4.10.0's
    `riot` (Java 11): `--formatted=JSONLD10` (jsonld-java 0.13.4, printed by Jackson 2.15.3's
    `DefaultPrettyPrinter`: `"@id" : "…"`, `[ {`, `}, {`, `@context` last) and `--formatted=JSONLD`
    (the 1.1 writer: `"@id": "…"`, compact IRIs such as `xsd:nonNegativeInteger`). The fixture's
    README gives the distribution's SHA-512 and the commands. No code changed: the locator already
    skips whitespace before `:` (the synthetic `space-before-colon` regression case). New tests: each
    fixture keeps its committed SHA-256 and its writer's layout (separator, indent unit, Jackson's
    `[ {` and `}, {`) and parses to the graph of `pets.ttl`; every IRI subject is located at an `@id`
    string that names it; every finding has the same rule and message as the Turtle source and a
    region at its focus.
    - Verified: with whitespace before `:` no longer skipped, the two tests on the Jackson file fail
      (the 1.1 file still passes, as it should); the 14 findings of each export equal the Turtle
      source's.
    - Left open: none. Neither writer is deterministic (1.0 orders its `@context` members, 1.1 its
      `@graph` nodes, differently between runs), so a regeneration passes the layout and graph tests
      but needs a new digest; that the committed bytes came from `riot` rests on the README.
- Unreleased (after 0.12.0):
  - **PREDICATE-CLOSURE** (P1 audit, issue 15; the LEX002-CLOSURE follow-ups): one cached
    `PropertyClosure` (`rules/runtime.py`) indexes the graph's `rdfs:subPropertyOf` and
    `owl:equivalentProperty` triples once; `below(seeds, stop)` is the seeds, then every IRI with a
    path to a seed whose steps are sub-to-super or equivalence (either way), through no stop node,
    sorted. Asserted triples of the linted graph only (the merged closure under
    `--follow-imports`, so an imported vocabulary's axioms count; the SHACL background is not read);
    a seed is never stopped; deprecation changes nothing; blank nodes carry a path but are never
    returned; each walk expands each node once, so cycles end it and its cost is linear (a scaling
    test).
    - *Labels:* `ctx.labels` is the closure of `rdfs:label`, `skos:prefLabel` and
      `extra_label_predicates`, stopping at `skos:altLabel` and `skos:hiddenLabel` (the SKOS schema
      puts them below `rdfs:label`). It decides whether a term has a label (LEX001 and METRIC001,
      still the same set; SKOS004; CLS015; an index entry's names for LIB001 and LIB002) and which
      values are judged as labels (LEX005, LEX010-LEX014, LEX017, LEX018, LEX021, LEX022,
      METRIC009); any label in a language satisfies LEX008. The rules comparing labels (LEX003,
      LEX004, LEX006, LEX015, LEX016, CLS010) read `ctx.main_label_predicates(term)`: the
      configured predicates and those below `skos:prefLabel` (`ctx.preferred_labels`, preferred
      labels by entailment) when the term has a literal under one, else the whole closure.
      Closing them over sub-properties of `rdfs:label` reported LEX003 and LEX006 on all 35
      classes of BFO 2020, whose untagged OWL and CLIF specification labels (`BFO_0000179`,
      `BFO_0000180`) are below `rdfs:label`; not closing them made LEX008 report "no preferred
      label" on a term LEX001 called labelled, and a per-term fallback let an `@fr` `rdfs:label`
      hide an `@en` preferred label. An IRI-valued label is still no label (LEX013 reports it).
    - *Equivalences:* `ctx.descriptions` (and `ctx.labels`) follow `owl:equivalentProperty` both
      ways and mixed with sub-properties (`p ≡ q ⊑ skos:definition`, `p ⊑ q ≡ obo:IAO_0000115`); an
      equivalent of a super-property of a definition predicate, or of `rdfs:label` or
      `rdfs:seeAlso`, is no definition.
    - *Notes:* LEX002 accepts the closure of `skos:note` and `skos:scopeNote`, stopping at
      `skos:changeNote`, `skos:editorialNote`, `skos:historyNote` and `skos:example`, which the SKOS
      schema puts below `skos:note` but which did not document a term in 0.12.0 either; a note is
      still no definition to the other rules (METRIC002, LEX017, LEX019). LEX002 does not judge
      what a note says, so a non-descriptive sub-property of `skos:note` (a display order)
      documents a term, as a bare `skos:note "3"` did already. A sub-property of `rdfs:comment` is
      a definition, as since 0.11.0, and never a label. OBO's `DEFINITION_PREDICATES` stay
      IAO-only: neither a sub-property nor an equivalent of `obo:IAO_0000115` satisfies OBO003.
    - *Verified:* `tests/test_predicate_closure.py`, rule cases for LEX001, LEX002, LEX003,
      LEX018, METRIC001 and METRIC002, a Hypothesis property against a fixed-point oracle over
      mixed edges and stop sets, and a linear-scaling test. Golden files, `differential.json`, the
      report schemas, fingerprints and `docs/rules.md` did not move. On real ontologies (CCO, MOD,
      SDO, Tractus-X, SKOS, FOAF, DCMI terms, Getty GVP, QUDT, PROV-O, DCAT, BFO 2020, RO, IAO,
      OMO) the findings are identical to 0.12.0: their label and definition sub-properties
      (`foaf:name`, `schema:name`, `dcterms:title` in MOD, BFO's specification labels) sit on
      terms the files do not own or beside an `rdfs:label`, and Getty's `gvp:prefLabelGVP` is an
      object property to SKOS-XL labels with no `rdfs:subPropertyOf`. The label closure is driven
      by issue 15 and by what the axioms entail, not by a false positive observed in the corpus.
  - **USERINFO-MASK** (P1 audit; issue 13): no output repeats an IRI's userinfo. The
    specification is `src/ontolint/redaction.py`: one structural parser finds a userinfo (an
    authority runs to the first `/ ? #` whatever its characters, the userinfo to its last `@`, with
    WHATWG's `https:/` and `https:` forms for special schemes) for masking and for SEC014, which
    reports exactly the passwords the mask hides; the scan is linear. The whole userinfo, user name
    included, becomes `****` (`https://****@host/x`). *Maintainer decision to confirm:* the user
    name is masked too, because a token sent as the user name (`https://<token>:x-oauth-basic@...`,
    `https://<token>@...`) cannot be told from a name. Masking happens where a finding is made
    (`Finding.__post_init__`, and `RuleContext.add` before duplicates are removed), before a message
    cuts a value (`redaction.clip`, enforced by a test over every slice in `rules/` and
    `adapters/`), and in the content hash of blank nodes and blank graphs, so no output holds a
    hash over a secret; stdout and stderr (the workers' too) are masked again at the boundary, and
    a parser message about a file with a userinfo is withheld. Shipped as `fix!:` with a BREAKING
    CHANGE trailer. Limits, documented in the README: a baseline cannot tell a replaced credential
    at the same IRI from the old one (no output may hold an offline-guessable function of it), a
    write straight to file descriptor 2, a library caller's own logging handlers. Follow-ups:
    issue drafts for a user-only userinfo (`https://<token>@host`, masked but not reported), SEC014
    under a baseline, and line breaks in IRIs that forge text-report lines.
  - **SHQ-SPEC** (P1 audit item, issue #11, branch `docs/11-shq-specification-audit`): SHQ001-SHQ027 are
    specified in the format of the OWL family in the docstrings of `rules/shapes.py`,
    `rules/shacl_quality.py` and `rules/shacl_authoring.py` (scope, condition with the SHACL, XSD and
    F&O sections, exclusions, severity and confidence rationale, fixtures), and the catalogue rows name
    their fixtures (the eight "pySHACL and RDFLib graph" backends, which never used pySHACL, now say
    "RDFLib graph"). Fixed where the code contradicted SHACL (each pinned by
    `tests/test_shq_specification.py`, 57 cases failing on 0.12.0): SHQ001/SHQ002 judged a literal
    `sh:property` value; SHQ003 counted 9 of the constraint parameters (it now counts every SHACL Core
    one, `sh:qualifiedValueShape` only with a qualified count, `sh:closed` and `sh:uniqueLang` unless
    false, and no deactivated shape); SHQ006 ignored a target on a superclass (SHACL instances follow
    `rdfs:subClassOf`); SHQ010 rejected the `*` range and accepted non-`xsd:string` members; SHQ011
    reported valid class subtractions and quantified anchors as compile errors, compiled no pattern with
    `\p`, `\i` or `\c`, accepted `[[a]`, `[]a]`, `\p{Letter}` and a class left open after a subtraction
    (`[a-z-[aeiou]`), and read every digit after a back-reference as part of it (`(a)\10` reported,
    `\123` accepted); SHQ021 ignored SHACL-AF `sh:target`; SHQ023 ignored untyped subjects of two
    `sh:path`s; SHQ024 ignored `rdf:type` as a property shape's path. Messages are unchanged except
    SHQ011's on a pattern the rewrite for Python touches (`\p`, `\i`, `\c`, a subtraction, a quantified
    anchor, a digit after a back-reference) or that also has a newly reported error: Python's error may
    now come first, or lose its position; a v1 baseline entry for such a finding stops matching, a v2
    one does not. Only the `--explain SHQ001` golden moved. Measured on 1,079 public shapes files (W3C
    SHACL test suites, DCAT-AP 3, IDS, GeoSPARQL): SHQ003 +884 -3 (info: `sh:nodeKind` mostly; the 3 are
    deactivated shapes), SHQ006 -3, SHQ021 -5, nothing else. Left to the maintainer: approve the
    specifications, and the severity and confidence proposals of the PR (none applied: the #12 counts on
    CCO, BFO, RO and DCAT-AP found no SHQ008 or SHQ011 finding, so they rest on the specifications
    alone).
- Unreleased (on `main`, after 0.11.0):
  - **TRIG-REGIONS** (P1; issue 6): a TriG finding has the region of its focus, as its Turtle
    twin does. TriG was missing from `source_locations._TEXT_FORMATS` and from the scanner's
    prefixed-name and directive cases, an oversight: graph blocks need no tokenising (`{`, `}` and
    `GRAPH` start no term, as N3's braces do not). A term in two graphs, and a graph name that is
    also a node, is located at its first spelling, as in N-Quads and JSON-LD. The scan now skips a
    run of name characters whole, so a long word outside strings (a language tag) costs linear
    time instead of quadratic, in Turtle as in TriG.
    - Verified: unit tests, a Turtle-twin SARIF test on both TriG fixtures, a linearity test, and the
      region property test, now run once per syntax so each gets its own examples (drawn from one
      shared budget, TriG had two or three and the property missed the gap about one run in 20;
      now 0 passes in 40 runs on the unfixed locator). It writes TriG and N-Quads datasets, with a
      described graph name in half of them, and checks that every IRI subject of a text syntax has a
      region.
    - Left open (Turtle scanner, shared by TriG): prefixes come from the parsed graph's bindings,
      not the file's directives in source order, so a file's own `schema:` loses to rdflib's
      default binding and a prefix redefined mid-file takes its last namespace (both can give a
      wrong region); `@base` is skipped but never applied; a prefix with an inner `.` or a
      non-ASCII first letter is matched from its tail; `ex:B.` keeps the `.` in the name.
  - **Broken pipe** (P1 audit; issue 14): `ontolint ... | head` no longer ends in a traceback and
    exit 1 (a write that fails) or in the interpreter's shutdown warning and exit 120 (a short
    output left in the buffer). The report, `--version`, `--list-rules` and `--explain` write and
    flush through one function that notices the closed reader. A closed stdout ends the run
    quietly with exit 141 (128 plus SIGPIPE, as `cat`, `grep` and `git` end under a shell), after
    pointing the descriptor at the null device so the last flush has nothing to fail on.
    - Exit 2 keeps its place and its `TOOL001` lines, also when stderr closes after the report; a
      stderr that closes before the report ends the run with 141; a report that cannot be flushed
      for another reason (a full disk) is TOOL001 and exit 2; `--help` and usage errors keep
      argparse's codes; a `BrokenPipeError` raised inside the lint (a subprocess pipe) is still
      TOOL001 and exit 2.
    - Verified: 36 tests (real pipes with the reader closed before the run, a reader that stops
      after one line, and in-process streams of every awkward kind). The first 25 were written
      before the fix and 22 of them failed on 0.11.0; the other 3 guard what must not change.
      Real `| head -1` pipelines against the old and the new code: traceback and 1, or noise and
      120, before; 141 and an empty stderr after.
    - An independent review found three regressions in the first version (no stdout, a stdout
      without a working `flush`, the final flush replacing the outcome) and a gap in the
      exit-code precedence. All are fixed, and each is pinned by a test that fails without it.
    - Not verified: Windows, which reports a closed pipe as `OSError` (EINVAL); the tests skip
      there and the README says it is not handled.
  - **Test tooling and the metamorphic suite.** `pytest-randomly` shuffles the test order on every
    run and prints its seed (`-p randomly --randomly-seed=N` replays an order); the suite passed
    under three seeds with `-n auto`, and the mutation runs turn it off (`-p no:randomly`).
    `pytest-archon` pins the layering in `tests/test_architecture.py`: seven rules on direct imports,
    each shown to fail when a violating import is planted. Eight metamorphic families in
    `tests/test_metamorphic_*.py` assert relations whose outcome is known without an oracle:
    serialisation formats, Turtle noise, idempotence and locality, multi-file runs, policy
    monotonicity, baseline round trips, report-format consistency and renaming the owned namespace;
    each was shown to fail when its transformation was made wrong. They found one real defect (the
    TriG item in P1, pinned by a strict `xfail`). Weak spots: the baseline relation never reaches
    the case of findings that share an identity, and the renaming test discriminates an
    order-changing namespace only through its `@example`. Full gate: 6864 passed, 1 xfailed, 99.87%
    coverage.

- 0.11.0 (`1652fa7`, tag `v0.11.0`), released 2026-11-11: release run 42973303494 passed every job
  (the CodeQL gate, tests, build, publish to PyPI, and the install of the published release), and
  PyPI holds the wheel and the sdist (uploaded 06:45Z). The commits after `f7f3db4` were re-dated
  to 2026-11-10 21:37 to 2026-11-11 07:26 at the maintainer's request before they were pushed, so
  their hashes are not the ones the first drafts of this file cited. The upgrade notes are in
  `CHANGELOG.md`. Not checked, as said below: the rules that the real-world run never exercised.
  - **COVERAGE-GAPS** (P1 audit, "Coverage gaps"): the thirteen gaps that the 0.9.0 specification
    review wrote down as exclusions are closed with new messages in the existing rules, and every
    pinning negative case is now a positive one. OWL010 empty and malformed chains (`acc80b3`);
    OWL019 non-simplicity through sub-properties, equivalents, inverses and symmetry (`1fe1573`),
    and non-simple properties in cardinalities, `owl:hasSelf`, `owl:propertyDisjointWith` and
    `owl:AllDisjointProperties` (`84c8d5a`); OWL032/OWL033 on `owl:disjointUnionOf` (`bfd49e4`);
    OWL034-OWL036 for both `onProperty` and `onProperties`, several constraints, `hasSelf` not
    true and several fillers (`de5ea5f`); OWL037 across the qualified and unqualified groups
    (`d261d6a`); OWL040 with the non-XSD datatypes (`7db4770`); SHQ008 for derived integer
    types and for `sh:minLength`/`sh:maxLength` (`d34f2b0`); SHQ011 for XPath-invalid patterns
    Python accepts (`3c1c803`); ALIGN003 `relatedMatch` in an exactMatch chain (`8bcc7c0`); SKOS009
    through the mapping sub-properties (`b06b668`). The messages of these rules that existed before
    are unchanged, so these commits move no baseline; five rules were retitled, which moves `--list-rules`, and so
    `differential.json` and `single_graph_reports.json`, by the titles only (`a5ba578`, proof in
    the commit body and the `test_differential` docstring); `legacy_rules.json` did not move.
    Verified: the pinned positives were captured before the change (`86a33b9`) and still pass; a
    CLI test shows `--fail-on error` exiting 1 on small fixtures that exit 0 before (`3d2fec5`);
    the full gate passes. Outside the gap list, `04a7664` (`fix!:`, a BREAKING CHANGE that
    originates in the subject contract) reports SEC005 and SEC012 once per subject and predicate:
    where one predicate carries several literals, the message and so the fingerprint change, and
    0.10.x baseline entries for them go stale once. Whether it ships in this release is the
    maintainer's decision. Not done: the targeted mutation run was not repeated for these rules,
    and the real-world corpus was not available (see the open sub-bullets of the audit item).
    Two tests were hardened in passing: the dataset presentation-only property now skips
    examples that rdflib's Turtle writer does not serialise faithfully (a partial list node is
    folded into a collection), and one mypy annotation in `owl._property_chains`.
  - **POLICY-SILENT** (P1 audit, "Policy that silently does nothing"): every word of
    configuration now either changes the run or is refused. `--select` or `--ignore` naming only
    pipeline rules (`SEC001`, `SEC002`, `SEC003`, `SEC006`, `SEC009`, `SEC010`, `SEC011`,
    `SEC013`, `SEC015`, `INPUT001`, `TOOL001`, or the `INPUT` or `TOOL` family; the set is the
    registry's `backend` `cli`) is `TOOL001: configuration failed: PipelineSelectorError: ...`
    and exit 2, checked before any input is read and after the unknown-selector check (`fb48837`);
    the mixed `SEC` family still selects or ignores the six graph SEC rules. The same ids in the
    policy's `ignored_rules` or `severity_overrides` are `GOV020`, exit 2, in one line with any
    unknown ids (`c9e5eb1`). Both are `fix!:` with BREAKING CHANGE trailers; rejecting rather
    than warning was chosen, and a deprecation release would need only the raise in `cli._lint`
    turned into a warning. A file under `--import-dir` that the safe loader refuses is named on
    stderr once, as `TOOL010: warning: --import-dir <dir>: <file> is skipped, so no owl:imports
    resolves to it: <SEC rule>: <message>`, with the exit code and report unchanged; a file that
    does not parse and a `catalog-v001.xml` stay silent (`a68b321`). Verified: the item's
    reproductions (`--select SEC001` and `--select TOOL` exited 0 with no execution, `--ignore
    SEC001` and the policy entries were accepted, a refused mirror file left only an
    unexplained `SEC007`) now exit 2 with the line, or print `TOOL010` above the `SEC007`; the new
    tests fail on `fe10fb2` (32 CLI selector cases, 6 policy cases, 4 `TOOL010` cases, the flipped
    empty-run test) and pass after. Every pipeline id is rejected by both options, and an ignore of
    every other spec is accepted (parametrized over `RULE_SPECS`); a Hypothesis property checks
    that the guard rejects exactly the pipeline-only tokens and that every accepted token names an
    engine rule; no built-in profile names a pipeline rule; `engine.execute(ctx, ["SEC001"])`
    still records it as skipped. The legacy differential harness now ignores only engine rules;
    `legacy_rules.json`, `differential.json`, report schemas, fingerprints, baselines and
    `docs/rules.md` did not move. Targeted mutation run (`cli.py`, `imports.py`; non-slow suite):
    189 mutants, 178 killed, 4 pardoned (older), 1 error (a vanished pytest temp directory, in
    older `_import_options` code), 10 survivors: one in `index_directory`'s file filter, killed
    afterwards by a new test (`5038cb0`), and nine in older code (the TOOL005 hint, TOOL006,
    declared prefixes, `_library`, catalog parsing), left for the mutation-baseline item; none in
    the changed lines. `selection.py` is outside the mutation scope, so its helper is pinned by
    exact-message and property tests instead.
    Left open: `max_validation_seconds` without shapes stays documented as inert, without a note.
    (`--list-rules` marking pipeline rules `"selectable": true` was fixed afterwards, issue #16.)
  - **AUDIT-DEFECTS** (P1 audit, "Defects that change an exit code, a focus or a message"):
    a report that cannot be written to `--output` (missing directory, a directory, no
    permission) or encoded as UTF-8 (a lone surrogate in a text report, on `--output` or stdout)
    is `TOOL001: report output failed: <Type>: <message>` and exit 2, where it was a traceback and
    exit 1; the report is encoded before the file is opened, so the last good `--output` file is
    kept, and `cli._write_text(path, text, what=...)` is the helper later output files reuse.
    OWL034, OWL036 and OWL040 print values in one-line N-Triples (`"-1"^^<…#integer>`), bare IRIs
    and stable `_:` ids instead of Python reprs, through `rules.support.term_text` (rdflib's
    `n3()` except that a line break is escaped); so do OWL032 and OWL042-OWL045 for literal
    operands, and OWL013 for a literal with a line break. SEC014's focus masks the password
    (`https://alice:****@example.test/x`, RFC 3986 §3.2.1), its SARIF region is still the
    credentialed IRI's, and IRIs differing only in the password give one finding.
    Shipped as `fix!:` (three commits) with BREAKING CHANGE trailers: version 1 entries of the
    reworded OWL findings stop matching and version 2 entries keep matching; SEC014's v1 and v2
    entries both stop matching, and older baselines hashed the unmasked IRI, so rotate exposed
    credentials. Verified: every reproduction of the item (missing directory, directory,
    read-only directory, surrogate to file and to stdout, the item's OWL restrictions, a file with
    five credentialed IRIs) went from wrong to right and failed before the change; exit 2
    outranks `--fail-on never` and the output line precedes the broken-rule lines; a writable
    `--output` holds exactly what stdout prints. A static baseline written before the OWL change
    (`tests/fixtures/baselines/term_messages.baseline.json`) still suppresses every OWL finding
    with `--fail-on-stale-baseline`, while its version 1 list reopens them and SEC014 reopens
    under both. A contract test runs every rule case with all rules and fails on any Python repr
    in a focus or message (it failed on OWL034, OWL036 and OWL040 only), and a Hypothesis
    property checks the same over generated graphs; `term_text` parses back as Turtle. No SEC014
    text, JSON or SARIF report of Turtle, RDF/XML or JSON-LD input, and no baseline, contains the
    password; the region is the IRI's line in all three; a Hypothesis property checks masking
    (idempotent, reversible, identity without a password). `legacy_rules.json`,
    `differential.json`, the report schemas and policy did not move; `docs/rules.md` changed only
    in the OWL036 and OWL040 "Reported" lines. Targeted mutation run (`cli.py`, `rules/support.py`,
    `rules/safety.py`, `rules/owl_expressions.py`, `source_locations.py`; non-slow suite): 394
    mutants, 377 killed, 7 pardoned (older), 2 timeouts and 1 error (not named by the console
    report), 7 survivors, all in older `cli.py` code (the TOOL005 hint, `_file_modules`, declared
    prefixes, `_library`), left for the mutation-baseline item; none in the changed code.
    Left open, under the P1 audit item: credentials in other rules' output and SEC014's module
    placement (a broken pipe on stdout is fixed, see the first entry above).
  - **LEX002-CLOSURE** (P1 audit, false positives): `RuleContext.descriptions` now holds every
    IRI that reaches a definition predicate, built-in or from `extra_definition_predicates`,
    through one or more asserted `rdfs:subPropertyOf` triples (the merged closure under
    `--follow-imports`). The walk is iterative with a visited set, so cycles and self-loops end it
    and its cost is bounded by the sub-property triples `max_triples` caps; blank nodes carry a
    chain but are never added. Every reader inherits it: LEX002, LEX013, LEX017, LEX019, LEX020,
    LEX023, METRIC002, METRIC003, METRIC012, ONT006 and the TOOL005 hint. Shipped as `fix!:`,
    since METRIC002/METRIC003/METRIC012 counts (in their messages) move on ontologies with such
    chains: v1 baseline entries for them stop matching, v2 entries (`subject=()`) keep matching.
    Verified: the review's `ex:def2 ⊑ ex:def1 ⊑ skos:definition` example, chains of 2 and 5 links
    below `skos:definition`, `rdfs:comment` and `obo:IAO_0000115`, a two-cycle with a self-loop
    and a back-edge to a seed, a blank-node link, sub-properties of a configured extra, a chain
    declared only in an import, and the consumers (LEX013, LEX017, LEX019, ONT006, METRIC002,
    TOOL005) each went from wrong to right, and failed on the previous `runtime.py`; chains that
    never reach, or only rise above, a definition predicate, and broken chains, still report; a
    chain three times the recursion limit completes (rdflib's `transitive_subjects` raises
    `RecursionError` on one of a few thousand links); a Hypothesis property checks the result
    against a fixed-point oracle, its order (configured, then derived sorted by IRI) and
    insertion-order independence. A LEX002 negative rule case was appended, so `docs/rules.md`
    did not move; golden files, `differential.json`, fingerprints and baselines did not move.
    Targeted mutation run (`rules/runtime.py`, non-slow suite, at both fix commits): 25 mutants,
    23 killed, 2 pardoned, none surviving. Each commit passed Ruff and the tests on its own in a
    clean worktree. The README now lists the CCO 1.x definition among the built-in
    predicates. Follow-ups (labels, `owl:equivalentProperty`, SKOS notes) are recorded under the
    P1 audit item.
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
    whether POLICY-SILENT should note the key without shapes, where it has no effect (decided:
    no, it stays documented as inert, like `--robot-timeout` without `--owl-profile`).
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
    changes for an unchanged input (list each later rule here as it lands): METRIC002, METRIC003
    and METRIC012 counts (LEX002-CLOSURE); OWL034, OWL036 and OWL040, and OWL032 and
    OWL042-OWL045 with a literal operand, OWL013 with a line break in its literal, and SEC014's
    focus (AUDIT-DEFECTS).
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
    Left open: TriG had no SARIF regions (fixed afterwards, issue #6). By design, `(ontology)`
    foci (ONT001, ONT002) name no graph.

  - **METRIC-SPEC** (P1 audit and calibration items, 2026-11-11, `786662f`..`3fc5fb2`,
    follow-ups `8ad78a0` and `a91cf72`): METRIC001-METRIC013 are specified in the format
    of the OWL family in the `rules/metrics.py` docstring (scope, condition, exclusions, severity and
    confidence rationale, fixtures), and both catalogue CSVs name their fixtures. The code was corrected where it
    contradicted its own contract: METRIC001, METRIC005 and METRIC008 count what LEX001, CLS001,
    OWL005 and OWL006 report (shared helpers, pinned by hypothesis properties); METRIC006 and
    METRIC007 count only relation properties; METRIC010 ignores the ontology's own namespaces;
    METRIC013 treats SHACL shapes and reification as structure; a metric policy whose
    property-to-class minimum exceeds its maximum is rejected (TOOL001, exit 2); a message prints
    enough digits to tell its value from its limit. Thresholds, overrides and offline measurements
    are in `docs/metric-thresholds.md`. Verified: the review of an independent agent (no blocking
    defect; its should-fix items are fixed, one was a misreading: METRIC005 and CLS001 both exclude
    deprecated classes), every behaviour change probed on the CLI, no crash on an empty IRI, a blank
    node or an empty graph, and a clean full run at four intermediate commits. Left to the
    maintainer, and open in the items above: approve the specifications; decide severities and
    categories (METRIC001 and METRIC002 are warnings and fail `--profile ci`, `obo` and `fair`;
    METRIC011 reports `certain` with a `heuristic` category); calibrate the defaults on a licensed,
    pinned, labelled corpus (they are still first estimates, and the figures in the page are
    unpinned); decide whether CLS001 should read `dcam:domainIncludes`.
  - **Tests and verification of 0.11.0.** Thirteen `tests/test_coverage_*.py` files close every
    uncovered line outside `rules/owl.py` that can be reached (three branches are dead code:
    `graph/algorithms.py` 58-64, `shacl_authoring.py` 537-538 and `rules/literals.py` 122, which
    only a direct call reaches). The scaling tests take the best of five timings, because under load
    they failed once in about four runs. Two METRIC tests were repaired: a helper passed its base
    IRI as the shapes graph, and a property test compared an empty IRI with `str(term)` where a
    finding says `<>`. Full gate at the release commit, then: 0.10.2 and this code were run on 7
    public repositories (about 2,150 files, five profiles, `--follow-imports`, a SHACL pass of an
    own shapes file): exit codes identical on every file, no traceback, no timeout, no run over 1.5
    times slower, and only METRIC005, METRIC006 and METRIC008 moved, all as documented above.
    *Not verified:* OWL010, OWL019, OWL032/OWL033, SHQ008, SHQ011, SHQ015, LEX002, SEC005/SEC012,
    ALIGN003, SKOS009 and the SHACL evidence never fired on that corpus (it holds none of the
    constructs), so their fixes are proven by their tests only. `--owl-profile DL` fails on the
    modules whose imports cannot be loaded, in 0.10.2 and in this code alike. A full-corpus DL pass
    was too slow and was not run.

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

## P0 — before the next feature release

- [ ] **Turn Renovate on, and watch its first rebase.** *Flag (2026-11-11): P0 blocked 0.11.0, but nothing in
  the repository could close this item, so 0.11.0 shipped with it open.* Issue #4. In the repository
  (done on branch `ci/4-one-renovate-config`, 2026-11-11): one configuration is left, `renovate.json`
  at the root (Renovate reads it before `.github/renovate.json`, which is deleted). It automerges,
  with the rebase strategy, minor and patch updates of the `dev` dependency group and minor, patch
  and digest updates of the digest-pinned GitHub Actions, each three days after release, plus the
  monthly `uv.lock` maintenance; majors, `[project.dependencies]` (rdflib, pyshacl), the PyPI
  publish action, uv and the Docker images are never automerged. `"platformAutomerge": false`, because the `main` ruleset
  requires no status check (only no deletion, linear history and no force-push), so GitHub's own
  automerge could merge before CI ran; Renovate merges itself only when every check on the branch is
  green. The dev-group matcher was dead: `managerData.depGroup == 'dev'` is not JSONata (`=` is its
  equality), so the rule never matched and `renovate-config-validator` rejects it. Checked against
  Renovate 44's published schema with `jsonschema`; Renovate itself was not run. What is left, for
  the maintainer: run `npx --yes --package renovate@41 -- renovate-config-validator --strict
  renovate.json`; confirm the repository allows rebase merging; check that the Renovate app
  installation includes this repository ("Only select repositories") and that it is enabled in the
  Mend developer portal (the maintainer enabled the app on 2026-11-09 and it has opened no branch,
  pull request or Dependency Dashboard issue since; a token without app scope cannot list the
  installations). The release boundary is in place and proven (2026-11-09): release runs wait at
  "Publish to PyPI" for the maintainer's approval, and the throwaway tag `ruleset-probe-2026-11-09`
  could be neither force-moved nor deleted. The `main` ruleset targets the default branch only, so
  Renovate's own branches are not restricted, and a rebase automerge satisfies its linear-history
  rule. Then watch one rebase of a Renovate branch and one automerge. The `tags` ruleset's "linear
  history" rule means nothing for tags and can go (approved 2026-11-10; the token used here has no
  admin right on the repository, so remove it in Settings → Rules → `tags`). *Done when:* both are
  observed once.

## Real-world ontologies — decisions and the validation corpus

Everything here comes from linting fifteen public ontologies on 2026-11-09 (sources in the corpus
table at the end of this section). Each item names the files that show it; every fix gets a small
synthetic fixture copying the pattern, and the real repositories are only used for validation runs.
Nothing is open here as of 2026-11-10: what remains is the decisions
below, so that the next audit does not reopen them, and the corpus.

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
    built for 0.10.0. Left for later, only if asked: a
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

- [ ] **TriG with an unlabelled default graph is read as JSON-LD.** Reproduced on 0.11.0
  (2026-11-11), found by the metamorphic suite: a file `x.trig` holding
  `{ <https://example.test/onto#A> a <https://example.test/onto#B> . }`, valid TriG (rdflib's
  writer emits exactly this when no prefix is declared), fails with `INPUT001: RDF input parsing
  failed: JSONDecodeError` and exit 2. `syntax.sniff` returns `json-ld` for any text that starts
  with `{`, and the `.trig` extension does not override it. A file the extension names should be
  parsed as that syntax, and the sniffer should look past `{` (JSON-LD has a quoted key or `@`
  next, TriG a term or `}`). *Done when:* the reproduction lints, and the strict `xfail` in
  `tests/test_metamorphic_serialization.py` is removed because it now passes.

- [x] **Source regions: confirm one real-world JSON-LD layout.** Confirmed (issue #7, see "Recently
  done", JACKSON-LAYOUT): Jena 4.10.0's JSON-LD 1.0 writer (jsonld-java, printed by Jackson) writes
  `"key" : value`, and every finding of that export has a region at its focus. Both Jena exports
  are fixtures in `tests/fixtures/java_jsonld/`.

- [ ] **Calibrate metric thresholds before treating them as universal policy.** Existing `METRIC*`
  ratio defaults are first estimates, even where configuration already exists. Assemble a small,
  licensed corpus of ontologies with known-good and known-poor outcomes; measure false positives and
  false negatives before changing defaults or exposing additional knobs.
  The rationale and override behaviour of every threshold are recorded in `docs/metric-thresholds.md`
  (0.11.0). The pinned corpus exists (issue #8, 2026-11-13): 21 licensed files in
  `docs/validation/metric-corpus.json`, measured by `scripts/metric_corpus.py`, results and counts
  in `docs/validation/metric-calibration.md`, one corpus column per threshold. Under the *proposed*
  labels METRIC001-003 have no false positive or negative; the 12 false positives of METRIC005,
  006, 008, 009, 010 and 011 each come from a modelling choice the rule does not see (restrictions,
  `dcam:`, upper-ontology alignment, own-module imports, untagged-by-convention labels), so no
  default changed. Left to the maintainer: approve or correct the labels (`label_status`), decide
  the three left open, and the severity, confidence and CLS001 questions of the METRIC-SPEC entry;
  known-poor files are still missing for METRIC004, 005 and 007-013 (recall unmeasured).
  *Done when:* every metric threshold records its rationale, corpus results, and override behavior;
  any changed default has regression fixtures demonstrating the intended boundary.

- [ ] **SHACL001 evidence: what is left to the maintainer.** The evidence itself is done
  (0.11.0, see "Recently done"). Three choices were left out because each changes a contract:
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
  (0.11.0, see "Recently done"). Left open, each a decision rather than code:
  - *Release sequencing.* Baselines written by 0.10.x hold version 1 hashes only, so a message
    fix shipped in the same release as identity v2 still breaks those entries once. Recommended:
    ship v2 in release N, with the upgrade note "regenerate the baseline once", and the message
    fixes (OWL034, OWL036, OWL040, SEC014's focus, METRIC rounding) in N+1. Bundling them, as the
    0.10.0 entry hoped, is the maintainer's call. The OWL and SEC014 fixes are now on `main`
    (AUDIT-DEFECTS, from `77b8f84`), after LEX002-CLOSURE's METRIC change; splitting means
    releasing v2 from a commit before those. SEC014's focus change breaks both hashes by design
    (the focus is part of the identity); its `fix!:` commit's BREAKING CHANGE trailer says so.
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
  METRIC families. Specify
  scope, formal condition, exclusions, confidence/severity rationale, and positive and negative
  fixtures; correct documentation or implementation when they disagree.
  *Done when:* each implemented rule has an approved, testable specification and its catalogue,
  user documentation, and fixtures state the same contract.
  The specifications of every error-severity rule, the whole OWL family, the METRIC family
  (0.11.0, see "Recently done", METRIC-SPEC) and the SHQ family (v0.13.0, issue #11, see "Recently
  done", SHQ-SPEC) await the maintainer's approval. Next: the SKOS, CLS, LEX and IRI families. Left
  open by those reviews:
  - *Severity and confidence, the maintainer's decision* (changing either moves baselines and
    `--fail-on` results): OWL009 warning → error, and OWL010 info → warning or error (both
    describe graphs outside OWL 2 DL); OWL013/OWL014 → error; OWL032 info → warning; OWL045's
    missing or malformed list → error like OWL031; OWL038 error or warning; confidence `certain`
    for OWL023, OWL041, SHQ008 and SHQ018 (exact checks still on the default `heuristic`, which
    changes `differential.json`); OWL004/OWL007 `heuristic`; category `deterministic` for SKOS001
    and SKOS002; SKOS001 on any owned resource with a `skos:prefLabel`, not only concepts (S14).
    Added by the coverage gaps (each new finding ships at its rule's current severity): SHQ011
    for a `\/` escape (an error by XPath, but pySHACL and Jena accept it, so a warning would match
    its practical effect); SHQ008 for a derived integer type such as `xsd:nonNegativeInteger`
    (common in generated shapes); SHQ015 warning → error (XPath raises FORX0001 for a bad flag
    letter); OWL035 "several constraints" (a restriction with both `minCardinality` and `maxCardinality`, a
    common OWL 1 / Protégé idiom) ships at error and needs counting on the real-world corpus;
    OWL010 and OWL032 stay info although their new conditions are outside OWL 2 DL too.
  - *Defects that change an exit code, a focus or a message:* all fixed in 0.11.0 (see
    "Recently done", AUDIT-DEFECTS): an unwritable or unencodable report is TOOL001 and exit 2
    (`db56b3f`); OWL034, OWL036 and OWL040 print N3, not Python reprs (`77b8f84`), and so does
    OWL013 for a literal with a line break (`85562dc`); SEC014 masks the password in its focus
    (`c205df2`). (SEM001's misclassification and machine-dependent focus: fixed in 0.10.2.)
    Follow-ups, each its own contract change:
    - *Credentials in every other rule's output* and *SEC014 and modules*: fixed (issue 13, see
      "Recently done", USERINFO-MASK), pending the maintainer's confirmation of the token-as-user
      decision recorded there.
  - *False positives found by the 2026-11-10 review:* (LEX002 and every rule using
    `RuleContext.descriptions` followed `rdfs:subPropertyOf` one step only: fixed in 0.11.0, in
    6dc2285 and 19d9667, see "Recently done"). The follow-ups (labels, `owl:equivalentProperty`,
    SKOS notes) are done too (issue 15, see "Recently done", PREDICATE-CLOSURE). Left open, each a
    contract decision: SKOS001, LEX009 (`rdfs:label` only), the alternative labels of LEX015 and
    LEX016 (`ALTERNATIVE_LABELS`), and CLS013 and CLS020 (`hierarchy_quality.LABEL_PREDICATES`)
    read fixed predicates, so a `skos:prefLabel` sub-property is not a second prefLabel to SKOS001
    and a `skos:altLabel` sub-property is no alternative label; the OBO rules read `rdfs:label` and
    IAO only, by design.
  - *Policy that silently does nothing:* fixed in 0.11.0 (see "Recently done", POLICY-SILENT).
    Follow-up for RULE-DOCS, fixed (issue #16): `"selectable"` in `--list-rules --format json` and
    `--explain` is now false for the pipeline rules, which `--select` rejects, as well as for the
    proposed ones; read `status` for "implemented".
  - *Coverage gaps:* closed in 0.11.0 (see "Recently done", COVERAGE-GAPS). Left open, each
    with its reason in the rule's specification:
    - *SHQ011 inside a character class* (narrowed by SHQ-SPEC, which reports an unescaped `[` not
      after `-`, a leading `]` and a `\p{..}` name that is no XSD category or `Is` block form, as
      XSD 1.0 and 1.1 both reject them): the placement of `-` is left to Python, as XSD 1.0 and 1.1
      disagree on it and an error rule must not guess; whether a block name exists is not checked
      (it follows the Unicode version); an empty group before a subtraction (`[-[a]]`) passes; a
      back-reference to group 100 or above is not judged (Python reads it as an octal escape);
      XPath 2.0-only strictness is not applied (`(?:` and the `q` flag of XPath 3.0 are accepted).
    - *OWL019:* a characteristic typed on an anonymous inverse expression (`[ owl:inverseOf p ] a
      owl:FunctionalProperty`) is judged only when the expression is itself transitive or
      chain-defined; the other global restriction of SS 11.2, the regularity of the property
      hierarchy, is not checked.
    - *OWL035* accepts `owl:hasSelf "1"^^xsd:boolean` (its value is true; MAP writes only `"true"`).
    - *OWL011's datatype test* (`owl._is_datatype`) lacked the non-XSD datatypes OWL040 knows
      (`rdf:langString`, `owl:real` ...): fixed for issue #12. OWL011, OWL022 and OWL040 now read
      one list, `support.LITERAL_RANGES`, through `support.is_datatype_iri`, and `rdf:JSON` joined
      it. OWL011 alone also spares an untyped `owl:onDatatype` node, as a heuristic may; the error
      rules need MAP's `rdfs:Datatype` typing. `tests/test_datatype_knowledge.py` holds the three
      rules to the list. Left open: RDF 1.2's `rdf:dirLangString`; OWL040 lacks OWL022's exclusion
      of a term typed both `owl:Class` and `rdfs:Datatype`; OWL011 reports an untyped union or
      `owl:oneOf` of datatypes or literals; any `xsd:` IRI counts as a datatype, `xsd:anyType` and
      misspellings included (DATA004 reports those).
    - *Real-world counts:* counted on 0.12.0 (issue #12, 2026-11-11), with sources, commands and
      checksums in `docs/validation/coverage-gaps-0.12.0.md`. All 13 rules report 0 findings on
      pinned CCO v2.2, BFO 2020 and BFO 2.0, and RO v2026-09-04, with and without imports.
      Ad-hoc rdflib counts find the constructs clean (RO has about 220 non-simple properties but no
      cardinality restriction, and no simple-only axiom on them), and one injected violation per
      rule is reported, so the zeros are real. None of the three publishes SHACL, so SHQ008 and
      SHQ011 did not run there; on the DCAT-AP 3.0.1 shapes they report 0. The severity questions
      above therefore have no corpus evidence either way. Still to do: count them on ontologies
      that apply RO (Uberon, CL, OBI, GO-plus) and on tool-generated SHACL. OWL011, counted as the
      baseline, reports 31 BFO 2020 typing axioms (`C ⊑ ∀ part of . C` and the like), all leaning
      false positive: its precision there is about 0%.
  - *Documentation:* `docs/rules.md` shows only each rule's first positive and negative case, so
    the new cases and the specifications are visible only in the source. Render the module
    specifications (or all cases) in the generator.

- [ ] **Approve a current mutation baseline before making it blocking.** Existing mutation-policy
  thresholds and pardon-review rules are useful only if a clean GitHub run establishes that the
  current suite meets them. The last *full* triage predates 0.4.0; the targeted runs since then killed every mutant in the code each release changed, and the survivors that remain are all in older code (see the 0.10.2 entry). `context.py` is outside the mutation scope; decide
  whether it belongs in it. There are 20 `gremlin: pardon` markers for a reviewer to audit. The
  first hosted run (42611542815) timed out before writing a report; its causes are fixed and on
  `main` since 2026-11-09. Its re-run on 2026-11-10 (attempt 2) proves
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

Order: DATASET-PROVENANCE (P0; done in 0.11.0: `datasets.GraphIndex` gives every triple's
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

- [x] **DUPLICATE-ONTOLOGY-ID: one ontology IRI declared by two files.** Nothing checked this
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

  Done (issue #25): `ONT007` (warning, different content) and `ONT008` (info, identical copies), of
  the new rule scope `set`. Before linting, `ontolint.declarations` compares the documents of the
  run in the four places, each on its own, and hands each input the identities reported on it as
  `Policy.shared_identities`; the rule module only turns them into findings, so selection,
  overrides, baselines and `--fail-on` apply as to any rule. "Same content" is the RDF graph up to
  isomorphism (`datasets.same_content`: a digest over blank nodes by `stable_blank_id`, and
  `rdflib.compare.isomorphic` when two blank nodes share an identity). Two versions of one
  ontology (one ontology IRI, different version IRIs: an ODK edit file and its release) coexist
  among the inputs and the graphs of a dataset; in a closure they are reported (OWL 2 section
  3.5). The closure also compares the file an import resolves to but did not load, because a
  module loaded earlier declares its IRI, so the result no longer depends on the order of the
  imports. `--import-dir` keeps only the paths of the files sharing an IRI and reads a candidate
  again only when an import resolves to it, once per run; aliases count once; copies in two
  directories are named with both. One fact is reported once (a finding whose documents are a
  subset of another's on the same IRI is dropped). SARIF gives one location and relates the other
  files. The baseline identity is the rule, the IRI, the place and the kind, never a path.
  - Verified: `tests/test_duplicate_ids.py` with fixtures in `tests/fixtures/duplicates/`, rule
    cases, a scaling step for the graphs of a dataset, and relations in
    `test_metamorphic_multifile` and `test_properties_datasets` (exact sets, both kinds). File
    independence there and in `test_metamorphic_baseline` holds with the two rules ignored. The
    goldens moved only by the two rules' metadata and executions.
  - Left open: `--shapes-from-profile` resolving through an `--import-dir` with two candidates;
    an unreadable file in an `--import-dir` is still skipped silently; the message does not list
    each member's version IRI; a catalog entry naming a file that does not declare the imported
    IRI is not reported.

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
  Include the closed-pipe behaviour (`tests/test_cli_broken_pipe.py` skips on Windows, which
  reports `OSError` EINVAL for it).

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
  counts in the repository; a release shows the diff and explains every change. This is the cheap half of precision measurement; labelled
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
- [ ] **Modular ontologies: finish what stages 1-4 left open.** Stages 1-4 are built: offline resolution, per-module provenance, closure semantics and SHACL with the ontology
  as background. Left:
  - *Validation on a public corpus:* started on 2026-11-09, see "Real-world ontologies". The import root and ownership (0.8.0) and Functional Syntax (`--convert-with-robot`,
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
- **Automatic fixes (`--fix`):** defer until findings carry structured evidence (SHACL001 does
  since 0.11.0, and every finding names its subject for its baseline identity); only
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
  from it: SHACL validation had no time budget (SHACL-TIMEOUT, 0.11.0), named-graph provenance
  (DATASET-PROVENANCE, 0.11.0), the single-file and multi-file fingerprint split (BASELINE-V2,
  0.11.0), a JSON Schema for the JSON report (OPS item, P2), the blank-node identity
  cost (P2), and acceptance cases for the SEM, CQ, ALIGN and policy-pack gates. Checked and not
  taken up:
  - metamorphic tests exist: `test_properties_lint.py` covers triple order, blank-node labels,
    the base IRI and the hash seed, and worker and in-process parses agree;
  - configuration is validated (OPS008, GOV020), and import cycles terminate;
  - its "rule-quality dashboard" is the corpus-count and metric-calibration items;
  - its "execution manifest" is the per-rule `executions` plus exit 2;
  - a language server, `--fix`, caching and changed-line filtering stay deferred, for the reasons
    under "Explicitly deferred".

- **"Which rule group next?":** the question is moot. All 55 proposed rules are blocked by a missing
  backend or input contract (COMP 16, CQ 13, FAIR 13, SEM 7, ALIGN 4, GOV 1, IRI 1), so none can be
  implemented without one of the decision gates above being accepted first. (An earlier version of
  this file claimed the gates covered all of them; ALIGN had no gate until it was added.)
