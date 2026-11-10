"""Pattern-library rules: LIB001-LIB003, an index ontology against its member pattern ontologies.

They run only with ``--pattern-library DIR`` (:mod:`ontolint.library`): the linted file is the index,
the ontologies under ``DIR`` are its members.  Otherwise they are skipped, never passed.

Terms.  An index *entry* is linked to a member when the entry's IRI is one of the member's identities
(ontology or version IRI), when the index states any triple from the entry to one of them (for example
``rdfs:isDefinedBy``), or when the member's header names the entry's IRI.  An entry and a member have
the *same name* when one of the entry's names (its local name and labels) and one of the member's names
(``opla-core:hasPatternName``, ``rdfs:label``, ``dcterms:title`` ...) are equal once case, everything
but letters and digits, and a trailing ``pattern`` are removed ("AgentRole" and "Agent Role").  The
*entry classes* are the classes of the index's own individuals that are linked to a member or share a
name with one; the entries are every owned individual of an entry class.

* **LIB001.** An entry linked to no member.  When a member has the same name the message names it and
  how to link them: the index describes the pattern but cannot refer to it (MODL: every entry).  Warning,
  heuristic: the entry classes are inferred.  When library files did not parse, an entry with no
  same-named member says it may be in one of them (as LIB003 does); the message is fixed text, so a
  baseline does not depend on how many.  Exclusions: individuals of other classes (MODL's
  categories), terms the index does not own.
* **LIB002.** A member that no entry is linked to and no entry shares a name with: a pattern missing
  from the index.  The finding belongs to the member's file.  Warning, heuristic.
* **LIB003.** A member's header names an IRI in the library namespace that no member declares (an
  ``opla-core:hasRelatedPattern`` to a pattern that does not exist).  The *library namespace* is the
  longest common prefix of the members' ontology IRIs cut back to a ``/`` or ``#``; it needs at least two
  members and a path below the host, else the rule checks nothing.  IRIs under a member's own ontology
  IRI (its terms) are not references to members.  The finding belongs to the member's file.  Warning,
  heuristic.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF

from ontolint.models import LibraryMember, PatternLibrary, Requirement, RuleBackend, RuleScope, RuleSpec, Severity
from ontolint.ownership import is_builtin

from .support import local_name

if TYPE_CHECKING:
    from .runtime import RuleContext

SPECS: tuple[RuleSpec, ...] = (
    RuleSpec(
        "LIB001",
        "LIB",
        "Pattern library index entry names no member ontology",
        Severity.WARNING,
        "Give the entry the member's ontology IRI, or link it to the member (for example with rdfs:isDefinedBy).",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.TERM,
        "library",
        Requirement.PATTERN_LIBRARY,
    ),
    RuleSpec(
        "LIB002",
        "LIB",
        "Pattern library member missing from the index",
        Severity.WARNING,
        "Add an index entry for the pattern ontology, or remove the file from the library.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.ONTOLOGY,
        "library",
        Requirement.PATTERN_LIBRARY,
    ),
    RuleSpec(
        "LIB003",
        "LIB",
        "Pattern library member refers to a pattern the library lacks",
        Severity.WARNING,
        "Correct the IRI, or add the pattern ontology it names to the library.",
        "heuristic",
        RuleBackend.RDFLIB,
        RuleScope.ONTOLOGY,
        "library",
        Requirement.PATTERN_LIBRARY,
    ),
)

_NOT_NAME = re.compile(r"[^0-9a-z]+")


def normalise_name(name: str) -> str:
    """``name`` compared as a pattern name: case-folded, letters and digits only, no trailing ``pattern``."""
    text = _NOT_NAME.sub("", name.casefold())
    return text.removesuffix("pattern") or text


def _names(values: Iterable[str]) -> set[str]:
    return {n for n in map(normalise_name, values) if n}


def library_namespace(members: Iterable[LibraryMember]) -> str | None:
    """The longest common prefix of the members' ontology IRIs, cut back to ``/`` or ``#``; see LIB003."""
    iris = sorted({m.ontology for m in members})
    if len(iris) < 2:  # noqa: PLR2004 -- one member has no common namespace with anything
        return None
    first, last = iris[0], iris[-1]
    common = first[: next((i for i, (a, b) in enumerate(zip(first, last, strict=False)) if a != b), len(first))]
    cut = max(common.rfind("/"), common.rfind("#"))
    namespace = common[: cut + 1]
    parts = urlsplit(namespace)
    return namespace if parts.netloc and parts.path.strip("/") else None


def _linked(g: Graph, entry: URIRef, member: LibraryMember) -> bool:
    """Whether ``entry`` is ``member``, points at it, or is named by its header (see the terms above)."""
    return (
        str(entry) in member.identities
        or any(str(o) in member.identities for o in g.objects(entry, None) if isinstance(o, URIRef))
        or any(iri == str(entry) for _p, iri in member.references)
    )


def _entry_names(ctx: RuleContext, entry: URIRef) -> set[str]:
    labels = (str(v) for p in ctx.labels for v in ctx.g.objects(entry, p) if isinstance(v, Literal))
    return _names([local_name(entry), *labels])


def run(ctx: RuleContext) -> None:
    """Compare the linted index with the member ontologies of ``--pattern-library``."""
    library = ctx.policy.library
    if library is None:
        return
    g = ctx.g
    member_names = {m.ontology: _names(m.names) for m in library.members}
    schema = ctx.classes | ctx.properties | ctx.ontologies
    candidates = sorted(
        {s for s in g.subjects(RDF.type, None) if isinstance(s, URIRef) and ctx.local(s) and s not in schema}, key=str
    )
    matches: dict[URIRef, list[LibraryMember]] = {}
    links: dict[URIRef, bool] = {}
    for entry in candidates:
        names = _entry_names(ctx, entry)
        linked = [m for m in library.members if _linked(g, entry, m)]
        matches[entry] = linked or [m for m in library.members if names & member_names[m.ontology]]
        links[entry] = bool(linked)
    # Built-in types (owl:NamedIndividual) say nothing about which individuals are entries.
    entry_classes = {t for e, found in matches.items() if found for t in g.objects(e, RDF.type) if not is_builtin(t)}
    entries = [e for e in candidates if set(g.objects(e, RDF.type)) & entry_classes]
    for entry in entries:
        if not links[entry]:
            _lib001(ctx, entry, sorted({m.ontology for m in matches[entry]}))
    _lib002(ctx, library, {m.ontology for e in entries for m in matches[e]})
    _lib003(ctx, library)


INCOMPLETE = " Some files of the library did not parse (TOOL008), so it may be in one of them."


def _caveat(ctx: RuleContext) -> str:
    """Added to a claim that something is missing when unreadable files may hold it; fixed, so fingerprints are."""
    library = ctx.policy.library
    return INCOMPLETE if library is not None and library.unreadable else ""


def _lib001(ctx: RuleContext, entry: URIRef, same_name: list[str]) -> None:
    if same_name:
        ctx.add(
            "LIB001",
            entry,
            f"Index entry names no pattern ontology by IRI; <{same_name[0]}> has its name: link them "
            f"(for example rdfs:isDefinedBy <{same_name[0]}>).",
        )
    else:
        ctx.add("LIB001", entry, "Index entry names no pattern ontology of the library." + _caveat(ctx))


def _lib002(ctx: RuleContext, library: PatternLibrary, covered: set[str]) -> None:
    for member in library.members:
        if member.ontology not in covered:
            ctx.add("LIB002", URIRef(member.ontology), "Pattern ontology is not in the index: no entry names it.")


def _lib003(ctx: RuleContext, library: PatternLibrary) -> None:
    namespace = library_namespace(library.members)
    if namespace is None:
        return
    known = {iri for m in library.members for iri in m.identities}
    for member in library.members:
        for predicate, iri in member.references:
            if not iri.startswith(namespace) or iri in known:
                continue
            if any(iri.startswith(m.ontology + sep) for m in library.members for sep in "#/"):
                continue  # a term of a member, not a member
            ctx.add(
                "LIB003",
                URIRef(member.ontology),
                f"The header names <{iri}> ({local_name(URIRef(predicate))}), which no pattern ontology of the "
                "library declares." + _caveat(ctx),
            )
