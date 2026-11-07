"""Properties of Policy and JSON configuration validation."""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, fields
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis_strategies import budget, hostile_mappings, valid_policy_mappings

from ontolint.models import Severity
from ontolint.policy import METRIC_FIELDS, METRIC_QUANTITY_DEFAULTS, METRIC_RATIO_DEFAULTS, Policy

pytestmark = pytest.mark.slow

IRI = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:[^\s<>\"{}|\\^`]+")
INT_FIELDS = ("depth_limit", "inheritance_limit", "soup_limit", "metric_min_sample", "metric_max_imports")


def check_invariants(policy: Policy) -> None:
    """The properties every Policy produced by ``from_mapping`` has."""
    assert policy.base is None or isinstance(policy.base, str)
    assert all(language == language.lower() for language in policy.languages)
    for name in INT_FIELDS + ("max_input_bytes", "max_triples"):
        value = getattr(policy, name)
        assert isinstance(value, int)
        assert not isinstance(value, bool)
    assert policy.metric_min_sample >= 1
    assert policy.metric_max_imports >= 0
    assert policy.max_input_bytes >= 1
    assert policy.max_triples >= 1
    for name in METRIC_FIELDS:
        value = getattr(policy, name)
        if name in ("metric_min_sample", "metric_max_imports"):
            continue
        assert isinstance(value, float)
        assert math.isfinite(value)
        assert value >= 0
        if name in METRIC_RATIO_DEFAULTS:
            assert value <= 1
    for predicates in (policy.extra_definition_predicates, policy.extra_label_predicates):
        assert all(IRI.fullmatch(p) for p in predicates)
        assert len(set(predicates)) == len(predicates)
    assert isinstance(policy.ignored_rules, frozenset)
    assert list(policy.severity_overrides) == sorted(policy.severity_overrides)
    assert {severity for _, severity in policy.severity_overrides} <= {s.value for s in Severity}
    assert policy.severity_mapping == dict(policy.severity_overrides)
    hash(policy)


def to_mapping(policy: Policy) -> dict[str, Any]:
    """Serialise a policy back into the JSON shape ``from_mapping`` reads."""
    data = asdict(policy)
    data["languages"] = list(policy.languages)
    data["ignored_rules"] = sorted(policy.ignored_rules)
    data["severity_overrides"] = dict(policy.severity_overrides)
    data["extra_definition_predicates"] = list(policy.extra_definition_predicates)
    data["extra_label_predicates"] = list(policy.extra_label_predicates)
    data["required_annotations"] = {kind: list(predicates) for kind, predicates in policy.required_annotations}
    data["alignment_namespaces"] = list(policy.alignment_namespaces)
    data.pop("unknown_keys")  # bookkeeping of from_mapping, not a configuration key
    return data


@budget(1)
@given(valid_policy_mappings())
def test_valid_mappings_give_a_policy_satisfying_its_invariants(mapping: dict[str, Any]) -> None:
    """INVARIANT: every valid JSON mapping is accepted, keeps its given values and satisfies the Policy invariants."""
    policy = Policy.from_mapping(mapping)

    check_invariants(policy)
    for name in INT_FIELDS + ("max_input_bytes", "max_triples", "base"):
        if name in mapping:
            assert getattr(policy, name) == mapping[name]
    if "languages" in mapping:
        assert policy.languages == tuple(x.lower() for x in mapping["languages"])
    if "ignored_rules" in mapping:
        assert policy.ignored_rules == frozenset(mapping["ignored_rules"])


@budget(1)
@given(valid_policy_mappings())
def test_policy_round_trips_through_its_mapping_form(mapping: dict[str, Any]) -> None:
    """INVARIANT: from_mapping(to_mapping(p)) == p, also through a JSON text round trip; defaults are a fixed point."""
    policy = Policy.from_mapping(mapping)

    assert Policy.from_mapping(to_mapping(policy)) == policy
    assert Policy.from_mapping(json.loads(json.dumps(to_mapping(policy)))) == policy
    assert Policy.from_mapping({}) == Policy()
    assert Policy.from_mapping(to_mapping(Policy())) == Policy()


@budget(2)
@given(hostile_mappings())
def test_arbitrary_json_values_give_a_policy_or_a_value_error(mapping: dict[str, Any]) -> None:
    """INVARIANT: from_mapping raises ValueError only (never TypeError/KeyError/...) and any result is valid."""
    try:
        policy = Policy.from_mapping(mapping)
    except ValueError:
        return

    check_invariants(policy)


@budget(1)
@given(st.sampled_from(sorted(METRIC_RATIO_DEFAULTS)), st.one_of(st.floats(), st.integers()), st.booleans())
def test_ratio_thresholds_accept_exactly_the_unit_interval(name: str, value: float, as_text: bool) -> None:
    """INVARIANT: a ratio threshold is accepted iff it is a finite real within [0, 1] (text is not)."""
    candidate: Any = str(value) if as_text else value
    valid = not as_text and math.isfinite(value) and 0 <= value <= 1

    if valid:
        assert getattr(Policy.from_mapping({name: candidate}), name) == float(value)
    else:
        with pytest.raises(ValueError):  # noqa: PT011 -- any message is fine, the type is the contract.
            Policy.from_mapping({name: candidate})


@pytest.mark.parametrize("name", [*sorted(METRIC_RATIO_DEFAULTS), *sorted(METRIC_QUANTITY_DEFAULTS)])
@pytest.mark.parametrize("huge", [10**400, -(10**400)])
def test_huge_integer_thresholds_are_rejected_with_a_value_error(name: str, huge: int) -> None:
    """Malformed values must raise ValueError; ``10**400`` does not fit a float (OverflowError inside float())."""
    with pytest.raises(ValueError):  # noqa: PT011
        Policy.from_mapping({name: huge})


@budget(1)
@given(
    st.sampled_from(("depth_limit", "inheritance_limit", "soup_limit", "metric_min_sample", "max_triples")),
    st.integers(),
)
def test_integer_thresholds_enforce_their_lower_bounds(name: str, value: int) -> None:
    """INVARIANT: sample size and loader limits must be >= 1; the other counts accept any integer."""
    minimum = {"metric_min_sample": 1, "max_triples": 1}.get(name)

    if minimum is not None and value < minimum:
        with pytest.raises(ValueError):  # noqa: PT011
            Policy.from_mapping({name: value})
    else:
        assert getattr(Policy.from_mapping({name: value}), name) == value


def test_policy_has_no_field_the_round_trip_test_cannot_reach() -> None:
    """Every Policy field can be written in a mapping, so the round-trip property covers the whole dataclass."""
    assert {f.name for f in fields(Policy)} - {"unknown_keys"} == set(to_mapping(Policy()))
