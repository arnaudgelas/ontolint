"""Label, definition, and naming-style rules: LEX001-LEX009."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import TYPE_CHECKING

from rdflib import Literal, URIRef
from rdflib.namespace import OWL, RDFS

from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity

from .support import DESCRIPTIONS, LABELS, MINIMUM_STYLE_SAMPLE_SIZE, local_name

if TYPE_CHECKING:
    from .runtime import RuleContext


type LabelIndex = defaultdict[tuple[str, str], set[URIRef]]


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
        Severity.WARNING,
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
        labels = {o for p in LABELS for o in g.objects(term, p) if isinstance(o, Literal)}
        if not labels and (term, OWL.deprecated, Literal(True)) not in g:
            ctx.add("LEX001", term, "Term has no label.", confidence="certain")
        if not any((term, p, None) in g for p in DESCRIPTIONS):
            ctx.add("LEX002", term, "Term has no description or definition.", confidence="certain")
        _language_checks(ctx, term, labels, label_index)
    return label_index


def _language_checks(ctx: RuleContext, term: URIRef, labels: set[Literal], label_index: LabelIndex) -> None:
    by_language: defaultdict[str, list[Literal]] = defaultdict(list)
    for o in labels:
        language = (o.language or "und").lower()
        by_language[language].append(o)
        if not str(o).strip() or str(o) != str(o).strip():
            ctx.add("LEX005", term, f"Blank or padded label: {str(o)!r}.", confidence="certain")
        label_index[(str(o).casefold().strip(), language)].add(term)
    for lang, literals in by_language.items():
        if len(literals) > 1:
            ctx.add("LEX003", term, f"{len(literals)} labels for language {lang}.")
    if len(by_language) > 1 and "und" in by_language:
        ctx.add("LEX006", term, "Mixed plain and language-tagged preferred labels.")
    for lang in ctx.policy.languages:
        if lang not in by_language:
            ctx.add("LEX008", term, f"Missing preferred label in language {lang}.")


def _duplicate_labels(ctx: RuleContext, label_index: LabelIndex) -> None:
    for (duplicate_label, lang), terms in label_index.items():
        if duplicate_label and len(terms) > 1:
            ctx.add(
                "LEX004",
                sorted(terms, key=str)[0],
                f"Duplicate label {duplicate_label!r}@{lang} for " + ", ".join(map(str, sorted(terms, key=str)[:5])),
            )


def _label_sort_key(label: Literal) -> tuple[str, str, str]:
    language = label.language if label.language is not None else ""
    datatype = str(label.datatype) if label.datatype is not None else ""
    return language, datatype, str(label)


def _capitalization(ctx: RuleContext) -> None:
    # Conventional capitalization is only a review hint, not a semantic rule.
    for term in ctx.classes | ctx.properties:
        style_labels = sorted(
            (label for label in ctx.g.objects(term, RDFS.label) if isinstance(label, Literal)),
            key=_label_sort_key,
        )
        label = style_labels[0] if style_labels else None
        if label and str(label) and str(label)[0].isalpha():
            if term in ctx.classes and str(label)[0].islower():
                ctx.add("LEX009", term, "Class label begins with lower case (style review).")
            if term in ctx.properties and str(label)[0].isupper():
                ctx.add("LEX009", term, "Property label begins with upper case (style review).")


def _naming_styles(ctx: RuleContext) -> None:
    # Naming is a configurable, non-blocking quality indicator.
    styles = Counter(
        "underscore" if "_" in n else "hyphen" if "-" in n else "camel" if re.search(r"[a-z][A-Z]", n) else "other"
        for n in (local_name(x) for x in ctx.terms)
    )
    meaningful = [(style, count) for style, count in styles.items() if style != "other" and count > 0]
    if len(meaningful) > 1 and len(ctx.terms) >= MINIMUM_STYLE_SAMPLE_SIZE:
        ctx.add("LEX007", "(vocabulary)", f"Mixed identifier styles: {dict(sorted(styles.items()))}.")
