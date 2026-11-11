"""Metamorphic relation: textual noise in a Turtle file (layout, comments, spelling of IRIs) never changes findings.

Turtle has many spellings of one graph.  ``TurtleWriter`` renders a graph's triples one statement per line and, as
directed by a drawn :class:`Noise`, adds comments, blank lines and indentation, renames the prefix labels, spells
terms as CURIEs or full IRIs, writes ``a`` for ``rdf:type``, declares ``@base`` and relative IRIs, and uses either
declaration style.  The reference is the same graph as N-Triples, with no noise at all.  Source regions may move
(they follow the text); the findings' identity fields (rule, severity, focus, message) may not.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from pathlib import Path

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st
from hypothesis_strategies import BASE, FOREIGN, OBO, budget, roundtrip_triple_lists
from hypothesis_strategies import build_graph as build
from metamorphic_support import Triple, cli_json, document_keys, keys, lint_all, serialisable, workdir
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.compare import isomorphic
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS, XSD
from rdflib.term import Node

from ontolint.loader import load_graph
from ontolint.paths import resolve_inputs
from ontolint.policy import Policy

pytestmark = pytest.mark.slow

NAMESPACES = (BASE, FOREIGN, OBO, str(OWL), str(RDF), str(RDFS), str(SKOS), str(DCTERMS), str(XSD))
LABEL_POOL = ("ex", "o", "a", "zz", "owlns", "x1", "p_q", "dc", "Ont", "n", "ns1", "foo-bar")
LOCAL_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")  # Plain ASCII names; anything else is spelled as a full IRI.
# Bases for which a relative reference below resolves back to the same IRI.  The fragment namespace itself is no
# base: ``A`` resolved against ``https://example.test/onto#`` is ``https://example.test/A``.
BASES = (None, "https://example.test/", "https://example.test/onto", OBO)
LINE_NOISE = 0.4  # Chance that a statement is preceded by a comment or blank line, or followed by a comment.
COMMENTS = (
    "a comment",
    "# {",
    '<https://example.test/onto#Fake> a <http://www.w3.org/2002/07/owl#Class> . # "quoted"',
    "@prefix fake: <urn:fake:> .",
    "\t\t tabs  and   spaces",
    "unicode é 日本 \U0001f600",
)


@dataclass(frozen=True)
class Noise:
    """Which kinds of textual noise a rendering applies, and the random stream that places it."""

    rng: random.Random
    labels: tuple[str, ...]  # One distinct prefix label per namespace, in ``NAMESPACES`` order.
    base: str | None
    sparql_style: bool  # ``PREFIX p: <...>`` and ``BASE <...>`` instead of ``@prefix p: <...> .``.
    curie_rate: float  # Share of terms spelled with a prefix label instead of a full IRI.
    relative_rate: float  # Share of the remaining IRIs under the base spelled relatively.
    keyword_rate: float  # Share of rdf:type predicates written ``a``.
    comments: bool
    blanks: bool
    indent: str
    padding: str  # Whitespace between the three terms of a statement.


noises = st.builds(
    Noise,
    rng=st.randoms(use_true_random=False),
    labels=st.permutations(LABEL_POOL).map(lambda p: tuple(p[: len(NAMESPACES)])),
    base=st.sampled_from(BASES),
    sparql_style=st.booleans(),
    curie_rate=st.sampled_from((0.0, 0.5, 1.0)),
    relative_rate=st.sampled_from((0.0, 0.5, 1.0)),
    keyword_rate=st.sampled_from((0.0, 1.0)),
    comments=st.booleans(),
    blanks=st.booleans(),
    indent=st.sampled_from(("", " ", "\t", "    ")),
    padding=st.sampled_from((" ", "  ", "\t", " \t ")),
)


class TurtleWriter:
    """Renders triples as Turtle text under a :class:`Noise`."""

    def __init__(self, noise: Noise) -> None:
        self.noise = noise
        self.prefixes = dict(zip(NAMESPACES, noise.labels, strict=True))
        self.used: set[str] = set()  # Namespaces some term was spelled with.

    def iri(self, node: URIRef) -> str:
        """One spelling of ``node``: a CURIE, a relative reference under the base, or the full IRI."""
        noise, text = self.noise, str(node)
        if node == RDF.type and noise.rng.random() < noise.keyword_rate:
            return "a"
        if noise.rng.random() < noise.curie_rate:
            for namespace, label in self.prefixes.items():
                local = text[len(namespace) :]
                if text.startswith(namespace) and LOCAL_NAME.fullmatch(local):
                    self.used.add(namespace)
                    return f"{label}:{local}"
        if noise.base and text.startswith(noise.base) and noise.rng.random() < noise.relative_rate:
            relative = text[len(noise.base) :]
            if relative != "#" and ":" not in relative and not relative.startswith("/"):
                return f"<{relative}>"
        return f"<{text}>"

    def term(self, node: Node) -> str:
        """Turtle for an IRI, blank node or literal."""
        if isinstance(node, URIRef):
            return self.iri(node)
        if isinstance(node, BNode):
            return f"_:{node}"
        assert isinstance(node, Literal) and node.datatype is None  # roundtrip_triple_lists gives plain literals only
        text = Literal(str(node)).n3()
        return f"{text}@{node.language}" if node.language else text

    def render(self, triples: list[Triple]) -> str:
        """The whole document."""
        noise = self.noise
        lines: list[str] = []
        for subject, predicate, obj in triples:
            if noise.comments and noise.rng.random() < LINE_NOISE:
                lines.append(noise.indent + "# " + noise.rng.choice(COMMENTS))
            if noise.blanks and noise.rng.random() < LINE_NOISE:
                lines.append(noise.rng.choice(("", " ", "\t")))
            parts = [self.term(subject), self.term(predicate), self.term(obj)]
            statement = noise.indent + noise.padding.join(parts) + noise.padding + "."
            if noise.comments and noise.rng.random() < LINE_NOISE:
                statement += " # " + noise.rng.choice(COMMENTS)
            lines.append(statement)
        # Only the prefixes in use are declared: IRI019 reports an unused declaration, which is a statement about
        # the text, so declaring every prefix would be a change of meaning for that rule, not noise.
        header = [
            f"PREFIX {label}: <{namespace}>" if noise.sparql_style else f"@prefix {label}: <{namespace}> ."
            for namespace, label in self.prefixes.items()
            if namespace in self.used
        ]
        if noise.base:
            header.append(f"BASE <{noise.base}>" if noise.sparql_style else f"@base <{noise.base}> .")
        return "\n".join([*header, *lines]) + "\n"


def load(path: Path, root: Path) -> Graph:
    """Read ``path`` through the real loader."""
    return load_graph(resolve_inputs([path.name], root)[0], Policy(), root)


@budget(1)
@given(roundtrip_triple_lists(), noises)
def test_findings_do_not_depend_on_the_turtle_spelling_through_the_loader(triples: list, noise: Noise) -> None:
    """RELATION (textual noise invariance): comments, blank lines, indentation, prefix labels, CURIE versus full
    IRI, ``a``, ``@base`` with relative IRIs and the declaration style leave the findings unchanged."""
    graph = build(serialisable(triples))
    assume(len(graph))

    with workdir() as root:
        (root / "plain.nt").write_text(graph.serialize(format="nt"), encoding="utf-8")
        (root / "noisy.ttl").write_text(TurtleWriter(noise).render(sorted(graph)), encoding="utf-8")
        plain, noisy = load(root / "plain.nt", root), load(root / "noisy.ttl", root)

    assert isomorphic(noisy, plain)  # The transformation itself must keep the meaning, or the relation is void.
    assert keys(lint_all(noisy)) == keys(lint_all(plain))


@budget(0.5)
@given(roundtrip_triple_lists(), noises)
def test_the_cli_reports_the_same_findings_for_any_turtle_spelling(triples: list, noise: Noise) -> None:
    """RELATION (textual noise invariance, CLI): ``--format json`` on the noisy Turtle file and on the plain
    N-Triples file agree on exit code, summary and findings; only the ``path`` differs."""
    graph = build(serialisable(triples))
    assume(len(graph))

    with workdir() as root:
        (root / "plain.nt").write_text(graph.serialize(format="nt"), encoding="utf-8")
        (root / "noisy.ttl").write_text(TurtleWriter(noise).render(sorted(graph)), encoding="utf-8")
        code, reference = cli_json("plain.nt")
        noisy_code, document = cli_json("noisy.ttl")

    assert noisy_code == code
    assert document_keys(document) == document_keys(reference)
    assert document["summary"] == reference["summary"]
