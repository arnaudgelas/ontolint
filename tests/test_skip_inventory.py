"""Every test that an ``ONTOLINT_*`` switch skips is named in ``docs/ci-schedule.md`` with its scheduled job (#166).

A test that is skipped unless a switch is set proves nothing until something sets the switch or runs the same code.
The platform skips are guarded by ``test_platform_skips.py``; this guards the other kind: a ``skipif`` (or a
``pytest.skip``) whose condition or reason reads an ``ONTOLINT_*`` name.  Each such switch must have a row in the
"Switches" table of ``docs/ci-schedule.md``.  The row names a workflow that exists, is a scheduled one and mentions,
outside a comment, the switch (or the entry point the row names); or it says the switch is a developer tool that never
skips a check in a normal run.  That is textual association, not proof of execution: ``fuzz.yml`` does not set
``ONTOLINT_FUZZ``, it runs the same targets through ``tests.fuzz.fuzzer``, and the row says so.

This is a source-level lint, like the platform one: a skip decided through a helper in another module, or with the
switch's name built at run time, is not seen.  A tool that may be missing (``actionlint``, ``docker``, ``uv``) is not a
switch and is not constrained here.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
TESTS = ROOT / "tests"
WORKFLOWS = ROOT / ".github" / "workflows"
SCHEDULE = ROOT / "docs" / "ci-schedule.md"
SWITCH = re.compile(r"ONTOLINT_[A-Z][A-Z_]*")
# The switches that are no schedule: a developer asks for something on purpose; a normal run skips nothing it needs.
DEVELOPER_TOOLS = {"ONTOLINT_UPDATE_GOLDEN": "regenerates the golden snapshots; a normal run compares them"}
ROW = re.compile(
    r"^\| `(?P<switch>ONTOLINT_[A-Z_]+)` \| (?P<what>[^|]+) \| (?P<workflow>[^|]+) \| (?P<evidence>[^|]+) \|$",
    re.MULTILINE,
)
WORKFLOW_LINK = re.compile(r"\[`(?P<file>[\w.-]+\.yml)`\]")


def switches_that_skip(source: str) -> set[str]:
    """The ``ONTOLINT_*`` names read by a ``skipif`` or ``pytest.skip`` of ``source``, through one module-level name."""
    tree = ast.parse(source)
    assigned = {
        target.id: ast.get_source_segment(source, node) or ""
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        if name not in {"skipif", "skip"}:
            continue
        text = ast.get_source_segment(source, node) or ""
        for _ in range(2):  # a name assigned from an expression that holds the switch (``IMAGE = os.environ.get(...)``)
            text += " ".join(assigned.get(n.id, "") for n in ast.walk(node) if isinstance(n, ast.Name))
        found |= set(SWITCH.findall(text))
    return found


def skip_switches_of_the_suite() -> set[str]:
    return {
        switch
        for path in sorted(TESTS.rglob("*.py"))
        if path.name != Path(__file__).name
        for switch in switches_that_skip(path.read_text(encoding="utf-8"))
    }


def _without_comments(workflow: str) -> str:
    """``workflow`` without its whole-line comments: a token that appears only in one is no evidence."""
    return "\n".join(line for line in workflow.splitlines() if not line.lstrip().startswith("#"))


def problems(found: set[str], table: str, workflows: dict[str, str], scheduled: set[str]) -> list[str]:
    """What is wrong between the switches the suite skips on, the table that names them and the workflows."""
    rows = {m["switch"]: m for m in ROW.finditer(table)}
    out = [f"{s} skips a test and has no row in the Switches table" for s in sorted(found - rows.keys())]
    out += [f"{s} has a row and no test skips on it" for s in sorted(rows.keys() - found)]
    for switch, row in sorted(rows.items()):
        link = WORKFLOW_LINK.search(row["workflow"])
        if link is None:
            if switch not in DEVELOPER_TOOLS:
                out.append(f"{switch} names no workflow and is not a developer tool")
            continue
        file = link["file"]
        if file not in workflows:
            out.append(f"{switch} names {file}, which does not exist")
            continue
        if file not in scheduled:
            out.append(f"{switch} names {file}, which is not on a schedule")
        token = row["evidence"].strip().strip("`")
        if token not in _without_comments(workflows[file]):
            out.append(f"{switch}: {file} does not contain {token!r}")
    return out


def _workflows() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(WORKFLOWS.glob("*.yml"))}


def _scheduled(workflows: dict[str, str]) -> set[str]:
    return {name for name, text in workflows.items() if re.search(r"^\s*- cron: ", text, re.MULTILINE)}


TABLE = SCHEDULE.read_text(encoding="utf-8")


def test_every_switch_the_suite_skips_on_is_named_with_the_scheduled_workflow_that_covers_it() -> None:
    workflows = _workflows()

    assert problems(skip_switches_of_the_suite(), TABLE, workflows, _scheduled(workflows)) == []


def test_today_s_switches_all_map_to_a_workflow_or_a_developer_tool() -> None:
    found = skip_switches_of_the_suite()

    assert {"ONTOLINT_BENCH", "ONTOLINT_FUZZ", "ONTOLINT_JENA_HOME", "ONTOLINT_ROBOT_IMAGE"} <= found
    assert set(DEVELOPER_TOOLS) <= found


# --- the checker itself --------------------------------------------------------------------------------------------

NEW_TABLE = (
    "| `ONTOLINT_X` | what | [`x.yml`](../.github/workflows/x.yml) | `ONTOLINT_X` |\n"
    "| `ONTOLINT_UPDATE_GOLDEN` | what | none | none |\n"
)


def test_a_new_skipif_on_a_switch_with_no_row_fails() -> None:
    source = (
        'import os\nimport pytest\n\n@pytest.mark.skipif(not os.environ.get("ONTOLINT_NEW"), reason="a switch")\n'
        "def test_a(): ...\n"
    )

    assert switches_that_skip(source) == {"ONTOLINT_NEW"}
    assert problems({"ONTOLINT_NEW"}, NEW_TABLE, {"x.yml": "ONTOLINT_X\n- cron: x"}, {"x.yml"}) == [
        "ONTOLINT_NEW skips a test and has no row in the Switches table",
        "ONTOLINT_UPDATE_GOLDEN has a row and no test skips on it",
        "ONTOLINT_X has a row and no test skips on it",
    ]


def test_a_row_naming_a_workflow_that_does_not_exist_fails() -> None:
    assert problems({"ONTOLINT_X", "ONTOLINT_UPDATE_GOLDEN"}, NEW_TABLE, {}, set()) == [
        "ONTOLINT_X names x.yml, which does not exist"
    ]


def test_a_row_naming_a_workflow_that_is_not_scheduled_or_does_not_set_the_switch_fails() -> None:
    both = {"ONTOLINT_X", "ONTOLINT_UPDATE_GOLDEN"}

    assert problems(both, NEW_TABLE, {"x.yml": "ONTOLINT_X\n"}, set()) == [
        "ONTOLINT_X names x.yml, which is not on a schedule"
    ]
    assert problems(both, NEW_TABLE, {"x.yml": "- cron: x\n"}, {"x.yml"}) == [
        "ONTOLINT_X: x.yml does not contain 'ONTOLINT_X'"
    ]


def test_a_token_that_only_a_comment_of_the_workflow_holds_is_no_evidence() -> None:
    both = {"ONTOLINT_X", "ONTOLINT_UPDATE_GOLDEN"}

    assert problems(both, NEW_TABLE, {"x.yml": "# ONTOLINT_X\n- cron: x\n"}, {"x.yml"}) == [
        "ONTOLINT_X: x.yml does not contain 'ONTOLINT_X'"
    ]


def test_a_switch_that_is_neither_scheduled_nor_a_developer_tool_fails() -> None:
    table = "| `ONTOLINT_Y` | what | none | none |\n"

    assert problems({"ONTOLINT_Y"}, table, {}, set()) == ["ONTOLINT_Y names no workflow and is not a developer tool"]


@pytest.mark.parametrize(
    "condition",
    ['sys.platform == "win32"', 'shutil.which("docker") is None', "os.name == 'nt'"],
)
def test_a_platform_or_tool_skip_is_not_a_switch(condition: str) -> None:
    source = f'import pytest\n\n@pytest.mark.skipif({condition}, reason="not here")\ndef test_a(): ...\n'

    assert switches_that_skip(source) == set()


def test_a_switch_read_through_a_module_level_name_is_found() -> None:
    source = (
        'import os\nimport pytest\nIMAGE = os.environ.get("ONTOLINT_ROBOT_IMAGE")\n\n'
        '@pytest.mark.skipif(not IMAGE, reason="an image")\ndef test_a(): ...\n'
    )

    assert switches_that_skip(source) == {"ONTOLINT_ROBOT_IMAGE"}
