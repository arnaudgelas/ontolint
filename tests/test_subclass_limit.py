"""CLS011's direct-subclass threshold is configurable as ``subclass_limit`` (policy) or ``--subclass-limit``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ontolint.cli import main
from ontolint.policy import DEFAULT_SUBCLASS_LIMIT, Policy

OWL_CLASS = "<http://www.w3.org/2002/07/owl#Class>"
SUBCLASS_OF = "<http://www.w3.org/2000/01/rdf-schema#subClassOf>"
FOUR_KIDS = f"<https://example.test/P> a {OWL_CLASS} .\n" + "".join(
    f"<https://example.test/K{i}> a {OWL_CLASS} ; {SUBCLASS_OF} <https://example.test/P> .\n" for i in range(4)
)


def _cls011(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], *argv: str, policy: dict[str, object] | None = None
) -> list[str]:
    source = tmp_path / "a.ttl"
    source.write_text(FOUR_KIDS, encoding="utf-8")
    args = [str(source), "--select", "CLS011", "--format", "json", "--fail-on", "never", *argv]
    if policy is not None:
        config = tmp_path / "policy.json"
        config.write_text(json.dumps({"policy_version": 1, **policy}), encoding="utf-8")
        args += ["--config", str(config)]
    assert main(args) == 0
    return [f["message"] for f in json.loads(capsys.readouterr().out)["findings"]]


def test_the_default_limit_is_fifty() -> None:
    assert Policy().subclass_limit == DEFAULT_SUBCLASS_LIMIT == 50  # noqa: PLR2004


def test_the_policy_key_sets_the_limit(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _cls011(tmp_path, capsys) == []
    assert _cls011(tmp_path, capsys, policy={"subclass_limit": 3}) == ["4 direct subclasses (threshold 3)."]


def test_the_command_line_flag_wins_over_the_policy(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _cls011(tmp_path, capsys, "--subclass-limit", "4", policy={"subclass_limit": 3}) == []


@pytest.mark.parametrize("value", ["3", 2.5, True])
def test_a_non_integer_limit_is_rejected(value: object) -> None:
    with pytest.raises(ValueError, match="policy thresholds must be integers"):
        Policy.from_mapping({"subclass_limit": value})
