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
  <a href="https://github.com/arnaudgelas/ontolint/blob/main/docs/rules.md"><img alt="Rules implemented: 240 of 295" src="https://img.shields.io/badge/rules-240%2F295_implemented-brightgreen"></a>
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

240 of the 295 catalogue rules are implemented; the rest are planned. The
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
python -m pip install pytest hypothesis pytest-gremlins pytest-xdist
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
| `2` | Tool failure: unreadable input or configuration, an unknown rule selector, a usage error, or a requested rule that `failed` or is `unsupported` (for example `--owl-profile` without Docker). |

Exit `2` outranks `1`: when a requested backend did not deliver a verdict the run cannot
pass, even with `--fail-on never`. The report is still written so you can see why. Rules that
are `skipped` (no shapes supplied, no OWL profile requested, ignored) never change the exit code.

Two advisory messages go to stderr and never change the exit code or the report:
`TOOL002` warns that `--base` selects none of the declared terms, and `TOOL003` notes that a
linted file looks like a SHACL shapes graph (more shapes than declared terms), which should
probably be passed with `--shapes` instead. With `--follow-imports`, `TOOL004` notes a catalog
entry that names a missing file.

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
   (`GOV020`, exit 2), so a typo cannot silently leave a rule running.
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
  scope, requirements, suggestion), `execution_summary` and per-file `files[].executions`.
* SARIF 2.1.0 adds `tool.driver.rules` (name, short/full description, help,
  `defaultConfiguration.level`, category/backend/scope properties), `ruleIndex` and an
  `artifactLocation` on every result, and a run `invocation`. Skipped, unsupported and failed
  rules are `toolExecutionNotifications` (levels `note`, `warning`, `error`);
  `executionSuccessful` is `false` when any rule failed or is unsupported.
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
* Fingerprints: a single-file run hashes `(rule, focus, message)` exactly as before, so existing
  baselines keep working. A multi-file run also hashes the report path so identical findings in
  two files stay distinct; a baseline written from one file therefore does not carry over to a
  multi-file run. Write multi-file baselines from multi-file runs.

### Modular ontologies: following `owl:imports`

By default each file is linted alone, so an umbrella ontology that only `owl:imports` its modules
checks almost nothing (`SEC007` lists the imports that were not followed). With
`--follow-imports`, ontolint loads the import closure from local files and lints it as one graph:

```bash
ontolint ontology.ttl --follow-imports                  # uses catalog-v001.xml next to ontology.ttl
ontolint ontology.ttl --catalog path/to/catalog-v001.xml  # an explicit catalog (implies --follow-imports)
```

Imports resolve through an OASIS XML catalog (the Protégé, ROBOT and ODK `catalog-v001.xml`:
`uri` entries, also inside `group`, and `rewriteURI` prefixes) or as `file:` IRIs; the network is
never used, and imports that do not resolve stay listed by `SEC007`. The catalog next to each
imported file is consulted before the root catalog, as Protégé does, and an import naming a file
already in the closure by its ontology or version IRI needs no entry. A catalog entry whose file
does not exist leaves the import unresolved, with a `TOOL004` note, rather than failing the run.
Every resolved file must lie inside the import root after symlinks are followed (`SEC009`): by
default the enclosing git repository of the catalog (or of the input without a catalog), so
catalogs may point at sibling directories (`../modules/x.ttl`), or the directory given with
`--import-root DIR`. Each file passes the usual safe loader, and the closure is bounded by
`max_import_depth` (16), `max_imported_files` (100) and `max_triples` as a whole (`SEC015`).
Cycles end and a module imported twice is loaded once. The headers of imported modules do not
count as extra ontologies for `ONT002`.

A finding belongs to the module that declares its focus (gives it an `rdf:type`), or else to the
first module that mentions it: JSON gives that module's `path`, SARIF its `artifactLocation` and
region, and text adds an `In:` line. Baseline fingerprints are unchanged, so a closure baseline
keeps matching.

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
only results about the linted file's own nodes, and the term rules still judge the data file alone.

```bash
ontolint data.ttl --shapes shapes.ttl --follow-imports   # shapes.ttl imports the ontology
```

### GitHub annotations

`--format github` is not available yet. The escaping helpers (`%`, CR, LF and, for properties,
`:` and `,`) already exist in `ontolint.github`; a formatter has not yet been added.

### Optional SHACL validation

Pass a shapes graph with `--shapes` to enable pySHACL validation:

```bash
ontolint ontology.ttl --shapes shapes.ttl
```

The integration uses `meta_shacl=True` and `advanced=True`. Newer SHACL draft
features are not guaranteed to be supported.

Each SHACL result becomes a `SHACL001` finding at the result's own severity:
`sh:Violation` is `error`, `sh:Warning` is `warning` and `sh:Info` is `info`, so
warnings-only data passes the default `--fail-on error`. A custom severity is
reported as `error` and named in the message. Blank-node shapes and focus nodes
are named by a content-stable identity, so baselines keep matching across runs.

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
  "max_parse_seconds": 60
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
in-process load.

```bash
# Emit SARIF using a policy
ontolint ontology.ttl \
  --config policy.json --format sarif --output findings.sarif

# Record accepted findings, then report only newly introduced ones
ontolint ontology.ttl --write-baseline baseline.json
ontolint ontology.ttl \
  --baseline baseline.json --fail-on warning
```

Baselines compare stable hashes of `(rule, focus, message)` (plus the report path for multi-file runs). They are useful for
incremental adoption, but are not semantic version comparisons.

A baseline entry that matches no finding of the run is *stale*: the finding was fixed, or its rule
was not selected this time. Every format reports stale entries (a note in text and SARIF, the list
`baseline.stale_fingerprints` in JSON), and `--fail-on-stale-baseline` makes them exit `1` so CI
asks for the baseline to be regenerated. Run with the same rule selection that wrote the baseline,
or entries for unselected rules will count as stale.

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

# Type checks
uv run pyright && uv run mypy && uv run mypy --platform win32

# Mutation testing (opt-in)
uv run pytest -m 'not slow' --gremlins --no-cov --gremlin-parallel --gremlin-cache

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
  `obo:IAO_0000115`, `obo:IAO_0000600` and `prov:definition`; labels from `rdfs:label` and `skos:prefLabel`.
  Add more with the policy lists `extra_definition_predicates` and `extra_label_predicates` (absolute IRIs).
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
Those mappings are traceability aids, not claims of identical behavior.

## Input safety

Ontologies are untrusted input, so the loader is deliberately strict:

- Parsing runs with the network disabled. Any socket or DNS attempt is blocked
  and reported (`SEC013`); a JSON-LD file with an external `@context` is
  refused (`SEC006`). `owl:imports` is never fetched; `--follow-imports` loads only local files.
- Inputs larger than `--max-input-bytes` (default 64 MiB) or holding more than
  `--max-triples` triples (default 5,000,000) are rejected (`SEC001`, `SEC002`).
  Both can also be set in the `--config` policy file. With
  `--max-parse-seconds` a parse that runs too long is stopped (`SEC003`).
- RDF/XML with external entities or nested entity expansion is refused
  (`SEC010`), compressed files are refused (`SEC011`), and relative paths that
  escape the working directory or symlinks that leave it are refused (`SEC009`).
- Rejected inputs are reported as `SECxxx: ...` on stderr with exit code `2`,
  like a parse failure. Post-parse hygiene checks (`SEC004`, `SEC005`,
  `SEC007`, `SEC008`, `SEC012`, `SEC014`) are ordinary findings; `SEC007` is an
  info note naming the `owl:imports` that were not followed.

To report a vulnerability, see [SECURITY.md](SECURITY.md).

## Roadmap

[`data/rule_catalogue.csv`](https://github.com/arnaudgelas/ontolint/blob/main/data/rule_catalogue.csv) is the machine-readable
catalogue. It records 295 entries: 240 executable diagnostics and 55 proposed
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
