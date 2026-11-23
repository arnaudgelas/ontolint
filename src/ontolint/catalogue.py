"""Typed view of the planning catalogue (implemented and proposed rules).

The catalogue records what is *planned* (:class:`CatalogueStatus`); runtime outcomes
(:class:`ExecutionStatus`) are a different concept and live on :class:`RuleExecution`.
The canonical file is ``data/rule_catalogue.csv`` in the repository; an identical copy
ships inside the package so the loader works from an installed wheel (a test enforces
that the two never drift).
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import cache
from importlib import resources

from .models import CatalogueStatus, RuleBackend

# Backends of implemented rules; planned rules use free-text backends and map to ``None``.
# Graph-algorithm rules (hierarchy metrics) and shapes-graph authoring rules run in-process on
# RDFLib graphs, so they map to the RDFLIB backend even though the catalogue prose is more specific.
# Mixed backends of still-proposed rows (for example "RDFLib graph or OWL profile backend") stay
# unmapped until a row is implemented and its actual backend is known.
BACKEND_IDS: dict[str, RuleBackend] = {
    "RDFLib graph": RuleBackend.RDFLIB,
    "RDFLib graph algorithms": RuleBackend.RDFLIB,
    "pySHACL and RDFLib graph": RuleBackend.RDFLIB,
    "pySHACL": RuleBackend.PYSHACL,
    "ROBOT Docker backend": RuleBackend.ROBOT_DOCKER,
    "CLI": RuleBackend.CLI,
}


@dataclass(frozen=True)
class CatalogueRow:
    """One catalogue entry."""

    rule_id: str
    family: str
    title: str
    status: CatalogueStatus
    category: str
    backend: str
    test_requirement: str

    @property
    def backend_id(self) -> RuleBackend | None:
        """The stable backend identifier, or ``None`` for a planned, unmapped backend."""
        return BACKEND_IDS.get(self.backend)


@cache
def load_catalogue() -> tuple[CatalogueRow, ...]:
    """Load every catalogue row in file order from the packaged CSV."""
    text = resources.files("ontolint").joinpath("data/rule_catalogue.csv").read_text(encoding="utf-8")
    return tuple(
        CatalogueRow(
            rule_id=row["rule_id"],
            family=row["family"],
            title=row["title"],
            status=CatalogueStatus(row["status"]),
            category=row["category"],
            backend=row["backend"],
            test_requirement=row["test_requirement"],
        )
        for row in csv.DictReader(text.splitlines())
    )


def implemented_rows() -> tuple[CatalogueRow, ...]:
    """Rows whose rules ship in the built-in registry."""
    return tuple(row for row in load_catalogue() if row.status is CatalogueStatus.IMPLEMENTED)


def planned_rows() -> tuple[CatalogueRow, ...]:
    """Rows that are proposed but not yet implemented."""
    return tuple(row for row in load_catalogue() if row.status is not CatalogueStatus.IMPLEMENTED)


CATALOGUE_COLUMNS = ("rule_id", "family", "title", "status", "category", "backend", "test_requirement")
"""The columns of the catalogue, in file order: the fields of a row in :func:`canonical_catalogue`."""


def _packaged_rows() -> list[dict[str, str]]:
    text = resources.files("ontolint").joinpath("data/rule_catalogue.csv").read_text(encoding="utf-8")
    return list(csv.DictReader(text.splitlines()))


def canonical_catalogue(rows: Iterable[Mapping[str, str]] | None = None) -> bytes:
    """The canonical text of the catalogue, whose hash identifies the rule set of a report (issue #173).

    One line per row, the rows sorted by rule id (then by their fields), each line the JSON array of the row's
    :data:`CATALOGUE_COLUMNS` (a missing column is the empty string) written without spaces and with the characters
    of the text kept as they are, the lines ending in ``\n``, the whole encoded as UTF-8.  The order of the rows in
    the file, the quoting and the line endings of the CSV, and the ontolint version do not matter; any field of any
    row does, and so does a row added or removed.  ``rows`` defaults to the packaged ``rule_catalogue.csv``.
    """
    lines = sorted(
        [row.get(column, "") for column in CATALOGUE_COLUMNS] for row in (_packaged_rows() if rows is None else rows)
    )
    return "".join(json.dumps(line, ensure_ascii=False, separators=(",", ":")) + "\n" for line in lines).encode("utf-8")


def catalogue_sha256(rows: Iterable[Mapping[str, str]] | None = None) -> str:
    """The sha256, in lower-case hexadecimal, of :func:`canonical_catalogue`."""
    return hashlib.sha256(canonical_catalogue(rows)).hexdigest()
