"""A baseline whose identity map is malformed is refused with a message naming the report path."""

from __future__ import annotations

import json

import pytest

from ontolint import baseline

HASH = "a" * 64


def _text(pairs: object) -> str:
    return json.dumps({"version": 2, "files": ["a.ttl"], "fingerprints": [HASH], "identities": {"a.ttl": pairs}})


@pytest.mark.parametrize(
    "pairs",
    [
        ["not", "a", "mapping"],
        {"short": HASH},  # the identity is not 64 hex digits
        {HASH: "short"},  # the fingerprint is not 64 hex digits
        {HASH: 7},  # the fingerprint is not a string
    ],
)
def test_bad_identities_are_refused(pairs: object) -> None:
    with pytest.raises(baseline.BaselineError) as info:
        baseline.loads(_text(pairs))

    assert str(info.value) == "identities['a.ttl'] must map 64-digit hex identities to fingerprints"


def test_well_formed_identities_are_kept() -> None:
    assert baseline.loads(_text({HASH: HASH})).identities == {"a.ttl": {HASH: HASH}}
