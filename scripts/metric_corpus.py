"""Measure the METRIC rules on the pinned calibration corpus (issue #8, docs/validation/metric-calibration.md).

    uv run python scripts/metric_corpus.py fetch DIR     # download every corpus file, verify its SHA-256
    uv run python scripts/metric_corpus.py measure DIR   # lint every file, rewrite the results file and the page
    uv run python scripts/metric_corpus.py check DIR     # lint every file, fail if the results file differs
    uv run python scripts/metric_corpus.py render        # rewrite the page's generated part from the JSON files

No corpus file is committed: ``docs/validation/metric-corpus.json`` names each one by URL, commit and checksum,
and ``fetch`` refuses a file whose checksum differs.  ``load_manifest`` refuses a manifest that could make the
script read or write outside DIR (an id that is not a plain file name), an entry that is not pinned or licensed,
an id given twice and a ``label_status`` other than ``proposed`` or ``approved``, so a custom manifest is held
to the rules the committed one follows.  A corpus file that is a symbolic link or not a regular file is
refused; one with a second hard link is treated as missing; one that changes between the check and the open
is refused before a byte is read (``O_NOFOLLOW`` where it exists, and on every platform a comparison of the
opened file with the checked one).  ``fetch`` writes by renaming a new file into place, which replaces a link
instead of following it, and ``measure`` lints a private copy of the bytes it verified.

Each file is linted twice with ``--select METRIC``:

* *default*: the default policy, which says whether each rule fires as shipped;
* *forced*: every limit at the end of its range and ``metric_min_sample`` 1, so every rule with a non-empty
  population reports and its message gives the measured value.  A rule that still stays silent has measured
  the boundary itself (0 for an upper limit, full coverage for METRIC009), or an empty population.

A run is used only if its report is of the file it was asked to lint, alone, and every METRIC rule executed
in it once, with at most one finding each: a rule that did not run reports nothing, which either run would
read as a measurement.

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
from fractions import Fraction
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "docs" / "validation" / "metric-corpus.json"
RESULTS = ROOT / "docs" / "validation" / "metric-corpus-results.json"
PAGE = ROOT / "docs" / "validation" / "metric-calibration.md"
CALIBRATION = ROOT / "docs" / "metric-calibration.md"
BEGIN, END = "<!-- metric_corpus.py: begin -->", "<!-- metric_corpus.py: end -->"
CALIBRATION_MARKERS = ("<!-- metric_corpus.py: distributions begin -->", "<!-- metric_corpus.py: distributions end -->")
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


LABEL_STATUSES = ("proposed", "approved")


def _label_status(data: Mapping[str, Any]) -> str:
    status = data.get("label_status")
    if status not in LABEL_STATUSES:
        raise ValueError(f"label_status must be one of {LABEL_STATUSES}, not {status!r}")
    return str(status)


def load_manifest(path: Path = MANIFEST) -> list[Entry]:
    """Read and validate the manifest: its label status, safe unique ids, pinned licensed sources, full labels."""
    data = json.loads(path.read_text(encoding="utf-8"))
    _label_status(data)
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
    return _label_status(json.loads(path.read_text(encoding="utf-8")))


def _read(directory: Path, entry: Entry) -> bytes | None:
    """Return the bytes of ``entry``'s file in ``directory``, or ``None``; refuse a link or a non-file.

    ``None`` stands for a missing file and for a hard-linked one, which is also a file elsewhere: ``fetch``
    then replaces it, and ``measure`` refuses it.
    """
    target = directory / safe_name(entry.id)
    try:
        checked = target.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(checked.st_mode):
        raise SystemExit(f"{entry.id}: {target} is a symbolic link or not a regular file; remove it")
    if checked.st_nlink != 1:
        return None
    # A link swapped in after the check: O_NOFOLLOW (POSIX) refuses to open it; where there is no O_NOFOLLOW
    # (Windows), the file opened is not the one checked, which the comparison below refuses before a read.
    try:
        descriptor = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
    except OSError as error:
        raise SystemExit(f"{entry.id}: {target} changed while it was opened ({error})") from None
    with os.fdopen(descriptor, "rb") as handle:
        opened = os.fstat(handle.fileno())
        if (opened.st_dev, opened.st_ino) != (checked.st_dev, checked.st_ino) or opened.st_nlink != 1:
            raise SystemExit(f"{entry.id}: {target} changed while it was opened")
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


def _run(path: Path, config: Path | None, *extra: str) -> dict[str, Any]:
    """Run ontolint on ``path`` with only the METRIC rules; return its checked JSON report."""
    argv = [sys.executable, "-m", "ontolint", str(path), "--format", "json", "--fail-on", "never", "--select", "METRIC"]
    if config is not None:
        argv += ["--config", str(config)]
    done = subprocess.run([*argv, *extra], capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise SystemExit(f"{path.name}: ontolint exited {done.returncode}: {done.stderr.strip()}")
    report = json.loads(done.stdout)
    check_report(path, report)
    return report


def _lint(path: Path, config: Path | None) -> dict[str, str]:
    """Run ontolint on ``path`` with only the METRIC rules; return each finding's message by rule."""
    return {finding["rule"]: finding["message"] for finding in _run(path, config)["findings"]}


def _vector(path: Path) -> dict[str, dict[str, int]]:
    """Run ontolint on ``path`` with ``--measurements`` and return the figures the METRIC rules read."""
    return vector_of(path.name, _run(path, None, "--measurements")["files"][0])


def vector_of(name: str, file_report: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    """Return the measurements the rules read, by id; refuse one that is absent, unavailable or of another version."""
    published = {m["id"]: m for m in file_report.get("measurements", [])}
    needed = {r.measurement for r in READINGS.values()} | {r.gate for r in READINGS.values() if r.gate}
    vector: dict[str, dict[str, int]] = {}
    for measurement_id in sorted(needed):
        found = published.get(measurement_id)
        if found is None or found.get("definition_version") != DEFINITION_VERSION:
            raise SystemExit(f"{name}: {measurement_id} is absent or not of definition version {DEFINITION_VERSION}")
        keys = ("value",) if found["kind"] == "count" else ("numerator", "denominator")
        if any(not isinstance(found.get(key), int) for key in keys):
            raise SystemExit(f"{name}: {measurement_id} has no value ({found.get('reason', 'no reason given')})")
        vector[measurement_id] = {"definition_version": DEFINITION_VERSION, **{key: found[key] for key in keys}}
    return vector


def check_report(path: Path, report: Mapping[str, Any]) -> None:
    """Refuse a report that is not of ``path`` alone, or in which a METRIC rule did not run once or reported twice.

    A rule that did not run reports nothing, which both runs would read as a measurement: silence at the
    default, the boundary or an empty population when forced.
    """
    name = path.name
    if len(report["files"]) != 1:
        raise SystemExit(f"{name}: the report holds {len(report['files'])} files, not one")
    # The CLI writes the path relative to the working directory when it can, so both sides are resolved.
    reported = report["files"][0]["path"]
    if not isinstance(reported, str) or (Path.cwd() / reported).resolve() != path.resolve():
        raise SystemExit(f"{name}: the report is of {reported!r}, not of {path}")
    executions = report["files"][0]["executions"]
    ran = sorted(e["rule"] for e in executions if e["status"] == "executed")
    if ran != list(RULES) or len(executions) != len(RULES):
        raise SystemExit(f"{name}: every METRIC rule must execute once; the report has {executions}")
    rules = [finding["rule"] for finding in report["findings"]]
    if len(rules) != len(set(rules)) or not set(rules) <= set(RULES):
        raise SystemExit(f"{name}: expected at most one finding per METRIC rule, got {sorted(rules)}")


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


PRINT_TOLERANCE = 0.005  # a forced mean is printed to two decimals
DEFINITION_VERSION = 1  # the measurement definitions the readings below were written against (measurements.md)


@dataclass(frozen=True)
class Reading:
    """How a METRIC rule turns a measurement into the value it compares with its limit."""

    measurement: str  # the id read
    missing: bool  # the rule reads what is absent (denominator - numerator) rather than the numerator
    gate: str | None  # the measurement whose denominator must reach the sample gate; None: no gate
    upper: bool  # fires above the limit, else below it


READINGS: dict[str, Reading] = {
    "METRIC001": Reading("class_label_coverage", True, "class_label_coverage", True),
    "METRIC002": Reading("class_definition_coverage", True, "class_definition_coverage", True),
    "METRIC003": Reading("property_documentation_coverage", True, "property_documentation_coverage", True),
    "METRIC004": Reading("class_fanout", False, "orphan_classes", True),  # gated on the owned classes
    "METRIC005": Reading("orphan_classes", False, "orphan_classes", True),
    "METRIC006": Reading("relation_properties_per_class", False, "relation_properties_per_class", False),
    "METRIC007": Reading("relation_properties_per_class", False, "relation_properties_per_class", True),
    "METRIC008": Reading("unsigned_properties", False, "unsigned_properties", True),
    "METRIC009": Reading("label_language_coverage", False, "label_language_coverage", False),
    "METRIC010": Reading("foreign_references", False, "foreign_references", True),
    "METRIC011": Reading("unresolved_imports", False, None, True),
    "METRIC012": Reading("definition_length", False, "definition_length", False),
    "METRIC013": Reading("blank_subjects", False, "blank_subjects", True),
}
LIMIT_KEYS: dict[str, str] = {
    "METRIC001": "metric_max_unlabelled_ratio",
    "METRIC002": "metric_max_undefined_ratio",
    "METRIC003": "metric_max_undocumented_property_ratio",
    "METRIC004": "metric_max_mean_fanout",
    "METRIC005": "metric_max_orphan_ratio",
    "METRIC006": "metric_min_property_class_ratio",
    "METRIC007": "metric_max_property_class_ratio",
    "METRIC008": "metric_max_unsigned_property_ratio",
    "METRIC009": "metric_min_language_coverage",
    "METRIC010": "metric_max_foreign_reference_ratio",
    "METRIC011": "metric_max_imports",
    "METRIC012": "metric_min_definition_words",
    "METRIC013": "metric_max_blank_node_ratio",
}


def default_limits() -> dict[str, Fraction]:
    """Return the shipped limit of every rule, read from the policy so that it cannot drift from the code."""
    from ontolint.policy import Policy  # noqa: PLC0415 -- only the calibration needs the package itself

    policy = Policy()
    return {rule: Fraction(getattr(policy, key)) for rule, key in LIMIT_KEYS.items()}


def sample_gate() -> int:
    from ontolint.policy import Policy  # noqa: PLC0415

    return int(Policy().metric_min_sample)


def reading(rule: str, vector: Mapping[str, Mapping[str, int]], gate: int) -> Fraction | None:
    """Return the value ``rule`` compares with its limit, or ``None`` when it makes no comparison.

    ``None`` is a population below the sample gate (``gate``), an empty population, or METRIC004 with no parent.
    """
    read = READINGS[rule]
    if read.gate is not None and vector[read.gate]["denominator"] < gate:
        return None
    figures = vector[read.measurement]
    if "value" in figures:
        return Fraction(figures["value"])
    if figures["denominator"] == 0:
        return None
    part = figures["denominator"] - figures["numerator"] if read.missing else figures["numerator"]
    return Fraction(part, figures["denominator"])


def would_fire(rule: str, value: Fraction | None, limit: Fraction) -> bool:
    """Say whether ``value`` crosses ``limit`` as the rule does: strictly, and never without a value."""
    if value is None:
        return False
    return value > limit if READINGS[rule].upper else value < limit


# What a rule's forced run prints when silent and the value could still be a measurement: the boundary.
BOUNDARY: dict[str, int] = {**{rule: 0 for rule, read in READINGS.items() if read.upper}, "METRIC009": 1}


def check_vector(name: str, rule: str, vector: Mapping[str, Mapping[str, int]], forced: Mapping[str, Any]) -> None:
    """Refuse a measurement vector that disagrees with what the forced run printed for ``rule``.

    The forced run prints the value of every non-empty population; a silent one measured the boundary or an
    empty population.  Two independent readings of one number must agree before either is recorded.
    """
    value = reading(rule, vector, 1)  # the forced policy's sample gate is 1
    if "value" in forced:
        agrees = value is not None and abs(float(value) - forced["value"]) <= PRINT_TOLERANCE
    else:
        agrees = value is None or (rule in BOUNDARY and value == BOUNDARY[rule])
    if not agrees:
        raise SystemExit(f"{name}: {rule} the vector reads {value} and disagrees with the forced run: {dict(forced)}")


def measure(directory: Path, entries: list[Entry]) -> dict[str, Any]:
    """Lint every fetched entry with the default and the forced policy; return the results document."""
    results: dict[str, Any] = {}
    vectors: dict[str, Any] = {}
    gate, limits = sample_gate(), default_limits()
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
            vector = _vector(path)
            for rule in RULES:
                measured[rule]["fires"] = rule in fired
                if rule != "METRIC007":  # METRIC007 reads the figure METRIC006 prints
                    check_vector(entry.id, rule, vector, measured[rule])
                if would_fire(rule, reading(rule, vector, gate), limits[rule]) != (rule in fired):
                    raise SystemExit(f"{entry.id}: {rule} fired={rule in fired}, but its vector says otherwise")
            results[entry.id] = {rule: measured[rule] for rule in RULES}
            vectors[entry.id] = vector
            print(f"{entry.id}: {sorted(fired)}", flush=True)
    return {"results": results, "vectors": vectors}


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


def _split(content: str, begin: str = BEGIN, end: str = END) -> tuple[str, str, str]:
    """Split the page into the text before the markers, the generated part and the text after them."""
    if content.count(begin) != 1 or content.count(end) != 1 or content.index(begin) > content.index(end):
        raise ValueError(f"the page must hold one {begin} line followed by one {end} line")
    head, _, rest = content.partition(begin)
    generated, _, tail = rest.partition(end)
    return head, generated.strip("\n"), tail


def write_page(text: str, page: Path = PAGE, begin: str = BEGIN, end: str = END) -> None:
    head, _, tail = _split(page.read_text(encoding="utf-8"), begin, end)
    page.write_text(f"{head}{begin}\n{text}\n{end}{tail}", encoding="utf-8")


def generated_part(page: Path = PAGE, begin: str = BEGIN, end: str = END) -> str:
    return _split(page.read_text(encoding="utf-8"), begin, end)[1]


def _quantile(ordered: list[Fraction], numerator: int, denominator: int) -> Fraction:
    """Return the ``numerator/denominator`` quantile by linear interpolation between order statistics (exact)."""
    position = Fraction((len(ordered) - 1) * numerator, denominator)
    low = position.numerator // position.denominator
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def describe(values: list[Fraction]) -> dict[str, Any]:
    """Return the size, minimum, quartiles (inclusive method) and maximum of ``values``, all exact."""
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "min": ordered[0],
        "q1": _quantile(ordered, 1, 4),
        "median": _quantile(ordered, 1, 2),
        "q3": _quantile(ordered, 3, 4),
        "max": ordered[-1],
    }


def values_of(rule: str, results: Mapping[str, Any]) -> dict[str, Fraction]:
    """Return, by file, the value ``rule`` compared with its limit; a file that made no comparison is left out."""
    gate = sample_gate()
    found = {name: reading(rule, vector, gate) for name, vector in results["vectors"].items()}
    return {name: value for name, value in found.items() if value is not None}


def _num(value: Fraction | float, rule: str) -> str:
    return str(int(value)) if rule == "METRIC011" else f"{float(value):.3f}"


def distribution_rows(entries: list[Entry], results: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Return, per rule, the distribution of its values over the corpus and how many files its default flags."""
    limits = default_limits()
    rows: dict[str, dict[str, Any]] = {}
    for rule in RULES:
        values = values_of(rule, results)
        row = describe(list(values.values()))
        row["limit"] = limits[rule]
        row["flagged"] = sum(results["results"][entry.id][rule]["fires"] for entry in entries)
        row["excluded"] = len(entries) - row["n"]
        rows[rule] = row
    return rows


def _bound(value: Fraction | None, infinity: str) -> str:
    return infinity if value is None else f"{float(value):.4f}"


def consistent_limits(entries: list[Entry], rule: str, values: Mapping[str, Fraction], *, checked_only: bool) -> str:
    """Return the interval of limits under which ``rule`` has no false positive and no false negative.

    Only files labelled ``fire`` or ``silent`` that have a value count (and, with ``checked_only``, only those
    whose label was checked).  An upper limit fires above it, so it must be at least every silent value and
    below every fire value; a lower limit fires below it, so it must be above every fire value and at most
    every silent value.  Bounds are printed to four decimals; the exact values are in the results file.
    """
    fire: list[Fraction] = []
    silent: list[Fraction] = []
    for entry in entries:
        label = entry.label(rule)
        if entry.id not in values or label["expect"] not in COUNTED or (checked_only and label["basis"] != "checked"):
            continue
        (fire if label["expect"] == "fire" else silent).append(values[entry.id])
    if READINGS[rule].upper:
        low, high = (max(silent) if silent else None), (min(fire) if fire else None)
        empty = low is not None and high is not None and low >= high
        text = f"[{_bound(low, '-inf')}, {_bound(high, '+inf')})"
    else:
        low, high = (max(fire) if fire else None), (min(silent) if silent else None)
        empty = low is not None and high is not None and low >= high
        text = f"({_bound(low, '-inf')}, {_bound(high, '+inf')}{']' if high is not None else ')'}"
    return "none" if empty else text


def render_calibration(entries: list[Entry], results: Mapping[str, Any]) -> str:
    """Return the generated part of docs/metric-calibration.md: the distributions and the limits the labels allow."""
    lines = [
        "### Distributions",
        "",
        f"Per rule, over the {len(entries)} corpus files that make a comparison (a population at or above the sample",
        "gate of the rule, and for METRIC004 a parent class). `n` is that number, `flagged` how many of the",
        f"{len(entries)} files the default flags, `excluded` the files with no comparison. Quartiles are linear",
        "interpolations (inclusive method) of exact fractions, printed to three decimals; METRIC001 to METRIC003",
        "read the share that is *missing*. METRIC006 and METRIC007 read one measurement.",
        "",
        "| Rule | n | flagged | excluded | Default | min | Q1 | median | Q3 | max |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for rule, row in distribution_rows(entries, results).items():
        sign = ">" if READINGS[rule].upper else "<"
        cells = [_num(row[k], rule) if row["n"] else "-" for k in ("min", "q1", "median", "q3", "max")]
        limit = _num(row["limit"], rule)
        lines.append(
            f"| {rule} | {row['n']} | {row['flagged']} | {row['excluded']} | {sign} {limit} | "
            + " | ".join(cells)
            + " |"
        )
    lines += [
        "",
        "### Limits the labels allow",
        "",
        "For each rule, the interval of limits that would give no false positive and no false negative under the",
        "proposed labels, among the files that make a comparison. `[a, b)` means a limit of at least a and below b",
        "for a rule that fires above its limit; `(a, b]` means above a and at most b for one that fires below it;",
        "`none` means a silent and a fire label cross. The first column uses every counted label, including the",
        "presumed silent ones; the second only labels whose reason was checked in the file. The default is inside",
        "the interval only when it is marked yes. An interval is only as good as the labels.",
        "",
        "| Rule | Default | All counted labels | Default inside | Checked labels only | Default inside |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    limits = default_limits()
    for rule in RULES:
        values = values_of(rule, results)
        cells = []
        for checked in (False, True):
            interval = consistent_limits(entries, rule, values, checked_only=checked)
            cells += [interval, "yes" if _inside(interval, limits[rule], READINGS[rule].upper) else "no"]
        lines.append(f"| {rule} | {_num(limits[rule], rule)} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _inside(interval: str, limit: Fraction, upper: bool) -> bool:
    """Say whether ``limit`` lies in a printed interval (a four-decimal comparison, as printed)."""
    if interval == "none":
        return False
    low, high = (part.strip() for part in interval[1:-1].split(","))
    value = float(limit)
    above_low = low == "-inf" or (value >= float(low) if upper else value > float(low))
    below_high = high == "+inf" or (value < float(high) if upper else value <= float(high))
    return above_low and below_high


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
    document = json.loads(RESULTS.read_text(encoding="utf-8"))
    write_page(render(entries, document, label_status()))
    write_page(render_calibration(entries, document), CALIBRATION, *CALIBRATION_MARKERS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
