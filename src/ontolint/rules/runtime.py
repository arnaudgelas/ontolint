"""Shared run-time state handed to every rule family."""

from __future__ import annotations

import re
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from dataclasses import replace

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDFS, SKOS
from rdflib.term import Node

from ontolint.context import GraphContext
from ontolint.models import CONFIDENCES, Finding
from ontolint.policy import Policy
from ontolint.redaction import redact_userinfo

from .specs import FIXES, SEVERITY
from .support import DESCRIPTIONS, LABEL_STOP, LABELS, stable_blank_id

EMPTY_FOCUS = "<>"


def _with_extras(defaults: tuple[URIRef, ...], extras: tuple[str, ...]) -> tuple[URIRef, ...]:
    """Return the default predicates followed by the configured extra ones, without duplicates."""
    return tuple(dict.fromkeys((*defaults, *(URIRef(extra) for extra in extras))))


class PropertyClosure:
    """The predicates that entail given ones through ``rdfs:subPropertyOf`` and ``owl:equivalentProperty``.

    ``below(seeds, stop)`` is the seeds, then, sorted by IRI, every other IRI ``p`` with a path
    ``p → … → s`` to a seed ``s`` in which each step is an asserted ``x rdfs:subPropertyOf y`` (from ``x``
    to ``y``) or an asserted ``owl:equivalentProperty`` triple read either way, as OWL 2 makes it
    symmetric.  So ``p ⊑ q ≡ r ⊑ s`` and ``p ≡ q ⊑ s`` reach ``s``, while a super-property of a seed,
    and whatever is equivalent to such a super-property, is not reached.  A node of ``stop`` is neither
    returned nor walked through, but a seed is never stopped: ``skos:altLabel`` is below
    ``rdfs:label`` in the SKOS schema, yet no label.  Stop nodes are matched by identity: a predicate
    equivalent to one is not reached through it, but is returned if another path reaches a seed.

    The graph is the one being linted (the merged closure under ``--follow-imports``); nothing is
    entailed beyond the asserted triples, and deprecation changes nothing.  The index is built once
    from the two predicates' triples (which ``max_triples`` caps), and each walk is iterative and
    expands each node once, so a cycle or self-loop ends it and its cost is linear in those triples;
    rdflib's ``transitive_subjects`` recurses once per link instead.  Blank nodes carry a path but are
    never returned, as only an IRI can be a predicate.  Each ``(seeds, stop)`` is computed once.
    """

    def __init__(self, graph: Graph) -> None:
        below: dict[Node, list[Node]] = {}
        for sub, sup in graph.subject_objects(RDFS.subPropertyOf):
            below.setdefault(sup, []).append(sub)
        for one, other in graph.subject_objects(OWL.equivalentProperty):
            below.setdefault(one, []).append(other)
            below.setdefault(other, []).append(one)
        self._below = below
        self._cache: dict[tuple[tuple[URIRef, ...], frozenset[URIRef]], tuple[URIRef, ...]] = {}

    def below(self, seeds: tuple[URIRef, ...], stop: frozenset[URIRef] = frozenset()) -> tuple[URIRef, ...]:
        """Return ``seeds`` followed by the IRIs below them, sorted (see the class)."""
        key = (seeds, stop)
        if key not in self._cache:
            seen: set[Node] = set(seeds)
            stack: list[Node] = list(seeds)
            while stack:
                for sub in self._below.get(stack.pop(), ()):
                    if sub not in seen and sub not in stop:
                        seen.add(sub)
                        stack.append(sub)
            derived = sorted((node for node in seen - set(seeds) if isinstance(node, URIRef)), key=str)
            self._cache[key] = (*seeds, *derived)
        return self._cache[key]


# A ``_:`` that may start a blank-node label of a message, and what continues a label past its end: ``_:x`` inside
# an IRI or a longer name (``#_:x``, ``_:x-y``, ``_:x.y``) is not the blank node ``x``.
_LABEL_START = re.compile(r"(?<![\w/#:-])_:")
# ``\w`` misses the Turtle PN_CHARS that are not letters or digits: the middle dot, the combining marks, the undertie.
_LABEL_GOES_ON = re.compile("[\\w/#:\\-\u00b7\u0300-\u036f\u203f\u2040]|\\.[\\w\u00b7\u0300-\u036f\u203f\u2040]")


class _BlankNames:
    """The stable identities of one graph's blank nodes, and the rewriting of their ``_:label`` inside messages.

    Every rule writes a blank node of its message ``_:label`` (:func:`~ontolint.rules.support.term_text`,
    :func:`~ontolint.rules.support.value_text`, :func:`~ontolint.rules.support.quoted_text`), and only that
    spelling is rewritten (see :meth:`rewrite`), so a message never depends on the labels a parser or an API
    caller chose: neither a label left in it nor a label such as JSON-LD's ``_:2`` rewriting a count or a word.
    """

    def __init__(self, graph: Graph) -> None:
        self.graph = graph
        self._ids: dict[BNode, str] = {}
        self._nodes: dict[str, BNode] | None = None  # label -> node, built on first use
        self._lengths: list[int] = []  # the labels' distinct lengths, longest first

    def identity(self, node: BNode) -> str:
        if node not in self._ids:
            self._ids[node] = stable_blank_id(self.graph, node)
        return self._ids[node]

    def rewrite(self, message: str) -> str:
        """Replace each ``_:label`` of a blank node of the graph inside ``message`` by the node's stable identity.

        The labels are those of the nodes in subject or object position; a node used only as a predicate, which
        RDF does not allow, is left as written.  ``_:label`` is replaced where it is neither preceded nor followed
        by a word character, ``/``, ``#``, ``:`` or ``-``, nor followed by ``.`` and a word character, so a label
        inside an IRI or a longer name stays; where labels of several lengths fit, the longest is taken.  A bare
        label is text, even one that holds a digit.

        Nothing tells ``_:label`` written by a rule from the same text copied into the message from a literal or
        an IRI (``"_:x"``, ``?q=_:x``) when ``x`` labels a node of the graph: that text is replaced too, as is an
        identity a rule wrote itself (``_:`` and 12 hex digits) when a label of the graph is those 12 digits.

        Each ``_:`` is looked up once per distinct label length, longest first, so its cost never grows with the
        number of labels; a message without ``_:`` never indexes the graph.
        """
        if "_:" not in message:
            return message
        if self._nodes is None:
            self._nodes = {str(n): n for t in self.graph for n in (t[0], t[2]) if isinstance(n, BNode)}
            self._lengths = sorted({len(label) for label in self._nodes}, reverse=True)
        nodes = self._nodes
        parts: list[str] = []
        done = 0  # ``parts`` holds ``message[:done]``, rewritten
        for prefix in _LABEL_START.finditer(message):
            if prefix.start() < done:  # inside a label just replaced
                continue
            begin = prefix.end()
            for length in self._lengths:
                end = begin + length
                node = nodes.get(message[begin:end])
                if node is not None and not _LABEL_GOES_ON.match(message, end):
                    parts += (message[done : prefix.start()], self.identity(node))
                    done = end
                    break
        parts.append(message[done:])
        return "".join(parts)


class RuleContext:
    """Graphs, policy, indexed facts, and the de-duplicating finding emitter for one lint run."""

    def __init__(self, graph: Graph, shapes: Graph | None, policy: Policy, context: GraphContext) -> None:
        self.g = graph
        self.shapes = shapes
        # SHACL-only background (stage 4 of the import closure): the ontology the shapes import, merged
        # into the data graph for validation but never judged by the term rules.
        self.shacl_background: Graph | None = None
        self.policy = policy
        self.context = context
        self.findings: list[Finding] = []
        self.seen: set[tuple[str, str, str]] = set()
        self._emitted: dict[tuple[str, str, str], int] = {}  # each seen key's position in ``findings``
        # Blank nodes are named by their content in the graph the running rules report on: the data graph,
        # or the shapes graph inside :meth:`naming_shapes`.  Every rule spells a blank node of a message ``_:label``
        # (:func:`~ontolint.rules.support.value_text`), and only that spelling is rewritten, in either graph.
        self._data_names = _BlankNames(graph)
        self._shape_names = _BlankNames(shapes) if shapes is not None else None
        self._names = self._data_names
        # The configured definition and label predicates, then every IRI below one of them (sorted).
        # ``labels`` says whether a term has a label and which values are judged as labels;
        # ``main_label_predicates`` says which of them name the term (see there).
        self.closure = PropertyClosure(graph)
        self.descriptions: tuple[URIRef, ...] = self.closure.below(
            _with_extras(DESCRIPTIONS, policy.extra_definition_predicates)
        )
        self.configured_labels: tuple[URIRef, ...] = _with_extras(LABELS, policy.extra_label_predicates)
        self.labels: tuple[URIRef, ...] = self.closure.below(self.configured_labels, LABEL_STOP)
        # skos:prefLabel and the predicates below it: preferred labels, by entailment.
        self.preferred_labels: tuple[URIRef, ...] = self.closure.below((SKOS.prefLabel,), LABEL_STOP)
        self._main_labels = tuple(dict.fromkeys((*self.configured_labels, *self.preferred_labels)))
        self._main_label_predicates: dict[Node, tuple[URIRef, ...]] = {}  # per term, several rules ask

    def main_label_predicates(self, term: Node) -> tuple[URIRef, ...]:
        """The predicates of ``term``'s main labels, which the rules comparing labels read.

        They are the configured label predicates and the preferred labels (``preferred_labels``)
        when ``term`` has a ``Literal`` under one of them, else every label predicate (``labels``).
        LEX003, LEX004, LEX006, LEX015, LEX016 and CLS010 read them; LEX008, which asks only whether a
        label exists in a language, reads ``labels`` as LEX001 does.

        A value of a sub-property of skos:prefLabel is a skos:prefLabel by entailment, so it is always
        a main label, also beside a configured label in another language.  A sub-property of
        rdfs:label (or of an extra) beside a main label is a specialised label: BFO 2020 gives each
        class an untagged OWL and CLIF specification label beside its tagged rdfs:label, and these are
        neither second labels, nor plain labels mixed with tagged ones, nor collisions.  Only a term
        with no main label at all is named by its specialised labels.
        """
        found = self._main_label_predicates.get(term)
        if found is None:
            named = any(isinstance(o, Literal) for p in self._main_labels for o in self.g.objects(term, p))
            found = self._main_label_predicates[term] = self._main_labels if named else self.labels
        return found

    @property
    def ontologies(self) -> frozenset[URIRef]:
        return self.context.ontologies

    @property
    def classes(self) -> frozenset[URIRef]:
        return self.context.classes

    @property
    def properties(self) -> frozenset[URIRef]:
        return self.context.properties

    @property
    def concepts(self) -> frozenset[URIRef]:
        return self.context.concepts

    @property
    def terms(self) -> frozenset[URIRef]:
        return self.context.terms

    def local(self, node: object) -> bool:
        """Return whether ``node`` is owned by the linted ontology (see :mod:`ontolint.ownership`)."""
        return self.context.ownership.owns(node)

    def add(  # noqa: PLR0913 -- the finding's parts; everything after the message is keyword-only.
        self,
        code: str,
        focus: object,
        message: str,
        *,
        confidence: str = "heuristic",
        related: Iterable[object] = (),
        subject: Iterable[object] = (),
    ) -> None:
        """Record a finding once per ``(rule, focus, message)``; severity and fix come from the specs.

        Focus, message, related terms and subject are masked (:func:`~ontolint.redaction.redact_userinfo`) before
        duplicates are removed, so IRIs that differ only in their userinfo give one finding.

        A blank node in ``message`` is written ``_:label`` (:func:`~ontolint.rules.support.value_text`), which is
        replaced by the node's stable identity when the node is a subject or an object of the graph the running
        rules report on; a bare label is left as text (see ``_BlankNames.rewrite``).

        ``related`` names the other terms a finding is about (the rest of a collision); they place the
        finding in every module involved (``--module-by``) and never change its identity or text.

        ``subject`` is what tells this finding from another of the same rule on the same focus, in a fixed
        order (sorted where it is a set): the baseline identity is the rule, the focus and the subject, so
        a reworded message keeps matching a baseline.  It holds machine values only: IRIs, blank nodes
        (rendered by their stable identity), literals (in N3, with their language or datatype), language
        tags and other keys.  Never prose, counts, ratios, thresholds or labels quoted for readability:
        a measurement that changes is not a new problem.  ``subject=()`` states that the rule reports at
        most one finding per focus.  It is never rendered.  When one message is emitted with several
        subjects, the finding keeps the least of them, so it does not depend on iteration order; a subject
        should still say no more than the message does.
        """
        if confidence not in CONFIDENCES:
            raise ValueError(f"{code}: confidence must be one of {sorted(CONFIDENCES)}, not {confidence!r}")
        text = self._focus_text(focus)
        message = self._message_text(message)
        key = (code, text, message)
        about = tuple(map(self._subject_text, subject))
        if key in self.seen:
            # One finding per message: of the subjects offered for it, keep the least, so the subject does not
            # depend on the order the graph is iterated in (a rule's subject finer than its message).
            index = self._emitted[key]
            self.findings[index] = replace(self.findings[index], subject=min(about, self.findings[index].subject))
            return
        self.seen.add(key)
        self._emitted[key] = len(self.findings)
        others = tuple(dict.fromkeys(t for t in map(self._focus_text, related) if t != text))
        self.findings.append(
            Finding(code, SEVERITY[code], text, message, FIXES[code], confidence, related=others, subject=about)
        )

    @contextmanager
    def naming_shapes(self) -> Generator[None]:
        """Name blank nodes by their content in the shapes graph while the block runs (rules about shapes).

        An inline shape (``sh:property [ ... ]``) has no triple in the data graph, where every such node would
        get the identity of an empty node.  Without a shapes graph this changes nothing.
        """
        previous = self._names
        self._names = self._shape_names or self._data_names
        try:
            yield
        finally:
            self._names = previous

    def _stable_id(self, node: BNode) -> str:
        return self._names.identity(node)

    def _message_text(self, message: str) -> str:
        """Replace parser-assigned blank-node labels inside ``message`` by their stable identity; mask userinfo."""
        return redact_userinfo(self._names.rewrite(message))

    def _subject_text(self, item: object) -> str:
        """Render one part of a subject: a blank node by its stable identity, a literal in N3, an IRI as is (masked).

        A string is taken as an already rendered key; anything else (a count, say) is refused, because a
        subject names what a finding is about, never how much.
        """
        if isinstance(item, BNode):
            return self._stable_id(item)
        if isinstance(item, Literal):
            return redact_userinfo(item.n3())
        if isinstance(item, URIRef):
            return redact_userinfo(str(item)) or EMPTY_FOCUS
        if isinstance(item, str):
            return redact_userinfo(item)
        raise TypeError(f"a finding subject holds terms and keys, not {type(item).__name__}: {item!r}")

    def _focus_text(self, focus: object) -> str:
        """Render a focus: blank nodes by stable content identity, the empty IRI as ``<>``, a userinfo masked."""
        if isinstance(focus, BNode):
            return self._stable_id(focus)
        return redact_userinfo(str(focus)) or EMPTY_FOCUS
