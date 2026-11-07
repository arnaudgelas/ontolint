"""Cases for SEC007 (``owl:imports`` not followed)."""

from __future__ import annotations

from rule_harness import rule_cases, ttl

ONT = "<https://example.test/onto> a owl:Ontology"

CASES = {
    "SEC007": rule_cases(
        [
            ttl("one IRI import", f"{ONT} ; owl:imports <https://example.test/other> ."),
            ttl("imports declared on a second ontology", f"{ONT} . <https://example.test/b> owl:imports ex:other ."),
            ttl("literal import target", f'{ONT} ; owl:imports "not an iri" .'),
        ],
        [
            ttl("no imports", f"{ONT} ."),
            ttl("import-like predicate only", f"{ONT} ; ex:imports <https://example.test/other> ."),
            ttl("empty graph", ""),
        ],
    ),
}
