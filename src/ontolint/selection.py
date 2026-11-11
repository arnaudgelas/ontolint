"""Rule selection: how ``--profile``, ``--select``, ``--ignore`` and the policy file combine.

Precedence, from the broadest to the strongest word:

1. The chosen set is ``--select`` when given, otherwise the profile's selection, otherwise every default
   rule (every rule outside :data:`~ontolint.profiles.OPT_IN_FAMILIES`).  An explicit ``--select``
   *replaces* the profile's selection (it does not add to it).  Opt-in families run only when named by
   ``--select`` (family or rule id), by the profile's ``select``, or by the profile's ``opt_in``.
2. Ignores always win: ``--ignore``, the profile's ``ignore`` and the policy file's ``ignored_rules``
   are unioned and removed from the chosen set, whatever selected the rule.
3. Severity overrides apply to what remains: profile first, then the policy file (policy wins).
   Selectors are validated strictly (typos are errors, never an empty run); the policy file's
   ``ignored_rules`` keep their historical exact-identifier, unvalidated behaviour.

Pipeline rules (``backend`` ``cli``: the safe-loader refusals ``SEC001``, ``SEC002``, ``SEC003``,
``SEC006``, ``SEC009``, ``SEC010``, ``SEC011``, ``SEC013`` and ``SEC015``, and the front-end diagnostics
``INPUT001`` and ``TOOL001``) are not engine rules: they always apply, so they are never part of a selection
or of the reported executions.  Naming one in ``--select`` or ``--ignore``, as an id or as a family made
only of them (``INPUT``, ``TOOL``), could change nothing, so :func:`check_selectors` rejects it.  A mixed
family (``SEC``) is accepted and applies to its graph rules.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from .models import RuleBackend, RuleSpec
from .profiles import Profile, is_opt_in
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


def default_rules(specs: Sequence[RuleSpec]) -> tuple[RuleSpec, ...]:
    """The rules that run when nothing is selected: everything outside the opt-in families."""
    return tuple(s for s in specs if not is_opt_in(s.family))


def _chosen(registry: RuleRegistry, profile: Profile | None, select: Sequence[str]) -> tuple[RuleSpec, ...]:
    tokens = tuple(select) or (profile.select if profile else ())
    chosen = registry.select(tokens) if tokens else default_rules(registry.all())
    opted = profile.opt_in if profile and not select else ()
    if not opted:
        return chosen
    extra = registry.select(opted)
    return tuple(sorted({*chosen, *extra}, key=lambda s: s.rule_id))


def resolve_selection(
    registry: RuleRegistry,
    profile: Profile | None,
    select: Sequence[str],
    ignore: Sequence[str],
) -> Selection:
    """Compose profile, ``--select`` and ``--ignore`` (policy ignores are applied by the engine)."""
    chosen = _engine_rules(_chosen(registry, profile, select))
    ignore_tokens = (*(profile.ignore if profile else ()), *ignore)
    ignored_ids = {s.rule_id for s in registry.select(ignore_tokens)} if ignore_tokens else set()
    return Selection(
        run=tuple(s for s in chosen if s.rule_id not in ignored_ids),
        ignored=tuple(s for s in chosen if s.rule_id in ignored_ids),
    )


PIPELINE_HELP = "safe-loader refusals and front-end diagnostics, never findings"
"""What a pipeline rule is, in the words of the configuration errors that name one."""


def is_pipeline(spec: RuleSpec) -> bool:
    """Whether ``spec`` is a pipeline rule: emitted by the loader or the CLI front end, whatever the selection."""
    return spec.backend is RuleBackend.CLI


def pipeline_selectors(registry: RuleRegistry, tokens: Iterable[str]) -> tuple[str, ...]:
    """The tokens (upper-cased, de-duplicated, in order) that name only pipeline rules.

    That is a pipeline rule id, or a family all of whose rules are pipeline rules.  A mixed family
    (``SEC``) is not returned, and neither is an unknown token: :meth:`RuleRegistry.select` reports those.
    """
    found: dict[str, None] = {}
    for token in tokens:
        upper = token.strip().upper()
        named = [s for s in registry.all() if upper in {s.rule_id, s.family.upper()}]
        if named and all(is_pipeline(s) for s in named):
            found[upper] = None
    return tuple(found)


class PipelineSelectorError(ValueError):
    """``--select`` or ``--ignore`` names only pipeline rules, which no selection changes."""

    def __init__(self, named: Sequence[tuple[str, tuple[str, ...]]]) -> None:
        self.named = tuple(named)
        parts = "; ".join(f"{option} {', '.join(tokens)}" for option, tokens in self.named)
        super().__init__(
            f"{parts}: these name only pipeline rules ({PIPELINE_HELP}), "
            "which always apply whatever the selection; remove them"
        )


def check_selectors(registry: RuleRegistry, select: Sequence[str], ignore: Sequence[str]) -> None:
    """Reject selectors that cannot change the run, before any input is read.

    Raises :class:`UnknownSelectorError` for a token that names nothing (checked first, so a typo next to a
    pipeline rule is reported as the typo), then :class:`PipelineSelectorError` for every token that names
    only pipeline rules.  An empty list means the default and is never checked.
    """
    lists = (("--select", select), ("--ignore", ignore))
    for _, tokens in lists:
        if tokens:
            registry.select(tokens)
    named = [(option, found) for option, tokens in lists if (found := pipeline_selectors(registry, tokens))]
    if named:
        raise PipelineSelectorError(named)


def unknown_selector_help(error: UnknownSelectorError, proposed: frozenset[str]) -> str:
    """Explain an unknown selector, distinguishing catalogue-only (proposed) rules from typos."""
    parts = [str(error)]
    planned = [s for s in error.selectors if s in proposed]
    if planned:
        parts.append(f"{', '.join(planned)} exist in the catalogue as proposed rules and are not implemented")
    return "; ".join(parts)
