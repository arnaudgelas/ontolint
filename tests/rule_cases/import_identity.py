"""Cases for ONT009: the imports a catalog maps to a file that does not declare them (``Policy.import_mismatches``).

The closure finds them (:mod:`ontolint.imports`); here they are given directly, the way the CLI hands them to the
linted file.  :mod:`tests.test_import_identity` reads them from files.
"""

from __future__ import annotations

from rule_harness import Case, rule_cases, ttl

from ontolint.models import ImportMismatch
from ontolint.policy import Policy

ONTOLOGY = "https://example.test/onto"
LIB = "https://example.test/lib"
OTHER = "https://example.test/other"
HEADER = f"<{ONTOLOGY}> a owl:Ontology ; owl:imports <{LIB}> .\n"


def case(name: str, *mismatches: ImportMismatch) -> Case:
    return ttl(name, HEADER, policy=Policy(import_mismatches=mismatches))


CASES = {
    "ONT009": rule_cases(
        [
            case("a file declaring another ontology", ImportMismatch(LIB, "wrong.ttl", ((OTHER, ()),))),
            case(
                "a file declaring another ontology and its version",
                ImportMismatch(LIB, "wrong.ttl", ((OTHER, (f"{OTHER}/1",)),)),
            ),
            case("a file declaring no ontology", ImportMismatch(LIB, "wrong.ttl", ())),
            case(
                "a file declaring several ontologies",
                ImportMismatch(
                    LIB, "wrong.ttl", ((f"{OTHER}/a", ()), (f"{OTHER}/b", (f"{OTHER}/b/1", f"{OTHER}/b/2")))
                ),
            ),
            case(
                "two imports",
                ImportMismatch(LIB, "wrong.ttl", ()),
                ImportMismatch(f"{LIB}2", "wrong2.ttl", ((OTHER, ()),)),
            ),
        ],
        [case("nothing mismatched")],
    ),
}
