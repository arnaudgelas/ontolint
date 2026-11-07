"""Properties of rule selection: selector parsing, registry selection and ``resolve_selection`` precedence."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis_strategies import FAMILIES, RULE_IDS, budget, selector_lists, selector_tokens

from ontolint.models import RuleBackend
from ontolint.profiles import OPT_IN_FAMILIES, PROFILES, Profile, is_opt_in
from ontolint.rules.registry import UnknownSelectorError, default_registry
from ontolint.selection import SelectorSyntaxError, default_rules, resolve_selection, split_selectors

pytestmark = pytest.mark.slow

REGISTRY = default_registry()
SPECS = REGISTRY.all()
OPT_IN_IDS = frozenset(s.rule_id for s in SPECS if is_opt_in(s.family))
ENGINE_IDS = frozenset(s.rule_id for s in SPECS if s.backend is not RuleBackend.CLI)
DEFAULT_IDS = frozenset(s.rule_id for s in SPECS if s.rule_id in ENGINE_IDS and s.rule_id not in OPT_IN_IDS)

profiles = st.builds(
    Profile,
    name=st.just("generated"),
    description=st.just("generated"),
    select=st.lists(selector_tokens(), max_size=3).map(lambda xs: tuple(x.upper() for x in xs)),
    ignore=st.lists(selector_tokens(), max_size=3).map(lambda xs: tuple(x.upper() for x in xs)),
    opt_in=st.sampled_from(((), ("OBO",), ("FAIR",), ("FAIR", "OBO"))),
)
maybe_profile = st.one_of(st.none(), profiles, st.sampled_from(sorted(PROFILES.values(), key=lambda p: p.name)))


def ids(specs: object) -> set[str]:
    return {s.rule_id for s in specs}  # type: ignore[attr-defined]


def tokens_ids(tokens: list[str]) -> set[str]:
    return ids(REGISTRY.select(tokens)) if tokens else set()


# --- selector parsing --------------------------------------------------------------------------------


@budget(1)
@given(st.lists(st.lists(selector_tokens(), min_size=1, max_size=4), max_size=4))
def test_split_selectors_flattens_uppercases_and_deduplicates_in_order(groups: list[list[str]]) -> None:
    """INVARIANT: split_selectors keeps first-seen order, upper-cases and drops repeats across arguments."""
    arguments = [",".join(group) for group in groups]

    result = split_selectors(arguments)

    expected = list(dict.fromkeys(token.upper() for group in groups for token in group))
    assert list(result) == expected
    assert split_selectors([",".join(result)] if result else []) == result  # idempotent


@budget(1)
@given(st.lists(st.text(alphabet="ab, \t", max_size=6), max_size=3))
def test_split_selectors_rejects_exactly_the_arguments_with_an_empty_entry(arguments: list[str]) -> None:
    """INVARIANT: an empty (or blank) comma-separated entry raises SelectorSyntaxError; nothing else does."""
    has_empty = any(not part.strip() for argument in arguments for part in argument.split(","))

    if has_empty:
        with pytest.raises(SelectorSyntaxError):
            split_selectors(arguments)
    else:
        assert all(token == token.upper() and token == token.strip() for token in split_selectors(arguments))


# --- registry ----------------------------------------------------------------------------------------


@budget(1)
@given(selector_lists)
def test_registry_select_is_the_union_of_ids_and_families(tokens: list[str]) -> None:
    """INVARIANT: select(tokens) is exactly the rules whose id or family is named (any case); [] gives the defaults."""
    chosen = ids(REGISTRY.select(tokens))

    if not tokens:
        assert chosen == {s.rule_id for s in SPECS if not is_opt_in(s.family)}
        return
    wanted = {t.upper() for t in tokens}
    assert chosen == {s.rule_id for s in SPECS if s.rule_id in wanted or s.family.upper() in wanted}
    assert [s.rule_id for s in REGISTRY.select(tokens)] == sorted(chosen)


@budget(1)
@given(selector_lists, selector_lists)
def test_registry_select_is_monotone_and_order_free(first: list[str], second: list[str]) -> None:
    """INVARIANT: adding selectors never removes rules, and selector order does not matter."""
    if not first and not second:
        return
    union = ids(REGISTRY.select([*first, *second]))
    assert union >= (tokens_ids(first) | tokens_ids(second))
    assert union == ids(REGISTRY.select([*second, *first]))


@budget(1)
@given(st.text(alphabet="ABCXYZ019", min_size=1, max_size=8))
def test_registry_rejects_unknown_selectors_and_names_them(token: str) -> None:
    """INVARIANT: a selector that is neither a rule id nor a family raises UnknownSelectorError naming it."""
    known = {*RULE_IDS, *FAMILIES}
    if token in known:
        assert REGISTRY.select([token])
        return
    with pytest.raises(UnknownSelectorError) as info:
        REGISTRY.select(["ONT001", token])
    assert info.value.selectors == (token,)


# --- resolve_selection -------------------------------------------------------------------------------


@budget(2)
@given(maybe_profile, selector_lists, selector_lists)
def test_resolution_partitions_the_chosen_set_and_never_runs_front_end_rules(
    profile: Profile | None, select: list[str], ignore: list[str]
) -> None:
    """INVARIANT: run and ignored are disjoint, contain only engine rules and ignores always win."""
    selection = resolve_selection(REGISTRY, profile, select, ignore)

    run, ignored = ids(selection.run), ids(selection.ignored)
    assert not run & ignored
    assert (run | ignored) <= ENGINE_IDS
    all_ignores = [*(profile.ignore if profile else ()), *ignore]
    ignore_ids = tokens_ids(all_ignores)
    assert not run & ignore_ids
    assert ignored == (run | ignored) & ignore_ids


@budget(2)
@given(maybe_profile, selector_lists, selector_lists)
def test_ignore_removes_exactly_the_ignored_rules(
    profile: Profile | None, select: list[str], ignore: list[str]
) -> None:
    """INVARIANT: run(select, ignore) == run(select, no ignore) minus what the ignore selectors name."""
    with_ignore = resolve_selection(REGISTRY, profile, select, ignore)
    without = resolve_selection(REGISTRY, profile, select, [])

    assert ids(with_ignore.run) == ids(without.run) - tokens_ids([*(profile.ignore if profile else ()), *ignore])
    assert ids(with_ignore.run) | ids(with_ignore.ignored) == ids(without.run) | ids(without.ignored)


@budget(1)
@given(selector_lists)
def test_default_selection_excludes_opt_in_families(ignore: list[str]) -> None:
    """INVARIANT: with no select and no profile the run is every default rule (no opt-in family) minus the ignores."""
    selection = resolve_selection(REGISTRY, None, [], ignore)

    assert not ids(selection.run) & OPT_IN_IDS
    assert ids(selection.run) == DEFAULT_IDS - tokens_ids(ignore)
    assert ids(default_rules(SPECS)) == {s.rule_id for s in SPECS if not is_opt_in(s.family)}


@budget(1)
@given(st.sampled_from(sorted(OPT_IN_FAMILIES)), st.sampled_from(("family", "id")), st.booleans())
def test_opt_in_rules_run_with_an_explicit_selection(family: str, how: str, lower: bool) -> None:
    """INVARIANT: naming an opt-in family (or each of its rules) selects all of its rules."""
    members = sorted(s.rule_id for s in SPECS if s.family.upper() == family)
    tokens = [family.lower() if lower else family] if how == "family" else members

    run = ids(resolve_selection(REGISTRY, None, tokens, []).run)

    assert run == set(members) & ENGINE_IDS
    assert set(members) <= OPT_IN_IDS


@budget(1)
@given(selector_lists.filter(bool), profiles)
def test_explicit_select_replaces_profile_selection_but_not_profile_ignores(
    select: list[str], profile: Profile
) -> None:
    """INVARIANT: --select replaces the profile's select and opt_in; the profile's ignores still apply."""
    result = ids(resolve_selection(REGISTRY, profile, select, []).run)

    expected = (tokens_ids(select) & ENGINE_IDS) - tokens_ids(list(profile.ignore))
    assert result == expected
    blank = Profile("blank", "", ignore=profile.ignore)
    assert result == ids(resolve_selection(REGISTRY, blank, select, []).run)


@budget(1)
@given(profiles)
def test_profile_selection_is_used_without_select_and_opt_in_adds_its_families(profile: Profile) -> None:
    """INVARIANT: without --select the profile's select (or the defaults) plus its opt_in families run."""
    result = ids(resolve_selection(REGISTRY, profile, [], []).run)

    base = tokens_ids(list(profile.select)) if profile.select else set(DEFAULT_IDS)
    extra = tokens_ids(list(profile.opt_in))
    expected = ((base | extra) & ENGINE_IDS) - tokens_ids(list(profile.ignore))
    assert result == expected


@budget(1)
@given(selector_lists.filter(bool), selector_lists.filter(bool))
def test_selection_is_monotone_in_select(first: list[str], second: list[str]) -> None:
    """INVARIANT: selecting more tokens never runs fewer rules."""
    small = ids(resolve_selection(REGISTRY, None, first, []).run)
    large = ids(resolve_selection(REGISTRY, None, [*first, *second], []).run)

    assert small <= large


@pytest.mark.parametrize("profile", sorted(PROFILES))
def test_builtin_profiles_resolve_to_known_rules(profile: str) -> None:
    """Every shipped profile resolves without error; an opt-in profile runs exactly its own opt-in family."""
    run = ids(resolve_selection(REGISTRY, PROFILES[profile], [], []).run)

    assert run
    enabled = {family for family in OPT_IN_FAMILIES if profile == family.lower()}
    for family in OPT_IN_FAMILIES:
        family_ids = {s.rule_id for s in SPECS if s.family == family}
        assert (run & family_ids == family_ids) if family in enabled else not run & family_ids
