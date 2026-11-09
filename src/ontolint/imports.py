"""Offline ``owl:imports`` closure: resolve imports to local files through an OASIS XML catalog.

A modular ontology is often an umbrella file with no terms of its own that ``owl:imports`` its modules,
and an OASIS XML catalog (``catalog-v001.xml``, the Protege, ROBOT and ODK convention) maps each module
IRI to a file.  Linting the umbrella alone checks nothing, so with ``--follow-imports`` (or
``--catalog FILE``) the CLI loads the whole closure into one graph.

The network is never used.  An import resolves only through the catalog (``uri`` entries, also inside
``group``, and ``rewriteURI`` prefixes) or as a ``file:`` IRI; anything else stays unresolved and is
reported by SEC007; a catalog entry naming a missing file leaves its import unresolved too.  The
catalog next to each imported file is consulted before the root catalog, as Protege does.  Every
resolved file must lie inside the import root (``--import-root``; by default the enclosing git
repository of the catalog, or of the input without a catalog) after symlinks are followed (SEC009);
each file passes the ordinary safe loader with its per-file limits; and the closure as a whole is
bounded by ``max_import_depth``, ``max_imported_files`` and ``max_triples`` (SEC015).  Cycles
terminate and a file reached twice is loaded once.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET  # noqa: S405 -- the catalog passes the DTD/entity preflight first.
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlsplit

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF

from .loader import InputRejected, LoadedGraph, LoadError, Module, dtd_problem, load_document
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
    missing: dict[str, Path] = field(default_factory=dict[str, Path])
    """Imports a catalog maps to a file that does not exist (they are also in :attr:`unresolved`)."""


def _imports(graph: Graph) -> list[str]:
    return sorted({str(o) for o in graph.objects(None, OWL.imports) if isinstance(o, URIRef)})


def _declared(graph: Graph) -> frozenset[str]:
    return frozenset(str(s) for s in graph.subjects(RDF.type, None) if isinstance(s, URIRef))


def _ontologies(graph: Graph) -> set[str]:
    return {str(s) for s in graph.subjects(RDF.type, OWL.Ontology) if isinstance(s, URIRef)}


def _identities(graph: Graph) -> set[str]:
    """The IRIs an import may use to name this document: its ontology IRIs and their version IRIs."""
    ontologies = _ontologies(graph)
    versions = {str(v) for o in ontologies for v in graph.objects(URIRef(o), OWL.versionIRI) if isinstance(v, URIRef)}
    return ontologies | versions


def _directory(path: Path) -> str:
    """``path``'s directory as a ``file:`` URI ending in ``/``."""
    return path.resolve().parent.as_uri().rstrip("/") + "/"


def _inside(path: Path, root: Path) -> bool:
    return Path(os.path.realpath(path)).is_relative_to(Path(os.path.realpath(root)))


def default_import_root(start: Path) -> Path:
    """The directory resolved imports must stay in: the enclosing repository, else ``start`` itself.

    Catalogs routinely point at sibling directories (``../modules/x.ttl``), so the catalog's own
    directory is too narrow; the nearest ancestor holding ``.git`` bounds the project instead.
    """
    start = start.resolve()
    return next((directory for directory in (start, *start.parents) if (directory / ".git").exists()), start)


RDF_SUFFIXES = (".ttl", ".owl", ".rdf", ".nt", ".n3", ".jsonld", ".json", ".xml", ".nq", ".trig")
"""File names an import directory is searched for."""


def index_directory(directory: Path, policy: Policy) -> Catalog:
    """Map the ontology and version IRIs declared by the RDF files under ``directory`` to those files.

    This is ``--import-dir``: a folder of downloaded imports (``robot mirror``, a release you saved) needs
    no catalog.  Each file is read once through the safe loader; at most ``max_imported_files`` files are
    indexed (SEC015), and a file that does not parse is skipped, since it may not be RDF at all.
    """
    root = directory.resolve()
    candidates = sorted(p for p in root.rglob("*") if p.suffix.lower() in RDF_SUFFIXES and p.is_file())
    if len(candidates) > policy.max_imported_files:
        raise InputRejected(
            "SEC015", f"--import-dir {directory} holds more than {policy.max_imported_files} files (max_imported_files)"
        )
    entries: dict[str, Path] = {}
    for path in candidates:
        try:
            graph = load_document(resolve_inputs([str(path)], Path.cwd())[0], policy, root).graph
        except (LoadError, OSError):
            continue
        for iri in sorted(_identities(graph)):
            entries.setdefault(iri, path)
    return Catalog(root, entries)


class _Resolver:
    """Resolve imports through the catalog next to the importing file, the root catalog, then import dirs."""

    def __init__(self, root: Catalog, policy: Policy, directories: tuple[Catalog, ...] = ()) -> None:
        self.root = root
        self.policy = policy
        self.directories = directories
        self.local: dict[Path, Catalog | None] = {root.root: root}

    def resolve(self, iri: str, directory: Path) -> Path | None:
        if directory not in self.local:
            found = directory / CATALOG_NAME
            self.local[directory] = read_catalog(found, self.policy.max_input_bytes) if found.is_file() else None
        here = self.local[directory]
        resolved = (here.resolve(iri) if here is not None else None) or self.root.resolve(iri)
        return resolved or next((d.entries[iri] for d in self.directories if iri in d.entries), None)


@dataclass
class _Walk:
    """The state of one breadth-first walk over an import closure."""

    policy: Policy
    sandbox: tuple[Path, ...]
    merged: Graph
    modules: list[Module]
    seen_iris: set[str]
    seen_files: set[str]
    resolved: set[str]
    unresolved: set[str]
    missing: dict[str, Path]
    files: list[str]
    imported: set[str]
    known: set[str]
    """Ontology and version IRIs of the files already loaded: importing one again needs no lookup."""


def load_closure(  # noqa: PLR0913 -- the root document, its path and identity, the policy and two lookup inputs.
    root_document: LoadedGraph,
    root_path: Path,
    policy: Policy,
    catalog: Catalog | None,
    root_item: InputFile | None = None,
    *,
    import_root: Path | None = None,
    import_dirs: tuple[Catalog, ...] = (),
) -> Closure:
    """Follow ``owl:imports`` from ``root_document`` breadth first, loading each local file once.

    Resolved files must stay inside ``import_root`` (by default :func:`default_import_root` of the
    catalog's directory, or of the input's directory without a catalog).  A catalog entry naming a
    file that does not exist leaves its import unresolved and is listed in :attr:`Closure.missing`.
    """
    start = catalog.root if catalog is not None else root_path.parent
    # An --import-dir is the user's explicit choice, so its files are allowed as well as the import root's.
    sandbox = ((import_root or default_import_root(start)).resolve(), *(d.root for d in import_dirs))
    resolver = _Resolver(
        catalog if catalog is not None else Catalog(root_path.parent.resolve(), {}), policy, import_dirs
    )
    merged = Graph()
    for prefix, namespace in root_document.graph.namespaces():  # pySHACL renders nodes with these prefixes
        # gremlin: pardon[equivalent] the merged graph is new: only rdflib's own default prefixes could clash
        merged.bind(prefix, namespace, override=False)
    merged += root_document.graph
    root = root_item or resolve_inputs([str(root_path)], Path.cwd())[0]
    walk = _Walk(
        policy,
        sandbox,
        merged,
        [
            Module(
                root.display,
                root.uri,
                _declared(root_document.graph),
                root_document.source_index,
                _directory(root_path),
            )
        ],
        set(),
        {os.path.realpath(root_path)},
        set(),
        set(),
        {},
        [],
        set(),
        _identities(root_document.graph),
    )
    directory = root_path.parent.resolve()
    queue = deque((iri, 1, directory) for iri in _imports(root_document.graph))
    while queue:
        iri, depth, directory = queue.popleft()
        if iri in walk.seen_iris:
            continue
        walk.seen_iris.add(iri)
        if iri in walk.known:  # the root or a module already loaded, named by its ontology or version IRI
            walk.resolved.add(iri)
            continue
        path = resolver.resolve(iri, directory)
        if path is None:
            walk.unresolved.add(iri)
            continue
        if not any(_inside(path, root) for root in sandbox):
            raise InputRejected("SEC009", f"owl:imports {iri} resolves to {path}, outside the import root {sandbox[0]}")
        if not path.is_file():
            walk.missing[iri] = path
            walk.unresolved.add(iri)
            continue
        walk.resolved.add(iri)
        if os.path.realpath(path) not in walk.seen_files:
            document = _load_module(walk, iri, path, depth)
            queue.extend((child, depth + 1, path.parent.resolve()) for child in _imports(document.graph))
    walk.imported -= _ontologies(root_document.graph)
    loaded = LoadedGraph(
        walk.merged,
        root_document.source_index,
        frozenset(walk.resolved),
        frozenset(walk.imported),
        tuple(walk.modules),
        root_document.comment_license,
    )
    return Closure(
        loaded,
        tuple(walk.files),
        frozenset(walk.resolved),
        frozenset(walk.unresolved),
        frozenset(walk.imported),
        walk.missing,
    )


def _load_module(walk: _Walk, iri: str, path: Path, depth: int) -> LoadedGraph:
    """Load one imported file into ``walk``, enforcing the closure limits (SEC015)."""
    policy, sandbox = walk.policy, walk.sandbox
    if depth > policy.max_import_depth:
        raise InputRejected("SEC015", f"owl:imports {iri} is deeper than {policy.max_import_depth} (max_import_depth)")
    if len(walk.files) >= policy.max_imported_files:
        raise InputRejected(
            "SEC015", f"the import closure has more than {policy.max_imported_files} files (max_imported_files)"
        )
    walk.seen_files.add(os.path.realpath(path))
    item = resolve_inputs([str(path)], Path.cwd())[0]
    document = load_document(item, policy, next(root for root in sandbox if _inside(path, root)))
    walk.files.append(item.display)
    walk.modules.append(
        Module(item.display, item.uri, _declared(document.graph), document.source_index, _directory(path))
    )
    walk.imported |= _ontologies(document.graph)
    walk.known |= _identities(document.graph)
    walk.merged += document.graph
    if len(walk.merged) > policy.max_triples:
        raise InputRejected("SEC015", f"the import closure has more than {policy.max_triples} triples (max_triples)")
    return document
