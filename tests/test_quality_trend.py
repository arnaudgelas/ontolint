"""The comparison of two quality snapshots (:func:`ontolint.quality.compare`, ``docs/quality.md``).

The cells of the split (a term lost the property, a new term lacks it, a term is gone, a term gained it) are
pinned one by one on hand-built snapshots, with both polarities; the refusal to compare is pinned per cause and
per measurement; the properties check that the split accounts for every term whatever the sets.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ontolint.models import Measurement, MeasurementKind
from ontolint.quality import Coverage, Entry, Shaping, Snapshot, compare

RATIO, COUNT, HISTOGRAM = MeasurementKind.RATIO, MeasurementKind.COUNT, MeasurementKind.HISTOGRAM
KEYS = ("regressed", "diluted", "removed", "improved", "added_good")


def term(name: str) -> str:
    return f"https://example.test/q#{name}"


def terms(names: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({term(n) for n in names}))


def coverage(
    numerator: str, denominator: str, *, better: str = "higher", version: int = 1, population: str = "owned_classes"
) -> Entry:
    """A coverage measure from names: ``"AB"`` is the terms ``A`` and ``B``."""
    n, d = terms(numerator), terms(denominator)
    measurement = Measurement("m", version, RATIO, population, numerator=len(n), denominator=len(d))
    return Entry(measurement, Coverage(better, n, d))


def snapshot(*entries: Entry, shaping: Shaping | None = None) -> Snapshot:
    return Snapshot(shaping or Shaping(), entries)


def split(old: Entry, new: Entry) -> dict[str, int]:
    (result,) = compare(snapshot(old), snapshot(new)).results
    assert result.reasons == ()
    assert result.change is not None
    return result.change.counts()


def counts(**given: int) -> dict[str, int]:
    return {key: given.get(key, 0) for key in KEYS}


def test_a_term_that_lost_the_property_is_a_regression() -> None:
    assert split(coverage("AB", "ABC"), coverage("A", "ABC")) == counts(regressed=1)


def test_a_new_term_without_the_property_is_dilution_and_not_a_regression() -> None:
    # The documented terms stay at 2 and the ratio falls: only the term sets say why.
    assert split(coverage("AB", "ABC"), coverage("AB", "ABCDEF")) == counts(diluted=3)


def test_a_removed_term_is_neither_a_regression_nor_dilution() -> None:
    assert split(coverage("AB", "ABC"), coverage("A", "AC")) == counts(removed=1)


def test_a_term_that_gained_the_property_is_an_improvement() -> None:
    assert split(coverage("A", "ABC"), coverage("AB", "ABC")) == counts(improved=1)


def test_a_new_term_with_the_property_is_counted_apart_from_the_gains() -> None:
    assert split(coverage("A", "AB"), coverage("AC", "ABC")) == counts(added_good=1)


def test_the_fixture_shape_of_the_issue_is_classified() -> None:
    # A regression (B), a dilution (F, G, H), a removal (C, E) and a gain (D), as tests/fixtures/quality.
    expected = counts(regressed=1, diluted=3, removed=2, improved=1)
    assert split(coverage("ABC", "ABCDE"), coverage("AD", "ABDFGH")) == expected


def test_when_lower_is_better_entering_the_numerator_is_the_regression() -> None:
    # An orphan set: C is now an orphan (worse), A no longer (better), F is a new orphan, G a new fine class.
    old, new = coverage("A", "ABC", better="lower"), coverage("CF", "BCFG", better="lower")
    assert split(old, new) == counts(regressed=1, diluted=1, removed=1, added_good=1)


def test_the_split_lists_the_terms_in_sorted_order() -> None:
    (result,) = compare(snapshot(coverage("ABC", "ABCDE")), snapshot(coverage("AD", "ABDFGH"))).results
    assert result.change is not None
    assert result.change.terms("regressed") == terms("B")
    assert result.change.terms("diluted") == terms("FGH")
    assert result.change.terms("removed") == terms("CE")
    assert result.change.terms("improved") == terms("D")
    assert result.change.terms("added_good") == ()


def test_the_ratio_delta_is_exact_and_signed() -> None:
    (result,) = compare(snapshot(coverage("ABC", "ABCDE")), snapshot(coverage("AD", "ABDFGH"))).results
    assert result.delta == "-0.2667"  # 2/6 - 3/5
    (result,) = compare(snapshot(coverage("A", "AB")), snapshot(coverage("AB", "AB"))).results
    assert result.delta == "+0.5000"
    (result,) = compare(snapshot(coverage("A", "AB")), snapshot(coverage("B", "AB"))).results
    assert result.delta == "0.0000"


def test_a_delta_that_rounds_to_zero_has_no_sign() -> None:
    old = Entry(Measurement("m", 1, RATIO, "p", numerator=1, denominator=1_000_000))
    new = Entry(Measurement("m", 1, RATIO, "p", numerator=0, denominator=1_000_000))
    (result,) = compare(snapshot(old), snapshot(new)).results
    assert result.delta == "0.0000"


def test_an_empty_population_has_no_delta() -> None:
    (result,) = compare(snapshot(coverage("", "")), snapshot(coverage("A", "AB"))).results
    assert result.reasons == () and result.delta is None
    (result,) = compare(snapshot(coverage("A", "AB")), snapshot(coverage("", ""))).results
    assert result.reasons == () and result.delta is None


def test_a_ratio_without_term_sets_is_compared_by_its_parts() -> None:
    old = Entry(Measurement("class_fanout", 1, RATIO, "owned_parent_classes", numerator=15, denominator=14))
    new = Entry(Measurement("class_fanout", 1, RATIO, "owned_parent_classes", numerator=18, denominator=12))
    (result,) = compare(snapshot(old), snapshot(new)).results
    assert result.reasons == () and result.change is None
    assert result.delta == "+0.4286"  # 18/12 - 15/14


def test_a_count_is_compared_by_its_difference() -> None:
    old = Entry(Measurement("unresolved_imports", 1, COUNT, "graph", value=3))
    new = Entry(Measurement("unresolved_imports", 1, COUNT, "graph", value=1))
    (result,) = compare(snapshot(old), snapshot(new)).results
    assert result.delta == COUNT_DROP and result.reasons == ()


def test_a_histogram_says_only_whether_it_changed() -> None:
    def hist(buckets: tuple[tuple[int, int], ...]) -> Entry:
        return Entry(Measurement("class_depth", 1, HISTOGRAM, "acyclic_owned_classes", buckets=buckets))

    (same,) = compare(snapshot(hist(((1, 4),))), snapshot(hist(((1, 4),)))).results
    (moved,) = compare(snapshot(hist(((1, 4),))), snapshot(hist(((1, 3), (2, 1))))).results
    assert same.changed is False and moved.changed is True
    assert same.delta is None and moved.delta is None


COUNT_DROP = -2
UNTAKEN = "no SHACL shapes graph was supplied"


@pytest.mark.parametrize(
    ("old", "new", "reason"),
    [
        (coverage("A", "AB"), coverage("A", "AB", version=2), "definition version 1 -> 2"),
        (
            coverage("A", "AB"),
            coverage("A", "AB", population="owned_properties"),
            "population owned_classes -> owned_properties",
        ),
        (coverage("A", "AB"), coverage("A", "AB", better="lower"), "numerator reading higher -> lower"),
        (
            coverage("A", "AB"),
            Entry(Measurement("m", 1, RATIO, "owned_classes", numerator=1, denominator=2)),
            "term sets are in the old snapshot only",
        ),
        (
            Entry(Measurement("m", 1, RATIO, "owned_classes", numerator=1, denominator=2)),
            coverage("A", "AB"),
            "term sets are in the new snapshot only",
        ),
        (coverage("A", "AB"), Entry(Measurement("m", 1, COUNT, "owned_classes", value=1)), "kind ratio -> count"),
        (
            coverage("A", "AB"),
            Entry(Measurement("m", 1, RATIO, "owned_classes", reason=UNTAKEN)),
            f"not taken in the new snapshot: {UNTAKEN}",
        ),
        (
            Entry(Measurement("m", 1, RATIO, "owned_classes", reason="failed: ValueError: boom")),
            coverage("A", "AB"),
            "not taken in the old snapshot: failed: ValueError: boom",
        ),
    ],
)
def test_a_pair_that_differs_in_what_is_measured_is_not_compared(old: Entry, new: Entry, reason: str) -> None:
    (result,) = compare(snapshot(old), snapshot(new)).results
    assert reason in result.reasons
    assert result.change is None and result.delta is None and result.before is None and result.after is None


def test_a_measurement_not_taken_in_either_snapshot_is_not_comparable() -> None:
    absent = Entry(Measurement("m", 1, RATIO, "owned_classes", reason=UNTAKEN))
    (result,) = compare(snapshot(absent), snapshot(absent)).results
    assert result.reasons == (f"not taken in the old snapshot: {UNTAKEN}", f"not taken in the new snapshot: {UNTAKEN}")


def test_every_difference_is_a_reason_of_its_own() -> None:
    old = coverage("A", "AB")
    new = coverage("A", "AB", version=2, population="owned_properties", better="lower")
    (result,) = compare(snapshot(old), snapshot(new)).results
    assert result.reasons == (
        "definition version 1 -> 2",
        "population owned_classes -> owned_properties",
        "numerator reading higher -> lower",
    )


def test_a_measurement_in_one_snapshot_only_is_not_comparable() -> None:
    other = Entry(Measurement("other", 1, COUNT, "graph", value=1))
    both = compare(snapshot(coverage("A", "A")), snapshot(coverage("A", "A"), other))
    assert [(r.id, r.reasons) for r in both.results] == [("m", ()), ("other", ("measured in the new snapshot only",))]
    gone = compare(snapshot(coverage("A", "A"), other), snapshot(coverage("A", "A")))
    assert [(r.id, r.reasons) for r in gone.results] == [("m", ()), ("other", ("measured in the old snapshot only",))]


@pytest.mark.parametrize(
    ("old", "new", "fields"),
    [
        (Shaping(base="https://a.test/"), Shaping(base="https://b.test/"), "base"),
        (Shaping(), Shaping(base="https://b.test/"), "base"),
        (Shaping(extra_label_predicates=("https://x.test/l",)), Shaping(), "extra_label_predicates"),
        (Shaping(), Shaping(extra_definition_predicates=("https://x.test/d",)), "extra_definition_predicates"),
        (Shaping(imports=("https://x.test/i",)), Shaping(), "imports"),
        (Shaping(base="a", imports=("i",)), Shaping(), "base, imports"),
    ],
)
def test_a_pair_taken_under_another_policy_is_refused_measurement_by_measurement(
    old: Shaping, new: Shaping, fields: str
) -> None:
    other = Entry(Measurement("other", 1, COUNT, "graph", value=1))
    before, after = snapshot(coverage("A", "AB"), other, shaping=old), snapshot(coverage("A", "AB"), other, shaping=new)
    assert [(r.id, r.reasons) for r in compare(before, after).results] == [
        ("m", (f"policy differs: {fields}",)),
        ("other", (f"policy differs: {fields}",)),
    ]


def test_one_incompatible_measurement_does_not_hide_the_compatible_ones() -> None:
    kept = Entry(Measurement("kept", 1, COUNT, "graph", value=1))
    old = snapshot(kept, Entry(Measurement("bumped", 1, COUNT, "graph", value=1)))
    new = snapshot(kept, Entry(Measurement("bumped", 2, COUNT, "graph", value=5)))
    comparison = compare(old, new)
    assert [(r.id, bool(r.reasons)) for r in comparison.results] == [("kept", False), ("bumped", True)]
    assert comparison.results[0].delta == 0


def test_the_comparison_says_that_a_rename_is_a_removal_and_a_new_term() -> None:
    comparison = compare(snapshot(coverage("A", "A")), snapshot(coverage("A", "A")))
    assert any("rename" in note and "removal" in note and "new term" in note for note in comparison.notes)
    assert comparison.to_dict()["notes"] == list(comparison.notes)


def test_a_rename_is_counted_as_one_removal_and_one_new_term() -> None:
    # B is renamed C, both defined.
    assert split(coverage("AB", "AB"), coverage("AC", "AC")) == counts(removed=1, added_good=1)


NAMES = st.sets(st.sampled_from("ABCDEFGHIJ"))


@st.composite
def populations(draw: st.DrawFn) -> tuple[str, str, str]:
    population = draw(NAMES)
    numerator = {n for n in population if draw(st.booleans())}
    better = draw(st.sampled_from(("higher", "lower")))
    return "".join(sorted(numerator)), "".join(sorted(population)), better


def pair(old: tuple[str, str, str], new: tuple[str, str, str]) -> tuple[Entry, Entry]:
    return coverage(old[0], old[1], better=old[2]), coverage(new[0], new[1], better=old[2])


@given(old=populations(), new=populations())
def test_the_split_accounts_for_every_term_of_both_populations(
    old: tuple[str, str, str], new: tuple[str, str, str]
) -> None:
    found = split(*pair(old, new))
    kept = set(old[1]) & set(new[1])
    assert found["removed"] == len(set(old[1]) - set(new[1]))
    assert found["diluted"] + found["added_good"] == len(set(new[1]) - set(old[1]))
    assert found["regressed"] + found["improved"] <= len(kept)

    def good(numerator: str, population: str) -> set[str]:
        return set(population) - set(numerator) if old[2] == "lower" else set(numerator)

    before, after = good(old[0], old[1]), good(new[0], new[1])
    # What is good after: what was good, less the regressions and the removed, plus the gains and the new.
    expected = len(before) - found["regressed"] + found["improved"] - len(before - set(new[1])) + found["added_good"]
    assert len(after) == expected


@given(old=populations(), new=populations())
def test_swapping_the_snapshots_swaps_the_two_directions(old: tuple[str, str, str], new: tuple[str, str, str]) -> None:
    a, b = pair(old, new)
    forward, backward = split(a, b), split(b, a)
    assert forward["regressed"] == backward["improved"] and forward["improved"] == backward["regressed"]
    assert forward["removed"] == backward["diluted"] + backward["added_good"]
    assert backward["removed"] == forward["diluted"] + forward["added_good"]


@given(entry=populations())
def test_a_snapshot_compared_with_itself_has_no_change(entry: tuple[str, str, str]) -> None:
    a = coverage(entry[0], entry[1], better=entry[2])
    assert split(a, a) == counts()


def test_to_dict_is_json_ready_and_names_the_format() -> None:
    comparison = compare(snapshot(coverage("ABC", "ABCDE")), snapshot(coverage("AD", "ABDFGH"))).to_dict()
    assert comparison["format"] == "ontolint-quality-comparison" and comparison["version"] == 1
    (m,) = comparison["measurements"]
    assert m["status"] == "compared"
    assert m["before"] == {"numerator": 3, "denominator": 5} and m["after"] == {"numerator": 2, "denominator": 6}
    assert m["delta"] == "-0.2667"
    assert m["coverage"]["better"] == "higher"
    assert {k: m["coverage"][k] for k in KEYS} == counts(regressed=1, diluted=3, removed=2, improved=1)
    assert m["coverage"]["terms"]["regressed"] == [term("B")]


def test_a_refused_measurement_is_published_with_its_reasons_only() -> None:
    comparison: dict[str, Any] = compare(
        snapshot(coverage("A", "AB")), snapshot(coverage("A", "AB", version=2))
    ).to_dict()
    assert comparison["measurements"] == [
        {"id": "m", "status": "not_comparable", "reasons": ["definition version 1 -> 2"]}
    ]
