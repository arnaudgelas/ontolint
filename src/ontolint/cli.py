"""Command-line interface: argument parsing, orchestration, and report output.

Exit codes: ``0`` clean, ``1`` findings reach ``--fail-on``, ``2`` tool failure.  A tool failure is
bad input/configuration/selectors, or a requested rule that failed or is unsupported (for example
``--owl-profile`` without Docker): the report is still written, but the run cannot pass.
Rules skipped for an optional input that was not supplied, or by an ignore, never affect the code.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Sequence
from contextvars import ContextVar
from dataclasses import dataclass, replace
from pathlib import Path

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, SH

from . import engine
from ._version import package_version
from .catalogue import planned_rows
from .imports import CATALOG_NAME, Catalog, index_directory, load_closure, read_catalog
from .loader import InputRejected, LoadedGraph, Module, ParseFailure, load_graph, source_index
from .models import ExecutionStatus, Finding, RuleBackend, RuleExecution
from .paths import InputFile, resolve_inputs
from .policy import MAX_PARSE_SECONDS, Policy, PolicyVersionError
from .profiles import PROFILES, Profile
from .reporting import FileReport, Location, Origin, RunReport, fingerprint, render_report, run_exit_code
from .rule_info import UnknownRuleError, explain_rule, render_explanation, render_rule_list, rule_rows
from .rules.registry import RuleRegistry, UnknownSelectorError, default_registry
from .rules.runtime import RuleContext
from .rules.support import local_name
from .selection import Selection, SelectorSyntaxError, resolve_selection, split_selectors, unknown_selector_help

FORMATS = ["text", "json", "sarif"]


def _positive_int(text: str) -> int:
    """argparse type for the loader limits: an integer of at least 1."""
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {text!r}") from None
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be a positive integer (at least 1), got {value}")
    return value


def _positive_seconds(text: str) -> float:
    """argparse type for ``--max-parse-seconds``: a finite number above 0 and at most one day."""
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"must be a positive number of seconds, got {text!r}") from None
    if not math.isfinite(value) or not 0 < value <= MAX_PARSE_SECONDS:
        raise argparse.ArgumentTypeError(f"must be a number of seconds above 0 and at most {MAX_PARSE_SECONDS:g}")
    return value


def build_parser() -> argparse.ArgumentParser:
    """Create the ``ontolint`` argument parser."""
    ap = argparse.ArgumentParser(description="Ontology anti-pattern linter. No automatic network/import access.")
    ap.add_argument(
        "ontology",
        nargs="*",
        help="Ontology RDF file(s); each is linted independently. Expand globs in your shell; directories are rejected",
    )
    ap.add_argument("--shapes", help="Optional SHACL shapes graph (requires pyshacl)")
    ap.add_argument(
        "--follow-imports",
        action="store_true",
        help=f"Load the owl:imports closure from local files, through {CATALOG_NAME} next to each input if present",
    )
    ap.add_argument("--catalog", help="OASIS XML catalog mapping import IRIs to local files (implies --follow-imports)")
    ap.add_argument(
        "--import-dir",
        action="append",
        default=[],
        help="Folder of local copies of imported ontologies, matched by their ontology or version IRI; repeatable",
    )
    ap.add_argument(
        "--import-root",
        help="Directory imported files must stay in (default: the enclosing git repository of the catalog or input)",
    )
    ap.add_argument("--base", help="Only lint declared terms in this namespace")
    ap.add_argument("--config", help="Optional JSON policy with ignored_rules, severity_overrides and thresholds")
    ap.add_argument("--baseline", help="JSON of fingerprints to exclude from displayed and gating findings")
    ap.add_argument("--write-baseline", help="Write full set of fingerprints for future differential linting")
    ap.add_argument(
        "--fail-on-stale-baseline",
        action="store_true",
        help="Exit 1 when a --baseline fingerprint matches no finding of the run (the baseline needs regenerating)",
    )
    ap.add_argument("--language", action="append", default=[], help="Required label language; repeatable")
    ap.add_argument("--depth-limit", type=int)
    ap.add_argument("--inheritance-limit", type=int)
    ap.add_argument("--soup-limit", type=int)
    ap.add_argument("--subclass-limit", type=int, help="CLS011: most direct subclasses a class may have (default 50)")
    ap.add_argument(
        "--max-input-bytes", type=_positive_int, help="Refuse input files larger than this (default 64 MiB)"
    )
    ap.add_argument(
        "--max-triples", type=_positive_int, help="Refuse inputs with more triples than this (default 5000000)"
    )
    ap.add_argument(
        "--max-parse-seconds",
        type=_positive_seconds,
        help="Abort parsing an input that takes longer than this wall-clock time (default: no limit); "
        "runs the parse in a worker process",
    )
    ap.add_argument("--owl-profile", choices=("EL", "QL", "RL", "DL", "Full"))
    ap.add_argument("--robot-image", default="ontolint-robot:1.9.11")
    ap.add_argument("--robot-timeout", type=int, default=120)
    ap.add_argument("--format", choices=FORMATS, default="text")
    ap.add_argument("--output", help="Output file (default stdout)")
    ap.add_argument("--fail-on", choices=["error", "warning", "info", "never"], default=None)
    _add_selection_arguments(ap)
    return ap


def _add_selection_arguments(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--profile", choices=sorted(PROFILES), help="Named rule profile; see the README for each profile")
    ap.add_argument(
        "--select", action="append", default=[], help="Rule IDs or families to run; comma-separated, repeatable"
    )
    ap.add_argument(
        "--ignore", action="append", default=[], help="Rule IDs or families to skip; comma-separated, repeatable"
    )
    ap.add_argument("--list-rules", action="store_true", help="List implemented and proposed rules, then exit")
    ap.add_argument("--explain", metavar="RULE", help="Explain one rule, then exit")
    ap.add_argument("--version", action="store_true", help="Print the version, then exit")


def _policy(args: argparse.Namespace, config: Policy, ignored: frozenset[str]) -> Policy:
    """Merge CLI options over the policy file; explicit CLI options take precedence."""
    return replace(
        config,
        base=args.base if args.base is not None else config.base,
        languages=tuple(x.lower() for x in args.language) if args.language else config.languages,
        depth_limit=args.depth_limit if args.depth_limit is not None else config.depth_limit,
        inheritance_limit=args.inheritance_limit if args.inheritance_limit is not None else config.inheritance_limit,
        soup_limit=args.soup_limit if args.soup_limit is not None else config.soup_limit,
        subclass_limit=args.subclass_limit if args.subclass_limit is not None else config.subclass_limit,
        max_input_bytes=args.max_input_bytes if args.max_input_bytes is not None else config.max_input_bytes,
        max_triples=args.max_triples if args.max_triples is not None else config.max_triples,
        max_parse_seconds=args.max_parse_seconds if args.max_parse_seconds is not None else config.max_parse_seconds,
        ignored_rules=ignored,
    )


@dataclass(frozen=True)
class RunPlan:
    """Everything shared by every file of one invocation."""

    policy: Policy
    selection: Selection
    overrides: dict[str, str]
    shapes: Graph | None
    registry: RuleRegistry
    shacl_background: Graph | None = None


_SHAPE_TYPES = (SH.NodeShape, SH.PropertyShape)


def _shape_count(graph: Graph) -> int:
    """How many SHACL shapes ``graph`` holds: typed node or property shapes, or nodes with an ``sh:path``."""
    typed = {s for type_ in _SHAPE_TYPES for s in graph.subjects(RDF.type, type_)}
    return len(typed | set(graph.subjects(SH.path, None)))


def _shapes_hint(item: InputFile, graph: Graph, ctx: RuleContext) -> None:
    """Say once when the linted file is mostly SHACL shapes: ontology rules were not written for it."""
    shapes = _shape_count(graph)
    terms = len(ctx.context.classes | ctx.context.properties | ctx.context.concepts)
    if shapes and shapes > terms:
        print(
            f"TOOL003: note: {item.display} looks like a SHACL shapes graph ({shapes} shapes, {terms} declared "
            "terms); ontology rules may not fit it. To validate data against it, pass it with --shapes.",
            file=sys.stderr,
        )


DEFINITION_HINT_MINIMUM = 10
"""LEX002 findings a file needs before ontolint looks for an unknown definition predicate (TOOL005)."""


def _definition_hint(item: InputFile, graph: Graph, ctx: RuleContext, findings: Sequence[Finding]) -> None:
    """Say once when most LEX002 terms carry an unrecognised predicate named like a definition."""
    undefined = [URIRef(f.focus) for f in findings if f.rule == "LEX002" and f.focus.startswith(("http", "urn"))]
    if len(undefined) < DEFINITION_HINT_MINIMUM:
        return
    counts: dict[URIRef, int] = {}
    for term in undefined:
        for predicate in {p for p, o in graph.predicate_objects(term) if isinstance(o, Literal)}:
            if isinstance(predicate, URIRef) and "definition" in local_name(predicate).casefold():
                counts[predicate] = counts.get(predicate, 0) + 1
    known = set(ctx.descriptions)
    candidates = sorted((n, str(p)) for p, n in counts.items() if p not in known and n * 2 >= len(undefined))
    if candidates:
        count, suggested = candidates[-1]
        print(
            f"TOOL005: note: {count} of the {len(undefined)} terms LEX002 reports in {item.display} carry "
            f"<{suggested}>, which looks like a definition; add it to extra_definition_predicates in the policy "
            "if it is one.",
            file=sys.stderr,
        )


def _lint_file(item: InputFile, loaded: LoadedGraph, plan: RunPlan, args: argparse.Namespace) -> FileReport:
    """Lint one parsed file and record an execution outcome for every selected rule."""
    graph = loaded.graph
    bases = {module.directory for module in loaded.modules} | {item.path.resolve().parent.as_uri().rstrip("/") + "/"}
    policy = replace(
        plan.policy,
        resolved_imports=loaded.resolved_imports,
        imported_ontologies=loaded.imported_ontologies,
        document_bases=tuple(sorted(bases)),
        root_terms=loaded.modules[0].declared if loaded.modules else frozenset(),
    )
    ctx = engine.build_context(graph, plan.shapes, policy)
    ctx.shacl_background = plan.shacl_background
    _shapes_hint(item, graph, ctx)
    if ctx.context.ownership.base_selected_nothing:
        print(
            f"TOOL002: warning: --base {plan.policy.base!r} selects none of the terms declared in {item.display}; "
            "term-level rules have nothing to check (is the base a prefix of the term IRIs?)",
            file=sys.stderr,
        )
    robot = (
        engine.RobotRequest(item.path, args.owl_profile, args.robot_image, args.robot_timeout)
        if args.owl_profile
        else None
    )
    executions: list[RuleExecution] = []
    findings: tuple[Finding, ...] = ()
    run_ids = [s.rule_id for s in plan.selection.run]
    if run_ids:
        result = engine.execute(ctx, run_ids, registry=plan.registry, robot=robot)
        findings, executions = result.findings, list(result.executions)
    executions += [
        RuleExecution(s.rule_id, ExecutionStatus.SKIPPED, "ignored by --ignore or profile")
        for s in plan.selection.ignored
    ]
    findings = tuple(replace(f, severity=plan.overrides.get(f.rule, f.severity)) for f in _legacy_order(findings, plan))
    _definition_hint(item, graph, ctx, findings)
    # Only SARIF renders regions, and the index is computed on first use, so other formats skip it.
    sarif = args.format == "sarif"
    if loaded.modules:
        origins, locations, problem = _module_origins(loaded.modules, graph, findings, sarif)
        executions_sorted = tuple(sorted(executions, key=lambda x: x.rule_id))
        return FileReport(item.display, item.uri, findings, executions_sorted, locations, problem, origins)
    return FileReport(
        item.display,
        item.uri,
        findings,
        tuple(sorted(executions, key=lambda x: x.rule_id)),
        loaded.source_index.for_findings(graph, findings) if sarif else {},
        loaded.source_index.problem if sarif else None,
    )


def _module_origins(
    modules: Sequence[Module], graph: Graph, findings: Sequence[Finding], sarif: bool
) -> tuple[dict[Finding, Origin], dict[Finding, Location], str | None]:
    """Attribute each finding of an import closure to the file it belongs to (``modules[0]`` is the root).

    A finding belongs to the first file that declares its focus (gives it an ``rdf:type``), else to the
    first file whose text mentions it, else to the root.  Its region, for SARIF, comes from that file.
    """
    located = [module.source_index.for_findings(graph, findings) for module in modules]
    origins: dict[Finding, Origin] = {}
    locations: dict[Finding, Location] = {}
    for finding in findings:
        owner = next((i for i, module in enumerate(modules) if finding.focus in module.declared), None)
        if owner is None:
            owner = next((i for i, found in enumerate(located) if finding in found), 0)
        if owner:
            origins[finding] = Origin(modules[owner].display, modules[owner].uri)
        if sarif and finding in located[owner]:
            locations[finding] = located[owner][finding]
    problems = [f"{m.display}: {m.source_index.problem}" for m in modules if sarif and m.source_index.problem]
    return origins, locations, "; ".join(problems) or None


def _legacy_order(findings: Sequence[Finding], plan: RunPlan) -> list[Finding]:
    """Graph rules first (already sorted), then SHACL, then ROBOT: the order reports have always used."""
    rank = {RuleBackend.RDFLIB: 0, RuleBackend.PYSHACL: 1, RuleBackend.ROBOT_DOCKER: 2}
    backends = {s.rule_id: s.backend for s in plan.registry.all()}
    return sorted(findings, key=lambda f: rank.get(backends.get(f.rule, RuleBackend.RDFLIB), 0))


def _file_fingerprints(report: FileReport, multi: bool) -> set[str]:
    return {fingerprint(f, report.path if multi else None) for f in report.findings}


def _apply_baselines(
    files: list[FileReport], args: argparse.Namespace
) -> tuple[list[FileReport], tuple[str, ...] | None]:
    """Write and/or apply the baseline; also return its fingerprints that matched no finding (OPS003)."""
    multi = len(files) > 1
    if args.write_baseline:
        everything = sorted(set().union(*(_file_fingerprints(r, multi) for r in files)))
        Path(args.write_baseline).write_text(
            json.dumps({"fingerprints": everything}, indent=2) + "\n", encoding="utf-8"
        )
    if args.baseline:
        prior = set(json.loads(Path(args.baseline).read_text(encoding="utf-8")).get("fingerprints", []))
        current = set().union(*(_file_fingerprints(r, multi) for r in files))
        files = [
            replace(r, findings=tuple(f for f in r.findings if fingerprint(f, r.path if multi else None) not in prior))
            for r in files
        ]
        return files, tuple(sorted(prior - current))
    return files, None


_LOADER_POLICY: ContextVar[Policy | None] = ContextVar("loader_policy", default=None)


# gremlin: pardon[equivalent] nothing mutates the options; frozen only guards against it
@dataclass(frozen=True)
class ImportOptions:
    """How to follow ``owl:imports``: with one explicit catalog, or with the one found next to each input."""

    catalog: Catalog | None = None
    import_root: Path | None = None
    import_dirs: tuple[Catalog, ...] = ()


def _import_options(args: argparse.Namespace, policy: Policy) -> ImportOptions | None:
    """How to follow owl:imports for this run, or ``None`` when no import option was given."""
    if not (args.catalog or args.follow_imports or args.import_root or args.import_dir):
        return None
    catalog = read_catalog(Path(args.catalog), policy.max_input_bytes) if args.catalog else None
    return ImportOptions(catalog, _import_root(args), _import_dirs(args, policy))


def _import_dirs(args: argparse.Namespace, policy: Policy) -> tuple[Catalog, ...]:
    return tuple(index_directory(Path(directory), policy) for directory in args.import_dir)


def _import_root(args: argparse.Namespace) -> Path | None:
    return Path(args.import_root).resolve() if args.import_root else None


def _closure(item: InputFile, policy: Policy, options: ImportOptions) -> LoadedGraph:
    graph = load_graph(item, policy)
    return _closure_of(item, LoadedGraph(graph, source_index(graph)), policy, options)


def _closure_of(item: InputFile, root: LoadedGraph, policy: Policy, options: ImportOptions) -> LoadedGraph:
    catalog = options.catalog
    if catalog is None and (found := item.path.parent / CATALOG_NAME).is_file():
        catalog = read_catalog(found, policy.max_input_bytes)
    closure = load_closure(
        root, item.path, policy, catalog, item, import_root=options.import_root, import_dirs=options.import_dirs
    )
    for iri, path in sorted(closure.missing.items()):
        print(
            f"TOOL004: note: the catalog maps owl:imports {iri} to {path}, which does not exist; "
            "the import is not followed (SEC007).",
            file=sys.stderr,
        )
    return closure.loaded


def _shapes_background(item: InputFile, shapes: Graph, policy: Policy, options: ImportOptions) -> Graph | None:
    """The ontology a shapes file imports, without the shapes: SHACL validates the data against it too.

    Shapes that check the class of a vocabulary individual need the ontology that types it; without it
    valid data reports false violations.  ``None`` when the shapes import nothing that resolves.
    """
    closure = _closure_of(item, LoadedGraph(shapes, source_index(shapes)), policy, options)
    background = closure.graph - shapes
    return background if len(background) else None


def _parse_inputs(inputs: list[InputFile], imports: ImportOptions | None = None) -> tuple[list[LoadedGraph], list[str]]:
    """Parse every input safely (no network, bounded size); return the graphs and one message per failure.

    The limits come from the policy of the current run (:data:`_LOADER_POLICY`, set by :func:`_lint`).
    With ``imports`` each input is loaded with its local ``owl:imports`` closure (:mod:`ontolint.imports`).
    """
    policy = _LOADER_POLICY.get() or Policy()
    graphs: list[LoadedGraph] = []
    errors: list[str] = []
    for item in inputs:
        try:
            if imports is not None:
                graphs.append(_closure(item, policy, imports))
                continue
            graph = load_graph(item, policy)
            graphs.append(LoadedGraph(graph, source_index(graph)))
        except InputRejected as exc:
            where = f" for {item.display}" if len(inputs) > 1 and item.display not in exc.message else ""
            errors.append(f"{exc.rule_id}: {exc.message}{where}")
        except Exception as exc:  # noqa: BLE001 -- any other failure (unreadable file ...) is a reportable input error.
            errors.append(_parse_error(exc, item.display if len(inputs) > 1 else None))
    return graphs, errors


def _parse_error(exc: Exception, display: str | None) -> str:
    """The ``INPUT001`` line for a parse failure; ``display`` names the file when several were given."""
    where = f" for {display}" if display else ""
    name, detail = (exc.cause_type, exc.detail) if isinstance(exc, ParseFailure) else (type(exc).__name__, str(exc))
    return f"INPUT001: RDF input parsing failed{where}: {name}: {detail}"


def _info_command(args: argparse.Namespace) -> int | None:
    """Handle --version, --list-rules and --explain; ``None`` means a normal lint run."""
    registry = default_registry()
    if args.version:
        print(f"ontolint {package_version()}")
    elif args.list_rules:
        print(render_rule_list(rule_rows(registry), "json" if args.format != "text" else "text"))
    elif args.explain:
        try:
            print(render_explanation(explain_rule(args.explain, registry), "json" if args.format != "text" else "text"))
        except UnknownRuleError:
            print(f"TOOL001: unknown rule {args.explain!r}; use --list-rules to see valid identifiers", file=sys.stderr)
            return 2
    else:
        return None
    return 0


def _profile(args: argparse.Namespace) -> Profile | None:
    return PROFILES[args.profile] if args.profile else None


def _plan(args: argparse.Namespace, config: Policy, shapes: Graph | None, registry: RuleRegistry) -> RunPlan:
    profile = _profile(args)
    selection = resolve_selection(registry, profile, split_selectors(args.select), split_selectors(args.ignore))
    overrides = {**dict(profile.severity_overrides if profile else ()), **config.severity_mapping}
    return RunPlan(_policy(args, config, config.ignored_rules), selection, overrides, shapes, registry)


class UnknownPolicyRuleError(ValueError):
    """The policy file names a rule that does not exist, so its ignore or override would do nothing."""


def _check_policy_rules(config: Policy, registry: RuleRegistry) -> None:
    """Reject unknown rule IDs in ``ignored_rules`` and ``severity_overrides``, as ``--ignore`` does (OPS009).

    A typo there would otherwise be silent: the rule it meant to silence keeps running, and an
    override changes nothing.  Proposed (catalogue-only) rules are rejected too, with a hint, because
    they never run; IDs are matched exactly, like the engine does.
    """
    named = {
        "ignored_rules": sorted(config.ignored_rules),
        "severity_overrides": [r for r, _ in config.severity_overrides],
    }
    unknown = {key: [rule for rule in rules if rule not in registry] for key, rules in named.items()}
    problems = [f"{key}: {', '.join(rules)}" for key, rules in unknown.items() if rules]
    if not problems:
        return
    message = f"unknown rule identifier(s) in {'; '.join(problems)}"
    proposed = frozenset(row.rule_id for row in planned_rows())
    planned = sorted({rule for rules in unknown.values() for rule in rules} & proposed)
    if planned:
        message += f"; {', '.join(planned)} exist in the catalogue as proposed rules and are not implemented"
    raise UnknownPolicyRuleError(message + "; use --list-rules to see valid identifiers")


def _emit(output: str, args: argparse.Namespace) -> None:
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    else:
        print(output)


def _lint(args: argparse.Namespace, stage: list[str]) -> RunReport | int:
    """Run the whole lint; ``stage`` tracks progress for error messages. Returns a report or an exit code."""
    registry = default_registry()
    config = Policy.from_mapping(json.loads(Path(args.config).read_text(encoding="utf-8")) if args.config else {})
    _check_policy_rules(config, registry)
    limits = _policy(args, config, config.ignored_rules)
    try:  # read catalogs and import dirs before parsing: a broken one is a configuration error
        imports = _import_options(args, limits)
    except InputRejected as exc:
        print(f"{exc.rule_id}: {exc.message}", file=sys.stderr)
        return 2
    stage[0] = "RDF input parsing"
    inputs = resolve_inputs(args.ontology, Path.cwd())
    _LOADER_POLICY.set(limits)
    graphs, errors = _parse_inputs(inputs, imports)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2
    shapes: Graph | None = None
    background: Graph | None = None
    if args.shapes:
        try:
            shapes_item = resolve_inputs([args.shapes], Path.cwd())[0]
            shapes = load_graph(shapes_item, limits)
            if imports is not None:
                background = _shapes_background(shapes_item, shapes, limits, imports)
        except InputRejected as exc:
            print(f"{exc.rule_id}: {exc.message}", file=sys.stderr)
            return 2
        except ParseFailure as exc:
            print(_parse_error(exc, None), file=sys.stderr)
            return 2
    stage[0] = "lint execution"
    plan = replace(_plan(args, config, shapes, registry), shacl_background=background)
    files = [_lint_file(item, graph, plan, args) for item, graph in zip(inputs, graphs, strict=True)]
    files, stale = _apply_baselines(files, args)
    return RunReport(tuple(files), plan.selection.run + plan.selection.ignored, plan.overrides, stale)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the linter CLI and return its process exit code (0 clean, 1 gated findings, 2 tool failure)."""
    parser = build_parser()
    args = parser.parse_args(argv)
    info = _info_command(args)
    if info is not None:
        return info
    if not args.ontology:
        parser.error("at least one ONTOLOGY path is required")
    if args.fail_on_stale_baseline and not args.baseline:
        parser.error("--fail-on-stale-baseline requires --baseline")
    stage = ["configuration"]
    try:
        outcome = _lint(args, stage)
    except (UnknownSelectorError, SelectorSyntaxError) as exc:
        proposed = frozenset(row.rule_id for row in planned_rows())
        message = unknown_selector_help(exc, proposed) if isinstance(exc, UnknownSelectorError) else str(exc)
        print(f"TOOL001: configuration failed: {type(exc).__name__}: {message}", file=sys.stderr)
        return 2
    except (PolicyVersionError, UnknownPolicyRuleError) as exc:
        print(f"GOV020: policy file rejected: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        # Parser/configuration errors are tool failures, not SHACL conformance results.
        code = "INPUT001" if stage[0] == "RDF input parsing" else "TOOL001"
        print(f"{code}: {stage[0]} failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if isinstance(outcome, int):
        return outcome
    return _finish(outcome, args)


def _finish(report: RunReport, args: argparse.Namespace) -> int:
    profile = _profile(args)
    fail_on = args.fail_on or (profile.fail_on if profile else "error")
    code = run_exit_code(report, fail_on)
    if args.fail_on_stale_baseline and report.stale_baseline and code == 0:
        code = 1
    _emit(render_report(report, args.format, code), args)
    for path, x in report.broken:
        print(f"TOOL001: rule {x.rule_id} {x.status.value} for {path}: {x.detail}", file=sys.stderr)
    return code
