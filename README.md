<p align="center">
  <img src="https://raw.githubusercontent.com/arnaudgelas/ontolint/main/logo.png" alt="ontolint logo" width="240">
</p>

# ontolint

<p align="center">
  <a href="https://github.com/arnaudgelas/ontolint/actions/workflows/ci.yml"><img alt="CI status" src="https://github.com/arnaudgelas/ontolint/actions/workflows/ci.yml/badge.svg?branch=main"></a>
  <a href="https://github.com/arnaudgelas/ontolint/actions/workflows/validation.yml"><img alt="Validation status (ROBOT image and mutation testing)" src="https://github.com/arnaudgelas/ontolint/actions/workflows/validation.yml/badge.svg?branch=main"></a>
  <a href="https://github.com/arnaudgelas/ontolint/commits/main"><img alt="Last commit" src="https://img.shields.io/github/last-commit/arnaudgelas/ontolint"></a>
  <a href="https://github.com/arnaudgelas/ontolint/issues"><img alt="Open issues" src="https://img.shields.io/github/issues/arnaudgelas/ontolint"></a>
</p>
<p align="center">
  <a href="https://pypi.org/project/ontolint/"><img alt="PyPI version" src="https://img.shields.io/pypi/v/ontolint"></a>
  <a href="https://pypi.org/project/ontolint/"><img alt="Python versions" src="https://img.shields.io/pypi/pyversions/ontolint"></a>
  <a href="https://github.com/arnaudgelas/ontolint/blob/main/LICENSE"><img alt="License: Apache-2.0" src="https://img.shields.io/badge/license-Apache--2.0-blue"></a>
  <a href="https://github.com/arnaudgelas/ontolint/blob/main/docs/rules.md"><img alt="Rules implemented: 247 of 302" src="https://img.shields.io/badge/rules-247%2F302_implemented-brightgreen"></a>
  <img alt="Offline first" src="https://img.shields.io/badge/mode-offline--first-informational">
  <img alt="Formats: RDF, OWL, SKOS, SHACL" src="https://img.shields.io/badge/formats-RDF%20%C2%B7%20OWL%20%C2%B7%20SKOS%20%C2%B7%20SHACL-6f42c1">
</p>
<p align="center">
  <a href="https://docs.astral.sh/ruff/"><img alt="Code style and lint: Ruff" src="https://img.shields.io/badge/lint%20%26%20format-ruff-D7FF64?logo=ruff&logoColor=black"></a>
  <img alt="Types: pyright strict and mypy" src="https://img.shields.io/badge/types-pyright%20strict%20%2B%20mypy-2a6db2">
  <img alt="Coverage gate: at least 95 percent" src="https://img.shields.io/badge/coverage%20gate-%E2%89%A595%25-brightgreen">
  <a href="https://github.com/arnaudgelas/ontolint/blob/main/docs/mutation-policy.md"><img alt="Mutation gate: at least 85 percent" src="https://img.shields.io/badge/mutation%20gate-%E2%89%A585%25-brightgreen"></a>
  <a href="https://docs.astral.sh/uv/"><img alt="Managed with uv" src="https://img.shields.io/badge/managed%20with-uv-DE5FE9"></a>
</p>

`ontolint` is an offline ontology-quality linter for RDF graphs. It provides
graph-local checks for RDF/OWL, SKOS, lexical quality, class hierarchies, and
optional SHACL validation. It is a practical review aid—not a substitute for
OWL 2 DL validation, a reasoner, or expert ontology review.

## What it checks

247 of the 302 catalogue rules are implemented; the rest are planned. The
[rule reference](https://github.com/arnaudgelas/ontolint/blob/main/docs/rules.md) documents each one with an example.

- 227 Python graph checks for metadata, identifiers, IRIs, labels and lexical
  quality, class hierarchies, OWL axioms and class expressions, SKOS, SHACL
  shape quality, governance, ontology metrics, mapping quality, input-safety
  hygiene and, opt-in, OBO Foundry and FAIR publishing conventions.
- `INPUT001` for RDF parsing failures.
- `SHACL001` for optional pySHACL validation results.
- `TOOL001` for configuration and execution failures.
- `SEM001` for opt-in ROBOT OWL-profile validation failures.
- `SEC001`, `SEC002`, `SEC003`, `SEC006`, `SEC009`, `SEC010`, `SEC011`, `SEC013` and
  `SEC015` for unsafe inputs, rejected by the loader before linting (see below).

Each finding includes a rule identifier, severity, focus, message, suggested
remediation, and confidence level. Rules are policy-oriented: a finding is not
automatically a logical inconsistency.

## Requirements and installation

Python 3.13 or later is required. ontolint is published on
[PyPI](https://pypi.org/project/ontolint/) and installs a command named `ontolint`.

Install it as a standalone tool, isolated from your other Python packages:

```bash
# uv (recommended)
uv tool install ontolint

# or pipx
pipx install ontolint

# or into the current environment
python -m pip install ontolint
```

Run it once without installing it:

```bash
uvx ontolint ontology.ttl
```

Upgrade with `uv tool upgrade ontolint`, `pipx upgrade ontolint` or
`python -m pip install --upgrade ontolint`. Check the installation with:

```bash
ontolint --version
ontolint --help
```

`python -m ontolint` works as well. Docker is needed only for `--owl-profile`.

To try the unreleased development version, install from GitHub instead, for
example `uv tool install git+https://github.com/arnaudgelas/ontolint`. From a
clone of the repository, `uv tool install .` installs the checkout and
`uv tool install --editable .` keeps it linked to your working copy.

### Development setup

```bash
uv sync --group dev
```

In a development checkout run the command through uv, for example
`uv run ontolint ontology.ttl`. For a standard `pip` environment, install the
package and its test tools:

```bash
python -m pip install -e .
python -m pip install pytest hypothesis pytest-gremlins pytest-xdist pytest-randomly pytest-archon
```

## Run the linter

Use the library directly when integrating ontolint into Python applications:

```python
from rdflib import Graph
from ontolint import Linter

graph = Graph().parse("ontology.ttl")
findings = Linter(graph, base="https://example.org/ont#").run()
```

The command-line interface is a thin wrapper around the same Python library
(in a development checkout, prefix the commands with `uv run`):

```bash
# Text report
ontolint ontology.ttl \
  --base 'https://example.org/ont#'

# JSON report written to a file
ontolint ontology.ttl \
  --base 'https://example.org/ont#' \
  --format json --output report.json

# Fail a CI job for warning- or error-level findings
ontolint ontology.ttl --fail-on warning
```

Supported report formats are `text`, `json`, and `sarif`.

| Exit code | Meaning |
| --- | --- |
| `0` | No finding meets the configured `--fail-on` threshold. |
| `1` | At least one finding meets the threshold. |
| `2` | Tool failure: unreadable input or configuration, an unknown rule selector, a usage error, a report that cannot be written to `--output` or encoded (`TOOL001: report output failed: ...`), or a requested rule that `failed` or is `unsupported` (for example `--owl-profile` without Docker, or a SHACL validation that exceeds `--max-validation-seconds`). |

Exit `2` outranks `1`: when a requested backend did not deliver a verdict the run cannot
pass, even with `--fail-on never`. The report is still written so you can see why. Rules that
are `skipped` (no shapes supplied, no OWL profile requested, ignored) never change the exit code.

Two advisory messages go to stderr and never change the exit code or the report:
`TOOL002` warns that `--base` selects none of the declared terms, and `TOOL003` notes that a
linted file looks like a SHACL shapes graph (more shapes than declared terms), which should
probably be passed with `--shapes` instead. With `--follow-imports`, `TOOL004` notes a catalog
entry that names a missing file. `TOOL005` notes when most terms without a definition (`LEX002`)
carry an unrecognised predicate named like one, and suggests `extra_definition_predicates`; besides
the built-in and configured lists, any predicate the ontology declares `rdfs:subPropertyOf` one of
them, directly or through a chain of sub-properties (cycles are fine), already counts. `TOOL006` says
when `--module-annotation` cannot group a file (its prefix is not declared, or no term carries the
predicate), `TOOL007` names the validator `--shapes-from-profile` uses (or passes over, when it is
not SHACL), `TOOL008` warns that a file under
`--pattern-library` does not parse and was skipped, `TOOL009` names each shape library a
shapes file imports, and `TOOL010` warns that a file under `--import-dir` was skipped because the
safe loader refused it (too large, compressed, an external DTD; the line gives the `SEC` rule and
its message), so no import resolves to it.

### Discovering rules

```bash
ontolint --version
ontolint --list-rules                 # table
ontolint --list-rules --format json   # machine-readable
ontolint --explain SHQ001             # title, severity, fix, backend, scope, requirements
```

`--list-rules` shows the catalogue *status* of every rule: `implemented` (can be selected and
run) or `proposed` (planned only; it has no severity or scope, cannot be selected and never
runs). This is different from the per-run *execution status* below. `--explain` on an unknown
identifier exits `2`.

### Selecting rules and profiles

`--select` and `--ignore` take rule identifiers (`ONT001`) or family prefixes (`ONT`),
case-insensitively, comma-separated and/or repeated. Unknown selectors, empty entries
(`ONT,`) and proposed-only rules are errors (exit `2`), so a typo never becomes an empty run.
So is a selector that names only *pipeline rules* (`TOOL001: configuration failed:
PipelineSelectorError: ...`, before any input is read): the safe-loader refusals `SEC001`,
`SEC002`, `SEC003`, `SEC006`, `SEC009`, `SEC010`, `SEC011`, `SEC013` and `SEC015`, the
diagnostics `INPUT001` and `TOOL001`, and the `INPUT` and `TOOL` families. They are not findings
and always apply, so no selection can change them (`--list-rules --format json` shows them with
backend `cli`). The `SEC` family is accepted: it selects or ignores the graph rules `SEC004`,
`SEC005`, `SEC007`, `SEC008`, `SEC012` and `SEC014`.

`--profile` picks a bundle of defaults:

| Profile | Rules | Severity overrides | Default `--fail-on` |
| --- | --- | --- | --- |
| `minimal` | `ONT`, `IRI`, `DATA`, `SKOS`, `SHACL`, `SEM` (structural integrity) | none | `error` |
| `recommended` | all (same as no profile) | none | `error` |
| `ci` | all | none | `warning` |
| `strict` | all except `SEC007` | `ONT003` becomes `error` | `info` (any finding fails) |
| `obo` | all, plus the opt-in `OBO` family | none | `warning` |
| `fair` | all, plus the opt-in `FAIR` family | none | `warning` |

**Opt-in rule families.** The `OBO` family (OBO Foundry conventions) and the `FAIR` family (offline publishing
checks) never run by default: it is excluded from running without a profile and from
`recommended`, `ci`, `strict` and `minimal`. Enable them with `--profile obo`,
`--profile fair`, `--select OBO`, `--select FAIR` or a single id such as `--select OBO003`. `--list-rules` and `--explain` mark these
rules as opt-in. An explicit `--select` replaces a profile's selection, so
`--profile obo --select LEX` runs only `LEX`.

Precedence when options combine:

1. The rule set is `--select` if given, else the profile's rules, else all rules. `--select`
   *replaces* the profile's selection.
2. Ignores always win over selection: `--ignore`, the profile's ignores and the policy file's
   `ignored_rules` are unioned and removed. Policy `ignored_rules` remain exact identifiers,
   and an identifier there or in `severity_overrides` that names no implemented rule is an error
   (`GOV020`, exit 2), so a typo cannot silently leave a rule running. So is one that names a
   pipeline rule (see above): it always applies, so the entry could not change anything.
3. Severity overrides: profile first, then the policy file's `severity_overrides` (policy wins).
4. `--fail-on`: the command line, else the profile's value, else `error`.

Other policy values (base, languages, thresholds) behave as before: explicit CLI options beat
the policy file.

### Rule execution status

JSON and SARIF always say what happened to every selected rule, so "no findings" can never be
confused with "not checked": `executed`, `skipped` (not applicable or ignored, with the
reason), `unsupported` (backend unavailable, e.g. no `pyshacl` or Docker) or `failed`
(the rule or backend raised). Rules that were deselected by `--select`/profile are simply
absent. Text output stays unchanged unless a rule was ignored, unsupported or failed, in which
case a `Rule execution:` block is appended.

* JSON keeps `summary` and `findings` and adds `schema_version` (currently `1`), a `path` on
  each finding, `rules` (id, family, title, effective and default severity, category, backend,
  scope, requirements, suggestion), `execution_summary` and per-file `files[].executions`. A
  finding whose message abbreviates a tool's output also carries the full output in `details`
  (`SEM001`: ROBOT's profile report, whose violations the message groups by kind). A finding
  whose backend returns a structured result carries it as an `evidence` object after `details`
  (`SHACL001`: every field of the SHACL validation result, see "Optional SHACL validation"); it is
  not part of the finding's identity, so fingerprints and baselines ignore it. In a dataset with
  named graphs, a finding also lists its `graphs` (see "Datasets: named graphs").
* SARIF 2.1.0 adds `tool.driver.rules` (name, short/full description, help,
  `defaultConfiguration.level`, category/backend/scope properties), `ruleIndex` and an
  `artifactLocation` on every result (and `properties.details`, `properties.evidence` and
  `properties.graphs` where JSON has `details`, `evidence` and `graphs`), and a run `invocation`.
  Skipped, unsupported and failed rules are `toolExecutionNotifications` (levels `note`,
  `warning`, `error`); `executionSuccessful` is `false` when any rule failed or is unsupported.
* SARIF findings for Turtle, N3, N-Triples, N-Quads and RDF/XML inputs include the source line and
  column of their focus term when it can be resolved. JSON-LD findings include a region for an
  explicit `@id`, including compact IRIs defined by a local context; generated JSON-LD nodes retain
  their artifact URI but omit a region rather than reporting an unreliable location.

### Several files

```bash
ontolint ontologies/*.ttl --format sarif --output findings.sarif
```

* Globbing is the shell's job (on Windows `cmd`/PowerShell pass the pattern through; use a
  shell that expands it or list the files). Directories are rejected with an error rather than
  walked.
* Each file is linted independently with the same options and its own report; results are
  aggregated. Files are ordered by report path regardless of argument order, and duplicates
  (`./a.ttl`, a symlink, another spelling on a case-insensitive file system) collapse into one.
  If any file cannot be parsed, every parse failure is reported and the run exits `2` before
  linting. `--shapes` and `--owl-profile` apply to every file; ROBOT runs once per file.
* Report paths (JSON `path`, SARIF `artifactLocation.uri`, fingerprints) are POSIX-style:
  relative to the working directory when the file is beneath it (`onto/a.ttl`), otherwise
  absolute (`file:///C:/x/a.ttl` in SARIF), with backslashes converted. Run from a stable
  directory such as the repository root so baselines and SARIF paths are portable.
* Baselines: a baseline records each finding's identity under its report path, so a baseline
  written from one file applies to that file in a multi-file run, and a multi-file baseline to
  one of its files linted alone (the entries of the files not linted are then stale). A baseline
  written from one file still applies to a one-file run whatever the file is called. The version
  1 fingerprints written next to the identities are unchanged: a single-file run hashes `(rule,
  focus, message)` and a multi-file run adds the report path (see "Policy and baselines").

### Modular ontologies: following `owl:imports`

By default each file is linted alone, so an umbrella ontology that only `owl:imports` its modules
checks almost nothing (`SEC007` lists the imports that were not followed). With
`--follow-imports`, ontolint loads the import closure from local files and lints it as one graph:

```bash
ontolint ontology.ttl --follow-imports                  # uses catalog-v001.xml next to ontology.ttl
ontolint ontology.ttl --catalog path/to/catalog-v001.xml  # an explicit catalog (implies --follow-imports)
```

Imports resolve through an OASIS XML catalog (the Protégé, ROBOT and ODK `catalog-v001.xml`: `uri`
entries, also inside `group`, and `rewriteURI` prefixes) or as `file:` IRIs; the network is never
used, and imports that do not resolve stay listed by `SEC007`. The catalog next to each imported
file is consulted before the root catalog, as Protégé does, and an import naming a file already in
the closure by its ontology or version IRI needs no entry. A catalog entry whose file does not exist
leaves the import unresolved, with a `TOOL004` note, rather than failing the run. Every resolved
file must lie inside the import root after symlinks are followed (`SEC009`): by default the
enclosing git repository of the catalog (or of the input without a catalog), so catalogs may point
at sibling directories (`../modules/x.ttl`), or the directory given with `--import-root DIR`. For
imports of published builds without a catalog (an upper ontology by its PURL, say), put local copies
in a folder, for example with `robot mirror`, and pass `--import-dir DIR` (repeatable): its RDF
files are matched by the ontology or version IRI they declare. A file there that the safe loader
refuses is skipped with a `TOOL010` warning (an import it would have resolved is then reported by
`SEC007`), and one that does not parse, or a `catalog-v001.xml`, is skipped silently. Ownership is decided by the root
file's own terms, so an import that declares more terms than the root never becomes the linted
ontology. Each file passes the usual safe loader, and the closure is bounded by `max_import_depth`
(16), `max_imported_files` (100) and `max_triples` as a whole (`SEC015`). Cycles end and a module
imported twice is loaded once. The headers of imported modules do not count as extra ontologies for
`ONT002`.

A finding belongs to the module that declares its focus (gives it an `rdf:type`), or else to the
first module that mentions it: JSON gives that module's `path`, SARIF its `artifactLocation` and
region, and text adds an `In:` line. Baseline fingerprints and identities are unchanged, so a
closure baseline keeps matching.

The closure is linted as one published ontology, the root's: header rules (`ONT003`-`ONT006`,
`GOV004` and the like) judge the root ontology only, as the modules inherit its metadata (lint a
module on its own to check its header); owned terms are derived from the root IRI, so a vendored
vocabulary with its own namespace is background, not judged; and `METRIC011` does not count imports
that resolved to local modules. Graph-wide heuristics (`CLS002`, `METRIC*` ratios) count the whole
closure, data modules included, on purpose: a class that no module instantiates is exactly what
`CLS002` reports.

SHACL shapes often check the class of a vocabulary individual, which only the ontology states, so
instance data validated alone reports false violations (and can silently pass where a target class
is reached through a subclass). With `--follow-imports`, a shapes file that `owl:imports` the
ontology supplies it: SHACL validates the data merged with that closure (inference off), reports
only results about nodes the linted file mentions (as a subject or an object, so a
`sh:targetObjectsOf` focus counts), and the term rules still judge the data file alone. An imported
file that declares shapes is a shape library: its shapes are validated with too (a `TOOL009` note
names it), and its other triples, if any, join the ontology background.

```bash
ontolint data.ttl --shapes shapes.ttl --follow-imports   # shapes.ttl imports the ontology
```

### Modules inside one file

Some ontologies keep their modules in one file. A MOMo schema marks each term with the module it is
native to; a merged release keeps one namespace per source ontology. Two options group the findings
by those modules, without changing any finding:

```bash
ontolint schema.ttl --module-annotation opla:isNativeTo   # an IRI, <IRI>, or a CURIE the file declares
ontolint release.ttl --module-by namespace                # each term's namespace is its module
```

A finding belongs to the modules of its focus; a local-name (`IRI003`) or label (`LEX004`)
collision belongs to the modules of every term involved, so a collision *between* modules lists
both. Text adds `In: module X` (or `In: modules A, B`) and a `Findings by module:` summary; JSON
adds `modules` to each finding and `module_summary` (counts by severity) to each file; SARIF adds
`properties.modules`. Findings whose focus is not an IRI, or whose term has no annotation, belong to
no module. Fingerprints, identities and baselines are the same with and without grouping. The policy keys
`module_annotation` (an absolute IRI) and `module_by` (`"namespace"`) do the same; the two are
alternatives, and a CLI option replaces the policy's choice.

### Datasets: named graphs

A TriG, N-Quads or JSON-LD file can hold named graphs. ontolint lints the union of its graphs, so
every rule runs once and a reference from one graph to a term described in another resolves. Each
finding then names the graphs it comes from:

```text
[INFO   ] LEX002 http://example.org/Thing: Term has no description or definition.
    Fix: Add a natural-language definition (rdfs:comment, skos:definition, or dcterms:description).
    In: graphs http://example.org/g1, http://example.org/g2
```

A finding names the graphs that describe its focus (state a triple with it as the subject), or, if
none does, the graphs that mention it (a superclass that is only used). A collision (`IRI003`,
`LEX004`) names the graphs of every term involved, as it names every module. A triple stated in
two graphs belongs to both, so a term described in two graphs names both; the finding is still
reported once. A finding whose focus is no node of the file (`(ontology)`, a literal) names no
graph, and neither does a finding about a pattern library member.

Graph names do not depend on where the file is read. The default graph is `(default graph)` and
is listed first. A graph IRI is printed in full, except a `file:` IRI, such as a relative
reference that resolved against the file (`<rel> { … }`, `<../g> { … }`, `<#g> { … }`): it is
shown relative to the file, `rel`, `../g` or `#g`, never as a `file:` IRI with a local path.
A blank-node graph (`_:g { … }`) has a new label on every parse, so it is named by its content:
`_:` and 12 hex digits of a digest of its triples. Two blank graphs with the same triples
therefore share one name, and editing a blank graph renames it. An empty named graph names
nothing.

Text adds `In: graph X` (or `In: graphs X, Y`), after an imported module's file and before the
modules inside the file; JSON adds `graphs` to each finding, between `path` and `modules`; SARIF
adds `properties.graphs`. All three appear only for a file with at least one triple outside its
default graph, so every other file reports exactly as before. Like modules, graphs are presentation
only: fingerprints, baselines and exit codes do not depend on them, and moving a triple to another
graph keeps its findings baselined. In an import closure, each finding names the graphs of the file
it belongs to.

### Pattern libraries

A pattern library is an index ontology plus one ontology per pattern, linked by naming
conventions rather than `owl:imports`. `--pattern-library DIR` lints the input as the index and the
RDF files under `DIR` that declare an `owl:Ontology` as its members (the index itself is not one):

```bash
ontolint modl/modl.owl --pattern-library modl
```

`LIB001` reports an index entry that names no member by IRI (its IRI is not a member's ontology or
version IRI, no index triple points at one, and no member header names it); when a member has the
same name (`AgentRole` and "Agent Role"), the message names it and how to link the two. `LIB002`
reports a member no entry names, and `LIB003` a member header naming an IRI in the library
namespace that no member declares (an `opla-core:hasRelatedPattern` to a missing pattern).
Findings about a member belong to its file. Members are read like `--import-dir` files: through
the safe loader, inside the import root (`SEC009`), at most `max_imported_files` (`SEC015`). A file
that does not parse is skipped with a `TOOL008` warning, and the rules then say what they report
missing may be in one of the skipped files. Without the option the `LIB` rules are `skipped`.

### GitHub annotations

`--format github` is not available yet. The escaping helpers (`%`, CR, LF and, for properties,
`:` and `,`) already exist in `ontolint.github`; a formatter has not yet been added.

### Optional SHACL validation

Pass a shapes graph with `--shapes` to enable pySHACL validation:

```bash
ontolint ontology.ttl --shapes shapes.ttl
```

The integration uses `meta_shacl=True` and `advanced=True`, with `inference="none"` and the
network disabled (see "Input safety" for what that admits). Newer SHACL draft
features are not guaranteed to be supported. Shapes can make validation run for a long time;
`--max-validation-seconds` (or `max_validation_seconds` in the policy) stops it, and `SHACL001`
then fails (exit `2`).

When a [W3C PROF](https://www.w3.org/TR/dx-prof/) profile names the shapes (`prof:hasResource [
prof:hasRole role:validator ; prof:hasArtifact <…/validator> ]`), let the profile say which:

```bash
ontolint ontology.ttl --shapes-from-profile profile.ttl
```

Each SHACL validator of the profile (a descriptor whose `dct:conformsTo` names SHACL, or nothing)
is found offline, in this order: the catalog next to the profile or `--catalog`, `--import-dir` by
ontology or version IRI, or a file beside the profile named after the IRI's last path segment
(`…/validator` → `validator.ttl`). It must lie inside the import root (`SEC009`). Several
validators are merged; a validator of another standard is passed over with a `TOOL007` note. A
profile that names no SHACL validator, or one with no local copy, fails the run (`TOOL001`, exit
`2`). `--shapes` and `--shapes-from-profile` are alternatives.

Each SHACL result becomes a `SHACL001` finding at the result's own severity:
`sh:Violation` is `error`, `sh:Warning` is `warning` and `sh:Info` is `info`, so
warnings-only data passes the default `--fail-on error`. A custom severity is
reported as `error` and named in the message. Blank-node shapes and focus nodes
are named by a content-stable identity, in the focus and in a finding's baseline identity alike,
so baselines keep matching across runs.

In JSON and SARIF (not in text), each `SHACL001` finding also carries the whole result as
`evidence` (`properties.evidence` in SARIF), so two violations of one shape on one node, which
share their message, still say which value or path to fix. Its keys are the SHACL names of the
result's properties, in this order, each present only when the report has it: `focusNode`,
`resultPath`, `value`, `sourceShape`, `sourceConstraintComponent`, `sourceConstraint` (SPARQL-based
constraints), `detail`, `resultMessage` (every message, sorted, without language tags) and
`resultSeverity` (the original IRI, also for a custom severity). An IRI is written as is, a blank
node by the same content-stable `_:` identity as a focus, and a literal as one N-Triples term
on one line (`"x"`, `"5"^^<http://www.w3.org/2001/XMLSchema#integer>`, `"chat"@fr`, with `\"`,
`\\`, `\n` and `\r` escaped), so a literal focus is `"x"` in the evidence but `x` in `focus`.
A path other than a single predicate is written in SPARQL property-path syntax (`^<p>`,
`<a>/<b>`, `<a>|<b>*`); a malformed, cyclic, or over-deep or over-large one is
`(malformed path)`. `detail` lists the nested results of a `sh:node` (or
similar) violation as evidence objects, sorted, at most 8 levels deep. pySHACL types those nested
results as validation results too, so each is also a finding of its own, as before. The evidence
copies each value in full, so a report with many results on long literals grows accordingly.
Findings with the same message are ordered by their evidence, so the output no longer depends on
pySHACL's hash-seed-dependent result order. The message, focus, severity and fingerprint are
unchanged. A baseline identity is made of the source shape, constraint component, path, value and
SPARQL constraint, so a pySHACL upgrade that rewords its messages keeps results accepted. Because
the version 1 fingerprint (by message) is still accepted too, a new result whose message equals an
accepted one's is accepted as well.

The data graph of a TriG, N-Quads or JSON-LD dataset is the union of its graphs, as for every
other rule: SHACL defines the validation of one data graph, and a value typed in one graph and
referenced from another conforms to `sh:class`. A `SHACL001` finding names the graphs of its
focus node (see "Datasets: named graphs"). To validate each graph on its own, write each one to
its own file and lint the files together; each file is validated separately.

### OWL profile validation with ROBOT in Docker

Build the minimal project image once. Its final stage contains only the ROBOT
JAR and a non-root Java runtime:

```bash
docker build --tag ontolint-robot:1.9.11 docker/robot
ontolint ontology.ttl --owl-profile DL
```

The profile run mounts the ontology directory read-only, disables container
networking, drops Linux capabilities, and applies CPU, memory, process, and
timeout limits. The image build verifies the ROBOT JAR against a pinned
SHA-256. Supply a digest-pinned image with `--robot-image` in CI.

`SEM001` is reported only when ROBOT lists profile violations. Any other failure (a missing
image, a Docker, Java or permission error) is no verdict on the ontology: the rule is `failed`,
with ROBOT's output in its detail, and the run exits `2`, as for a timeout. A profile pass says
the ontology fits the profile; it does not say the ontology is consistent.

## Policy and baselines

A JSON policy can supply a base IRI, label-language requirements, thresholds,
ignored rules, and severity overrides.

```json
{
  "base": "https://example.org/ont#",
  "languages": ["en"],
  "depth_limit": 10,
  "inheritance_limit": 5,
  "soup_limit": 15,
  "subclass_limit": 50,
  "ignored_rules": ["CLS002"],
  "severity_overrides": {"ONT003": "error", "OWL005": "info"},
  "required_annotations": {"class": ["http://www.w3.org/2004/02/skos/core#definition"]},
  "alignment_namespaces": ["http://purl.obolibrary.org/obo/"],
  "alignment_min_coverage": 0.5,
  "max_parse_seconds": 60,
  "max_validation_seconds": 120,
  "module_by": "namespace"
}
```

The optional keys switch rules on only when set: `required_annotations` maps a term kind
(`class`, `property`, `individual`, `concept`) to the predicates every owned term of that
kind must carry (`GOV016`); `alignment_namespaces` lists the namespaces mapping targets
must belong to (`ALIGN012`); `alignment_min_coverage` is the share of classes and
properties that must have a mapping (`ALIGN016`). `subclass_limit` (also `--subclass-limit`,
default 50) is the most direct subclasses a class may have before `CLS011` reports it.
Unknown keys are reported by `GOV020`,
and an unsupported `policy_version` rejects the file. `max_parse_seconds` (also
`--max-parse-seconds`) limits the time spent parsing one input and reports `SEC003`
when it is exceeded; it parses in a worker process, so leave it unset for the fastest
in-process load. `max_validation_seconds` (also `--max-validation-seconds`) does the same for
SHACL validation: past it the validation is stopped and `SHACL001` is `failed` (no finding,
`TOOL001` on stderr, exit `2`, as for a ROBOT timeout). It counts from the moment the worker
process has imported pySHACL, once per linted file, and includes handing the data and shapes
graphs to the worker. It has no effect without shapes. Neither key inherits the other.

The `metric_*` keys set the thresholds of `METRIC001`-`METRIC013`. Each is validated (an invalid
value is `TOOL001`, exit `2`) and has no flag or profile value;
[docs/metric-thresholds.md](https://github.com/arnaudgelas/ontolint/blob/main/docs/metric-thresholds.md)
lists every key with its default, the rationale and the offline measurements.

```bash
# Emit SARIF using a policy
ontolint ontology.ttl \
  --config policy.json --format sarif --output findings.sarif

# Record accepted findings, then report only newly introduced ones
ontolint ontology.ttl --write-baseline baseline.json
ontolint ontology.ttl \
  --baseline baseline.json --fail-on warning
```

A baseline file (version 2) records every finding of the run twice. `fingerprints` lists the
version 1 hash of `(rule, focus, message)`, plus the report path in a multi-file run, exactly as
ontolint 0.10 wrote it. `identities` maps each report path to the finding's *identity*, a hash of
its rule, focus and subject. The subject is what the finding is about besides its focus: the
predicate, the other term, the literal, the language. It never includes the message, counts,
ratios or thresholds. `files` lists the report paths of the run. `--baseline` accepts a finding
when either hash is recorded, so:

* rewording a message, a pySHACL upgrade, or a measurement that changes (a `METRIC*` ratio, an
  `OWL004` count, ROBOT's `SEM001` summary) no longer reopens an accepted finding. This loosens
  gating on purpose: a metric ratio that rises further stays accepted, and `SEM001` stays accepted
  until the profile passes;
* identities are matched per report path (see "Several files"), so one-file and multi-file
  baselines carry over to each other.

Two findings of one file that share an identity are recorded and matched by fingerprint only, so
a new problem is never hidden behind an accepted one. A baseline written by 0.10 (no `version`,
only `fingerprints`) keeps its old behaviour until it is regenerated once with `--write-baseline`.
ontolint 0.10 reads a version 2 file's `fingerprints` and ignores the rest, but drops `identities`
if it rewrites the file. Deleting a line from `fingerprints` withdraws that finding's identity too.
A file whose `fingerprints`, `files`, `version` or `identities` has the wrong shape (a `version`
below 1, `identities` for a path missing from `files`), or that is not JSON, exits `2` (`TOOL001: lint execution failed: BaselineError: …`). Unknown keys are ignored, and
a later `version` is read for the sections this one knows. Baselines are useful for incremental
adoption, but are not semantic version comparisons.

A baseline entry (a fingerprint and its identity) that matches no finding of the run by either hash
is *stale*: the finding was fixed, or its rule was not selected this time. Every format reports
stale entries (a note in text and SARIF, the list of their fingerprints
`baseline.stale_fingerprints` in JSON), and `--fail-on-stale-baseline` makes them exit `1` so CI
asks for the baseline to be regenerated. A reworded finding matched by its identity is not stale.
Run with the same rule selection that wrote the baseline, or entries for unselected rules will
count as stale.

## Development and quality checks

```bash
# The full validation gate, exactly as CI runs it (add --fix to apply Ruff fixes first)
uv run python scripts/gate.py

# Unit and property-based tests (coverage must stay at or above 95%)
uv run pytest -q

# Run tests in parallel
uv run pytest -q -n auto

# Skip the slow Hypothesis and fuzz tests
uv run pytest -q -n auto -m 'not slow'

# The order is shuffled on every run (pytest-randomly); the seed is in the header. Replay a failing
# order with it, or switch shuffling off
uv run pytest -q -p randomly --randomly-seed=12345
uv run pytest -q -p no:randomly

# The package's layering (pytest-archon): rule modules never import the CLI, and so on
uv run pytest -q --no-cov tests/test_architecture.py

# Type checks
uv run pyright && uv run mypy && uv run mypy --platform win32

# Mutation testing (opt-in; the order stays fixed)
uv run pytest -p no:randomly -m 'not slow' --gremlins --no-cov --gremlin-parallel --gremlin-cache

# Lint and format the project
uv run ruff check . && uv run ruff format --check .
```

Hypothesis tests generate RDF graphs and check properties of the linter, such as
deterministic output and agreement of cycle diagnostics with an independent
reachability oracle. A mutation-based fuzzer (`tests/fuzz/`) feeds mutated
files to the loader, the rules and the CLI. Both are marked `slow`; run the
longer profile with `HYPOTHESIS_PROFILE=ci-deep`. Mutation testing targets the
engine, linter, CLI, loader, reporting, source locations, adapters and rules (see
[docs/mutation-policy.md](https://github.com/arnaudgelas/ontolint/blob/main/docs/mutation-policy.md)).
To add rules, see [docs/adding-rules.md](https://github.com/arnaudgelas/ontolint/blob/main/docs/adding-rules.md).

### Releasing

`uv run python scripts/bump_version.py {major|minor|patch|X.Y.Z}` updates the version files and
`CHANGELOG.md`; it never commits, tags or pushes. See
[docs/releasing.md](https://github.com/arnaudgelas/ontolint/blob/main/docs/releasing.md).

### CI workflows

`.github/workflows/ci.yml` runs `scripts/gate.py`: Ruff, Pyright, mypy (host and
Win32), tests with coverage and warnings as errors, `pip-audit` and the package build. All actions are pinned to
commit SHAs and the uv version is pinned; Renovate keeps both current.

`.github/workflows/fuzz.yml` runs the mutation fuzzer weekly with a longer
budget per target and uploads any crashing input.

`.github/workflows/release.yml` runs on a `vX.Y.Z` tag: it calls the CI
workflow, requires a green CodeQL scan of the tagged commit, checks that the
tag matches the version in `pyproject.toml`, builds the distributions,
publishes them to PyPI with Trusted Publishing from the `pypi` environment,
and finally installs the published version from PyPI and lints a file with it.

`.github/workflows/validation.yml` runs weekly and on manual dispatch:

- ROBOT Docker image build and smoke test (also on pull requests that touch
  `docker/` and carry the `validation` label). Logs are uploaded as artifacts.
- Mutation testing with the command above plus JSON/HTML reports, followed by
  `.github/scripts/mutation_gate.py`, which enforces the per-operator and
  overall thresholds. Reports are uploaded as artifacts.

The operators, thresholds, scope, waiver process and blocking/advisory rules
are defined in [docs/mutation-policy.md](https://github.com/arnaudgelas/ontolint/blob/main/docs/mutation-policy.md).

## Rule reference

[docs/rules.md](https://github.com/arnaudgelas/ontolint/blob/main/docs/rules.md) documents every rule with its severity, fix, a flagged
example, a clean example and the reported message. Rules that are not
implemented yet are listed as TODO. The file is generated; regenerate it with
`uv run python tests/rule_docs_generator.py`.

## Interpretation principles

1. RDF syntax validity and OWL logical consistency are different properties.
2. SHACL validation does not establish ontology-design quality.
3. Multiple RDFS domains or ranges are conjunctive, not alternative choices.
4. Under OWL's open-world assumption, missing evidence is not falsehood.
5. A subclass cycle is a review warning, not automatically an inconsistency.
6. `owl:allValuesFrom` does not imply the existence of a value.
7. A SKOS `broader` cycle is informational; it is not universally prohibited.
8. The linter never fetches URLs; it resolves `owl:imports` only to local files, and only with
   `--follow-imports` or `--catalog`.
9. Semantic OWL axioms are never auto-fixed because intent cannot be inferred
   reliably.

## Scope and limitations

- Term-level rules only judge terms the file owns.  With `--base` the base decides (a base such as
  `http://purl.obolibrary.org/obo/RO_` is a plain prefix; a warning is printed when it selects no declared
  term).  Without it the owned namespaces are derived from the `owl:Ontology` IRI(s) (the IRI, the IRI
  without `#`/`/`/`.owl`, and for OBO ontologies the `.../obo/<NAME>_` ID space); RDF/RDFS/OWL/XSD terms
  are never owned, and if no declared term matches, every declared term is treated as owned.
- Definitions are read from `rdfs:comment`, `skos:definition`, `dcterms:description`, `dc:description`,
  `obo:IAO_0000115`, `obo:IAO_0000600`, `prov:definition` and the Common Core Ontologies 1.x
  `<http://www.ontologyrepository.com/CommonCoreOntologies/definition>`; labels from `rdfs:label` and
  `skos:prefLabel`.
  Add more with the policy lists `extra_definition_predicates` and `extra_label_predicates` (absolute IRIs).
  A predicate the ontology declares `rdfs:subPropertyOf` a definition predicate, built-in or extra,
  directly or through a chain, is a definition predicate too.
- With `--shapes`, the SHACL step first checks the shapes graph and reports SHACL001 as failed with
  `ShapesRejected` when pySHACL would crash or stall on it: an IRI that rdflib cannot serialise (such as
  `{`, `}`, `|`, `^`, a space or a quote), a cyclic `rdf:list`, a list cell with several `rdf:rest` values,
  a list shared by several lists, a list longer than 400 items, or lists whose squared lengths sum above
  160000 (pySHACL's meta-validation re-walks each list for every internal result). The data graph is not
  refused up front: odd IRIs, large enumerations and malformed lists are accepted, and if pySHACL fails on
  one anyway the failure is reported as `ShapesRejected` with the underlying error.
- Class-hierarchy analysis uses asserted `rdfs:subClassOf` statements; it does
  not calculate entailments or inspect an import closure.
- `CLS002` can be noisy for TBox-only ontologies and is often disabled in that
  profile.
- Shape coverage (`SHQ006`) checks direct instances and direct class targets
  only.
- SARIF source regions are available for Turtle-family, N-Triples-family and RDF/XML inputs, and
  for JSON-LD resources with an explicit `@id` (including local compact IRI contexts). Generated
  JSON-LD nodes remain future work.

## Related tools and sources

- [RDFLib](https://rdflib.readthedocs.io/)
- [pySHACL](https://github.com/RDFLib/pySHACL)
- [W3C SHACL Recommendation](https://www.w3.org/TR/shacl/)
- [W3C SKOS Reference](https://www.w3.org/TR/skos-reference/)
- [OOPS! pitfall catalogue](https://oops.linkeddata.es/catalogue.jsp)
- [OntoSniff](https://ise-fizkarlsruhe.github.io/ontoink/ontosniff/)
- [ROBOT](https://robot.obolibrary.org/)
- [OBO Foundry principles](https://obofoundry.org/principles/fp-000-summary.html)

The `data/` directory contains crosswalks to the OOPS! and OntoSniff catalogues.
Those mappings are traceability aids, not claims of identical behavior; their sources, what is
reused from each and how to cite them are in [`data/README.md`](data/README.md).

## Input formats

ontolint reads Turtle, N-Triples, N3, N-Quads, TriG, RDF/XML and JSON-LD. The parser is chosen
from the file extension, unless the first bytes clearly say otherwise: Turtle saved as `.owl`,
RDF/XML as `.ttl` or JSON-LD as `.rdf` are parsed as what they are, and the RDF/XML safety checks
apply to the detected syntax. OWL Functional Syntax, Manchester Syntax and OWL/XML (common for
ODK edit files and Protégé exports, often named `.owl`) are not RDF. By default they fail with an
`INPUT001` that names the syntax and the ways forward. A parse failure in a file that contains an
HTML page (a saved web page or server error) says where that page starts. The named graphs of a
TriG, N-Quads or JSON-LD file (a node with `@id` and `@graph`) are merged with its default graph
and linted as one graph; a triple stated in several graphs counts once. Findings name their graphs
(see "Datasets: named graphs").

With `--convert-with-robot`, each such file, the input or any file of its import closure, is
converted to Turtle with the ROBOT image of `--robot-image` (see "OWL profile validation with
ROBOT in Docker"), so an ODK edit file and its components lint directly:

```bash
ontolint src/ontology/automatce-edit.owl --follow-imports --convert-with-robot
```

Each conversion runs in the same isolated container as profile validation, but only the file
itself is mounted, read-only, and is converted on its own: every import it declares is answered by
an empty stub, and ontolint then follows the imports itself, under the usual sandbox. Two
consequences:

- A Manchester Syntax file must declare every class and property it uses. One that relies on an
  import's declarations fails with an `INPUT001` saying so; convert the closure yourself (`robot
  merge`) and lint the result.
- Findings on a converted file have no line or column (SARIF regions), because the lines of the
  Turtle are not the file's.

A conversion takes a few seconds per file, and the `--robot-timeout` limit applies to each one.

A few rules read what the file's text says and RDF does not keep. `IRI019` reports a prefix the
file declares (Turtle `@prefix`, RDF/XML `xmlns:`) for a namespace no IRI uses. A JSON-LD
`@context` never counts, and neither do the `rdf:`, `rdfs:`, `owl:`, `xsd:` and `xml:`
declarations that editors write into every file. `ONT003` mentions a licence the file names only
in an `SPDX-License-Identifier:` comment.

## Input safety

Ontologies are untrusted input, so the loader is deliberately strict:

- Parsing runs with the network disabled. Any socket, UDP or DNS attempt is blocked
  and reported (`SEC013`); a JSON-LD file with an external `@context` is
  refused (`SEC006`). `owl:imports` is never fetched; `--follow-imports` loads only local files.
- SHACL validation runs with the network disabled too: a socket or DNS attempt
  by a shape, even one pySHACL catches, makes `SHACL001` `failed` (exit `2`).
  It runs with `inference="none"` (no RDFS or OWL entailment is added to the data)
  and `advanced=True`, which admits SHACL-AF: SPARQL-based and custom targets,
  `sh:rule` (triple and SPARQL rules, applied once to a copy of the data graph)
  and SHACL functions; JavaScript extensions stay off. SPARQL-based constraints
  (`sh:sparql`) are SHACL Core and run whatever `advanced` says, so any shapes
  file, including one named by a PROF profile or imported as a shape library,
  can be slow: set `--max-validation-seconds` for shapes you did not write.
- Inputs and XML catalogs larger than `--max-input-bytes` (default 64 MiB), or inputs
  holding more than `--max-triples` triples (default 5,000,000), are rejected (`SEC001`,
  `SEC002`).
  Both can also be set in the `--config` policy file. With
  `--max-parse-seconds` a parse that runs too long is stopped (`SEC003`).
- Bounded: sizes and triple counts (always), ROBOT (`--robot-timeout`, 120 s by
  default) and, when you set a budget, parsing (`--max-parse-seconds`, `SEC003`)
  and SHACL validation (`--max-validation-seconds`, a `failed` `SHACL001`); those
  two run in a worker process that is stopped at the budget. Not bounded: the
  rule families, whose cost on large inputs is measured by `tests/test_scaling.py`.
- RDF/XML with external entities or nested entity expansion is refused
  (`SEC010`), compressed files are refused (`SEC011`), and relative paths that
  escape the working directory, or leave it through a symlink or a symlinked
  directory, are refused (`SEC009`).
- Rejected inputs are reported as `SECxxx: ...` on stderr with exit code `2`,
  like a parse failure. Post-parse hygiene checks (`SEC004`, `SEC005`,
  `SEC007`, `SEC008`, `SEC012`, `SEC014`) are ordinary findings; `SEC007` is an
  info note naming the `owl:imports` that were not followed. `SEC014` reports an
  IRI that embeds a password with the password masked
  (`https://alice:****@example.test/x`), so its report and baseline entries never
  repeat the password; the user name is still printed, so a token used as the
  user name (`https://<token>:x-oauth-basic@...`) is not masked. Other rules
  that report such an IRI still print it whole.

To report a vulnerability, see [SECURITY.md](SECURITY.md).

## Roadmap

[`data/rule_catalogue.csv`](https://github.com/arnaudgelas/ontolint/blob/main/data/rule_catalogue.csv) is the machine-readable
catalogue. It records 302 entries: 247 executable diagnostics and 55 proposed
candidates. The additional entry beyond the original roadmap is `TOOL001`, an
operational diagnostic for the linter itself. The 18 `OPS` entries of the
original roadmap describe command-line and report features, not checks on an
ontology; they moved to [docs/cli-features.md](https://github.com/arnaudgelas/ontolint/blob/main/docs/cli-features.md).
Thirteen further entries that cannot be specified soundly, or duplicate another rule, were
removed; see [docs/dropped-rules.md](https://github.com/arnaudgelas/ontolint/blob/main/docs/dropped-rules.md).

The next major areas are competency-question and ontology-diff rules (both need
a second input), reasoner-based semantic checks through ROBOT, safe
import-closure support, richer SHACL authoring checks, and network-based FAIR
checks.

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](https://github.com/arnaudgelas/ontolint/blob/main/LICENSE).
