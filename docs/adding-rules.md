# Adding rules

A new rule family touches **one new source file, one new test file and the catalogue**.  No shared
file other than a single registration line (and the catalogue CSV rows) is edited, so several people
or agents can add families in parallel.

The catalogue (`data/rule_catalogue.csv`, mirrored byte-for-byte in `src/ontolint/data/`) is the
authority on what is planned: a rule is `proposed` until it is implemented, and a registered rule
must be `implemented`.  `--list-rules` shows proposed and unsupported rules separately, and a test
guarantees that proposed rules are never reported as executed.

## Steps

1. **Pick the rows.**  Find your rules in `data/rule_catalogue.csv`.  The row's `backend` and
   `test_requirement` tell you what is expected.  Rules that need a backend ontolint does not have
   (SPARQL runner, OWL reasoner, ontology diff, network) stay `proposed`; do not fake them with
   RDFLib approximations.
2. **Write the module** `src/ontolint/rules/<family>.py`:
   * `SPECS: tuple[RuleSpec, ...]` -- one `RuleSpec` per rule (id, family prefix, title matching the
     catalogue, severity, suggestion, category, backend, scope, `module="<family>"`);
   * `def run(ctx: RuleContext) -> None` -- emit with `ctx.add(rule_id, focus, message, confidence=...)`.
     Use `ctx.context` (pre-built indexes), `ctx.classes`, `ctx.local(...)`, and helpers in
     `rules/support.py`; do not re-scan the graph per term.
   * Import `RuleContext` under `if TYPE_CHECKING:` (the module must not import `runtime` at run
     time; `specs.py` imports every module).
   * Thresholds belong on `Policy`, never as magic numbers hidden in the rule.
3. **Register it** with one line in `RULE_MODULES` in `src/ontolint/rules/builtin.py`.  Append at the end:
   order is observable (first emission wins de-duplication).  Registration derives the registry,
   the engine's execution order, `SEVERITY` and `FIXES`.  Rules that need an adapter or the CLI front
   end instead of a graph `run` go in `rules/external.py` with `module=""`.
4. **Flip the catalogue rows** to `implemented` in `data/rule_catalogue.csv` and copy the file to
   `src/ontolint/data/rule_catalogue.csv`.  Keep `title`, `family` and `category` identical to the
   spec.  Update the counts (`CATALOGUE_ROW_COUNT`/`IMPLEMENTED_COUNT` in `tests/test_registry.py`).
   The `test_requirement` column is a contract: satisfy it with the tests below.
5. **Add per-rule tests** in `tests/rule_cases/<family>.py` exporting `CASES` (see
   `tests/rule_harness.py`).  For **every** rule provide at least one positive and one negative case:

   ```python
   from rule_harness import rule_cases, ttl

   CASES = {
       "ABC001": rule_cases(
           [ttl("no label", "ex:A a owl:Class .")],  # fires, and only ABC001 is selected
           [ttl("labelled", 'ex:A a owl:Class ; rdfs:label "A" .')],  # does not fire
       ),
   }
   ```

   Use `built(...)` for inputs Turtle cannot express, `with_shapes(...)` for shape rules,
   `probed(...)` for adapter/CLI rules, and `threshold_cases(option, limit, factory)` for any
   `> limit` policy threshold (it emits the at-limit negative and limit+1 positive).  Odd inputs
   (empty graph, blank-node focus, literals where IRIs are expected, huge literals, unicode,
   malformed lists) are fed to every rule module automatically by `tests/test_rule_cases.py`; add
   family-specific hostile inputs to your case file if the rule has special structure.
6. **Run the gate**:
   `uv run ruff format && uv run ruff format --check && uv run ruff check --fix && uv run pyright && uv run mypy && uv run mypy --platform win32 && uv run pytest -n auto -W error`.
   If your rules change the kitchen-sink/golden output, review `tests/golden/differential.json` with
   the maintainer; do not regenerate it casually.

## What the tests enforce

| Test | Guarantees |
| --- | --- |
| `test_rule_modules.py` | module list consistent (`validate_modules`), each module emits only its own `SPECS`, catalogue status matches registration, proposed rules are never reported as executed |
| `test_rule_cases.py` | every implemented rule has positive and negative cases, positives fire exactly the rule, negatives do not, no rule module crashes on odd inputs, large hierarchies do not recurse |
| `test_registry.py` | reachability of every graph rule, spec/catalogue field agreement, execution-status semantics |

A `proposed` rule must not appear in `CASES` or the registry; `execute()` reports a rule as
`executed` only when its module or adapter actually ran.
