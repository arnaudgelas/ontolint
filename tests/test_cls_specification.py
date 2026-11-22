"""The CLS family specification (see the ``classes``, ``class_heuristics`` and ``hierarchy_quality`` docstrings).

One section per rule: each pins a condition, an exclusion, a boundary or a known gap of the rule's
specification, with the standard it rests on.  OWL 2 is the OWL 2 Structural Specification and the OWL 2 Direct
Semantics of the 2012-12-11 Recommendations, RDFS the RDF Schema 1.1 Recommendation (RDF Semantics 1.1 for the
entailment patterns) and DCAM the DCMI Abstract Model vocabulary.  A comment saying "gap" marks behaviour that
is pinned as it is today and that deviates from the standard named; changing it is a decision, not a fix.
"""

from __future__ import annotations

from rule_harness import graph

from ontolint import Linter
from ontolint.policy import Policy

NS = "https://example.test/onto#"
C = "a owl:Class"


def _foci(rule: str, turtle: str, **policy: int) -> list[str]:
    result = Linter(graph(turtle), policy=Policy(**policy)).execute([rule])
    return sorted(f.focus.removeprefix(NS) for f in result.findings)


# --- defects fixed by this specification ---------------------------------------------------------------


def test_cls014_reports_a_class_below_disjoint_classes_inside_a_subclass_cycle() -> None:
    # OWL 2 Structural Specification 9.1.3 (DisjointClasses): A subClassOf B and A disjoint with B leave A empty,
    # and the members of a subclass cycle are equivalent (9.1.2, 9.1.1), so none of them is exempt from the check.
    cycle = f"ex:A {C}; rdfs:subClassOf ex:B . ex:B {C}; rdfs:subClassOf ex:A ."
    assert _foci("CLS014", cycle + " ex:A owl:disjointWith ex:B .") == ["A"]
    # The disjoint pair is above the cycle: it is reported once, at the representative of the cycle.
    above = f"{cycle} ex:B rdfs:subClassOf ex:D, ex:E . ex:D {C} . ex:E {C} . ex:D owl:disjointWith ex:E ."
    assert _foci("CLS014", above) == ["A"]
    # A class below the cycle is not reported again.
    assert _foci("CLS014", cycle + " ex:A owl:disjointWith ex:B . ex:X " + C + "; rdfs:subClassOf ex:A .") == ["A"]


def test_cls019_reads_equivalent_class_in_both_directions() -> None:
    # OWL 2 Structural Specification 9.1.2: EquivalentClasses is symmetric, and the RDF triple has no direction,
    # so "owl:Nothing owl:equivalentClass ex:A" asserts ex:A equal to owl:Nothing as much as the reverse.
    assert _foci("CLS019", f"ex:A {C} ; owl:equivalentClass owl:Nothing .") == ["A"]
    assert _foci("CLS019", f"ex:A {C} . owl:Nothing owl:equivalentClass ex:A .") == ["A"]


def _messages(rule: str, turtle: str, **policy: int) -> list[str]:
    result = Linter(graph(turtle), policy=Policy(**policy)).execute([rule])
    return sorted(f.message.replace(NS, "ex:") for f in result.findings)


def _chain(length: int, prefix: str = "C") -> str:
    """``length`` subclass edges: ex:C0 below ex:C1 ... below ex:C<length>."""
    edges = " ".join(f"ex:{prefix}{i} {C}; rdfs:subClassOf ex:{prefix}{i + 1} ." for i in range(length))
    return f"{edges} ex:{prefix}{length} {C} ."


def _children(parent: str, names: list[str], extra: str = "") -> str:
    kids = " ".join(f"ex:{n} {C}; rdfs:subClassOf {parent}; {extra} ." for n in names)
    return f"{parent} {C} . {kids}"


def _labelled(labels: list[str], parent: str = "ex:P") -> str:
    kids = " ".join(f"ex:K{i} {C}; rdfs:subClassOf {parent}; {label} ." for i, label in enumerate(labels))
    return f"{parent} {C} . {kids}"


def _populated(count: int, extra: str = "") -> str:
    """``count`` classes with one instance each, plus ``extra``."""
    return " ".join(f"ex:P{i} {C} . ex:i{i} a ex:P{i} ." for i in range(count)) + " " + extra


# --- CLS001: disconnected class (RDFS rdfs:subClassOf, domain and range; OWL 2 5.1 restrictions) -----------


def test_cls001_a_class_with_no_link_and_no_use_fires() -> None:
    assert _foci("CLS001", f"ex:A {C} .") == ["A"]
    assert _foci("CLS001", "ex:A a rdfs:Class .") == ["A"]


def test_cls001_a_link_or_a_use_connects_a_class() -> None:
    restriction = "[ a owl:Restriction ; owl:onProperty ex:p ; owl:someValuesFrom ex:A ]"
    for connected in (
        f"ex:A {C}; rdfs:subClassOf <http://other.test/X> .",  # a foreign or anonymous parent is a link
        f"ex:A {C}; rdfs:subClassOf {restriction} .",
        f"ex:A {C}; owl:equivalentClass ex:B .",
        f"ex:A {C}; rdfs:subClassOf owl:Thing .",
        f"ex:A {C}. ex:p rdfs:domain ex:A .",
        f"ex:A {C}. ex:p rdfs:range ex:A .",
        f"ex:A {C}. {restriction} .",
        f"ex:A {C}. [ a owl:Restriction ; owl:onProperty ex:p ; owl:allValuesFrom ex:A ] .",
        f"ex:A {C}. [ a owl:Restriction ; owl:onProperty ex:p ; owl:onClass ex:A ; owl:qualifiedCardinality 1 ] .",
        f"ex:A {C}. ex:i a ex:A .",
        f"ex:A {C}; owl:deprecated true .",
        f"ex:A {C}. ex:Z rdfs:subClassOf ex:A .",
    ):
        assert _foci("CLS001", connected) == [], connected


def test_cls001_reads_the_domain_and_range_hints_of_schema_org_and_dcam() -> None:
    # DCAM dcam:domainIncludes and dcam:rangeIncludes (the DCMI Abstract Model vocabulary) are read since 0.16.0.
    dcam = "<http://purl.org/dc/dcam/"
    assert _foci("CLS001", f"ex:A {C}. ex:p {dcam}domainIncludes> ex:A .") == []
    assert _foci("CLS001", f"ex:A {C}. ex:p {dcam}rangeIncludes> ex:A .") == []
    assert _foci("CLS001", f"ex:A {C}. ex:p <https://schema.org/domainIncludes> ex:A .") == []
    assert _foci("CLS001", f"ex:A {C}. ex:p <http://schema.org/rangeIncludes> ex:A .") == []
    # The subject of such a triple is a property: being its subject connects nothing.
    assert _foci("CLS001", f"ex:A {C}. ex:A {dcam}domainIncludes> ex:B .") == ["A"]


def test_cls001_exclusions_and_the_blank_or_ill_typed_deprecation() -> None:
    # owl:deprecated is read as the boolean true: the string "true" does not exempt, "1"^^xsd:boolean is true.
    assert _foci("CLS001", f"ex:A {C}; owl:deprecated 'true' .") == ["A"]
    assert _foci("CLS001", f"ex:A {C}; owl:deprecated '1'^^xsd:boolean .") == []
    # Only owned classes are judged (owl:Ontology IRI is the base).
    owned = f"<{NS[:-1]}> a owl:Ontology . ex:A {C} . <http://other.test/B> {C} ."
    assert _foci("CLS001", owned) == ["A"]


def test_cls001_known_gaps_pinned_as_they_are() -> None:
    # Gap (RDFS 1.1 semantics, rdfs:domain / rdfs:range are about any class expression): a class that is only a
    # member of a union used as domain, a union, an intersection, a complement or a disjointness is not connected.
    assert _foci("CLS001", f"ex:A {C}. ex:p rdfs:domain [ owl:unionOf (ex:A ex:B) ] .") == ["A"]
    assert _foci("CLS001", f"ex:A {C}. ex:B {C}; owl:unionOf (ex:A ex:C) .") == ["A", "B"]
    assert _foci("CLS001", f"ex:A {C}. ex:B {C}; owl:complementOf ex:A .") == ["A", "B"]
    assert _foci("CLS001", f"ex:A {C}; owl:disjointWith ex:B . ex:B {C} .") == ["A", "B"]
    assert _foci("CLS001", f"ex:A {C}. [ a owl:Restriction ; owl:onProperty ex:p ; owl:hasValue ex:A ] .") == ["A"]
    # Gap (RDFS entailment rdfs10, subClassOf is reflexive): an asserted self-subclass is a link here.
    assert _foci("CLS001", f"ex:A {C}; rdfs:subClassOf ex:A .") == []


# --- CLS002: class without instances or subclasses ---------------------------------------------------------


def test_cls002_a_leaf_without_instance_fires_when_the_graph_is_populated() -> None:
    # One class of four has individuals: at least POPULATED_CLASS_SHARE_DENOMINATOR = 4 share.
    leaves = f"ex:L {C} . ex:M {C} . ex:N {C} ."
    assert _foci("CLS002", _populated(1, leaves)) == ["L", "M", "N"]


def test_cls002_boundary_a_quarter_of_the_classes_populated() -> None:
    assert _foci("CLS002", _populated(1, f"ex:L {C} . ex:M {C} . ex:N {C} . ex:O {C} .")) == []  # 1 of 5
    assert _foci("CLS002", _populated(1, f"ex:L {C} . ex:M {C} . ex:N {C} .")) != []  # 1 of 4


def test_cls002_exclusions() -> None:
    populated = _populated(1, f"ex:L {C} . ex:K {C}; rdfs:subClassOf ex:L .")
    assert "L" not in _foci("CLS002", populated)  # has a subclass
    assert _foci("CLS002", f"ex:L {C} . ex:M {C} .") == []  # no individual anywhere: not instance-oriented
    # A class typed by another class is not an individual: it does not make the graph instance-oriented.
    assert _foci("CLS002", f"ex:L {C} . ex:M {C}, ex:L .") == []


def test_cls002_known_gaps_pinned_as_they_are() -> None:
    # Gap (convention, CLS001 exempts these): a deprecated class is judged, an equivalent class does not
    # inherit instances (OWL 2 Direct Semantics: equivalent classes have one extension), a foreign subclass
    # does not count, and a self-subclass counts as a subclass.
    assert _foci("CLS002", _populated(1, f"ex:L {C}; owl:deprecated true .")) == ["L"]
    assert _foci("CLS002", _populated(1, f"ex:L {C}; owl:equivalentClass ex:P0 .")) == ["L"]
    assert _foci("CLS002", _populated(1, f"ex:L {C} . <http://other.test/F> rdfs:subClassOf ex:L .")) == ["L"]
    assert _foci("CLS002", _populated(1, f"ex:L {C}; rdfs:subClassOf ex:L .")) == []


# --- CLS003: asserted subclass cycle (OWL 2 9.1.1: a cycle is legal and means equivalence) -----------------


def test_cls003_a_cycle_is_reported_once_at_its_first_member() -> None:
    two = f"ex:B {C}; rdfs:subClassOf ex:A . ex:A {C}; rdfs:subClassOf ex:B ."
    assert _foci("CLS003", two) == ["A"]
    three = f"ex:A {C}; rdfs:subClassOf ex:B . ex:B {C}; rdfs:subClassOf ex:C . ex:C {C}; rdfs:subClassOf ex:A ."
    assert _messages("CLS003", three) == ["Asserted subclass cycle: ex:A, ex:B, ex:C"]
    assert _foci("CLS003", f"ex:A {C}; rdfs:subClassOf ex:A .") == ["A"]  # a self-loop is a cycle of one


def test_cls003_exclusions_and_boundary() -> None:
    assert _foci("CLS003", f"ex:A {C}; rdfs:subClassOf ex:B . ex:B {C}; rdfs:subClassOf ex:C . ex:C {C} .") == []
    assert _foci("CLS003", f"ex:A {C}; owl:equivalentClass ex:B . ex:B {C} .") == []  # equivalence is not a cycle
    two_cycles = (
        f"ex:A {C}; rdfs:subClassOf ex:B . ex:B {C}; rdfs:subClassOf ex:A . "
        f"ex:X {C}; rdfs:subClassOf ex:Y . ex:Y {C}; rdfs:subClassOf ex:X ."
    )
    assert _foci("CLS003", two_cycles) == ["A", "X"]


def test_cls003_known_gap_a_cycle_through_an_undeclared_class_is_not_seen() -> None:
    # Gap (RDFS entailment rdfs11, subClassOf is transitive for any resource): only declared classes are nodes.
    assert _foci("CLS003", f"ex:A {C}; rdfs:subClassOf ex:B . ex:B rdfs:subClassOf ex:A .") == []


# --- CLS004: transitively redundant subclass axiom (RDFS entailment rdfs11) ------------------------------------


def test_cls004_an_edge_implied_by_a_longer_path_fires_at_the_child() -> None:
    shortcut = f"ex:A {C}; rdfs:subClassOf ex:B, ex:C . ex:B {C}; rdfs:subClassOf ex:C . ex:C {C} ."
    assert _messages("CLS004", shortcut) == ["Asserted subclass edge to ex:C is transitively redundant."]
    assert _foci("CLS004", shortcut) == ["A"]


def test_cls004_exclusions_and_boundary() -> None:
    diamond = (
        f"ex:A {C}; rdfs:subClassOf ex:B, ex:C . ex:B {C}; rdfs:subClassOf ex:D . "
        f"ex:C {C}; rdfs:subClassOf ex:D . ex:D {C} ."
    )
    assert _foci("CLS004", diamond) == []
    assert _foci("CLS004", f"ex:A {C}; rdfs:subClassOf ex:B . ex:B {C}; rdfs:subClassOf ex:A .") == []
    assert _foci("CLS004", f"ex:A {C}; rdfs:subClassOf ex:A .") == []
    assert _foci("CLS004", f"ex:A {C}; rdfs:subClassOf ex:B . ex:B {C}; rdfs:subClassOf ex:C . ex:C {C}.") == []


def test_cls004_known_gaps_pinned_as_they_are() -> None:
    # Gap (rdfs11 holds for any resource): a path through an undeclared class, or an undeclared target, is not seen.
    assert _foci("CLS004", f"ex:A {C}; rdfs:subClassOf ex:B, ex:C . ex:B rdfs:subClassOf ex:C . ex:C {C} .") == []
    assert _foci("CLS004", f"ex:A {C}; rdfs:subClassOf ex:B, ex:C . ex:B {C}; rdfs:subClassOf ex:C .") == []
    # Gap (OWL 2 9.1.2): a path through an equivalent class is not seen.
    through = f"ex:A {C}; rdfs:subClassOf ex:B, ex:C . ex:B {C}; owl:equivalentClass ex:D . ex:D rdfs:subClassOf ex:C ."
    assert _foci("CLS004", through + f" ex:C {C} .") == []
    # Gap: each edge of a cycle is judged alone, so both shortcuts of two equivalent classes are reported
    # although removing both would lose ex:A subClassOf ex:C.
    both = f"ex:A {C}; rdfs:subClassOf ex:B, ex:C . ex:B {C}; rdfs:subClassOf ex:A, ex:C . ex:C {C} ."
    assert _foci("CLS004", both) == ["A", "B"]


# --- CLS005: excessive hierarchy depth (convention, depth_limit 10) ----------------------------------------


def test_cls005_boundary_the_limit_counts_classes_on_the_longest_chain() -> None:
    assert _foci("CLS005", _chain(9)) == []  # ten classes: the limit
    assert _foci("CLS005", _chain(10)) == ["C10"]  # eleven classes
    assert _messages("CLS005", _chain(10)) == ["Asserted subtree depth 11 exceeds 10."]


def test_cls005_reports_the_topmost_over_deep_class_of_each_branch_only() -> None:
    assert _foci("CLS005", _chain(11)) == ["C11"]
    two = _chain(3, "X") + _chain(3, "Y")
    assert _foci("CLS005", two, depth_limit=2) == ["X3", "Y3"]
    assert _foci("CLS005", _chain(3), depth_limit=2) == ["C3"]


def test_cls005_known_gap_a_cycle_has_no_depth() -> None:
    # Gap (convention): the members of a cycle count 0, so a cycle never makes a branch deep (CLS003 reports it).
    assert _foci("CLS005", f"ex:A {C}; rdfs:subClassOf ex:B . ex:B {C}; rdfs:subClassOf ex:A .", depth_limit=0) == []


# --- CLS006: excessive direct superclasses (convention, inheritance_limit 5) ----------------------------


def _supers(count: int, extra: str = "") -> str:
    parents = " ".join(f"ex:S{i} {C} ." for i in range(count))
    linked = ", ".join(f"ex:S{i}" for i in range(count))
    return f"{parents} ex:A {C}; rdfs:subClassOf {linked}{extra} ."


def test_cls006_boundary_more_than_the_limit_of_declared_direct_superclasses() -> None:
    assert _foci("CLS006", _supers(5)) == []
    assert _foci("CLS006", _supers(6)) == ["A"]
    assert _messages("CLS006", _supers(6)) == ["6 direct superclasses (threshold 5)."]
    assert _foci("CLS006", _supers(3), inheritance_limit=2) == ["A"]


def test_cls006_a_restriction_or_a_foreign_superclass_is_not_counted() -> None:
    restriction = ", [ a owl:Restriction ; owl:onProperty ex:p ; owl:someValuesFrom ex:S0 ]"
    assert _foci("CLS006", _supers(5, restriction)) == []
    assert _foci("CLS006", _supers(5, ", <http://other.test/F>")) == []


def test_cls006_known_gap_a_self_subclass_counts_as_a_direct_superclass() -> None:
    # Gap (RDFS entailment rdfs10: a class is its own subclass, which is no superclass worth reviewing): CLS011,
    # CLS012 and CLS013 drop self-loops, CLS006 does not.
    assert _foci("CLS006", _supers(5, ", ex:A")) == ["A"]


# --- CLS007: long single-child taxonomic chain (convention, MINIMUM_SINGLE_CHILD_CHAIN_LENGTH 3) -----------


def test_cls007_boundary_three_edges_below_a_class() -> None:
    assert _foci("CLS007", _chain(2)) == []
    assert _foci("CLS007", _chain(3)) == ["C3"]
    assert _messages("CLS007", _chain(3)) == ["Single-child hierarchy extends 3 edges below class."]


def test_cls007_every_class_above_the_boundary_is_reported() -> None:
    assert _foci("CLS007", _chain(4)) == ["C3", "C4"]


def test_cls007_a_second_child_or_a_second_parent_of_the_leaf_ends_the_chain() -> None:
    assert _foci("CLS007", _chain(3) + f" ex:Z {C}; rdfs:subClassOf ex:C1 .") == []
    assert _foci("CLS007", _chain(3) + f" ex:Z {C}; rdfs:subClassOf ex:C3 .") == []


def test_cls007_known_gaps_a_ring_of_classes_is_a_chain() -> None:
    # Gap (a cycle is not a chain, CLS003 reports it): each member of a ring of three sees the whole ring.
    ring = f"ex:A {C}; rdfs:subClassOf ex:B . ex:B {C}; rdfs:subClassOf ex:C . ex:C {C}; rdfs:subClassOf ex:A ."
    assert _foci("CLS007", ring) == ["A", "B", "C"]
    assert _foci("CLS007", f"ex:A {C}; rdfs:subClassOf ex:A .") == []


# --- CLS008: class with excessive asserted properties (convention, soup_limit 15) -------------------------


def _domain_of(
    count: int, domain: str = "ex:A", predicate: str = "rdfs:domain", kind: str = "a owl:ObjectProperty"
) -> str:
    return f"ex:A {C} . " + " ".join(f"ex:p{i} {kind}; {predicate} {domain} ." for i in range(count))


def test_cls008_boundary_more_than_the_limit_of_properties_with_the_class_as_domain() -> None:
    assert _foci("CLS008", _domain_of(15)) == []
    assert _foci("CLS008", _domain_of(16)) == ["A"]
    assert _messages("CLS008", _domain_of(2), soup_limit=1) == [
        f"2 properties with asserted domain {NS.replace(NS, 'ex:')}A."
    ]


def test_cls008_counts_any_subject_of_rdfs_domain_and_a_property_once() -> None:
    assert _foci("CLS008", _domain_of(16, kind="a rdf:Property")) == ["A"]
    assert _foci("CLS008", _domain_of(16, kind="")) == ["A"]
    assert _foci("CLS008", _domain_of(15) + " ex:p0 rdfs:domain ex:A .") == []


def test_cls008_known_gaps_pinned_as_they_are() -> None:
    # Gap (OWL005 and CLS001 read the domain hints): dcam:domainIncludes is not a domain here.
    assert _foci("CLS008", _domain_of(16, predicate="<http://purl.org/dc/dcam/domainIncludes>")) == []
    # Gap (RDFS rdfs2): a domain that is a union does not count for its members, nor does an inherited property.
    assert _foci("CLS008", _domain_of(16, domain="[ owl:unionOf (ex:A ex:B) ]")) == []
    inherited = _domain_of(16) + f" ex:B {C}; rdfs:subClassOf ex:A ."
    assert _foci("CLS008", inherited) == ["A"]
    # A foreign class is not judged.
    assert _foci("CLS008", _domain_of(16, domain="<http://other.test/X>")) == []


# --- CLS009: equivalent classes with identical labels --------------------------------------------------


def _equivalent(left: str, right: str) -> str:
    return f"ex:A {C}; {left}; owl:equivalentClass ex:B . ex:B {C}; {right} ."


def test_cls009_equivalent_classes_with_one_rdfs_label_after_case_folding_fire() -> None:
    assert _foci("CLS009", _equivalent('rdfs:label "X"', 'rdfs:label "x"')) == ["A"]
    reverse = f'ex:A {C}; rdfs:label "X" . ex:B {C}; rdfs:label "x"; owl:equivalentClass ex:A .'
    assert _foci("CLS009", reverse) == ["B"]  # the triple's subject is the focus
    assert _messages("CLS009", _equivalent('rdfs:label "X"', 'rdfs:label "x"')) == [
        "Equivalent class ex:B has an identical label (review duplication)."
    ]


def test_cls009_exclusions() -> None:
    assert _foci("CLS009", _equivalent('rdfs:label "x"', 'rdfs:label "y"')) == []
    assert _foci("CLS009", f'ex:A {C}; owl:equivalentClass ex:B . ex:B {C}; rdfs:label "x" .') == []
    assert _foci("CLS009", _equivalent('rdfs:label "X"', 'rdfs:label "x"').replace("ex:B a owl:Class", "ex:B")) == []
    assert _foci("CLS009", f'ex:A {C}; rdfs:label "X"; owl:equivalentClass ex:A .') == []  # OWL012 reports it
    assert _foci("CLS009", _equivalent('skos:altLabel "X"', 'skos:altLabel "x"')) == []


def test_cls009_known_gaps_pinned_as_they_are() -> None:
    # Gap (RDF 1.1 Concepts 3.3, a language tag is part of the literal; CLS010 and CLS020 compare it): the
    # language and the datatype are ignored.
    assert _foci("CLS009", _equivalent('rdfs:label "X"@en', 'rdfs:label "x"@fr')) == ["A"]
    assert _foci("CLS009", _equivalent("rdfs:label 1", 'rdfs:label "1"')) == ["A"]
    # Gap (RDFS 1.1: the range of rdfs:label is rdfs:Literal): an IRI value is compared by its text, and a blank
    # label is an identical label.
    assert _foci("CLS009", _equivalent("rdfs:label ex:Z", "rdfs:label ex:Z")) == ["A"]
    assert _foci("CLS009", _equivalent('rdfs:label ""', 'rdfs:label ""')) == ["A"]
    # Gap (convention, CLS010 reads the main labels): only rdfs:label is read, no prefLabel, no inner whitespace
    # collapsing, no stripping.
    assert _foci("CLS009", _equivalent('skos:prefLabel "X"', 'skos:prefLabel "x"')) == []
    assert _foci("CLS009", _equivalent('rdfs:label "x  y"', 'rdfs:label "x y"')) == []
    assert _foci("CLS009", _equivalent('rdfs:label " x"', 'rdfs:label "x"')) == []


def test_owl012_a_class_equivalent_to_itself_is_not_a_cls009_finding() -> None:
    assert _foci("OWL012", f"ex:A {C}; owl:equivalentClass ex:A .") == ["A"]


# --- CLS010: sibling classes with identical labels (convention) ----------------------------------------


def test_cls010_siblings_with_one_main_label_in_one_language_fire() -> None:
    assert _foci("CLS010", _labelled(['rdfs:label "x"', 'rdfs:label "X"'])) == ["K0", "K1"]
    three = _labelled(['rdfs:label "x"', 'rdfs:label "x"', 'rdfs:label "x"'])
    assert _foci("CLS010", three) == ["K0", "K1", "K2"]
    assert _messages("CLS010", _labelled(['rdfs:label "x"', 'rdfs:label "x"'])) == [
        "Shares label 'x' with sibling ex:K0 under ex:P.",
        "Shares label 'x' with sibling ex:K1 under ex:P.",
    ]


def test_cls010_labels_are_compared_after_collapsing_inner_whitespace_and_across_main_predicates() -> None:
    assert _foci("CLS010", _labelled(['rdfs:label "x y"', 'rdfs:label "x  y"'])) == ["K0", "K1"]
    assert _foci("CLS010", _labelled(['skos:prefLabel "x"; rdfs:label "z"', 'rdfs:label "x"'])) == ["K0", "K1"]


def test_cls010_exclusions() -> None:
    assert _foci("CLS010", _labelled(['rdfs:label "x"@en', 'rdfs:label "x"@fr'])) == []
    assert _foci("CLS010", _labelled(['rdfs:label ""', 'rdfs:label " "'])) == []
    assert _foci("CLS010", _labelled(['rdfs:label "x", "x"@en'])) == []  # one class, two labels
    assert _foci("CLS010", _labelled(['rdfs:label "a"; skos:altLabel "x"', 'rdfs:label "b"; skos:altLabel "x"'])) == []
    other_parents = f"ex:P {C} . ex:Q {C} . ex:K0 {C}; rdfs:subClassOf ex:P; rdfs:label 'x' . "
    assert _foci("CLS010", other_parents + f"ex:K1 {C}; rdfs:subClassOf ex:Q; rdfs:label 'x' .") == []


def test_cls010_known_gaps_pinned_as_they_are() -> None:
    # Gap (LEX004 exempts a deprecated term): a deprecated sibling is judged.
    deprecated = _labelled(['rdfs:label "x"; owl:deprecated true', 'rdfs:label "x"'])
    assert _foci("CLS010", deprecated) == ["K0", "K1"]
    # Gap (RDF 1.1 Concepts 3.3): the datatype is ignored, "x"^^xsd:string is the plain "x", and so is any other.
    assert _foci("CLS010", _labelled(['rdfs:label "1"', "rdfs:label 1"])) == ["K0", "K1"]
    # Two siblings of two parents are reported once under each.
    both = f"ex:Q {C} . " + _labelled(['rdfs:label "x"', 'rdfs:label "x"']).replace(
        "rdfs:subClassOf ex:P", "rdfs:subClassOf ex:P, ex:Q"
    )
    assert len(_messages("CLS010", both)) == 4


# --- CLS011: excessive direct subclasses (convention, subclass_limit 50) --------------------------------


def test_cls011_boundary_more_than_the_limit_of_declared_direct_subclasses() -> None:
    assert _foci("CLS011", _children("ex:P", [f"K{i}" for i in range(50)])) == []
    assert _foci("CLS011", _children("ex:P", [f"K{i}" for i in range(51)])) == ["P"]
    assert _messages("CLS011", _children("ex:P", ["A", "B", "C"]), subclass_limit=2) == [
        "3 direct subclasses (threshold 2)."
    ]


def test_cls011_exclusions() -> None:
    assert _foci("CLS011", _children("ex:P", [f"K{i}" for i in range(50)]) + " ex:P rdfs:subClassOf ex:P .") == []
    foreign = " ".join(f"ex:K{i} {C}; rdfs:subClassOf <http://other.test/P> ." for i in range(51))
    assert _foci("CLS011", foreign) == []


# --- CLS012: instantiated class with only unused leaf subclasses -----------------------------------------


def test_cls012_an_instantiated_class_whose_subclasses_are_all_unused_leaves_fires() -> None:
    base = f"ex:P {C} . ex:i a ex:P . ex:K {C}; rdfs:subClassOf ex:P ."
    assert _foci("CLS012", base) == ["P"]
    assert _messages("CLS012", base) == ["Class has instances but its 1 subclass(es) are unused leaves."]
    assert _foci("CLS012", base + f" ex:K2 {C}; rdfs:subClassOf ex:P .") == ["P"]


def test_cls012_exclusions_and_boundary() -> None:
    base = f"ex:P {C} . ex:i a ex:P . ex:K {C}; rdfs:subClassOf ex:P ."
    assert _foci("CLS012", base + " ex:j a ex:K .") == []  # a used leaf
    assert _foci("CLS012", base + f" ex:L {C}; rdfs:subClassOf ex:K .") == []  # not a leaf
    assert _foci("CLS012", base + f" ex:K2 {C}; rdfs:subClassOf ex:P . ex:j a ex:K2 .") == []  # one used among two
    assert _foci("CLS012", f"ex:P {C} . ex:i a ex:P .") == []  # no subclass at all
    assert _foci("CLS012", f"ex:P {C} . ex:K {C}; rdfs:subClassOf ex:P .") == []  # not instantiated
    assert _foci("CLS012", f"ex:P {C} . ex:i a ex:P . <http://other.test/K> rdfs:subClassOf ex:P .") == []


def test_cls012_known_gaps_pinned_as_they_are() -> None:
    # Gap (CLS001 exempts a deprecated class): a deprecated leaf is an unused leaf.
    assert _foci("CLS012", f"ex:P {C} . ex:i a ex:P . ex:K {C}; owl:deprecated true; rdfs:subClassOf ex:P .") == ["P"]
    # Gap (OWL 2 punning): a class typed by the parent counts as an instance of it.
    assert _foci("CLS012", f"ex:P {C} . ex:Q {C}, ex:P . ex:K {C}; rdfs:subClassOf ex:P .") == ["P"]


# --- CLS013: miscellaneous remainder class (convention) -------------------------------------------------


def _remainder(name: str, label: str | None = None, parent_label: str | None = None) -> str:
    own = f'; rdfs:label "{label}"' if label else ""
    parent = f'; rdfs:label "{parent_label}"' if parent_label else ""
    return f"ex:Animal {C}{parent} . ex:{name} {C}; rdfs:subClassOf ex:Animal{own} ."


def test_cls013_a_marker_word_with_only_filler_or_parent_words_fires() -> None:
    for name in ("Other", "OtherAnimal", "Other_Animal", "OtherKindOfAnimal", "OtherAndAnimal", "Remainder"):
        assert _foci("CLS013", _remainder(name)) == [name], name
    assert _foci("CLS013", _remainder("UnclassifiedAnimal")) == ["UnclassifiedAnimal"]
    assert _foci("CLS013", _remainder("K1", label="Other (animal)")) == ["K1"]  # a label counts
    assert _foci("CLS013", _remainder("OtherK", parent_label="K")) == ["OtherK"]  # so does the parent's label
    assert _messages("CLS013", _remainder("Other")) == ["Catch-all subclass of ex:Animal."]


def test_cls013_exclusions() -> None:
    assert _foci("CLS013", _remainder("OtherPlant")) == []  # a word that is not the parent's
    assert _foci("CLS013", _remainder("AnotherAnimal")) == []  # the marker is a whole token
    assert _foci("CLS013", _remainder("Miscellany")) == []
    assert _foci("CLS013", f"ex:Other {C} .") == []  # needs a declared parent
    assert _foci("CLS013", f"ex:Other {C}; rdfs:subClassOf <http://other.test/Animal> .") == []


def test_cls013_known_gaps_pinned_as_they_are() -> None:
    # Gap (convention): no plural or accent handling, so "Other animals" and "Autres animaux" are not remainders.
    assert _foci("CLS013", _remainder("OtherAnimals")) == []
    assert _foci("CLS013", _remainder("K1", label="Misc. animals")) == []
    assert _foci("CLS013", _remainder("K1", label="Autres animaux")) == []
    # Gap (OWL 2 5.1, owl:Thing is the top class): a catch-all below owl:Thing is not below a declared class.
    assert _foci("CLS013", f"ex:Other {C}; rdfs:subClassOf owl:Thing .") == []


# --- CLS014: class below two asserted-disjoint classes (OWL 2 9.1.3, 9.1.4) -------------------------------


def _below(disjointness: str) -> str:
    return f"ex:A {C} . ex:B {C} . ex:X {C}; rdfs:subClassOf ex:A, ex:B . {disjointness}"


def test_cls014_a_class_below_two_disjoint_classes_fires_certainly() -> None:
    for disjointness in (
        "ex:A owl:disjointWith ex:B .",
        "ex:B owl:disjointWith ex:A .",
        "[ a owl:AllDisjointClasses ; owl:members (ex:A ex:B) ] .",
    ):
        assert _foci("CLS014", _below(disjointness)) == ["X"], disjointness
    result = Linter(graph(_below("ex:A owl:disjointWith ex:B .")), policy=Policy()).execute(["CLS014"])
    assert [(f.severity, f.confidence) for f in result.findings] == [("warning", "certain")]
    assert _messages("CLS014", _below("ex:A owl:disjointWith ex:B .")) == ["Below disjoint classes ex:A and ex:B."]


def test_cls014_is_reported_at_the_topmost_class_through_ancestors() -> None:
    via = (
        f"ex:A {C} . ex:B {C} . ex:A1 {C}; rdfs:subClassOf ex:A . ex:B1 {C}; rdfs:subClassOf ex:B . "
        f"ex:X {C}; rdfs:subClassOf ex:A1, ex:B1 . ex:Y {C}; rdfs:subClassOf ex:X . ex:A owl:disjointWith ex:B ."
    )
    assert _foci("CLS014", via) == ["X"]
    members = "ex:C a owl:Class . [ a owl:AllDisjointClasses ; owl:members (ex:A ex:C ex:B) ] ."
    assert _foci("CLS014", _below(members)) == ["X"]


def test_cls014_exclusions() -> None:
    assert _foci("CLS014", _below("")) == []
    assert _foci("CLS014", _below("[ a owl:AllDisjointClasses ; owl:distinctMembers (ex:A ex:B) ] .")) == []
    assert _foci("CLS014", f"ex:A {C}; owl:disjointWith ex:A .") == []
    # A class that is only declared below one of the pair, or an instance typed by both, is not a class below both.
    assert _foci("CLS014", f"ex:A {C} . ex:B {C} . ex:A owl:disjointWith ex:B . ex:i a ex:A, ex:B .") == []


def test_cls014_a_subclass_cycle_is_judged_as_one_class() -> None:
    cycle = f"ex:A {C}; rdfs:subClassOf ex:B . ex:B {C}; rdfs:subClassOf ex:A . ex:A owl:disjointWith ex:B ."
    assert _foci("CLS014", cycle) == ["A"]


def test_cls014_known_gaps_pinned_as_they_are() -> None:
    # Gap (OWL 2 9.1.4): owl:disjointUnionOf makes its members pairwise disjoint; it is not read.
    union = f"ex:C {C}; owl:disjointUnionOf (ex:A ex:B) ."
    assert _foci("CLS014", _below(union)) == []
    # Gap (OWL 2 9.1.2): an equivalent class carries its disjointness over; it is not followed.
    equal = f"ex:A {C}; owl:disjointWith ex:B . ex:B {C} . ex:X {C}; rdfs:subClassOf ex:A; owl:equivalentClass ex:B ."
    assert _foci("CLS014", equal) == []
    # Gap (OWL 2 9.1.3, DisjointClasses with one class repeated is unsatisfiable): not read.
    # Gap (RDFS entailment rdfs11): an ancestor that is not a declared class is not an ancestor here.
    assert _foci("CLS014", f"ex:A {C} . ex:X {C}; rdfs:subClassOf ex:A, ex:B . ex:A owl:disjointWith ex:B .") == []


# --- CLS015: unlabelled class with several subclasses (convention) -------------------------------------


def _parent(label: str, subclasses: int = 3) -> str:
    return f"ex:P {C}{label} . " + " ".join(f"ex:K{i} {C}; rdfs:subClassOf ex:P ." for i in range(subclasses))


def test_cls015_boundary_three_direct_subclasses_and_no_label() -> None:
    assert _foci("CLS015", _parent("")) == ["P"]
    assert _messages("CLS015", _parent("")) == ["Class has 3 direct subclasses but no label."]
    assert _foci("CLS015", _parent("", 2)) == []


def test_cls015_any_literal_label_of_the_closure_counts() -> None:
    assert _foci("CLS015", _parent('; rdfs:label "p"')) == []
    assert _foci("CLS015", _parent('; skos:prefLabel "p"')) == []


def test_cls015_known_gaps_pinned_as_they_are() -> None:
    # A blank label, an IRI value and an alt label are no label; a deprecated parent is still judged (LEX001
    # exempts it).
    for label in ('; rdfs:label " "', "; rdfs:label ex:Z", '; skos:altLabel "p"', "; owl:deprecated true"):
        assert _foci("CLS015", _parent(label)) == ["P"], label


# --- CLS016: generic is-a style property (convention) ----------------------------------------------------


def test_cls016_a_property_named_is_or_is_a_kind_of_fires() -> None:
    for name in ("isA", "is_a", "is-a-kind-of", "isKindOf", "is", "IS", "isa", "isTypeOf", "IsA"):
        assert _foci("CLS016", f"ex:{name} a owl:ObjectProperty .") == [name], name
    assert _foci("CLS016", "ex:isA a owl:AnnotationProperty .") == ["isA"]
    assert _foci("CLS016", "ex:isa a rdf:Property .") == ["isa"]


def test_cls016_exclusions() -> None:
    for name in ("isPartOf", "hasType", "is1a", "isAnimal"):
        assert _foci("CLS016", f"ex:{name} a owl:ObjectProperty .") == [], name
    assert _foci("CLS016", 'ex:p a owl:ObjectProperty ; rdfs:label "is a" .') == []  # only the local name is read
    assert _foci("CLS016", f"ex:isA {C} .") == []  # a class is not a property


# --- CLS017: class also used as an individual (OWL 2 punning) -----------------------------------------


def test_cls017_a_class_typed_as_an_individual_fires() -> None:
    assert _foci("CLS017", f"ex:A {C}, owl:NamedIndividual .") == ["A"]
    assert _foci("CLS017", f"ex:A {C}, ex:B . ex:B {C} .") == ["A"]
    assert _foci("CLS017", "ex:A a rdfs:Class, ex:B . ex:B a rdfs:Class .") == ["A"]
    assert _messages("CLS017", f"ex:A {C}, owl:NamedIndividual .") == [
        "Class is also typed as an individual (punning)."
    ]


def test_cls017_exclusions() -> None:
    assert _foci("CLS017", f"ex:A {C}, ex:B .") == []  # typed by an undeclared class
    assert _foci("CLS017", f"ex:A {C}, <http://other.test/Z> .") == []
    meta = f"ex:Meta rdfs:subClassOf rdfs:Class . ex:Meta {C} . ex:A {C}, ex:Meta ."
    assert _foci("CLS017", meta) == []  # a metaclass (below rdfs:Class) is not an individual's class
    assert _foci("CLS017", f"ex:A {C}, owl:Thing .") == []


def test_cls017_known_gaps_judges_only_typing() -> None:
    # Gap (OWL 2 Structural Specification, punning: an IRI is an individual wherever it is the subject or the
    # object of an individual assertion): a class that is the object or subject of a property assertion is not
    # reported, only an rdf:type to owl:NamedIndividual or a declared class is.
    assert _foci("CLS017", f"ex:A {C} . ex:i ex:p ex:A .") == []
    assert _foci("CLS017", f"ex:A {C}; ex:p 'v' .") == []
    assert _foci("CLS017", f"ex:A {C}, owl:ObjectProperty .") == []  # property punning is not read either
    assert _foci("CLS017", f"ex:A {C}, skos:Concept .") == []


# --- CLS018: redundant owl:Thing superclass (OWL 2 5.1: every class is below owl:Thing) -------------------


def test_cls018_owl_thing_or_rdfs_resource_beside_another_superclass_fires() -> None:
    assert _foci("CLS018", f"ex:A {C}; rdfs:subClassOf owl:Thing, ex:B . ex:B {C} .") == ["A"]
    assert _foci("CLS018", f"ex:A {C}; rdfs:subClassOf rdfs:Resource, ex:B . ex:B {C} .") == ["A"]
    restriction = "[ a owl:Restriction ; owl:onProperty ex:p ; owl:someValuesFrom ex:B ]"
    assert _foci("CLS018", f"ex:A {C}; rdfs:subClassOf owl:Thing, {restriction} .") == ["A"]
    assert _foci("CLS018", f"ex:A {C}; rdfs:subClassOf owl:Thing, <http://other.test/F> .") == ["A"]
    assert _messages("CLS018", f"ex:A {C}; rdfs:subClassOf owl:Thing, ex:B .") == [
        "Explicit owl:Thing/rdfs:Resource superclass next to another superclass."
    ]


def test_cls018_exclusions() -> None:
    assert _foci("CLS018", f"ex:A {C}; rdfs:subClassOf owl:Thing .") == []
    assert _foci("CLS018", f"ex:A {C}; rdfs:subClassOf owl:Thing, ex:A .") == []  # itself is no other superclass
    assert _foci("CLS018", f"ex:A {C}; rdfs:subClassOf owl:Thing, rdfs:Resource .") == []


def test_cls018_known_gaps_pinned_as_they_are() -> None:
    # Gap (OWL 2 5.1): owl:Nothing is below every class, yet it counts as "another superclass"; an equivalent
    # class does not.
    assert _foci("CLS018", f"ex:A {C}; rdfs:subClassOf owl:Thing, owl:Nothing .") == ["A"]
    assert _foci("CLS018", f"ex:A {C}; rdfs:subClassOf owl:Thing; owl:equivalentClass ex:B .") == []


# --- CLS019: class asserted equal to or below owl:Nothing (OWL 2 5.1, 9.1.1, 9.1.2) ----------------------


def test_cls019_a_class_below_or_equivalent_to_owl_nothing_fires_certainly() -> None:
    assert _foci("CLS019", f"ex:A {C}; rdfs:subClassOf owl:Nothing .") == ["A"]
    assert _foci("CLS019", f"ex:A {C}; owl:equivalentClass owl:Nothing .") == ["A"]
    assert _foci("CLS019", f"ex:A {C} . owl:Nothing owl:equivalentClass ex:A .") == ["A"]
    result = Linter(graph(f"ex:A {C}; rdfs:subClassOf owl:Nothing ."), policy=Policy()).execute(["CLS019"])
    assert [(f.severity, f.confidence) for f in result.findings] == [("warning", "certain")]


def test_cls019_exclusions_and_the_class_below_an_empty_class() -> None:
    assert _foci("CLS019", f"ex:A {C}; rdfs:subClassOf owl:Thing .") == []
    assert _foci("CLS019", f"ex:A {C}; rdfs:subClassOf ex:B . ex:B {C} .") == []
    # owl:Nothing declared as a class is the bottom class, not a finding of its own.
    assert _foci("CLS019", f"owl:Nothing {C}; rdfs:subClassOf owl:Nothing .") == []


def test_cls019_known_gaps_pinned_as_they_are() -> None:
    # Gap (OWL 2 Direct Semantics): a class below an unsatisfiable class, or disjoint with owl:Thing, or equivalent
    # to the complement of owl:Thing, is empty too; only the asserted link to owl:Nothing is read.
    assert _foci("CLS019", f"ex:A {C}; owl:disjointWith owl:Thing .") == []
    assert _foci("CLS019", f"ex:A {C}; owl:equivalentClass [ owl:complementOf owl:Thing ] .") == []
    assert _foci("CLS019", f"ex:A {C}; rdfs:subClassOf owl:Nothing . ex:B {C}; rdfs:subClassOf ex:A .") == ["A"]


# --- CLS020: subclass labelled like its superclass (convention) ---------------------------------------


def _pair(parent: str, child: str) -> str:
    return f"ex:P {C}; {parent} . ex:K {C}; rdfs:subClassOf ex:P; {child} ."


def test_cls020_a_subclass_sharing_a_label_with_its_direct_superclass_fires() -> None:
    assert _foci("CLS020", _pair('rdfs:label "x"', 'rdfs:label "X"')) == ["K"]
    assert _foci("CLS020", _pair('skos:prefLabel "x"', 'rdfs:label "x"')) == ["K"]
    assert _messages("CLS020", _pair('rdfs:label "x"', 'rdfs:label "x"')) == ["Same label as its superclass ex:P."]


def test_cls020_exclusions() -> None:
    assert _foci("CLS020", _pair('rdfs:label "x"@en', 'rdfs:label "x"@fr')) == []
    assert _foci("CLS020", _pair('skos:altLabel "x"', 'skos:altLabel "x"')) == []
    assert _foci("CLS020", _pair('rdfs:label ""', 'rdfs:label " "')) == []
    assert _foci("CLS020", _pair('rdfs:label "x."', 'rdfs:label "x"')) == []
    assert _foci("CLS020", f'ex:P {C}; rdfs:subClassOf ex:P; rdfs:label "x" .') == []  # a self-loop is dropped
    grand = f'ex:G {C}; rdfs:label "x" . ex:P {C}; rdfs:subClassOf ex:G; rdfs:label "y" . '
    assert _foci("CLS020", grand + f'ex:K {C}; rdfs:subClassOf ex:P; rdfs:label "x" .') == []  # direct links only


def test_cls020_known_gaps_pinned_as_they_are() -> None:
    # Gap (convention, CLS010 reads the main labels): only rdfs:label and skos:prefLabel are read, so a
    # configured extra label predicate or a sub-property of rdfs:label is not.
    sub = f'ex:lab rdfs:subPropertyOf rdfs:label . ex:P {C}; ex:lab "x" . ex:K {C}; rdfs:subClassOf ex:P; ex:lab "x" .'
    assert _foci("CLS020", sub) == []
    # Both members of a two-class cycle are each other's superclass.
    cycle = f'ex:A {C}; rdfs:subClassOf ex:B; rdfs:label "x" . ex:B {C}; rdfs:subClassOf ex:A; rdfs:label "x" .'
    assert _foci("CLS020", cycle) == ["A", "B"]


# --- CLS021: equivalent class that is also an asserted ancestor (OWL 2 9.1.2) -----------------------------


def test_cls021_a_class_equivalent_to_its_asserted_ancestor_fires_in_either_direction() -> None:
    assert _foci("CLS021", f"ex:P {C} . ex:K {C}; rdfs:subClassOf ex:P; owl:equivalentClass ex:P .") == ["K"]
    assert _foci("CLS021", f"ex:P {C}; owl:equivalentClass ex:K . ex:K {C}; rdfs:subClassOf ex:P .") == ["K"]
    assert _messages("CLS021", f"ex:P {C} . ex:K {C}; rdfs:subClassOf ex:P; owl:equivalentClass ex:P .") == [
        "Equivalent to its asserted ancestor ex:P."
    ]
    grand = f"ex:G {C} . ex:P {C}; rdfs:subClassOf ex:G . ex:K {C}; rdfs:subClassOf ex:P; owl:equivalentClass ex:G ."
    assert _foci("CLS021", grand) == ["K"]


def test_cls021_exclusions_and_the_two_way_case() -> None:
    assert _foci("CLS021", f"ex:A {C}; owl:equivalentClass ex:B . ex:B {C} .") == []
    assert _foci("CLS021", f"ex:A {C}; owl:equivalentClass ex:A; rdfs:subClassOf ex:A .") == []
    both = f"ex:A {C}; rdfs:subClassOf ex:B; owl:equivalentClass ex:B . ex:B {C}; rdfs:subClassOf ex:A ."
    assert _foci("CLS021", both) == ["A", "B"]  # each is the other's ancestor


def test_cls021_known_gap_an_ancestor_path_through_an_undeclared_class_is_not_seen() -> None:
    # Gap (RDFS entailment rdfs11): only declared classes are on the path.
    path = f"ex:G {C} . ex:K {C}; rdfs:subClassOf ex:P; owl:equivalentClass ex:G . ex:P rdfs:subClassOf ex:G ."
    assert _foci("CLS021", path) == []


# --- CLS022: class named like a property (convention) -----------------------------------------------------


def test_cls022_a_local_name_starting_with_a_verb_and_a_word_boundary_fires() -> None:
    for name in ("hasPart", "has_part", "is-part", "has1", "isPart", "canDo", "doesWork", "wasBorn"):
        assert _foci("CLS022", f"ex:{name} {C} .") == [name], name
    assert _messages("CLS022", f"ex:hasPart {C} .") == ["Local name 'hasPart' looks like a property name."]


def test_cls022_exclusions() -> None:
    for name in ("Hashing", "HasPart", "Issue", "Island", "isolation", "hasa", "has", "Is"):
        assert _foci("CLS022", f"ex:{name} {C} .") == [], name
    assert _foci("CLS022", "ex:hasPart a owl:ObjectProperty .") == []  # classes only
    assert _foci("CLS022", f"<http://other.test/has/Part> {C} .") == []  # the last path segment is read


# --- CLS023: class name encodes a conjunction (convention) ---------------------------------------------


def test_cls023_and_or_between_two_other_tokens_fires() -> None:
    for name in ("CatAndDog", "CatOrDog", "cat_and_dog", "Cat-and-Dog", "CAT_AND_DOG", "CatANDDog", "XAndOrY"):
        assert _foci("CLS023", f"ex:{name} {C} .") == [name], name
    assert _messages("CLS023", f"ex:CatAndDog {C} .") == ["Local name 'CatAndDog' joins concepts with a conjunction."]


def test_cls023_boundary_the_first_and_last_token_do_not_count() -> None:
    for name in ("And", "AndDog", "CatAnd", "Random", "BrandNew", "ANDRE", "CATANDDOG"):
        assert _foci("CLS023", f"ex:{name} {C} .") == [], name
    assert _foci("CLS023", f'ex:K1 {C}; rdfs:label "Cat and dog" .') == []  # the local name only


def test_cls023_known_gap_a_fixed_expression_is_a_conjunction() -> None:
    # Gap (convention): "Bed and Breakfast" and "Smith and Wesson" name one concept each.
    for name in ("BedAndBreakfast", "SmithAndWesson", "Cat2And3"):
        assert _foci("CLS023", f"ex:{name} {C} .") == [name]


# --- CLS024: sibling class breaking the naming pattern (convention) -------------------------------------


def _siblings(names: list[str], parent: str = "ex:Cat") -> str:
    return _children(parent, names, "")


def test_cls024_the_one_sibling_not_ending_in_the_parents_head_word_fires() -> None:
    assert _foci("CLS024", _siblings(["BlackCat", "WhiteCat", "RedCat", "Dog"])) == ["Dog"]
    assert _messages("CLS024", _siblings(["BlackCat", "WhiteCat", "RedCat", "Dog"])) == [
        "Name does not end in 'cat' like its 3 siblings under ex:Cat."
    ]
    assert _foci("CLS024", _siblings(["BlackCat", "WhiteCat", "RedCat", "Dog"], "ex:BigCat")) == ["Dog"]
    assert _foci("CLS024", _siblings(["BlackCat", "WhiteCat", "RedCat", "Reddog"])) == ["Reddog"]


def test_cls024_boundary_four_siblings_and_exactly_one_outlier() -> None:
    assert _foci("CLS024", _siblings(["BlackCat", "WhiteCat", "Dog"])) == []  # three siblings
    assert _foci("CLS024", _siblings(["BlackCat", "WhiteCat", "Dog", "Cow"])) == []  # two outliers
    assert _foci("CLS024", _siblings(["A1", "B1", "C1", "D1"])) == []


def test_cls024_exclusions() -> None:
    assert _foci("CLS024", _siblings(["BlackCat", "WhiteCat", "RedCat", "Cat"])) == []  # one token: not a modifier
    assert _foci("CLS024", _siblings(["BlackCat", "WhiteCat", "RedCat", "Dog"], "ex:Animal")) == []
    assert _foci("CLS024", _siblings(["BlackCat", "WhiteCat", "RedCat", "Dog"], "ex:A1")) == []
    foreign = _siblings(["BlackCat", "WhiteCat", "RedCat"]) + " <http://other.test/Dog> rdfs:subClassOf ex:Cat ."
    assert _foci("CLS024", foreign) == []


def test_cls024_known_gap_only_local_names_are_read() -> None:
    # Gap (convention): the labels are not read, and no plural is stemmed.
    labelled = _siblings(["BlackCat", "WhiteCat", "RedCat", "Dog"]).replace(
        "ex:Dog a owl:Class;", 'ex:Dog a owl:Class; rdfs:label "Dog Cat";'
    )
    assert _foci("CLS024", labelled) == ["Dog"]
    assert _foci("CLS024", _siblings(["BlackCat", "WhiteCats", "RedCat", "Dog"])) == []  # two outliers now


# --- CLS025: instance typed with a class and its ancestor (RDFS entailment rdfs9) --------------------------


def test_cls025_an_instance_typed_by_a_class_and_its_ancestor_fires() -> None:
    base = f"ex:A {C} . ex:B {C}; rdfs:subClassOf ex:A . "
    assert _foci("CLS025", base + "ex:i a ex:A, ex:B .") == ["i"]
    assert _messages("CLS025", base + "ex:i a ex:A, ex:B .") == ["Typed ex:B and its ancestor ex:A."]
    grand = base + f"ex:C {C}; rdfs:subClassOf ex:B . ex:i a ex:A, ex:C ."
    assert _messages("CLS025", grand) == ["Typed ex:C and its ancestor ex:A."]
    chain = base + f"ex:C {C}; rdfs:subClassOf ex:B . ex:i a ex:A, ex:B, ex:C ."
    assert len(_messages("CLS025", chain)) == 3  # one finding per (class, ancestor) pair


def test_cls025_exclusions() -> None:
    assert _foci("CLS025", f"ex:A {C} . ex:B {C} . ex:i a ex:A, ex:B .") == []
    assert _foci("CLS025", f"ex:A {C} . ex:B {C}; rdfs:subClassOf ex:A . ex:C {C}, ex:A, ex:B .") == []  # a class
    assert _foci("CLS025", f"ex:A {C} . ex:B {C}; rdfs:subClassOf ex:A . [] a ex:A, ex:B .") == []  # a blank node
    assert _foci("CLS025", f"ex:A {C} . ex:B {C}; rdfs:subClassOf ex:A . ex:i a ex:A .") == []


def test_cls025_known_gaps_pinned_as_they_are() -> None:
    # Gap (RDFS entailment rdfs9, rdfs11): an undeclared ancestor or middle class, an equivalent class and owl:Thing
    # are not followed.
    assert _foci("CLS025", f"ex:B {C}; rdfs:subClassOf ex:A . ex:i a ex:A, ex:B .") == []
    assert (
        _foci("CLS025", f"ex:A {C} . ex:B rdfs:subClassOf ex:A . ex:C {C}; rdfs:subClassOf ex:B . ex:i a ex:A, ex:C .")
        == []
    )
    assert _foci("CLS025", f"ex:A {C}; owl:equivalentClass ex:B . ex:B {C} . ex:i a ex:A, ex:B .") == []
    assert _foci("CLS025", f"ex:B {C}; rdfs:subClassOf owl:Thing . ex:i a owl:Thing, ex:B .") == []
    # Two classes of a cycle are each other's ancestor: both pairs are reported.
    cycle = f"ex:A {C}; rdfs:subClassOf ex:B . ex:B {C}; rdfs:subClassOf ex:A . ex:i a ex:A, ex:B ."
    assert len(_messages("CLS025", cycle)) == 2
