"""Specifications for the safe-loader rules, emitted by the CLI front end while it reads input.

``SEC001``..``SEC013`` here are raised by :mod:`ontolint.loader` (``module=""``): no graph exists yet when
they apply, so there is no ``run(ctx)``.  The CLI prints them like ``INPUT001`` and exits with code 2.
``SEC003`` (parse time budget) is raised when ``--max-parse-seconds`` / ``max_parse_seconds`` is set: the parse then
runs in a killable worker process.  ``SEC007`` (``owl:imports`` not followed) is a graph rule in
:mod:`ontolint.rules.imports_note`.
"""

from __future__ import annotations

from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity


def _spec(rule_id: str, title: str, suggestion: str) -> RuleSpec:
    return RuleSpec(
        rule_id, "SEC", title, Severity.ERROR, suggestion, "deterministic", RuleBackend.CLI, RuleScope.INPUT, ""
    )


SPECS: tuple[RuleSpec, ...] = (
    _spec(
        "SEC001",
        "Input file exceeds the size limit",
        "Split the ontology, or raise --max-input-bytes (or max_input_bytes in the policy) if the size is expected.",
    ),
    _spec(
        "SEC002",
        "Input exceeds the triple limit",
        "Lint a smaller module, or raise --max-triples (or max_triples in the policy) if the size is expected.",
    ),
    _spec(
        "SEC003",
        "Parsing exceeds the time budget",
        "Lint a smaller module, or raise --max-parse-seconds (or max_parse_seconds in the policy) if it is expected.",
    ),
    _spec(
        "SEC006",
        "Remote JSON-LD context refused",
        "Inline the @context in the document; ontolint never downloads contexts.",
    ),
    _spec(
        "SEC009",
        "Unsafe input path",
        "Pass a regular file inside the working directory, not a device, a '..' escape or a link leaving it.",
    ),
    _spec(
        "SEC010",
        "RDF/XML unsafe DTD or entity refused",
        "Remove SYSTEM/PUBLIC identifiers and nested entities; plain internal entities (Protege style) are accepted.",
    ),
    _spec(
        "SEC011",
        "Compressed input refused",
        "Decompress the file yourself and pass the plain RDF serialization.",
    ),
    _spec(
        "SEC013",
        "Network access attempted while disabled",
        "Make the input self-contained; ontolint runs with the network disabled and never fetches resources.",
    ),
)
