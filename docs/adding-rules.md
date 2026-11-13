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
   * `def run(ctx: RuleContext) -> None` -- emit with `ctx.add(rule_id, focus, message, confidence=...,
     subject=...)`.
     `subject` is what tells this finding from another of the same rule on the same focus: the
     predicate, the other term, the literal (in N3, with its language), the language tag. Pass it
     in a fixed order, sorted where it is a set. Never put prose, counts, ratios, thresholds or
     labels quoted for readability in it: with the rule and the focus, the subject is the
     finding's identity, independent of how its message is worded. A baseline matches findings
     by that identity, so a reworded message, or a measurement that changes, does not reopen an
     accepted finding, and two problems that share a subject would hide each other.
     `tests/test_subject_contract.py` fails for an add site with a computed message, or of a rule
     with several add sites, that does not pass `subject=`.
     `subject=()` says that the rule reports at most one finding per focus.
     In `message`, write a term that may be a blank node with `term_text` (an RDF term),
     `value_text` (as `str()` would, but a blank node `_:label`) or `quoted_text` (a quoted value),
     never with `{node}` or `str(node)`: `RuleContext` rewrites only `_:label` to the node's stable
     identity, so a bare label would leave the parser's own label in the message.
     Use `ctx.context` (pre-built indexes), `ctx.classes`, `ctx.local(...)`, and helpers in
     `rules/support.py`; do not re-scan the graph per term.
   * Import `RuleContext` under `if TYPE_CHECKING:` (the module must not import `runtime` at run
     time; `specs.py` imports every module).
   * Write each rule's specification in the module docstring as a top-level bullet,
     `* **ABC001.** text` (`* **ABC001 / ABC002.** text` for one text that specifies two rules), its
     continuation lines indented two spaces and the bullet ended by a blank line, the next bullet or an
     unindented paragraph. The rest of the docstring holds what the module's rules share. Both are
     rendered in `docs/rules/<family>.md`, so the generator refuses a bullet header it would misread
     (`* **ABC001.**text`) and a paragraph that would start a Markdown block (`#`, `>`, `-`, `1.`,
     `<` ...).
   * Thresholds belong on `Policy`, never as magic numbers hidden in the rule.
3. **Register it** with one line in `RULE_MODULES` in `src/ontolint/rules/builtin.py`.  Append at the end:
   order is observable (first emission wins de-duplication).  Registration derives the registry,
   the engine's execution order, `SEVERITY` and `FIXES`.  Rules that need an adapter or the CLI front
   end instead of a graph `run` go in `rules/external.py` with `module=""`.  A family that must never run by default
   (like `OBO` and `FAIR`) is added to `OPT_IN_FAMILIES` in `src/ontolint/profiles.py`, with a profile if useful.
4. **Flip the catalogue rows** to `implemented` in `data/rule_catalogue.csv` and copy the file to
   `src/ontolint/data/rule_catalogue.csv`.  Keep `title`, `family` and `category` identical to the
   spec.  Update `CATALOGUE_ROW_COUNT` in `tests/test_registry.py` if rows were added or removed (`IMPLEMENTED_COUNT` is derived), and drop the ids from `tests/planned_rule_intents.py`.
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

   A rule whose message names a value that may be a blank node needs a positive case where it is one
   (`ex:p rdfs:range [ ... ]`): `tests/test_rule_cases.py` runs every case with every rule and fails
   when a message holds a parser's blank-node label, but only for the messages a case reaches.

   Use `built(...)` for inputs Turtle cannot express, `with_shapes(...)` for shape rules,
   `probed(...)` for adapter/CLI rules, and `threshold_cases(option, limit, factory)` for any
   `> limit` policy threshold (it emits the at-limit negative and limit+1 positive).  Odd inputs
   (empty graph, blank-node focus, literals where IRIs are expected, huge literals, unicode,
   malformed lists) are fed to every rule module automatically by `tests/test_rule_cases.py`; add
   family-specific hostile inputs to your case file if the rule has special structure.
6. **Regenerate the rule reference and run the gate**:
   `uv run python tests/rule_docs_generator.py` regenerates `docs/rules.md` and `docs/rules/*.md`;
   `tests/test_rule_docs.py` fails while any page is stale. Every Markdown file in `docs/rules/` is
   generated: the generator deletes any other. Then run
   `uv run python scripts/gate.py --fix`. It applies Ruff formatting and autofixes, then runs exactly
   the checks CI runs: format check, Ruff, Pyright, mypy (host and Win32), `pytest -n auto -W error`,
   `pip-audit` and `uv build`. Without `--fix` it only checks, as CI does.
   If your rules change the kitchen-sink/golden output, review `tests/golden/differential.json` with
   the maintainer; do not regenerate it casually.
   A new positive case also needs `tests/golden/identities.json`, the baseline identity of every
   positive case: regenerate it with `ONTOLINT_UPDATE_GOLDEN=1 uv run pytest tests/test_identity_golden.py`
   and check that the diff only adds your cases. A changed or removed entry means a finding's
   focus or subject changed, so baselines stop accepting it by identity: say why in that test's
   docstring ("Deliberate identity change") and give the release an upgrade note naming the rule.
   A pySHACL or rdflib upgrade that changes a `SHACL001` subject brings the same duty: SHACL001's
   own cases are probes, so the file pins it through the shape and data pairs of `SHACL_CASES` in
   that test (one per constraint family, `sh:message`, a blank shape, a nested `sh:node`). Probe
   cases of the other adapters and of the CLI front end (SEM001, INPUT001, TOOL001) are not pinned:
   check a change to their subject by hand.

## What the tests enforce

| Test | Guarantees |
| --- | --- |
| `test_rule_modules.py` | module list consistent (`validate_modules`), each module emits only its own `SPECS`, catalogue status matches registration, proposed rules are never reported as executed |
| `test_rule_cases.py` | every implemented rule has positive and negative cases, positives fire exactly the rule, negatives do not, no message prints a parser's blank-node label, no rule module crashes on odd inputs, large hierarchies do not recurse |
| `test_registry.py` | reachability of every graph rule, spec/catalogue field agreement, execution-status semantics |
| `test_subject_contract.py` | every add site that needs a `subject=` passes one, and no two findings of a corpus or random run share rule, focus and subject |
| `test_rule_docs.py` | the rule reference is current, lists every catalogue rule, and shows every case and every specification bullet under each rule it names; no page exceeds 500,000 bytes |
| `test_identity_golden.py` | the rule, focus, subject and baseline identity of each finding of every positive graph case and of the SHACL001 cases of `SHACL_CASES` equal `tests/golden/identities.json`, so a change to a rule's subject shows in review (probe cases are not covered) |

A `proposed` rule must not appear in `CASES` or the registry; `execute()` reports a rule as
`executed` only when its module or adapter actually ran.
