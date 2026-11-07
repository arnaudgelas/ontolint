"""Cases for the policy-driven rules GOV016, GOV020, ALIGN012 and ALIGN016.

Each rule needs a policy field, passed through ``policy=`` (``Linter(policy=...)``).
"""

# ruff: noqa: PLR2004

from __future__ import annotations

from rule_harness import rule_cases, ttl

from ontolint.policy import Policy

LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
COMMENT = "http://www.w3.org/2000/01/rdf-schema#comment"
PREF = "http://www.w3.org/2004/02/skos/core#prefLabel"
NS = ("https://ref.test/a#", "https://ref.test/b/")


def _required(**kinds: list[str]) -> Policy:
    return Policy.from_mapping({"required_annotations": kinds})


def _coverage(total: int, mapped: int, **extra: object) -> str:
    lines = [f"ex:C{i} a owl:Class ." for i in range(total)]
    lines += [f"ex:C{i} skos:exactMatch <https://ref.test/a#C{i}> ." for i in range(mapped)]
    return "\n".join(lines) + "\n" + "\n".join(f"{k} {v} ." for k, v in extra.items())


def _cov_policy(ratio: float, sample: int = 10) -> Policy:
    return Policy(alignment_min_coverage=ratio, metric_min_sample=sample)


CASES = {
    "GOV016": rule_cases(
        [
            ttl(
                "class without comment", 'ex:A a owl:Class ; rdfs:label "A" .', policy=_required(**{"class": [COMMENT]})
            ),
            ttl("blank literal", 'ex:A a owl:Class ; rdfs:comment "  " .', policy=_required(**{"class": [COMMENT]})),
            ttl("blank node value", "ex:A a owl:Class ; rdfs:comment [] .", policy=_required(**{"class": [COMMENT]})),
            ttl("property", "ex:p a owl:ObjectProperty .", policy=_required(property=[LABEL])),
            ttl("concept", "ex:c a skos:Concept .", policy=_required(concept=[PREF])),
            ttl("individual", "ex:i a owl:NamedIndividual .", policy=_required(individual=[LABEL])),
            ttl(
                "one of two predicates missing",
                'ex:A a owl:Class ; rdfs:label "A" .',
                policy=_required(**{"class": [LABEL, COMMENT]}),
            ),
        ],
        [
            ttl("silent without policy", "ex:A a owl:Class ."),
            ttl("satisfied", 'ex:A a owl:Class ; rdfs:comment "d" .', policy=_required(**{"class": [COMMENT]})),
            ttl("iri value counts", "ex:A a owl:Class ; rdfs:comment ex:B .", policy=_required(**{"class": [COMMENT]})),
            ttl(
                "deprecated skipped",
                "ex:A a owl:Class ; owl:deprecated true .",
                policy=_required(**{"class": [COMMENT]}),
            ),
            ttl("other kind not required", "ex:p a owl:ObjectProperty .", policy=_required(**{"class": [COMMENT]})),
            ttl(
                "foreign term not owned",
                "<https://other.test/x#A> a owl:Class . ex:o a owl:Ontology . ex:B a owl:Class ; rdfs:comment 'x' .",
                policy=_required(**{"class": [COMMENT]}),
                base="https://example.test/onto#",
            ),
        ],
    ),
    "GOV020": rule_cases(
        [
            ttl("one unknown key", "ex:A a owl:Class .", policy=Policy.from_mapping({"bogus": 1})),
            ttl("misspelt key", "", policy=Policy.from_mapping({"depth_limt": 3})),
        ],
        [
            ttl("silent without policy", "ex:A a owl:Class ."),
            ttl(
                "known keys only", "ex:A a owl:Class .", policy=Policy.from_mapping({"policy_version": 1, "base": None})
            ),
        ],
    ),
    "ALIGN012": rule_cases(
        [
            ttl(
                "exactMatch outside",
                "ex:A a owl:Class ; skos:exactMatch <https://elsewhere.test/A> .",
                policy=Policy(alignment_namespaces=NS),
            ),
            ttl(
                "equivalentClass outside",
                "ex:A a owl:Class ; owl:equivalentClass <https://elsewhere.test/A> .",
                policy=Policy(alignment_namespaces=NS),
            ),
            ttl(
                "sameAs outside on an individual",
                "ex:i a owl:NamedIndividual ; owl:sameAs <https://elsewhere.test/i> .",
                policy=Policy(alignment_namespaces=NS),
            ),
            ttl(
                "one of two targets outside",
                "ex:A a owl:Class ; skos:closeMatch <https://ref.test/a#A>, <https://elsewhere.test/A> .",
                policy=Policy(alignment_namespaces=NS),
            ),
        ],
        [
            ttl("silent without policy", "ex:A a owl:Class ; skos:exactMatch <https://elsewhere.test/A> ."),
            ttl(
                "inside first namespace",
                "ex:A a owl:Class ; skos:exactMatch <https://ref.test/a#A> .",
                policy=Policy(alignment_namespaces=NS),
            ),
            ttl(
                "inside second namespace",
                "ex:A a owl:Class ; owl:equivalentClass <https://ref.test/b/A> .",
                policy=Policy(alignment_namespaces=NS),
            ),
            ttl(
                "non-mapping predicate ignored",
                "ex:A a owl:Class ; rdfs:seeAlso <https://elsewhere.test/A> .",
                policy=Policy(alignment_namespaces=NS),
            ),
            ttl(
                "literal target ignored",
                'ex:A a owl:Class ; skos:exactMatch "x" .',
                policy=Policy(alignment_namespaces=NS),
            ),
            ttl(
                "undeclared subject ignored",
                "ex:U skos:exactMatch <https://elsewhere.test/A> . ex:A a owl:Class .",
                policy=Policy(alignment_namespaces=NS),
            ),
        ],
    ),
    "ALIGN016": rule_cases(
        [
            ttl("1 of 10 mapped", _coverage(10, 1), policy=_cov_policy(0.5)),
            ttl("none mapped", _coverage(10, 0), policy=_cov_policy(0.1)),
            ttl("just below ratio", _coverage(10, 4), policy=_cov_policy(0.5)),
            ttl("below sample of 1", _coverage(1, 0), policy=_cov_policy(0.5, 1)),
            ttl(
                "self mapping does not count",
                "ex:A a owl:Class ; owl:equivalentClass ex:A .",
                policy=_cov_policy(0.5, 1),
            ),
            ttl(
                "properties count in population",
                "ex:A a owl:Class ; skos:exactMatch <https://r.test/A> . ex:p a owl:ObjectProperty .",
                policy=_cov_policy(0.9, 2),
            ),
        ],
        [
            ttl("silent without policy", _coverage(10, 0)),
            ttl("exactly at ratio", _coverage(10, 5), policy=_cov_policy(0.5)),
            ttl("above ratio", _coverage(10, 9), policy=_cov_policy(0.5)),
            ttl("sample not met", _coverage(9, 0), policy=_cov_policy(0.5)),
            ttl("ratio zero never fires", _coverage(10, 0), policy=_cov_policy(0.0)),
            ttl(
                "deprecated terms skipped",
                _coverage(10, 0) + "\n" + "\n".join(f"ex:C{i} owl:deprecated true ." for i in range(10)),
                policy=_cov_policy(0.5, 1),
            ),
            ttl(
                "property mapping counts",
                "ex:A a owl:Class ; skos:exactMatch <https://r.test/A> . ex:p a owl:ObjectProperty ;"
                " owl:equivalentProperty <https://r.test/p> .",
                policy=_cov_policy(1.0, 2),
            ),
        ],
    ),
}
