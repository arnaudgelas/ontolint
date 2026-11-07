# ontolint

`ontolint` is an offline ontology-quality linter for RDF graphs. It provides
graph-local checks for RDF/OWL, SKOS, lexical quality, class hierarchies, and
optional SHACL validation. It is a practical review aid—not a substitute for
OWL 2 DL validation, a reasoner, or expert ontology review.

## What it checks

The prototype defines 62 diagnostics:

- 59 Python graph checks for metadata, identifiers, labels, class hierarchies,
  OWL usage, SKOS, SHACL-shape quality, and governance.
- `INPUT001` for RDF parsing failures.
- `SHACL001` for optional pySHACL validation results.
- `TOOL001` for configuration and execution failures.

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
| `2` | The tool could not parse input or load configuration. |

### Optional SHACL validation

Pass a shapes graph with `--shapes` to enable pySHACL validation:

```bash
uv run python -m ontolint.ontolint ontology.ttl --shapes shapes.ttl
```

The integration uses `meta_shacl=True` and `advanced=True`. Newer SHACL draft
features are not guaranteed to be supported.

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

Baselines compare stable hashes of `(rule, focus, message)`. They are useful for
incremental adoption, but are not semantic version comparisons.

## Development and quality checks

```bash
# Unit and property-based tests
uv run pytest -q

# Run tests in parallel
uv run pytest -q -n auto

# Mutation testing (opt-in)
uv run pytest --gremlins --gremlin-parallel --gremlin-cache

# Lint the project
uv run ruff check .
```

Hypothesis tests generate RDF class hierarchies and verify that the linter's
cycle diagnostics agree with an independent reachability oracle. Mutation
testing is configured to target `src/ontolint/ontolint.py`.

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
catalogue. It records 329 entries: 62 executable diagnostics and 267 proposed
candidates. The additional entry beyond the original 328-rule roadmap is
`TOOL001`, an operational diagnostic for the linter itself.

The next major areas are comprehensive rule fixtures and false-positive cases,
OWLAPI/ROBOT and reasoner adapters, safe import-closure support, richer SHACL
authoring checks, ontology-diff regression testing, and opt-in publishing/FAIR
checks.
