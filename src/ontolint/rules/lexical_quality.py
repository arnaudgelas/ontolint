"""Terminology and documentation quality rules: LEX010-LEX017, LEX019, LEX020, LEX022-LEX024.

LEX018 (polysemy / merged ideas) needs NLP and domain judgement, and LEX021 (malformed language
tags) cannot be observed because RDFLib rejects such tags at parse time, so both stay proposed.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rdflib import Literal, URIRef
from rdflib.namespace import RDFS, SKOS, XSD
from rdflib.term import Node

from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity

from .support import DESCRIPTIONS, LABELS, local_name

if TYPE_CHECKING:
    from .runtime import RuleContext

ALTERNATIVE_LABELS = (SKOS.altLabel, SKOS.hiddenLabel)
PRIMARY_LABELS = (RDFS.label, SKOS.prefLabel)
CAMEL_CASE = re.compile(r"[a-z][A-Z]")
TERMINAL_PUNCTUATION = (".", ":", ";", ",")
ODD_WHITESPACE = re.compile(r"[\r\n\t]|\s{2,}")


def _spec(rule_id: str, title: str, severity: Severity, suggestion: str, scope: RuleScope) -> RuleSpec:
    return RuleSpec(
        rule_id, "LEX", title, severity, suggestion, "heuristic", RuleBackend.RDFLIB, scope, "lexical_quality"
    )


SPECS: tuple[RuleSpec, ...] = (
    _spec(
        "LEX010",
        "Label is a verbatim identifier",
        Severity.INFO,
        "Write a human-readable label (words separated by spaces) instead of repeating the identifier.",
        RuleScope.TERM,
    ),
    _spec(
        "LEX011",
        "Label contains line breaks, tabs or repeated whitespace",
        Severity.WARNING,
        "Use single spaces inside labels.",
        RuleScope.TERM,
    ),
    _spec(
        "LEX012",
        "Label ends with punctuation",
        Severity.INFO,
        "Remove trailing punctuation such as '.', ':', ';' or ',' from labels.",
        RuleScope.TERM,
    ),
    _spec(
        "LEX013",
        "Label or definition is not a literal",
        Severity.WARNING,
        "Use a literal value for labels and definitions; link resources with a different property.",
        RuleScope.TERM,
    ),
    _spec(
        "LEX014",
        "Label literal has a non-string datatype",
        Severity.WARNING,
        "Use plain or language-tagged string literals for labels.",
        RuleScope.TERM,
    ),
    _spec(
        "LEX015",
        "Alternative label repeats the preferred label",
        Severity.INFO,
        "Remove alternative labels that equal the term's own label in the same language.",
        RuleScope.TERM,
    ),
    _spec(
        "LEX016",
        "Alternative label is another term's label",
        Severity.WARNING,
        "Resolve the overlap: relate the terms or remove the conflicting synonym.",
        RuleScope.VOCABULARY,
    ),
    _spec(
        "LEX017",
        "Definition repeats the label",
        Severity.INFO,
        "Write a definition that says more than the label.",
        RuleScope.TERM,
    ),
    _spec(
        "LEX019",
        "Blank definition",
        Severity.WARNING,
        "Provide definition text or remove the empty annotation.",
        RuleScope.TERM,
    ),
    _spec(
        "LEX020",
        "Identical definition on several terms",
        Severity.WARNING,
        "Write a distinguishing definition for each term.",
        RuleScope.VOCABULARY,
    ),
    _spec(
        "LEX022",
        "Label in a language outside the configured languages",
        Severity.INFO,
        "Use a configured language tag or extend the language policy.",
        RuleScope.TERM,
    ),
    _spec(
        "LEX023",
        "Missing definition in a required language",
        Severity.INFO,
        "Add the definition in every configured language, or none.",
        RuleScope.TERM,
    ),
    _spec(
        "LEX024",
        "Several skos:definition values in one language",
        Severity.WARNING,
        "Keep one skos:definition per language and term.",
        RuleScope.TERM,
    ),
)


@dataclass
class TermText:
    """Annotation values of one term, gathered once."""

    labels: list[Literal] = field(default_factory=list[Literal])
    primary: list[Literal] = field(default_factory=list[Literal])
    alternatives: list[Literal] = field(default_factory=list[Literal])
    definitions: list[Literal] = field(default_factory=list[Literal])
    skos_definitions: list[Literal] = field(default_factory=list[Literal])


def run(ctx: RuleContext) -> None:
    """Run every terminology and documentation rule."""
    texts = {term: _gather(ctx, term) for term in sorted(ctx.terms, key=str)}
    for term, text in texts.items():
        _label_style(ctx, term, text)
        _label_types(ctx, term)
        _alternatives(ctx, term, text)
        _definitions(ctx, term, text)
        _language_policy(ctx, term, text)
    _cross_term(ctx, texts)


def _literals(ctx: RuleContext, term: URIRef, predicates: tuple[URIRef, ...]) -> list[Literal]:
    found = {o for p in predicates for o in ctx.g.objects(term, p) if isinstance(o, Literal)}
    return sorted(found, key=lambda x: (x.language or "", x.datatype is not None, str(x.datatype), str(x)))


def _gather(ctx: RuleContext, term: URIRef) -> TermText:
    return TermText(
        labels=_literals(ctx, term, LABELS),
        primary=_literals(ctx, term, PRIMARY_LABELS),
        alternatives=_literals(ctx, term, ALTERNATIVE_LABELS),
        definitions=_literals(ctx, term, DESCRIPTIONS),
        skos_definitions=_literals(ctx, term, (SKOS.definition,)),
    )


def _norm(literal: Literal) -> str:
    return " ".join(str(literal).split()).casefold()


def _language(literal: Literal) -> str:
    return (literal.language or "und").lower()


def _label_style(ctx: RuleContext, term: URIRef, text: TermText) -> None:
    name = local_name(term)
    for label in text.labels:
        value = str(label).strip()
        if value and value == name and " " not in value and (CAMEL_CASE.search(value) or "_" in value):
            ctx.add("LEX010", term, f"Label {value!r} repeats the identifier.")
        if ODD_WHITESPACE.search(value):
            ctx.add("LEX011", term, "Label contains line breaks, tabs or repeated whitespace.", confidence="certain")
        if value.endswith(TERMINAL_PUNCTUATION):
            ctx.add("LEX012", term, f"Label {value!r} ends with punctuation.")
        if label.datatype is not None and label.datatype != XSD.string:
            ctx.add("LEX014", term, f"Label {value!r} has datatype {label.datatype}.", confidence="certain")


def _label_types(ctx: RuleContext, term: URIRef) -> None:
    for predicate in (*LABELS, *DESCRIPTIONS):
        for value in ctx.g.objects(term, predicate):
            if not isinstance(value, Literal):
                ctx.add("LEX013", term, f"{predicate} value is not a literal.", confidence="certain")


def _alternatives(ctx: RuleContext, term: URIRef, text: TermText) -> None:
    own = {(_norm(label), _language(label)) for label in text.primary}
    for alternative in text.alternatives:
        if (_norm(alternative), _language(alternative)) in own:
            ctx.add("LEX015", term, f"Alternative label {str(alternative)!r} repeats the term's own label.")


def _definitions(ctx: RuleContext, term: URIRef, text: TermText) -> None:
    labels = {_norm(label) for label in text.labels}
    for definition in text.definitions:
        if not str(definition).strip():
            ctx.add("LEX019", term, "Definition is blank.", confidence="certain")
        elif _norm(definition) in labels:
            ctx.add("LEX017", term, f"Definition {str(definition)!r} repeats the label.")
    counts: defaultdict[str, int] = defaultdict(int)
    for definition in text.skos_definitions:
        counts[_language(definition)] += 1
    for language, count in sorted(counts.items()):
        if count > 1:
            ctx.add("LEX024", term, f"{count} skos:definition values for language {language}.")


def _language_policy(ctx: RuleContext, term: URIRef, text: TermText) -> None:
    allowed = ctx.policy.languages
    if not allowed:
        return
    for label in text.labels:
        tag = _language(label)
        if tag != "und" and not any(tag == lang or tag.startswith(lang + "-") for lang in allowed):
            ctx.add("LEX022", term, f"Label language {tag} is not among the configured languages.")
    present = {_language(d) for d in text.definitions if str(d).strip()}
    if present:
        for lang in allowed:
            if not any(tag == lang or tag.startswith(lang + "-") for tag in present):
                ctx.add("LEX023", term, f"Missing definition in language {lang}.")


def _cross_term(ctx: RuleContext, texts: dict[URIRef, TermText]) -> None:
    owners: defaultdict[tuple[str, str], set[URIRef]] = defaultdict(set)
    definitions: defaultdict[tuple[str, str], set[URIRef]] = defaultdict(set)
    for term, text in texts.items():
        for label in text.primary:
            owners[(_norm(label), _language(label))].add(term)
        for definition in text.definitions:
            if str(definition).strip():
                definitions[(_norm(definition), _language(definition))].add(term)
    for term, text in texts.items():
        for alternative in text.alternatives:
            others = owners.get((_norm(alternative), _language(alternative)), set()) - {term}
            if _norm(alternative) and others:
                other: Node = sorted(others, key=str)[0]
                ctx.add("LEX016", term, f"Alternative label {str(alternative)!r} is the label of {other}.")
    for (value, language), terms in sorted(definitions.items()):
        if len(terms) > 1:
            names = ", ".join(sorted(map(str, terms))[:5])
            ctx.add("LEX020", sorted(map(str, terms))[0], f"Identical definition {value!r}@{language} on {names}.")
