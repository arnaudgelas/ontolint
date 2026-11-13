"""Command-line interface: argument parsing, orchestration, and report output.

Exit codes: ``0`` clean, ``1`` findings reach ``--fail-on``, ``2`` tool failure.  A tool failure is
bad input/configuration/selectors, or a requested rule that failed or is unsupported (for example
``--owl-profile`` without Docker): the report is still written, but the run cannot pass.
Rules skipped for an optional input that was not supplied, or by an ignore, never affect the code.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import math
import os
import sys
import traceback
from collections.abc import Mapping, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, replace
from functools import partial
from pathlib import Path
from typing import TextIO, cast

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import RDF, SH
from rdflib.term import Node

from . import baseline, engine
from ._version import package_version
from .adapters.robot import robot_convert
from .catalogue import planned_rows
from .datasets import finding_graphs
from .declarations import Place, Shared, shared_identities
from .imports import (
    CATALOG_NAME,
    Catalog,
    default_import_root,
    index_directory,
    inside_root,
    load_closure,
    read_catalog,
)
from .library import load_library
from .loader import InputRejected, LoadedGraph, Module, ParseFailure, load_graph, loaded_graph, source_index
from .models import ExecutionStatus, Finding, PatternLibrary, RuleBackend, RuleExecution
from .modules import MODULE_BY, UnresolvedModulePredicate, finding_modules, resolve_predicate
from .paths import InputFile, resolve_inputs
from .policy import MAX_PARSE_SECONDS, Policy, PolicyVersionError
from .prof import ProfileError, shapes_files
from .profiles import PROFILES, Profile
from .redaction import REDACTED_USERINFO, RedactingStream, redact_rendered, redact_userinfo
from .reporting import TOOL_FAILURE_EXIT, FileReport, Location, Origin, RunReport, render_report, run_exit_code
from .rule_info import UnknownRuleError, explain_rule, render_explanation, render_rule_list, rule_rows
from .rules import measurements
from .rules.duplicate_ids import SET_RULES, finding_key
from .rules.registry import RuleRegistry, UnknownSelectorError, default_registry
from .rules.runtime import RuleContext
from .rules.support import local_name
from .selection import (
    PIPELINE_HELP,
    PipelineSelectorError,
    Selection,
    SelectorSyntaxError,
    check_selectors,
    is_pipeline,
    resolve_selection,
    split_selectors,
    unknown_selector_help,
)

FORMATS = ["text", "json", "sarif", "markdown"]


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
    """argparse type for ``--max-parse-seconds`` and ``--max-validation-seconds``: above 0, at most one day."""
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
        "--shapes-from-profile",
        metavar="PROFILE",
        help="Use as --shapes the SHACL validator a W3C PROF profile names (prof:hasRole role:validator), "
        "found locally through a catalog, --import-dir or a file named after it beside the profile",
    )
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
    ap.add_argument(
        "--pattern-library",
        metavar="DIR",
        help="Lint the input as the index of a pattern library whose member ontologies are the RDF files under "
        "DIR (rules LIB001-LIB003)",
    )
    ap.add_argument("--base", help="Only lint declared terms in this namespace")
    ap.add_argument(
        "--module-annotation",
        metavar="PREDICATE",
        help="Group findings by the module each term names with this annotation (an IRI or a CURIE the file "
        "declares, e.g. opla:isNativeTo)",
    )
    ap.add_argument(
        "--module-by", choices=MODULE_BY, help="Group findings by module: 'namespace' groups them by term namespace"
    )
    ap.add_argument("--config", help="Optional JSON policy with ignored_rules, severity_overrides and thresholds")
    ap.add_argument(
        "--baseline", help="Baseline file (from --write-baseline) whose findings are excluded from display and gating"
    )
    ap.add_argument(
        "--write-baseline", help="Write every finding of the run (version 1 hash and identity) as a baseline file"
    )
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
    ap.add_argument(
        "--max-validation-seconds",
        type=_positive_seconds,
        help="Stop the SHACL validation of an input that takes longer than this wall-clock time (default: no "
        "limit; SHACL001 then fails); runs validation in a worker process",
    )
    ap.add_argument("--owl-profile", choices=("EL", "QL", "RL", "DL", "Full"))
    ap.add_argument(
        "--convert-with-robot",
        action="store_true",
        help="Read OWL Functional, Manchester and OWL/XML inputs and imports by converting each to Turtle "
        "with ROBOT in Docker (--robot-image, no network)",
    )
    ap.add_argument("--robot-image", default="ontolint-robot:1.9.11")
    ap.add_argument("--robot-timeout", type=int, default=120)
    ap.add_argument("--format", choices=FORMATS, default="text")
    ap.add_argument(
        "--measurements",
        action="store_true",
        help="Add each file's measurement vector to the JSON report (files[].measurements: the ratios behind the "
        "METRIC rules and more, as numerators and denominators); requires --format json",
    )
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
    module_annotation, module_by = _module_options(args, config)
    return replace(
        config,
        base=args.base if args.base is not None else config.base,
        module_annotation=module_annotation,
        module_by=module_by,
        languages=tuple(x.lower() for x in args.language) if args.language else config.languages,
        depth_limit=args.depth_limit if args.depth_limit is not None else config.depth_limit,
        inheritance_limit=args.inheritance_limit if args.inheritance_limit is not None else config.inheritance_limit,
        soup_limit=args.soup_limit if args.soup_limit is not None else config.soup_limit,
        subclass_limit=args.subclass_limit if args.subclass_limit is not None else config.subclass_limit,
        max_input_bytes=args.max_input_bytes if args.max_input_bytes is not None else config.max_input_bytes,
        max_triples=args.max_triples if args.max_triples is not None else config.max_triples,
        max_parse_seconds=args.max_parse_seconds if args.max_parse_seconds is not None else config.max_parse_seconds,
        max_validation_seconds=args.max_validation_seconds
        if args.max_validation_seconds is not None
        else config.max_validation_seconds,
        ignored_rules=ignored,
        owl_converter=partial(robot_convert, image=args.robot_image, timeout=args.robot_timeout)
        if args.convert_with_robot
        else None,
    )


def _module_options(args: argparse.Namespace, config: Policy) -> tuple[str | None, str | None]:
    """``(module_annotation, module_by)``: the CLI's choice, when it made one, replaces the policy's."""
    if args.module_annotation is None and args.module_by is None:
        return config.module_annotation, config.module_by
    return args.module_annotation, args.module_by


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
    foci = [f.focus for f in findings if f.rule == "LEX002" and f.focus.startswith(("http", "urn"))]
    if len(foci) < DEFINITION_HINT_MINIMUM:
        return
    masked = {focus for focus in foci if REDACTED_USERINFO in focus}
    undefined = [URIRef(focus) for focus in foci if focus not in masked]
    if masked:  # a masked focus (ontolint.redaction) stands for every term that masks to it
        subjects = {s for s in graph.subjects() if isinstance(s, URIRef)}
        undefined += sorted(s for s in subjects if redact_userinfo(str(s)) in masked)
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


def _lint_file(
    item: InputFile, loaded: LoadedGraph, plan: RunPlan, args: argparse.Namespace, shared: Sequence[Shared] = ()
) -> FileReport:
    """Lint one parsed file and record an execution outcome for every selected rule.

    ``shared`` are the identities the run's documents share that are reported on this file (ONT007, ONT008).
    """
    graph = loaded.graph
    bases = {module.directory for module in loaded.modules} | {item.path.resolve().parent.as_uri().rstrip("/") + "/"}
    policy = replace(
        plan.policy,
        resolved_imports=loaded.resolved_imports,
        imported_ontologies=loaded.imported_ontologies,
        document_bases=tuple(sorted(bases)),
        root_terms=loaded.modules[0].declared if loaded.modules else frozenset(),
        source=loaded.source,
        shared_identities=tuple(found.identity for found in shared),
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
    modules = _file_modules(item, loaded, plan.policy, findings)
    executions_sorted = tuple(sorted(executions, key=lambda x: x.rule_id))
    if loaded.modules:
        origins, locations, problem, owners = _module_origins(loaded.modules, graph, findings, sarif)
        graphs = _closure_graphs(loaded.modules, graph, findings, owners)
    else:
        origins = {}
        locations = loaded.source_index.for_findings(graph, findings) if sarif else {}
        problem = loaded.source_index.problem if sarif else None
        graphs = finding_graphs(graph, loaded.graphs, findings)
    members = _library_origins(plan.policy.library, findings)
    if members:  # a finding about a member ontology belongs to the member's file, not to the index
        origins = {**origins, **members}
        locations = {f: where for f, where in locations.items() if f not in members}
        graphs = {f: names for f, names in graphs.items() if f not in members}
    others = _shared_places((item, loaded), findings, shared, sarif, (origins, locations, graphs)) if shared else {}
    # Taken after the rules ran, so a measurement a METRIC rule read is the value it compared.
    measured = measurements.publish(ctx) if args.measurements else None
    return FileReport(
        item.display,
        item.uri,
        findings,
        executions_sorted,
        locations,
        problem,
        origins,
        modules,
        graphs,
        others,
        measured,
    )


def _shared_places(
    source: tuple[InputFile, LoadedGraph],
    findings: Sequence[Finding],
    shared: Sequence[Shared],
    sarif: bool,
    shown: tuple[dict[Finding, Origin], dict[Finding, Location], dict[Finding, tuple[str, ...]]],
) -> dict[Finding, tuple[tuple[Origin, Location | None], ...]]:
    """Place each ONT007 and ONT008 finding of ``findings`` at the files of its members; return the other files.

    The finding belongs to its first member's file (``origins``, updated in place with ``locations`` and
    ``graphs``) and is located there; for SARIF, every other member's file is a related location.  Its named
    graphs are found like any finding's (:func:`ontolint.datasets.finding_graphs`), in that file: every graph of
    it that describes the IRI (none for a file the closure did not load, which has no index).
    """
    item, loaded = source
    origins, locations, graphs = shown
    indexes = {module.display: module.graphs for module in loaded.modules} or {item.display: loaded.graphs}
    by_key = {finding_key(found.identity): found for found in shared}
    others: dict[Finding, tuple[tuple[Origin, Location | None], ...]] = {}
    for finding in findings:
        found = by_key.get((finding.rule, finding.focus, finding.subject, finding.message))
        if found is None:
            continue
        first, *rest = found.places
        origins.pop(finding, None)
        if first.path != item.display:
            origins[finding] = Origin(first.path, first.uri)
        locations.pop(finding, None)
        graphs.pop(finding, None)
        if (index := indexes.get(first.path)) is not None and (names := finding_graphs(loaded.graph, index, [finding])):
            graphs[finding] = names[finding]
        if sarif and (where := _place_location(first, finding.focus)) is not None:
            locations[finding] = where
        if rest:
            others[finding] = tuple(
                (Origin(place.path, place.uri), _place_location(place, finding.focus) if sarif else None)
                for place in rest
            )
    return others


def _place_location(place: Place, iri: str) -> Location | None:
    """Where ``iri`` first occurs in the file of ``place``, when its syntax gives positions."""
    return place.source_index.locations.get(URIRef(iri)) if place.source_index is not None else None


def _library_origins(library: PatternLibrary | None, findings: Sequence[Finding]) -> dict[Finding, Origin]:
    """With ``--pattern-library``: the member file of each finding whose focus is a member ontology."""
    if library is None:
        return {}
    files = {redact_userinfo(m.ontology): Origin(m.display, m.uri) for m in library.members}
    return {f: files[f.focus] for f in findings if f.focus in files}


def _file_modules(
    item: InputFile, loaded: LoadedGraph, policy: Policy, findings: Sequence[Finding]
) -> dict[Finding, tuple[str, ...]]:
    """The modules inside the file each finding belongs to (``--module-annotation``, ``--module-by``)."""
    if policy.module_by == "namespace":
        return finding_modules(loaded.graph, findings, None)
    if policy.module_annotation is None:
        return {}
    graph = loaded.graph
    # The file's own declarations win over RDFLib's default bindings.
    prefixes = [
        *((p, str(n)) for p, n in graph.namespace_manager.namespaces()),
        *(loaded.source.declared_prefixes or ()),
    ]
    try:
        predicate = resolve_predicate(policy.module_annotation, prefixes)
    except UnresolvedModulePredicate:
        print(
            f"TOOL006: warning: module annotation {policy.module_annotation!r} is not an IRI and {item.display} "
            "declares no such prefix; findings are not grouped by module",
            file=sys.stderr,
        )
        return {}
    if (None, predicate, None) not in graph:
        print(
            f"TOOL006: note: no term in {item.display} carries <{predicate}>; findings are not grouped by module",
            file=sys.stderr,
        )
        return {}
    return finding_modules(graph, findings, predicate)


def _module_origins(
    modules: Sequence[Module], graph: Graph, findings: Sequence[Finding], sarif: bool
) -> tuple[dict[Finding, Origin], dict[Finding, Location], str | None, dict[Finding, int]]:
    """Attribute each finding of an import closure to the file it belongs to (``modules[0]`` is the root).

    A finding belongs to the first file that declares its focus (gives it an ``rdf:type``), else to the
    first file whose text mentions it, else to the root.  Its region, for SARIF, comes from that file.
    Also returns the position in ``modules`` of each finding's file.
    """
    located = [module.source_index.for_findings(graph, findings) for module in modules]
    declared = [frozenset(map(redact_userinfo, module.declared)) for module in modules]  # foci are masked
    origins: dict[Finding, Origin] = {}
    locations: dict[Finding, Location] = {}
    owners: dict[Finding, int] = {}
    for finding in findings:
        owner = next((i for i, names in enumerate(declared) if finding.focus in names), None)
        if owner is None:
            owner = next((i for i, found in enumerate(located) if finding in found), 0)
        owners[finding] = owner
        if owner:
            origins[finding] = Origin(modules[owner].display, modules[owner].uri)
        if sarif and finding in located[owner]:
            locations[finding] = located[owner][finding]
    problems = [f"{m.display}: {m.source_index.problem}" for m in modules if sarif and m.source_index.problem]
    return origins, locations, "; ".join(problems) or None, owners


def _closure_graphs(
    modules: Sequence[Module], graph: Graph, findings: Sequence[Finding], owners: Mapping[Finding, int]
) -> dict[Finding, tuple[str, ...]]:
    """The named graphs of each closure finding, in the file it belongs to (another file's graphs are not its)."""
    owned: dict[int, list[Finding]] = {}
    for finding in findings:
        owned.setdefault(owners[finding], []).append(finding)
    graphs: dict[Finding, tuple[str, ...]] = {}
    for owner, group in owned.items():
        graphs.update(finding_graphs(graph, modules[owner].graphs, group))
    return graphs


def _legacy_order(findings: Sequence[Finding], plan: RunPlan) -> list[Finding]:
    """Graph rules first (already sorted), then SHACL, then ROBOT: the order reports have always used."""
    rank = {RuleBackend.RDFLIB: 0, RuleBackend.PYSHACL: 1, RuleBackend.ROBOT_DOCKER: 2}
    backends = {s.rule_id: s.backend for s in plan.registry.all()}
    return sorted(findings, key=lambda f: rank.get(backends.get(f.rule, RuleBackend.RDFLIB), 0))


def _apply_baselines(
    files: list[FileReport], args: argparse.Namespace
) -> tuple[list[FileReport], tuple[str, ...] | None, tuple[tuple[Finding, ...], ...] | None]:
    """Write and/or apply the baseline (see :mod:`ontolint.baseline`).

    Also return its stale entries (OPS003) and, per file, the findings it accepted; both are ``None`` without
    ``--baseline``.
    """
    if args.write_baseline:
        Path(args.write_baseline).write_text(baseline.dumps(baseline.build(files)), encoding="utf-8")
    if args.baseline:
        applied = baseline.apply(baseline.loads(Path(args.baseline).read_text(encoding="utf-8")), files, SET_RULES)
        return applied.files, applied.stale, tuple(applied.baselined)
    return files, None, None


_LOADER_POLICY: ContextVar[Policy | None] = ContextVar("loader_policy", default=None)


# gremlin: pardon[untestable] every test covers a decorator: too slow to time; test_mutation_pardon_audit kills it
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
    """Index every ``--import-dir`` once, warning about each file the safe loader refused (TOOL010)."""
    catalogs = []
    for directory in args.import_dir:
        catalog = index_directory(Path(directory), policy)
        for line in catalog.refused:
            print(f"TOOL010: warning: --import-dir {directory}: {line}", file=sys.stderr)
        catalogs.append(catalog)
    return tuple(catalogs)


def _import_root(args: argparse.Namespace) -> Path | None:
    return Path(args.import_root).resolve() if args.import_root else None


def _closure(item: InputFile, policy: Policy, options: ImportOptions) -> LoadedGraph:
    graph = load_graph(item, policy)
    return _closure_of(item, loaded_graph(graph), policy, options)


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


def _shapes_closure(
    item: InputFile, shapes: Graph, policy: Policy, options: ImportOptions
) -> tuple[Graph | None, Graph | None]:
    """What a shapes file imports, split into more shapes and the ontology background.

    An imported file that declares shapes (a shape library) is validated with like the shapes file
    itself; the others are the ontology SHACL validates the data against too, since shapes that check
    the class of a vocabulary individual need the ontology that types it (without it valid data reports
    false violations).  A file with both shapes and other triples is used both ways.  Each part is
    ``None`` when nothing that resolves supplies it.
    """
    closure = _closure_of(item, LoadedGraph(shapes, source_index(shapes)), policy, options)
    library, background = Graph(), Graph()
    for module in closure.modules[1:]:  # modules[0] is the shapes file itself
        graph = module.graph if module.graph is not None else Graph()
        if _shape_count(graph):
            print(
                f"TOOL009: note: {item.display} imports shapes from {module.display}; they are validated too",
                file=sys.stderr,
            )
            library += graph
            background += graph - _shape_triples(graph)
        else:
            background += graph
    return (library if len(library) else None), (background if len(background) else None)


def _shape_triples(graph: Graph) -> Graph:
    """The triples about ``graph``'s shapes and the blank nodes they own (inline property shapes, lists)."""
    owned = Graph()
    pending = [s for type_ in _SHAPE_TYPES for s in graph.subjects(RDF.type, type_)]
    pending += list(graph.subjects(SH.path, None))
    seen: set[Node] = set()
    while pending:
        node = pending.pop()
        if node in seen:
            continue
        seen.add(node)
        for p, o in graph.predicate_objects(node):
            owned.add((node, p, o))
            if isinstance(o, BNode):
                pending.append(o)
    return owned


class _ShapesParseFailure(Exception):
    """A shapes, profile or validator file did not parse; ``display`` names it unless it is ``--shapes``."""

    def __init__(self, failure: ParseFailure, display: str | None) -> None:
        super().__init__(str(failure))
        self.failure = failure
        self.display = display


def _parsed(item: InputFile, policy: Policy, named: bool) -> Graph:
    try:
        return load_graph(item, policy)
    except ParseFailure as exc:
        raise _ShapesParseFailure(exc, item.display if named else None) from exc


def _load_shapes(
    args: argparse.Namespace, policy: Policy, imports: ImportOptions | None
) -> tuple[Graph | None, Graph | None]:
    """The run's shapes graph and its SHACL-only background (the ontology the shapes import), if any.

    Several validators of one profile are merged into one shapes graph, and their backgrounds likewise.
    """
    shapes: Graph | None = None
    background: Graph | None = None
    named = bool(args.shapes_from_profile)  # the historical --shapes failure line names no file
    for item in _shapes_inputs(args, policy, imports):
        graph = _parsed(item, policy, named)
        library, more = _shapes_closure(item, graph, policy, imports) if imports is not None else (None, None)
        shapes = _union(shapes, graph, library)
        background = _union(background, more)
    return shapes, background


def _union(*graphs: Graph | None) -> Graph | None:
    """The union of the graphs that are not ``None``; ``None`` when all are."""
    present = [g for g in graphs if g is not None]
    if not present:
        return None
    merged = Graph()
    for graph in present:
        merged += graph
    return merged


def _shapes_inputs(args: argparse.Namespace, policy: Policy, imports: ImportOptions | None) -> list[InputFile]:
    """The shapes files of the run: ``--shapes``, or the SHACL validators ``--shapes-from-profile`` names."""
    if args.shapes:
        return [resolve_inputs([args.shapes], Path.cwd())[0]]
    if not args.shapes_from_profile:
        return []
    profile = resolve_inputs([args.shapes_from_profile], Path.cwd())[0]
    graph = _parsed(profile, policy, named=True)
    beside = profile.path.parent / CATALOG_NAME
    catalogs = [
        *([read_catalog(beside, policy.max_input_bytes)] if beside.is_file() else []),
        *([imports.catalog] if imports is not None and imports.catalog is not None else []),
    ]
    found, passed_over = shapes_files(profile.path, graph, catalogs, imports.import_dirs if imports else ())
    root = (imports.import_root if imports else None) or default_import_root(profile.path.parent)
    for iri in passed_over:
        print(
            f"TOOL007: note: {profile.display} names validator {iri}, which is not SHACL; it is not used",
            file=sys.stderr,
        )
    items: list[InputFile] = []
    for iri, path in found:
        if not inside_root(path, root):
            raise InputRejected("SEC009", f"the validator {iri} resolves to {path}, outside the import root {root}")
        item = resolve_inputs([str(path)], Path.cwd())[0]
        print(
            f"TOOL007: note: {profile.display} names validator {iri}; using {item.display} as --shapes", file=sys.stderr
        )
        items.append(item)
    return items


def _library(
    args: argparse.Namespace, policy: Policy, imports: ImportOptions | None, inputs: Sequence[InputFile]
) -> PatternLibrary | None:
    """The members of ``--pattern-library``, read inside the import root; the linted files are not members."""
    if not args.pattern_library:
        return None
    directory = Path(args.pattern_library)
    if not directory.is_dir():
        raise InputRejected("TOOL001", f"--pattern-library {directory} is not a directory")
    root = (imports.import_root if imports else None) or default_import_root(directory)
    return load_library(directory, policy, root, exclude=[item.path for item in inputs])


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
            graphs.append(loaded_graph(graph))
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


EXIT_PIPE_CLOSED = 141
"""Exit status when the reader of stdout or stderr closed the pipe first (``ontolint ... | head``).

It is 128 plus SIGPIPE, what a shell reports for the tools a closed pipe kills (``cat``, ``grep``, ``git``). It is
neither a verdict (0, 1) nor a tool failure (2): the report was not delivered. A run that had already failed keeps 2.
"""


class _StdoutClosed(Exception):
    """The reader of stdout has gone: stop writing and say nothing."""


def _release(stream: TextIO) -> None:
    """Point the file descriptor of ``stream`` at the null device once its reader has gone.

    Python flushes the standard streams again when it exits. With a dead pipe underneath, that flush fails after
    ``main`` has returned (``Exception ignored ... BrokenPipeError``, status 120); what is still buffered goes to the
    null device instead. It runs only after a genuine ``BrokenPipeError``, and it affects the whole process, which is
    right for a command line and the reason a library caller of ``main`` should not rely on stdout afterwards.
    """
    try:
        descriptor = stream.fileno()
        null = os.open(os.devnull, os.O_WRONLY)
    except (AttributeError, OSError, ValueError):  # no descriptor behind the stream: a capture, a custom stdout
        return
    try:
        os.dup2(null, descriptor)
    finally:
        os.close(null)


def _write_stdout(text: str) -> None:
    """Write ``text`` to stdout and flush it; raise ``_StdoutClosed`` when its reader has gone.

    The flush is what makes a small output fail here, where it can be handled, not at the interpreter's last flush.
    With no stdout at all (``pythonw``, ``>&-``) there is nothing to write to, as ``print`` has always taken it.
    """
    stream = sys.stdout
    if stream is None:
        return
    try:
        stream.write(text)
        flush = getattr(stream, "flush", None)
        if flush is not None:
            flush()
    except BrokenPipeError:
        _release(sys.stdout)
        raise _StdoutClosed from None


def _flush_standard_streams() -> None:
    """Flush stdout and stderr; a reader that left while output was buffered is released, not reported.

    This runs on the way out of ``main``, so it must never replace the outcome (a return value, or the ``SystemExit`` of
    ``--help``): any other failure is left for the interpreter's own flush, which reports it as it always did.
    """
    for stream in (sys.stdout, sys.stderr):
        flush = getattr(stream, "flush", None)  # no stream (pythonw) or a custom one without flush
        if flush is None:
            continue
        try:
            flush()
        except BrokenPipeError:
            _release(stream)
        except (OSError, ValueError):
            continue


def _info_command(args: argparse.Namespace) -> int | None:
    """Handle --version, --list-rules and --explain; ``None`` means a normal lint run.

    ``--format json`` and ``--format sarif`` print the rules as JSON; every other format, ``markdown`` included,
    prints the text form, since a rule list is no run to summarise.
    """
    registry = default_registry()
    kind = "json" if args.format in ("json", "sarif") else "text"
    try:
        if args.version:
            _write_stdout(f"ontolint {package_version()}\n")
        elif args.list_rules:
            _write_stdout(render_rule_list(rule_rows(registry), kind) + "\n")
        elif args.explain:
            try:
                _write_stdout(render_explanation(explain_rule(args.explain, registry), kind) + "\n")
            except UnknownRuleError:
                try:
                    print(
                        f"TOOL001: unknown rule {args.explain!r}; use --list-rules to see valid identifiers",
                        file=sys.stderr,
                    )
                except BrokenPipeError:  # nobody reads it; the exit status still says what happened
                    _release(sys.stderr)
                return 2
        else:
            return None
    except _StdoutClosed:
        return EXIT_PIPE_CLOSED
    return 0


def _profile(args: argparse.Namespace) -> Profile | None:
    return PROFILES[args.profile] if args.profile else None


def _plan(args: argparse.Namespace, config: Policy, shapes: Graph | None, registry: RuleRegistry) -> RunPlan:
    profile = _profile(args)
    selection = resolve_selection(registry, profile, split_selectors(args.select), split_selectors(args.ignore))
    overrides = {**dict(profile.severity_overrides if profile else ()), **config.severity_mapping}
    return RunPlan(_policy(args, config, config.ignored_rules), selection, overrides, shapes, registry)


class UnknownPolicyRuleError(ValueError):
    """The policy file names a rule its ignore or override cannot act on: an unknown or a pipeline rule."""


def _check_policy_rules(config: Policy, registry: RuleRegistry) -> None:
    """Reject rule IDs in ``ignored_rules`` and ``severity_overrides`` that cannot change the run (OPS009).

    A typo there would otherwise be silent: the rule it meant to silence keeps running, and an
    override changes nothing.  Proposed (catalogue-only) rules are rejected too, with a hint, because
    they never run; IDs are matched exactly, like the engine does.  So are pipeline rules (the
    safe-loader refusals, ``INPUT001``, ``TOOL001``): they always apply and never produce a finding to
    ignore or re-grade.  Every problem goes into one message, unknown IDs first.
    """
    named = {
        "ignored_rules": sorted(config.ignored_rules),
        "severity_overrides": [r for r, _ in config.severity_overrides],
    }
    unknown = {key: [rule for rule in rules if rule not in registry] for key, rules in named.items()}
    pipeline = {
        key: [rule for rule in rules if rule in registry and is_pipeline(registry.get(rule))]
        for key, rules in named.items()
    }
    parts = []
    if problems := _policy_problems(unknown):
        message = f"unknown rule identifier(s) in {problems}"
        proposed = frozenset(row.rule_id for row in planned_rows())
        planned = sorted({rule for rules in unknown.values() for rule in rules} & proposed)
        if planned:
            message += f"; {', '.join(planned)} exist in the catalogue as proposed rules and are not implemented"
        parts.append(message + "; use --list-rules to see valid identifiers")
    if problems := _policy_problems(pipeline):
        parts.append(
            f"pipeline rule(s) in {problems} ({PIPELINE_HELP}), which always apply and the policy cannot change; "
            "remove them"
        )
    if parts:
        raise UnknownPolicyRuleError("; ".join(parts))


def _policy_problems(by_key: dict[str, list[str]]) -> str:
    """``key: A, B; other: C`` for the keys that name any rule, else the empty string."""
    return "; ".join(f"{key}: {', '.join(rules)}" for key, rules in by_key.items() if rules)


def _output_failure(what: str, exc: Exception) -> str:
    return f"TOOL001: {what} output failed: {type(exc).__name__}: {exc}"


def _write_text(path: str | Path, text: str, *, what: str) -> str | None:
    """Write ``text`` to ``path`` as UTF-8; return the TOOL001 line when it cannot be written, else ``None``.

    The text is encoded first, so a report that UTF-8 cannot hold (a lone surrogate) leaves an existing file as it
    was instead of truncating it.  ``write_text`` keeps the platform's newline translation.
    """
    try:
        text.encode("utf-8")
        Path(path).write_text(text, encoding="utf-8")
    except (OSError, UnicodeEncodeError) as exc:
        return _output_failure(what, exc)
    return None


def _emit(output: str, args: argparse.Namespace) -> str | None:
    """Write the report to ``--output`` or stdout; return the TOOL001 line when it could not be written.

    Raises ``_StdoutClosed`` when the reader of stdout has gone, which is not a failure to report.  Every finding
    is masked where it is made; the report is masked again here, so no text of it (a rule's failure, a locator's
    problem) can print an IRI userinfo (:mod:`ontolint.redaction`).
    """
    text = redact_rendered(output) + "\n"
    if args.output:
        return _write_text(args.output, text, what="report")
    try:
        _write_stdout(text)
    except (UnicodeEncodeError, OSError) as exc:  # a closed pipe is ``_StdoutClosed``, raised before this
        return _output_failure("report", exc)
    return None


def _secondary_input_error(exc: InputRejected | _ShapesParseFailure | ProfileError) -> str:
    """The failure line for a shapes, profile or pattern-library input that cannot be used."""
    if isinstance(exc, InputRejected):
        return f"{exc.rule_id}: {exc.message}"
    if isinstance(exc, _ShapesParseFailure):
        return _parse_error(exc.failure, exc.display)
    return f"TOOL001: --shapes-from-profile: {exc}"


def _lint(args: argparse.Namespace, stage: list[str]) -> RunReport | int:
    """Run the whole lint; ``stage`` tracks progress for error messages. Returns a report or an exit code."""
    registry = default_registry()
    config = Policy.from_mapping(json.loads(Path(args.config).read_text(encoding="utf-8")) if args.config else {})
    _check_policy_rules(config, registry)
    check_selectors(registry, split_selectors(args.select), split_selectors(args.ignore))
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
    try:
        shapes, background = _load_shapes(args, limits, imports)
        library = _library(args, limits, imports, inputs)
    except (InputRejected, _ShapesParseFailure, ProfileError) as exc:
        print(_secondary_input_error(exc), file=sys.stderr)
        return 2
    stage[0] = "lint execution"
    plan = replace(_plan(args, config, shapes, registry), shacl_background=background)
    if library is not None:
        plan = replace(plan, policy=replace(plan.policy, library=library))
    shared = (
        shared_identities(inputs, graphs, limits)
        if any(spec.rule_id in SET_RULES for spec in plan.selection.run)
        else [()] * len(inputs)
    )
    # gremlin: pardon[equivalent] shared holds one entry per input, like graphs, so strict never fires
    rows = zip(inputs, graphs, shared, strict=True)
    files = [_lint_file(item, graph, plan, args, found) for item, graph, found in rows]
    files, stale, baselined = _apply_baselines(files, args)
    return RunReport(
        tuple(files), plan.selection.run + plan.selection.ignored, plan.overrides, stale, baselined=baselined
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the linter CLI and return its process exit code.

    0 is clean, 1 gated findings, 2 a tool failure, and 141 (``EXIT_PIPE_CLOSED``) that the reader of stdout or
    stderr closed the pipe first. Stdout is handled where the report is written. The lint turns every other
    exception into TOOL001, so a ``BrokenPipeError`` that gets this far was raised by a write to stderr before the
    report existed: with nobody to read diagnostics, the run stops (``ontolint ... 2>&1 | head``). Once the report is
    out, a closed stderr no longer changes the exit status (see ``_finish``).

    Stderr is written through a :class:`~ontolint.redaction.RedactingStream` while the command runs, so no note,
    refusal, parser message or library warning prints an IRI userinfo; the caller's stream is restored after.  An
    exception that escapes the command (an ontolint bug) is printed through it too, as a traceback, with the
    status of a tool failure: once the stream is restored, the interpreter would print its message unmasked.
    """
    stderr = sys.stderr
    redacting = None if stderr is None else RedactingStream(stderr)  # None under pythonw: nothing is written
    if redacting is not None:
        sys.stderr = cast("TextIO", redacting)
    try:
        return _main(argv)
    except BrokenPipeError:
        _release(sys.stderr)
        return EXIT_PIPE_CLOSED
    except Exception:  # noqa: BLE001 -- printed masked, see above
        traceback.print_exc()
        return TOOL_FAILURE_EXIT
    finally:
        if redacting is not None:
            with contextlib.suppress(OSError, ValueError):  # a closed stderr: the flush below releases it
                redacting.drain()
        _flush_standard_streams()
        sys.stderr = stderr


def _usage_problem(args: argparse.Namespace) -> str | None:
    """The first usage error of a lint run's options, checked after the info commands; ``None`` if there is none."""
    if not args.ontology:
        return "at least one ONTOLOGY path is required"
    if args.fail_on_stale_baseline and not args.baseline:
        return "--fail-on-stale-baseline requires --baseline"
    if args.shapes and args.shapes_from_profile:
        return "--shapes and --shapes-from-profile are alternatives; give one"
    if args.module_annotation is not None and args.module_by is not None:
        return "--module-annotation and --module-by are alternatives; give one"
    if args.measurements and args.format != "json":
        return "--measurements requires --format json"
    return None


def _main(argv: Sequence[str] | None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # RDFLib logs its own warnings (and tracebacks) while parsing; ontolint reports input problems itself.
    logging.getLogger("rdflib").setLevel(logging.ERROR)
    info = _info_command(args)
    if info is not None:
        return info
    if (problem := _usage_problem(args)) is not None:
        parser.error(problem)
    stage = ["configuration"]
    try:
        outcome = _lint(args, stage)
    except (UnknownSelectorError, SelectorSyntaxError, PipelineSelectorError) as exc:
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
    closed = False
    try:
        failure = _emit(render_report(report, args.format, code), args)
    except _StdoutClosed:
        failure, closed = None, True
    if failure is not None:
        code = TOOL_FAILURE_EXIT
    try:
        if failure is not None:
            print(failure, file=sys.stderr)
        for path, x in report.broken:
            print(f"TOOL001: rule {x.rule_id} {x.status.value} for {path}: {x.detail}", file=sys.stderr)
    except BrokenPipeError:  # the report is out and the exit status says what these lines would have: keep it
        _release(sys.stderr)
    return EXIT_PIPE_CLOSED if closed and code != TOOL_FAILURE_EXIT else code
