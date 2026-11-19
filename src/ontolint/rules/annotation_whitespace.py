"""LEX025: whitespace-padded annotation values.

* **LEX025.** A string literal (plain, language-tagged or ``xsd:string``) whose lexical form starts or ends
  with whitespace (anything ``str.strip()`` removes, a no-break space included), used as the object of an
  annotation property on an owned IRI subject.  An annotation property is one declared ``owl:AnnotationProperty``
  in the graph, a documentation predicate (``rdfs:comment``, ``skos:definition``, ``dcterms:description``,
  ``obo:IAO_0000115`` and the other definition predicates, plus any configured extra definition predicate and
  the predicates below them), a SKOS note or ``skos:altLabel`` / ``skos:hiddenLabel``, ``dcterms:title``,
  ``dc:title`` or an ``oboInOwl`` synonym.  The label predicates (``rdfs:label``, ``skos:prefLabel``, the
  configured extra label predicates and everything below them) are left to LEX005, so a label is never
  reported twice, and a blank value of a definition predicate is left to LEX019.  One finding per property
  and literal on a subject, so the same padded text under two properties is two findings.  Excluded: a
  subject that is a blank node or not owned, a non-string datatype and an annotation under an undeclared custom
  predicate (known gap: no declaration, no finding).  ``skos:hiddenLabel`` and ``skos:altLabel`` are judged here,
  since they are no label of LEX005.  Confidence ``certain``.  Warning: RDF 1.1 Concepts 3.3 compares lexical forms
  character by character, so a padded value is a different literal from the trimmed one and every consumer that
  matches on text sees two values.

Fixtures: ``tests/rule_cases/lexical_quality.py`` and ``tests/test_lex_specification.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rdflib import Literal, URIRef
from rdflib.namespace import DC, DCTERMS, OWL, RDF, RDFS, SKOS, XSD

from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity

from .support import ntriples_literal, quoted_text, term_text

if TYPE_CHECKING:
    from .runtime import RuleContext

OBO_IN_OWL = "http://www.geneontology.org/formats/oboInOwl#"
# Annotation predicates used without a declaration in most vocabularies.  A declared owl:AnnotationProperty
# and the definition predicates of the context are added on top.
WELL_KNOWN = (
    RDFS.comment,
    SKOS.altLabel,
    SKOS.hiddenLabel,
    SKOS.note,
    SKOS.changeNote,
    SKOS.editorialNote,
    SKOS.example,
    SKOS.historyNote,
    SKOS.scopeNote,
    DCTERMS.title,
    DC.title,
    *(
        URIRef(OBO_IN_OWL + name)
        for name in ("hasSynonym", *(f"has{k}Synonym" for k in ("Exact", "Broad", "Narrow", "Related")))
    ),
)
STRING_TYPES = (None, XSD.string, RDF.langString)
MAX_SHOWN = 80

SPECS: tuple[RuleSpec, ...] = (
    RuleSpec(
        "LEX025",
        "LEX",
        "Whitespace-padded annotation value",
        Severity.WARNING,
        "Trim the leading and trailing whitespace of the annotation value.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "annotation_whitespace",
    ),
)


def run(ctx: RuleContext) -> None:
    """Report padded values of annotation properties other than labels."""
    labels = set(ctx.labels) | set(ctx.preferred_labels)
    declared = {s for s in ctx.g.subjects(RDF.type, OWL.AnnotationProperty) if isinstance(s, URIRef)}
    predicates = (declared | set(WELL_KNOWN) | set(ctx.descriptions)) - labels
    for predicate in sorted(predicates, key=str):
        blank_is_lex019 = predicate in ctx.descriptions
        for subject, value in sorted(
            ctx.g.subject_objects(predicate),
            key=lambda so: (str(so[0]), ntriples_literal(so[1]) if isinstance(so[1], Literal) else ""),
        ):
            if not isinstance(subject, URIRef) or not isinstance(value, Literal) or not ctx.local(subject):
                continue
            text = str(value)
            if value.datatype not in STRING_TYPES or text == text.strip():
                continue
            if blank_is_lex019 and not text.strip():
                continue
            ctx.add(
                "LEX025",
                subject,
                f"{term_text(predicate)} value {quoted_text(value, MAX_SHOWN)} has leading or trailing whitespace.",
                confidence="certain",
                subject=(predicate, ntriples_literal(value)),
            )
