"""Per-rule finding counts on the pinned validation corpus: record, check and diff (issue #168).

    uv run python scripts/corpus_counts.py record DIR        # lint the corpus in DIR, rewrite rule-counts.json
    uv run python scripts/corpus_counts.py check DIR         # lint it, exit 1 and print the diff when the counts differ
    uv run python scripts/corpus_counts.py diff OLD NEW      # a Markdown table of two counts files, by rule and by file

A release can double one rule's findings on CCO unnoticed.  DIR is a directory ``scripts/corpus.py fetch`` made (it
is verified against the manifest first: counts are of the pinned corpus or of nothing).  Every run of the manifest is
one ontolint command, the manifest's fixed arguments (``counts.command`` of ``docs/validation/metric-corpus.json``:
``--format json --fail-on never``) after the run's own, and the file holds, for each run:

* ``exit_status``: what ontolint ended with, so that a file that stops being lintable (0 to 2) is a status change, not
  a count of zero; ``check`` also fails when it is not the exit status the manifest expects;
* ``files``: for each file a finding is about (the linted file, or a module of its closure) the findings per rule,
  and the rules that ``failed`` or were ``unsupported`` on the linted file, which are not counted as zero findings;
* ``error``: instead of ``files``, the reason when ontolint wrote no report (an input it refused).

The file is deterministic: sorted keys, paths relative to the source's directory with ``/`` separators, no timing, the
same bytes from any working directory.  The ontolint version is recorded beside the counts, not inside what ``check``
compares, so a release with identical counts is not a difference.  ``diff`` flags a rule whose total doubled; that is
a flag for the reviewer, never a failure.
"""

# ruff: noqa: S603 -- runs this interpreter on ontolint with arguments built from the manifest

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import corpus  # noqa: E402 -- the sibling script; its directory is first on the path when this one is run

ROOT = corpus.ROOT
COUNTS = ROOT / "docs" / "validation" / "rule-counts.json"
BROKEN = ("failed", "unsupported")
DOUBLED = 2
Runner = Callable[[Sequence[str]], "subprocess.CompletedProcess[str]"]


def fixed_arguments(manifest: Path = corpus.MANIFEST) -> list[str]:
    """The arguments every run ends with, stated in the manifest (``counts.command``)."""
    data = json.loads(manifest.read_text(encoding="utf-8"))
    command = data.get("counts", {}).get("command")
    if not isinstance(command, list) or not command or not all(isinstance(a, str) for a in command):
        raise ValueError("the manifest states the fixed command as counts.command, a list of arguments")
    return command


def ontolint_version() -> str:
    done = subprocess.run([sys.executable, "-m", "ontolint", "--version"], capture_output=True, text=True, check=False)
    return done.stdout.strip().split()[-1] if done.returncode == 0 and done.stdout.strip() else "unknown"


def _run_ontolint(argv: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "ontolint", *argv], capture_output=True, text=True, check=False)


def _relative(path: str, root: Path) -> str:
    """``path`` of a report (relative to the working directory, or absolute) relative to ``root``, with ``/``.

    A file outside the source cannot be recorded: its absolute place is the host's, so the baseline would differ on
    every other machine and ``check`` would fail for a reason that is not a change.  Pin the import in the source.
    """
    resolved = (Path.cwd() / path).resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        raise corpus.CorpusError(
            f"{path} is outside the source directory {root}: a count on it would be specific to this host; "
            "add the file to the source (pinned by commit) or lint it with a catalog that stays inside it"
        ) from None


def summarise(report: Mapping[str, Any], root: Path) -> dict[str, Any]:
    """The counts of one JSON report: findings per rule per file, and what failed or was unsupported per linted file."""
    counts: dict[str, Counter[str]] = {}
    for finding in report["findings"]:
        counts.setdefault(_relative(finding["path"], root), Counter())[finding["rule"]] += 1
    broken: dict[str, dict[str, list[str]]] = {}
    for file in report["files"]:
        name = _relative(file["path"], root)
        for status in BROKEN:
            rules = sorted(x["rule"] for x in file["executions"] if x["status"] == status)
            if rules:
                broken.setdefault(name, {})[status] = rules
    files: dict[str, dict[str, Any]] = {}
    for name in sorted({*counts, *broken, *(_relative(f["path"], root) for f in report["files"])}):
        entry: dict[str, Any] = {"counts": dict(sorted(counts.get(name, Counter()).items()))}
        entry.update(broken.get(name, {}))
        files[name] = entry
    return {"files": files}


def record(
    directory: Path,
    sources: Sequence[corpus.Source],
    fixed: Sequence[str],
    runner: Runner = _run_ontolint,
) -> dict[str, Any]:
    """The counts document of ``directory``: one entry per run, ``<source>/<run>``; the tree is verified first."""
    problems = corpus.verify(directory, sources)
    if problems:
        raise corpus.CorpusError("the directory is not the pinned corpus (run fetch):\n" + "\n".join(problems))
    runs: dict[str, Any] = {}
    for source in sources:
        for run in source.runs:
            done = runner([*source.command(directory, run), *fixed])
            entry: dict[str, Any] = {"exit_status": done.returncode, "expected_exit_status": run.exit_status}
            try:
                report = json.loads(done.stdout)
            except json.JSONDecodeError:
                entry["error"] = (done.stderr.strip().splitlines() or ["no report"])[0][:300]
            else:
                entry.update(summarise(report, source.root(directory)))
            runs[f"{source.id}/{run.name}"] = entry
    return {"command": ["ontolint", "<inputs>", "<run arguments>", *fixed], "runs": dict(sorted(runs.items()))}


def dump(document: Mapping[str, Any], version: str | None = None) -> str:
    """The file's text: sorted keys, two-space indent, the ontolint version beside the counts, a final newline."""
    body = {"ontolint_version": version if version is not None else ontolint_version(), **document}
    return json.dumps(body, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def comparable(document: Mapping[str, Any]) -> dict[str, Any]:
    """What ``check`` compares: everything but the ontolint version."""
    return {key: value for key, value in document.items() if key != "ontolint_version"}


def unexpected_exits(document: Mapping[str, Any]) -> list[str]:
    """The runs whose exit status is not the one the manifest expects."""
    return [
        f"{name}: exited {run['exit_status']}, the manifest expects {run['expected_exit_status']}"
        for name, run in document["runs"].items()
        if run["exit_status"] != run["expected_exit_status"]
    ]


def _totals(run: Mapping[str, Any]) -> Counter[str]:
    total: Counter[str] = Counter()
    for file in run.get("files", {}).values():
        total.update(file["counts"])
    return total


def _status_changes(old_runs: Mapping[str, Any], new_runs: Mapping[str, Any]) -> list[str]:
    """The rows of what changed besides a count: a run added or removed, its exit status, its report, its rules."""
    rows: list[str] = []
    for name in sorted({*old_runs, *new_runs}):
        before, after = old_runs.get(name), new_runs.get(name)
        if before is None or after is None:
            rows.append(f"| `{name}` | {'added' if before is None else 'removed'} | |")
            continue
        if before["exit_status"] != after["exit_status"]:
            rows.append(f"| `{name}` | exit status | {before['exit_status']} -> {after['exit_status']} |")
        if before.get("error") != after.get("error"):
            rows.append(f"| `{name}` | report | {before.get('error', 'ok')} -> {after.get('error', 'ok')} |")
        for file in sorted({*before.get("files", {}), *after.get("files", {})}):
            for status in BROKEN:
                was = before.get("files", {}).get(file, {}).get(status, [])
                now = after.get("files", {}).get(file, {}).get(status, [])
                if was != now:
                    change = f"{', '.join(was) or 'none'} -> {', '.join(now) or 'none'}"
                    rows.append(f"| `{name}` `{file}` | {status} rules | {change} |")
    return rows


def _file_rows(old_runs: Mapping[str, Any], new_runs: Mapping[str, Any]) -> list[str]:
    """The rows of the table by rule and file, for the runs that have a report on both sides."""
    rows: list[str] = []
    for name in sorted({*old_runs, *new_runs}):
        before, after = old_runs.get(name, {}), new_runs.get(name, {})
        if "files" not in before or "files" not in after:
            continue  # a run with no report on one side has a status change, not counts to compare
        for file in sorted({*before["files"], *after["files"]}):
            was = before["files"].get(file, {}).get("counts", {})
            now = after["files"].get(file, {}).get("counts", {})
            rows += [
                f"| {rule} | `{name}` `{file}` | {was.get(rule, 0)} | {now.get(rule, 0)} "
                f"| {now.get(rule, 0) - was.get(rule, 0):+d} |"
                for rule in sorted({*was, *now})
                if was.get(rule, 0) != now.get(rule, 0)
            ]
    return rows


def _rule_rows(old_runs: Mapping[str, Any], new_runs: Mapping[str, Any]) -> list[str]:
    """The rows of the totals per rule over the runs that have a report on both sides, with the doubling flag."""
    old_total: Counter[str] = Counter()
    new_total: Counter[str] = Counter()
    for name in sorted({*old_runs, *new_runs}):
        if "files" in old_runs.get(name, {}) and "files" in new_runs.get(name, {}):
            old_total.update(_totals(old_runs[name]))
            new_total.update(_totals(new_runs[name]))
    rows: list[str] = []
    for rule in sorted({*old_total, *new_total}):
        before, after = old_total.get(rule, 0), new_total.get(rule, 0)
        if before != after:
            flag = " **doubled**" if before and after >= DOUBLED * before else ("" if before else " new")
            rows.append(f"| {rule} | {before} | {after} | {after - before:+d}{flag} |")
    return rows


def diff(old: Mapping[str, Any], new: Mapping[str, Any]) -> str:
    """A Markdown report of the differences between two counts documents; empty text when there are none.

    Status changes come first (a run's exit status, a rule that now fails or is unsupported, a run that lost or gained
    its report), then the totals per rule with a flag on a rule that doubled, then the table by rule and file.  A run
    with no report on one side is not compared count by count: its exit status changed, which is the finding.
    """
    old_runs, new_runs = old.get("runs", {}), new.get("runs", {})
    tables = (
        ("Status changes", "| Run | What | Change |\n| --- | --- | --- |", _status_changes(old_runs, new_runs)),
        ("Rules", "| Rule | Before | After | Change |\n| --- | ---: | ---: | --- |", _rule_rows(old_runs, new_runs)),
        (
            "By file",
            "| Rule | Run and file | Before | After | Change |\n| --- | --- | ---: | ---: | ---: |",
            _file_rows(old_runs, new_runs),
        ),
    )
    return "\n\n".join(f"### {title}\n\n{header}\n" + "\n".join(rows) for title, header, rows in tables if rows)


def _shown(path: Path) -> str:
    """``path`` relative to the repository when it is inside it, else as given."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Per-rule finding counts on the pinned validation corpus (issue #168)."
    )
    parser.add_argument("command", choices=("record", "check", "diff"))
    parser.add_argument("paths", nargs="+", help="DIR for record and check; OLD NEW (counts files) for diff")
    args = parser.parse_args(argv)
    if args.command == "diff":
        if len(args.paths) != 2:  # noqa: PLR2004 -- the old and the new file
            parser.error("diff needs OLD and NEW")
        report = diff(*(json.loads(Path(p).read_text(encoding="utf-8")) for p in args.paths))
        print(report or "No difference.")
        return 0
    if len(args.paths) != 1:
        parser.error(f"{args.command} needs one directory")
    document = record(Path(args.paths[0]), corpus.load(), fixed_arguments())
    bad = unexpected_exits(document)
    if args.command == "record":
        if bad:  # a baseline that records an unexpected exit is not written
            print("Nothing written; " + "\n".join(bad))
            return 1
        COUNTS.write_text(dump(document), encoding="utf-8")
        print(f"Wrote {_shown(COUNTS)}.")
        return 0
    committed = json.loads(COUNTS.read_text(encoding="utf-8"))
    changed = diff(committed, document)
    if changed or bad:
        print(f"The counts differ from {_shown(COUNTS)}; run record and review the diff.\n")
        print("\n".join(bad), changed, sep="\n\n" if bad and changed else "")
        return 1
    if comparable(committed) != comparable(
        document
    ):  # a difference diff does not show (the command): still a difference
        print(f"The counts differ from {_shown(COUNTS)} in the command or the runs; run record.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
