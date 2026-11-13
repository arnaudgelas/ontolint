"""Measure the METRIC rules on the pinned calibration corpus (issue #8, docs/validation/metric-calibration.md).

    uv run python scripts/metric_corpus.py fetch DIR     # download every corpus file, verify its SHA-256
    uv run python scripts/metric_corpus.py measure DIR   # lint every file, rewrite the results file and the page
    uv run python scripts/metric_corpus.py check DIR     # lint every file, fail if the results file differs
    uv run python scripts/metric_corpus.py render        # rewrite the page's generated part from the JSON files

No corpus file is committed: ``docs/validation/metric-corpus.json`` names each one by URL, commit and checksum,
and ``fetch`` refuses a file whose checksum differs.  Each file is linted twice with ``--select METRIC``:

* *default*: the default policy, which says whether each rule fires as shipped;
* *forced*: every limit at the end of its range and ``metric_min_sample`` 1, so every rule with a non-empty
  population reports and its message gives the measured value.  A rule that still stays silent has measured
  the boundary itself (0 for an upper limit, full coverage for METRIC009), or an empty population.

METRIC007 is never forced: it reads the same ratio as METRIC006, whose forced message gives it.  The labels in
the manifest are proposals until the maintainer approves them (``"status": "approved"``).
"""

# ruff: noqa: S310, S603 -- downloads fixed, checksummed HTTPS URLs; runs this interpreter on ontolint.

from __future__ import annotations

import argparse
import hashlib
import json
import re
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
LABELS = ("fire", "silent")

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

# What a forced message says, per rule: (pattern, kind).  "ratio" captures a numerator and a whole,
# "mean" a population and a printed mean, "count" one number.
MESSAGES: dict[str, tuple[re.Pattern[str], str]] = {
    "METRIC001": (re.compile(r"^(\d+) of (\d+) classes lack a label "), "ratio"),
    "METRIC002": (re.compile(r"^(\d+) of (\d+) classes lack a definition "), "ratio"),
    "METRIC003": (re.compile(r"^(\d+) of (\d+) properties lack documentation "), "ratio"),
    "METRIC004": (re.compile(r"^(\d+) parent classes have ([\d.]+) direct subclasses on average "), "mean"),
    "METRIC005": (re.compile(r"^(\d+) of (\d+) classes are orphans: "), "ratio"),
    "METRIC006": (re.compile(r"^(\d+) properties for (\d+) classes "), "ratio"),
    "METRIC008": (re.compile(r"^(\d+) of (\d+) object/datatype properties have neither domain nor range "), "ratio"),
    "METRIC009": (re.compile(r"^(\d+) of (\d+) labelled terms have a language-tagged label "), "ratio"),
    "METRIC010": (re.compile(r"^(\d+) of (\d+) structural references point to another namespace "), "ratio"),
    "METRIC011": (re.compile(r"^(\d+) distinct owl:imports "), "count"),
    "METRIC012": (re.compile(r"^(\d+) defined classes average ([\d.]+) words per definition "), "mean"),
    "METRIC013": (re.compile(r"^(\d+) of (\d+) subjects are blank nodes "), "ratio"),
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

    def expect(self, rule: str) -> str | None:
        """Return the label for ``rule`` (``fire`` or ``silent``), or None when unlabelled or left open."""
        label = self.labels.get(rule, self.labels.get("*", {})).get("expect")
        return label if label in LABELS else None


def load_manifest(path: Path = MANIFEST) -> list[Entry]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [Entry(item["id"], item["url"], item["sha256"], item.get("labels", {})) for item in data["entries"]]


def label_status(path: Path = MANIFEST) -> str:
    return str(json.loads(path.read_text(encoding="utf-8"))["label_status"])


def fetch(directory: Path, entries: list[Entry]) -> None:
    """Download every entry into ``directory`` (named by its id) unless a file with its checksum is there."""
    directory.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        target = directory / entry.id
        if target.is_file() and _sha256(target.read_bytes()) == entry.sha256:
            continue
        with urllib.request.urlopen(entry.url, timeout=120) as response:
            body = response.read()
        digest = _sha256(body)
        if digest != entry.sha256:
            raise SystemExit(f"{entry.id}: SHA-256 {digest} differs from the manifest's {entry.sha256} ({entry.url})")
        target.write_bytes(body)
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
    not_run = [e for f in report["files"] for e in f["executions"] if e["status"] != "executed"]
    if not_run:
        raise SystemExit(f"{path.name}: rules did not execute: {not_run}")
    return {finding["rule"]: finding["message"] for finding in report["findings"]}


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
        match = pattern.match(message)
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
        for entry in entries:
            path = directory / entry.id
            if not path.is_file() or _sha256(path.read_bytes()) != entry.sha256:
                raise SystemExit(f"{entry.id}: missing or changed in {directory}; run fetch first")
            fired = _lint(path, None)
            measured = parse_forced(_lint(path, forced))
            for rule in RULES:
                measured[rule]["fires"] = rule in fired
            results[entry.id] = {rule: measured[rule] for rule in RULES}
            print(f"{entry.id}: {sorted(fired)}", flush=True)
    return {"results": results}


def confusion(entries: list[Entry], results: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    """Count, per rule, labelled pairs by outcome: tp, fp, tn, fn; and the pairs left unlabelled."""
    counts: dict[str, dict[str, int]] = {
        rule: dict.fromkeys(("tp", "fp", "tn", "fn", "unlabelled"), 0) for rule in RULES
    }
    for entry in entries:
        for rule in RULES:
            fires = results["results"][entry.id][rule]["fires"]
            label = entry.expect(rule)
            if label is None:
                counts[rule]["unlabelled"] += 1
            elif label == "fire":
                counts[rule]["tp" if fires else "fn"] += 1
            else:
                counts[rule]["fp" if fires else "tn"] += 1
    return counts


def _mark(label: str | None, fires: bool) -> str:
    mark = {"fire": "F", "silent": "S", None: "?"}[label]
    if label == "fire" and not fires:
        return mark + " FN"
    if label == "silent" and fires:
        return mark + " FP"
    return mark


def render(entries: list[Entry], results: Mapping[str, Any], status: str) -> str:
    """Return the generated part of the page: the measurements, the outcome counts and the labels."""
    lines = [
        "### Measurements",
        "",
        "Each cell is the forced measurement; **bold** means the rule fires at its default. The label is",
        "in brackets: `F` expected to fire, `S` expected silent, `?` unlabelled or left open. A cell whose",
        "outcome contradicts its label is marked FP or FN.",
        "",
        "| File | " + " | ".join(RULES) + " |",
        "| --- |" + " --- |" * len(RULES),
    ]
    for entry in entries:
        cells = []
        for rule in RULES:
            cell = results["results"][entry.id][rule]
            text = f"**{cell['measured']}**" if cell["fires"] else cell["measured"]
            cells.append(f"{text} [{_mark(entry.expect(rule), cell['fires'])}]")
        lines.append(f"| `{entry.id}` | " + " | ".join(cells) + " |")
    lines += [
        "",
        f"### Outcomes under the {status} labels",
        "",
        f"| Rule | Fires (of {len(entries)}) | True positive | False positive | True negative | False negative "
        "| Unlabelled |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    counts = confusion(entries, results)
    for rule in RULES:
        fired = sum(results["results"][entry.id][rule]["fires"] for entry in entries)
        c = counts[rule]
        lines.append(f"| {rule} | {fired} | {c['tp']} | {c['fp']} | {c['tn']} | {c['fn']} | {c['unlabelled']} |")
    lines += ["", f"### The {status} labels", "", "| File | Rules | Label | Why |", "| --- | --- | --- | --- |"]
    for entry in entries:
        for rule, label in sorted(entry.labels.items(), key=lambda item: (item[0] != "*", item[0])):
            rules = "every other rule" if rule == "*" and len(entry.labels) > 1 else "all" if rule == "*" else rule
            lines.append(f"| `{entry.id}` | {rules} | {label['expect']} | {label['why']} |")
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
