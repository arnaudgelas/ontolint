"""Findings on blank nodes of the shapes graph name each node by its content in the shapes graph.

Property shapes are usually written inline (``sh:property [ ... ]``), so most SHQ findings are about a blank
node.  Such a node has no triple in the data graph: naming it there gave every one of them the identity of an
empty node, and the de-duplicating emitter then merged them into one finding.
"""

from __future__ import annotations

import json
from pathlib import Path
from random import Random

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis_strategies import budget
from rdflib import BNode, Graph
from rule_harness import PREFIXES, graph

from ontolint import Linter
from ontolint.cli import main
from ontolint.engine import SHAPES_MODULES
from ontolint.loader import load_graph
from ontolint.models import Finding
from ontolint.paths import resolve_inputs
from ontolint.policy import Policy
from ontolint.rules.support import stable_blank_id

# The identity of a blank node with no triple at all: what every shapes-graph blank node got in the data graph.
EMPTY = stable_blank_id(Graph(), BNode())
DATA = graph("<https://example.test/onto> a owl:Ontology .")
FIVE = 5
PAIR = 2  # two shapes, or two values, that must not be merged
TWO = """
    ex:A a sh:NodeShape ; sh:targetClass ex:K ;
        sh:property [ sh:path ex:p ; sh:minCount 1 ] , [ sh:path ex:q ; sh:minCount 1 ] .
"""


def _run(shapes: Graph, rules: list[str], data: Graph = DATA) -> list[Finding]:
    return list(Linter(data, shapes).execute(rules).findings)


def _foci(rule: str, shapes: Graph, data: Graph = DATA) -> list[str]:
    return sorted(f.focus for f in _run(shapes, [rule], data) if f.rule == rule)


def _json_ld(document: object, path: Path) -> Graph:
    """``document`` written to ``path`` and read back by the loader, as a linted or ``--shapes`` file is."""
    path.write_text(json.dumps(document), encoding="utf-8")
    return load_graph(resolve_inputs([path.name], path.parent)[0], Policy(), path.parent)


def test_the_shape_rule_modules_name_blank_nodes_in_the_shapes_graph() -> None:
    assert {"shapes", "shacl_quality", "shacl_authoring"} == SHAPES_MODULES


def test_two_blank_property_shapes_give_two_findings() -> None:
    foci = _foci("SHQ001", graph(TWO))
    assert len(foci) == PAIR
    assert len(set(foci)) == PAIR
    assert EMPTY not in foci
    assert all(focus.startswith("_:") for focus in foci)


@pytest.mark.parametrize("rule", ["SHQ001", "SHQ002", "SHQ003"])
def test_every_blank_property_shape_is_reported(rule: str) -> None:
    shapes = graph(
        "".join(f"ex:S{i} a sh:NodeShape ; sh:property [ sh:path ex:p{i} ; sh:minCount 1 ] .\n" for i in range(FIVE))
    )
    assert len(set(_foci(rule, shapes))) == FIVE


def test_the_identity_does_not_depend_on_parser_labels_or_syntax() -> None:
    first = graph(TWO)
    reparsed = graph(TWO)
    as_ntriples = Graph().parse(data=first.serialize(format="nt"), format="nt")
    reordered = graph(
        "ex:A sh:property [ sh:minCount 1 ; sh:path ex:q ] . ex:A sh:property [ sh:minCount 1 ; sh:path ex:p ] ."
        "ex:A sh:targetClass ex:K ; a sh:NodeShape ."
    )
    expected = _foci("SHQ001", first)
    assert _foci("SHQ001", reparsed) == expected
    assert _foci("SHQ001", as_ntriples) == expected
    assert _foci("SHQ001", reordered) == expected


def test_a_json_ld_label_shared_with_the_data_graph_is_named_in_the_shapes_graph(tmp_path: Path) -> None:
    # JSON-LD keeps document labels, so both graphs hold the blank node ``b0``; the finding is about the shape.
    shapes_doc = {
        "@id": "https://example.test/onto#A",
        "http://www.w3.org/ns/shacl#property": {"@id": "_:b0"},
        "@included": [{"@id": "_:b0", "http://www.w3.org/ns/shacl#path": {"@id": "https://example.test/onto#p"}}],
    }
    data_doc = {"@id": "_:b0", "https://example.test/onto#other": "value"}
    shapes, data = _json_ld(shapes_doc, tmp_path / "shapes.jsonld"), _json_ld(data_doc, tmp_path / "data.jsonld")
    assert BNode("b0") in set(data.subjects()) & set(shapes.objects())
    as_turtle = graph("ex:A sh:property [ sh:path ex:p ] .")
    assert _foci("SHQ001", shapes, data) == _foci("SHQ001", as_turtle)


def test_the_focus_matches_the_source_shape_of_a_shacl_result() -> None:
    data = graph("<https://example.test/onto> a owl:Ontology . ex:i a ex:K .")
    findings = _run(graph(TWO), ["SHQ001", "SHACL001"], data)
    shq = {f.focus for f in findings if f.rule == "SHQ001"}
    sources = {f.subject[0] for f in findings if f.rule == "SHACL001"}
    assert len(shq) == PAIR
    assert sources == shq


def test_a_blank_value_in_a_message_is_named_by_its_content_not_its_label() -> None:
    turtle = "ex:A a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:maxCount [ ex:v 1 ] , [ ex:v 2 ] ] ."
    first = [f for f in _run(graph(turtle), ["SHQ008"]) if f.rule == "SHQ008"]
    again = [f for f in _run(graph(turtle), ["SHQ008"]) if f.rule == "SHQ008"]
    assert [(f.focus, f.message, f.subject) for f in first] == [(f.focus, f.message, f.subject) for f in again]
    assert len({f.message for f in first}) == PAIR
    assert len({f.subject for f in first}) == PAIR
    for finding in first:
        value = finding.subject[1]
        assert value.startswith("_:")
        assert value != EMPTY
        assert finding.message == f"sh:maxCount value {value} is not a non-negative integer."


def test_shapes_with_the_same_content_and_owner_share_one_identity() -> None:
    # No label-free identity can tell them apart: they are interchangeable in the graph (a known limit).
    shapes = graph("ex:A sh:property [ sh:path ex:p ] , [ sh:path ex:p ] . ex:B sh:property [ sh:path ex:p ] .")
    assert len(set(_foci("SHQ001", shapes))) == PAIR


def test_data_graph_blank_nodes_are_still_named_in_the_data_graph() -> None:
    data = graph(
        "<https://example.test/onto> a owl:Ontology .\n"
        "ex:C a owl:Class ; rdfs:subClassOf [ a owl:Restriction ; owl:someValuesFrom ex:D ] .\n"
        "[ ] a owl:AllDisjointClasses ; owl:members ( ex:A ) ."
    )
    with_shapes = {(f.rule, f.focus, f.message) for f in _run(graph(TWO), [], data) if not f.rule.startswith("SH")}
    without = {(f.rule, f.focus, f.message) for f in Linter(data).execute([]).findings}
    assert with_shapes == without
    blank = {rule for rule, focus, _message in without if focus.startswith("_:")}
    assert {"OWL034", "OWL045"} <= blank


@st.composite
def _property_shapes(draw: st.DrawFn) -> list[tuple[str, int]]:
    """Distinct ``(path, minCount)`` pairs: property shapes no two of which have the same content."""
    return draw(
        st.lists(
            st.tuples(st.sampled_from(["p", "q", "r", "s"]), st.integers(min_value=0, max_value=3)),
            min_size=1,
            max_size=8,
            unique=True,
        )
    )


@budget(0.5)
@given(shapes=_property_shapes(), order=st.randoms(use_true_random=False))
def test_distinct_property_shapes_give_distinct_findings(shapes: list[tuple[str, int]], order: Random) -> None:
    def turtle(items: list[tuple[str, int]]) -> str:
        return "ex:A a sh:NodeShape ; sh:property " + " , ".join(
            f"[ sh:path ex:{path} ; sh:minCount {count} ]" for path, count in items
        )

    foci = _foci("SHQ001", Graph().parse(data=PREFIXES + turtle(shapes) + " .", format="turtle"))
    assert len(set(foci)) == len(shapes)
    shuffled = list(shapes)
    order.shuffle(shuffled)
    assert _foci("SHQ001", Graph().parse(data=PREFIXES + turtle(shuffled) + " .", format="turtle")) == foci


def _cli_foci(capsys: pytest.CaptureFixture[str], *argv: str) -> list[str]:
    main([*argv, "--select", "SHQ001", "--format", "json", "--fail-on", "never"])
    findings = json.loads(capsys.readouterr().out)["findings"]
    return sorted(f["focus"] for f in findings if f["rule"] == "SHQ001")


def test_an_imported_shape_library_names_its_shapes_as_when_given_directly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "lib.ttl").write_text(
        PREFIXES + "<https://ex.test/lib> a owl:Ontology .\n" + TWO.replace("ex:A", "<https://ex.test/A>"),
        encoding="utf-8",
    )
    (tmp_path / "uses-lib.ttl").write_text(
        PREFIXES + "<https://ex.test/shapes> a owl:Ontology ; owl:imports <https://ex.test/lib> .\n", encoding="utf-8"
    )
    (tmp_path / "catalog-v001.xml").write_text(
        '<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">'
        '<uri name="https://ex.test/lib" uri="lib.ttl"/></catalog>',
        encoding="utf-8",
    )
    (tmp_path / "data.ttl").write_text(
        "<https://ex.test/d> a <http://www.w3.org/2002/07/owl#Ontology> .\n", encoding="utf-8"
    )
    data = str(tmp_path / "data.ttl")
    direct = _cli_foci(capsys, data, "--shapes", str(tmp_path / "lib.ttl"))
    imported = _cli_foci(capsys, data, "--shapes", str(tmp_path / "uses-lib.ttl"), "--follow-imports")
    assert len(set(direct)) == PAIR
    assert imported == direct
