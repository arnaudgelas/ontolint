"""``docs/rules.md`` is generated; it must be current and mention every catalogue rule."""

from __future__ import annotations

import logging

from planned_rule_intents import INTENTS
from rule_docs_generator import DOC, build

from ontolint.catalogue import load_catalogue


def test_rule_reference_is_current() -> None:
    logging.getLogger("rdflib").setLevel(logging.ERROR)
    assert DOC.read_text(encoding="utf-8") == build(), (
        "docs/rules.md is stale: run `uv run python tests/rule_docs_generator.py`"
    )


def test_every_catalogue_rule_is_documented() -> None:
    text = DOC.read_text(encoding="utf-8")
    for row in load_catalogue():
        heading = f"#### {row.rule_id}:"
        listed = f"| {row.rule_id} | TODO |"
        assert (heading in text) if row.status.value == "implemented" else (listed in text), row.rule_id


def test_every_proposed_rule_has_an_intent_and_no_other_does() -> None:
    proposed = {row.rule_id for row in load_catalogue() if row.status.value != "implemented"}
    assert set(INTENTS) == proposed
    assert all(text.strip() for text in INTENTS.values())


def test_readme_rule_counts_match_the_catalogue() -> None:
    rows = load_catalogue()
    done = sum(1 for row in rows if row.status.value == "implemented")
    readme = (DOC.parent.parent / "README.md").read_text(encoding="utf-8")
    assert f"rules-{done}%2F{len(rows)}_implemented" in readme
    assert f"{done} of the {len(rows)} catalogue rules are implemented" in readme
    assert f"{done} executable diagnostics and {len(rows) - done} proposed" in readme
