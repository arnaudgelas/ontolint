"""Pattern libraries (``--pattern-library DIR``): read the member ontologies an index file describes.

A pattern library is an index ontology plus one ontology per pattern (MODL: ``modl.owl`` describes 31
patterns as individuals, and each pattern is its own file).  Nothing links the two by ``owl:imports``,
so linting files one by one cannot tell whether the index and the patterns agree.  With
``--pattern-library DIR`` the linted file is the index and every RDF file under ``DIR`` that declares an
``owl:Ontology`` is a member; rules ``LIB001``-``LIB003`` (:mod:`ontolint.rules.library`) compare them.

Members are read like ``--import-dir`` files: through the safe loader, inside the import root (SEC009),
at most ``max_imported_files`` of them (SEC015), never from the network.  The index itself is not a
member even when it lies under ``DIR``.  A file that does not parse is skipped with a ``TOOL008`` warning
(MODL: 12 of its 31 pattern files are not valid Turtle), and the rules then say that what they report
missing may be in one of those files; a file without an ``owl:Ontology`` is not a member.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Collection
from pathlib import Path

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DC, DCTERMS, OWL, RDF, RDFS, SKOS

from .imports import RDF_SUFFIXES
from .loader import InputRejected, LoadError, load_document
from .models import LibraryMember, PatternLibrary
from .paths import resolve_inputs
from .policy import Policy

OPLA_CORE = "http://ontologydesignpatterns.org/opla-core#"
NAME_PREDICATES = (
    URIRef(OPLA_CORE + "hasPatternName"),
    URIRef("http://ontologydesignpatterns.org/opla#hasPatternName"),
    RDFS.label,
    SKOS.prefLabel,
    DCTERMS.title,
    DC.title,
)
"""Header annotations that name a member ontology."""

_IRI_SCHEMES = ("http://", "https://", "urn:")


def _members_of(graph: Graph, item_display: str, item_uri: str) -> list[LibraryMember]:
    members: list[LibraryMember] = []
    for ontology in sorted(o for o in graph.subjects(RDF.type, OWL.Ontology) if isinstance(o, URIRef)):
        versions = {str(v) for v in graph.objects(ontology, OWL.versionIRI) if isinstance(v, URIRef)}
        names = sorted({str(n) for p in NAME_PREDICATES for n in graph.objects(ontology, p) if isinstance(n, Literal)})
        references = sorted(
            {
                (str(p), str(o))
                for p, o in graph.predicate_objects(ontology)
                if p != RDF.type
                and (isinstance(o, URIRef) or (isinstance(o, Literal) and str(o).startswith(_IRI_SCHEMES)))
                and " " not in str(o)
            }
        )
        members.append(
            LibraryMember(
                item_display,
                item_uri,
                str(ontology),
                frozenset({str(ontology), *versions}),
                tuple(names),
                tuple(references),
            )
        )
    return members


def load_library(directory: Path, policy: Policy, root: Path, exclude: Collection[Path] = ()) -> PatternLibrary:
    """Read the member ontologies under ``directory`` (not the files in ``exclude``, the linted index)."""
    base = directory.resolve()
    skip = {os.path.realpath(p) for p in exclude}
    candidates = sorted(
        p
        for p in base.rglob("*")
        if p.suffix.lower() in RDF_SUFFIXES and p.is_file() and os.path.realpath(p) not in skip
    )
    if len(candidates) > policy.max_imported_files:
        raise InputRejected(
            "SEC015",
            f"--pattern-library {directory} holds more than {policy.max_imported_files} files (max_imported_files)",
        )
    members: list[LibraryMember] = []
    unreadable: list[str] = []
    for path in candidates:
        item = resolve_inputs([str(path)], Path.cwd())[0]
        try:
            graph = load_document(item, policy, root).graph
        except InputRejected:
            raise
        except (LoadError, OSError) as exc:
            print(f"TOOL008: warning: {item.display} in the pattern library is skipped: {exc}", file=sys.stderr)
            unreadable.append(item.display)
            continue
        members += _members_of(graph, item.display, item.uri)
    return PatternLibrary(str(directory), tuple(members), tuple(unreadable))
