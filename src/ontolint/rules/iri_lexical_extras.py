"""Extra heuristics: IRI015 (opaque and readable local names in one namespace), LEX018 and LEX021.

All three inspect only the asserted graph and never leave the process.  Their specifications:

* **IRI015.** Group the owned declared terms by namespace (the IRI minus its local name).  A local name
  is *opaque* when it is an optional prefix of up to eight letters, an optional ``_``, ``:`` or ``-``,
  then at least three digits (``T0001234``, ``BFO_0000001``); it is *readable* when it is letters,
  ``_`` and ``-`` only, starting with a letter, with three lower-case letters in a row (``hasPart``).
  Other names (``ab12``, empty) are not classified.  One finding per namespace that holds both kinds,
  focused on the namespace, unless the smaller kind is under 10% of the classified names.
* **LEX018.** A label of an owned term (``rdfs:label``, ``skos:prefLabel``, ``skos:altLabel`` and any
  configured extra label predicate) containing an XML/HTML tag (``<b>``, ``</b>``) or a named, decimal or
  hexadecimal character entity (``&amp;``, ``&#233;``).  A bare ``<``, ``>`` or ``&`` is plain text, and
  a trailing ``<word>`` disambiguator that is not an HTML tag name is allowed.  Comments and definitions
  are not labels and are not checked.
* **LEX021.** A label, on the same predicates as LEX018, that differs from its Unicode NFC normal form
  (for example a decomposed ``e`` plus combining acute accent).
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from typing import TYPE_CHECKING

from rdflib import Literal, URIRef
from rdflib.namespace import RDFS, SKOS

from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity

from .support import LABELS, local_name

if TYPE_CHECKING:
    from .runtime import RuleContext

OPAQUE_NAME = re.compile(r"^(?:[A-Za-z]{1,8}[_:-]?)?\d{3,}$")
READABLE_NAME = re.compile(r"^(?=.*[a-z]{3})[A-Za-z][A-Za-z_-]*$")
MARKUP = re.compile(r"</?[A-Za-z][^<>]*>|&(?:[A-Za-z][A-Za-z0-9]*|#\d+|#[xX][0-9A-Fa-f]+);")
LABEL_PREDICATES = (*LABELS, SKOS.altLabel, RDFS.label)
EXAMPLE_LIMIT = 3
# IRI015 needs a real mix: the minority kind must be at least this share of the named terms.
MINORITY_PERCENT = 10
# ``Gnathostomata <vertebrates>``: a trailing ``<word>`` after a space is a disambiguator, not markup.
DISAMBIGUATOR = re.compile(r"\s<([^<>/=&]+)>\s*$")
HTML_TAGS = frozenset(
    [
        "a",
        "abbr",
        "b",
        "big",
        "blockquote",
        "br",
        "code",
        "div",
        "em",
        "font",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "i",
        "img",
        "li",
        "ol",
        "p",
        "pre",
        "s",
        "small",
        "span",
        "strike",
        "strong",
        "sub",
        "sup",
        "table",
        "td",
        "th",
        "tr",
        "tt",
        "u",
        "ul",
    ]
)


def _spec(rule_id: str, title: str, severity: Severity, suggestion: str, scope: RuleScope) -> RuleSpec:
    family = rule_id[:3]
    return RuleSpec(
        rule_id, family, title, severity, suggestion, "heuristic", RuleBackend.RDFLIB, scope, "iri_lexical_extras"
    )


SPECS: tuple[RuleSpec, ...] = (
    _spec(
        "IRI015",
        "Opaque and readable local names mixed in one namespace",
        Severity.INFO,
        "Use one naming scheme per namespace: either opaque numeric identifiers or readable names.",
        RuleScope.VOCABULARY,
    ),
    _spec(
        "LEX018",
        "Label contains markup or character entities",
        Severity.WARNING,
        "Store labels as plain text; remove HTML/XML tags and character entities.",
        RuleScope.TERM,
    ),
    _spec(
        "LEX021",
        "Label is not Unicode NFC-normalized",
        Severity.INFO,
        "Normalize labels to Unicode NFC so equal-looking labels compare equal.",
        RuleScope.TERM,
    ),
)


def run(ctx: RuleContext) -> None:
    """Run IRI015, LEX018 and LEX021."""
    _mixed_naming(ctx)
    _label_text(ctx)


def _namespace(iri: str) -> str:
    return iri[: len(iri) - len(local_name(URIRef(iri)))]


def _mixed_naming(ctx: RuleContext) -> None:
    opaque: defaultdict[str, list[str]] = defaultdict(list)
    readable: defaultdict[str, list[str]] = defaultdict(list)
    for term in ctx.terms:
        name = local_name(term)
        if OPAQUE_NAME.match(name):
            opaque[_namespace(str(term))].append(name)
        elif READABLE_NAME.match(name):
            readable[_namespace(str(term))].append(name)
    for namespace in sorted(opaque.keys() & readable.keys()):
        minority = min(len(opaque[namespace]), len(readable[namespace]))
        if minority * 100 < MINORITY_PERCENT * (len(opaque[namespace]) + len(readable[namespace])):
            continue
        first_opaque = sorted(opaque[namespace])[:EXAMPLE_LIMIT]
        first_readable = sorted(readable[namespace])[:EXAMPLE_LIMIT]
        ctx.add(
            "IRI015",
            namespace,
            f"Namespace mixes {len(opaque[namespace])} opaque local names (e.g. {', '.join(first_opaque)}) "
            f"and {len(readable[namespace])} readable ones (e.g. {', '.join(first_readable)}).",
        )


def _without_disambiguator(value: str) -> str:
    match = DISAMBIGUATOR.search(value)
    if match and match.group(1).strip().casefold() not in HTML_TAGS:
        return value[: match.start()]
    return value


def _label_text(ctx: RuleContext) -> None:
    by_predicate = ctx.context.subjects_by_predicate
    for predicate in dict.fromkeys((*LABEL_PREDICATES, *ctx.labels)):
        for term in sorted(by_predicate.get(predicate, frozenset()) & ctx.terms, key=str):
            for label in sorted((o for o in ctx.g.objects(term, predicate) if isinstance(o, Literal)), key=str):
                value = str(label)
                if MARKUP.search(_without_disambiguator(value)):
                    ctx.add("LEX018", term, f"Label {value!r} contains markup or a character entity.")
                if unicodedata.normalize("NFC", value) != value:
                    ctx.add("LEX021", term, f"Label {value!r} is not Unicode NFC-normalized.")
