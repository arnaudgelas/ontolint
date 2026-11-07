"""Graph-local security hygiene rules: SEC004, SEC005, SEC008, SEC012 and SEC014.

These rules inspect the already-parsed RDFLib graph only; parser, network and file-system policy
belong to the loader.  Every traversal is iterative so hostile inputs cannot exhaust the stack.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import TYPE_CHECKING

from rdflib import BNode, Literal, URIRef
from rdflib.namespace import RDF
from rdflib.term import Node

from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity

if TYPE_CHECKING:
    from .runtime import RuleContext


MAX_BLANK_NODE_DEPTH = 100  # Longest chain of nested blank nodes (excluding rdf:rest) tolerated.
MAX_LIST_LENGTH = 5000  # Longest rdf:List tolerated.
MAX_LITERAL_LENGTH = 100_000  # Longest literal lexical form (characters) tolerated.
UNSAFE_SCHEMES = frozenset({"blob", "data", "file", "ftp", "gopher", "jar", "javascript", "vbscript"})

_SCHEME = re.compile(r"([A-Za-z][A-Za-z0-9+.\-]*):")
_USERINFO = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*://([^/?#@]*)@")
_LITERAL_HAZARD = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]")
_IRI_HAZARD = re.compile("[\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]")
_URL_STRIPPED = str.maketrans("", "", "\t\r\n")

SPECS: tuple[RuleSpec, ...] = (
    RuleSpec(
        "SEC004",
        "SEC",
        "Deeply nested or very long blank-node structure",
        Severity.WARNING,
        "Flatten the structure or give intermediate nodes IRIs; recursive consumers can exhaust their stack on it.",
        "deterministic",
        RuleBackend.RDFLIB,
        RuleScope.INPUT,
        "safety",
    ),
    RuleSpec(
        "SEC005",
        "SEC",
        "Unreasonably large literal value",
        Severity.WARNING,
        "Store large payloads outside the ontology and reference them by IRI.",
        "deterministic",
        RuleBackend.RDFLIB,
        RuleScope.INPUT,
        "safety",
    ),
    RuleSpec(
        "SEC008",
        "SEC",
        "IRI with an unsafe scheme",
        Severity.WARNING,
        "Use http(s), urn or another resolvable-by-design scheme instead of file:, javascript:, data: or similar.",
        "deterministic",
        RuleBackend.RDFLIB,
        RuleScope.INPUT,
        "safety",
    ),
    RuleSpec(
        "SEC012",
        "SEC",
        "Control or bidirectional-override characters",
        Severity.WARNING,
        "Remove control and bidirectional-override characters; they can disguise the text a reader sees.",
        "deterministic",
        RuleBackend.RDFLIB,
        RuleScope.INPUT,
        "safety",
    ),
    RuleSpec(
        "SEC014",
        "SEC",
        "Credentials embedded in an IRI",
        Severity.ERROR,
        "Remove the user:password@ part of the IRI and rotate the exposed credential.",
        "deterministic",
        RuleBackend.RDFLIB,
        RuleScope.INPUT,
        "safety",
    ),
)


def run(ctx: RuleContext) -> None:
    """Run all graph-local security hygiene rules."""
    _blank_node_depth(ctx)
    _list_length(ctx)
    _terms(ctx)


def _owners(ctx: RuleContext, targets: set[Node]) -> dict[Node, Node]:
    """Return, per target blank node, the lexically least IRI subject that refers to it."""
    owners: dict[Node, Node] = {}
    for s, _, o in ctx.g:
        if isinstance(s, URIRef) and o in targets:
            owners[o] = min(s, owners.get(o, s), key=str)
    return owners


def _components(children: dict[Node, list[Node]]) -> list[list[Node]]:
    """Return the strongly connected components, successors before predecessors (iterative Tarjan)."""
    index: dict[Node, int] = {}
    low: dict[Node, int] = {}
    components: list[list[Node]] = []
    stack: list[Node] = []
    on_stack: set[Node] = set()
    for start in sorted(children, key=str):
        if start in index:
            continue
        index[start] = low[start] = len(index)
        stack.append(start)
        on_stack.add(start)
        work = [(start, iter(children[start]))]
        while work:
            node, pending = work[-1]
            child = next(pending, None)
            if child is not None:
                if child not in index:
                    index[child] = low[child] = len(index)
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, iter(children.get(child, ()))))
                elif child in on_stack:
                    low[node] = min(low[node], index[child])
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[node])
            if low[node] == index[node]:
                members: list[Node] = []
                while not members or members[-1] != node:
                    members.append(stack.pop())
                    on_stack.discard(members[-1])
                components.append(members)
    return components


def _condensed_depths(children: dict[Node, list[Node]]) -> dict[Node, int]:
    """Return the nesting depth of every node, counting each cycle of blank nodes as one level.

    Collapsing strongly connected components makes the result independent of traversal order,
    which depends on blank-node labels and so differs between parses of the same graph.
    """
    component: dict[Node, int] = {}
    depth: list[int] = []
    for number, members in enumerate(_components(children)):
        for member in members:
            component[member] = number
        below = {component[c] for m in members for c in children.get(m, ()) if component[c] != number}
        depth.append(1 + max((depth[c] for c in below), default=0))
    return {node: depth[number] for node, number in component.items()}


def _blank_node_depth(ctx: RuleContext) -> None:
    children: dict[Node, list[Node]] = defaultdict(list)
    nested: set[Node] = set()
    for s, p, o in ctx.g:
        if isinstance(s, BNode) and isinstance(o, BNode) and p != RDF.rest and s != o:
            children[s].append(o)
            nested.add(o)
    roots = sorted((n for n in children if n not in nested), key=str)
    depth = _condensed_depths(children)
    deep = [r for r in roots if depth[r] > MAX_BLANK_NODE_DEPTH]
    owners = _owners(ctx, set(deep))
    for root in deep:
        ctx.add(
            "SEC004",
            owners.get(root, root),
            f"Blank-node structure is nested {depth[root]} levels deep (limit {MAX_BLANK_NODE_DEPTH}).",
            confidence="certain",
        )


def _list_length(ctx: RuleContext) -> None:
    g = ctx.g
    members = ctx.context.subjects_by_predicate.get(RDF.rest, frozenset())
    followed = {o for s in members for o in g.objects(s, RDF.rest)}
    lengths: dict[Node, int] = {}
    for head in sorted((m for m in members if m not in followed), key=str):
        seen: set[Node] = set()
        node: Node | None = head
        while node is not None and node in members and node not in seen:
            seen.add(node)
            node = next(iter(g.objects(node, RDF.rest)), None)
        if len(seen) > MAX_LIST_LENGTH:
            lengths[head] = len(seen)
    owners = _owners(ctx, set(lengths))
    for head, length in lengths.items():
        ctx.add(
            "SEC004",
            owners.get(head, head),
            f"RDF list has {length} members (limit {MAX_LIST_LENGTH}).",
            confidence="certain",
        )


def _hazards(text: str, pattern: re.Pattern[str]) -> str:
    return ", ".join(sorted({f"U+{ord(c):04X}" for c in pattern.findall(text)}))


def _terms(ctx: RuleContext) -> None:
    iris: set[str] = set()
    for s, p, o in ctx.g:
        for node in (s, p, o):
            if isinstance(node, URIRef):
                iris.add(str(node))
        if isinstance(o, Literal):
            text = str(o)
            if len(text) > MAX_LITERAL_LENGTH:
                ctx.add(
                    "SEC005",
                    s,
                    f"Literal on {p} has {len(text)} characters (limit {MAX_LITERAL_LENGTH}).",
                    confidence="certain",
                )
            found = _hazards(text, _LITERAL_HAZARD)
            if found:
                ctx.add(
                    "SEC012",
                    s,
                    f"Literal on {p} contains control or bidirectional-override characters ({found}).",
                    confidence="certain",
                )
    for iri in sorted(iris):
        _check_iri(ctx, iri)


def _check_iri(ctx: RuleContext, iri: str) -> None:
    scheme = _SCHEME.match(iri.lstrip("\x00 \t\r\n\x0b\x0c").translate(_URL_STRIPPED))
    if scheme and scheme.group(1).lower() in UNSAFE_SCHEMES:
        ctx.add("SEC008", iri, f"IRI uses the unsafe scheme {scheme.group(1).lower()}:.", confidence="certain")
    found = _hazards(iri, _IRI_HAZARD)
    if found:
        ctx.add(
            "SEC012",
            iri,
            f"IRI contains control or bidirectional-override characters ({found}).",
            confidence="certain",
        )
    userinfo = _USERINFO.match(iri)
    if userinfo:
        user, separator, password = userinfo.group(1).partition(":")
        if separator and password:
            ctx.add("SEC014", iri, f"IRI embeds a password for user {user!r}.", confidence="certain")
