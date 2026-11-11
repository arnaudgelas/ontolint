"""validate_modules reports a rule id declared both by a rule module and by the external specs."""

from __future__ import annotations

import pytest

from ontolint.models import RuleBackend, RuleSpec
from ontolint.rules import builtin


def test_an_external_spec_reusing_a_module_rule_id_is_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    taken = builtin.module_specs(builtin.RULE_MODULES[0])[0]
    clash = RuleSpec(
        taken.rule_id, "fam", "title", taken.severity, "fix", "cat", RuleBackend.PYSHACL, taken.scope, module=""
    )
    monkeypatch.setattr(builtin, "EXTERNAL_SPECS", (clash,))

    problems = builtin.validate_modules(builtin.RULE_MODULES[:1])

    owner = builtin.module_name(builtin.RULE_MODULES[0])
    assert f"{taken.rule_id}: declared in both {owner} and external" in problems
