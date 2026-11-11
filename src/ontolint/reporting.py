"""Report rendering, fingerprints, and exit-code gating for lint findings.

A run produces one :class:`FileReport` per input file.  JSON and SARIF always carry the
per-rule execution status so a skipped, unsupported or failed rule can never be mistaken
for a clean pass.  SARIF results carry a source region when the loader could locate the
finding's focus (:mod:`ontolint.source_locations`); other formats do not use locations.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ._version import package_version
from .models import ExecutionStatus, Finding, RuleExecution, RuleSpec, plain_evidence
from .modules import module_summary
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


# gremlin: pardon[equivalent] nothing mutates an origin; frozen only guards against it
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


def render_executions(executions: Sequence[RuleExecution]) -> str:
    """Render rule execution outcomes as text, listing every rule that did not execute with its reason."""
    summary = ", ".join(f"{count} {status}" for status, count in summarise_executions(executions).items())
    lines = [f"Rule execution: {summary}"]
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


def render_report(report: RunReport, output_format: str, exit_status: int | None = None) -> str:
    """Render ``report`` in ``text`` (default), ``json`` or ``sarif`` format."""
    if output_format == "json":
        return render_json(report)
    if output_format == "sarif":
        return render_sarif(report, exit_status)
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
