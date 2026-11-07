"""Targeted tests that pin behaviour the mutation run could leave unobserved (security hygiene rules)."""

from __future__ import annotations

from typing import Any

from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import RDF
from rule_cases.safety import bnode_chain, iri_graph, literal_graph, long_list
from rule_harness import BASE, graph

from ontolint import Linter
from ontolint.models import ExecutionStatus, Finding
from ontolint.rules import safety


def _run(rule: str, data: Graph, **options: Any) -> list[Finding]:
    result = Linter(data, None, **options).execute([rule])
    assert {x.status for x in result.executions} == {ExecutionStatus.EXECUTED}, result.executions
    return list(result.findings)


def _ex(name: str) -> URIRef:
    return URIRef(BASE + name)


# --- SEC004 ----------------------------------------------------------------------------------


def test_sec004_depth_message_and_focus_is_the_owning_iri() -> None:
    (finding,) = _run("SEC004", bnode_chain(101))
    assert finding.focus == str(_ex("a"))
    assert finding.message == "Blank-node structure is nested 101 levels deep (limit 100)."
    assert finding.severity == "warning"
    assert finding.confidence == "certain"
    assert _run("SEC004", bnode_chain(100)) == []


def test_sec004_depth_without_owner_focuses_the_blank_root() -> None:
    data = bnode_chain(101)
    root = next(iter(data.objects(_ex("a"), _ex("p"))))
    data.remove((_ex("a"), _ex("p"), root))
    (finding,) = _run("SEC004", data)
    assert finding.focus == str(root)


def test_sec004_depth_counts_non_rest_predicates_and_ignores_rest() -> None:
    data = Graph()
    previous: BNode = BNode()
    data.add((_ex("a"), _ex("p"), previous))
    for i in range(150):
        node = BNode()
        data.add((previous, RDF.rest if i % 2 else _ex("q"), node))
        previous = node
    assert _run("SEC004", data) == []


def test_sec004_depth_takes_the_longest_branch_and_survives_cycles_and_self_loops() -> None:
    data = bnode_chain(101)
    root = next(iter(data.objects(_ex("a"), _ex("p"))))
    short = BNode()
    data.add((root, _ex("q"), short))  # a shorter sibling branch must not lower the depth
    data.add((short, _ex("q"), short))
    second = next(iter(data.objects(root, _ex("p"))))
    data.add((short, _ex("q"), second))  # cycle-free join onto the main chain
    data.add((second, _ex("r"), short))  # cycle: short -> second -> short
    assert [f.message for f in _run("SEC004", data)] == ["Blank-node structure is nested 101 levels deep (limit 100)."]


def test_sec004_shared_deep_child_is_not_double_counted() -> None:
    data = bnode_chain(60)
    leaf = BNode()
    for node in set(data.objects()):
        data.add((node, _ex("q"), leaf))
    other = BNode()
    data.add((_ex("b"), _ex("p"), other))
    data.add((other, _ex("p"), next(iter(data.objects(_ex("a"), _ex("p"))))))
    assert _run("SEC004", data) == []


def test_sec004_list_message_and_focus() -> None:
    (finding,) = _run("SEC004", long_list(5001))
    assert finding.focus == str(_ex("a"))
    assert finding.message == "RDF list has 5001 members (limit 5000)."
    assert _run("SEC004", long_list(5000)) == []


def test_sec004_list_without_owner_and_cyclic_list() -> None:
    data = long_list(5001)
    head = next(iter(data.objects(_ex("a"), _ex("p"))))
    data.remove((_ex("a"), _ex("p"), head))
    assert [f.focus for f in _run("SEC004", data)] == [str(head)]
    cyclic = Graph()
    nodes = [BNode() for _ in range(5001)]
    for i, node in enumerate(nodes):
        cyclic.add((node, RDF.rest, nodes[(i + 1) % len(nodes)]))
    assert _run("SEC004", cyclic) == []


def test_sec004_list_stops_at_a_node_without_rest() -> None:
    data = long_list(5001)
    head = next(iter(data.objects(_ex("a"), _ex("p"))))
    nxt = next(iter(data.objects(head, RDF.rest)))
    data.remove((nxt, RDF.rest, None))
    assert _run("SEC004", data) == []


# --- SEC005 ----------------------------------------------------------------------------------


def test_sec005_message_focus_and_boundary() -> None:
    (finding,) = _run("SEC005", literal_graph("x" * 100_001))
    assert finding.focus == str(_ex("a"))
    assert finding.message == f"Literal on {_ex('p')} has 100001 characters (limit 100000)."
    assert finding.confidence == "certain"
    assert _run("SEC005", literal_graph("x" * 100_000)) == []


def test_sec005_ignores_iri_objects() -> None:
    assert _run("SEC005", iri_graph("https://example.test/" + "x" * 200_000)) == []


# --- SEC008 ----------------------------------------------------------------------------------


def test_sec008_every_unsafe_scheme_is_reported_once_per_iri() -> None:
    for scheme in sorted(safety.UNSAFE_SCHEMES):
        (finding,) = _run("SEC008", iri_graph(f"{scheme}:x"))
        assert finding.message == f"IRI uses the unsafe scheme {scheme}:."
        assert finding.focus == f"{scheme}:x"
    data = graph("ex:a <file:///x> <file:///x> . <file:///x> ex:p <file:///x> .")
    assert len(_run("SEC008", data)) == 1


def test_sec008_predicate_and_object_positions_and_scheme_case() -> None:
    data = graph("ex:a <file:///p> ex:b . ex:a ex:q <JavaScript:alert(1)> .")
    findings = _run("SEC008", data)
    assert {f.message for f in findings} == {
        "IRI uses the unsafe scheme file:.",
        "IRI uses the unsafe scheme javascript:.",
    }
    assert findings[0].severity == "warning"


def test_sec008_stripped_prefix_forms_and_safe_schemes() -> None:
    for iri in ("\x00javascript:x", "\x0bdata:x", "\x0cfile:x", "\rfile:x", "\nfile:x", "jav\r\nascript:x"):
        assert len(_run("SEC008", iri_graph(iri))) >= 1, repr(iri)
    for iri in ("x-file:y", "1file:y", "http://example.test/", "file", "afile:y"):
        assert _run("SEC008", iri_graph(iri)) == [], iri


# --- SEC012 ----------------------------------------------------------------------------------


def _hazard_codes(chars: str) -> list[str]:
    return [f.message for f in _run("SEC012", literal_graph(f"a{chars}b"))]


def test_sec012_literal_message_lists_sorted_unique_code_points() -> None:
    (finding,) = _run("SEC012", literal_graph("a\u202e\u0000\u202ez"))
    assert finding.focus == str(_ex("a"))
    assert finding.message == (
        f"Literal on {_ex('p')} contains control or bidirectional-override characters (U+0000, U+202E)."
    )
    assert finding.severity == "warning"


def test_sec012_literal_range_edges() -> None:
    flagged = [
        "\x00",
        "\x08",
        "\x0b",
        "\x0c",
        "\x0e",
        "\x1f",
        "\x7f",
        "\x80",
        "\x9f",
        "\u202a",
        "\u202e",
        "\u2066",
        "\u2069",
    ]
    for char in flagged:
        assert len(_hazard_codes(char)) == 1, hex(ord(char))
    clean = ["\t", "\n", "\r", " ", "\xa0", "\u2029", "\u202f", "\u2065", "\u206a", "\u200e", "\u200f", "\u061c"]
    for char in clean:
        assert _hazard_codes(char) == [], hex(ord(char))


def test_sec012_iri_range_edges_and_message() -> None:
    (finding,) = _run("SEC012", iri_graph(BASE + "a\u202e\tb"))
    assert finding.focus == BASE + "a\u202e\tb"
    assert finding.message == "IRI contains control or bidirectional-override characters (U+0009, U+202E)."
    for char in ("\x00", "\t", "\n", "\x1f", "\x7f", "\x9f", "\u202a", "\u202e", "\u2066", "\u2069"):
        assert len(_run("SEC012", iri_graph(BASE + char))) == 1, hex(ord(char))
    for char in ("\xa0", "\u2065", "\u206a", "\u2029", "\u200f"):
        assert _run("SEC012", iri_graph(BASE + char)) == [], hex(ord(char))


def test_sec012_literal_and_iri_hazards_are_independent() -> None:
    data = iri_graph(BASE + "\u202e")
    data.add((_ex("c"), _ex("p"), Literal("\u202e")))
    assert sorted(f.message.split()[0] for f in _run("SEC012", data)) == ["IRI", "Literal"]


# --- SEC014 ----------------------------------------------------------------------------------


def test_sec014_message_focus_and_no_password_echo() -> None:
    iri = "https://alice:s3cret@example.test/x"
    (finding,) = _run("SEC014", iri_graph(iri))
    assert finding.focus == iri
    assert finding.message == "IRI embeds a password for user 'alice'."
    assert "s3cret" not in finding.message
    assert finding.severity == "error"
    assert finding.confidence == "certain"


def test_sec014_both_operands_and_forms() -> None:
    for iri in ("https://:pw@h/", "x+y.z-1://u:p:q@h/", "HTTP://u:p@h"):
        assert len(_run("SEC014", iri_graph(iri))) == 1, iri
    for iri in (
        "https://u:@h/",
        "https://@h/",
        "https://:@h/",
        "https://u@h:80/",
        "https://h/p?q=u:p@h",
        "//u:p@h",
        "mailto:u:p@h",
    ):
        assert _run("SEC014", iri_graph(iri)) == [], iri
