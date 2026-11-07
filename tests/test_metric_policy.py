"""Validation of the METRIC thresholds on Policy."""

# ruff: noqa: PLR2004

from __future__ import annotations

import math
from typing import Any

import pytest

from ontolint.policy import METRIC_FIELDS, METRIC_QUANTITY_DEFAULTS, METRIC_RATIO_DEFAULTS, Policy


def test_defaults_round_trip_through_from_mapping() -> None:
    assert Policy.from_mapping({}) == Policy()
    assert len(METRIC_FIELDS) == 14
    assert Policy().metric_min_sample == 10


def test_valid_values_are_accepted_and_integers_become_floats() -> None:
    policy = Policy.from_mapping({"metric_max_orphan_ratio": 1, "metric_max_mean_fanout": 3, "metric_max_imports": 0})
    assert policy.metric_max_orphan_ratio == 1.0
    assert isinstance(policy.metric_max_orphan_ratio, float)
    assert policy.metric_max_mean_fanout == 3.0
    assert policy.metric_max_imports == 0


@pytest.mark.parametrize("name", sorted(METRIC_RATIO_DEFAULTS))
@pytest.mark.parametrize("value", [-0.1, 1.1, math.nan, math.inf, True, "0.5", None])
def test_ratios_must_be_within_zero_and_one(name: str, value: Any) -> None:
    with pytest.raises(ValueError, match=name):
        Policy.from_mapping({name: value})


@pytest.mark.parametrize("name", sorted(METRIC_QUANTITY_DEFAULTS))
@pytest.mark.parametrize("value", [-1, math.nan, -math.inf, False, "1"])
def test_quantities_must_be_finite_and_non_negative(name: str, value: Any) -> None:
    with pytest.raises(ValueError, match=name):
        Policy.from_mapping({name: value})


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("metric_min_sample", 0),
        ("metric_min_sample", 1.5),
        ("metric_min_sample", True),
        ("metric_max_imports", -1),
        ("metric_max_imports", 2.0),
        ("metric_max_imports", "3"),
    ],
)
def test_counts_must_be_integers_in_range(name: str, value: Any) -> None:
    with pytest.raises(ValueError, match=name):
        Policy.from_mapping({name: value})
