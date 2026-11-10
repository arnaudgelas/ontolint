"""Specifications for rules that are not run by a graph rule module.

SHACL001 and SEM001 are produced by adapters (pySHACL, ROBOT) and INPUT001/TOOL001 by the CLI
front end.  They carry ``module=""`` because no ``run(ctx)`` function emits them.

SHACL001 and SEM001 are findings: they appear in the report, gate the exit code through ``--fail-on`` (``1``),
and obey ``--select``/``--ignore``, baselines and ``severity_overrides``.  INPUT001 and TOOL001 are diagnostics
printed on stderr as ``<ID>: <message>`` with exit code ``2``; the selection never affects them.

* **SHACL001.** Only with ``--shapes FILE`` (the shapes file passes the safe loader) and pySHACL installed
  (``unsupported`` otherwise, which exits ``2``).  The data graph (merged, with ``--follow-imports``, with the
  ontology the shapes import, keeping only results whose focus the linted file mentions, as a subject or an
  object) is validated with
  ``inference="none"``, ``advanced=True``, ``meta_shacl=True``.  One finding per ``sh:ValidationResult``, focused on
  its ``sh:focusNode`` (a blank node by its content-stable id), with the result messages joined by ``; `` and
  ``[shape: <source shape>]``.  The severity is the result's: ``sh:Violation`` error, ``sh:Warning`` warning,
  ``sh:Info`` info, any other value error with ``(severity <value>)`` appended; the spec's ``error`` is only the
  default shown in rule listings.  Each finding's ``evidence`` (JSON ``evidence``, SARIF ``properties.evidence``,
  never text) holds every property of its result under its SHACL name, in this order and only when present:
  ``focusNode``, ``resultPath``, ``value``, ``sourceShape``, ``sourceConstraintComponent``, ``sourceConstraint``,
  ``detail``, ``resultMessage`` (sorted, without language tags), ``resultSeverity`` (the original IRI).  IRIs are
  plain, blank nodes the content-stable ``_:`` id (data terms in the data graph, shapes terms in the shapes graph),
  literals one-line N-Triples, a complex path SPARQL 1.1 property-path syntax, or ``(malformed path)`` when it
  does not parse or exceeds 32 levels or 1,000 nodes; ``detail`` nests the ``sh:detail`` results, sorted, at most
  8 deep, never around a cycle, and each of them is also a finding of its own.  Findings tied on focus and message
  are ordered by their evidence, since pySHACL's result order depends on the hash seed.  The evidence is not part
  of the finding's identity: messages and fingerprints are unchanged.  A non-conforming report without result
  nodes gives one error on ``(shapes)``, without evidence.  A shapes graph refused by the pre-check
  (unserialisable IRI, cyclic, shared or overlong ``rdf:list``) or a pySHACL crash makes the rule ``failed`` (no
  finding, TOOL001 line, exit ``2``).  Confidence ``certain``: the verdict is pySHACL's, on the user's own shapes.
  Why error: a violated shape is a contract the user wrote; a shape that means less says so with ``sh:severity``.
* **INPUT001.** An ontology argument or the ``--shapes`` file cannot be read as RDF: the file is missing or
  unreadable, is a directory, is written in a non-RDF OWL syntax (Functional, Manchester, OWL/XML) without
  ``--convert-with-robot`` (``UnsupportedSyntax``; the message names the flag and suggests ``robot convert``) or
  with it and ROBOT cannot convert it (``ConversionFailed``: no Docker, a timeout, ROBOT's first error line, and
  for Manchester Syntax the reminder that every entity must be declared in the file), or the parser raised (any
  exception, including recursion and memory exhaustion, and a parse worker that did not start or died).  So is
  a file of an ``owl:imports`` closure.  The message is ``INPUT001: RDF input parsing failed[ for <file>]:
  <ExceptionType>: <parser message>``, with a hint when the file holds an HTML page; it quotes the parser's or
  the operating system's message (which may hold a fragment of the input or the file's path), nothing else.  As
  for the SEC rules, every argument is attempted, then the run stops with no report and exit ``2``.  Why error:
  nothing can be linted.
* **TOOL001.** The linter could not do what was asked: an unknown ``--explain`` rule, an unknown ``--select`` or
  ``--ignore`` selector (the message suggests the closest valid identifiers), a selector syntax error, an
  unreadable or invalid policy file or catalog, or any other exception raised while configuring
  (``TOOL001: configuration failed: ...``) or while linting (``TOOL001: lint execution failed: ...``, for example
  an unwritable ``--write-baseline``); these exit ``2`` with no report.  A selected rule whose module or adapter
  raised (``failed``) or whose backend is missing (``unsupported``) is listed in the report, which is still
  written, and then printed as ``TOOL001: rule <ID> <status> for <file>: <detail>``; the exit code is ``2`` even
  with ``--fail-on never``.  Policy files with an unknown rule or ``policy_version`` are GOV020, not TOOL001.
  Why error: the run cannot vouch for a result.
* **SEM001.** Only with ``--owl-profile EL|QL|RL|DL|Full`` and ``docker`` on ``PATH`` (``unsupported``
  otherwise).  For each ontology argument, the original file (not an ``owl:imports`` closure) is run through
  ``robot validate-profile`` in ``--robot-image`` (default ``ontolint-robot:1.9.11``), with ``--network none``,
  its directory mounted read-only, 2 GB memory, 256 processes, 2 CPUs, no capabilities and ``--robot-timeout``
  seconds (default 120).  Exit ``0`` is no finding.  Any other exit with a profile report that lists
  violations gives exactly one finding focused on ``(ontology)`` (the report path names the file): the
  message groups the violations by kind and subject (at most 10 kinds, 5 subjects each) and the full report
  goes in ``details``.  Any other exit without such a list (a missing image, a Docker, Java or permission
  error) is no verdict on the ontology: the rule is ``failed`` with ROBOT's output quoted up to 500 characters
  (TOOL001, exit ``2``), as are a timeout and a failure to start ``docker``.
  Confidence ``certain``: the verdict is the OWL API's.  Why error: the user asked for this profile explicitly,
  and an ontology outside it cannot be relied on by the tools and reasoners built for that profile.
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
