"""Validated, immutable linting policy independent of CLI argument parsing."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Any

from .models import Severity

_ABSOLUTE_IRI = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:[^\s<>\"{}|\\^`]+")
DEFAULT_DEPTH_LIMIT = 10
DEFAULT_INHERITANCE_LIMIT = 5
DEFAULT_SOUP_LIMIT = 15
DEFAULT_SUBCLASS_LIMIT = 50  # CLS011: more direct subclasses than this is a flat, hard-to-browse fan-out

# Safe-loader limits (SEC001, SEC002): generous for real ontologies, small enough to stop decompression-bomb
# style inputs in CI.  Both must be positive integers.
DEFAULT_MAX_INPUT_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_TRIPLES = 5_000_000
DEFAULT_MAX_IMPORT_DEPTH = 16
DEFAULT_MAX_IMPORTED_FILES = 100
LOADER_LIMIT_DEFAULTS: dict[str, int] = {
    "max_input_bytes": DEFAULT_MAX_INPUT_BYTES,
    "max_triples": DEFAULT_MAX_TRIPLES,
    # Bounds of an owl:imports closure (--follow-imports, --catalog); max_triples bounds its whole graph.
    "max_import_depth": DEFAULT_MAX_IMPORT_DEPTH,
    "max_imported_files": DEFAULT_MAX_IMPORTED_FILES,
}

# Ontology-metric thresholds (METRIC001-METRIC013).  Ratios live in [0, 1]; counts are integers.
# ``metric_min_sample`` is the smallest population a metric needs before it can fire, so tiny
# ontologies never trigger a ratio rule.
DEFAULT_METRIC_MIN_SAMPLE = 10
DEFAULT_METRIC_MAX_IMPORTS = 10
METRIC_RATIO_DEFAULTS: dict[str, float] = {
    "metric_max_unlabelled_ratio": 0.5,
    "metric_max_undefined_ratio": 0.5,
    "metric_max_undocumented_property_ratio": 0.5,
    "metric_max_orphan_ratio": 0.3,
    "metric_max_unsigned_property_ratio": 0.5,
    "metric_min_language_coverage": 0.5,
    "metric_max_foreign_reference_ratio": 0.5,
    "metric_max_blank_node_ratio": 0.6,
}
# Non-ratio real-valued thresholds: they only need to be finite and non-negative.
METRIC_QUANTITY_DEFAULTS: dict[str, float] = {
    "metric_max_mean_fanout": 8.0,
    "metric_min_property_class_ratio": 0.1,
    "metric_max_property_class_ratio": 5.0,
    "metric_min_definition_words": 4.0,
}


@dataclass(frozen=True)
class Policy:
    """Configuration for graph-local rules and report post-processing."""

    base: str | None = None
    languages: tuple[str, ...] = ()
    depth_limit: int = DEFAULT_DEPTH_LIMIT
    inheritance_limit: int = DEFAULT_INHERITANCE_LIMIT
    soup_limit: int = DEFAULT_SOUP_LIMIT
    subclass_limit: int = DEFAULT_SUBCLASS_LIMIT
    metric_min_sample: int = DEFAULT_METRIC_MIN_SAMPLE
    metric_max_imports: int = DEFAULT_METRIC_MAX_IMPORTS
    metric_max_unlabelled_ratio: float = 0.5
    metric_max_undefined_ratio: float = 0.5
    metric_max_undocumented_property_ratio: float = 0.5
    metric_max_orphan_ratio: float = 0.3
    metric_max_unsigned_property_ratio: float = 0.5
    metric_min_language_coverage: float = 0.5
    metric_max_foreign_reference_ratio: float = 0.5
    metric_max_blank_node_ratio: float = 0.6
    metric_max_mean_fanout: float = 8.0
    metric_min_property_class_ratio: float = 0.1
    metric_max_property_class_ratio: float = 5.0
    metric_min_definition_words: float = 4.0
    max_input_bytes: int = DEFAULT_MAX_INPUT_BYTES
    max_triples: int = DEFAULT_MAX_TRIPLES
    max_import_depth: int = DEFAULT_MAX_IMPORT_DEPTH
    max_imported_files: int = DEFAULT_MAX_IMPORTED_FILES
    extra_definition_predicates: tuple[str, ...] = ()
    extra_label_predicates: tuple[str, ...] = ()
    ignored_rules: frozenset[str] = frozenset()
    severity_overrides: tuple[tuple[str, str], ...] = ()
    required_annotations: tuple[tuple[str, tuple[str, ...]], ...] = ()
    alignment_namespaces: tuple[str, ...] = ()
    alignment_min_coverage: float | None = None
    max_parse_seconds: float | None = None  # wall-clock budget for parsing one input (SEC003); None = no budget
    unknown_keys: tuple[str, ...] = ()  # config keys the policy file carried but ontolint does not know (GOV020)
    # Set by the loader for one file, never by a policy file: the owl:imports IRIs it resolved to local
    # files, and the ontology IRIs declared by those imported files (see :mod:`ontolint.imports`).
    resolved_imports: frozenset[str] = frozenset()
    imported_ontologies: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        for name in LOADER_LIMIT_DEFAULTS:
            _check_limit(name, getattr(self, name))
        _check_parse_seconds(self.max_parse_seconds)

    @property
    def severity_mapping(self) -> dict[str, str]:
        """Return overrides in the shape expected by report filtering."""
        return dict(self.severity_overrides)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> Policy:
        """Create policy from JSON-compatible data and reject malformed values."""
        _check_version(data)
        base = data.get("base")
        languages = data.get("languages", [])
        ignored_rules = data.get("ignored_rules", [])
        overrides = data.get("severity_overrides", {})
        numeric_values = {
            "depth_limit": data.get("depth_limit", DEFAULT_DEPTH_LIMIT),
            "inheritance_limit": data.get("inheritance_limit", DEFAULT_INHERITANCE_LIMIT),
            "soup_limit": data.get("soup_limit", DEFAULT_SOUP_LIMIT),
            "subclass_limit": data.get("subclass_limit", DEFAULT_SUBCLASS_LIMIT),
        }
        if base is not None and not isinstance(base, str):
            raise ValueError("base must be a string or null")
        if not isinstance(languages, list) or not all(isinstance(value, str) for value in languages):
            raise ValueError("languages must be a list of strings")
        if not isinstance(ignored_rules, list) or not all(isinstance(value, str) for value in ignored_rules):
            raise ValueError("ignored_rules must be a list of rule identifiers")
        if not isinstance(overrides, dict) or not all(
            isinstance(rule, str) and isinstance(severity, str) for rule, severity in overrides.items()
        ):
            raise ValueError("severity_overrides must map rule identifiers to severities")
        valid_severities = {severity.value for severity in Severity}
        if any(severity not in valid_severities for severity in overrides.values()):
            raise ValueError("severity_overrides must be error, warning or info")
        if any(not isinstance(value, int) or isinstance(value, bool) for value in numeric_values.values()):
            raise ValueError("policy thresholds must be integers")
        metrics = _metric_values(data)
        limits = _loader_limits(data)
        extra_definitions = _iri_list(data, "extra_definition_predicates")
        extra_labels = _iri_list(data, "extra_label_predicates")
        return cls(
            **metrics,
            **limits,
            base=base,
            languages=tuple(language.lower() for language in languages),
            depth_limit=numeric_values["depth_limit"],
            inheritance_limit=numeric_values["inheritance_limit"],
            soup_limit=numeric_values["soup_limit"],
            subclass_limit=numeric_values["subclass_limit"],
            extra_definition_predicates=extra_definitions,
            extra_label_predicates=extra_labels,
            ignored_rules=frozenset(ignored_rules),
            severity_overrides=tuple(sorted(overrides.items())),
            required_annotations=_required_annotations(data),
            alignment_namespaces=_iri_list(data, "alignment_namespaces"),
            alignment_min_coverage=_optional_ratio(data, "alignment_min_coverage"),
            max_parse_seconds=_parse_seconds(data),
            unknown_keys=tuple(sorted({str(key) for key in data} - _known_keys())),
            resolved_imports=frozenset(),
            imported_ontologies=frozenset(),
        )


POLICY_VERSION = 1
ANNOTATION_KINDS = ("class", "property", "individual", "concept")


class PolicyVersionError(ValueError):
    """The policy file declares a ``policy_version`` this ontolint does not support (reported as GOV020)."""


_RUNTIME_FIELDS = frozenset({"unknown_keys", "resolved_imports", "imported_ontologies"})
"""Policy fields filled in while linting, not accepted from a policy file."""


def _known_keys() -> frozenset[str]:
    """Every accepted top-level policy key: the Policy fields (minus bookkeeping) and ``policy_version``."""
    return frozenset(f.name for f in fields(Policy) if f.name not in _RUNTIME_FIELDS) | {"policy_version"}


def _check_version(data: Mapping[str, Any]) -> None:
    """Accept an absent version (= current) or the current one; reject anything else."""
    value = data.get("policy_version", POLICY_VERSION)
    if not isinstance(value, int) or isinstance(value, bool):
        raise PolicyVersionError("policy_version must be an integer")
    if value != POLICY_VERSION:
        raise PolicyVersionError(
            f"policy_version {value} is not supported (this ontolint reads policy version {POLICY_VERSION})"
        )


def _optional_ratio(data: Mapping[str, Any], name: str) -> float | None:
    """Validate an optional ratio in [0, 1]; ``null`` or absent means off."""
    value = data.get(name)
    if value is None:
        return None
    ratio = _real(name, value)
    if not 0.0 <= ratio <= 1.0:
        raise ValueError(f"{name} must be a ratio between 0 and 1")
    return ratio


def _required_annotations(data: Mapping[str, Any]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Validate ``required_annotations``: term kind -> absolute predicate IRIs; sorted by kind, empty kinds dropped."""
    value = data.get("required_annotations", {})
    if not isinstance(value, dict):
        raise ValueError("required_annotations must map term kinds to lists of predicate IRIs")
    result: list[tuple[str, tuple[str, ...]]] = []
    for kind in sorted(value, key=str):
        if kind not in ANNOTATION_KINDS:
            raise ValueError(f"required_annotations kind must be one of {', '.join(ANNOTATION_KINDS)}: {kind!r}")
        predicates = _iri_list(value, kind)
        if predicates:
            result.append((kind, predicates))
    return tuple(result)


def _iri_list(data: Mapping[str, Any], name: str) -> tuple[str, ...]:
    """Validate a list of absolute predicate IRIs (no whitespace, with a scheme); keep order, drop duplicates."""
    value = data.get(name, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be a list of IRI strings")
    for item in value:
        if not _ABSOLUTE_IRI.fullmatch(item):
            raise ValueError(f"{name} must contain absolute IRIs without whitespace: {item!r}")
    return tuple(dict.fromkeys(value))


def _real(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} must be a finite number")
    try:
        number = float(value)  # an int beyond the float range raises OverflowError
    except OverflowError:
        raise ValueError(f"{name} must be a finite number") from None
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


def _metric_values(data: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the METRIC thresholds: positive sample size, non-negative counts, ratios within [0, 1]."""
    values: dict[str, Any] = {}
    for name, count_default in (
        ("metric_min_sample", DEFAULT_METRIC_MIN_SAMPLE),
        ("metric_max_imports", DEFAULT_METRIC_MAX_IMPORTS),
    ):
        value = data.get(name, count_default)
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{name} must be an integer")
        if value < (1 if name == "metric_min_sample" else 0):
            raise ValueError(f"{name} must be {'at least 1' if name == 'metric_min_sample' else 'non-negative'}")
        values[name] = value
    for name, ratio_default in METRIC_RATIO_DEFAULTS.items():
        ratio = _real(name, data.get(name, ratio_default))
        if not 0.0 <= ratio <= 1.0:
            raise ValueError(f"{name} must be a ratio between 0 and 1")
        values[name] = ratio
    for name, quantity_default in METRIC_QUANTITY_DEFAULTS.items():
        quantity = _real(name, data.get(name, quantity_default))
        if quantity < 0:
            raise ValueError(f"{name} must be non-negative")
        values[name] = quantity
    return values


def _check_limit(name: str, value: Any) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    if value < 1:
        raise ValueError(f"{name} must be at least 1")


def _loader_limits(data: Mapping[str, Any]) -> dict[str, int]:
    """Validate the safe-loader limits: positive integers."""
    values: dict[str, int] = {}
    for name, default in LOADER_LIMIT_DEFAULTS.items():
        value = data.get(name, default)
        _check_limit(name, value)
        values[name] = value
    return values


MAX_PARSE_SECONDS = 86_400.0
"""Upper bound of ``max_parse_seconds`` (one day): anything longer is a typo, not a budget."""


def _check_parse_seconds(value: Any) -> None:
    """``None`` (no budget) or a finite number in ``(0, MAX_PARSE_SECONDS]``; booleans and strings are refused."""
    if value is None:
        return
    seconds = _real("max_parse_seconds", value)
    if seconds <= 0:
        raise ValueError("max_parse_seconds must be positive")
    if seconds > MAX_PARSE_SECONDS:
        raise ValueError(f"max_parse_seconds must be at most {MAX_PARSE_SECONDS:g}")


def _parse_seconds(data: Mapping[str, Any]) -> float | None:
    value = data.get("max_parse_seconds")
    _check_parse_seconds(value)
    return None if value is None else float(value)


METRIC_FIELDS = tuple(f.name for f in fields(Policy) if f.name.startswith("metric_"))
