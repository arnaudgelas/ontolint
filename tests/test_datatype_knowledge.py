"""OWL011, OWL022 and OWL040 recognise the same datatypes (issue #12).

The datatype IRIs outside ``xsd:`` are listed once, in :data:`ontolint.rules.support.LITERAL_RANGES`, and
read through :func:`ontolint.rules.support.is_datatype_iri`.  Each rule then adds only what its own
specification says: OWL011 also accepts an untyped ``owl:onDatatype`` / ``owl:datatypeComplementOf`` node
(a heuristic that only suppresses), OWL022 drops a datatype that is also typed ``owl:Class`` (OWL030's).
OWL040 has no such exclusion, so on a term typed both ``owl:Class`` and ``rdfs:Datatype`` the two error rules
still disagree; the last test pins that difference.
"""

from __future__ import annotations

import pytest
from rdflib import OWL, RDF, RDFS, URIRef
from rule_harness import graph

from ontolint import Linter
from ontolint.rules.support import LITERAL_RANGES, is_datatype_iri

XSD = "http://www.w3.org/2001/XMLSchema#"
# RDF 1.2's directional language-tagged string, not yet in rdflib's RDF namespace nor in the list.
DIR_LANG_STRING = URIRef(str(RDF) + "dirLangString")

# The OWL 2 datatype map's non-XSD datatypes (Structural Specification section 4), rdfs:Literal (section
# 5.2, outside the map), RDF 1.1's two further datatypes, and JSON-LD 1.1's rdf:JSON.
EXPECTED = {
    RDFS.Literal,
    OWL.real,
    OWL.rational,
    RDF.PlainLiteral,
    RDF.XMLLiteral,
    RDF.langString,
    RDF.HTML,
    RDF.JSON,
}
DATATYPES = sorted(EXPECTED, key=str) + [URIRef(XSD + "integer"), URIRef(XSD + "dateTimeStamp")]


def _findings(rule: str, turtle: str) -> list[str]:
    return [f.rule for f in Linter(graph(turtle)).execute([rule]).findings]


def test_the_list_is_the_datatype_map_and_rdf_extensions() -> None:
    assert LITERAL_RANGES == EXPECTED


@pytest.mark.parametrize("datatype", DATATYPES, ids=str)
def test_every_rule_reads_the_datatype_as_one(datatype: URIRef) -> None:
    assert is_datatype_iri(datatype)
    restriction = f"[] a owl:Restriction ; owl:onProperty ex:p ; owl:{{}} <{datatype}> ."
    assert _findings("OWL011", restriction.format("allValuesFrom")) == []
    assert _findings("OWL040", "ex:p a owl:ObjectProperty . " + restriction.format("someValuesFrom")) == ["OWL040"]
    assert _findings("OWL022", f"ex:p a owl:ObjectProperty ; rdfs:range <{datatype}> .") == ["OWL022"]


@pytest.mark.parametrize(
    "iri",
    [
        RDFS.Resource,
        RDF.Property,
        RDF.List,
        DIR_LANG_STRING,
        OWL.Thing,
        URIRef("https://example.test/onto#D"),
    ],
    ids=str,
)
def test_other_iris_are_not_datatypes_by_name(iri: URIRef) -> None:
    assert not is_datatype_iri(iri)


def test_a_blank_node_is_never_a_datatype_by_name() -> None:
    assert not is_datatype_iri(graph("[] a rdfs:Datatype .").value(predicate=RDF.type, object=RDFS.Datatype))


@pytest.mark.parametrize("iri", [RDF.List, DIR_LANG_STRING], ids=str)
def test_owl011_reports_an_rdf_iri_outside_the_list(iri: URIRef) -> None:
    restriction = f"[] a owl:Restriction ; owl:onProperty ex:p ; owl:allValuesFrom <{iri}> ."
    assert _findings("OWL011", restriction) == ["OWL011"]


def test_a_term_typed_class_and_datatype_is_dropped_by_owl022_only() -> None:
    punned = "ex:D a owl:Class, rdfs:Datatype . ex:p a owl:ObjectProperty ; rdfs:range ex:D . "
    restriction = "[] a owl:Restriction ; owl:onProperty ex:p ; owl:{} ex:D ."
    assert _findings("OWL022", punned) == []
    assert _findings("OWL040", punned + restriction.format("someValuesFrom")) == ["OWL040"]
    assert _findings("OWL011", punned + restriction.format("allValuesFrom")) == []
