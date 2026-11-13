"""Report rendering, fingerprints, and exit-code gating for lint findings.

A run produces one :class:`FileReport` per input file.  JSON and SARIF always carry the
per-rule execution status so a skipped, unsupported or failed rule can never be mistaken
for a clean pass.  SARIF results carry a source region when the loader could locate the
finding's focus (:mod:`ontolint.source_locations`); other formats do not use locations.
The Markdown summary (:func:`render_markdown`) is a bounded view of a run for a pull request,
in which no text of the report can become markup.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ._version import package_version
from .models import ExecutionStatus, Finding, RuleExecution, RuleSpec, plain_evidence
from .modules import module_summary
from .redaction import clip, redact_rendered
from .rules.registry import default_registry

SEVERITY_ORDER = ("error", "warning", "info")
SARIF_LEVELS = {"error": "error", "warning": "warning", "info": "note"}
FAIL_THRESHOLDS = {"error": 0, "warning": 1, "info": 2, "never": -1}
SCHEMA_VERSION = 1
TOOL_FAILURE_EXIT = 2
# Statuses that mean a requested rule did not deliver a verdict; they gate like a tool failure.
BROKEN = (ExecutionStatus.FAILED, ExecutionStatus.UNSUPPORTED)
NOTIFICATION_LEVELS = {
    ExecutionStatus.FAILED: "error",
    ExecutionStatus.UNSUPPORTED: "warning",
    ExecutionStatus.SKIPPED: "note",
}


@dataclass(frozen=True)
class Location:
    """A one-based source position (line, and column in Unicode code points) inside a file."""

    line: int
    column: int | None = None


# gremlin: pardon[untestable] every test covers a decorator: too slow to time; test_mutation_pardon_audit kills it
@dataclass(frozen=True)
class Origin:
    """The file a finding belongs to when it is not the linted file itself (an imported module)."""

    path: str
    uri: str


@dataclass(frozen=True)
class FileReport:
    """Findings and rule execution outcomes for one linted file."""

    path: str
    uri: str
    findings: tuple[Finding, ...]
    executions: tuple[RuleExecution, ...] = ()
    locations: Mapping[Finding, Location] = field(default_factory=dict[Finding, Location])
    location_problem: str | None = None  # why source regions could not be computed, if they could not
    # With --follow-imports: findings about a term an imported module declares, mapped to that module.
    origins: Mapping[Finding, Origin] = field(default_factory=dict[Finding, Origin])
    # With --module-annotation or --module-by: the modules inside the file each finding belongs to.
    modules: Mapping[Finding, tuple[str, ...]] = field(default_factory=dict[Finding, tuple[str, ...]])
    # For a dataset with named graphs (TriG, N-Quads, JSON-LD): the graphs each finding's terms are stated in.
    graphs: Mapping[Finding, tuple[str, ...]] = field(default_factory=dict[Finding, tuple[str, ...]])
    # For a finding about several files (ONT007, ONT008): the files besides its own, each with its region if known.
    others: Mapping[Finding, tuple[tuple[Origin, Location | None], ...]] = field(
        default_factory=dict[Finding, tuple[tuple[Origin, Location | None], ...]]
    )

    def path_of(self, finding: Finding) -> str:
        """The report path of the file ``finding`` belongs to: its module's, or this file's."""
        origin = self.origins.get(finding)
        return origin.path if origin is not None else self.path

    def uri_of(self, finding: Finding) -> str:
        """The artifact URI of the file ``finding`` belongs to: its module's, or this file's."""
        origin = self.origins.get(finding)
        return origin.uri if origin is not None else self.uri


@dataclass(frozen=True)
class RunReport:
    """All file reports of one invocation plus the metadata of the rules that were selected."""

    files: tuple[FileReport, ...]
    rules: tuple[RuleSpec, ...] = ()
    severity_overrides: Mapping[str, str] = field(default_factory=dict[str, str])
    # Baseline entries (their version 1 fingerprints) that matched no finding of this run by either hash;
    # ``None`` when no baseline was read.
    stale_baseline: tuple[str, ...] | None = None
    # For each file, in the order of ``files``, the findings the baseline accepted (removed from the file);
    # ``None`` when no baseline was read.  Only the Markdown summary renders them.
    baselined: tuple[tuple[Finding, ...], ...] | None = None

    @property
    def findings(self) -> tuple[Finding, ...]:
        """Findings of every file, in file order."""
        return tuple(f for report in self.files for f in report.findings)

    @property
    def broken(self) -> tuple[tuple[str, RuleExecution], ...]:
        """``(path, execution)`` for every failed or unsupported rule."""
        return tuple((r.path, x) for r in self.files for x in r.executions if x.status in BROKEN)


def fingerprint(f: Finding, path: str | None = None) -> str:
    """Return the version 1 baseline hash of a finding, which depends on its message (see :func:`identity`).

    Single-file runs hash ``(rule, focus, message)``, unchanged from earlier releases so existing
    baselines keep working.  Multi-file runs pass the report path, which is appended to the payload.
    """
    parts = [f.rule, f.focus, f.message] if path is None else [f.rule, f.focus, f.message, path]
    payload = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8", errors="surrogatepass")).hexdigest()


IDENTITY_TAG = "ontolint-identity-2"


def identity(f: Finding) -> str:
    """Return the version 2 baseline identity: a hash of the rule, the focus and the subject, never the message.

    The tag and the nested subject list keep the payload from ever reading as a version 1 one.  The path is
    not hashed: a baseline keys identities by report path, so one identity can be matched with or without it.
    """
    payload = json.dumps([IDENTITY_TAG, f.rule, f.focus, list(f.subject)], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8", errors="surrogatepass")).hexdigest()


def effective_severity(spec: RuleSpec, overrides: Mapping[str, str]) -> str:
    """The severity a rule reports at after profile and policy overrides."""
    return overrides.get(spec.rule_id, spec.severity.value)


def rule_metadata(spec: RuleSpec, overrides: Mapping[str, str]) -> dict[str, Any]:
    """JSON description of a rule."""
    return {
        "id": spec.rule_id,
        "family": spec.family,
        "title": spec.title,
        "severity": effective_severity(spec, overrides),
        "default_severity": spec.severity.value,
        "category": spec.category,
        "backend": spec.backend.value,
        "scope": spec.scope.value,
        "requires": spec.requires.value,
        "suggestion": spec.suggestion,
    }


def _severity_summary(findings: Sequence[Finding]) -> dict[str, int]:
    return dict(Counter(x.severity for x in findings))


def _execution_dicts(executions: Sequence[RuleExecution]) -> list[dict[str, str]]:
    return [{"rule": x.rule_id, "status": x.status.value, "detail": x.detail} for x in executions]


def summarise_executions(executions: Sequence[RuleExecution]) -> dict[str, int]:
    """Count executions per status; every status is present so absent states are explicit."""
    counts = Counter(x.status for x in executions)
    return {status.value: counts[status] for status in ExecutionStatus}


def _all_executions(report: RunReport) -> list[RuleExecution]:
    return [x for r in report.files for x in r.executions]


def to_json(report: RunReport) -> dict[str, Any]:
    """The JSON document: the historical ``summary``/``findings`` keys plus schema, rules and executions."""
    return {
        "schema_version": SCHEMA_VERSION,
        "summary": _severity_summary(report.findings),
        "findings": [
            {
                **f.to_dict(),
                "path": r.path_of(f),
                # Each present only when it applies, so other files keep their historical shape.
                **({"graphs": list(r.graphs[f])} if f in r.graphs else {}),
                **({"modules": list(r.modules[f])} if f in r.modules else {}),
            }
            for r in report.files
            for f in r.findings
        ],
        "execution_summary": summarise_executions(_all_executions(report)),
        "rules": [rule_metadata(s, report.severity_overrides) for s in report.rules],
        "files": [
            {
                "path": r.path,
                "summary": _severity_summary(r.findings),
                "execution_summary": summarise_executions(r.executions),
                "executions": _execution_dicts(r.executions),
                # Present only with module grouping, so runs without it keep their historical shape.
                **({"module_summary": module_summary(_shown_modules(r))} if r.modules else {}),
            }
            for r in report.files
        ],
        # Present only when a baseline was read, so runs without one keep their historical shape.
        **(
            {"baseline": {"stale_fingerprints": list(report.stale_baseline)}}
            if report.stale_baseline is not None
            else {}
        ),
    }


def _shown_modules(report: FileReport) -> dict[Finding, tuple[str, ...]]:
    """The module of each finding still in the report (a baseline may have removed some)."""
    return {f: report.modules[f] for f in report.findings if f in report.modules}


def stale_baseline_message(count: int) -> str:
    """The note shown when ``count`` baseline fingerprints matched no finding of the run (OPS003)."""
    return (
        f"Baseline: {count} fingerprint(s) match no finding of this run (fixed, or not selected); "
        "regenerate the baseline with --write-baseline to drop them."
    )


def render_json(report: RunReport) -> str:
    """Render :func:`to_json` as indented JSON."""
    return json.dumps(to_json(report), indent=2)


def _sarif_rule(spec: RuleSpec, overrides: Mapping[str, str]) -> dict[str, Any]:
    return {
        "id": spec.rule_id,
        "name": spec.rule_id,
        "shortDescription": {"text": spec.title},
        "fullDescription": {"text": f"{spec.title}. {spec.suggestion}"},
        "help": {"text": spec.suggestion},
        "defaultConfiguration": {"level": SARIF_LEVELS[effective_severity(spec, overrides)]},
        "properties": {"category": spec.category, "backend": spec.backend.value, "scope": spec.scope.value},
    }


def _sarif_location(uri: str, location: Location | None) -> dict[str, Any]:
    physical: dict[str, Any] = {"artifactLocation": {"uri": uri}}
    if location is not None:
        region: dict[str, int] = {"startLine": location.line}
        if location.column is not None:
            region["startColumn"] = location.column
        physical["region"] = region
    return {"physicalLocation": physical}


def _sarif_result(f: Finding, file: FileReport, rule_index: Mapping[str, int]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ruleId": f.rule,
        "level": SARIF_LEVELS[f.severity],
        "message": {"text": f"{f.message} Focus: {f.focus}. Suggestion: {f.suggestion}"},
        "locations": [_sarif_location(file.uri_of(f), file.locations.get(f))],
    }
    # A finding about several files (ONT007, ONT008) is fixed by changing one of them, so SARIF 2.1.0
    # (section 3.27.12) gives it one location; the other files are related locations (section 3.27.22).
    related = [
        {"id": number, **_sarif_location(origin.uri, location), "message": {"text": "Also declared here."}}
        for number, (origin, location) in enumerate(file.others.get(f, ()), start=1)
    ]
    if related:
        result["relatedLocations"] = related
    if f.rule in rule_index:
        result["ruleIndex"] = rule_index[f.rule]
    properties: dict[str, Any] = {}
    if f.details is not None:
        properties["details"] = f.details
    if f.evidence is not None:
        properties["evidence"] = plain_evidence(f.evidence)
    if f in file.graphs:
        properties["graphs"] = list(file.graphs[f])
    if f in file.modules:
        properties["modules"] = list(file.modules[f])
    if properties:
        result["properties"] = properties
    return result


def _sarif_notification(file: FileReport, x: RuleExecution) -> dict[str, Any]:
    return {
        "level": NOTIFICATION_LEVELS[x.status],
        "message": {"text": f"Rule {x.rule_id} {x.status.value}: {x.detail}"},
        "associatedRule": {"id": x.rule_id},
        "locations": [{"physicalLocation": {"artifactLocation": {"uri": file.uri}}}],
        "properties": {"status": x.status.value},
    }


def _sarif_location_notification(file: FileReport) -> dict[str, Any]:
    return {
        "level": "note",
        "message": {"text": f"Source regions are unavailable for this file: {file.location_problem}"},
        "locations": [{"physicalLocation": {"artifactLocation": {"uri": file.uri}}}],
    }


def _sarif_invocation(report: RunReport, exit_status: int | None) -> dict[str, Any]:
    """Execution outcome; non-executed rules are notifications, so they never read as a clean pass."""
    invocation: dict[str, Any] = {
        "executionSuccessful": not report.broken,
        "toolExecutionNotifications": [
            *(
                _sarif_notification(r, x)
                for r in report.files
                for x in r.executions
                if x.status != ExecutionStatus.EXECUTED
            ),
            *(_sarif_location_notification(r) for r in report.files if r.location_problem),
            *(
                [{"level": "note", "message": {"text": stale_baseline_message(len(report.stale_baseline))}}]
                if report.stale_baseline
                else []
            ),
        ],
        "properties": {"executionSummary": summarise_executions(_all_executions(report))},
    }
    if exit_status is not None:
        invocation["exitCode"] = exit_status
    return invocation


def to_sarif_report(report: RunReport, exit_status: int | None = None) -> dict[str, Any]:
    """Return a SARIF 2.1.0 document: rule metadata, results with artifact locations and an invocation."""
    rule_index = {s.rule_id: i for i, s in enumerate(report.rules)}
    run: dict[str, Any] = {
        "tool": {
            "driver": {
                "name": "ontolint",
                "version": package_version(),
                "rules": [_sarif_rule(s, report.severity_overrides) for s in report.rules],
            }
        },
        "invocations": [_sarif_invocation(report, exit_status)],
        "results": [_sarif_result(f, r, rule_index) for r in report.files for f in r.findings],
    }
    if report.findings:
        # SARIF requires the column unit when a run processes text artifacts and has results.
        run["columnKind"] = "unicodeCodePoints"
    return {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [run],
    }


def to_sarif(findings: Sequence[Finding]) -> dict[str, Any]:
    """Return a SARIF document for bare ``findings`` (rule metadata comes from the built-in registry)."""
    registry = default_registry()
    used = sorted({f.rule for f in findings})
    specs = tuple(registry.get(rule) for rule in used if rule in registry)
    return to_sarif_report(RunReport((FileReport("", "", tuple(findings)),), specs))


def render_sarif(report: RunReport, exit_status: int | None = None) -> str:
    """Render :func:`to_sarif_report` as indented JSON."""
    return json.dumps(to_sarif_report(report, exit_status), indent=2)


def _where(f: Finding, file: FileReport) -> str:
    """The ``In:`` line: the imported module's file, the named graphs and the modules inside the file, if any."""
    parts = [file.origins[f].path] if f in file.origins else []
    graphs = file.graphs.get(f, ())
    if graphs:
        parts.append(("graph " if len(graphs) == 1 else "graphs ") + ", ".join(graphs))
    names = file.modules.get(f, ())
    if names:
        parts.append(("module " if len(names) == 1 else "modules ") + ", ".join(names))
    return f"\n    In: {', '.join(parts)}" if parts else ""


def _finding_lines(file: FileReport) -> list[str]:
    lines = [
        f"[{f.severity.upper():7}] {f.rule} {f.focus}: {f.message}\n    Fix: {f.suggestion}" + _where(f, file)
        for f in file.findings
    ]
    summary = module_summary(_shown_modules(file))
    if summary:
        lines.append("Findings by module:")
        lines.extend(
            f"    {name}: " + ", ".join(f"{counts[s]} {s}" for s in SEVERITY_ORDER if s in counts)
            for name, counts in summary.items()
        )
    return lines


def render_text(report: RunReport) -> str:
    """Render findings as text; a single file keeps the historical layout, several get per-file sections."""
    if len(report.files) == 1:
        only = report.files[0]
        return "\n".join([f"Ontology linter: {len(only.findings)} finding(s)", *_finding_lines(only)])
    lines = [f"Ontology linter: {len(report.findings)} finding(s) in {len(report.files)} file(s)"]
    for r in report.files:
        lines.append(f"== {r.path}: {len(r.findings)} finding(s)")
        lines.extend(_finding_lines(r))
    return "\n".join(lines)


def _execution_counts(executions: Sequence[RuleExecution]) -> str:
    """The ``Rule execution:`` line: how many rules ended in each status, every status named."""
    summary = ", ".join(f"{count} {status}" for status, count in summarise_executions(executions).items())
    return f"Rule execution: {summary}"


def render_executions(executions: Sequence[RuleExecution]) -> str:
    """Render rule execution outcomes as text, listing every rule that did not execute with its reason."""
    lines = [_execution_counts(executions)]
    lines.extend(
        f"[{x.status.value.upper():11}] {x.rule_id}: {x.detail}"
        for x in executions
        if x.status != ExecutionStatus.EXECUTED
    )
    return "\n".join(lines)


def text_needs_executions(report: RunReport) -> bool:
    """Whether text output must append execution outcomes.

    Rules skipped only because an optional input (shapes, OWL profile) was not supplied are the
    unchanged default and stay silent in text; ignored, unsupported or failed rules are shown.
    """
    return any(
        x.status in BROKEN or (x.status is ExecutionStatus.SKIPPED and x.detail.startswith("ignored"))
        for r in report.files
        for x in r.executions
    )


MARKDOWN_SHOWN = 50
"""How many findings the Markdown summary lists, most severe first; SARIF lists every one."""
MARKDOWN_BROKEN_SHOWN = 20
"""How many rule runs without a verdict the summary lists; every one is also on stderr (TOOL001) and in SARIF."""
MARKDOWN_MAX_BYTES = 512 * 1024
"""The most UTF-8 bytes a summary takes, half of GitHub's 1 MiB per step summary.  The caps on the lists and
the fields keep it there even when every character takes its longest escape (``\\U000e0001``, 10 bytes): a test
renders that case.  Nothing is cut at run time, so no cut can fall inside a code span."""
_QUOTE_LIMITS = {"rule": 40, "path": 200, "focus": 200, "message": 300, "detail": 300}
"""How many characters of each quoted field the summary keeps before ``...``."""
_SEVERITY_LABELS = {s: f"**{s}**" for s in SEVERITY_ORDER}
"""How the summary writes a severity: from this table only, so an unknown one raises ``KeyError``, as in SARIF."""
_SEVERITY_RANK = {s: rank for rank, s in enumerate(SEVERITY_ORDER)}
_INVISIBLE = frozenset({"Cc", "Cf", "Cs", "Zl", "Zp"})
"""The Unicode categories a code span shows as escapes: controls (line breaks included), format characters
(bidi controls, zero-width and tag characters), lone surrogates, and the line and paragraph separators."""
_IGNORABLE = frozenset(
    chr(code)
    for first, last in (
        (0x034F, 0x034F),  # combining grapheme joiner
        (0x115F, 0x1160),  # Hangul fillers
        (0x17B4, 0x17B5),  # Khmer inherent vowels
        (0x180B, 0x180F),  # Mongolian free variation selectors
        (0x2065, 0x2065),  # unassigned, among the invisible operators
        (0x3164, 0x3164),  # Hangul filler
        (0xFE00, 0xFE0F),  # variation selectors
        (0xFFA0, 0xFFA0),  # halfwidth Hangul filler
        (0xFFF0, 0xFFF8),  # unassigned, before the specials
        (0xE0000, 0xE0FFF),  # tags, variation selectors supplement and the unassigned rest of the block
    )
    for code in range(first, last + 1)
)
"""The default-ignorable characters (Unicode's ``Default_Ignorable_Code_Point``) those categories miss, which a
renderer draws as nothing: a run of variation selectors can carry a hidden text as tag characters can, so they
are shown as escapes too.  The unassigned ones (``Cn``) are drawn as nothing as well; they are written out as
ranges, so the set does not depend on the Unicode database Python ships.  The plane-14 range holds the tag
characters too."""
_BACKTICK_RUN = re.compile(r"`+")


def _visible(text: str) -> str:
    """``text`` with each invisible character written as its Python escape: ``\\n``, ``\\x00``, ``\\u202e``, and
    ``\\U000e0001`` above U+FFFF, where a ``\\u`` followed by five digits would be ambiguous.

    So no code span holds a line break, a bidi control, a hidden tag character, variation selector or other
    default-ignorable character, or a lone surrogate, and a summary always encodes as UTF-8.  ``ascii`` spells
    the escape: no invisible character is a quote or a backslash.
    """
    return "".join(ascii(c)[1:-1] if c in _IGNORABLE or unicodedata.category(c) in _INVISIBLE else c for c in text)


def markdown_code(text: str, limit: int) -> str:
    """``text`` as a CommonMark code span that shows it literally, cut to ``limit`` characters and ``...``.

    Nothing inside a code span is parsed: no emphasis, link, image, HTML, entity, autolink or ``@`` mention.
    The order of the steps matters.  The text is masked, then cut (:func:`~ontolint.redaction.clip`), before its
    invisible characters are escaped, because an escape adds letters that would hide a scheme from the mask.  The
    escaped text is masked again as a rendered report is (:func:`~ontolint.redaction.redact_rendered`): an escape
    before ``://`` makes a scheme of its own (``\\x00://``), and the span must hold what the CLI writes after its
    own mask.  The fence is one backtick longer than the longest run of them inside, and a space on each side
    keeps a leading or trailing backtick or space, since CommonMark strips one space from each side.  It strips
    none from a text of spaces only, which is not padded; an empty text is shown as one space.
    """
    content = redact_rendered(_visible(clip(text, limit, "...")))
    fence = "`" * (max(map(len, _BACKTICK_RUN.findall(content)), default=0) + 1)
    if content.strip(" "):
        return f"{fence} {content} {fence}"
    return f"{fence}{content or ' '}{fence}"


def _markdown_verdict(report: RunReport, exit_status: int) -> str:
    """Why the run exits as it does; the rule runs behind exit 2 are listed below the counts."""
    if exit_status == 0:
        return "**Passed** (exit 0)."
    if exit_status == 1:
        stale = ", or the baseline has stale entries (`--fail-on-stale-baseline`)" if report.stale_baseline else ""
        return f"**Failed** (exit 1): a finding reached the `--fail-on` threshold{stale}."
    if exit_status == TOOL_FAILURE_EXIT:
        broken = f": {len(report.broken)} rule run(s) did not deliver a verdict" if report.broken else ""
        return f"**Failed** (exit 2){broken}."
    return f"Exit status {exit_status}."


def _markdown_counts(report: RunReport) -> str:
    """The table of findings per severity; with a baseline, the new findings and the baselined ones."""
    new = Counter(f.severity for f in report.findings)
    if report.baselined is None:
        rows = [f"| {s} | {new[s]} |" for s in SEVERITY_ORDER]
        return "\n".join(["| Severity | Findings |", "| --- | ---: |", *rows, f"| total | {len(report.findings)} |"])
    accepted = [f for file in report.baselined for f in file]
    old = Counter(f.severity for f in accepted)
    rows = [f"| {s} | {new[s]} | {old[s]} |" for s in SEVERITY_ORDER]
    total = f"| total | {len(report.findings)} | {len(accepted)} |"
    return "\n".join(["| Severity | New | Baselined |", "| --- | ---: | ---: |", *rows, total])


def _markdown_broken(report: RunReport) -> list[str]:
    """The first :data:`MARKDOWN_BROKEN_SHOWN` rule runs that delivered no verdict, the cause of exit 2."""
    broken = report.broken
    if not broken:
        return []
    items = [
        f"- {markdown_code(x.rule_id, _QUOTE_LIMITS['rule'])} {x.status.value} for "
        f"{markdown_code(path, _QUOTE_LIMITS['path'])}: {markdown_code(x.detail, _QUOTE_LIMITS['detail'])}"
        for path, x in broken[:MARKDOWN_BROKEN_SHOWN]
    ]
    blocks = ["### Rules that delivered no verdict", "\n".join(items)]
    if len(broken) > MARKDOWN_BROKEN_SHOWN:
        blocks.append(f"{len(broken) - MARKDOWN_BROKEN_SHOWN} more not shown.")
    return blocks


def _markdown_finding(file: FileReport, f: Finding, several: bool) -> str:
    """One finding's list item; its file is named when the run has several or the finding is an import's."""
    where = f" in {markdown_code(file.path_of(f), _QUOTE_LIMITS['path'])}" if several or f in file.origins else ""
    return (
        f"- {_SEVERITY_LABELS[f.severity]} {markdown_code(f.rule, _QUOTE_LIMITS['rule'])} "
        f"{markdown_code(f.focus, _QUOTE_LIMITS['focus'])}{where}: {markdown_code(f.message, _QUOTE_LIMITS['message'])}"
    )


def _markdown_findings(report: RunReport) -> list[str]:
    """The first :data:`MARKDOWN_SHOWN` findings, most severe first, then in file and report order."""
    new = "" if report.baselined is None else "new "
    # A stable sort: report order puts the SHACL and ROBOT findings last, whatever their severity.
    entries = sorted(
        ((file, f) for file in report.files for f in file.findings), key=lambda entry: _SEVERITY_RANK[entry[1].severity]
    )
    if not entries:
        return ["### Findings", f"No {new}findings."]
    lead = (
        f"All {len(entries)} {new}finding(s), most severe first."
        if len(entries) <= MARKDOWN_SHOWN
        else f"The first {MARKDOWN_SHOWN} of {len(entries)} {new}finding(s), most severe first."
    )
    pointer = f"The SARIF report (`--format sarif`) lists every {new}finding, with its source location where known."
    several = len(report.files) > 1
    items = [_markdown_finding(file, f, several) for file, f in entries[:MARKDOWN_SHOWN]]
    return ["### Findings", f"{lead} {pointer}", "\n".join(items)]


def render_markdown(report: RunReport, exit_status: int | None = None) -> str:
    """Render ``report`` as a GitHub-flavoured Markdown summary of the run, for a pull request.

    It shows the verdict when ``exit_status`` is given, the findings per severity (new and baselined when a
    baseline was read), the rule execution counts, the rule runs that delivered no verdict, the first findings,
    most severe first, with a pointer to SARIF, and the stale-baseline note.  Every text the report supplies (rule
    ids, foci, messages, paths, details) is shown literally in a code span (:func:`markdown_code`) and never in
    a table, whose cells GitHub splits at ``|`` even inside one; everything else is fixed text.  The summary is
    deterministic, a fixed point of :func:`~ontolint.redaction.redact_rendered`, and at most
    :data:`MARKDOWN_MAX_BYTES` long.  Its layout is for people, not a parsing contract.
    """
    blocks = [f"## ontolint {package_version()}"]
    if exit_status is not None:
        blocks.append(_markdown_verdict(report, exit_status))
    blocks += [_markdown_counts(report), _execution_counts(_all_executions(report))]
    blocks += [*_markdown_broken(report), *_markdown_findings(report)]
    if report.stale_baseline:
        blocks.append(stale_baseline_message(len(report.stale_baseline)))
    # A blank line between blocks: a line just after a list would continue its last item.
    return "\n\n".join(blocks)


def render_report(report: RunReport, output_format: str, exit_status: int | None = None) -> str:
    """Render ``report`` in ``text`` (default), ``json``, ``sarif`` or ``markdown`` format."""
    if output_format == "json":
        return render_json(report)
    if output_format == "sarif":
        return render_sarif(report, exit_status)
    if output_format == "markdown":
        return render_markdown(report, exit_status)
    text = render_text(report)
    if text_needs_executions(report):
        text += "\n" + "\n".join(
            f"{r.path}: {render_executions(r.executions)}" if len(report.files) > 1 else render_executions(r.executions)
            for r in report.files
        )
    if report.stale_baseline:
        text += "\n" + stale_baseline_message(len(report.stale_baseline))
    return text


def exit_code(findings: Sequence[Finding], fail_on: str) -> int:
    """Return 1 when any finding reaches the ``fail_on`` severity threshold, otherwise 0."""
    threshold = FAIL_THRESHOLDS[fail_on]
    return int(any(SEVERITY_ORDER.index(x.severity) <= threshold for x in findings))


def run_exit_code(report: RunReport, fail_on: str) -> int:
    """Exit status: 2 when a requested rule failed or is unsupported, else ``exit_code`` over all findings."""
    return TOOL_FAILURE_EXIT if report.broken else exit_code(report.findings, fail_on)
