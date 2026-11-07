"""Scanner helpers of the safe loader and the file suffix of input rejections (written to kill mutants)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ontolint import cli
from ontolint.loader import InputRejected, dtd_problem
from ontolint.paths import InputFile


def test_text_after_the_doctype_is_not_scanned_for_external_ids() -> None:
    data = b'<!DOCTYPE r [<!ENTITY a "x">]><r>SYSTEM PUBLIC</r>'
    assert dtd_problem(data, 100) is None


def test_unterminated_doctype_does_not_count_following_entity_uses() -> None:
    data = b'<!DOCTYPE r [<!ENTITY a "0123456789"> &a;&a;'
    assert dtd_problem(data, 15) is None


def test_unterminated_entity_value_is_scanned_up_to_the_end() -> None:
    data = b'<!DOCTYPE r [<!ENTITY a "&b;'
    assert dtd_problem(data, 100) == "declares entity 'a' that references another entity"


def test_terminated_entity_value_stops_at_its_closing_quote() -> None:
    assert dtd_problem(b'<!DOCTYPE r [<!ENTITY a "x"> <!ENTITY b "&c;">]><r/>', 100) is not None
    assert dtd_problem(b"<!DOCTYPE r [<!ENTITY a 'x'> <!-- &c; -->]><r/>", 100) is None


def _item(tmp_path: Path, name: str) -> InputFile:
    path = tmp_path / name
    path.write_text("", encoding="utf-8")
    return InputFile(path, name, name)


def _reject(message: str) -> object:
    def load(item: InputFile, policy: object) -> None:  # noqa: ARG001
        raise InputRejected("SEC002", message)

    return load


def test_rejection_without_file_name_gets_suffix_only_for_multiple_inputs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli, "load_graph", _reject("graph too big"))
    one, two = _item(tmp_path, "one.ttl"), _item(tmp_path, "two.ttl")
    assert cli._parse_inputs([one])[1] == ["SEC002: graph too big"]  # noqa: SLF001
    assert cli._parse_inputs([one, two])[1] == [  # noqa: SLF001
        "SEC002: graph too big for one.ttl",
        "SEC002: graph too big for two.ttl",
    ]


def test_rejection_naming_the_file_is_not_suffixed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli, "load_graph", _reject("one.ttl is bad"))
    one, two = _item(tmp_path, "one.ttl"), _item(tmp_path, "two.ttl")
    assert cli._parse_inputs([one, two])[1][0] == "SEC002: one.ttl is bad"  # noqa: SLF001
