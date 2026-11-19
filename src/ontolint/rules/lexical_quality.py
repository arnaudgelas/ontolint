"""Terminology and documentation quality rules: LEX010-LEX017, LEX019, LEX020, LEX022-LEX024.

LEX018 and LEX021 are implemented in ``iri_lexical_extras`` as markup and NFC checks: polysemy needs
NLP and domain judgement, and malformed language tags cannot be observed because RDFLib rejects
them at parse time.

Terms, labels, main labels, definitions and languages are those of ``lexical`` (read its docstring first);
"normalised" below means whitespace runs collapsed to one space and case-folded.  Every finding is
``heuristic`` unless said otherwise.  Specifications:

* **LEX010.** A label of an owned term that equals the term's local name, has no space, and is camelCase or
  contains ``_`` (``hasPart``, ``has_part``); one finding per label.  When at least
  ``MINIMUM_AGGREGATE_LABELLED_TERMS`` terms are labelled and more than ``AGGREGATE_PERCENT`` percent of them
  have a label equal to their local name (schema.org style), one finding on the ontology instead.  Excluded:
  a one-word label (``cell``).  Info.
* **LEX011.** A label (stripped first, so the ends are LEX005's) containing a line break, a tab or two
  whitespace characters in a row.  Confidence ``certain``.  Warning: such a label renders differently by tool.
* **LEX012.** A label, stripped, ending with ``.``, ``:``, ``;`` or ``,``.  Excluded: ``!``, ``?``, an ellipsis
  and any other mark.  Info: an abbreviation (``etc.``) is legitimate.
* **LEX013.** A value of a label predicate that is not a literal, or of a definition predicate that is neither a
  literal nor a node with ``rdf:value`` (the SKOS documentation-note pattern, SKOS Reference 7.1 and 7.3).
  RDFS 5.4.1 and 5.4.2 give ``rdfs:label`` and ``rdfs:comment`` the range ``rdfs:Literal``, and SKOS 5.3 S12
  makes the label properties' range the plain literals.  Confidence ``certain``.  Warning.
* **LEX014.** A label with a datatype other than ``xsd:string``, which includes ``rdf:langString`` written
  explicitly.  SKOS 5.3 S12: the range of the label properties is the plain literals (RDF 1.0), which RDF 1.1
  Concepts 3.3 replaces by ``xsd:string`` and ``rdf:langString``.  Confidence ``certain``.  Warning.
* **LEX015.** An alternative label (``skos:altLabel``, ``skos:hiddenLabel``) whose normalised text and language
  equal a main label of the same term.  SKOS Reference 5.4 S13: the three label properties are pairwise
  disjoint; the rule is wider (case and inner whitespace ignored) and does not report an ``skos:altLabel`` that
  equals a ``skos:hiddenLabel`` (known gap).  Info.
* **LEX016.** An alternative label that is a main label of another owned term, same normalised text and
  language.  One finding per alternative label, naming the first other term.  Excluded: a blank alternative
  label.  A deprecated term still owns its labels here (LEX004 skips it): known gap.  Warning: the synonym
  makes the lookup ambiguous.
* **LEX017.** A definition whose normalised text equals a label of the same term (any language, any label
  predicate but ``skos:altLabel``).  Blank definitions are LEX019's.  Info.
* **LEX019.** A definition value that is empty or only whitespace.  Confidence ``certain``.  Warning.  A padded
  but not blank definition is LEX025's.
* **LEX020.** Two or more owned terms with the same normalised non-blank definition and language; one finding
  per text, focused on the first term.  Deprecated terms are not excluded.  Warning.
* **LEX022.** A label whose language is not ``und`` and matches no configured language by RFC 4647 3.3.1
  (equal, or the configured range followed by ``-``).  Silent when no language is configured.  Info.
* **LEX023.** When a term has a non-blank definition, each configured language in which it has none (basic
  filtering); an untagged definition satisfies none, so a term with only untagged definitions is reported for
  every configured language.  A term with no definition is LEX002's.  Info.
* **LEX024.** More than one distinct ``skos:definition`` literal in one language on a term ("x" and
  "x"^^xsd:string are one literal, RDF 1.1 Concepts 3.3).  SKOS Reference 7.3 puts no limit on the number of
  definitions: this is a convention, unlike LEX003's S14.  Warning.

Fixtures: ``tests/rule_cases/lexical_quality.py`` and ``tests/test_lex_specification.py``.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rdflib import Literal, URIRef
from rdflib.namespace import RDF, SKOS, XSD
from rdflib.term import Node

from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity

from .support import local_name

if TYPE_CHECKING:
    from .runtime import RuleContext

# LEX015 and LEX016 compare these with a term's main labels (``RuleContext.main_label_predicates``).
ALTERNATIVE_LABELS = (SKOS.altLabel, SKOS.hiddenLabel)
CAMEL_CASE = re.compile(r"[a-z][A-Z]")
TERMINAL_PUNCTUATION = (".", ":", ";", ",")
ODD_WHITESPACE = re.compile(r"[\r\n\t]|\s{2,}")
# LEX010 collapses to one ontology-level finding when most labels repeat the local name (schema.org style).
AGGREGATE_PERCENT = 50
MINIMUM_AGGREGATE_LABELLED_TERMS = 10


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
    _verbatim_labels(ctx, texts)


def _literals(ctx: RuleContext, term: URIRef, predicates: tuple[URIRef, ...]) -> list[Literal]:
    found = {o for p in predicates for o in ctx.g.objects(term, p) if isinstance(o, Literal)}
    return sorted(found, key=lambda x: (x.language or "", x.datatype is not None, str(x.datatype), str(x)))


def _gather(ctx: RuleContext, term: URIRef) -> TermText:
    return TermText(
        labels=_literals(ctx, term, ctx.labels),
        primary=_literals(ctx, term, ctx.main_label_predicates(term)),
        alternatives=_literals(ctx, term, ALTERNATIVE_LABELS),
        definitions=_literals(ctx, term, ctx.descriptions),
        skos_definitions=_literals(ctx, term, (SKOS.definition,)),
    )


def _norm(literal: Literal) -> str:
    return " ".join(str(literal).split()).casefold()


def _language(literal: Literal) -> str:
    return (literal.language or "und").lower()


def _label_style(ctx: RuleContext, term: URIRef, text: TermText) -> None:
    for label in text.labels:
        value = str(label).strip()
        if ODD_WHITESPACE.search(value):
            ctx.add("LEX011", term, "Label contains line breaks, tabs or repeated whitespace.", confidence="certain")
        if value.endswith(TERMINAL_PUNCTUATION):
            ctx.add("LEX012", term, f"Label {value!r} ends with punctuation.", subject=(value,))
        if label.datatype is not None and label.datatype != XSD.string:
            ctx.add(
                "LEX014",
                term,
                f"Label {value!r} has datatype {label.datatype}.",
                confidence="certain",
                subject=(value, label.datatype),
            )


def _verbatim_labels(ctx: RuleContext, texts: dict[URIRef, TermText]) -> None:
    """LEX010: per term, or once for the ontology when more than half of the labelled terms repeat their name."""
    flagged: list[tuple[URIRef, str]] = []
    labelled = equal = 0
    for term, text in texts.items():
        name = local_name(term)
        values = [str(label).strip() for label in text.labels]
        if not values:
            continue
        labelled += 1
        equal += name in values
        flagged.extend(
            (term, value)
            for value in values
            if value and value == name and " " not in value and (CAMEL_CASE.search(value) or "_" in value)
        )
    if not flagged:
        return
    if labelled >= MINIMUM_AGGREGATE_LABELLED_TERMS and equal * 100 > labelled * AGGREGATE_PERCENT:
        focus = sorted(map(str, ctx.ontologies))[0] if ctx.ontologies else "(vocabulary)"
        ctx.add(
            "LEX010",
            focus,
            f"{len({term for term, _ in flagged})} of {labelled} labelled terms use their identifier as the label "
            f"(e.g. {flagged[0][1]!r}).",
            subject=(),
        )
        return
    for term, value in flagged:
        ctx.add("LEX010", term, f"Label {value!r} repeats the identifier.", subject=(value,))


def _label_types(ctx: RuleContext, term: URIRef) -> None:
    for predicate in (*ctx.labels, *ctx.descriptions):
        # SKOS documentation-note pattern: a definition may be a node carrying its text in rdf:value.
        node_allowed = predicate in ctx.descriptions and predicate not in ctx.labels
        for value in ctx.g.objects(term, predicate):
            if isinstance(value, Literal) or (node_allowed and (value, RDF.value, None) in ctx.g):
                continue
            ctx.add("LEX013", term, f"{predicate} value is not a literal.", confidence="certain", subject=(predicate,))


def _alternatives(ctx: RuleContext, term: URIRef, text: TermText) -> None:
    own = {(_norm(label), _language(label)) for label in text.primary}
    for alternative in text.alternatives:
        if (_norm(alternative), _language(alternative)) in own:
            ctx.add(
                "LEX015",
                term,
                f"Alternative label {str(alternative)!r} repeats the term's own label.",
                subject=(str(alternative),),
            )


def _definitions(ctx: RuleContext, term: URIRef, text: TermText) -> None:
    labels = {_norm(label) for label in text.labels}
    for definition in text.definitions:
        if not str(definition).strip():
            ctx.add("LEX019", term, "Definition is blank.", confidence="certain")
        elif _norm(definition) in labels:
            ctx.add("LEX017", term, f"Definition {str(definition)!r} repeats the label.", subject=(str(definition),))
    values: defaultdict[str, set[str]] = defaultdict(set)
    for definition in text.skos_definitions:
        values[_language(definition)].add(str(definition))  # "x" and "x"^^xsd:string are one literal
    for language, found in sorted(values.items()):
        if (count := len(found)) > 1:
            ctx.add("LEX024", term, f"{count} skos:definition values for language {language}.", subject=(language,))


def _language_policy(ctx: RuleContext, term: URIRef, text: TermText) -> None:
    allowed = ctx.policy.languages
    if not allowed:
        return
    for label in text.labels:
        tag = _language(label)
        if tag != "und" and not any(tag == lang or tag.startswith(lang + "-") for lang in allowed):
            ctx.add("LEX022", term, f"Label language {tag} is not among the configured languages.", subject=(tag,))
    present = {_language(d) for d in text.definitions if str(d).strip()}
    if present:
        for lang in allowed:
            if not any(tag == lang or tag.startswith(lang + "-") for tag in present):
                ctx.add("LEX023", term, f"Missing definition in language {lang}.", subject=(lang,))


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
                ctx.add(
                    "LEX016",
                    term,
                    f"Alternative label {str(alternative)!r} is the label of {other}.",
                    subject=(str(alternative),),
                )
    for (value, language), terms in sorted(definitions.items()):
        if len(terms) > 1:
            names = ", ".join(sorted(map(str, terms))[:5])
            ctx.add(
                "LEX020",
                sorted(map(str, terms))[0],
                f"Identical definition {value!r}@{language} on {names}.",
                subject=(value, language),
            )
