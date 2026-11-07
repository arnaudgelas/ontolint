"""Exact-expectation tests for bugs found by the fuzzer and the property suite (IRI parsing, focus identity)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from ontolint import Linter, main
from ontolint.rules.runtime import EMPTY_FOCUS
from ontolint.rules.support import DIGEST_DEPTH, safe_urlsplit, stable_blank_id

EX = "https://example.test/onto#"


def _ex(name: str) -> URIRef:
    return URIRef(EX + name)


def _run(data: Graph, *rules: str) -> list[tuple[str, str, str]]:
    result = Linter(data, None).execute(list(rules))
    assert not [x for x in result.executions if x.status.value == "failed"], result.executions
    return [(f.rule, f.focus, f.message) for f in result.findings]


# --- safe_urlsplit --------------------------------------------------------------------------------


def test_safe_urlsplit_matches_urlsplit_for_valid_iris() -> None:
    pieces = safe_urlsplit("https://host.test/a/b?q=1#frag")
    assert (pieces.scheme, pieces.netloc, pieces.path, pieces.query, pieces.fragment) == (
        "https",
        "host.test",
        "/a/b",
        "q=1",
        "frag",
    )


def test_safe_urlsplit_returns_an_empty_split_for_malformed_iris() -> None:
    pieces = safe_urlsplit("s://]")
    assert tuple(pieces) == ("", "", "", "", "")
    assert pieces.hostname is None


def test_iri001_flags_a_malformed_iri_instead_of_crashing() -> None:
    data = Graph()
    data.add((URIRef("s://]"), RDF.type, OWL.Class))
    findings = _run(data, "IRI001", "IRI006", "IRI008", "IRI013")
    assert findings == [("IRI001", "s://]", "IRI contains whitespace or is not absolute.")]


def test_ontology_iri_rules_survive_a_malformed_ontology_iri() -> None:
    data = Graph()
    data.add((URIRef("s://]"), RDF.type, OWL.Ontology))
    data.add((_ex("A"), RDF.type, OWL.Class))
    assert _run(data, "IRI001", "IRI004", "IRI016", "IRI017", "IRI002") == [
        ("IRI001", "s://]", "IRI contains whitespace or is not absolute.")
    ]


def test_ontology_namespace_rule_survives_a_malformed_root() -> None:
    data = Graph()
    data.add((URIRef("s://]#"), RDF.type, OWL.Ontology))
    data.add((_ex("A"), RDF.type, OWL.Class))
    assert _run(data, "IRI004") == []


# --- empty focus ----------------------------------------------------------------------------------


def test_finding_about_the_empty_iri_gets_a_visible_focus() -> None:
    data = Graph()
    data.add((URIRef(""), RDF.type, OWL.Class))
    findings = _run(data, "IRI001")
    assert EMPTY_FOCUS == "<>"
    assert findings == [("IRI001", "<>", "IRI contains whitespace or is not absolute.")]


def test_non_empty_iri_focus_is_unchanged() -> None:
    data = Graph()
    data.add((URIRef("relative"), RDF.type, OWL.Class))
    assert _run(data, "IRI001")[0][1] == "relative"


# --- OWL011 ---------------------------------------------------------------------------------------


def _two_property_restriction(first: URIRef, second: URIRef) -> Graph:
    data = Graph()
    node = BNode("r")
    data.add((_ex("A"), RDF.type, OWL.Class))
    data.add((node, OWL.allValuesFrom, _ex("A")))
    data.add((_ex("A"), RDFS.subClassOf, node))
    data.add((node, OWL.onProperty, first))
    data.add((node, OWL.onProperty, second))
    return data


def test_owl011_names_every_property_in_sorted_order() -> None:
    expected = [
        (
            "OWL011",
            EX + "A",
            f"Universal restriction on {EX}p, {EX}q does not imply any property value.",
        )
    ]
    assert _run(_two_property_restriction(_ex("p"), _ex("q")), "OWL011") == expected
    assert _run(_two_property_restriction(_ex("q"), _ex("p")), "OWL011") == expected


def test_owl011_blank_node_properties_are_named_independently_of_parser_labels() -> None:
    """Sorting by raw blank-node labels made the message depend on how the parser labelled the nodes."""

    def build(first: str, second: str) -> Graph:
        data = Graph()
        restriction = BNode("r")
        data.add((_ex("A"), RDF.type, OWL.Class))
        data.add((restriction, OWL.allValuesFrom, _ex("A")))
        data.add((_ex("A"), RDFS.subClassOf, restriction))
        for label, target in ((first, _ex("p")), (second, _ex("q"))):
            inverse = BNode(label)
            data.add((restriction, OWL.onProperty, inverse))
            data.add((inverse, OWL.inverseOf, target))
        return data

    messages = {_run(build(a, b), "OWL011")[0][2] for a, b in (("a", "b"), ("b", "a"), ("x9", "c1"), ("c1", "x9"))}
    assert len(messages) == 1
    assert re.fullmatch(
        r"Universal restriction on _:[0-9a-f]{12}, _:[0-9a-f]{12} does not imply any property value\.", messages.pop()
    )


def test_owl011_single_property_message_is_unchanged_and_datatype_property_is_exempt() -> None:
    data = Graph()
    node = BNode("r")
    data.add((_ex("A"), RDF.type, OWL.Class))
    data.add((node, OWL.allValuesFrom, _ex("A")))
    data.add((_ex("A"), RDFS.subClassOf, node))
    data.add((node, OWL.onProperty, _ex("p")))
    assert _run(data, "OWL011")[0][2] == f"Universal restriction on {EX}p does not imply any property value."
    data.add((_ex("q"), RDF.type, OWL.DatatypeProperty))
    data.add((node, OWL.onProperty, _ex("q")))
    assert _run(data, "OWL011") == []  # any datatype property exempts the restriction


def test_owl011_without_a_property_has_no_via_clause() -> None:
    data = Graph()
    node = BNode("r")
    data.add((_ex("A"), RDF.type, OWL.Class))
    data.add((node, OWL.allValuesFrom, _ex("A")))
    data.add((_ex("A"), RDFS.subClassOf, node))
    assert _run(data, "OWL011")[0][2] == "Universal restriction does not imply any property value."


# --- stable blank node identity ---------------------------------------------------------------------


def _labelled(label: str) -> Graph:
    data = Graph()
    node = BNode(label)
    data.add((_ex("A"), RDFS.subClassOf, node))
    data.add((node, OWL.unionOf, RDF.nil))
    data.add((node, RDFS.label, Literal("x")))
    return data


def test_stable_blank_id_has_a_fixed_shape_and_ignores_labels() -> None:
    one, two = stable_blank_id(_labelled("a"), BNode("a")), stable_blank_id(_labelled("zzz"), BNode("zzz"))
    assert one == two
    assert re.fullmatch(r"_:[0-9a-f]{12}", one)


def test_stable_blank_id_depends_on_content_owner_and_referencing_predicate() -> None:
    base = stable_blank_id(_labelled("a"), BNode("a"))

    other_literal = _labelled("a")
    other_literal.set((BNode("a"), RDFS.label, Literal("y")))
    assert stable_blank_id(other_literal, BNode("a")) != base

    other_owner = _labelled("a")
    other_owner.remove((_ex("A"), RDFS.subClassOf, BNode("a")))
    other_owner.add((_ex("B"), RDFS.subClassOf, BNode("a")))
    assert stable_blank_id(other_owner, BNode("a")) != base

    other_predicate = _labelled("a")
    other_predicate.remove((_ex("A"), RDFS.subClassOf, BNode("a")))
    other_predicate.add((_ex("A"), RDFS.subPropertyOf, BNode("a")))
    assert stable_blank_id(other_predicate, BNode("a")) != base

    no_owner = Graph()
    no_owner.add((BNode("a"), OWL.unionOf, RDF.nil))
    with_owner = Graph()
    with_owner.add((_ex("A"), OWL.unionOf, BNode("a")))
    with_owner.add((BNode("a"), OWL.unionOf, RDF.nil))
    assert stable_blank_id(no_owner, BNode("a")) != stable_blank_id(with_owner, BNode("a"))


def test_stable_blank_id_distinguishes_iri_from_literal_objects() -> None:
    iri, literal = Graph(), Graph()
    iri.add((BNode("a"), RDFS.label, URIRef("x")))
    literal.add((BNode("a"), RDFS.label, Literal("x")))
    assert stable_blank_id(iri, BNode("a")) != stable_blank_id(literal, BNode("a"))


def test_stable_blank_id_follows_nested_blank_nodes_and_survives_cycles() -> None:
    def build(outer: str, inner: str, tail: URIRef) -> Graph:
        data = Graph()
        data.add((BNode(outer), OWL.unionOf, BNode(inner)))
        data.add((BNode(inner), RDF.first, tail))
        data.add((BNode(inner), RDF.rest, BNode(outer)))  # cycle
        return data

    assert stable_blank_id(build("o", "i", _ex("a")), BNode("o")) == stable_blank_id(
        build("p", "j", _ex("a")), BNode("p")
    )
    assert stable_blank_id(build("o", "i", _ex("a")), BNode("o")) != stable_blank_id(
        build("o", "i", _ex("b")), BNode("o")
    )


def test_stable_blank_id_content_digest_stops_at_the_depth_limit() -> None:
    def chain(length: int, leaf: str) -> Graph:
        data = Graph()
        for index in range(length):
            data.add((BNode(f"n{index}"), RDF.rest, BNode(f"n{index + 1}")))
        data.add((BNode(f"n{length}"), RDF.first, Literal(leaf)))
        return data

    # Differences deeper than DIGEST_DEPTH are not part of the identity ...
    deep = DIGEST_DEPTH + 2
    assert stable_blank_id(chain(deep, "a"), BNode("n0")) == stable_blank_id(chain(deep, "b"), BNode("n0"))
    # ... while differences within it are.
    shallow = DIGEST_DEPTH - 2
    assert stable_blank_id(chain(shallow, "a"), BNode("n0")) != stable_blank_id(chain(shallow, "b"), BNode("n0"))


def test_blank_node_focus_is_stable_across_parses_and_named_focus_is_untouched() -> None:
    text = "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n[] owl:unionOf () .\n"
    runs = [_run(Graph().parse(data=text, format="turtle"), "OWL031") for _ in range(3)]
    assert runs[0] == runs[1] == runs[2]
    assert runs[0][0][0] == "OWL031"
    assert re.fullmatch(r"_:[0-9a-f]{12}", runs[0][0][1])


def test_same_blank_node_reported_twice_reuses_its_cached_identity() -> None:
    data = Graph()
    node = BNode("q")
    data.add((node, OWL.unionOf, RDF.nil))
    data.add((node, OWL.intersectionOf, RDF.nil))
    findings = _run(data, "OWL031")
    assert len({focus for _rule, focus, _message in findings}) == 1


def test_cli_baseline_silences_blank_node_findings_on_reparse(tmp_path: Path) -> None:
    source, baseline, out = tmp_path / "o.ttl", tmp_path / "b.json", tmp_path / "out.json"
    source.write_text("@prefix owl: <http://www.w3.org/2002/07/owl#> .\n[] owl:unionOf () .\n", encoding="utf-8")
    main([str(source), "--write-baseline", str(baseline), "--output", str(out), "--format", "json"])
    main([str(source), "--baseline", str(baseline), "--output", str(out), "--format", "json"])
    assert json.loads(out.read_text(encoding="utf-8"))["findings"] == []


# --- surrogates through rendering -------------------------------------------------------------------


def test_lone_surrogate_in_a_literal_renders_in_every_format(tmp_path: Path) -> None:
    source = tmp_path / "o.jsonld"
    source.write_text(
        json.dumps(
            {
                "@context": {"p": {"@type": "@id"}},
                "@id": "http://e/a",
                "@type": "http://www.w3.org/2002/07/owl#Class",
                "http://www.w3.org/2000/01/rdf-schema#label": "A\ud800",
            }
        ),
        encoding="utf-8",
    )
    for fmt in ("text", "json", "sarif"):
        out = tmp_path / f"out.{fmt}"
        code = main([str(source), "--format", fmt, "--output", str(out), "--fail-on", "never"])
        assert code == 0, fmt
        assert out.read_bytes()


# --- blank-node labels inside messages ----------------------------------------------------------------


def _skos013_message(label: str, subject: URIRef | None = None) -> str:
    from rdflib.namespace import SKOS  # noqa: PLC0415

    data = Graph()
    term = subject or _ex("A")
    data.add((term, RDF.type, OWL.Class))
    data.add((term, SKOS.prefLabel, BNode(label)))
    findings = _run(data, "SKOS013")
    assert len(findings) == 1
    return findings[0][2]


def test_blank_label_in_a_message_is_replaced_by_the_stable_identity() -> None:
    message = _skos013_message("QBNX1")
    assert "QBNX1" not in message
    assert re.fullmatch(r"skos:prefLabel value '_:[0-9a-f]{12}' is not a string literal\.", message)
    assert message == _skos013_message("other")


def test_short_blank_label_inside_an_iri_is_left_alone() -> None:
    message = _skos013_message("b0", _ex("b0"))
    assert message.startswith("skos:prefLabel value '_:")
    assert "b0" not in message.split("'")[1]
    assert re.fullmatch(r"skos:prefLabel value '_:[0-9a-f]{12}' is not a string literal\.", message)


def test_graphs_without_blank_nodes_leave_messages_untouched() -> None:
    data = Graph()
    data.add((_ex("A"), RDF.type, OWL.Class))
    data.add((_ex("A"), RDFS.label, Literal("")))
    findings = _run(data, "CLS001", "SKOS013")
    assert all("_:" not in message for _rule, _focus, message in findings)


# --- confidence values --------------------------------------------------------------------------------------


def test_rule_context_rejects_a_confidence_outside_the_two_known_values() -> None:
    """A rule once passed its category ('deterministic') as the confidence; fail fast instead of reporting it."""
    import pytest  # noqa: PLC0415 -- local to the one test.

    from ontolint.models import CONFIDENCES  # noqa: PLC0415

    assert {"certain", "heuristic"} == CONFIDENCES
    context = Linter(Graph()).rule_context
    for confidence in ("certain", "heuristic"):
        context.add("ONT001", "x", f"message {confidence}", confidence=confidence)
    with pytest.raises(
        ValueError, match=r"ONT001: confidence must be one of \['certain', 'heuristic'\], not 'deterministic'"
    ):
        context.add("ONT001", "x", "other", confidence="deterministic")
    assert [f.confidence for f in context.findings] == ["certain", "heuristic"]
