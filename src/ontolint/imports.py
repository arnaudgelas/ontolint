"""Offline ``owl:imports`` closure: resolve imports to local files through an OASIS XML catalog.

A modular ontology is often an umbrella file with no terms of its own that ``owl:imports`` its modules,
and an OASIS XML catalog (``catalog-v001.xml``, the Protege, ROBOT and ODK convention) maps each module
IRI to a file.  Linting the umbrella alone checks nothing, so with ``--follow-imports`` (or
``--catalog FILE``) the CLI loads the whole closure into one graph.

The network is never used.  An import resolves only through the catalog (``uri`` entries, also inside
``group``, and ``rewriteURI`` prefixes) or as a ``file:`` IRI; anything else stays unresolved and is
reported by SEC007.  Every resolved file must lie inside the import root (the catalog's directory, or the
input's directory without a catalog) after symlinks are followed (SEC009); each file passes the ordinary
safe loader with its per-file limits; and the closure as a whole is bounded by ``max_import_depth``,
``max_imported_files`` and ``max_triples`` (SEC015).  Cycles terminate and a file reached twice is loaded
once.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET  # noqa: S405 -- the catalog passes the DTD/entity preflight first.
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF

from .loader import InputRejected, LoadedGraph, Module, dtd_problem, load_document
from .paths import InputFile, resolve_inputs
from .policy import Policy

CATALOG_NAME = "catalog-v001.xml"
_CATALOG_NS = "{urn:oasis:names:tc:entity:xmlns:xml:catalog}"


class CatalogError(ValueError):
    """The catalog file is not a readable OASIS XML catalog; a configuration error (``TOOL001``)."""


# gremlin: pardon[equivalent] nothing mutates a catalog; frozen only guards against it
@dataclass(frozen=True)
class Catalog:
    """IRI-to-file mappings from one OASIS XML catalog, and the directory every resolved file must stay in."""

    root: Path
    entries: dict[str, Path]
    rewrites: tuple[tuple[str, Path], ...] = ()

    def resolve(self, iri: str) -> Path | None:
        """The local file for ``iri``: an exact entry, else the longest ``rewriteURI`` prefix, else a file IRI."""
        if iri in self.entries:
            return self.entries[iri]
        for prefix, target in self.rewrites:  # longest prefix first
            if iri.startswith(prefix):
                return Path(os.path.normpath(target / iri[len(prefix) :]))
        return _file_iri(iri)


def _file_iri(iri: str) -> Path | None:
    parts = urlsplit(iri)
    if parts.scheme != "file" or parts.netloc not in ("", "localhost"):
        return None
    return Path(os.path.normpath(unquote(parts.path)))


def read_catalog(path: Path, max_bytes: int) -> Catalog:
    """Read an OASIS XML catalog; relative targets resolve against its directory (and any ``xml:base``)."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise CatalogError(f"cannot read the catalog {path}: {exc}") from exc
    problem = dtd_problem(data, max_bytes)
    if problem is not None:
        raise InputRejected("SEC010", f"catalog {path} {problem}")
    try:
        root = ET.fromstring(data)  # noqa: S314 -- no DTD survives the preflight above.
    except ET.ParseError as exc:
        raise CatalogError(f"the catalog {path} is not well-formed XML: {exc}") from exc
    if root.tag != f"{_CATALOG_NS}catalog":
        raise CatalogError(f"{path} is not an OASIS XML catalog (root element {root.tag})")
    entries: dict[str, Path] = {}
    rewrites: list[tuple[str, Path]] = []
    base = path.parent.resolve()

    def walk(element: ET.Element, directory: Path) -> None:
        xml_base = element.get("{http://www.w3.org/XML/1998/namespace}base")
        here = Path(os.path.normpath(directory / xml_base)) if xml_base else directory
        for child in element:
            if child.tag == f"{_CATALOG_NS}uri" and child.get("name") and child.get("uri"):
                entries.setdefault(child.get("name", ""), Path(os.path.normpath(here / child.get("uri", ""))))
            elif child.tag == f"{_CATALOG_NS}rewriteURI" and child.get("uriStartString") and child.get("rewritePrefix"):
                rewrites.append(
                    (child.get("uriStartString", ""), Path(os.path.normpath(here / child.get("rewritePrefix", ""))))
                )
            elif child.tag == f"{_CATALOG_NS}group":
                walk(child, here)

    walk(root, base)
    return Catalog(base, entries, tuple(sorted(rewrites, key=lambda pair: -len(pair[0]))))


# gremlin: pardon[equivalent] nothing mutates a closure; frozen only guards against it
@dataclass(frozen=True)
class Closure:
    """A root document merged with every import that resolved to a local file."""

    loaded: LoadedGraph
    files: tuple[str, ...]
    """Display names of the imported files, in load order (the root file excluded)."""
    resolved: frozenset[str]
    unresolved: frozenset[str]
    imported_ontologies: frozenset[str]
    """Ontology IRIs declared by the imported files (not by the root)."""


def _imports(graph: Graph) -> list[str]:
    return sorted({str(o) for o in graph.objects(None, OWL.imports) if isinstance(o, URIRef)})


def _declared(graph: Graph) -> frozenset[str]:
    return frozenset(str(s) for s in graph.subjects(RDF.type, None) if isinstance(s, URIRef))


def _ontologies(graph: Graph) -> set[str]:
    return {str(s) for s in graph.subjects(RDF.type, OWL.Ontology) if isinstance(s, URIRef)}


def _inside(path: Path, root: Path) -> bool:
    return Path(os.path.realpath(path)).is_relative_to(Path(os.path.realpath(root)))


def load_closure(  # noqa: C901, PLR0912 -- one breadth-first walk with its checks in order.
    root_document: LoadedGraph,
    root_path: Path,
    policy: Policy,
    catalog: Catalog | None,
    root_item: InputFile | None = None,
) -> Closure:
    """Follow ``owl:imports`` from ``root_document`` breadth first, loading each local file once."""
    sandbox = catalog.root if catalog is not None else root_path.parent.resolve()
    resolver = catalog if catalog is not None else Catalog(sandbox, {})
    merged = Graph()
    for prefix, namespace in root_document.graph.namespaces():  # pySHACL renders nodes with these prefixes
        # gremlin: pardon[equivalent] the merged graph is new: only rdflib's own default prefixes could clash
        merged.bind(prefix, namespace, override=False)
    merged += root_document.graph
    seen_iris: set[str] = set()
    seen_files = {os.path.realpath(root_path)}
    resolved: set[str] = set()
    unresolved: set[str] = set()
    files: list[str] = []
    imported: set[str] = set()
    root = root_item or resolve_inputs([str(root_path)], Path.cwd())[0]
    modules = [Module(root.display, root.uri, _declared(root_document.graph), root_document.source_index)]
    queue = deque((iri, 1) for iri in _imports(root_document.graph))
    while queue:
        iri, depth = queue.popleft()
        if iri in seen_iris:
            continue
        seen_iris.add(iri)
        path = resolver.resolve(iri)
        if path is None:
            unresolved.add(iri)
            continue
        if not _inside(path, sandbox):
            raise InputRejected("SEC009", f"owl:imports {iri} resolves to {path}, outside the import root {sandbox}")
        resolved.add(iri)
        if os.path.realpath(path) in seen_files:
            continue
        if depth > policy.max_import_depth:
            raise InputRejected(
                "SEC015", f"owl:imports {iri} is deeper than {policy.max_import_depth} (max_import_depth)"
            )
        if len(files) >= policy.max_imported_files:
            raise InputRejected(
                "SEC015", f"the import closure has more than {policy.max_imported_files} files (max_imported_files)"
            )
        seen_files.add(os.path.realpath(path))
        item = resolve_inputs([str(path)], Path.cwd())[0]
        document = load_document(item, policy, sandbox)
        files.append(item.display)
        modules.append(Module(item.display, item.uri, _declared(document.graph), document.source_index))
        imported |= _ontologies(document.graph)
        merged += document.graph
        if len(merged) > policy.max_triples:
            raise InputRejected(
                "SEC015", f"the import closure has more than {policy.max_triples} triples (max_triples)"
            )
        queue.extend((child, depth + 1) for child in _imports(document.graph))
    imported -= _ontologies(root_document.graph)
    return Closure(
        LoadedGraph(merged, root_document.source_index, frozenset(resolved), frozenset(imported), tuple(modules)),
        tuple(files),
        frozenset(resolved),
        frozenset(unresolved),
        frozenset(imported),
    )
