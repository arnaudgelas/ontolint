"""Rules that are driven by the policy file: GOV016, GOV020, ALIGN012 and ALIGN016.

Every rule is silent unless its policy field is set (``required_annotations``, ``alignment_namespaces``,
``alignment_min_coverage``) or, for GOV020, the policy file carried keys ontolint does not know.  GOV020
therefore needs no CLI-only plumbing: ``Policy.from_mapping`` records the unknown top-level keys, and the
rule reports them like any other finding (focus ``(policy)``), so selection, ``--fail-on`` and severity
overrides keep working.  An unsupported ``policy_version`` is not a finding: the file cannot be read at all,
so the CLI refuses it with ``GOV020`` on standard error and exit code 2.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from rdflib import Literal, URIRef
from rdflib.namespace import DC, DCTERMS, OWL, RDF, RDFS, SKOS
from rdflib.term import Node

from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity

from .owl import is_deprecated

if TYPE_CHECKING:
    from .runtime import RuleContext

POLICY_FOCUS = "(policy)"
FOCUS_FALLBACK = "urn:ontolint:graph"
MAX_KEY_CHARS = 80
_PREFIXES = (
    (str(RDFS), "rdfs:"),
    (str(SKOS), "skos:"),
    (str(DCTERMS), "dcterms:"),
    (str(DC), "dc:"),
    (str(OWL), "owl:"),
    (str(RDF), "rdf:"),
)
# Mapping predicates counted by ALIGN012 and ALIGN016.
MAPPING_PREDICATES = (
    SKOS.exactMatch,
    SKOS.closeMatch,
    SKOS.broadMatch,
    SKOS.narrowMatch,
    SKOS.relatedMatch,
    OWL.equivalentClass,
    OWL.equivalentProperty,
    OWL.sameAs,
)


def _spec(  # noqa: PLR0913, PLR0917 -- one positional field per RuleSpec column.
    rule_id: str, family: str, title: str, severity: Severity, suggestion: str, scope: RuleScope
) -> RuleSpec:
    category = "context-dependent" if rule_id == "ALIGN016" else "deterministic"
    return RuleSpec(rule_id, family, title, severity, suggestion, category, RuleBackend.RDFLIB, scope, "policy_rules")


SPECS: tuple[RuleSpec, ...] = (
    _spec(
        "GOV016",
        "GOV",
        "Term missing the annotations the policy requires",
        Severity.WARNING,
        "Add the missing annotations, or drop them from required_annotations in the policy file.",
        RuleScope.TERM,
    ),
    _spec(
        "GOV020",
        "GOV",
        "Policy file invalid or for a different policy-pack version",
        Severity.WARNING,
        "Remove or fix the unknown keys; the policy file only supports the documented keys and policy_version 1.",
        RuleScope.ONTOLOGY,
    ),
    _spec(
        "ALIGN012",
        "ALIGN",
        "Mapping target outside the declared alignment namespaces",
        Severity.WARNING,
        "Map to a term inside one of alignment_namespaces, or add the target's namespace to the policy file.",
        RuleScope.TERM,
    ),
    _spec(
        "ALIGN016",
        "ALIGN",
        "Mapping coverage below the expected ratio",
        Severity.INFO,
        "Align more classes and properties (skos:exactMatch, owl:equivalentClass) or lower alignment_min_coverage.",
        RuleScope.ONTOLOGY,
    ),
)


def _focus(ctx: RuleContext) -> str:
    return str(min(ctx.ontologies, key=str)) if ctx.ontologies else FOCUS_FALLBACK


def _compact(predicate: str) -> str:
    return next(
        (prefix + predicate[len(base) :] for base, prefix in _PREFIXES if predicate.startswith(base)), predicate
    )


def _has_value(ctx: RuleContext, term: URIRef, predicate: URIRef) -> bool:
    """Return whether ``term`` has a non-blank literal or an IRI value for ``predicate``."""
    for value in ctx.g.objects(term, predicate):
        if isinstance(value, URIRef) or (isinstance(value, Literal) and str(value).strip()):
            return True
    return False


def _individuals(ctx: RuleContext) -> Iterable[URIRef]:
    named = ctx.context.subjects_by_type.get(OWL.NamedIndividual, frozenset())
    return (s for s in named if isinstance(s, URIRef) and ctx.local(s))


def _required_annotations(ctx: RuleContext) -> None:
    required = dict(ctx.policy.required_annotations)
    if not required:
        return
    by_kind: dict[str, Iterable[URIRef]] = {
        "class": ctx.classes,
        "property": ctx.properties,
        "concept": ctx.concepts,
        "individual": _individuals(ctx),
    }
    needed: dict[URIRef, set[str]] = {}
    for kind, predicates in required.items():
        for term in by_kind[kind]:
            needed.setdefault(term, set()).update(predicates)
    for term, wanted in needed.items():
        if is_deprecated(ctx.g, term):
            continue
        absent = sorted(p for p in wanted if not _has_value(ctx, term, URIRef(p)))
        if absent:
            missing = sorted(map(_compact, absent))
            ctx.add(
                "GOV016",
                term,
                f"Missing required annotations: {', '.join(missing)}.",
                confidence="certain",
                subject=map(URIRef, absent),
            )


def _unknown_keys(ctx: RuleContext) -> None:
    for key in ctx.policy.unknown_keys:
        shown = key if len(key) <= MAX_KEY_CHARS else key[:MAX_KEY_CHARS] + "..."
        ctx.add(
            "GOV020", POLICY_FOCUS, f"Unknown policy key {shown!r} is ignored.", confidence="certain", subject=(key,)
        )


def _mappings(ctx: RuleContext, subjects: Iterable[Node]) -> Iterable[tuple[URIRef, URIRef, URIRef]]:
    """Yield ``(subject, predicate, target)`` for asserted mappings of ``subjects`` to a different IRI."""
    wanted = set(subjects)
    for predicate in MAPPING_PREDICATES:
        for subject, target in ctx.g.subject_objects(predicate):
            if subject in wanted and isinstance(subject, URIRef) and isinstance(target, URIRef) and target != subject:
                yield subject, predicate, target


def _mapping_namespaces(ctx: RuleContext) -> None:
    namespaces = ctx.policy.alignment_namespaces
    if not namespaces:
        return
    for term, predicate, target in _mappings(ctx, ctx.terms):
        if not str(target).startswith(namespaces):
            ctx.add(
                "ALIGN012",
                term,
                f"{_compact(str(predicate))} target {target} is outside the declared alignment namespaces.",
                confidence="certain",
                subject=(predicate, target),
            )


def _mapping_coverage(ctx: RuleContext) -> None:
    minimum = ctx.policy.alignment_min_coverage
    if minimum is None:
        return
    terms = {t for t in ctx.classes | ctx.properties if not is_deprecated(ctx.g, t)}
    total = len(terms)
    if total < ctx.policy.metric_min_sample:
        return
    mapped = len({s for s, _p, _t in _mappings(ctx, terms)})
    ratio = mapped / total
    if ratio < minimum:
        ctx.add(
            "ALIGN016",
            _focus(ctx),
            f"{mapped} of {total} classes and properties have a mapping ({ratio:.2f} < {minimum:.2f}).",
            subject=(),
        )


def run(ctx: RuleContext) -> None:
    """Run the policy-driven rules; each one is silent when its policy field is unset."""
    _required_annotations(ctx)
    _unknown_keys(ctx)
    _mapping_namespaces(ctx)
    _mapping_coverage(ctx)


__all__ = ["SPECS", "run"]
