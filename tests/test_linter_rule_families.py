"""End-to-end fixtures covering the linter's major graph-local rule families."""

from __future__ import annotations

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SH, SKOS

from ontolint import Linter

EX = Namespace("https://example.test/")
XSD_INTEGER = URIRef("http://www.w3.org/2001/XMLSchema#integer")


def test_metadata_lexical_and_hierarchy_threshold_rules() -> None:  # noqa: PLR0915 -- comprehensive fixture.
    graph = Graph()
    first_ontology, second_ontology = EX["first.owl"], EX["second.ttl"]
    for ontology in (first_ontology, second_ontology):
        graph.add((ontology, RDF.type, OWL.Ontology))

    classes = [EX[f"Class{index}"] for index in range(5)]
    for term in classes:
        graph.add((term, RDF.type, OWL.Class))
    graph.add((classes[0], RDFS.label, Literal(" padded ")))
    graph.add((classes[0], RDFS.label, Literal("plain")))
    graph.add((classes[0], RDFS.label, Literal("english", lang="en")))
    graph.add((classes[0], RDFS.label, Literal("second", lang="en")))
    graph.add((classes[1], RDFS.label, Literal("plain")))
    graph.add((classes[1], RDFS.comment, Literal("description")))
    graph.add((classes[2], RDFS.label, Literal("lower case")))
    graph.add((classes[2], RDFS.subClassOf, classes[3]))
    graph.add((classes[3], RDFS.subClassOf, classes[4]))
    graph.add((classes[4], RDFS.subClassOf, EX.Root))
    graph.add((classes[2], RDFS.subClassOf, EX.AlternateParent))
    graph.add((EX.Root, RDF.type, OWL.Class))
    graph.add((EX.AlternateParent, RDF.type, OWL.Class))
    graph.add((EX.CamelCase, RDF.type, OWL.Class))
    graph.add((EX.with_underscore, RDF.type, OWL.Class))
    graph.add((URIRef("https://other.example/Foo"), RDF.type, OWL.Class))
    graph.add((URIRef("https://another.example/Foo"), RDF.type, OWL.Class))
    # IRI003 between two owned namespaces; the foreign Foo classes above are not owned (dominant namespace).
    graph.add((EX["sub/Foo"], RDF.type, OWL.Class))
    graph.add((EX["alt#Foo"], RDF.type, OWL.Class))
    graph.add((EX.property_one, RDF.type, OWL.ObjectProperty))
    graph.add((EX.property_one, RDFS.domain, classes[2]))
    graph.add((EX.property_two, RDF.type, OWL.ObjectProperty))
    graph.add((EX.property_two, RDFS.domain, classes[2]))

    rules = {
        finding.rule
        for finding in Linter(graph, languages=("fr",), depth_limit=2, inheritance_limit=1, soup_limit=1).run()
    }

    assert {
        "ONT002",
        "ONT003",
        "ONT004",
        "ONT005",
        "ONT006",
        "IRI002",
        "IRI003",
        "LEX001",
        "LEX002",
        "LEX003",
        "LEX004",
        "LEX005",
        "LEX006",
        "LEX007",
        "LEX008",
        "CLS005",
        "CLS006",
        "CLS008",
    } <= rules


def test_clean_metadata_and_label_do_not_raise_required_metadata_rules() -> None:
    graph = Graph()
    ontology, term = EX.clean_ontology, EX.CleanTerm
    graph.add((ontology, RDF.type, OWL.Ontology))
    graph.add((ontology, DCTERMS.license, URIRef("https://example.test/license")))
    graph.add((ontology, OWL.versionInfo, Literal("1.0")))
    graph.add((ontology, DCTERMS.creator, Literal("maintainer")))
    graph.add((ontology, DCTERMS.created, Literal("2026-01-01")))
    graph.add((ontology, DCTERMS.description, Literal("description")))
    graph.add((term, RDF.type, OWL.Class))
    graph.add((term, RDFS.label, Literal("Clean term", lang="en")))
    graph.add((term, RDFS.comment, Literal("definition")))

    rules = {finding.rule for finding in Linter(graph, languages=("en",)).run()}

    assert not {"ONT001", "ONT002", "ONT003", "ONT004", "ONT005", "ONT006", "LEX001", "LEX002", "LEX008"} & rules


def test_metadata_requires_both_creator_and_creation_date() -> None:
    graph = Graph()
    ontology = EX.partial_metadata
    graph.add((ontology, RDF.type, OWL.Ontology))
    graph.add((ontology, DCTERMS.creator, Literal("maintainer")))

    rules_without_date = {finding.rule for finding in Linter(graph).run()}
    graph.add((ontology, DCTERMS.created, Literal("2026-01-01")))
    rules_with_both = {finding.rule for finding in Linter(graph).run()}

    assert "ONT005" in rules_without_date
    assert "ONT005" not in rules_with_both


def test_ont005_names_the_provenance_that_is_missing() -> None:
    """The message says which of the two is absent, or both (0.10.0; earlier: "creator or dcterms:created")."""
    graph = Graph()
    ontology = EX.provenance
    graph.add((ontology, RDF.type, OWL.Ontology))

    def message() -> str | None:
        return next((f.message for f in Linter(graph).run() if f.rule == "ONT005"), None)

    assert message() == "Missing creator and dcterms:created provenance."
    graph.add((ontology, DCTERMS.created, Literal("2026-01-01")))
    assert message() == "Missing creator provenance."
    graph.remove((ontology, DCTERMS.created, None))
    graph.add((ontology, URIRef("http://purl.org/pav/createdBy"), Literal("maintainer")))
    assert message() == "Missing dcterms:created provenance."
    graph.add((ontology, DCTERMS.created, Literal("2026-01-01")))
    assert message() is None


def test_owl013_prints_the_literal_in_n3() -> None:
    """Not ``rdflib.term.Literal('text', ...)``, the Python repr earlier releases printed."""
    graph = Graph()
    graph.add((EX.p, RDF.type, OWL.ObjectProperty))
    graph.add((EX.i, EX.p, Literal("text", lang="en")))
    graph.add((EX.j, EX.p, Literal(1)))
    messages = sorted(f.message for f in Linter(graph).run() if f.rule == "OWL013")
    assert messages == [
        f'Object property {EX.p} points to literal "1"^^<http://www.w3.org/2001/XMLSchema#integer>.',
        f'Object property {EX.p} points to literal "text"@en.',
    ]


def test_owl013_keeps_a_literal_with_a_line_break_on_one_line() -> None:
    """``n3()`` triple-quotes such a literal, which split the text report's finding line."""
    graph = Graph()
    graph.add((EX.p, RDF.type, OWL.ObjectProperty))
    graph.add((EX.i, EX.p, Literal("a\nb\r")))
    [message] = [f.message for f in Linter(graph).run() if f.rule == "OWL013"]
    assert message == rf'Object property {EX.p} points to literal "a\nb\r".'


def test_identifier_and_declaration_boundary_rules() -> None:
    graph = Graph()
    invalid, undeclared_class, undeclared_range_property = URIRef("relative"), EX.undeclared_class, EX.range_property
    graph.add((invalid, RDF.type, OWL.Class))
    graph.add((undeclared_class, RDFS.subClassOf, EX.Parent))
    graph.add((undeclared_range_property, RDFS.range, EX.Parent))

    rules = {finding.rule for finding in Linter(graph).run()}

    assert "IRI001" in rules
    assert "OWL001" in rules
    assert "OWL002" in rules


def test_deprecated_term_is_exempt_from_missing_label_but_not_description() -> None:
    graph = Graph()
    term = EX.deprecated_term
    graph.add((term, RDF.type, OWL.Class))
    graph.add((term, OWL.deprecated, Literal(True)))

    rules = {finding.rule for finding in Linter(graph).run()}

    assert "LEX001" not in rules
    assert "LEX002" in rules


def test_identifier_and_lexical_negative_boundaries() -> None:
    graph = Graph()
    ontology = EX.stable_ontology
    graph.add((ontology, RDF.type, OWL.Ontology))
    same_namespace_left = EX["one/Foo"]
    for term in (same_namespace_left,):
        graph.add((term, RDF.type, OWL.Class))
        graph.add((term, RDFS.label, Literal("Trimmed", lang="en")))
        graph.add((term, RDFS.comment, Literal("definition")))
    graph.add((EX.numeric_label, RDF.type, OWL.Class))
    graph.add((EX.numeric_label, RDFS.label, Literal("123", lang="en")))
    graph.add((EX.numeric_label, RDFS.comment, Literal("definition")))

    rules = {finding.rule for finding in Linter(graph, languages=("en",)).run()}

    assert not {"IRI001", "IRI002", "IRI003", "LEX005", "LEX006", "LEX008", "LEX009"} & rules


def test_class_instance_and_owl_thing_prevent_orphan_and_empty_class_findings() -> None:
    graph = Graph()
    instantiated, root = EX.instantiated, EX.root
    graph.add((instantiated, RDF.type, OWL.Class))
    graph.add((EX.instance, RDF.type, instantiated))
    graph.add((root, RDF.type, OWL.Class))
    graph.add((root, RDFS.subClassOf, OWL.Thing))

    findings = {(finding.rule, finding.focus) for finding in Linter(graph).run()}

    assert ("CLS002", str(instantiated)) not in findings
    assert ("CLS001", str(root)) not in findings


def test_lexical_edge_cases_do_not_promote_review_findings() -> None:
    graph = Graph()
    tagged, empty_left, empty_right = EX.tagged, EX.empty_left, EX.empty_right
    graph.add((tagged, RDF.type, OWL.Class))
    graph.add((tagged, RDFS.label, Literal("English", lang="en")))
    graph.add((tagged, RDFS.label, Literal("Français", lang="fr")))
    for term in (empty_left, empty_right):
        graph.add((term, RDF.type, OWL.Class))
        graph.add((term, RDFS.label, Literal("")))
    for index in range(4):
        graph.add((EX[f"Other{index}"], RDF.type, OWL.Class))

    rules = {finding.rule for finding in Linter(graph).run()}

    assert "LEX006" not in rules
    assert "LEX004" not in rules
    assert "LEX007" not in rules


def test_classes_with_only_children_or_only_instances_have_distinct_empty_class_behavior() -> None:
    graph = Graph()
    parent, child, populated = EX.parent, EX.child, EX.populated
    for term in (parent, child, populated):
        graph.add((term, RDF.type, OWL.Class))
    graph.add((child, RDFS.subClassOf, parent))
    graph.add((EX.instance, RDF.type, populated))

    findings = {(finding.rule, finding.focus) for finding in Linter(graph).run()}

    assert ("CLS002", str(parent)) not in findings
    assert ("CLS002", str(populated)) not in findings
    assert ("CLS002", str(child)) in findings


def test_hierarchy_cycle_is_not_misreported_as_excessive_depth() -> None:
    """A cycle is reported separately and must not be counted as a deep tree."""
    graph = Graph()
    cycle = (EX.cycle_a, EX.cycle_b)
    tail = (EX.tail_a, EX.tail_b)
    for term in (*cycle, *tail):
        graph.add((term, RDF.type, OWL.Class))
    graph.add((cycle[0], RDFS.subClassOf, cycle[1]))
    graph.add((cycle[1], RDFS.subClassOf, cycle[0]))
    graph.add((cycle[1], RDFS.subClassOf, tail[0]))
    graph.add((tail[0], RDFS.subClassOf, tail[1]))

    findings = {(finding.rule, finding.focus) for finding in Linter(graph, depth_limit=2).run()}

    assert ("CLS003", str(cycle[0])) in findings
    assert not {("CLS005", str(term)) for term in (*cycle, *tail)} & findings


def test_cyclic_classes_are_excluded_from_depth_threshold_even_at_zero() -> None:
    graph = Graph()
    left, right = EX.zero_cycle_left, EX.zero_cycle_right
    for term in (left, right):
        graph.add((term, RDF.type, OWL.Class))
    graph.add((left, RDFS.subClassOf, right))
    graph.add((right, RDFS.subClassOf, left))

    findings = {(finding.rule, finding.focus) for finding in Linter(graph, depth_limit=-1).run()}

    assert ("CLS005", str(left)) not in findings
    assert ("CLS005", str(right)) not in findings


def test_equivalent_classes_require_an_actual_shared_label_for_duplicate_review() -> None:
    graph = Graph()
    left, right = EX.distinct_left, EX.distinct_right
    for term in (left, right):
        graph.add((term, RDF.type, OWL.Class))
    graph.add((left, RDFS.label, Literal("Left")))
    graph.add((left, OWL.equivalentClass, right))

    rules = {finding.rule for finding in Linter(graph).run()}

    assert "CLS009" not in rules


def test_owl_skos_shapes_and_governance_rules_are_reported() -> None:  # noqa: PLR0915 -- comprehensive fixture.
    graph = Graph()
    ontology = EX.ontology
    graph.add((ontology, RDF.type, OWL.Ontology))
    graph.add((ontology, OWL.imports, Literal("not-an-iri")))

    first_class, second_class = EX.First, EX.Second
    for term in (first_class, second_class):
        graph.add((term, RDF.type, OWL.Class))
        graph.add((term, RDFS.label, Literal("same label", lang="en")))
    graph.add((first_class, RDFS.subClassOf, second_class))
    graph.add((second_class, RDFS.subClassOf, first_class))
    graph.add((first_class, OWL.equivalentClass, first_class))

    object_property, data_property = EX.objectProperty, EX.dataProperty
    graph.add((object_property, RDF.type, OWL.ObjectProperty))
    graph.add((object_property, RDF.type, OWL.DatatypeProperty))
    graph.add((object_property, RDFS.domain, first_class))
    graph.add((object_property, RDFS.domain, second_class))
    graph.add((object_property, OWL.inverseOf, object_property))
    graph.add((EX.subject, object_property, Literal("literal object")))
    graph.add((data_property, RDF.type, OWL.DatatypeProperty))
    graph.add((data_property, RDFS.range, XSD_INTEGER))
    graph.add((EX.subject, data_property, EX.resource))
    graph.add((EX.other_subject, data_property, Literal("wrong datatype")))
    graph.add((EX.undeclared_property, RDFS.domain, first_class))
    graph.add((EX.undeclared_class, RDFS.subClassOf, first_class))

    restriction = BNode()
    graph.add((restriction, OWL.allValuesFrom, first_class))
    chain = BNode()
    graph.add((chain, RDF.first, object_property))
    graph.add((chain, RDF.rest, RDF.nil))
    graph.add((EX.chain_property, OWL.propertyChainAxiom, chain))

    concept = EX.concept
    graph.add((concept, RDF.type, SKOS.Concept))
    graph.add((concept, SKOS.prefLabel, Literal("Concept", lang="en")))
    graph.add((concept, SKOS.prefLabel, Literal("Another", lang="en")))
    graph.add((concept, SKOS.altLabel, Literal("Concept", lang="en")))
    graph.add((concept, SKOS.broader, concept))
    graph.add((concept, SKOS.topConceptOf, EX.scheme))
    graph.add((EX.unlabelled_concept, RDF.type, SKOS.Concept))

    deprecated = EX.deprecated
    graph.add((deprecated, OWL.deprecated, Literal(True)))
    graph.add((EX.user, EX.uses, deprecated))

    shapes = Graph()
    node_shape, property_shape = EX.NodeShape, EX.PropertyShape
    shapes.add((node_shape, RDF.type, SH.NodeShape))
    shapes.add((node_shape, SH.targetClass, first_class))
    shapes.add((property_shape, RDF.type, SH.PropertyShape))
    shapes.add((property_shape, SH.minCount, Literal(1)))
    shapes.add((property_shape, SH.name, Literal("name", lang="en")))
    shapes.add((property_shape, SH.name, Literal("another name", lang="en")))
    shapes.add((EX.undocumented_property_shape, RDF.type, SH.PropertyShape))

    rules = {finding.rule for finding in Linter(graph, shapes, base=str(EX)).run()}

    assert {
        "CLS003",
        "LEX003",
        "LEX004",
        "OWL001",
        "OWL002",
        "OWL003",
        "OWL004",
        "OWL007",
        "OWL010",
        "OWL011",
        "OWL013",
        "OWL014",
        "DATA001",
        "SKOS001",
        "SKOS002",
        "SKOS003",
        "SKOS004",
        "SKOS005",
        "SKOS006",
        "SHQ001",
        "SHQ002",
        "SHQ003",
        "SHQ004",
        "SHQ005",
        "GOV001",
        "GOV002",
    } <= rules
