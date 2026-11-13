"""W3C PROF profiles: find the SHACL validator a profile names, offline (``--shapes-from-profile``).

A profile (PROF, https://www.w3.org/TR/dx-prof/) lists its resources with ``prof:hasResource``; the one
with ``prof:hasRole role:validator`` is the validator, and its ``prof:hasArtifact`` is the IRI of the
shapes file (FAIR-IMPACT MOD: ``prof:hasArtifact <https://w3id.org/mod/dcat-profile/validator>``).  With
``--shapes-from-profile PROFILE`` that file is used as ``--shapes``, so the profile, not the command
line, says which shapes an ontology must meet.

The network is never used.  Each artifact IRI resolves, in this order, through the catalog next to the
profile (or ``--catalog``), through ``--import-dir`` (by ontology or version IRI), or to a file in the
profile's own directory named after the IRI's last path segment, with or without an RDF extension
(``https://…/validator`` → ``validator.ttl``).  The file must lie inside the import root, like an import (SEC009).
A descriptor whose ``dct:conformsTo`` names only other standards (ShEx, a JSON schema) is not SHACL and
is passed over with a note.  A profile that names no SHACL validator, or one that does not resolve, is a
configuration error: guessing would lint against no shapes and look like a pass.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import DCTERMS

from .imports import CATALOG_NAME, RDF_SUFFIXES, Catalog

PROF = Namespace("http://www.w3.org/ns/dx/prof/")
VALIDATOR_ROLE = URIRef("http://www.w3.org/ns/dx/prof/role/validator")
SHACL_STANDARDS = frozenset(
    {
        "https://www.w3.org/TR/shacl/",
        "http://www.w3.org/TR/shacl/",
        "https://www.w3.org/TR/shacl",
        "http://www.w3.org/TR/shacl",
        "http://www.w3.org/ns/shacl#",
        "http://www.w3.org/ns/shacl",
    }
)
"""``dct:conformsTo`` values that identify SHACL."""


class ProfileError(ValueError):
    """The profile names no SHACL validator, or one ontolint cannot find locally; a ``TOOL001`` failure."""


@dataclass(frozen=True)
class Validators:
    """The validator artifacts a profile names: the SHACL ones, and those passed over as another standard."""

    shacl: tuple[str, ...]
    other: tuple[str, ...]


def validator_artifacts(graph: Graph) -> Validators:
    """Every ``prof:hasArtifact`` IRI of a resource descriptor with the validator role, split by standard."""
    shacl: set[str] = set()
    other: set[str] = set()
    for descriptor in set(graph.subjects(PROF.hasRole, VALIDATOR_ROLE)):
        standards = {str(s) for s in graph.objects(descriptor, DCTERMS.conformsTo)}
        artifacts = {str(a) for a in graph.objects(descriptor, PROF.hasArtifact) if isinstance(a, URIRef)}
        (shacl if not standards or standards & SHACL_STANDARDS else other).update(artifacts)
    return Validators(tuple(sorted(shacl)), tuple(sorted(other - shacl)))


def _named_after(iri: str, directory: Path) -> Path | None:
    """The file in ``directory`` named after the last path segment of ``iri``, with or without an extension.

    Only an IRI with an authority (``https://host/…``) has path segments to name a file after; a URN does not.
    """
    parts = urlsplit(iri)
    segments = [s for s in unquote(parts.path).split("/") if s]
    if not parts.netloc or not segments or segments[-1] in (".", ".."):
        return None
    name = segments[-1]
    candidates = [name] if Path(name).suffix.lower() in RDF_SUFFIXES else [name + s for s in RDF_SUFFIXES]
    return next((directory / c for c in candidates if (directory / c).is_file()), None)


def resolve_artifact(
    iri: str, profile: Path, catalogs: Sequence[Catalog], import_dirs: Sequence[Catalog]
) -> Path | None:
    """The local file for validator ``iri``: a catalog entry, an ``--import-dir`` match, or a named sibling."""
    for catalog in catalogs:
        found = catalog.resolve(iri)
        if found is not None:
            return found
    for directory in import_dirs:
        if iri in directory.entries:
            return directory.entries[iri]
    return _named_after(iri, profile.parent)


def shapes_files(
    profile: Path, graph: Graph, catalogs: Sequence[Catalog], import_dirs: Sequence[Catalog]
) -> tuple[list[tuple[str, Path]], tuple[str, ...]]:
    """``(artifact IRI, file)`` for every SHACL validator of the profile, and the non-SHACL ones passed over.

    Raises :class:`ProfileError` when the profile names no SHACL validator or one does not resolve.
    """
    validators = validator_artifacts(graph)
    if not validators.shacl:
        passed = f" (passed over, not SHACL: {', '.join(validators.other)})" if validators.other else ""
        raise ProfileError(f"{profile} names no SHACL validator (prof:hasRole role:validator){passed}")
    found: list[tuple[str, Path]] = []
    for iri in validators.shacl:
        path = resolve_artifact(iri, profile, catalogs, import_dirs)
        if path is None or not path.is_file():
            raise ProfileError(
                f"the validator {iri} of {profile} has no local copy: map it in {CATALOG_NAME}, pass "
                f"--import-dir, or put it next to the profile as {_segment(iri)}.ttl"
            )
        found.append((iri, path))
    return found, validators.other


def _segment(iri: str) -> str:
    segments = [s for s in unquote(urlsplit(iri).path).split("/") if s]
    return segments[-1] if segments else "validator"
