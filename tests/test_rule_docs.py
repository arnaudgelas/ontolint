"""The rule reference is generated; every page must be current and mention every catalogue rule.

``docs/rules.md`` is the index and ``docs/rules/<family>.md`` the family pages.  Only the staleness test
builds the pages, which takes seconds; the other page tests read the committed files, which it pins.
"""

from __future__ import annotations

import logging
from pathlib import Path

from planned_rule_intents import INTENTS
from rule_docs_generator import DOC, PAGES, build, stale_pages, write_pages

from ontolint.catalogue import load_catalogue

PAGE_BUDGET = 500_000  # UTF-8 bytes; github.com stops rendering a Markdown file at about 512 KB


def _committed() -> dict[str, str]:
    """Return the committed pages, keyed like :func:`build`: ``rules.md`` and ``rules/<family>.md``."""
    pages = {"rules.md": DOC.read_text(encoding="utf-8")}
    pages.update({f"rules/{path.name}": path.read_text(encoding="utf-8") for path in PAGES.glob("*.md")})
    return pages


def test_rule_reference_is_current() -> None:
    logging.getLogger("rdflib").setLevel(logging.ERROR)
    stale = stale_pages(build())
    assert not stale, f"rule reference pages {stale}: run `uv run python tests/rule_docs_generator.py`"


def test_every_catalogue_rule_is_documented() -> None:
    pages = _committed()
    for row in load_catalogue():
        family = f"rules/{row.family.lower()}.md"
        assert f"| [{row.rule_id}]({family}) |" in pages["rules.md"], row.rule_id
        heading = f"#### {row.rule_id}:"
        listed = f"| {row.rule_id} | TODO |"
        assert (heading in pages[family]) if row.status.value == "implemented" else (listed in pages[family]), (
            row.rule_id
        )


def test_every_page_renders_on_github() -> None:
    for name, text in _committed().items():
        assert len(text.encode("utf-8")) < PAGE_BUDGET, name


def test_stale_missing_and_orphan_pages_are_reported_and_other_files_ignored(tmp_path: Path) -> None:
    pages = {"rules.md": "index\n", "rules/a.md": "a\n", "rules/b.md": "b\n"}
    write_pages(pages, tmp_path)
    assert stale_pages(pages, tmp_path) == []
    (tmp_path / "rules" / "a.md").write_text("edited\n", encoding="utf-8")
    (tmp_path / "rules" / "b.md").unlink()
    (tmp_path / "rules" / "extra.md").write_text("hand-written\n", encoding="utf-8")
    (tmp_path / "rules" / ".DS_Store").write_bytes(b"\0")
    assert stale_pages(pages, tmp_path) == ["rules/a.md (stale)", "rules/b.md (missing)", "rules/extra.md (orphan)"]
    write_pages(pages, tmp_path)
    assert stale_pages(pages, tmp_path) == []
    assert not (tmp_path / "rules" / "extra.md").exists()
    assert (tmp_path / "rules" / ".DS_Store").read_bytes() == b"\0"


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
