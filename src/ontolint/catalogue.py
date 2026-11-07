"""Typed view of the planning catalogue (implemented and proposed rules).

The catalogue records what is *planned* (:class:`CatalogueStatus`); runtime outcomes
(:class:`ExecutionStatus`) are a different concept and live on :class:`RuleExecution`.
The canonical file is ``data/rule_catalogue.csv`` in the repository; an identical copy
ships inside the package so the loader works from an installed wheel (a test enforces
that the two never drift).
"""

from __future__ import annotations

import csv
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
