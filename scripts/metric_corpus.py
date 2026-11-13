"""Measure the METRIC rules on the pinned calibration corpus (issue #8, docs/validation/metric-calibration.md).

    uv run python scripts/metric_corpus.py fetch DIR     # download every corpus file, verify its SHA-256
    uv run python scripts/metric_corpus.py measure DIR   # lint every file, rewrite the results file and the page
    uv run python scripts/metric_corpus.py check DIR     # lint every file, fail if the results file differs
    uv run python scripts/metric_corpus.py render        # rewrite the page's generated part from the JSON files

No corpus file is committed: ``docs/validation/metric-corpus.json`` names each one by URL, commit and checksum,
and ``fetch`` refuses a file whose checksum differs.  ``load_manifest`` refuses a manifest that could make the
script read or write outside DIR (an id that is not a plain file name), an entry that is not pinned or licensed,
and an id given twice, so a custom manifest is held to the rules the committed one follows.  A corpus file
that is a symbolic link or not a regular file is refused, so neither command reads or writes through one;
``fetch`` writes by renaming a new file into place, which replaces a link instead of following it, and
``measure`` lints a private copy of the bytes it verified.

Each file is linted twice with ``--select METRIC``:

* *default*: the default policy, which says whether each rule fires as shipped;
* *forced*: every limit at the end of its range and ``metric_min_sample`` 1, so every rule with a non-empty
  population reports and its message gives the measured value.  A rule that still stays silent has measured
  the boundary itself (0 for an upper limit, full coverage for METRIC009), or an empty population.

A run is used only if its report is of the one file and every METRIC rule executed in it once, with at most
one finding each: a rule that did not run reports nothing, which either run would read as a measurement.

METRIC007 is never forced: it reads the same ratio as METRIC006, whose forced message gives it.  The labels in
the manifest are proposals until the maintainer approves them (``"label_status": "approved"``).  Every rule of
every entry must be labelled, by name or through ``"*"``, so an omission cannot pass for a judgement.

The results are a snapshot of one ontolint version: nothing runs ``check`` in CI or at release (issue #31).
"""

# ruff: noqa: S310, S603 -- downloads fixed, checksummed HTTPS URLs; runs this interpreter on ontolint.

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "docs" / "validation" / "metric-corpus.json"
RESULTS = ROOT / "docs" / "validation" / "metric-corpus-results.json"
PAGE = ROOT / "docs" / "validation" / "metric-calibration.md"
BEGIN, END = "<!-- metric_corpus.py: begin -->", "<!-- metric_corpus.py: end -->"
RULES = tuple(f"METRIC{n:03d}" for n in range(1, 14))
COUNTED = ("fire", "silent")  # labels that make a true or false positive or negative
EXPECTS = (*COUNTED, "unknown", "unassessed")  # unknown: assessed and left open; unassessed: not looked at
BASES = ("checked", "presumed", "none")  # how the label's reason was established
# The bases each expectation may have: a positive is always checked, a negative is checked or presumed, a
# judgement left open was assessed, and only an unassessed pair has no basis.
ALLOWED_BASES: dict[str, tuple[str, ...]] = {
    "fire": ("checked",),
    "silent": ("checked", "presumed"),
    "unknown": ("checked",),
    "unassessed": ("none",),
}
SHA256 = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")

# Every limit at the far end of its range: an upper limit of 0 fires on any non-zero value, a lower limit
# above any possible value fires on any population.  METRIC007's 1e9 upper limit keeps the policy valid
# (its minimum must not exceed its maximum) and never fires.
FORCED_POLICY: dict[str, float] = {
    "metric_min_sample": 1,
    "metric_max_imports": 0,
    "metric_max_unlabelled_ratio": 0.0,
    "metric_max_undefined_ratio": 0.0,
    "metric_max_undocumented_property_ratio": 0.0,
    "metric_max_mean_fanout": 0.0,
    "metric_max_orphan_ratio": 0.0,
    "metric_min_property_class_ratio": 1e9,
    "metric_max_property_class_ratio": 1e9,
    "metric_max_unsigned_property_ratio": 0.0,
    "metric_min_language_coverage": 1.0,
    "metric_max_foreign_reference_ratio": 0.0,
    "metric_min_definition_words": 1e9,
    "metric_max_blank_node_ratio": 0.0,
}

# What a forced message says, per rule: (pattern, kind), matched against the whole message.  "ratio" captures
# a numerator and a whole, "mean" a population and a printed mean, "count" one number.  A value or limit is
# printed with 2 to 6 decimals, or in full (``repr``) when those tie.
_N = r"[\d.e+-]+"
_GT, _LT = rf" \({_N} > {_N}\)\.", rf" \({_N} < {_N}\)\."
MESSAGES: dict[str, tuple[re.Pattern[str], str]] = {
    "METRIC001": (re.compile(r"(\d+) of (\d+) classes lack a label" + _GT), "ratio"),
    "METRIC002": (re.compile(r"(\d+) of (\d+) classes lack a definition" + _GT), "ratio"),
    "METRIC003": (re.compile(r"(\d+) of (\d+) properties lack documentation" + _GT), "ratio"),
    "METRIC004": (
        re.compile(rf"(\d+) parent classes have ({_N}) direct subclasses on average \(threshold {_N}\)\."),
        "mean",
    ),
    "METRIC005": (
        re.compile(r"(\d+) of (\d+) classes are orphans: no asserted sub/superclass, instance, domain or range" + _GT),
        "ratio",
    ),
    "METRIC006": (re.compile(r"(\d+) properties for (\d+) classes" + _LT), "ratio"),
    "METRIC008": (
        re.compile(r"(\d+) of (\d+) object/datatype properties have neither domain nor range" + _GT),
        "ratio",
    ),
    "METRIC009": (re.compile(r"(\d+) of (\d+) labelled terms have a language-tagged label" + _LT), "ratio"),
    "METRIC010": (re.compile(r"(\d+) of (\d+) structural references point to another namespace" + _GT), "ratio"),
    "METRIC011": (re.compile(r"(\d+) distinct owl:imports \(threshold \d+\)\."), "count"),
    "METRIC012": (
        re.compile(rf"(\d+) defined classes average ({_N}) words per definition \(threshold {_N}\)\."),
        "mean",
    ),
    "METRIC013": (re.compile(r"(\d+) of (\d+) subjects are blank nodes" + _GT), "ratio"),
}
# What a rule silent under the forced policy measured: the boundary, or an empty population, which the
# forced run cannot tell apart (a population of one or more makes the forced rule fire unless its value is
# the boundary itself).
SILENT_VALUE: dict[str, str] = {
    **dict.fromkeys(RULES, "0"),
    "METRIC004": "no parent",
    "METRIC006": "no class",
    "METRIC009": "none untagged",
    "METRIC012": "no definition",
}


@dataclass(frozen=True)
class Entry:
    id: str
    url: str
    sha256: str
    labels: Mapping[str, Mapping[str, str]]

    def label(self, rule: str) -> Mapping[str, str]:
        """Return the label of ``rule``: its own, else the entry's ``*``; a rule with neither is an error."""
        label = self.labels.get(rule, self.labels.get("*"))
        if label is None:
            raise ValueError(f"{self.id}: {rule} has no label; name it, or give the entry a '*' label")
        return label

    def expect(self, rule: str) -> str:
        return self.label(rule)["expect"]


def validate(entry: Entry) -> None:
    """Refuse an entry with an unknown rule key, an unlabelled rule, an unknown value or a label without a reason."""
    extra = set(entry.labels) - {"*", *RULES}
    if extra:
        raise ValueError(f"{entry.id}: labels for unknown rules {sorted(extra)}")
    for rule in RULES:
        label = entry.label(rule)
        expect, basis = label.get("expect"), label.get("basis")
        if expect not in EXPECTS or basis not in BASES or not label.get("why", "").strip():
            raise ValueError(f"{entry.id}: {rule} needs an expect in {EXPECTS}, a basis in {BASES} and a reason")
        if basis not in ALLOWED_BASES[expect]:
            raise ValueError(
                f"{entry.id}: {rule}: {expect!r} cannot have basis {basis!r} (allowed: {ALLOWED_BASES[expect]})"
            )


def safe_name(entry_id: str) -> str:
    """Return ``entry_id`` if it is a plain file name, so that ``DIR / id`` stays inside DIR; else raise."""
    if (
        not entry_id
        or entry_id in (".", "..")
        or "/" in entry_id
        or "\\" in entry_id
        or Path(entry_id).name != entry_id
    ):
        raise ValueError(f"{entry_id!r}: a corpus id must be a plain file name, without a directory or '..'")
    return entry_id


def _check_source(item: Mapping[str, Any]) -> None:
    """Refuse an entry that is not pinned (checksum, HTTPS, commit in the URL) or names no licence."""
    name = item.get("id")
    if not isinstance(item.get("sha256"), str) or not SHA256.fullmatch(item["sha256"]):
        raise ValueError(f"{name}: the SHA-256 must be 64 lower-case hex digits")
    if not isinstance(item.get("url"), str) or not item["url"].startswith("https://"):
        raise ValueError(f"{name}: the URL must use https")
    if "commit" not in item:
        raise ValueError(f"{name}: state the commit, or null for a file pinned by its checksum only")
    commit = item["commit"]
    if commit is not None and (
        not isinstance(commit, str) or not COMMIT.fullmatch(commit) or f"/{commit}/" not in item["url"]
    ):
        raise ValueError(f"{name}: the commit must be 40 hex digits and appear in the URL")
    if not isinstance(item.get("licence"), str) or not item["licence"].strip():
        raise ValueError(f"{name}: name the licence")


def load_manifest(path: Path = MANIFEST) -> list[Entry]:
    """Read and validate the manifest: safe, unique ids, pinned and licensed sources, and complete labels."""
    data = json.loads(path.read_text(encoding="utf-8"))
    entries: list[Entry] = []
    seen: set[str] = set()
    for item in data["entries"]:
        name = safe_name(item.get("id", ""))
        if name in seen:
            raise ValueError(f"{name}: the id appears twice")
        seen.add(name)
        _check_source(item)
        entry = Entry(name, item["url"], item["sha256"], item["labels"])
        validate(entry)
        entries.append(entry)
    return entries


def label_status(path: Path = MANIFEST) -> str:
    return str(json.loads(path.read_text(encoding="utf-8"))["label_status"])


def _read(directory: Path, entry: Entry) -> bytes | None:
    """Return the bytes of ``entry``'s file in ``directory``, ``None`` if there is none; refuse a link or a non-file."""
    target = directory / safe_name(entry.id)
    try:
        mode = target.lstat().st_mode
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(mode):
        raise SystemExit(f"{entry.id}: {target} is a symbolic link or not a regular file; remove it")
    # O_NOFOLLOW (POSIX) also refuses a link swapped in after the check above.
    descriptor = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
    with os.fdopen(descriptor, "rb") as handle:
        return handle.read()


def fetch(directory: Path, entries: list[Entry]) -> None:
    """Download every entry into ``directory`` (named by its id) unless a file with its checksum is there."""
    directory.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        target = directory / safe_name(entry.id)
        current = _read(directory, entry)
        if current is not None and _sha256(current) == entry.sha256:
            continue
        with urllib.request.urlopen(entry.url, timeout=120) as response:
            body = response.read()
        digest = _sha256(body)
        if digest != entry.sha256:
            raise SystemExit(f"{entry.id}: SHA-256 {digest} differs from the manifest's {entry.sha256} ({entry.url})")
        # A new file renamed over the target replaces the directory entry: it never writes through a link.
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".fetch-", delete=False) as handle:
            handle.write(body)
        try:
            os.replace(handle.name, target)
        except OSError:
            Path(handle.name).unlink()
            raise
        print(f"{entry.id}: {len(body)} bytes", flush=True)


def _sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _lint(path: Path, config: Path | None) -> dict[str, str]:
    """Run ontolint on ``path`` with only the METRIC rules; return each finding's message by rule."""
    argv = [sys.executable, "-m", "ontolint", str(path), "--format", "json", "--fail-on", "never", "--select", "METRIC"]
    if config is not None:
        argv += ["--config", str(config)]
    done = subprocess.run(argv, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise SystemExit(f"{path.name}: ontolint exited {done.returncode}: {done.stderr.strip()}")
    report = json.loads(done.stdout)
    check_report(path.name, report)
    return {finding["rule"]: finding["message"] for finding in report["findings"]}


def check_report(name: str, report: Mapping[str, Any]) -> None:
    """Refuse a report that is not of one file on which every METRIC rule ran once and reported at most once.

    A rule that did not run reports nothing, which both runs would read as a measurement: silence at the
    default, the boundary or an empty population when forced.
    """
    if len(report["files"]) != 1:
        raise SystemExit(f"{name}: the report holds {len(report['files'])} files, not one")
    executions = report["files"][0]["executions"]
    ran = sorted(e["rule"] for e in executions if e["status"] == "executed")
    if ran != list(RULES) or len(executions) != len(RULES):
        raise SystemExit(f"{name}: every METRIC rule must execute once; the report has {executions}")
    reported = [finding["rule"] for finding in report["findings"]]
    if len(reported) != len(set(reported)) or not set(reported) <= set(RULES):
        raise SystemExit(f"{name}: expected at most one finding per METRIC rule, got {sorted(reported)}")


def parse_forced(messages: Mapping[str, str]) -> dict[str, dict[str, Any]]:
    """Turn the forced run's messages into one measurement per rule; an unknown message is an error."""
    measured: dict[str, dict[str, Any]] = {}
    for rule in RULES:
        if rule == "METRIC007":
            continue
        message = messages.get(rule)
        if message is None:
            measured[rule] = {"measured": SILENT_VALUE[rule]}
            continue
        pattern, kind = MESSAGES[rule]
        match = pattern.fullmatch(message)
        if match is None:
            raise ValueError(f"{rule}: message no longer matches the measurement pattern: {message!r}")
        if kind == "ratio":
            part, whole = int(match[1]), int(match[2])
            measured[rule] = {"measured": f"{part} / {whole}", "value": round(part / whole, 4)}
        elif kind == "mean":
            measured[rule] = {"measured": f"{match[2]} over {match[1]}", "value": float(match[2])}
        else:
            measured[rule] = {"measured": match[1], "value": int(match[1])}
    measured["METRIC007"] = dict(measured["METRIC006"])
    return measured


def measure(directory: Path, entries: list[Entry]) -> dict[str, Any]:
    """Lint every fetched entry with the default and the forced policy; return the results document."""
    results: dict[str, Any] = {}
    with tempfile.TemporaryDirectory() as scratch:
        forced = Path(scratch) / "forced.json"
        forced.write_text(json.dumps(FORCED_POLICY), encoding="utf-8")
        copies = Path(scratch) / "corpus"  # apart from forced.json, which an entry may be named
        copies.mkdir()
        for entry in entries:
            body = _read(directory, entry)
            if body is None or _sha256(body) != entry.sha256:
                raise SystemExit(f"{entry.id}: missing or changed in {directory}; run fetch first")
            # ontolint reads the copy it is given, so the file it lints is the one whose checksum was checked.
            path = copies / entry.id
            path.write_bytes(body)
            fired = _lint(path, None)
            measured = parse_forced(_lint(path, forced))
            for rule in RULES:
                measured[rule]["fires"] = rule in fired
            results[entry.id] = {rule: measured[rule] for rule in RULES}
            print(f"{entry.id}: {sorted(fired)}", flush=True)
    return {"results": results}


OUTCOMES = ("tp", "fp", "tn_checked", "tn_presumed", "fn", "unknown", "unassessed")


def outcome(entry: Entry, rule: str, fires: bool) -> str:
    """Return one of OUTCOMES for ``rule`` on ``entry``; a true negative says whether its label was checked."""
    label = entry.label(rule)
    expect = label["expect"]
    if expect not in COUNTED:
        return expect
    if expect == "fire":
        return "tp" if fires else "fn"
    if fires:
        return "fp"
    return "tn_checked" if label["basis"] == "checked" else "tn_presumed"


def confusion(entries: list[Entry], results: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    """Count, per rule, the (file, rule) pairs of each outcome."""
    counts: dict[str, dict[str, int]] = {rule: dict.fromkeys(OUTCOMES, 0) for rule in RULES}
    for entry in entries:
        for rule in RULES:
            counts[rule][outcome(entry, rule, results["results"][entry.id][rule]["fires"])] += 1
    return counts


MARKS = {"fire": "F", "silent": "S", "unknown": "?", "unassessed": "-"}


def _mark(entry: Entry, rule: str, fires: bool) -> str:
    mark = MARKS[entry.expect(rule)]
    if entry.label(rule)["basis"] == "presumed":
        mark += "p"
    found = outcome(entry, rule, fires)
    return f"{mark} {found.upper()}" if found in ("fp", "fn") else mark


def render(entries: list[Entry], results: Mapping[str, Any], status: str) -> str:
    """Return the generated part of the page: the measurements, the outcome counts and the labels."""
    lines = [
        "### Measurements",
        "",
        "Each cell is the forced measurement; **bold** means the rule fires at its default. The label is",
        "in brackets: `F` expected to fire, `S` expected silent (`Sp`: presumed from the file's standing,",
        "not checked), `?` assessed and left open, `-` not assessed. A cell whose outcome contradicts its",
        "label is marked FP or FN.",
        "",
        "| File | " + " | ".join(RULES) + " |",
        "| --- |" + " --- |" * len(RULES),
    ]
    for entry in entries:
        cells = []
        for rule in RULES:
            cell = results["results"][entry.id][rule]
            text = f"**{cell['measured']}**" if cell["fires"] else cell["measured"]
            cells.append(f"{text} [{_mark(entry, rule, cell['fires'])}]")
        lines.append(f"| `{entry.id}` | " + " | ".join(cells) + " |")
    lines += [
        "",
        f"### Outcomes under the {status} labels",
        "",
        "Counts of (file, rule) pairs. A true negative is *checked* when its label's reason was verified in",
        "the file, *presumed* when it rests on the file's standing alone.",
        "",
        f"| Rule | Fires (of {len(entries)}) | True positive | False positive | True negative, checked "
        "| True negative, presumed | False negative | Left open | Not assessed |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    counts = confusion(entries, results)
    for rule in RULES:
        fired = sum(results["results"][entry.id][rule]["fires"] for entry in entries)
        lines.append(f"| {rule} | {fired} | " + " | ".join(str(counts[rule][name]) for name in OUTCOMES) + " |")
    lines += [
        "",
        f"### The {status} labels",
        "",
        "| File | Rules | Label | Basis | Why |",
        "| --- | --- | --- | --- | --- |",
    ]
    for entry in entries:
        for rule, label in sorted(entry.labels.items(), key=lambda item: (item[0] != "*", item[0])):
            rules = "every other rule" if rule == "*" and len(entry.labels) > 1 else "all" if rule == "*" else rule
            lines.append(f"| `{entry.id}` | {rules} | {label['expect']} | {label['basis']} | {label['why']} |")
    return "\n".join(lines)


def _split(content: str) -> tuple[str, str, str]:
    """Split the page into the text before the markers, the generated part and the text after them."""
    if content.count(BEGIN) != 1 or content.count(END) != 1 or content.index(BEGIN) > content.index(END):
        raise ValueError(f"the page must hold one {BEGIN} line followed by one {END} line")
    head, _, rest = content.partition(BEGIN)
    generated, _, tail = rest.partition(END)
    return head, generated.strip("\n"), tail


def write_page(text: str, page: Path = PAGE) -> None:
    head, _, tail = _split(page.read_text(encoding="utf-8"))
    page.write_text(f"{head}{BEGIN}\n{text}\n{END}{tail}", encoding="utf-8")


def generated_part(page: Path = PAGE) -> str:
    return _split(page.read_text(encoding="utf-8"))[1]


def _dump(document: Mapping[str, Any]) -> str:
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure the METRIC rules on the pinned calibration corpus.")
    parser.add_argument("command", choices=("fetch", "measure", "check", "render"))
    parser.add_argument("directory", nargs="?", type=Path, help="where the corpus files are kept (not committed)")
    args = parser.parse_args(argv)
    entries = load_manifest()
    if args.command != "render" and args.directory is None:
        parser.error(f"{args.command} needs a directory")
    if args.command == "fetch":
        fetch(args.directory, entries)
        return 0
    if args.command in ("measure", "check"):
        document = measure(args.directory, entries)
        if args.command == "check":
            if _dump(document) != RESULTS.read_text(encoding="utf-8"):
                print(f"The measurements differ from {RESULTS.relative_to(ROOT)}; run measure and review the diff.")
                return 1
            return 0
        RESULTS.write_text(_dump(document), encoding="utf-8")
    write_page(render(entries, json.loads(RESULTS.read_text(encoding="utf-8")), label_status()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
