"""pySHACL adapter: SHACL validation results become SHACL001 findings.

Validation runs under :func:`ontolint.loader.network_disabled`, which patches process-global socket functions
under a lock: validations from several threads of one process are serialised, as parses are.  With a time budget
(:func:`bounded_shacl_issues`) it runs in a :mod:`ontolint.worker` process that is stopped when the budget is
exhausted; the worker answers with finished findings as JSON, which equal the in-process ones because blank nodes
are named by their content, never by their label.
"""

from __future__ import annotations

import contextlib
import json
import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field, fields
from typing import Any

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.extras.shacl import SHACLPathError, parse_shacl_path
from rdflib.namespace import RDF, SH
from rdflib.term import Node

from ontolint.loader import network_disabled
from ontolint.models import Evidence, EvidenceValue, Finding, plain_evidence
from ontolint.redaction import clip
from ontolint.rules.shacl_quality import has_path_defect, property_shape_nodes
from ontolint.rules.specs import FIXES
from ontolint.rules.support import ntriples_literal, stable_blank_id
from ontolint.worker import WorkerFailed, WorkerGone, WorkerTimeout, decode_graph, encode_graph, run_bounded

MAX_LIST_LENGTH = 400
"""Longest rdf:list the SHACL backend is asked to validate (pySHACL meta-validation is quadratic in it)."""
MAX_LIST_COST = 160_000
"""Bound on the sum over lists of ``length ** 2`` (a few seconds of pySHACL work)."""

_BAD_IRI_CHARS = frozenset('<>" {}|\\^`')
"""The characters ``rdflib`` refuses to serialise in an IRI (``rdflib.term._is_valid_uri``)."""


SEVERITIES: dict[Node, str] = {SH.Violation: "error", SH.Warning: "warning", SH.Info: "info"}
"""Finding severity for each standard ``sh:resultSeverity``; any other (custom) severity is an error."""

MAX_PATH_DEPTH = 32
"""Deepest nesting of SHACL path constructors spelled in evidence; a deeper ``sh:resultPath`` is malformed."""
MAX_PATH_SIZE = 1_000
"""Most path nodes and list cells walked for one ``sh:resultPath``, counted again each time a shared part is."""
MAX_DETAIL_DEPTH = 8
"""Deepest ``sh:detail`` nesting copied into evidence; results below it appear in no output (their top-level result
still does)."""
MALFORMED_PATH = "(malformed path)"
"""The ``resultPath`` evidence of a path that is not a well-formed, bounded SHACL path."""

_FIELDS = (
    ("focusNode", SH.focusNode),
    ("resultPath", SH.resultPath),
    ("value", SH.value),
    ("sourceShape", SH.sourceShape),
    ("sourceConstraintComponent", SH.sourceConstraintComponent),
    ("sourceConstraint", SH.sourceConstraint),
    ("detail", SH.detail),
    ("resultMessage", SH.resultMessage),
    ("resultSeverity", SH.resultSeverity),
)
"""Each evidence key and the result property it holds, in the order of the SHACL result table (SHACL 3.6.2).

SHACL-AF result annotations (``sh:resultAnnotation``, SHACL Advanced Features section 4) are not here: pySHACL 0.40.2
does not write them.  When the annotation canaries of ``tests/test_shacl_evidence.py`` fail, a pySHACL upgrade writes
them: map them here, update the evidence key list in README "Optional SHACL validation" and ``rules/external.py``,
and update ``test_each_evidence_key_is_the_local_name_of_its_shacl_property``.
"""
EVIDENCE_FIELDS = frozenset(predicate for _key, predicate in _FIELDS)
"""Every validation result property SHACL001 keeps (all but ``rdf:type``)."""
_RESULT_KEY = ("sourceShape", "sourceConstraintComponent", "resultPath", "value", "sourceConstraint")
_PATH_LINKS = (SH.inversePath, SH.alternativePath, SH.zeroOrMorePath, SH.oneOrMorePath, SH.zeroOrOnePath, RDF.first)
"""The path constructors (and the list items of a sequence or alternative) nested one level below a path node."""


class ShapesRejected(ValueError):
    """An input graph would make pySHACL crash or run for minutes; it is refused before validation."""


META_SHACL_PREFIX = "SHACL File does not validate against the SHACL Shapes SHACL (MetaSHACL) file."
"""The first line of the error pySHACL raises when ``meta_shacl=True`` finds the shapes graph ill-formed; it then
appends its whole validation report, and logs the same text at ERROR on :data:`PYSHACL_LOGGER`."""
PYSHACL_LOGGER = "pyshacl-validate"
"""The logger ``pyshacl.validate`` writes to stderr with (it replaces the handlers of this name on every call)."""
MAX_RESULT_LINES = 20
"""Most MetaSHACL results :class:`ShapesNotWellFormed` lists; the rest are counted."""
MAX_RESULT_LINE = 300
"""Longest result line before its pointer, as many characters as a rule run's detail takes in the Markdown summary."""
ELLIPSIS = "..."
_SHQ_COMPONENT_PATHS: dict[tuple[str, URIRef], str] = {
    **{("DatatypeConstraintComponent", p): "SHQ008" for p in (SH.minCount, SH.maxCount, SH.minLength, SH.maxLength)},
    **{("NodeKindConstraintComponent", p): "SHQ022" for p in (SH.targetClass, SH.targetSubjectsOf, SH.targetObjectsOf)},
    ("NodeKindConstraintComponent", SH.severity): "SHQ014",
}
"""``(constraint component, result path)`` of a MetaSHACL result and the SHQ rule that reports the same defect on the
same shape (see :func:`_pointer`); a pair that is not here has no rule, or one that does not always fire."""


class ShapesNotWellFormed(RuntimeError):
    """The shapes graph does not conform to SHACL-SHACL (SHACL's own shapes for shapes graphs).

    pySHACL refuses it before validating any data, so SHACL001 has no verdict (the rule is ``failed``, exit ``2``),
    but the defect is the user's, not a tool crash: the message is :attr:`summary` and one line per result, so the
    report prints each result once instead of pySHACL's whole validation report.  A line is ``<focus>: <path>:
    <message>`` (no path for a node-level result), masked, cut at :data:`MAX_RESULT_LINE` characters and ended by
    ``(SHQnnn)`` when that rule reports the same defect.
    """

    summary = "the shapes graph does not conform to SHACL-SHACL"

    def __init__(self, results: tuple[str, ...]) -> None:
        super().__init__("\n".join((self.summary, *results)))
        self.results = results


def _first_unserialisable_iri(graph: Graph) -> str | None:
    seen: set[str] = set()
    for triple in graph:
        for term in triple:
            if isinstance(term, URIRef) and term not in seen:
                seen.add(term)
                if not _BAD_IRI_CHARS.isdisjoint(term):
                    return str(term)
    return None


def _check_iris(graph: Graph, name: str) -> None:
    bad = _first_unserialisable_iri(graph)
    if bad is not None:
        raise ShapesRejected(f"{name} contains an IRI that cannot be serialised: {clip(bad, 80)!r}")


@dataclass
class _Lists:
    """The rdf:list structure of one graph and the cells the checks have walked so far."""

    name: str
    rest: dict[Node, Node]
    cells: set[Node]
    reached: set[Node] = field(default_factory=set[Node])


def _walk_list(head: Node, lists: _Lists, *, strict: bool) -> int:
    """Walk one list from ``head`` and return its length; reject cycles, and in strict mode sharing and length."""
    length, cell = 0, head
    walk: set[Node] = set()
    while cell != RDF.nil and cell in lists.cells:
        if cell in walk:
            raise ShapesRejected(f"{lists.name} contains a cyclic rdf:list (rdf:rest loops back)")
        if cell in lists.reached:
            if strict:
                raise ShapesRejected(f"{lists.name} contains an rdf:list cell shared by several lists")
            break  # a shared tail is legal RDF; the cells beyond it were already walked
        walk.add(cell)
        lists.reached.add(cell)
        length += 1
        if strict and length > MAX_LIST_LENGTH:
            raise ShapesRejected(f"{lists.name} contains an rdf:list longer than {MAX_LIST_LENGTH} items")
        cell = lists.rest.get(cell, RDF.nil)
    return length


def _check_lists(graph: Graph, name: str, *, strict: bool) -> None:
    rest: dict[Node, Node] = {}
    indegree: Counter[Node] = Counter()
    for cell, _, tail in graph.triples((None, RDF.rest, None)):
        if cell in rest and rest[cell] != tail:
            raise ShapesRejected(f"{name} contains an rdf:list cell with several rdf:rest values")
        rest[cell] = tail
        indegree[tail] += 1
    lists = _Lists(name, rest, set(rest) | {s for s, _, _ in graph.triples((None, RDF.first, None))})
    cost = 0
    for head in (c for c in lists.cells if indegree[c] == 0):
        length = _walk_list(head, lists, strict=strict)
        cost += length * length
        if strict and cost > MAX_LIST_COST:
            raise ShapesRejected(f"{name} contains too many long rdf:lists to validate in reasonable time")
    if lists.reached != lists.cells - {RDF.nil}:
        raise ShapesRejected(f"{name} contains a cyclic rdf:list (rdf:rest loops back)")


def check_graph(graph: Graph, name: str, *, strict: bool = True) -> None:
    """Raise :class:`ShapesRejected` unless pySHACL can process ``graph`` safely (linear time, no recursion).

    Every check looks for IRIs rdflib cannot serialise and for cyclic lists. ``strict`` (the shapes graph)
    additionally rejects shared, overlong or numerous long lists, because pySHACL's meta-validation of the
    shapes walks each list once per internal result, which is quadratic in the list length.
    """
    _check_iris(graph, name)
    _check_lists(graph, name, strict=strict)


def _name(graph: Graph, node: Node | None) -> str:
    """Name a report node: a blank node by its content-stable identity in ``graph``, never its parser label.

    Inline shapes (``sh:property [ ... ]``) and blank focus nodes get new labels on every parse; using the
    label would change the message, and so the baseline fingerprint, from one run to the next.
    """
    if node is None:
        return "(unknown)"
    if isinstance(node, BNode):
        return stable_blank_id(graph, node)
    return str(node)


def _term(graph: Graph, node: Node) -> str:
    """A data term as evidence: a literal in N-Triples (never confused with an IRI), any other node as :func:`_name`."""
    return ntriples_literal(node) if isinstance(node, Literal) else _name(graph, node)


def _check_path(graph: Graph, node: Node) -> None:
    """Raise :class:`SHACLPathError` unless the path below ``node`` is acyclic and within the depth and size bounds.

    rdflib's parser recurses once per nesting level and expands a shared part each time it is reached, and
    the report is input like any other graph, so this walk comes first (iteratively).
    """
    stack: list[tuple[Node, int, frozenset[Node]]] = [(node, 0, frozenset())]
    size = 0
    while stack:
        current, depth, above = stack.pop()
        size += 1
        if size > MAX_PATH_SIZE or depth > MAX_PATH_DEPTH or current in above:
            raise SHACLPathError("the path is cyclic, too deep or too large")
        if isinstance(current, BNode):
            above |= {current}
            stack.extend((child, depth + 1, above) for link in _PATH_LINKS for child in graph.objects(current, link))
            stack.extend((tail, depth, above) for tail in graph.objects(current, RDF.rest))


def _path_text(report: Graph, sg: Graph, node: Node) -> str:
    """``sh:resultPath`` as evidence: a predicate path's IRI, any other path in SPARQL 1.1 property-path syntax."""
    if isinstance(node, URIRef):
        return str(node)
    for graph in (report, sg):  # pySHACL copies a complex path into the report; the shapes graph is a fallback
        try:
            _check_path(graph, node)
            return parse_shacl_path(graph, node).n3()
        except (SHACLPathError, TypeError, ValueError):
            continue
    return MALFORMED_PATH


def _canonical(evidence: Evidence) -> str:
    """The sort key of an evidence object: its JSON, keys in field order, characters unescaped (code-point order)."""
    return json.dumps(evidence, ensure_ascii=False)


@dataclass(frozen=True)
class _Report:
    """A validation report with the graphs its terms are named in."""

    graph: Graph
    data: Graph
    shapes: Graph


def _evidence(report: _Report, result: Node, depth: int = 0, above: frozenset[Node] = frozenset()) -> Evidence:
    """Every result property of :data:`_FIELDS` of one validation result, keyed by its SHACL name; one the report
    lacks is omitted.

    Data terms (focus node, value) are named in the data graph and shapes terms in the shapes graph, as the
    finding names them.  ``sh:detail`` results are nested, sorted, at most :data:`MAX_DETAIL_DEPTH` deep and
    never around a cycle.
    """
    evidence: dict[str, EvidenceValue] = {}
    for key, predicate in _FIELDS:
        values = list(report.graph.objects(result, predicate))
        if not values:
            continue
        if key == "resultMessage":  # the lexical forms, as in the finding's message (language tags dropped)
            evidence[key] = tuple(sorted(map(str, values)))
        elif key == "detail":
            inside = above | {result}
            nested = (
                [_evidence(report, d, depth + 1, inside) for d in values if d not in inside]
                if depth < MAX_DETAIL_DEPTH
                else []
            )
            if nested:
                evidence[key] = tuple(sorted(nested, key=_canonical))
        # The single-valued fields below take one value, arbitrarily, if a (non-pySHACL) report gives several.
        elif key in ("focusNode", "value"):
            evidence[key] = _term(report.data, values[0])
        elif key == "resultPath":
            evidence[key] = _path_text(report.graph, report.shapes, values[0])
        else:
            evidence[key] = _name(report.shapes, values[0])
    return evidence


def shacl_result_key(evidence: Evidence) -> tuple[str, ...]:
    """What tells one SHACL result from another of the same shape on the same focus, ``""`` for a missing part.

    ``(sourceShape, sourceConstraintComponent, resultPath, value, sourceConstraint)``: the structured subject of a
    SHACL001 finding, independent of the message wording.
    """
    return tuple(value if isinstance(value := evidence.get(key, ""), str) else "" for key in _RESULT_KEY)


def detail_foci(evidence: Evidence | None) -> set[str]:
    """The ``focusNode`` of every result nested in ``evidence``'s ``detail``, at any depth, spelled as the evidence
    spells it (an IRI as is, a blank node by its content-stable id, a literal in N-Triples)."""
    foci: set[str] = set()
    stack = [evidence] if evidence is not None else []
    while stack:
        current = stack.pop()
        for nested in current.get("detail", ()):
            if isinstance(nested, str):  # never in SHACL001 evidence: ``detail`` holds evidence objects
                continue
            focus = nested.get("focusNode")
            if isinstance(focus, str):
                foci.add(focus)
            stack.append(nested)
    return foci


def _results(report: Graph) -> set[Node]:
    """The validation results of ``report``: the ``sh:result`` values of its ``sh:ValidationReport`` (SHACL 3.6.1.2).

    A result nested with ``sh:detail`` explains another (SHACL 3.5, 4.7.1) and is only that result's evidence,
    although pySHACL types it ``sh:ValidationResult`` too.  Only a report node that is the object of no triple is
    read: pySHACL copies into the report every triple reachable from a blank ``sh:value`` or ``sh:focusNode``,
    so a data value shaped like a report (always the object of the triple that holds it) must not add findings.
    A report that links no result (never pySHACL's) falls back to every node typed ``sh:ValidationResult``.
    """
    listed = {
        r
        for node in report.subjects(RDF.type, SH.ValidationReport)
        if (None, None, node) not in report
        for r in report.objects(node, SH.result)
    }
    return listed or set(report.subjects(RDF.type, SH.ValidationResult))


def _short(iri: str) -> str:
    """A result path as the SHACL vocabulary's ``sh:`` name when it is one."""
    return "sh:" + iri.removeprefix(str(SH)) if iri.startswith(str(SH)) else iri


def _pointer(
    sg: Graph, focus: Node | None, component: str, path: Node | None, property_shapes: set[Node]
) -> str | None:
    """The SHQ rule that reports the defect of one MetaSHACL result on its shape, or ``None``.

    A shapes graph that breaks SHACL-SHACL through a pair of :data:`_SHQ_COMPONENT_PATHS` breaks the condition of
    exactly that rule.  SHQ023 is told by its own condition (:func:`has_path_defect`), because the results that
    follow from a property shape's paths also arise where SHQ023 keeps a gap: a node shape with a path
    (``sh:maxCount 0`` of SHACL 2.2) has the same result as a property shape with two.  They are the ``sh:path``
    cardinality results and the ``sh:xone`` of a shape that is neither a node nor a property shape, which has no path.
    """
    if focus is None:
        return None
    if path is None:
        follows = component == "XoneConstraintComponent"
    else:
        follows = path == SH.path and component in ("MinCountConstraintComponent", "MaxCountConstraintComponent")
    if follows and has_path_defect(sg, focus, property_shapes):
        return "SHQ023"
    return _SHQ_COMPONENT_PATHS.get((component, path)) if isinstance(path, URIRef) else None


def _local(report: Graph, result: Node) -> str:
    """The local name of a result's constraint component (``MinCountConstraintComponent``), ``""`` if it has none."""
    component = next(report.objects(result, SH.sourceConstraintComponent), None)
    return str(component).rpartition("#")[2] if component is not None else ""


def _metashacl_lines(report: Graph, sg: Graph) -> tuple[str, ...]:
    """One sorted line per MetaSHACL result of ``report``, at most :data:`MAX_RESULT_LINES` and a count of the rest."""
    property_shapes = property_shape_nodes(sg)
    lines: list[str] = []
    for result in _results(report):
        path_node = next(report.objects(result, SH.resultPath), None)
        path = _short(_path_text(report, sg, path_node)) if path_node is not None else None
        component = _local(report, result)
        message = "; ".join(sorted(map(str, report.objects(result, SH.resultMessage)))) or component or "(no message)"
        focus_node = next(report.objects(result, SH.focusNode), None)
        parts = (_name(sg, focus_node), path, " ".join(message.split()))  # one line, whatever pySHACL wrote
        line = clip(": ".join(part for part in parts if part), MAX_RESULT_LINE, ELLIPSIS)
        rule = _pointer(sg, focus_node, component, path_node, property_shapes)
        lines.append(line if rule is None else f"{line} ({rule})")
    lines.sort()
    if len(lines) > MAX_RESULT_LINES:
        lines[MAX_RESULT_LINES:] = [f"... and {len(lines) - MAX_RESULT_LINES} more result(s) not shown"]
    return tuple(lines)


class _WithoutMetaShaclReport(logging.Filter):
    """Drops the record pySHACL logs with the whole MetaSHACL report: :class:`ShapesNotWellFormed` says it once."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.getMessage().startswith(META_SHACL_PREFIX)


def _metashacl_failure(sg: Graph, failure: Exception) -> ShapesNotWellFormed | None:
    """``failure`` as a :class:`ShapesNotWellFormed` when it is pySHACL's MetaSHACL error and the shapes graph does
    not conform to SHACL-SHACL; ``None`` otherwise.

    The text only says where to look: the shapes graph is meta-validated again, so a pass leaves the failure what it
    is.  The second run is the price of a structured report (the exception holds pySHACL's text); it happens only
    when the first one failed.
    """
    if not str(failure).startswith(META_SHACL_PREFIX):
        return None
    try:
        from pyshacl.entrypoints import meta_validate  # noqa: PLC0415 -- the same module as ``validate``.
    except ImportError:  # a pySHACL that does not export it: no result to list, the failure keeps its text
        return None
    conforms, report, _ = meta_validate(sg, inference="none", advanced=True, abort_on_first=False)
    if conforms or not isinstance(report, Graph):
        return None
    return ShapesNotWellFormed(_metashacl_lines(report, sg))


def _pyshacl(validate: Callable[..., Any], g: Graph, sg: Graph) -> tuple[bool, object]:
    """``(conforms, report)`` from pySHACL, run with the network disabled; a failure is diagnosed, then re-raised.

    Shapes are input too: a SPARQL constraint or SHACL-AF function must not reach the network, and an attempt
    fails the rule even when pySHACL swallowed the refusal.  A shapes graph that breaks SHACL-SHACL is raised as
    :class:`ShapesNotWellFormed`, with pySHACL's own copy of its report kept off stderr.
    """
    failure: Exception | None = None
    quiet = _WithoutMetaShaclReport()
    pyshacl_log = logging.getLogger(PYSHACL_LOGGER)
    with network_disabled() as attempts:  # serialised: the logger filter below is process-global
        pyshacl_log.addFilter(quiet)
        try:
            conforms, report, _ = validate(
                g, shacl_graph=sg, inference="none", advanced=True, meta_shacl=True, abort_on_first=False
            )
        except Exception as exc:  # noqa: BLE001 -- classified below, once the network guard is lifted.
            failure = exc
        finally:
            pyshacl_log.removeFilter(quiet)
    if attempts.network:
        raise RuntimeError(
            f"SHACL validation tried to use the network ({attempts.network[0]}); the network is disabled"
        ) from failure
    if failure is None:
        return bool(conforms), report
    if (not_well_formed := _metashacl_failure(sg, failure)) is not None:
        raise not_well_formed from failure
    if not isinstance(failure, ShapesRejected):
        # The data graph may hold large enumerations, odd IRIs (IRI001 reports those) or malformed lists, and
        # pySHACL fails on them only when a violation message has to describe such a node: diagnose it then.
        try:
            check_graph(g, "data graph", strict=False)
        except ShapesRejected as problem:
            raise ShapesRejected(f"{problem}; pySHACL failed on it: {type(failure).__name__}: {failure}") from failure
    raise failure


def shacl_issues(g: Graph, sg: Graph) -> list[Finding]:
    """Validate ``g`` against ``sg`` with pySHACL (imported lazily; required only with shapes).

    One finding per result the report lists (:func:`_results`), at that result's severity; the results nested in
    its ``sh:detail`` are its evidence, not findings.
    """
    try:
        from pyshacl import validate  # noqa: PLC0415 -- optional dependency, required only with --shapes.
    except ImportError:
        raise RuntimeError("pySHACL is needed for --shapes: pip install pyshacl") from None
    check_graph(sg, "shapes graph")
    conforms, report = _pyshacl(validate, g, sg)
    if conforms:
        return []
    if not isinstance(report, Graph):
        raise RuntimeError(f"pySHACL returned an unexpected report type: {type(report).__name__}")
    keyed: list[tuple[tuple[str, str, str], Finding]] = []
    graphs = _Report(report, g, sg)
    for result in _results(report):
        focus = _name(g, next(report.objects(result, SH.focusNode), None))
        message = "; ".join(sorted(map(str, report.objects(result, SH.resultMessage)))) or "SHACL constraint violation"
        src = _name(sg, next(report.objects(result, SH.sourceShape), None))
        level = next(report.objects(result, SH.resultSeverity), SH.Violation)
        severity = SEVERITIES.get(level, "error")
        if level not in SEVERITIES:
            message += f" (severity {level})"
        message = f"{message} [shape: {src}]"
        evidence = _evidence(graphs, result)
        finding = Finding(
            "SHACL001",
            severity,
            focus,
            message,
            FIXES["SHACL001"],
            "certain",
            evidence=evidence,
            subject=shacl_result_key(evidence),
        )
        # Sorted by what the finding holds, masked (ontolint.redaction): the order never depends on a password.
        keyed.append(((finding.focus, finding.message, _canonical(finding.evidence or {})), finding))
    # pySHACL's result order depends on the hash seed; findings tied on their message differ in evidence.
    results = [finding for _key, finding in sorted(keyed, key=lambda pair: pair[0])]
    if not results:
        results.append(
            Finding(
                "SHACL001",
                "error",
                "(shapes)",
                "SHACL returned nonconformant without individual result nodes.",
                FIXES["SHACL001"],
                "certain",
            )
        )
    return results


# --- validation under a time budget ------------------------------------------------------------------------------


class ValidationTimeout(TimeoutError):
    """SHACL validation did not finish within ``max_validation_seconds``; the worker was stopped."""


def _restore_evidence(raw: dict[str, Any]) -> Evidence:
    """The evidence :func:`plain_evidence` wrote: each list a tuple again, nested results included."""
    return {key: _restore_value(value) for key, value in raw.items()}


def _restore_value(value: Any) -> EvidenceValue:
    if isinstance(value, str):
        return value
    if all(isinstance(item, str) for item in value):
        return tuple[str, ...](value)
    return tuple(_restore_evidence(item) for item in value)


def _findings_to_json(findings: list[Finding]) -> list[dict[str, Any]]:
    """Every field of each finding as JSON (tuples become lists, evidence plain mappings)."""
    encoded = []
    for finding in findings:
        record: dict[str, Any] = {f.name: getattr(finding, f.name) for f in fields(Finding)}
        record["related"], record["subject"] = list(finding.related), list(finding.subject)
        record["evidence"] = None if finding.evidence is None else plain_evidence(finding.evidence)
        encoded.append(record)
    return encoded


def _findings_from_json(records: list[dict[str, Any]]) -> list[Finding]:
    """The findings :func:`_findings_to_json` wrote, field for field."""
    findings = []
    for record in records:
        values: dict[str, Any] = {**record, "related": tuple(record["related"]), "subject": tuple(record["subject"])}
        values["evidence"] = None if record["evidence"] is None else _restore_evidence(record["evidence"])
        findings.append(Finding(**values))
    return findings


# gremlin: pardon[untestable] every test covers a decorator: too slow to time; test_mutation_pardon_audit kills it
@dataclass(frozen=True)
class _ValidationJob:
    """A :class:`~ontolint.worker.WorkerTask`: the data and shapes graphs, encoded by the parent."""

    data: bytes
    shapes: bytes

    def prepare(self) -> None:
        """Import pySHACL before the budget starts (its absence is reported by :func:`shacl_issues`)."""
        with contextlib.suppress(ImportError):
            import pyshacl  # noqa: F401, PLC0415 -- warm-up import only

    def run(self) -> bytes:
        """Validate and answer with the findings; an exception becomes the worker's ``worker_error`` reply."""
        data, shapes = decode_graph(json.loads(self.data)), decode_graph(json.loads(self.shapes))
        return json.dumps({"findings": _findings_to_json(shacl_issues(data, shapes))}).encode()


def bounded_shacl_issues(g: Graph, sg: Graph, seconds: float) -> list[Finding]:
    """:func:`shacl_issues` in a worker process, stopped after ``seconds``: :class:`ValidationTimeout`.

    The budget starts once the worker has imported pySHACL and includes decoding the two graphs there.  A shapes
    graph the pre-check refuses is refused here, before any worker starts.  A failure inside the worker is a
    :class:`~ontolint.worker.WorkerFailed` naming the in-process exception, so the rule's detail reads the same.
    """
    check_graph(sg, "shapes graph")
    job = _ValidationJob(encode_graph(g), encode_graph(sg))
    try:
        reply = run_bounded(job, seconds, name="validation")
    except WorkerTimeout:
        raise ValidationTimeout(
            f"SHACL validation did not finish within the time budget of {seconds:g} seconds (max_validation_seconds)"
        ) from None
    except WorkerGone as exc:
        raise WorkerFailed("WorkerError", str(exc)) from None
    return _findings_from_json(reply["findings"])
