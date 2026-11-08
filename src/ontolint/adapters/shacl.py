"""pySHACL adapter: SHACL validation results become SHACL001 findings."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from rdflib import BNode, Graph, URIRef
from rdflib.namespace import RDF, SH
from rdflib.term import Node

from ontolint.models import Finding
from ontolint.rules.specs import FIXES
from ontolint.rules.support import stable_blank_id

MAX_LIST_LENGTH = 400
"""Longest rdf:list the SHACL backend is asked to validate (pySHACL meta-validation is quadratic in it)."""
MAX_LIST_COST = 160_000
"""Bound on the sum over lists of ``length ** 2`` (a few seconds of pySHACL work)."""

_BAD_IRI_CHARS = frozenset('<>" {}|\\^`')
"""The characters ``rdflib`` refuses to serialise in an IRI (``rdflib.term._is_valid_uri``)."""


SEVERITIES: dict[Node, str] = {SH.Violation: "error", SH.Warning: "warning", SH.Info: "info"}
"""Finding severity for each standard ``sh:resultSeverity``; any other (custom) severity is an error."""


class ShapesRejected(ValueError):
    """An input graph would make pySHACL crash or run for minutes; it is refused before validation."""


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
        raise ShapesRejected(f"{name} contains an IRI that cannot be serialised: {bad[:80]!r}")


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


def shacl_issues(g: Graph, sg: Graph) -> list[Finding]:
    """Validate ``g`` against ``sg`` with pySHACL (imported lazily; required only with shapes)."""
    try:
        from pyshacl import validate  # noqa: PLC0415 -- optional dependency, required only with --shapes.
    except ImportError:
        raise RuntimeError("pySHACL is needed for --shapes: pip install pyshacl") from None
    check_graph(sg, "shapes graph")
    try:
        conforms, report, _ = validate(
            g, shacl_graph=sg, inference="none", advanced=True, meta_shacl=True, abort_on_first=False
        )
    except ShapesRejected:
        raise
    except Exception as exc:
        # The data graph may hold large enumerations, odd IRIs (IRI001 reports those) or malformed lists, and
        # pySHACL fails on them only when a violation message has to describe such a node: diagnose it then.
        try:
            check_graph(g, "data graph", strict=False)
        except ShapesRejected as problem:
            raise ShapesRejected(f"{problem}; pySHACL failed on it: {type(exc).__name__}: {exc}") from exc
        raise
    if conforms:
        return []
    if not isinstance(report, Graph):
        raise RuntimeError(f"pySHACL returned an unexpected report type: {type(report).__name__}")
    results: list[Finding] = []
    for result in report.subjects(RDF.type, SH.ValidationResult):
        focus = _name(g, next(report.objects(result, SH.focusNode), None))
        message = "; ".join(sorted(map(str, report.objects(result, SH.resultMessage)))) or "SHACL constraint violation"
        src = _name(sg, next(report.objects(result, SH.sourceShape), None))
        level = next(report.objects(result, SH.resultSeverity), SH.Violation)
        severity = SEVERITIES.get(level, "error")
        if level not in SEVERITIES:
            message += f" (severity {level})"
        results.append(Finding("SHACL001", severity, focus, f"{message} [shape: {src}]", FIXES["SHACL001"], "certain"))
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
