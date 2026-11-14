"""Data-graph findings do not depend on the labels a parser gave the graph's blank nodes.

JSON-LD keeps a document's own labels (``_:a``, ``_:2``, ``_:b0``), and an API caller may build a graph with any.
A data rule writes a node that may be blank as ``_:label`` (:func:`~ontolint.rules.support.value_text`,
:func:`~ontolint.rules.support.quoted_text`), which ``RuleContext`` rewrites to the node's stable identity, so a
label without a digit is never left in a message.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis_strategies import budget
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS, SKOS, XSD
from rdflib.term import Node
from rule_harness import BASE, graph

from ontolint import Linter
from ontolint.loader import load_graph
from ontolint.paths import resolve_inputs
from ontolint.policy import Policy
from ontolint.rules.runtime import _BlankNames  # noqa: PLC2701 -- the rewriting is compared alone with its reference.
from ontolint.rules.support import stable_blank_id

BLANK = r"_:[0-9a-f]{12}"
OBO = "http://purl.obolibrary.org/obo/"

# One blank value for every data-graph message that names a value that may be a blank node, and messages that
# hold a count (ONT002, LEX003), a literal (OWL013) or a digit of their own wording (DATA004's "OWL 2").  Each
# pair OWL024-OWL026 compare is asserted one way, and OWL029's pair is two blank nodes, so which of a pair is the
# focus depends only on the order of the labels, which every relabelling below keeps.
FAULTS = f"""
    <https://example.test/onto> a owl:Ontology ; owl:imports [ ex:v 1 ] .
    <https://example.test/other> a owl:Ontology .
    <{OBO}xx.owl> a owl:Ontology ; owl:versionIRI [ ex:v 2 ] .
    ex:sym a owl:SymmetricProperty ; owl:inverseOf [ ex:v 3 ] .
    ex:d a owl:DatatypeProperty . ex:i ex:d [ ex:v 4 ] .
    ex:o a owl:ObjectProperty ; rdfs:domain _:domain . _:domain ex:v 5 .
    ex:i ex:o ex:j ; a _:kind . _:kind owl:disjointWith _:domain .
    ex:op a owl:ObjectProperty ; rdfs:subPropertyOf [ a owl:DatatypeProperty ] .
    ex:dp owl:propertyDisjointWith _:property ; rdfs:subPropertyOf _:property . _:property ex:v 7 .
    ex:A a owl:Class ; owl:disjointWith _:class ; rdfs:subClassOf _:class . _:class owl:complementOf ex:Z .
    ex:k owl:differentFrom _:individual ; owl:sameAs _:individual . _:individual ex:v 8 .
    [ a owl:NegativePropertyAssertion ; owl:sourceIndividual ex:m ; owl:assertionProperty ex:np ;
      owl:targetIndividual _:target ] .
    ex:m ex:np _:target . _:target ex:v 9 .
    ex:ap a owl:AsymmetricProperty . _:first ex:ap _:second ; ex:v 10 . _:second ex:ap _:first .
    _:deprecated owl:deprecated true ; ex:v 11 . ex:B a owl:Class ; ex:rel _:deprecated ; ex:list ( _:deprecated ) .
    ex:c a skos:Concept ; skos:topConceptOf [ ex:v 12 ] ; skos:broader ex:e ;
        skos:prefLabel _:label ; skos:altLabel _:label . _:label ex:v 13 .
    ex:n a owl:ObjectProperty . ex:n2 ex:n 2 .
    ex:R a owl:Restriction ; owl:onDatatype xsd:gYear .
    ex:L a owl:Class ; rdfs:label "x"@en , "y"@en .
"""
EX = re.escape(BASE)
FAULT_MESSAGES = {
    "DATA002": [rf"Usage of {EX}o infers {BLANK} but subject is explicitly typed {BLANK}, declared disjoint\."],
    "DATA004": [
        r"xsd:gYear \(used as owl:onDatatype\) is not in the OWL 2 datatype map, so OWL 2 DL tools reject it; "
        r"xsd:dateTime is\."
    ],
    "GOV001": [
        rf"Deprecated term {BLANK} appears as object of {EX}rel\.",
        rf"Deprecated term {BLANK} appears in a list of {EX}list\.",
    ],
    "GOV002": [rf"Non-IRI import target: {BLANK}\."],
    "LEX003": [r"2 labels for language en\."],
    "OBO011": [
        r"Ontology IRI https://example\.test/(onto|other) does not follow the OBO PURL pattern "
        r"http://purl\.obolibrary\.org/obo/<id>\.owl\.",
        rf"Version IRI {BLANK} does not follow http://purl\.obolibrary\.org/obo/<id>/releases/YYYY-MM-DD/<id>\.owl\.",
    ],
    "ONT002": [r"3 owl:Ontology declarations found\."],
    "OWL008": [rf"Symmetric property also declared inverse of {BLANK}\."],
    "OWL013": [rf'Object property {EX}n points to literal "2"\^\^<http://www\.w3\.org/2001/XMLSchema#integer>\.'],
    "OWL014": [rf"Datatype property {EX}d points to resource {BLANK}\."],
    "OWL021": [
        rf"Object property is related by http://www\.w3\.org/2000/01/rdf-schema#subPropertyOf to datatype property "
        rf"{BLANK}\."
    ],
    "OWL024": [rf"The property is disjoint with {BLANK} but also asserted a subproperty of or equivalent to it\."],
    "OWL025": [rf"The class is disjoint with {BLANK} but also asserted a subclass of or equivalent to it\."],
    "OWL026": [rf"Individual is both owl:sameAs and owl:differentFrom {BLANK}\."],
    "OWL027": [rf"Negative assertion on {EX}np with {BLANK} contradicts an asserted triple\."],
    "OWL029": [rf"Asymmetric property {EX}ap is asserted in both directions with {BLANK}\."],
    "SKOS002": [rf"Literal '{BLANK}' \(no language\) appears in skos:prefLabel and skos:altLabel\."],
    "SKOS006": [rf"Top concept of {BLANK} also has an asserted broader concept\."],
    "SKOS013": [rf"skos:(pref|alt)Label value '{BLANK}' is not a string literal\."],
}
FAULT_RULES = sorted(FAULT_MESSAGES)

type Exact = tuple[str, str, str, str, tuple[str, ...], tuple[str, ...]]


def _exact(data: Graph, rules: list[str]) -> list[Exact]:
    """Findings compared whole: a parser label left in a message, or a count rewritten, must show."""
    findings = Linter(data).execute(rules).findings
    return sorted((f.rule, f.severity, f.focus, f.message, f.subject, f.related) for f in findings)


def _blanks(data: Graph) -> list[BNode]:
    return sorted({n for t in data for n in (t[0], t[2]) if isinstance(n, BNode)}, key=str)


def _relabelled(data: Graph, scheme: Callable[[int], str]) -> Graph:
    """``data`` with each blank node renamed by ``scheme``, the old and the new labels in the same order.

    Every label of the schemes sorts before ``h``, so before every IRI of :data:`FAULTS`, as the parser's do not:
    a rule that orders nodes by their text sees the same order in every renamed copy.
    """
    old = _blanks(data)
    rename: dict[Node, Node] = dict(zip(old, sorted(map(BNode, map(scheme, range(len(old))))), strict=True))
    out = Graph()
    for s, p, o in data:
        out.add((rename.get(s, s), p, rename.get(o, o)))
    return out


SCHEMES: dict[str, Callable[[int], str]] = {
    "letters": lambda i: "abcdefg"[i % 7] * (1 + i // 7),
    "digits": str,
    "json-ld": lambda i: f"b{i}",
}


def _reference(i: int) -> str:
    return f"A{i}"


def test_every_blank_value_count_and_literal_in_a_data_message_is_spelled_as_expected() -> None:
    by_rule: dict[str, list[str]] = {}
    for rule, _severity, _focus, message, _subject, _related in _exact(graph(FAULTS), FAULT_RULES):
        by_rule.setdefault(rule, []).append(message)
    assert sorted(by_rule) == FAULT_RULES
    for rule, patterns in FAULT_MESSAGES.items():
        for message in by_rule[rule]:
            assert any(re.fullmatch(pattern, message) for pattern in patterns), (rule, message)
        for pattern in patterns:
            assert any(re.fullmatch(pattern, message) for message in by_rule[rule]), (rule, pattern)


@pytest.mark.parametrize("scheme", sorted(SCHEMES))
def test_data_findings_do_not_depend_on_the_labels_of_blank_nodes(scheme: str) -> None:
    # Letters (``a``) were left raw in OWL008, OWL014, OWL021, OWL024-OWL027, OWL029, GOV001, GOV002, SKOS002,
    # SKOS006, SKOS013, OBO011 and DATA002; digits (``2``) rewrote the counts of ONT002 and LEX003, the literal of
    # OWL013 and the "OWL 2" of DATA004.
    data = graph(FAULTS)
    expected = _exact(_relabelled(data, _reference), FAULT_RULES)
    assert _exact(_relabelled(data, SCHEMES[scheme]), FAULT_RULES) == expected


def _json_ld(document: object, path: Path) -> Graph:
    """``document`` written to ``path`` and read back by the loader, as a linted file is."""
    path.write_text(json.dumps(document), encoding="utf-8")
    return load_graph(resolve_inputs([path.name], path.parent)[0], Policy(), path.parent)


def _alt_label(label: str) -> dict[str, object]:
    """A JSON-LD concept whose skos:altLabel is the blank node ``label``, which has one property."""
    return {
        "@id": BASE + "C",
        str(SKOS.altLabel): {"@id": label},
        "@included": [{"@id": label, BASE + "p": "v"}],
    }


def _messages(data: Graph, rules: list[str]) -> list[str]:
    return [message for _rule, _severity, _focus, message, _subject, _related in _exact(data, rules)]


@pytest.mark.parametrize("label", ["_:x", "_:2", "_:b0"])
def test_a_label_elsewhere_in_a_json_ld_file_does_not_rewrite_a_count(label: str, tmp_path: Path) -> None:
    document = [
        {"@id": "https://example.test/a", "@type": str(OWL.Ontology)},
        {"@id": "https://example.test/b", "@type": str(OWL.Ontology)},
        {"@id": label, BASE + "p": "v"},
    ]
    data = _json_ld(document, tmp_path / "data.jsonld")
    assert BNode(label.removeprefix("_:")) in set(data.subjects())
    assert _messages(data, ["ONT002"]) == ["2 owl:Ontology declarations found."]


def test_a_digit_label_rewrites_neither_a_literal_nor_an_iri_nor_the_wording() -> None:
    # Bare rewriting replaced the ``2`` of ``"2"^^xsd:integer``, of ``ex:q=2`` and of "OWL 2" by a node identity.
    data = graph(
        "ex:n a owl:ObjectProperty . ex:i ex:n 2 . <https://example.test/onto#q=2> a owl:ObjectProperty .\n"
        "ex:i <https://example.test/onto#q=2> 'v' . ex:R a owl:Restriction ; owl:onDatatype xsd:gYear .\n"
    )
    data.add((BNode("2"), URIRef(BASE + "v"), Literal("v")))
    assert _messages(data, ["DATA004", "OWL013"]) == [
        "xsd:gYear (used as owl:onDatatype) is not in the OWL 2 datatype map, so OWL 2 DL tools reject it; "
        "xsd:dateTime is.",
        f'Object property {BASE}n points to literal "2"^^<http://www.w3.org/2001/XMLSchema#integer>.',
        f'Object property {BASE}q=2 points to literal "v".',
    ]


def test_a_label_copied_from_a_literal_or_an_iri_is_the_known_residual() -> None:
    # Documented limit (``_BlankNames.rewrite``): ``_:x`` written in a literal or an IRI is read as the blank node
    # ``x`` when the graph has one, unless a word character, ``/``, ``#``, ``:`` or ``-`` touches it.
    data = graph(
        "ex:n a owl:ObjectProperty . ex:i ex:n '_:x' . ex:L a owl:Class ; rdfs:label ' see _:x here' .\n"
        "<https://example.test/onto?q=_:x> a owl:ObjectProperty . ex:i <https://example.test/onto?q=_:x> 'v' .\n"
        "<https://example.test/onto#_:x> a owl:ObjectProperty . ex:i <https://example.test/onto#_:x> 'v' .\n"
    )
    x = BNode("x")
    data.add((x, URIRef(BASE + "v"), Literal("v")))
    identity = stable_blank_id(data, x)
    assert _messages(data, ["LEX005", "OWL013"]) == [
        f"Blank or padded label: ' see {identity} here'.",
        f'Object property {BASE}_:x points to literal "v".',
        f'Object property {BASE}n points to literal "{identity}".',
        f'Object property https://example.test/onto?q={identity} points to literal "v".',
    ]


@pytest.mark.parametrize("label", ["_:a", "_:2", "_:b1"])
def test_a_json_ld_blank_value_reports_as_its_turtle_twin(label: str, tmp_path: Path) -> None:
    as_json_ld = _json_ld(_alt_label(label), tmp_path / "data.jsonld")
    assert BNode(label.removeprefix("_:")) in set(as_json_ld.objects())
    as_turtle = graph("ex:C skos:altLabel [ ex:p 'v' ] .")
    assert _exact(as_json_ld, ["SKOS013"]) == _exact(as_turtle, ["SKOS013"])
    ((_rule, _severity, _focus, message, _subject, _related),) = _exact(as_json_ld, ["SKOS013"])
    assert re.fullmatch(rf"skos:altLabel value '{BLANK}' is not a string literal\.", message), message


LONG = "x" * 70


@pytest.mark.parametrize("label", [f"_:{LONG}", "_:it's", "_:back\\slash"], ids=["70 characters", "quote", "backslash"])
def test_a_quoted_blank_value_is_its_whole_identity_whatever_its_label(label: str, tmp_path: Path) -> None:
    # ``clip(str(value), 60)!r`` cut a long label, escaped a backslash and quoted ``'`` with ``"``, so the label
    # was no longer found and stayed in the message.
    document = _alt_label(label)
    document[str(SKOS.prefLabel)] = {"@id": label}
    data = _json_ld(document, tmp_path / "data.jsonld")
    identity = stable_blank_id(data, BNode(label.removeprefix("_:")))
    assert _messages(data, ["SKOS002", "SKOS013"]) == [
        f"Literal '{identity}' (no language) appears in skos:prefLabel and skos:altLabel.",
        f"skos:altLabel value '{identity}' is not a string literal.",
        f"skos:prefLabel value '{identity}' is not a string literal.",
    ]


def test_a_quoted_literal_is_still_cut_and_quoted_by_python() -> None:
    data = graph(f"ex:C skos:altLabel '{'y' * 80}'^^xsd:integer , \"it's\"^^xsd:integer .")
    assert _messages(data, ["SKOS013"]) == [
        'skos:altLabel value "it\'s" is not a string literal.',
        f"skos:altLabel value '{'y' * 60}' is not a string literal.",
    ]


# --- a blank property, which only a graph built through the API holds -----------------------------------------

SOURCE, TARGET = URIRef(BASE + "s"), URIRef(BASE + "o")


def _typed(p: BNode, *types: URIRef) -> Graph:
    data = Graph()
    for type_ in types:
        data.add((p, RDF.type, type_))
    return data


def _owl013(p: BNode) -> Graph:
    data = _typed(p, OWL.ObjectProperty)
    data.add((SOURCE, p, Literal("v")))
    return data


def _owl014(p: BNode) -> Graph:
    data = _typed(p, OWL.DatatypeProperty)
    data.add((SOURCE, p, TARGET))
    return data


def _data001(p: BNode) -> Graph:
    data = _typed(p, OWL.DatatypeProperty)
    data.add((p, RDFS.range, XSD.integer))
    data.add((SOURCE, p, Literal(True)))
    return data


def _owl027(p: BNode) -> Graph:
    data = _typed(p, OWL.ObjectProperty)
    assertion = BNode()
    data.add((assertion, RDF.type, OWL.NegativePropertyAssertion))
    data.add((assertion, OWL.sourceIndividual, SOURCE))
    data.add((assertion, OWL.assertionProperty, p))
    data.add((assertion, OWL.targetIndividual, TARGET))
    data.add((SOURCE, p, TARGET))
    return data


def _owl028(p: BNode) -> Graph:
    data = _typed(p, OWL.IrreflexiveProperty)
    data.add((SOURCE, p, SOURCE))
    return data


def _owl029_self(p: BNode) -> Graph:
    data = _typed(p, OWL.AsymmetricProperty)
    data.add((SOURCE, p, SOURCE))
    return data


def _owl029_both(p: BNode) -> Graph:
    data = _typed(p, OWL.AsymmetricProperty)
    data.add((SOURCE, p, TARGET))
    data.add((TARGET, p, SOURCE))
    return data


def _data003(p: BNode) -> Graph:
    data = _typed(p, RDF.Property)
    data.add((SOURCE, p, Literal("abc", datatype=XSD.integer)))
    return data


def _sec005(p: BNode) -> Graph:
    data = _typed(p, RDF.Property)
    data.add((SOURCE, p, Literal("x" * 100_001)))
    return data


def _sec012(p: BNode) -> Graph:
    data = _typed(p, RDF.Property)
    data.add((SOURCE, p, Literal("a" + chr(0x202E) + "b")))
    return data


def _gov001_object(p: BNode) -> Graph:
    data = _typed(p, RDF.Property)
    data.add((TARGET, OWL.deprecated, Literal(True)))
    data.add((SOURCE, p, TARGET))
    return data


def _gov001_assertion(p: BNode) -> Graph:
    data = _typed(p, RDF.Property)
    data.add((p, OWL.deprecated, Literal(True)))
    data.add((SOURCE, p, TARGET))
    return data


def _gov013(p: BNode) -> Graph:
    data = _typed(p, RDF.Property)
    data.add((TARGET, RDF.type, OWL.DeprecatedClass))
    data.add((SOURCE, p, TARGET))
    return data


def _owl043(p: BNode) -> Graph:
    data = _typed(p, RDF.Property)
    union, head = BNode(), BNode()
    Collection(data, head, [URIRef(BASE + "A"), OWL.Thing])
    data.add((union, OWL.unionOf, head))
    data.add((URIRef(BASE + "C"), p, union))
    return data


# Each graph, the rule it fires and its message, ``{p}`` standing for the blank property's identity.
API_CASES: dict[str, tuple[Callable[[BNode], Graph], str, str]] = {
    "OWL013": (_owl013, "OWL013", 'Object property {p} points to literal "v".'),
    "OWL014": (_owl014, "OWL014", f"Datatype property {{p}} points to resource {TARGET}."),
    "DATA001": (
        _data001,
        "DATA001",
        f"{{p}} has range {XSD.integer} but value has datatype {XSD.boolean}.",
    ),
    "OWL027": (_owl027, "OWL027", f"Negative assertion on {{p}} with {TARGET} contradicts an asserted triple."),
    "OWL028": (_owl028, "OWL028", "Irreflexive property {p} relates the individual to itself."),
    "OWL029 self": (_owl029_self, "OWL029", "Asymmetric property {p} relates the individual to itself."),
    "OWL029 both": (_owl029_both, "OWL029", f"Asymmetric property {{p}} is asserted in both directions with {SOURCE}."),
    "DATA003": (
        _data003,
        "DATA003",
        "Value 'abc' of {p} is typed xsd:integer, but it is not a valid xsd:integer.",
    ),
    "SEC005": (_sec005, "SEC005", "Literal on {p} has 100001 characters (limit 100000)."),
    "SEC012": (_sec012, "SEC012", "Literal on {p} contains control or bidirectional-override characters (U+202E)."),
    "GOV001 object": (_gov001_object, "GOV001", f"Deprecated term {TARGET} appears as object of {{p}}."),
    "GOV001 assertion": (_gov001_assertion, "GOV001", "Deprecated property {p} used in assertion."),
    "GOV013": (_gov013, "GOV013", f"Obsolete term {TARGET} appears as object of {{p}}."),
    "OWL043": (
        _owl043,
        "OWL043",
        f"owl:unionOf in the {{p}} of {BASE}C contains owl:Thing; it is equivalent to owl:Thing.",
    ),
}


@pytest.mark.parametrize("case", sorted(API_CASES))
@pytest.mark.parametrize("label", ["p1", "pa"])
def test_a_blank_property_of_an_api_graph_is_named_by_its_identity(case: str, label: str) -> None:
    # A blank property is not RDF, but rdflib accepts one; a label holding a digit was rewritten, ``pa`` stayed.
    build, rule, template = API_CASES[case]
    data = build(BNode(label))
    assert _messages(data, [rule]) == [template.format(p=stable_blank_id(data, BNode(label)))]


def test_a_blank_range_whose_label_spells_an_xsd_iri_is_named_by_its_identity() -> None:
    # DATA001 judges a range by its text, so a blank one labelled like an XSD IRI reaches the message.
    data, p, datatype = Graph(), URIRef(BASE + "p"), BNode(str(XSD.integer))
    data.add((p, RDF.type, OWL.DatatypeProperty))
    data.add((p, RDFS.range, datatype))
    data.add((SOURCE, p, Literal(True)))
    assert _messages(data, ["DATA001"]) == [
        f"{p} has range {stable_blank_id(data, datatype)} but value has datatype {XSD.boolean}."
    ]


def test_a_blank_node_used_only_as_a_predicate_keeps_its_label() -> None:
    # Documented limit (``_BlankNames.rewrite``): only subjects and objects are looked up, as RDF has no blank
    # predicate; such a node has no content to be named by either.
    data = Graph()
    data.add((SOURCE, BNode("pa"), Literal("a" + chr(0x202E) + "b")))
    assert _messages(data, ["SEC012"]) == [
        "Literal on _:pa contains control or bidirectional-override characters (U+202E)."
    ]


# --- the rewriting itself ---------------------------------------------------------------------------------------


def _pattern_rewrite(data: Graph, message: str) -> str:
    """The rewriting as one pattern over every label, as it was before labels were looked up: the reference."""
    nodes = {str(n): n for t in data for n in (t[0], t[2]) if isinstance(n, BNode)}
    if not nodes:
        return message
    alternatives = "|".join(re.escape(label) for label in sorted(nodes, key=lambda label: (-len(label), label)))
    pattern = re.compile(rf"(?<![\w/#:-])_:({alternatives})(?![\w/#:-]|\.\w)")
    return pattern.sub(lambda match: stable_blank_id(data, nodes[match.group(1)]), message)


def _labelled(labels: Iterable[str]) -> Graph:
    data = Graph()
    for i, label in enumerate(labels):
        data.add((BNode(label), URIRef(BASE + "v"), Literal(i)))
    return data


REWRITES: list[tuple[tuple[str, ...], str]] = [
    (("a", "a b"), "_:a b and _:a c"),  # the longest label that fits is taken
    (("a", "a.b"), "_:a.b, _:a.c, _:a. and _:a."),  # ``.`` and a word character continue a name
    (("a",), "_:a"),
    (("a",), "x_:a /_:a #_:a :_:a -_:a (_:a)"),
    (("a",), "_:ab _:a_ _:a/ _:a# _:a: _:a- _:a, _:a's"),
    (("a",), "_:_:a"),
    (("_:a", "a"), "_:_:a _:a"),
    (("x _:a", "a"), "_:x _:a then _:a"),  # a label holding ``_:`` is replaced whole, and only once
    (("abc", "a"), "ends with _:a"),  # the longer label runs past the end of the message
    (("", "a"), "_: and _:a"),
    ((), "_:a"),
    (("a",), "a, without the prefix"),
]


@pytest.mark.parametrize(("labels", "message"), REWRITES)
def test_labels_are_found_as_one_pattern_over_every_label_found_them(labels: tuple[str, ...], message: str) -> None:
    data = _labelled(labels)
    assert _BlankNames(data).rewrite(message) == _pattern_rewrite(data, message)


LABEL_TEXT = st.text(alphabet="ab1_:. -/#'\\é", max_size=4)
MESSAGE_PARTS = st.sampled_from(["_:", "a", "b", "1", "_", ":", " ", ".", "-", "/", "#", "'", "\\", "é"])


@pytest.mark.slow
@budget()
@given(labels=st.sets(LABEL_TEXT, max_size=6), parts=st.lists(MESSAGE_PARTS, max_size=16))
def test_labels_are_always_found_as_one_pattern_over_every_label_found_them(labels: set[str], parts: list[str]) -> None:
    data, message = _labelled(sorted(labels)), "".join(parts)
    assert _BlankNames(data).rewrite(message) == _pattern_rewrite(data, message)


@pytest.mark.parametrize("tail", ["·t", "́", "‿t", "⁀t", ".·t"])
def test_a_label_continued_by_a_non_word_turtle_label_character_is_a_longer_name(tail: str) -> None:
    """The middle dot, combining marks and undertie are Turtle label characters that ``\\w`` does not match."""
    data = Graph()
    data.add((BNode("x"), URIRef(f"{BASE}p"), URIRef(f"{BASE}o")))
    rewritten = _BlankNames(data).rewrite(f"literal _:x{tail}")
    assert rewritten == f"literal _:x{tail}"
