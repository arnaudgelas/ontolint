"""The set-level scope: which ontology and version IRIs several documents of one run declare (ONT007, ONT008).

Rules judge one file at a time.  This module looks at the set of documents a run has read, before any file
is linted, and finds every ontology or version IRI that more than one of them declares, in four places
compared separately (see :mod:`ontolint.rules.duplicate_ids` for the rule contract):

* the inputs of the run, each without its imports;
* the files of each input's import closure, with the files an import resolves to but was not loaded from
  because a loaded file already declares its IRI;
* the files of the ``--import-dir`` options that an import of a closure had to choose between;
* the named graphs of each dataset file (an input, or a file of its closure).

One fact is reported once: of the findings that name one IRI, a finding whose documents are all documents of
another is dropped, and of two with the same documents the first is kept (in report-path order of the
inputs, each input's closure, datasets and import choices before the inputs themselves).  The CLI passes the
identities to that input's rules as ``Policy.shared_identities`` and uses the :class:`Place` of each member
to say where the finding is (its file, its named graphs, a SARIF location per file).

The result never depends on the argument order: inputs arrive sorted by report path, and every other order
(load order, path order, graph names) is fixed by the files themselves.  Content is compared through
:func:`ontolint.datasets.same_content`, only for documents that share an IRI; an ``--import-dir`` candidate the
closure did not load is read only then, and once per run.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.namespace import OWL, RDF
from rdflib.term import Node

from .datasets import Content, GraphIndex, Triple, content_of, ordered, same_content
from .loader import InputRejected, LoadedGraph, LoadError, Module, load_document
from .models import SharedIdentity
from .paths import InputFile, resolve_inputs
from .policy import Policy
from .source_locations import SourceIndex


# gremlin: pardon[equivalent] nothing mutates a place; frozen only guards against it
@dataclass(frozen=True)
class Place:
    """One file a shared identity is declared in: its report path, its SARIF artifact URI, its source positions."""

    path: str
    uri: str
    source_index: SourceIndex | None = None


# gremlin: pardon[equivalent] nothing mutates a shared identity; frozen only guards against it
@dataclass(frozen=True)
class Shared:
    """A shared identity and the file of each of its members."""

    identity: SharedIdentity
    places: tuple[Place, ...]
    """The files of the members, first member first: one per member, or the single dataset file for ``graphs``."""


# gremlin: pardon[equivalent] nothing mutates the facts; frozen only guards against it
@dataclass(frozen=True)
class _Facts:
    """What a document declares, and where its file's terms are."""

    ontologies: frozenset[str]
    versions: frozenset[str]
    unversioned: frozenset[str]
    """The ontology IRIs it declares without giving them a version IRI."""
    source_index: SourceIndex | None


@dataclass
class _Document:
    """A document that may declare ontology and version IRIs: a file, or one graph of a dataset file."""

    label: str
    key: tuple[str, str]
    """What tells it from another document of the run: its file's report path, and its graph name (or ``""``)."""
    path: str
    uri: str
    read: Callable[[], tuple[Iterable[Triple], SourceIndex | None]]
    """Its triples and its file's source positions."""
    typed: frozenset[str] | None = None
    """For a graph of a dataset: the ontology IRIs any graph of its file declares (a version IRI may be given
    in another graph than the header)."""
    from_disk: bool = False
    """A file no closure loaded: ``read`` parses it again on each call, so its content is taken with its facts,
    and its triples are held in memory only meanwhile."""
    _facts: _Facts | None = field(default=None, init=False)
    _content: Content | None = field(default=None, init=False)

    def facts(self) -> _Facts:
        if self._facts is None:
            triples, source_index = self.read()
            self._facts = _Facts(*_identities(triples, self.typed), source_index)
            if self.from_disk:
                self._content = content_of(triples)
        return self._facts

    def content(self) -> Content:
        """Its :class:`Content`, computed on first use: only documents that share an IRI are compared."""
        if self._content is None and self.from_disk:
            self.facts()
        if self._content is None:
            self._content = content_of(self.read()[0])
        return self._content

    @property
    def place(self) -> Place:
        return Place(self.path, self.uri, self.facts().source_index)


def _identities(
    triples: Iterable[Triple], typed: frozenset[str] | None = None
) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    """The ontology IRIs ``triples`` declare, the version IRIs they give them, and those they give none.

    A graph is asked through its indexes, so a large file costs two lookups, not a scan.
    """
    headers: list[Node]
    given: list[tuple[Node, Node]]
    if isinstance(triples, Graph):
        headers = list(triples.subjects(RDF.type, OWL.Ontology))
        given = list(triples.subject_objects(OWL.versionIRI))
    else:
        rows = list(triples)
        headers = [s for s, p, o in rows if p == RDF.type and o == OWL.Ontology]
        given = [(s, o) for s, p, o in rows if p == OWL.versionIRI]
    ontologies = frozenset(str(s) for s in headers if isinstance(s, URIRef))
    owners = ontologies if typed is None else typed
    pairs = {(str(s), str(v)) for s, v in given if isinstance(v, URIRef) and str(s) in owners}
    return ontologies, frozenset(v for _s, v in pairs), ontologies - {s for s, _v in pairs}


def _identical(members: Sequence[_Document]) -> bool:
    return same_content([m.content() for m in members], lambda: [m.read()[0] for m in members])


def _shared(
    documents: Sequence[_Document], scope: str, where: str = "", *, strict: bool
) -> list[tuple[SharedIdentity, list[_Document]]]:
    """Every ontology or version IRI two or more of ``documents`` declare, with them in the order given.

    ``strict`` is for the files of one import closure, which OWL 2 (Structural Specification, section 3.5)
    forbids to hold two versions of one ontology series: there, an ontology IRI is reported whenever two files
    declare it, and a version IRI only when its files do not all declare one ontology IRI (which says it
    already).  Otherwise (the inputs, the graphs of a dataset) documents are independent, and two versions of
    one series, which share the ontology IRI under different version IRIs, may coexist (section 3.3): a
    version IRI is reported whenever two documents declare it, and an ontology IRI only among the documents
    that give it no version IRI.
    """
    declaring: dict[tuple[str, str], list[_Document]] = {}
    for document in documents:
        facts = document.facts()
        for kind, iris in (
            ("ontology", facts.ontologies if strict else facts.unversioned),
            ("version", facts.versions),
        ):
            for iri in sorted(iris):
                declaring.setdefault((kind, iri), []).append(document)
    found: list[tuple[SharedIdentity, list[_Document]]] = []
    for (kind, iri), members in sorted(declaring.items()):
        if len(members) < 2:  # noqa: PLR2004 -- shared means declared twice or more
            continue
        if strict and kind == "version" and frozenset.intersection(*(m.facts().ontologies for m in members)):
            continue
        labels = tuple(member.label for member in members)
        identity = SharedIdentity(iri, kind, scope, labels, _identical(members), where)
        found.append((identity, members))
    return found


def _module_document(module: Module) -> _Document:
    graph = module.graph if module.graph is not None else Graph()
    return _Document(
        module.display, (module.display, ""), module.display, module.uri, lambda: (graph, module.source_index)
    )


def _graph_documents(file: _Document, index: GraphIndex, source_index: SourceIndex | None) -> list[_Document]:
    """The graphs of the dataset ``file`` that declare an ontology or version IRI, each built on first use.

    The header triples are found in one pass over ``index``, and every graph that holds one is built in one
    more pass, the first time one of them is compared: the work is linear in the triples of the file.
    """
    typed = frozenset(
        str(s) for (s, p, o) in index.triples if p == RDF.type and o == OWL.Ontology and isinstance(s, URIRef)
    )
    names: set[str] = set()
    for (s, p, o), graphs in index.triples.items():
        if (p == RDF.type and o == OWL.Ontology and isinstance(s, URIRef)) or (
            p == OWL.versionIRI and str(s) in typed and isinstance(o, URIRef)
        ):
            names.update(graphs)
    built: dict[str, list[Triple]] = {}

    def subgraph(name: str) -> Callable[[], tuple[Iterable[Triple], SourceIndex | None]]:
        def build() -> tuple[Iterable[Triple], SourceIndex | None]:
            if not built:
                built.update((each, []) for each in names)
                for triple, graphs in index.triples.items():
                    for each in graphs:
                        if each in built:
                            built[each].append(triple)
            return built[name], source_index

        return build

    return [_Document(name, (file.key[0], name), file.path, file.uri, subgraph(name), typed) for name in ordered(names)]


class _Documents:
    """The file documents of a run, one per report path, so each is compared (and read, if no closure loaded
    it: an ``--import-dir`` candidate, a shadowed import) at most once, and only when it is compared."""

    def __init__(self, policy: Policy, loaded: Sequence[LoadedGraph]) -> None:
        self.policy = policy
        self.modules = {module.display: module for graph in loaded for module in graph.modules}
        self.documents: dict[str, _Document] = {}

    def module(self, module: Module) -> _Document:
        if module.display not in self.documents:
            self.documents[module.display] = _module_document(module)
        return self.documents[module.display]

    def document(self, path: Path, root: Path) -> _Document:
        item = resolve_inputs([str(path)], Path.cwd())[0]
        if item.display in self.modules:  # loaded by a closure already
            return self.module(self.modules[item.display])
        if item.display not in self.documents:

            def read() -> tuple[Iterable[Triple], SourceIndex | None]:
                try:
                    document = load_document(item, self.policy, root)
                except (InputRejected, LoadError, OSError):  # changed since it was indexed: compare it as empty
                    return Graph(), None
                return document.graph, document.source_index

            key = (item.display, "")
            self.documents[item.display] = _Document(item.display, key, item.display, item.uri, read, from_disk=True)
        return self.documents[item.display]


def _choices(loaded: LoadedGraph, documents: _Documents) -> list[tuple[SharedIdentity, list[_Document]]]:
    """For each import the ``--import-dir`` options held in several files: those files, the one it took first."""
    found: list[tuple[SharedIdentity, list[_Document]]] = []
    for choice in loaded.choices:
        files = [documents.document(path, root) for path, root in choice.candidates]
        kind = "ontology" if choice.iri in files[0].facts().ontologies else "version"
        labels = tuple(file.label for file in files)
        where = ", ".join(choice.directories)
        found.append((SharedIdentity(choice.iri, kind, "import-dir", labels, _identical(files), where), files))
    return found


def _closure(loaded: LoadedGraph, documents: _Documents) -> list[tuple[SharedIdentity, list[_Document]]]:
    """What the files of one closure share, the files its imports resolve to but did not load included."""
    files = [documents.module(module) for module in loaded.modules]
    shadows: dict[tuple[str, str], str] = {}  # the key of a file not loaded -> the import IRI it was named for
    for shadow in loaded.shadowed:
        document = documents.document(shadow.path, shadow.root)
        if document.key not in shadows:
            files.append(document)
            shadows[document.key] = shadow.iri
    found = []
    for identity, members in _shared(files, "closure", strict=True):
        unloaded = tuple((shadows[m.key], m.label) for m in members if m.key in shadows)
        found.append((replace(identity, unloaded=unloaded), members))
    return found


def _of_input(
    item: InputFile, loaded: LoadedGraph, documents: _Documents
) -> list[tuple[SharedIdentity, list[_Document]]]:
    """What the closure, the datasets and the ``--import-dir`` choices of one input share."""
    found = _closure(loaded, documents) if loaded.modules else []
    files = [(m.graphs, documents.module(m), m.source_index) for m in loaded.modules] or [
        (loaded.graphs, _root(item, loaded, documents), loaded.source_index)
    ]
    for index, document, source_index in files:
        if index.triples:
            graphs = _graph_documents(document, index, source_index)
            found += _shared(graphs, "graphs", document.label, strict=False)
    return found + _choices(loaded, documents)


def _root(item: InputFile, loaded: LoadedGraph, documents: _Documents) -> _Document:
    """An input without its imports: the closure's first module, else the parsed file itself."""
    if loaded.modules:
        return documents.module(loaded.modules[0])
    if item.display not in documents.documents:
        graph, source_index = loaded.graph, loaded.source_index
        document = _Document(item.display, (item.display, ""), item.display, item.uri, lambda: (graph, source_index))
        documents.documents[item.display] = document
    return documents.documents[item.display]


def _unique(
    found: Sequence[tuple[int, SharedIdentity, list[_Document]]],
) -> list[tuple[int, SharedIdentity, list[_Document]]]:
    """``found`` without the findings another one states: same IRI and kind, and a subset of its documents."""
    members = [frozenset(document.key for document in documents) for _input, _identity, documents in found]
    kept = []
    for position, (number, identity, documents) in enumerate(found):
        name = (identity.iri, identity.kind)
        if not any(
            (other[1].iri, other[1].kind) == name
            and (members[position] < members[index] or (members[position] == members[index] and index < position))
            for index, other in enumerate(found)
        ):
            kept.append((number, identity, documents))
    return kept


def shared_identities(
    inputs: Sequence[InputFile], loaded: Sequence[LoadedGraph], policy: Policy
) -> list[tuple[Shared, ...]]:
    """For each input (in the order given, which is report-path order), the shared identities reported on it.

    ``policy`` is the loader policy an ``--import-dir`` candidate or a shadowed import is read with, when the
    closure did not load it.
    """
    documents = _Documents(policy, loaded)
    found: list[tuple[int, SharedIdentity, list[_Document]]] = []
    for number, (item, graph) in enumerate(zip(inputs, loaded, strict=True)):
        found += [(number, identity, members) for identity, members in _of_input(item, graph, documents)]
    if len(inputs) > 1:
        roots = [_root(item, graph, documents) for item, graph in zip(inputs, loaded, strict=True)]
        for identity, members in _shared(roots, "inputs", strict=False):
            found.append((next(n for n, root in enumerate(roots) if root is members[0]), identity, members))
    per_input: list[list[Shared]] = [[] for _ in inputs]
    for number, identity, members in _unique(found):
        places = (members[0].place,) if identity.scope == "graphs" else tuple(member.place for member in members)
        per_input[number].append(Shared(identity, places))
    return [tuple(each) for each in per_input]
