"""A finding's structured ``subject``: what it is about beyond rule and focus, never rendered."""

from __future__ import annotations

import json

import pytest
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

from ontolint import Linter
from ontolint.engine import build_context
from ontolint.models import Finding
from ontolint.policy import Policy
from ontolint.reporting import FileReport, RunReport, fingerprint, render_report
from ontolint.rules.runtime import EMPTY_FOCUS, RuleContext

EX = "https://example.test/"


def _ctx(graph: Graph | None = None) -> RuleContext:
    return build_context(graph if graph is not None else Graph(), None, Policy())


def test_subject_renders_terms_and_keeps_order() -> None:
    ctx = _ctx()
    ctx.add(
        "OWL002",
        URIRef(EX + "p"),
        "message",
        subject=(RDFS.range, Literal("x", lang="en"), Literal("1", datatype=XSD.integer), "key", URIRef("")),
    )

    assert ctx.findings[0].subject == (
        str(RDFS.range),
        '"x"@en',
        f'"1"^^<{XSD.integer}>',
        "key",
        EMPTY_FOCUS,
    )


def test_subject_names_a_blank_node_by_its_stable_identity() -> None:
    graph = Graph()
    node = BNode("parserlabel1")
    graph.add((node, RDF.type, OWL.Restriction))
    ctx = _ctx(graph)
    ctx.add("OWL002", URIRef(EX + "p"), "message", subject=(node,))

    (part,) = ctx.findings[0].subject
    assert part.startswith("_:")
    assert "parserlabel1" not in part
    assert part == ctx._focus_text(node)  # noqa: SLF001 -- the same identity a blank focus has


@pytest.mark.parametrize("value", [3, 0.5, True, None, (URIRef(EX + "a"),)])
def test_subject_refuses_anything_but_terms_and_keys(value: object) -> None:
    with pytest.raises(TypeError, match="a finding subject holds terms and keys"):
        _ctx().add("OWL002", URIRef(EX + "p"), "message", subject=(value,))


def test_subject_defaults_to_empty_and_does_not_change_deduplication() -> None:
    ctx = _ctx()
    ctx.add("OWL002", URIRef(EX + "p"), "message")
    ctx.add("OWL002", URIRef(EX + "p"), "message", subject=(RDFS.range,))

    assert [f.subject for f in ctx.findings] == [()]


def test_subject_is_not_rendered_and_not_part_of_equality_or_fingerprint() -> None:
    plain = Finding("ONT001", "warning", "focus", "message", "fix")
    about = Finding("ONT001", "warning", "focus", "message", "fix", subject=("x",))

    assert plain == about
    assert hash(plain) == hash(about)
    assert fingerprint(plain) == fingerprint(about)
    assert about.to_dict() == plain.to_dict()
    assert "subject" not in about.to_dict()
    for fmt in ("json", "sarif", "text"):
        rendered = render_report(RunReport((FileReport("a.ttl", "file:///a.ttl", (about,)),)), fmt)
        assert rendered == render_report(RunReport((FileReport("a.ttl", "file:///a.ttl", (plain,)),)), fmt)
    assert "subject" not in json.loads(render_report(RunReport((FileReport("a.ttl", "a.ttl", (about,)),)), "json"))


def test_one_message_with_several_subjects_keeps_the_least_whatever_the_order() -> None:
    first, second = (URIRef(EX + "b"),), (URIRef(EX + "a"),)
    forward, backward = _ctx(), _ctx()
    for ctx, order in ((forward, (first, second)), (backward, (second, first))):
        ctx.add("OWL002", URIRef(EX + "p"), "message", subject=order[0])
        ctx.add("OWL002", URIRef(EX + "q"), "other")
        ctx.add("OWL002", URIRef(EX + "p"), "message", subject=order[1])

    assert [f.subject for f in forward.findings] == [(EX + "a",), ()]
    assert [f.subject for f in backward.findings] == [(EX + "a",), ()]
    assert forward.findings == backward.findings


def test_the_linter_facade_passes_the_subject_through() -> None:
    linter = Linter(Graph())
    linter.add("OWL002", URIRef(EX + "p"), "message", subject=(RDFS.range,))
    linter.add("OWL002", URIRef(EX + "q"), "message")
    assert [f.subject for f in linter.rule_context.findings] == [(str(RDFS.range),), ()]
