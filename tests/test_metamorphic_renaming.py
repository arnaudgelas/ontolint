"""Metamorphic relation: renaming the owned namespace renames every finding's focus and changes nothing else.

The owned namespace ``https://example.test/onto#`` (the strategies' ``BASE``) is replaced, in every IRI of the graph
and in ``--base``, by another namespace of the same shape (an https IRI ending in ``#``).  Rule ids, severities and
counts must stay and every focus (and every IRI in a message) must be the renamed original: the linter knows no
namespace by name, only the one it is given.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

import pytest
from hypothesis import assume, example, given
from hypothesis import strategies as st
from hypothesis_strategies import BASE, FOREIGN, budget, roundtrip_triple_lists, triple_lists
from hypothesis_strategies import build_graph as build
from metamorphic_support import Key, Triple, cli_json, document_keys, keys, lint_all, serialisable, workdir
from rdflib import BNode, URIRef
from rdflib.namespace import OWL, RDF, RDFS

from ontolint.policy import Policy

pytestmark = pytest.mark.slow

OLD_ROOT = BASE.removesuffix("#")  # The ontology IRI, ``https://example.test/onto``, is a prefix of every owned IRI.
# Namespaces of the same shape (https, host, path, ``#``), same length (``ontx``), longer and shorter.  They are also
# chosen to keep the order of IRIs: some findings name the smallest of several terms by IRI text (OWL034 names the
# first class that uses a restriction), so a renaming that moved an owned IRI across a foreign one (``https://other``)
# or the generators' ``https://example.test/with space`` would legitimately change which term is named.
NAMESPACES = (
    "https://example.test/ontx#",
    "https://example.test/ontologies/core#",
    "https://example.test/o#",
)
# Not excluded, because a survey of 1,500 graphs found no rule that reads the namespace text for such a renaming, but
# a namespace of another *shape* does change rules that read IRI text, for example IRI013 (version or date segments)
# and FAIR007 (a version token in the version IRI); ``test_a_namespace_with_a_version_segment_...`` pins that boundary.


def rename_text(text: str, namespace: str) -> str:
    """``text`` with the owned namespace (and the ontology IRI, its prefix) replaced by ``namespace``."""
    return text.replace(OLD_ROOT, namespace.removesuffix("#"))


def rename_findings(findings: list[Key], namespace: str) -> list[Key]:
    """The comparison keys of the original findings as they should read after the renaming."""
    return sorted((r, s, rename_text(f, namespace), rename_text(m, namespace)) for r, s, f, m in findings)


def rename_triples(triples: Sequence[Triple], namespace: str) -> list[Triple]:
    """``triples`` with the owned namespace replaced in every IRI (literals are left alone)."""
    return [tuple(URIRef(rename_text(str(n), namespace)) if isinstance(n, URIRef) else n for n in t) for t in triples]  # type: ignore[misc]


# One restriction used by an owned and a foreign class: OWL034 names the smaller IRI, so the renaming must keep the
# owned class the smaller one (``https://example.test/...`` before ``https://other.example/...``).
SHARED_RESTRICTION: list[Triple] = [
    (URIRef(BASE + "A"), RDFS.subClassOf, BNode("QBNA0")),
    (URIRef(FOREIGN + "X"), RDFS.subClassOf, BNode("QBNA0")),
    (BNode("QBNA0"), RDF.type, OWL.Restriction),
]


@budget(1)
@example(SHARED_RESTRICTION, NAMESPACES[0], True)
@given(triple_lists(20), st.sampled_from(NAMESPACES), st.booleans())
def test_renaming_the_owned_namespace_renames_the_foci_and_changes_nothing_else(
    triples: list, namespace: str, with_base: bool
) -> None:
    """RELATION (IRI renaming): after replacing the owned namespace in the graph (and in ``base``, when one is
    given), the findings are the original ones with every focus and message IRI renamed; the counts per rule and
    severity are the same.  Without a base the owned namespace is inferred, which must not read its text either."""
    before = lint_all(build(triples), Policy(base=BASE if with_base else None))
    after = lint_all(build(rename_triples(triples, namespace)), Policy(base=namespace if with_base else None))

    assert Counter((f.rule, f.severity) for f in after) == Counter((f.rule, f.severity) for f in before)
    assert keys(after) == rename_findings(keys(before), namespace)


@budget(0.3)
@given(roundtrip_triple_lists(), st.sampled_from(NAMESPACES))
def test_the_cli_base_option_follows_the_renamed_namespace(triples: list, namespace: str) -> None:
    """RELATION (IRI renaming, CLI): ``--base`` with the old namespace on the original file and with the new one on
    the renamed file give the same exit code and the original findings with every IRI renamed."""
    graph = build(serialisable(triples))
    assume(len(graph))

    with workdir() as root:
        (root / "old.ttl").write_text(graph.serialize(format="turtle"), encoding="utf-8")
        (root / "new.ttl").write_text(
            build(rename_triples(sorted(graph), namespace)).serialize(format="turtle"), encoding="utf-8"
        )
        code, before = cli_json("old.ttl", "--base", BASE)
        new_code, after = cli_json("new.ttl", "--base", namespace)

    assert new_code == code
    assert document_keys(after) == rename_findings(document_keys(before), namespace)


def test_a_namespace_with_a_version_segment_is_a_different_shape() -> None:
    """BOUNDARY of the relation: IRI013 reads the IRI text, so a namespace that embeds a version segment is not a
    renaming but a different input, and is why the renaming above keeps to namespaces without one."""
    triples = [(URIRef(BASE + "A"), RDF.type, OWL.Class), (URIRef(BASE + "B"), RDF.type, OWL.Class)]

    plain = {f.rule for f in lint_all(build(rename_triples(triples, NAMESPACES[0])), Policy())}
    versioned = {f.rule for f in lint_all(build(rename_triples(triples, "https://example.test/v2#")), Policy())}

    assert "IRI013" not in plain
    assert "IRI013" in versioned
