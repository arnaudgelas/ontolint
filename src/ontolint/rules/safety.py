"""Graph-local security hygiene rules: SEC004, SEC005, SEC008, SEC012 and SEC014.

These rules inspect the already-parsed RDFLib graph only; parser, network and file-system policy
belong to the loader.  Every traversal is iterative so hostile inputs cannot exhaust the stack.

* **SEC014.** An IRI in subject, predicate or object position of the data graph (not the shapes graph,
  not an ``xsd:anyURI`` literal) that holds a userinfo with a password.  Where a userinfo is, is decided
  by the parser that also masks it (:mod:`ontolint.redaction`, which specifies it), so SEC014 reports
  exactly the passwords the mask hides: after a scheme (any, case-insensitive: ``https``, ``HTTP``,
  ``ftp``, ``x+y.z-1``) and ``//`` (for ``http``, ``https``, ``ws``, ``wss`` and ``ftp``, any run of
  ``/`` and ``\\``, none included, as a WHATWG parser reads ``https:/u:p@h``), an authority runs to the
  first ``/ ? #``, whatever its characters (white space, braces, a line break), and its userinfo to its
  last ``@``; the part after the first ``:`` of that userinfo is not empty (``https://alice:secret@...``,
  ``https://:pw@...``, ``https://u:p@ss@...``, ``https://alice:pw SPACE@...``).  An IRI nested in the IRI
  (``urn:x:https://u:p@h``, a query ``?to=https://u:p@h``) counts too, and so does a scheme read after
  the digits or signs that start its run of scheme characters (``1https://u:p@h``,
  ``urn:x:1https://u:p@h``).  Excluded: a user without a password (``https://alice@...``) or with an
  empty one (``https://alice:@...``), so a bare token used as the user name is not caught (it is still
  masked); a percent-encoded colon (``alice%3Asecret@``), which is data, not the separator; an ``@`` in
  the path, query or fragment; a scheme without an authority (``mailto:u:p@h``, ``file:///``); and a
  relative reference resolved against the document (GOV002's concern), such as ``1https://u:p@h`` in
  RDF/XML, which resolves it as a relative path because a scheme starts with a letter (it is still
  masked).  The focus is the IRI with its whole userinfo, user name included, replaced by ``****``
  (``https://****@example.test/x``), like every IRI in every finding and output of ontolint (RFC 3986
  section 3.2.1 says not to render the password, and a token sent as the user name cannot be told from a
  name), and the message names no part of the userinfo, so no report or baseline repeats a secret; the
  SARIF region is the credentialed IRI's.  One finding per distinct IRI once masked, so IRIs that differ
  only in their userinfo give one finding, located at the first of them: the finding stays until the last
  is removed.  Error, certain: RFC 3986 section 3.2.1 deprecates ``user:password`` and the syntactic
  test has no false positive; a published credential must be rotated.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import TYPE_CHECKING

from rdflib import BNode, Literal, URIRef
from rdflib.namespace import RDF
from rdflib.term import Node

from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity
from ontolint.redaction import userinfo_password

from .support import relative_reference, value_text

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .runtime import RuleContext


MAX_BLANK_NODE_DEPTH = 100  # Longest chain of nested blank nodes (excluding rdf:rest) tolerated.
MAX_LIST_LENGTH = 5000  # Longest rdf:List tolerated.
MAX_LITERAL_LENGTH = 100_000  # Longest literal lexical form (characters) tolerated.
UNSAFE_SCHEMES = frozenset({"blob", "data", "file", "ftp", "gopher", "jar", "javascript", "vbscript"})

_SCHEME = re.compile(r"([A-Za-z][A-Za-z0-9+.\-]*):")


def _char_class(codepoints: Iterable[int]) -> re.Pattern[str]:
    """Compile a character class that lists every code point, so no range can silently match more."""
    return re.compile("[" + "".join(re.escape(chr(cp)) for cp in sorted(codepoints)) + "]")


_C0_CONTROLS = range(0x20)
_C1_CONTROLS = range(0x7F, 0xA0)
_BIDI_CONTROLS = (*range(0x202A, 0x202F), *range(0x2066, 0x206A))  # embeddings, overrides and isolates
_TEXT_WHITESPACE = frozenset({0x09, 0x0A, 0x0D})  # tab, line feed and carriage return are ordinary in a literal
_LITERAL_HAZARD = _char_class(
    cp for cp in (*_C0_CONTROLS, *_C1_CONTROLS, *_BIDI_CONTROLS) if cp not in _TEXT_WHITESPACE
)
_IRI_HAZARD = _char_class((*_C0_CONTROLS, *_C1_CONTROLS, *_BIDI_CONTROLS))
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
        "Remove the user:password@ part of the IRI and rotate the exposed credential; the report masks it, so find it "
        "at the SARIF region or in the source.",
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
            subject=("nesting",),
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
            subject=("list",),
        )


def _hazards(text: str, pattern: re.Pattern[str]) -> str:
    return ", ".join(sorted({f"U+{ord(c):04X}" for c in pattern.findall(text)}))


def _terms(ctx: RuleContext) -> None:
    iris: set[str] = set()
    # One SEC005 and one SEC012 finding per subject and predicate (their identity), however many literals:
    # the longest literal, and every hazardous character of all of them.
    longest: dict[tuple[Node, Node], int] = {}
    hazardous: dict[tuple[Node, Node], str] = {}
    for s, p, o in ctx.g:
        for node in (s, p, o):
            if isinstance(node, URIRef):
                iris.add(str(node))
        if isinstance(o, Literal):
            text = str(o)
            if len(text) > MAX_LITERAL_LENGTH:
                longest[s, p] = max(len(text), longest.get((s, p), 0))
            if _LITERAL_HAZARD.search(text):
                hazardous[s, p] = hazardous.get((s, p), "") + text
    for (s, p), length in longest.items():
        message = f"Literal on {value_text(p)} has {length} characters (limit {MAX_LITERAL_LENGTH})."
        ctx.add("SEC005", s, message, confidence="certain", subject=(p,))
    for (s, p), text in hazardous.items():
        message = (
            f"Literal on {value_text(p)} contains control or bidirectional-override characters "
            f"({_hazards(text, _LITERAL_HAZARD)})."
        )
        ctx.add("SEC012", s, message, confidence="certain", subject=(p,))
    for iri in sorted(iris):
        _check_iri(ctx, iri)


def _check_iri(ctx: RuleContext, iri: str) -> None:
    if relative_reference(iri, ctx.policy.document_bases) is not None:
        return  # a relative reference resolved against the file (GOV002 reports relative imports)
    scheme = _SCHEME.match(iri.lstrip("\x00 \t\r\n\x0b\x0c").translate(_URL_STRIPPED))
    if scheme and scheme.group(1).lower() in UNSAFE_SCHEMES:
        ctx.add(
            "SEC008", iri, f"IRI uses the unsafe scheme {scheme.group(1).lower()}:.", confidence="certain", subject=()
        )
    found = _hazards(iri, _IRI_HAZARD)
    if found:
        ctx.add(
            "SEC012",
            iri,
            f"IRI contains control or bidirectional-override characters ({found}).",
            confidence="certain",
            subject=(),
        )
    if userinfo_password(iri) is not None:
        # RuleContext.add masks the userinfo of the focus (ontolint.redaction).
        ctx.add("SEC014", iri, "IRI embeds a password in its userinfo.", confidence="certain", subject=())
