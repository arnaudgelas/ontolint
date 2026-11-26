"""``scripts/measure_action_runs.py`` runs the commands the Action runs, on inputs it writes itself (issue #188)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.slow

ROOT = Path(__file__).parent.parent


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("measure_action_runs", ROOT / "scripts" / "measure_action_runs.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["measure_action_runs"] = module
    spec.loader.exec_module(module)
    return module


def test_the_commands_are_the_two_the_action_runs(tmp_path: Path) -> None:
    script = _script()
    entry = script._entrypoint()  # noqa: SLF001 -- the module under test loads the Action's own script
    scenario = script.large_file(tmp_path, 20)

    both = script.commands(entry, scenario, tmp_path)

    assert sorted(both) == ["markdown", "sarif"]
    for fmt, argv in both.items():
        assert argv[:3] == [sys.executable, "-m", "ontolint"]
        assert argv[argv.index("--format") + 1] == fmt
        assert "large.ttl" in argv
    # What the Action itself builds for the same settings (report_command): the script does not reimplement it.
    assert both["markdown"][-1] == str(tmp_path / "out" / "summary.md")
    assert both["sarif"][-1] == str(tmp_path / "out" / "ontolint.sarif")


def test_a_small_run_reports_every_column_and_the_reports_repeat_byte_for_byte(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    script = _script()
    out = tmp_path / "cost.md"

    assert (
        script.main(
            [
                "--classes",
                "30",
                "--imports",
                "2",
                "--per-import",
                "5",
                "--nodes",
                "30",
                "--repetitions",
                "2",
                "--pairs",
                "1",
                "--out",
                str(out),
            ]
        )
        == 0
    )

    text = out.read_text(encoding="utf-8")
    assert text == capsys.readouterr().out.rstrip("\n") + "\n"
    for needle in ("30 classes, one file", "2 imports of 5 classes", "30 nodes, SHACL", "Disagreement trial"):
        assert needle in text, needle
    scenarios = ("30 classes, one file", "2 imports of 5 classes", "30 nodes, SHACL")
    rows = [line for line in text.splitlines() if line.startswith(tuple(f"| {n}" for n in scenarios))]
    assert len(rows) == len(scenarios)
    assert all(line.endswith("| yes |") for line in rows), "the reports of the repetitions are byte-identical"
    assert "NO" not in text


def _fake_run(script: ModuleType, exit_code: int, reports: dict[str, bytes]) -> object:
    return script.Run(0.1, 1, exit_code, reports)


def test_a_command_that_fails_or_writes_no_report_is_not_measured() -> None:
    script = _script()

    script.require_success(_fake_run(script, 0, {"summary.md": b"x"}), "ok")
    with pytest.raises(SystemExit, match="exited 2, expected 0"):
        script.require_success(_fake_run(script, 2, {"summary.md": b"x"}), "failing", ["ontolint"])
    with pytest.raises(SystemExit, match="wrote no report"):
        script.require_success(_fake_run(script, 0, {}), "silent", ["ontolint"])


def test_measure_stops_when_the_command_exits_non_zero(tmp_path: Path) -> None:
    script = _script()
    entry = script._entrypoint()  # noqa: SLF001
    scenario = script.large_file(tmp_path, 5)
    scenario = script.Scenario(scenario.name, ["missing.ttl"], scenario.extra)  # ontolint cannot read this file

    with pytest.raises(SystemExit, match="expected 0"):
        script.measure(entry, scenario, tmp_path, 1)


def test_measure_stops_when_the_report_is_not_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = _script()
    entry = script._entrypoint()  # noqa: SLF001
    scenario = script.large_file(tmp_path, 5)
    monkeypatch.setattr(script, "run_one", lambda *_a, **_k: script.Run(0.1, 1, 0, {}))

    with pytest.raises(SystemExit, match="wrote no report"):
        script.measure(entry, scenario, tmp_path, 1)


def test_the_disagreement_experiment_asserts_each_exit_0_side_wrote_its_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = _script()
    entry = script._entrypoint()  # noqa: SLF001
    monkeypatch.setattr(script, "threshold", lambda *_a, **_k: 1.0)
    monkeypatch.setattr(script, "action_pair", lambda *_a, **_k: (_fake_run(script, 2, {}), _fake_run(script, 0, {})))

    with pytest.raises(SystemExit, match="SARIF run: exited 0 but wrote no report"):
        script.disagreement(entry, tmp_path, 5, 1)

    monkeypatch.setattr(
        script, "action_pair", lambda *_a, **_k: (_fake_run(script, 1, {}), _fake_run(script, 0, {"a": b"x"}))
    )
    with pytest.raises(SystemExit, match="Markdown run: exited 1"):
        script.disagreement(entry, tmp_path, 5, 1)
