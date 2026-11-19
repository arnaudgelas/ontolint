"""A test that is skipped for a platform says so with a marker and a reason; it is never skipped in silence.

The cross-platform smoke suite (``test_cross_platform_smoke.py``) runs on Linux, macOS and Windows, so a skip that
nobody can see would turn "passes on Windows" into "was not run on Windows".  Two forms are therefore refused in
every test module:

* a ``skipif`` whose condition looks at the platform (``sys.platform``, ``os.name``, ``platform.system()`` ...) and
  gives no ``reason`` of its own, and a bare ``skip``;
* a ``pytest.skip(...)`` call inside an ``if`` that looks at the platform: the skip is then decided while the test
  runs, out of reach of ``-rs`` and of the marker, so it must be a ``skipif`` marker instead.

Tools that may be missing (``actionlint``, ``uv``) are not platforms; their ``skipif`` markers are not constrained.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.smoke

TESTS = Path(__file__).parent
PLATFORM_PROBE = re.compile(r"sys\.platform|os\.name|platform\.system|platform\.platform|getwindowsversion|geteuid")
MIN_REASON = 8


def _is(node: ast.expr, name: str) -> bool:
    return (isinstance(node, ast.Attribute) and node.attr == name) or (isinstance(node, ast.Name) and node.id == name)


def _reason(call: ast.Call) -> str:
    for keyword in call.keywords:
        if keyword.arg == "reason" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
            return keyword.value.value.strip()
    return ""


def _is_pytest_call(node: ast.AST, names: set[str]) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in names
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "pytest"
    )


def silent_platform_skips(source: str) -> list[str]:
    """Describe each platform skip in ``source`` that has no marker or no reason (empty when all are explicit)."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and _is(node.func, "skipif") and node.args:
            condition = ast.get_source_segment(source, node.args[0]) or ""
            if PLATFORM_PROBE.search(condition) and len(_reason(node)) < MIN_REASON:
                found.append(f"line {node.lineno}: skipif({condition}) has no reason")
        elif (
            isinstance(node, ast.Attribute)
            and node.attr == "skip"
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "mark"
        ):
            found.append(f"line {node.lineno}: pytest.mark.skip hides the test on every platform")
        elif isinstance(node, ast.If) and PLATFORM_PROBE.search(ast.get_source_segment(source, node.test) or ""):
            found.extend(
                f"line {inner.lineno}: pytest.{inner.func.attr}() decided by the platform"  # type: ignore[attr-defined]
                for inner in ast.walk(node)
                if _is_pytest_call(inner, {"skip", "xfail"})
            )
    return found


def test_no_test_module_skips_for_a_platform_without_a_marker_and_a_reason() -> None:
    problems = [
        f"{path.relative_to(TESTS)}: {problem}"
        for path in sorted(TESTS.rglob("test_*.py"))
        for problem in silent_platform_skips(path.read_text(encoding="utf-8"))
    ]
    assert problems == []


@pytest.mark.parametrize(
    "source",
    [
        "@pytest.mark.skipif(sys.platform == 'win32')\ndef test_a(): ...",
        "@pytest.mark.skipif(sys.platform == 'win32', reason='x')\ndef test_a(): ...",
        "@pytest.mark.skipif(os.name == 'nt', reason='')\ndef test_a(): ...",
        "@pytest.mark.skip\ndef test_a(): ...",
        "def test_a():\n    if sys.platform == 'win32':\n        pytest.skip('no pipes on Windows, honest')",
        "def test_a():\n    if os.name != 'posix':\n        pytest.xfail('later')",
    ],
)
def test_the_check_refuses_a_silent_platform_skip(source: str) -> None:
    assert silent_platform_skips(source)


@pytest.mark.parametrize(
    "source",
    [
        "@pytest.mark.skipif(sys.platform == 'win32', reason='Windows reports a closed pipe as OSError')\ndef t(): ...",
        "@pytest.mark.skipif(shutil.which('actionlint') is None, reason='x')\ndef t(): ...",
        "def test_a():\n    if shutil.which('uv') is None:\n        pytest.skip('uv')",
    ],
)
def test_the_check_accepts_an_explicit_platform_skip_and_a_missing_tool(source: str) -> None:
    assert silent_platform_skips(source) == []
