<p align="center">
  <img src="logo.png" alt="ontolint logo" width="240">
</p>

# ontolint

`ontolint` is an offline ontology-quality linter for RDF graphs. It provides
graph-local checks for RDF/OWL, SKOS, lexical quality, class hierarchies, and
optional SHACL validation. It is a practical review aid—not a substitute for
OWL 2 DL validation, a reasoner, or expert ontology review.

## What it checks

The prototype defines 63 diagnostics:

- 59 Python graph checks for metadata, identifiers, labels, class hierarchies,
  OWL usage, SKOS, SHACL-shape quality, and governance.
- `INPUT001` for RDF parsing failures.
- `SHACL001` for optional pySHACL validation results.
- `TOOL001` for configuration and execution failures.
- `SEM001` for opt-in ROBOT OWL-profile validation failures.

Each finding includes a rule identifier, severity, focus, message, suggested
remediation, and confidence level. Rules are policy-oriented: a finding is not
automatically a logical inconsistency.

## Requirements and installation

Python 3.13 or later is required.

```bash
uv sync --group dev
```

For a standard `pip` environment, install the package and its test tools:

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

The command-line interface is a thin wrapper around the same Python library:

```bash
# Text report
uv run python -m ontolint.ontolint ontology.ttl \
  --base 'https://example.org/ont#'

# JSON report written to a file
uv run python -m ontolint.ontolint ontology.ttl \
  --base 'https://example.org/ont#' \
  --format json --output report.json

# Fail a CI job for warning- or error-level findings
uv run python -m ontolint.ontolint ontology.ttl --fail-on warning
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

### Discovering rules

```bash
uv run python -m ontolint.ontolint --version
uv run python -m ontolint.ontolint --list-rules                 # table
uv run python -m ontolint.ontolint --list-rules --format json   # machine-readable
uv run python -m ontolint.ontolint --explain SHQ001             # title, severity, fix, backend, scope, requirements
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
| `strict` | all | `ONT003` becomes `error` | `info` (any finding fails) |

Precedence when options combine:

1. The rule set is `--select` if given, else the profile's rules, else all rules. `--select`
   *replaces* the profile's selection.
2. Ignores always win over selection: `--ignore`, the profile's ignores and the policy file's
   `ignored_rules` are unioned and removed. Policy `ignored_rules` remain exact identifiers.
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
* Findings carry no line/column yet. The report model has an optional location slot that SARIF
  will turn into a `region` once rules can supply real positions.

### Several files

```bash
uv run python -m ontolint.ontolint ontologies/*.ttl --format sarif --output findings.sarif
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

### GitHub annotations

`--format github` is not available yet. Workflow-command annotations need a file *and a line*,
and findings carry no source locations. The escaping helpers (`%`, CR, LF and, for properties,
`:` and `,`) already exist in `ontolint.github`; the formatter is gated on location support.

### Optional SHACL validation

Pass a shapes graph with `--shapes` to enable pySHACL validation:

```bash
uv run python -m ontolint.ontolint ontology.ttl --shapes shapes.ttl
```

The integration uses `meta_shacl=True` and `advanced=True`. Newer SHACL draft
features are not guaranteed to be supported.

### OWL profile validation with ROBOT in Docker

Build the minimal project image once. Its final stage contains only the ROBOT
JAR and a non-root Java runtime:

```bash
docker build --tag ontolint-robot:1.9.11 docker/robot
uv run python -m ontolint.ontolint ontology.ttl --owl-profile DL
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
  "depth_limit": 7,
  "inheritance_limit": 3,
  "soup_limit": 15,
  "ignored_rules": ["CLS002"],
  "severity_overrides": {"ONT003": "error", "OWL005": "info"}
}
```

```bash
# Emit SARIF using a policy
uv run python -m ontolint.ontolint ontology.ttl \
  --config policy.json --format sarif --output findings.sarif

# Record accepted findings, then report only newly introduced ones
uv run python -m ontolint.ontolint ontology.ttl --write-baseline baseline.json
uv run python -m ontolint.ontolint ontology.ttl \
  --baseline baseline.json --fail-on warning
```

Baselines compare stable hashes of `(rule, focus, message)` (plus the report path for multi-file runs). They are useful for
incremental adoption, but are not semantic version comparisons.

## Development and quality checks

```bash
# Unit and property-based tests
uv run pytest -q

# Run tests in parallel
uv run pytest -q -n auto

# Mutation testing (opt-in)
uv run pytest --gremlins --no-cov --gremlin-parallel --gremlin-cache

# Lint the project
uv run ruff check .
```

Hypothesis tests generate RDF class hierarchies and verify that the linter's
cycle diagnostics agree with an independent reachability oracle. Mutation
testing is configured to target `src/ontolint/ontolint.py`.

### CI workflows

`.github/workflows/ci.yml` runs the fast PR checks (Ruff, mypy, pyright,
`pip-audit`, tests with coverage, package build). All actions are pinned to
commit SHAs and the uv version is pinned; Renovate keeps both current.

`.github/workflows/validation.yml` runs weekly and on manual dispatch:

- ROBOT Docker image build and smoke test (also on pull requests that touch
  `docker/` and carry the `validation` label). Logs are uploaded as artifacts.
- Mutation testing with the command above plus JSON/HTML reports, followed by
  `.github/scripts/mutation_gate.py`, which enforces the per-operator and
  overall thresholds. Reports are uploaded as artifacts.

The operators, thresholds, scope, waiver process and blocking/advisory rules
are defined in [docs/mutation-policy.md](docs/mutation-policy.md).

## Interpretation principles

1. RDF syntax validity and OWL logical consistency are different properties.
2. SHACL validation does not establish ontology-design quality.
3. Multiple RDFS domains or ranges are conjunctive, not alternative choices.
4. Under OWL's open-world assumption, missing evidence is not falsehood.
5. A subclass cycle is a review warning, not automatically an inconsistency.
6. `owl:allValuesFrom` does not imply the existence of a value.
7. A SKOS `broader` cycle is informational; it is not universally prohibited.
8. The linter does not fetch URLs or resolve `owl:imports` automatically.
9. Semantic OWL axioms are never auto-fixed because intent cannot be inferred
   reliably.

## Scope and limitations

- Use `--base` to restrict checks to a local namespace. Without it, every
  explicitly declared term is treated as local.
- Class-hierarchy analysis uses asserted `rdfs:subClassOf` statements; it does
  not calculate entailments or inspect an import closure.
- `CLS002` can be noisy for TBox-only ontologies and is often disabled in that
  profile.
- Shape coverage (`SHQ006`) checks direct instances and direct class targets
  only.
- Strongly connected components are calculated recursively, which can reach
  Python's recursion limit on unusually large graphs.
- SARIF output does not yet include source line or column locations.

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

## Roadmap

[`data/rule_catalogue.csv`](data/rule_catalogue.csv) is the machine-readable
catalogue. It records 329 entries: 63 executable diagnostics and 266 proposed
candidates. The additional entry beyond the original 328-rule roadmap is
`TOOL001`, an operational diagnostic for the linter itself.

The next major areas are comprehensive rule fixtures and false-positive cases,
OWLAPI/ROBOT and reasoner adapters, safe import-closure support, richer SHACL
authoring checks, ontology-diff regression testing, and opt-in publishing/FAIR
checks.

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).
