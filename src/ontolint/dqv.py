"""``--write-dqv``: the measurements of one run as W3C Data Quality Vocabulary (DQV) Turtle (``docs/dqv.md``).

The report is a projection of the quality snapshot (:mod:`ontolint.quality`), not a second measurement path: it
publishes the snapshot's measurements and nothing the snapshot does not hold, so the JSON report, the snapshot and
the DQV file are one set of values.  DQV has one ``dqv:value`` per measurement, so each kind of measurement
(:class:`~ontolint.models.MeasurementKind`) has a defined mapping:

* a ratio is two measurements, its numerator and its denominator, both ``xsd:integer``; the quotient is never
  published (it is not exact, and a denominator of 0 has none);
* a count is one ``xsd:integer`` measurement;
* a histogram is one ``xsd:integer`` measurement per bucket (a metric per depth, ``...:bucket:<value>``) and the
  number of terms it counts (``...:terms``), so an empty histogram is a taken measurement of 0 terms;
* a measurement that could not be taken is **not** published as a measurement, and never as 0; the run says so
  in an ``rdfs:comment`` (``not measured: <id>: <reason>``);
* ``by_namespace`` and the term sets of a coverage measure are not published: DQV carries values, not term lists.

The IRIs are in the ``urn:ontolint:`` namespace: it hosts nothing and promises nothing but stability (the
definition version is part of every metric IRI, so a changed definition is another metric).  Findings are not
published (no ``dqv:QualityAnnotation``).  The output is deterministic: a fixed vocabulary, sorted Turtle, no
blank node, and a timestamp only when ``SOURCE_DATE_EPOCH`` supplies one.  Every IRI and text is masked
(:func:`ontolint.redaction.redact_userinfo`) before it is written, and holds no control, format, surrogate,
private-use or separator character: a text writes each as an escape (:func:`ontolint.escaping.one_line`, as the text
report does) and an IRI as a percent-encoding (:func:`ontolint.escaping.safe_iri`).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from rdflib import OWL, RDF, RDFS, XSD, Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, PROV, SKOS

from .escaping import one_line, safe_iri
from .models import Measurement, MeasurementKind
from .redaction import redact_userinfo

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .quality import Snapshot
    from .rules.runtime import RuleContext

DQV = Namespace("http://www.w3.org/ns/dqv#")
URN = "urn:ontolint:"
"""The namespace of every IRI ontolint mints here: metrics, measurements, the run and the tool."""
EPOCH_VARIABLE = "SOURCE_DATE_EPOCH"
_HEX = 32
_DIGITS = frozenset("0123456789")


class DqvError(ValueError):
    """A DQV report that cannot be written: no single ontology to compute it on, or an unusable timestamp."""


@dataclass(frozen=True)
class Subject:
    """What the measurements are computed on: the ``owl:Ontology`` IRIs of the run and their version IRIs."""

    ontologies: tuple[str, ...]
    versions: tuple[str, ...]

    def computed_on(self) -> str:
        """The version IRI when the ontology has one, else its IRI; :class:`DqvError` if either is ambiguous."""
        if len(self.ontologies) != 1:
            found = "none" if not self.ontologies else f"{len(self.ontologies)}"
            raise DqvError(
                f"--write-dqv needs exactly one owl:Ontology IRI to compute the measurements on, found {found}"
            )
        if len(self.versions) > 1:
            raise DqvError(f"--write-dqv needs at most one owl:versionIRI on the ontology, found {len(self.versions)}")
        return self.versions[0] if self.versions else self.ontologies[0]


def subject(ctx: RuleContext) -> Subject:
    """The ontology IRIs of the run (the published ones, as the rules judge them) and their version IRIs, sorted."""
    ontologies = sorted(ctx.context.ontologies)
    versions = {str(v) for o in ontologies for v in ctx.g.objects(o, OWL.versionIRI) if isinstance(v, URIRef)}
    return Subject(tuple(str(o) for o in ontologies), tuple(sorted(versions)))


def generated_at(environ: Mapping[str, str]) -> str | None:
    """The ``SOURCE_DATE_EPOCH`` of ``environ`` as an ``xsd:dateTime`` in UTC; ``None`` when it is unset or empty.

    Raises :class:`DqvError` for a value that is not a whole number of seconds ``datetime`` can hold.
    """
    raw = environ.get(EPOCH_VARIABLE, "")
    if not raw:
        return None
    if not set(raw) <= _DIGITS:
        raise DqvError(f"{EPOCH_VARIABLE} is a number of seconds since the epoch, not {raw!r}")
    try:
        return datetime.fromtimestamp(int(raw), UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        raise DqvError(f"{EPOCH_VARIABLE} {raw!r} is outside the dates ontolint can write") from None


def _iri(text: str) -> URIRef:
    return URIRef(safe_iri(redact_userinfo(text)))


def _metric(m: Measurement, part: str) -> URIRef:
    """The IRI of a metric: the measurement's id and definition version, then which of its values."""
    return URIRef(f"{URN}metric:{m.id}:{m.definition_version}:{part}")


def _values(m: Measurement) -> list[tuple[str, str, int]]:
    """The published values of a taken measurement as ``(part, label, value)``, in publication order."""
    if m.kind is MeasurementKind.RATIO:
        return [("numerator", "numerator", m.numerator or 0), ("denominator", "denominator", m.denominator or 0)]
    if m.kind is MeasurementKind.COUNT:
        return [("value", "value", m.value or 0)]
    buckets = [(f"bucket:{depth}", f"terms with value {depth}", n) for depth, n in m.buckets]
    return [*buckets, ("terms", "terms counted", sum(n for _v, n in m.buckets))]


def _hash(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:_HEX]


def build(snapshot: Snapshot, on: Subject, *, tool_version: str, generated: str | None = None) -> Graph:
    """The DQV graph of ``snapshot``, computed on ``on``; raises :class:`DqvError` if ``on`` is ambiguous."""
    target = _iri(on.computed_on())
    entries = [e.measurement for e in snapshot.entries]
    identity = json.dumps(
        [target, tool_version, generated, snapshot.shaping.to_dict(), [m.to_dict() for m in entries]],
        sort_keys=True,
        default=str,
    )
    run = URIRef(f"{URN}run:{_hash(identity)}")
    tool = URIRef(f"{URN}tool:{tool_version}")
    g = Graph()
    for prefix, namespace in (
        ("dcterms", DCTERMS),
        ("dqv", DQV),
        ("prov", PROV),
        ("rdfs", RDFS),
        ("skos", SKOS),
        ("xsd", XSD),
    ):
        g.bind(prefix, namespace)
    g.add((tool, RDF.type, PROV.SoftwareAgent))
    g.add((tool, SKOS.prefLabel, Literal("ontolint")))
    g.add((tool, DCTERMS.hasVersion, Literal(tool_version)))
    g.add((run, RDF.type, PROV.Activity))
    g.add((run, PROV.wasAssociatedWith, tool))
    g.add((run, PROV.used, target))
    if generated is not None:
        g.add((run, PROV.endedAtTime, Literal(generated, datatype=XSD.dateTime)))
    for m in entries:
        if m.reason is not None:  # not taken: no measurement, and never a 0
            g.add((run, RDFS.comment, Literal(one_line(f"not measured: {m.id}: {m.reason}"))))
            continue
        for part, label, value in _values(m):
            metric = _metric(m, part)
            g.add((metric, RDF.type, DQV.Metric))
            g.add((metric, DCTERMS.identifier, Literal(f"{m.id}:{m.definition_version}:{part}")))
            g.add((metric, SKOS.prefLabel, Literal(f"{m.id}: {label}")))
            what = f"The {label} of {m.id} (definition version {m.definition_version}), over {m.population}"
            g.add((metric, RDFS.comment, Literal(f"{what}; docs/measurements.md.")))
            g.add((metric, DQV.expectedDataType, XSD.integer))
            node = URIRef(f"{URN}measurement:{_hash(str(run), str(metric))}")
            g.add((node, RDF.type, DQV.QualityMeasurement))
            g.add((node, DQV.computedOn, target))
            g.add((node, DQV.isMeasurementOf, metric))
            g.add((node, DQV.value, Literal(value, datatype=XSD.integer)))
            g.add((node, PROV.wasGeneratedBy, run))
            if generated is not None:
                g.add((node, PROV.generatedAtTime, Literal(generated, datatype=XSD.dateTime)))
    return g


def dumps(snapshot: Snapshot, on: Subject, *, tool_version: str, generated: str | None = None) -> str:
    """The report's text: Turtle, UTF-8, sorted by rdflib's serialiser, with a final newline."""
    return build(snapshot, on, tool_version=tool_version, generated=generated).serialize(format="turtle")
