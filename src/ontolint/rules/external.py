"""Specifications for rules that are not run by a graph rule module.

SHACL001 and SEM001 are produced by adapters (pySHACL, ROBOT) and INPUT001/TOOL001 by the CLI
front end.  They carry ``module=""`` because no ``run(ctx)`` function emits them.
"""

from __future__ import annotations

from ontolint.models import Requirement, RuleBackend, RuleScope, RuleSpec, Severity

SPECS: tuple[RuleSpec, ...] = (
    RuleSpec(
        "SHACL001",
        "SHACL",
        "SHACL validation violation",
        Severity.ERROR,
        "Fix the supplied SHACL shapes or data, and inspect the SHACL report.",
        "deterministic",
        RuleBackend.PYSHACL,
        RuleScope.SHAPES,
        "",
        Requirement.SHAPES,
    ),
    RuleSpec(
        "INPUT001",
        "INPUT",
        "RDF input could not be parsed",
        Severity.ERROR,
        "Fix RDF syntax or explicitly choose the input serialization format.",
        "deterministic",
        RuleBackend.CLI,
        RuleScope.INPUT,
        "",
    ),
    RuleSpec(
        "TOOL001",
        "TOOL",
        "Linter tool or configuration failure",
        Severity.ERROR,
        "Correct the configuration or execution error and run the linter again.",
        "deterministic",
        RuleBackend.CLI,
        RuleScope.TOOL,
        "",
    ),
    RuleSpec(
        "SEM001",
        "SEM",
        "OWL profile violation reported by ROBOT",
        Severity.ERROR,
        "Correct the reported OWL profile violations, or select the intended OWL profile.",
        "deterministic",
        RuleBackend.ROBOT_DOCKER,
        RuleScope.ONTOLOGY,
        "",
        Requirement.OWL_PROFILE,
    ),
)
