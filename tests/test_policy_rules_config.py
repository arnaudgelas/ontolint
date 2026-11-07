"""Validation of the policy fields behind GOV016, GOV020, ALIGN012 and ALIGN016."""

# ruff: noqa: PLR2004

from __future__ import annotations

from typing import Any

import pytest

from ontolint.policy import POLICY_VERSION, Policy, PolicyVersionError

P = "http://www.w3.org/2000/01/rdf-schema#comment"
Q = "https://example.org/vocab#note"


def test_defaults_are_off() -> None:
    policy = Policy.from_mapping({})
    assert policy == Policy()
    assert policy.required_annotations == ()
    assert policy.alignment_namespaces == ()
    assert policy.alignment_min_coverage is None
    assert policy.unknown_keys == ()


def test_required_annotations_parse_sort_and_dedupe() -> None:
    policy = Policy.from_mapping({"required_annotations": {"property": [Q], "class": [P, Q, P], "concept": []}})
    assert policy.required_annotations == (("class", (P, Q)), ("property", (Q,)))
    assert isinstance(policy.required_annotations, tuple)
    assert all(isinstance(predicates, tuple) for _kind, predicates in policy.required_annotations)
    hash(policy)  # frozen and hashable


@pytest.mark.parametrize(
    "value",
    [
        [],
        "class",
        1,
        None,
        {"classes": [P]},
        {"Class": [P]},
        {1: [P]},
        {"class": P},
        {"class": [1]},
        {"class": [None]},
        {"class": ["not an iri"]},
        {"class": ["http://x.test/a b"]},
        {"class": [""]},
        {"class": [P, ""]},
        {"class": {"a": 1}},
    ],
)
def test_required_annotations_rejects_hostile_values(value: Any) -> None:
    with pytest.raises(ValueError, match="required_annotations|class"):
        Policy.from_mapping({"required_annotations": value})


def test_required_annotations_survive_huge_input() -> None:
    iris = [f"https://x.test/p{i}" for i in range(2000)]
    policy = Policy.from_mapping({"required_annotations": {"class": iris + iris}})
    assert policy.required_annotations == (("class", tuple(iris)),)


def test_alignment_namespaces() -> None:
    policy = Policy.from_mapping({"alignment_namespaces": ["https://a.test/", "https://b.test/", "https://a.test/"]})
    assert policy.alignment_namespaces == ("https://a.test/", "https://b.test/")


@pytest.mark.parametrize("value", ["https://a.test/", 1, None, ["x"], [1], ["a b:c"], [["https://a.test/"]], {}])
def test_alignment_namespaces_rejects_hostile_values(value: Any) -> None:
    with pytest.raises(ValueError, match="alignment_namespaces"):
        Policy.from_mapping({"alignment_namespaces": value})


@pytest.mark.parametrize(("value", "expected"), [(None, None), (0, 0.0), (1, 1.0), (0.25, 0.25), (1.0, 1.0)])
def test_alignment_min_coverage_accepts_ratios(value: Any, expected: float | None) -> None:
    assert Policy.from_mapping({"alignment_min_coverage": value}).alignment_min_coverage == expected


@pytest.mark.parametrize(
    "value", [-0.01, 1.01, 2, 10**400, -(10**400), float("nan"), float("inf"), True, False, "0.5", [0.5], {}]
)
def test_alignment_min_coverage_rejects_hostile_values(value: Any) -> None:
    with pytest.raises(ValueError, match="alignment_min_coverage"):
        Policy.from_mapping({"alignment_min_coverage": value})


def test_policy_version_current_and_absent_are_accepted() -> None:
    assert POLICY_VERSION == 1
    assert Policy.from_mapping({"policy_version": 1}) == Policy()
    assert Policy.from_mapping({}).unknown_keys == ()


@pytest.mark.parametrize("value", [2, 0, -1, 10**30, True, False, 1.0, "1", None, [1]])
def test_policy_version_rejects_everything_else(value: Any) -> None:
    with pytest.raises(PolicyVersionError):
        Policy.from_mapping({"policy_version": value})


def test_policy_version_error_is_a_value_error_naming_versions() -> None:
    with pytest.raises(ValueError, match="policy_version 2 is not supported .*version 1"):
        Policy.from_mapping({"policy_version": 2})
    with pytest.raises(ValueError, match="policy_version must be an integer"):
        Policy.from_mapping({"policy_version": "1"})


def test_unknown_keys_are_recorded_sorted_and_deduplicated() -> None:
    policy = Policy.from_mapping({"zeta": 1, "alpha": [], "base": None, "policy_version": 1, "metric_min_sample": 3})
    assert policy.unknown_keys == ("alpha", "zeta")


def test_every_documented_key_is_known() -> None:
    data: dict[str, Any] = {
        "base": None,
        "languages": ["en"],
        "depth_limit": 3,
        "inheritance_limit": 3,
        "soup_limit": 3,
        "ignored_rules": [],
        "severity_overrides": {},
        "extra_definition_predicates": [],
        "extra_label_predicates": [],
        "max_input_bytes": 5,
        "max_triples": 5,
        "required_annotations": {},
        "alignment_namespaces": [],
        "alignment_min_coverage": None,
        "policy_version": 1,
    }
    assert Policy.from_mapping(data).unknown_keys == ()


def test_unknown_key_cannot_set_the_bookkeeping_field() -> None:
    assert Policy.from_mapping({"unknown_keys": ["x"]}).unknown_keys == ("unknown_keys",)


def test_huge_unknown_key_is_kept_verbatim() -> None:
    key = "k" * 100_000
    assert Policy.from_mapping({key: 1}).unknown_keys == (key,)
