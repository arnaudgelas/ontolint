"""Named rule profiles, expressed as pure data.

A profile bundles a rule selection, optional ignores, severity overrides and a default
``--fail-on`` threshold.  Selectors are rule identifiers or family prefixes, exactly as
accepted by ``--select``; an empty ``select`` means every *default* rule, that is every rule outside
the opt-in families.  Profiles hold no logic: :mod:`ontolint.selection` composes them with
``--select``/``--ignore`` and the policy file.
"""

from __future__ import annotations

from dataclasses import dataclass

# Rule families that never run unless asked for: by ``--select`` (family or rule id) or by a profile's
# ``opt_in``.  They encode conventions that only make sense for some ontologies (here: OBO Foundry
# ontologies), so the default selection, ``recommended``, ``ci``, ``strict`` and ``minimal`` skip them.
OPT_IN_FAMILIES: frozenset[str] = frozenset({"OBO"})


def is_opt_in(family: str) -> bool:
    """Whether ``family`` (any case) is an opt-in rule family."""
    return family.upper() in OPT_IN_FAMILIES


@dataclass(frozen=True)
class Profile:
    """A documented, immutable bundle of defaults."""

    name: str
    description: str
    select: tuple[str, ...] = ()
    ignore: tuple[str, ...] = ()
    opt_in: tuple[str, ...] = ()  # Opt-in families added to the default selection (ignored by --select).
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
            "obo",
            "Every default rule plus the opt-in OBO Foundry convention rules (OBO); gate on warnings.",
            opt_in=("OBO",),
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
