"""The rule reference is generated; every page must be current and mention every catalogue rule.

``docs/rules.md`` is the index and ``docs/rules/<family>.md`` the family pages.  Only the staleness test
builds the pages, which takes seconds; the other page tests read the committed files, which it pins.
The docstring parser that turns each rule's ``* **ID.**`` bullet into its specification is tested on
fake modules, on the real ones, rewrapped, and on random docstrings.
"""

from __future__ import annotations

import inspect
import logging
import re
import string
import textwrap
import types
from collections import Counter
from pathlib import Path

import pytest
import rule_docs_generator
from hypothesis import given
from hypothesis import strategies as st
from hypothesis_strategies import budget
from planned_rule_intents import INTENTS
from rdflib import Graph
from rule_cases import load_cases
from rule_docs_generator import (
    DOC,
    PAGES,
    SPEC_BULLET,
    _block,
    _code,
    _markdown,
    _prose,
    _reflow,
    _value,
    build,
    read_module,
    render,
    spec_modules,
    specifications,
    stale_pages,
    write_pages,
)
from rule_harness import built, probed, rule_cases, ttl, with_shapes

from ontolint.catalogue import load_catalogue
from ontolint.models import LibraryMember, PatternLibrary, SharedIdentity
from ontolint.policy import Policy
from ontolint.rules.builtin import RULE_MODULES
from ontolint.rules.registry import default_registry

PAGE_BUDGET = 500_000  # UTF-8 bytes; github.com stops rendering a Markdown file at about 512 KB
SPECIFIED_RULES_FLOOR = 115  # rules with a specification bullet (114 bullets) when this test was written


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


def _fake(doc: str | None) -> types.ModuleType:
    """Return a module named ``fake`` with this docstring."""
    return types.ModuleType("fake", doc)


def _real_specs() -> dict[str, tuple[str, str]]:
    """Return every real rule's home module and specification, as the generator reads them."""
    return specifications([read_module(module) for module in spec_modules()])


def _notes(page: str) -> str:
    """Return the module notes of a family page: from ``## Modules`` to ``## Rules``."""
    return page.split("\n## Rules\n", 1)[0].split("\n## Modules\n", 1)[-1] if "\n## Modules\n" in page else ""


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
        render({"OWL001": rule_cases([ttl("two\nlines", case.turtle)], [case])}, spec_modules())
    monkeypatch.setattr(rule_docs_generator, "_first_message", lambda rule_id, case: "two\rlines")
    with pytest.raises(ValueError, match="message"):
        render({"OWL001": rule_cases([case], [case])}, spec_modules())


def test_titles_fixes_and_intents_keep_their_angle_brackets() -> None:
    assert _prose("Use .../obo/<id>.owl") == "Use .../obo/\\<id>.owl"
    assert _prose("Encode < > \\ ^") == "Encode \\< > \\\\ ^"
    entries = [
        line
        for page in _committed().values()
        for line in page.splitlines()
        if line.startswith(("#### ", "- **Fix:** ", "| "))
    ]
    assert (
        "- **Fix:** Use .../obo/\\<id>.owl and a version IRI such as .../obo/\\<id>/releases/YYYY-MM-DD/\\<id>.owl."
        in (entries)
    )
    assert not [line for line in entries if re.search(r"(?<!\\)<", re.sub(r"`[^`]*`", "", line))]


def test_a_bullet_ends_at_its_first_unindented_line() -> None:
    doc = read_module(
        _fake(
            "Fake rules.\n\n"
            "* **A001.** First\n  rule.\nFixtures: none.\n"
            "* **A002.**\n  Header only,\n  then text.\n"
            "* **A003.** Next bullet.\n"
            "* **A004.** Ends at a blank line.\n\n"
            "Closing words.\n"
        )
    )
    assert doc.name == "fake"
    assert doc.specs == {
        "A001": "First rule.",
        "A002": "Header only, then text.",
        "A003": "Next bullet.",
        "A004": "Ends at a blank line.",
    }
    assert doc.notes == (
        "Fake rules.",
        "",
        "*Specified under each rule: A001.*",
        "",
        "Fixtures: none.",
        "",
        "*Specified under each rule: A002, A003, A004.*",
        "",
        "Closing words.",
    )
    for header in ("* **A001.**text", "* **A001** text", "* **A001 /A002.** x"):
        with pytest.raises(ValueError, match="fake"):
            read_module(_fake(f"Fake.\n\n{header}\n"))
    with pytest.raises(ValueError, match="empty"):
        read_module(_fake("Fake.\n\n* **A001.**\n"))


def test_a_bullet_naming_two_rules_specifies_both() -> None:
    assert read_module(_fake("Fake.\n\n* **A001 / A002.** Shared\n  text.\n")).specs == {
        "A001": "Shared text.",
        "A002": "Shared text.",
    }
    sections = _sections()
    shared = _real_specs()["OWL005"][1]
    assert _real_specs()["OWL006"][1] == shared
    assert f"**Specification.** {shared}" in sections["OWL005"]
    assert f"**Specification.** {shared}" in sections["OWL006"]


def test_a_rule_specified_twice_or_not_implemented_is_refused() -> None:
    with pytest.raises(ValueError, match="twice"):
        read_module(_fake("Fake.\n\n* **A001.** One.\n* **A001.** Two.\n"))
    one = read_module(types.ModuleType("ontolint.rules.one", "One.\n\n* **A001.** One.\n"))
    two = read_module(types.ModuleType("ontolint.rules.two", "Two.\n\n* **A001.** Two.\n"))
    with pytest.raises(ValueError, match="A001 is specified in both one and two"):
        specifications([one, two])
    with pytest.raises(ValueError, match="ZZZ999"):
        render({}, [*spec_modules(), _fake("Fake.\n\n* **ZZZ999.** Unknown.\n")])
    with pytest.raises(ValueError, match="OWL001 is specified in both"):
        render({}, [*spec_modules(), _fake("Fake.\n\n* **OWL001.** Again.\n")])


def test_sphinx_roles_become_code_spans() -> None:
    assert _markdown(":func:`~.support.list_items`") == "`support.list_items`"
    assert _markdown("see :mod:`ontolint.ownership` and :data:`~.support.LITERAL_RANGES`.") == (
        "see `ontolint.ownership` and `support.LITERAL_RANGES`."
    )
    assert _markdown("``literal`` stays") == "``literal`` stays"
    with pytest.raises(ValueError, match="explicit title"):
        _markdown(":mod:`the owner <ontolint.ownership>`")
    for name, page in _committed().items():
        rendered = [line for line in page.splitlines() if line.startswith("**Specification.** ")]
        assert not [line for line in [*rendered, _notes(page)] if re.search(r":[a-z]+:`", line)], name


def test_every_specification_is_rendered_once_under_each_rule_it_names() -> None:
    sections = _sections()
    pages = _committed()
    specs = _real_specs()
    registry = default_registry()
    assert len(specs) >= SPECIFIED_RULES_FLOOR
    for rule_id, (_, text) in specs.items():
        line = f"**Specification.** {text}"
        assert sections[rule_id].count(line) == 1, rule_id
        page = pages[f"rules/{registry.get(rule_id).family.lower()}.md"]
        sharing = [other for other, (_, same) in specs.items() if same == text and f"#### {other}:" in page]
        assert page.count(line) == len(sharing), rule_id


def test_module_notes_are_complete_and_every_module_link_resolves() -> None:
    specs = _real_specs()
    sections = _sections()
    for name, page in _committed().items():
        if name == "rules.md":
            continue
        notes = _notes(page)
        assert not [line for line in notes.splitlines() if SPEC_BULLET.fullmatch(line)], name
        modules = set(re.findall(r"^### Module (\w+)$", page, flags=re.MULTILINE))
        assert set(re.findall(r"\(#module-(\w+)\)", page)) == modules, name
        for module in modules & {home for home, _ in specs.values()}:
            assert "*Specified under each rule: " in notes.split(f"### Module {module}\n", 1)[1].split("### ")[0]
    for rule_id, section in sections.items():
        if rule_id not in specs:
            assert "*No rule-level specification yet; see the module notes above.*" in section, rule_id
    assert "](#module-owl)" in sections["OWL012"]  # its bullet is in owl.py, its RuleSpec in classes.py


def _rewrap(doc: str, width: int) -> str:
    """Rewrap every paragraph and item of a docstring after its summary line at ``width``."""
    lines = inspect.cleandoc(doc).splitlines()
    out = [lines[0]]
    unit: list[str] = []

    def flush() -> None:
        if unit:
            text = " ".join(line.strip() for line in unit)
            header = re.match(r"\* \*\*[^*]+\*\*|\* ", text)
            if header:  # keep a bullet's header in one piece
                text = header[0].replace(" ", "\0") + text[len(header[0]) :]
            indent = "  " if header else ""
            wrapped = textwrap.fill(
                text, width, subsequent_indent=indent, break_long_words=False, break_on_hyphens=False
            )
            out.extend(wrapped.replace("\0", " ").splitlines())
            unit.clear()

    for line in lines[1:]:
        item = unit and unit[0].startswith("* ")
        if not line.strip() or line.startswith("* ") or (item and not line.startswith("  ")):
            flush()
        if line.strip():
            unit.append(line)
        else:
            out.append("")
    flush()
    return "\n".join(out)


@pytest.mark.parametrize("width", [60, 200])
def test_the_rendering_does_not_depend_on_how_docstrings_are_wrapped(width: int) -> None:
    def collapsed(text: str) -> str:
        return " ".join(text.split())

    for module in spec_modules():
        original = read_module(module)
        rewrapped = read_module(types.ModuleType(module.__name__, _rewrap(module.__doc__ or "", width)))
        assert {key: collapsed(text) for key, text in rewrapped.specs.items()} == {
            key: collapsed(text) for key, text in original.specs.items()
        }, module.__name__
        assert [collapsed(line) for line in rewrapped.notes] == [collapsed(line) for line in original.notes]


WORDS = st.text(string.ascii_letters + string.digits + ".,;:()/'-_<>[]&|#=+!?*", min_size=1, max_size=9).filter(
    lambda word: not word.startswith("*")
)


@pytest.mark.slow
@budget(0.3)
@given(
    specs=st.dictionaries(
        st.from_regex(r"[A-Z]{1,4}[0-9]{3}", fullmatch=True), st.lists(WORDS, min_size=1), min_size=1
    ),
    width=st.integers(10, 120),
    header_only=st.booleans(),
    fixtures=st.booleans(),
)
def test_a_random_docstring_round_trips(
    specs: dict[str, list[str]], width: int, header_only: bool, fixtures: bool
) -> None:
    lines = ["Fake rules.", "", *textwrap.wrap("Some prose about the rules, wrapped anyhow.", width), ""]
    for rule_id, words in specs.items():
        body = textwrap.wrap(" ".join(words), width, break_long_words=False, break_on_hyphens=False)
        if header_only:
            lines += [f"* **{rule_id}.**", *[f"  {line}" for line in body]]
        else:
            lines += [f"* **{rule_id}.** {body[0]}", *[f"  {line}" for line in body[1:]]]
    lines += ["Fixtures: none."] if fixtures else []
    doc = read_module(_fake("\n".join(lines)))
    assert doc.specs == {rule_id: " ".join(words) for rule_id, words in specs.items()}
    assert f"*Specified under each rule: {', '.join(specs)}.*" in doc.notes
    assert ("Fixtures: none." in doc.notes) is fixtures


@pytest.mark.slow
@budget(0.3)
@given(st.lists(st.text(st.characters(exclude_characters="\n\r"), max_size=12), max_size=6))
def test_reflowing_is_idempotent(lines: list[str]) -> None:
    once = _reflow(lines)
    assert _reflow([once]) == once
    assert "\n" not in once


@pytest.mark.parametrize(
    "note",
    [
        "# heading",
        "## heading",
        "1. first",
        "1) first",
        "<div>x</div>",
        "---",
        "***",
        "> quote",
        "- dash",
        "+ plus",
        "| a |",
        "```",
        "[x]: https://example.test/",
        "* # item",
    ],
)
def test_a_note_that_would_not_render_as_text_is_refused(note: str) -> None:
    with pytest.raises(ValueError, match="fake"):
        read_module(_fake(f"Fake.\n\n{note}\n"))


def test_every_note_block_is_separated_so_no_paragraph_joins_an_item() -> None:
    doc = read_module(
        _fake("Fake.\n\n* item one\n  continued\n* item two\nParagraph after.\n\n* **A001.** Spec.\n* item three\n")
    )
    assert doc.notes == (
        "Fake.",
        "",
        "* item one continued",
        "* item two",
        "",
        "Paragraph after.",
        "",
        "*Specified under each rule: A001.*",
        "",
        "* item three",
    )


def test_a_module_without_docstring_is_refused() -> None:
    with pytest.raises(ValueError, match="-OO"):
        read_module(_fake(None))


def test_the_spec_modules_partition_the_registry() -> None:
    declared = Counter(spec.rule_id for module in spec_modules() for spec in module.SPECS)
    assert set(declared) == {spec.rule_id for spec in default_registry().all()}
    assert set(declared.values()) == {1}
    assert set(RULE_MODULES) <= set(spec_modules())


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
