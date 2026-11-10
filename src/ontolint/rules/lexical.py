"""Label, definition, and naming-style rules: LEX001-LEX009."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import TYPE_CHECKING

from rdflib import Literal, URIRef
from rdflib.namespace import OWL, RDFS, SKOS

from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity

from .iri_lexical_extras import OPAQUE_NAME
from .support import MINIMUM_STYLE_SAMPLE_SIZE, local_name

if TYPE_CHECKING:
    from .runtime import RuleContext


type LabelIndex = defaultdict[tuple[str, str, str], set[URIRef]]

# LEX009 judges capitalization against the convention the ontology itself follows: it only reports
# deviations from a clear majority (at least ``MAJORITY_PERCENT`` percent of at least
# ``MINIMUM_CAPITALIZATION_SAMPLE`` labels of one term kind).
MINIMUM_CAPITALIZATION_SAMPLE = 10
MAJORITY_PERCENT = 80
LABEL_LIKE = ("label", "name", "title")
# LEX002 also accepts SKOS documentation notes; other rules keep ``ctx.descriptions`` (definitions only).
DOCUMENTATION_NOTES = (SKOS.scopeNote, SKOS.note)
# Collections (microthesauri) and schemes are named like the concepts they group, so LEX004 skips them.
GROUPING_TYPES = frozenset({SKOS.Collection, SKOS.ConceptScheme})


SPECS: tuple[RuleSpec, ...] = (
    RuleSpec(
        "LEX001",
        "LEX",
        "Term without label",
        Severity.WARNING,
        "Add rdfs:label or an accepted alternative to the declared local term.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "lexical",
    ),
    RuleSpec(
        "LEX002",
        "LEX",
        "Term without definition",
        Severity.INFO,
        "Add a natural-language definition (rdfs:comment, skos:definition, or dcterms:description).",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "lexical",
    ),
    RuleSpec(
        "LEX003",
        "LEX",
        "Multiple labels in one language",
        Severity.WARNING,
        "Use one language-specific primary label per term and language.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "lexical",
    ),
    RuleSpec(
        "LEX004",
        "LEX",
        "Duplicate label across terms",
        Severity.INFO,
        "Differentiate labels or formally document and link genuinely equivalent concepts.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.VOCABULARY,
        "lexical",
    ),
    RuleSpec(
        "LEX005",
        "LEX",
        "Blank or whitespace-padded label",
        Severity.WARNING,
        "Trim whitespace or replace empty labels.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "lexical",
    ),
    RuleSpec(
        "LEX006",
        "LEX",
        "Mixed plain and language-tagged labels",
        Severity.INFO,
        "Use a consistent label language-tag policy.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.VOCABULARY,
        "lexical",
    ),
    RuleSpec(
        "LEX007",
        "LEX",
        "Mixed identifier naming styles",
        Severity.INFO,
        "Use one configured naming convention for comparable term identifiers.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.VOCABULARY,
        "lexical",
    ),
    RuleSpec(
        "LEX008",
        "LEX",
        "Missing label in a required language",
        Severity.INFO,
        "Add the required preferred language label.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "lexical",
    ),
    RuleSpec(
        "LEX009",
        "LEX",
        "Label capitalization inconsistent with term kind",
        Severity.INFO,
        "Review capitalization and wording relative to the namespace policy.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "lexical",
    ),
)


def run(ctx: RuleContext) -> None:
    """Run all lexical rules."""
    label_index = _term_labels(ctx)
    _duplicate_labels(ctx, label_index)
    _capitalization(ctx)
    _naming_styles(ctx)


def _term_labels(ctx: RuleContext) -> LabelIndex:
    """Check per-term labels and descriptions; return an index of normalized labels."""
    g = ctx.g
    label_index: LabelIndex = defaultdict(set)
    for term in sorted(ctx.terms, key=str):
        labels = {o for p in ctx.labels for o in g.objects(term, p) if isinstance(o, Literal)}
        if not labels and (term, OWL.deprecated, Literal(True)) not in g:
            ctx.add("LEX001", term, "Term has no label.", confidence=_missing_label_confidence(ctx, term))
        if not any((term, p, None) in g for p in (*ctx.descriptions, *DOCUMENTATION_NOTES)):
            ctx.add("LEX002", term, "Term has no description or definition.", confidence="certain")
        _language_checks(ctx, term, labels, label_index)
    return label_index


def _missing_label_confidence(ctx: RuleContext, term: URIRef) -> str:
    """Return ``certain`` unless the term has a literal under a label-like predicate we do not recognise."""
    for predicate, value in ctx.g.predicate_objects(term):
        if (
            isinstance(value, Literal)
            and predicate not in ctx.labels
            and any(word in str(predicate).rsplit("/", 1)[-1].rsplit("#", 1)[-1].casefold() for word in LABEL_LIKE)
        ):
            return "heuristic"
    return "certain"


def _language_checks(ctx: RuleContext, term: URIRef, labels: set[Literal], label_index: LabelIndex) -> None:
    by_language: defaultdict[str, list[Literal]] = defaultdict(list)
    for o in labels:
        language = (o.language or "und").lower()
        by_language[language].append(o)
        if not str(o).strip() or str(o) != str(o).strip():
            ctx.add("LEX005", term, f"Blank or padded label: {str(o)!r}.", confidence="certain", subject=(str(o),))
        text = str(o).strip()
        if _indexable_label(ctx, term, text):
            for kind in _kinds(ctx, term):
                label_index[(text, language, kind)].add(term)
    _multiple_labels(ctx, term, labels)
    if len(by_language) > 1 and "und" in by_language:
        ctx.add("LEX006", term, "Mixed plain and language-tagged preferred labels.")
    for lang in ctx.policy.languages:
        if lang not in by_language:
            ctx.add("LEX008", term, f"Missing preferred label in language {lang}.", subject=(lang,))


def _multiple_labels(ctx: RuleContext, term: URIRef, labels: set[Literal]) -> None:
    """LEX003 counts one label family: skos:prefLabel, or the other label properties when there is none.

    A notation-prefixed rdfs:label next to a prefLabel is the same label, not a second one.
    """
    preferred = {o for o in ctx.g.objects(term, SKOS.prefLabel) if isinstance(o, Literal)}
    family: defaultdict[str, int] = defaultdict(int)
    for o in preferred or labels:
        family[(o.language or "und").lower()] += 1
    for lang, count in family.items():
        if count > 1:
            ctx.add("LEX003", term, f"{count} labels for language {lang}.", subject=(lang,))


def _kinds(ctx: RuleContext, term: URIRef) -> tuple[str, ...]:
    kinds = tuple(kind for kind, group in (("class", ctx.classes), ("property", ctx.properties)) if term in group)
    return kinds or ("other",)


def _indexable_label(ctx: RuleContext, term: URIRef, text: str) -> bool:
    """Deprecated terms, collections, schemes and labels starting with ``obsolete`` legitimately repeat labels."""
    return (
        bool(text)
        and not text.casefold().startswith("obsolete")
        and (term, OWL.deprecated, Literal(True)) not in ctx.g
        and not ctx.context.types_by_subject.get(term, frozenset()) & GROUPING_TYPES
    )


def _duplicate_labels(ctx: RuleContext, label_index: LabelIndex) -> None:
    for (duplicate_label, lang, kind), terms in sorted(label_index.items()):
        if len(terms) > 1:
            ctx.add(
                "LEX004",
                sorted(terms, key=str)[0],
                f"Duplicate label {duplicate_label!r}@{lang} for " + ", ".join(map(str, sorted(terms, key=str)[:5])),
                related=terms,
                subject=(duplicate_label, lang, kind),
            )


def _label_sort_key(label: Literal) -> tuple[str, str, str]:
    language = label.language if label.language is not None else ""
    datatype = str(label.datatype) if label.datatype is not None else ""
    return language, datatype, str(label)


def _first_label(ctx: RuleContext, term: URIRef) -> str:
    labels = sorted(
        (label for label in ctx.g.objects(term, RDFS.label) if isinstance(label, Literal)),
        key=_label_sort_key,
    )
    return str(labels[0]) if labels else ""


def _capitalization(ctx: RuleContext) -> None:
    # Conventions differ per ontology (OBO labels are lower case, FOAF's are sentence case), so only
    # labels deviating from a clear majority of the ontology's own labels are reported.
    for kind, terms in (("Class", ctx.classes), ("Property", ctx.properties)):
        initials: dict[URIRef, str] = {}
        for term in sorted(terms, key=str):
            label = _first_label(ctx, term)
            if label and label[0].isalpha():
                initials[term] = "upper" if label[0].isupper() else "lower"
        total = len(initials)
        if total < MINIMUM_CAPITALIZATION_SAMPLE:
            continue
        counts = Counter(initials.values())
        dominant, count = counts.most_common(1)[0]
        if count * 100 < total * MAJORITY_PERCENT:
            continue
        for term, case in initials.items():
            if case != dominant:
                ctx.add(
                    "LEX009",
                    term,
                    f"{kind} label begins with {case} case, but {count} of {total} {kind.lower()} labels "
                    f"begin with {dominant} case (style review).",
                    subject=(kind,),
                )


def _naming_styles(ctx: RuleContext) -> None:
    # Naming is a configurable, non-blocking quality indicator.
    names = [n for n in (local_name(x) for x in ctx.terms) if not OPAQUE_NAME.match(n)]
    styles = Counter(
        "underscore" if "_" in n else "hyphen" if "-" in n else "camel" if re.search(r"[a-z][A-Z]", n) else "other"
        for n in names
    )
    meaningful = [style for style in styles if style != "other"]
    if len(meaningful) > 1 and len(names) >= MINIMUM_STYLE_SAMPLE_SIZE:
        ctx.add("LEX007", "(vocabulary)", f"Mixed identifier styles: {dict(sorted(styles.items()))}.", subject=())
