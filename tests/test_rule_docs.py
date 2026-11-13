"""The rule reference is generated; every page must be current and mention every catalogue rule.

``docs/rules.md`` is the index and ``docs/rules/<family>.md`` the family pages.  Only the staleness test
builds the pages, which takes seconds; the other page tests read the committed files, which it pins.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest
import rule_docs_generator
from planned_rule_intents import INTENTS
from rdflib import Graph
from rule_cases import load_cases
from rule_docs_generator import DOC, PAGES, _block, _code, _value, build, render, stale_pages, write_pages
from rule_harness import built, probed, rule_cases, ttl, with_shapes

from ontolint.catalogue import load_catalogue
from ontolint.models import LibraryMember, PatternLibrary, SharedIdentity
from ontolint.policy import Policy

PAGE_BUDGET = 500_000  # UTF-8 bytes; github.com stops rendering a Markdown file at about 512 KB


def _committed() -> dict[str, str]:
    """Return the committed pages, keyed like :func:`build`: ``rules.md`` and ``rules/<family>.md``."""
    pages = {"rules.md": DOC.read_text(encoding="utf-8")}
    pages.update({f"rules/{path.name}": path.read_text(encoding="utf-8") for path in PAGES.glob("*.md")})
    return pages


def _sections() -> dict[str, str]:
    """Return the entry of every implemented rule on the committed family pages, by rule id."""
    sections: dict[str, str] = {}
    for name, text in _committed().items():
        if name != "rules.md":
            for chunk in re.split(r"^#### ", text, flags=re.MULTILINE)[1:]:
                sections[chunk.split(":", 1)[0]] = re.split(r"^#{1,3} ", chunk, flags=re.MULTILINE)[0]
    return sections


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


def test_options_print_only_the_fields_a_case_sets_and_sets_sorted_at_every_depth() -> None:
    assert _value(Policy()) == "Policy()"
    assert _value(Policy(unknown_keys=("x",))) == "Policy(unknown_keys=('x',))"
    assert _value(frozenset({"b", "a"})) == "frozenset({'a', 'b'})"
    assert _value(frozenset({9, 10})) == "frozenset({10, 9})"  # sorted as text; ints iterate 9, 10 at any seed
    assert _value({"b", "a"}) == "{'a', 'b'}"
    assert _value(frozenset()) == "frozenset()"
    assert _value(set[str]()) == "set()"
    assert _value(("x", ["y", {"k": 1.5}])) == "('x', ['y', {'k': 1.5}])"
    member = LibraryMember("m.ttl", "file:///m.ttl", "https://example.test/m", frozenset({"b", "a"}))
    library = PatternLibrary("lib", (member,))
    assert _value(Policy(library=library)) == (
        "Policy(library=PatternLibrary(directory='lib', members=(LibraryMember(display='m.ttl', "
        "uri='file:///m.ttl', ontology='https://example.test/m', identities=frozenset({'a', 'b'})),)))"
    )
    shared = SharedIdentity("https://example.test/o", "ontology", "inputs", ("a.ttl", "b.ttl"), identical=False)
    assert _value(shared) == (
        "SharedIdentity(iri='https://example.test/o', kind='ontology', scope='inputs', members=('a.ttl', 'b.ttl'), "
        "identical=False)"
    )
    defaults = f"depth_limit={Policy().depth_limit}, inheritance_limit={Policy().inheritance_limit}"
    assert not [name for name, text in _committed().items() if defaults in text]


def test_every_case_of_every_rule_is_shown_in_order() -> None:
    sections = _sections()
    for rule_id, cases in load_cases().items():
        expected = [f"*Flagged:* {_code(case.name)}" for case in cases.positive]
        expected += [f"*Clean:* {_code(case.name)}" for case in cases.negative]
        shown = [line for line in sections[rule_id].splitlines() if line.startswith(("*Flagged:* ", "*Clean:* "))]
        assert len(shown) == len(expected), rule_id
        for line, start in zip(shown, expected, strict=True):
            assert line == start or line.startswith(f"{start} ("), (rule_id, line)


def test_every_flagged_graph_case_shows_its_message() -> None:
    sections = _sections()
    total = 0
    for rule_id, cases in load_cases().items():
        graph_cases = sum(1 for case in cases.positive if case.probe is None)
        reported = [line for line in sections[rule_id].splitlines() if line.startswith("Reported: ")]
        assert len(reported) == graph_cases, rule_id
        total += graph_cases
    assert total > len(sections)  # 778 messages for 249 rules when this test was written


def test_a_case_is_labelled_by_how_it_is_made_and_shows_its_options() -> None:
    label = "(run through the command line or an adapter; see `tests/rule_cases/`)"
    assert _block("Flagged", probed("cli", lambda: ["TOOL001"])) == [f"*Flagged:* `cli` {label}", ""]
    assert _block("Clean", ttl("empty", "")) == ["*Clean:* `empty` (the empty data graph)", ""]
    assert _block("Flagged", ttl("empty", " \n", policy=Policy(unknown_keys=("k",)))) == [
        "*Flagged:* `empty` (the empty data graph)",
        "",
        "Linter options: `policy=Policy(unknown_keys=('k',))`.",
        "",
    ]
    assert _block("Flagged", with_shapes("shapes only", "", "ex:S a sh:NodeShape .")) == [
        "*Flagged:* `shapes only` (the empty data graph)",
        "",
        "Shapes graph:",
        "",
        "```turtle",
        "ex:S a sh:NodeShape .",
        "```",
        "",
    ]
    assert _block("Clean", built("relative", Graph, base="https://example.test/")) == [
        "*Clean:* `relative` (built programmatically; see `tests/rule_cases/`)",
        "",
        "Linter options: `base='https://example.test/'`.",
        "",
    ]


def test_names_messages_and_turtle_cannot_break_out_of_their_code(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _code("plain") == "`plain`"
    assert _code("a`b") == "``a`b``"
    assert _code("`x") == "`` `x ``"
    assert _code("x``") == "``` x`` ```"
    assert _code(" both ") == "`  both  `"
    assert _code(" ") == "` `"
    with pytest.raises(ValueError, match="empty"):
        _code("")
    assert _block("Flagged", ttl("x <http://x.test/> [y]", "ex:A a owl:Class ."))[0] == (
        "*Flagged:* `x <http://x.test/> [y]`"
    )
    assert _block("Flagged", ttl("fence", 'ex:A rdfs:comment "```" .'))[2:5] == [
        "````turtle",
        'ex:A rdfs:comment "```" .',
        "````",
    ]
    case = ttl("undeclared", "ex:A rdfs:subClassOf ex:B .")
    with pytest.raises(ValueError, match="case name"):
        render({"OWL001": rule_cases([ttl("two\nlines", case.turtle)], [case])})
    monkeypatch.setattr(rule_docs_generator, "_first_message", lambda rule_id, case: "two\rlines")
    with pytest.raises(ValueError, match="message"):
        render({"OWL001": rule_cases([case], [case])})


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
