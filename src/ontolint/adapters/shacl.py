"""pySHACL adapter: SHACL validation results become SHACL001 findings."""

from __future__ import annotations

from rdflib import Graph
from rdflib.namespace import RDF, SH

from ontolint.models import Finding
from ontolint.rules.specs import FIXES


def shacl_issues(g: Graph, sg: Graph) -> list[Finding]:
    """Validate ``g`` against ``sg`` with pySHACL (imported lazily; required only with shapes)."""
    try:
        from pyshacl import validate  # noqa: PLC0415 -- optional dependency, required only with --shapes.
    except ImportError:
        raise RuntimeError("pySHACL is needed for --shapes: pip install pyshacl") from None
    conforms, report, _ = validate(
        g, shacl_graph=sg, inference="none", advanced=True, meta_shacl=True, abort_on_first=False
    )
    if conforms:
        return []
    if not isinstance(report, Graph):
        raise RuntimeError(f"pySHACL returned an unexpected report type: {type(report).__name__}")
    results: list[Finding] = []
    for result in report.subjects(RDF.type, SH.ValidationResult):
        focus = str(next(report.objects(result, SH.focusNode), "(unknown)"))
        message = "; ".join(map(str, report.objects(result, SH.resultMessage))) or "SHACL constraint violation"
        src = str(next(report.objects(result, SH.sourceShape), "(unknown)"))
        results.append(Finding("SHACL001", "error", focus, f"{message} [shape: {src}]", FIXES["SHACL001"], "certain"))
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
