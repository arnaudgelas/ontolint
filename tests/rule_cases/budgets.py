"""Cases for METRIC014, the breach of a ``quality_budgets`` bound.

A bound is inclusive, so each bound has an at-limit negative; there is no sample gate, so a small population has a
positive; an empty one has none.
"""

# ruff: noqa: PLR2004

from __future__ import annotations

from rule_harness import rule_cases, ttl

from ontolint.policy import Policy

LABELLED = 'rdfs:label "c"@en'


def _budgets(**named: dict[str, float]) -> Policy:
    return Policy.from_mapping({"quality_budgets": named})


def _imports(n: int) -> str:
    return "ex:o a owl:Ontology ; owl:imports " + ", ".join(f"<https://o{i}.test/>" for i in range(n)) + " ."


def _labelled(total: int, labelled: int) -> str:
    return "\n".join(f"ex:C{i} a owl:Class {'; ' + LABELLED if i < labelled else ''} ." for i in range(total))


CASES = {
    "METRIC014": rule_cases(
        [
            ttl("2 imports over a maximum of 1", _imports(2), policy=_budgets(unresolved_imports={"maximum": 1})),
            ttl("1 import under a minimum of 2", _imports(1), policy=_budgets(unresolved_imports={"minimum": 2})),
            ttl(
                "4 of 10 classes labelled under a minimum of 0.5",
                _labelled(10, 4),
                policy=_budgets(class_label_coverage={"minimum": 0.5}),
            ),
            ttl(
                "10 of 10 classes orphans over a maximum of 0.5",
                _labelled(10, 4),
                policy=_budgets(orphan_classes={"maximum": 0.5}),
            ),
            ttl(
                "one class below the sample size of the METRIC rules",
                _labelled(1, 0),
                policy=_budgets(class_label_coverage={"minimum": 1}),
            ),
        ],
        [
            ttl("no budget", _imports(2)),
            ttl("2 imports at a maximum of 2", _imports(2), policy=_budgets(unresolved_imports={"maximum": 2})),
            ttl("2 imports at a minimum of 2", _imports(2), policy=_budgets(unresolved_imports={"minimum": 2})),
            ttl(
                "5 of 10 classes labelled at a minimum of 0.5",
                _labelled(10, 5),
                policy=_budgets(class_label_coverage={"minimum": 0.5}),
            ),
            ttl(
                "within both bounds",
                _labelled(10, 5),
                policy=_budgets(class_label_coverage={"minimum": 0.1, "maximum": 0.9}),
            ),
            ttl("no class: a ratio over nothing", "", policy=_budgets(class_label_coverage={"minimum": 1})),
        ],
    ),
}
