"""Rule selection: how ``--profile``, ``--select``, ``--ignore`` and the policy file combine.

Precedence, from the broadest to the strongest word:

1. The chosen set is ``--select`` when given, otherwise the profile's selection, otherwise every rule.
   An explicit ``--select`` *replaces* the profile's selection (it does not add to it).
2. Ignores always win: ``--ignore``, the profile's ``ignore`` and the policy file's ``ignored_rules``
   are unioned and removed from the chosen set, whatever selected the rule.
3. Severity overrides apply to what remains: profile first, then the policy file (policy wins).
   Selectors are validated strictly (typos are errors, never an empty run); the policy file's
   ``ignored_rules`` keep their historical exact-identifier, unvalidated behaviour.

Rules emitted only by the command-line front end (``INPUT001``/``TOOL001``) are not engine rules,
so they are never part of a selection or of the reported executions.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .models import RuleBackend, RuleSpec
from .profiles import Profile
from .rules.registry import RuleRegistry, UnknownSelectorError


class SelectorSyntaxError(ValueError):
    """Raised for malformed selector lists such as an empty entry."""


def split_selectors(values: Sequence[str]) -> tuple[str, ...]:
    """Flatten repeatable, comma-separated selector arguments, upper-cased and de-duplicated in order."""
    tokens: dict[str, None] = {}
    for value in values:
        for part in value.split(","):
            token = part.strip().upper()
            if not token:
                raise SelectorSyntaxError(f"empty rule selector in {value!r}")
            tokens[token] = None
    return tuple(tokens)


@dataclass(frozen=True)
class Selection:
    """The outcome of composing selectors: what runs and what was explicitly ignored."""

    run: tuple[RuleSpec, ...]
    ignored: tuple[RuleSpec, ...]


def _engine_rules(specs: Sequence[RuleSpec]) -> tuple[RuleSpec, ...]:
    return tuple(s for s in specs if s.backend is not RuleBackend.CLI)


def resolve_selection(
    registry: RuleRegistry,
    profile: Profile | None,
    select: Sequence[str],
    ignore: Sequence[str],
) -> Selection:
    """Compose profile, ``--select`` and ``--ignore`` (policy ignores are applied by the engine)."""
    chosen_tokens = tuple(select) or (profile.select if profile else ())
    chosen = _engine_rules(registry.select(chosen_tokens))
    ignore_tokens = (*(profile.ignore if profile else ()), *ignore)
    ignored_ids = {s.rule_id for s in registry.select(ignore_tokens)} if ignore_tokens else set()
    return Selection(
        run=tuple(s for s in chosen if s.rule_id not in ignored_ids),
        ignored=tuple(s for s in chosen if s.rule_id in ignored_ids),
    )


def unknown_selector_help(error: UnknownSelectorError, proposed: frozenset[str]) -> str:
    """Explain an unknown selector, distinguishing catalogue-only (proposed) rules from typos."""
    parts = [str(error)]
    planned = [s for s in error.selectors if s in proposed]
    if planned:
        parts.append(f"{', '.join(planned)} exist in the catalogue as proposed rules and are not implemented")
    return "; ".join(parts)
