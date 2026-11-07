"""Named rule profiles, expressed as pure data.

A profile bundles a rule selection, optional ignores, severity overrides and a default
``--fail-on`` threshold.  Selectors are rule identifiers or family prefixes, exactly as
accepted by ``--select``; an empty ``select`` means every rule.  Profiles hold no logic:
:mod:`ontolint.selection` composes them with ``--select``/``--ignore`` and the policy file.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    """A documented, immutable bundle of defaults."""

    name: str
    description: str
    select: tuple[str, ...] = ()
    ignore: tuple[str, ...] = ()
    severity_overrides: tuple[tuple[str, str], ...] = ()
    fail_on: str = "error"


PROFILES: dict[str, Profile] = {
    p.name: p
    for p in (
        Profile(
            "minimal",
            "Structural integrity only: ontology metadata, IRIs, data typing, SKOS, SHACL and OWL-profile results.",
            select=("ONT", "IRI", "DATA", "SKOS", "SHACL", "SEM"),
        ),
        Profile(
            "recommended",
            "Every rule at its default severity; gate on errors. Equivalent to running without a profile.",
        ),
        Profile(
            "ci",
            "Every rule at its default severity; gate on warnings so CI fails on anything above informational.",
            fail_on="warning",
        ),
        Profile(
            "strict",
            "Every rule; a missing license is an error and any finding at all fails the run.",
            severity_overrides=(("ONT003", "error"),),
            fail_on="info",
        ),
    )
}
