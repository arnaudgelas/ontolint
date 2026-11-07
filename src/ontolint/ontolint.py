"""Ontology-quality linter. RDFLib does parsing; pySHACL is an optional validation backend.

Graph-local anti-pattern checks are not claims of OWL inconsistency.  No remote
URLs or owl:imports are fetched automatically. Python >=3.10.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import DC, DCTERMS, OWL, RDF, RDFS, SH, SKOS, XSD
from rdflib.term import Identifier, Node

# Codes and default severities are policy, not formal entailment judgments.
SEVERITY = {
    "ONT001": "warning",
    "ONT002": "warning",
    "ONT003": "warning",
    "ONT004": "info",
    "ONT005": "info",
    "ONT006": "warning",
    "IRI001": "warning",
    "IRI002": "warning",
    "IRI003": "info",
    "LEX001": "warning",
    "LEX002": "info",
    "LEX003": "warning",
    "LEX004": "warning",
    "LEX005": "warning",
    "LEX006": "info",
    "LEX007": "info",
    "LEX008": "info",
    "LEX009": "info",
    "CLS001": "info",
    "CLS002": "info",
    "CLS003": "warning",
    "CLS004": "info",
    "CLS005": "info",
    "CLS006": "info",
    "CLS007": "info",
    "CLS008": "info",
    "CLS009": "info",
    "OWL001": "warning",
    "OWL002": "warning",
    "OWL003": "error",
    "OWL004": "warning",
    "OWL005": "info",
    "OWL006": "info",
    "OWL007": "warning",
    "OWL008": "warning",
    "OWL009": "warning",
    "OWL010": "info",
    "OWL011": "info",
    "OWL012": "info",
    "OWL013": "warning",
    "OWL014": "warning",
    "OWL015": "warning",
    "SKOS001": "error",
    "SKOS002": "error",
    "SKOS003": "info",
    "SKOS004": "info",
    "SKOS005": "warning",
    "SKOS006": "info",
    "SHQ001": "info",
    "SHQ002": "info",
    "SHQ003": "info",
    "SHQ004": "info",
    "SHQ005": "warning",
    "SHQ006": "warning",
    "GOV001": "warning",
    "GOV002": "info",
    "GOV003": "warning",
    "DATA001": "warning",
    "DATA002": "warning",
    "SHACL001": "error",
    "INPUT001": "error",
    "TOOL001": "error",
    "SEM001": "error",
}

FIXES = {
    "ONT001": "Declare a stable ontology IRI using rdf:type owl:Ontology.",
    "ONT002": "Prefer one primary owl:Ontology declaration per standalone ontology document.",
    "ONT003": "Add dcterms:license (or an agreed equivalent) to the ontology.",
    "ONT004": "Add owl:versionIRI or owl:versionInfo according to your release policy.",
    "ONT005": "Add creator and creation date provenance (e.g. dcterms:creator and dcterms:created).",
    "ONT006": "Describe the ontology with dcterms:description or rdfs:comment.",
    "IRI001": "Use stable absolute IRIs; avoid whitespace in identifiers.",
    "IRI002": "Consider an extension-independent ontology identifier (policy-dependent).",
    "IRI003": "Check whether duplicate local identifiers across namespaces confuse users.",
    "LEX001": "Add rdfs:label or an accepted alternative to the declared local term.",
    "LEX002": "Add a natural-language definition (rdfs:comment, skos:definition, or dcterms:description).",
    "LEX003": "Use one language-specific primary label per term and language.",
    "LEX004": "Differentiate labels or formally document and link genuinely equivalent concepts.",
    "LEX005": "Trim whitespace or replace empty labels.",
    "LEX006": "Use a consistent label language-tag policy.",
    "LEX007": "Use one configured naming convention for comparable term identifiers.",
    "LEX008": "Add the required preferred language label.",
    "LEX009": "Review capitalization and wording relative to the namespace policy.",
    "CLS001": "Inspect whether the disconnected class is intentional (e.g., a top-level class).",
    "CLS002": "Check whether this class is intentionally uninstantiated, abstract, or imported.",
    "CLS003": "Review the asserted subclass cycle; an OWL subclass cycle is not by itself inconsistent.",
    "CLS004": "Remove a redundant asserted subclass axiom if it adds no documentation value.",
    "CLS005": "Review unusually deep asserted hierarchy and possible re-modeling.",
    "CLS006": "Review the intended meaning of multiple direct superclasses.",
    "CLS007": "Check long single-child taxonomic chains for needless subdivisions.",
    "CLS008": "Consider splitting classes or using property groups/shapes where appropriate.",
    "CLS009": "Check whether class equivalence is purposeful and not merely a duplicate name.",
    "OWL001": "Explicitly declare local classes used in class axioms.",
    "OWL002": "Explicitly declare local properties used in schema axioms.",
    "OWL003": "Do not simultaneously declare a property as both owl:ObjectProperty and owl:DatatypeProperty.",
    "OWL004": "Review conjunction semantics of multiple rdfs:domain/rdfs:range; use owl:unionOf if intended.",
    "OWL005": "Consider declaring domain or explaining why a global domain is inappropriate.",
    "OWL006": "Consider declaring range or explaining why a global range is inappropriate.",
    "OWL007": "Replace self-inverse modeling with owl:SymmetricProperty when this is intentional.",
    "OWL008": "Review redundant or unintended inverse axioms on symmetric properties.",
    "OWL009": "Use object properties for owl:inverseOf and symmetric/transitive property semantics.",
    "OWL010": "Review an owl:propertyChainAxiom whose RDF list has only one element.",
    "OWL011": "Check intended allValuesFrom semantics; it does not imply existence of a value.",
    "OWL012": "Review the use of owl:equivalentClass on the class itself.",
    "OWL013": "An object-property assertion should point to a resource, not a literal.",
    "OWL014": "A datatype-property assertion should point to a literal.",
    "OWL015": "Declare a local predicate as a property (or exclude it from schema-only policy).",
    "SKOS001": "Keep only one skos:prefLabel per language tag for a given resource.",
    "SKOS002": "Do not reuse the same literal across prefLabel, altLabel and hiddenLabel of one resource.",
    "SKOS003": "Inspect hierarchical cycles; SKOS does not universally prohibit them.",
    "SKOS004": "Give a concept a preferred label in your supported language(s).",
    "SKOS005": "Use skos:Concept with skos:inScheme and an appropriate scheme policy.",
    "SKOS006": "Review whether a scheme top concept should also have a broader concept.",
    "SHQ001": "Add sh:name to property shapes to support generated forms and documentation.",
    "SHQ002": "Add sh:description to non-trivial property shapes.",
    "SHQ003": "Add sh:message to constraint-bearing shapes for better diagnostics.",
    "SHQ004": "Add label and comment to published node shapes.",
    "SHQ005": "Use one annotation per language for each SHACL name/description/message.",
    "SHQ006": "Add a shape targeting this class, or exempt it from data-quality validation.",
    "GOV001": "Migrate non-annotation references to deprecated terms or justify them.",
    "GOV002": "Pin or resolve imported ontology versions in an explicit import manifest.",
    "GOV003": "Review references to local undeclared vocabulary terms.",
    "DATA001": "Check a property assertion for range/type confusion.",
    "DATA002": "Check a property assertion for datatype/object-property confusion.",
    "SHACL001": "Fix the supplied SHACL shapes or data, and inspect the SHACL report.",
    "INPUT001": "Fix RDF syntax or explicitly choose the input serialization format.",
    "TOOL001": "Correct the configuration or execution error and run the linter again.",
    "SEM001": "Correct the reported OWL profile violations, or select the intended OWL profile.",
}

KINDS = (
    OWL.Class,
    RDFS.Class,
    OWL.ObjectProperty,
    OWL.DatatypeProperty,
    OWL.AnnotationProperty,
    RDF.Property,
    SKOS.Concept,
    SKOS.ConceptScheme,
    SKOS.Collection,
    OWL.NamedIndividual,
)
CLASSES = (OWL.Class, RDFS.Class)
PROPERTIES = (OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty, RDF.Property)
DESCRIPTIONS = (RDFS.comment, SKOS.definition, DCTERMS.description, DC.description)
LABELS = (RDFS.label, SKOS.prefLabel)
META_LICENSE = (DCTERMS.license, URIRef("http://creativecommons.org/ns#license"))
META_CREATOR = (DCTERMS.creator, DC.creator, URIRef("http://www.w3.org/ns/prov#wasAttributedTo"))
MINIMUM_STYLE_SAMPLE_SIZE = 4
MINIMUM_SINGLE_CHILD_CHAIN_LENGTH = 3


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    focus: str
    message: str
    suggestion: str
    confidence: str = "heuristic"

    def to_dict(self):
        return asdict(self)


class Linter:
    def __init__(  # noqa: PLR0913 -- policy thresholds are independently configurable.
        self,
        graph: Graph,
        shapes: Graph | None = None,
        *,
        base: str | None = None,
        languages: tuple[str, ...] = (),
        depth_limit: int = 7,
        inheritance_limit: int = 3,
        soup_limit: int = 15,
    ):
        self.g = graph
        self.shapes = shapes
        self.base = base
        self.languages = tuple(x.lower() for x in languages)
        self.depth_limit = depth_limit
        self.inheritance_limit = inheritance_limit
        self.soup_limit = soup_limit
        self.issues: list[Finding] = []
        self.seen: set[tuple[str, str, str]] = set()
        self.ontologies = {s for s in graph.subjects(RDF.type, OWL.Ontology) if isinstance(s, URIRef)}
        self.classes = {s for t in CLASSES for s in graph.subjects(RDF.type, t) if isinstance(s, URIRef)}
        self.properties = {s for t in PROPERTIES for s in graph.subjects(RDF.type, t) if isinstance(s, URIRef)}
        self.concepts = {s for s in graph.subjects(RDF.type, SKOS.Concept) if isinstance(s, URIRef)}
        self.terms = {s for t in KINDS for s in graph.subjects(RDF.type, t) if isinstance(s, URIRef)}
        # Explicitly declared terms are considered local unless a base is given.
        # This deliberately does not fetch owl:imports or define external vocabulary terms.
        if base:
            self.terms = {s for s in self.terms if self.local(s)}
            self.classes = {s for s in self.classes if self.local(s)}
            self.properties = {s for s in self.properties if self.local(s)}
            self.concepts = {s for s in self.concepts if self.local(s)}

    def local(self, node: object) -> bool:
        if not isinstance(node, URIRef):
            return False
        if not self.base:
            return True
        iri = str(node)
        b = self.base
        return iri.startswith(b) if b.endswith(("#", "/")) else (iri == b or iri.startswith((b + "#", b + "/")))

    def add(self, code: str, focus: object, message: str, *, confidence: str = "heuristic") -> None:
        k = (code, str(focus), message)
        if k not in self.seen:
            self.seen.add(k)
            self.issues.append(Finding(code, SEVERITY[code], str(focus), message, FIXES[code], confidence))

    def run(self):
        self.metadata()
        self.identifiers()
        self.lexical()
        self.classes_checks()
        self.owl_checks()
        self.skos_checks()
        self.shapes_checks()
        self.governance()
        return sorted(
            self.issues, key=lambda x: (["error", "warning", "info"].index(x.severity), x.rule, x.focus, x.message)
        )

    def metadata(self):
        if not self.ontologies:
            self.add("ONT001", "(ontology)", "Missing owl:Ontology declaration.", confidence="certain")
        if len(self.ontologies) > 1:
            self.add("ONT002", "(ontology)", f"{len(self.ontologies)} owl:Ontology declarations found.")
        for ont in sorted(self.ontologies, key=str):
            if not any((ont, p, None) in self.g for p in META_LICENSE):
                self.add("ONT003", ont, "Ontology has no license annotation.", confidence="certain")
            if not any((ont, p, None) in self.g for p in (OWL.versionIRI, OWL.versionInfo)):
                self.add("ONT004", ont, "No versionIRI/versionInfo.")
            if not any((ont, p, None) in self.g for p in META_CREATOR) or (ont, DCTERMS.created, None) not in self.g:
                self.add("ONT005", ont, "Missing creator or dcterms:created provenance.")
            if not any((ont, p, None) in self.g for p in DESCRIPTIONS):
                self.add("ONT006", ont, "Missing ontology description.")

    @staticmethod
    def local_name(iri: URIRef) -> str:
        s = str(iri)
        return re.split(r"[/#]", s)[-1]

    def identifiers(self):
        all_ids = self.terms | self.ontologies
        names = defaultdict(set)
        for u in all_ids:
            s = str(u)
            pieces = urlsplit(s)
            if " " in s or "\t" in s or "\n" in s or not pieces.scheme:
                self.add("IRI001", u, "IRI contains whitespace or is not absolute.", confidence="certain")
            if u in self.ontologies and re.search(r"\.(owl|ttl|n3|rdf|rdfxml)$", pieces.path, flags=re.I):
                self.add("IRI002", u, "Ontology IRI contains a serialization file extension.")
            if u in self.terms:
                names[self.local_name(u).casefold()].add(u)
        for _name, iris in names.items():
            # The set cannot contain two distinct IRIs with the same complete
            # namespace/local-name split, so cardinality alone is sufficient.
            if len(iris) > 1:
                self.add(
                    "IRI003",
                    sorted(map(str, iris))[0],
                    "Local-name collision across IRIs: " + ", ".join(sorted(map(str, iris))[:5]),
                )

    def lexical(self):  # noqa: C901, PLR0912 -- cohesive lexical-policy pass.
        label_index = defaultdict(set)
        for term in sorted(self.terms, key=str):
            labels = {o for p in LABELS for o in self.g.objects(term, p) if isinstance(o, Literal)}
            if not labels and (term, OWL.deprecated, Literal(True)) not in self.g:
                self.add("LEX001", term, "Term has no label.", confidence="certain")
            if not any((term, p, None) in self.g for p in DESCRIPTIONS):
                self.add("LEX002", term, "Term has no description or definition.", confidence="certain")
            by_language = defaultdict(list)
            for o in labels:
                language = (o.language or "und").lower()
                by_language[language].append(o)
                if not str(o).strip() or str(o) != str(o).strip():
                    self.add("LEX005", term, f"Blank or padded label: {str(o)!r}.", confidence="certain")
                label_index[(str(o).casefold().strip(), language)].add(term)
            for lang, literals in by_language.items():
                if len(literals) > 1:
                    self.add("LEX003", term, f"{len(literals)} labels for language {lang}.")
            if len(by_language) > 1 and "und" in by_language:
                self.add("LEX006", term, "Mixed plain and language-tagged preferred labels.")
            for lang in self.languages:
                if lang not in by_language:
                    self.add("LEX008", term, f"Missing preferred label in language {lang}.")
        for (duplicate_label, lang), terms in label_index.items():
            if duplicate_label and len(terms) > 1:
                self.add(
                    "LEX004",
                    sorted(terms, key=str)[0],
                    f"Duplicate label {duplicate_label!r}@{lang} for "
                    + ", ".join(map(str, sorted(terms, key=str)[:5])),
                )
        # Conventional capitalization is only a review hint, not a semantic rule.
        for term in self.classes | self.properties:
            label: Literal | None = next((x for x in self.g.objects(term, RDFS.label) if isinstance(x, Literal)), None)
            if label and str(label) and str(label)[0].isalpha():
                if term in self.classes and str(label)[0].islower():
                    self.add("LEX009", term, "Class label begins with lower case (style review).")
                if term in self.properties and str(label)[0].isupper():
                    self.add("LEX009", term, "Property label begins with upper case (style review).")
        # Naming is a configurable, non-blocking quality indicator.
        local_names = [self.local_name(x) for x in self.terms]
        styles = Counter(
            "underscore" if "_" in n else "hyphen" if "-" in n else "camel" if re.search(r"[a-z][A-Z]", n) else "other"
            for n in local_names
        )
        meaningful = [(style, count) for style, count in styles.items() if style != "other" and count > 0]
        if len(meaningful) > 1 and len(self.terms) >= MINIMUM_STYLE_SAMPLE_SIZE:
            self.add("LEX007", "(vocabulary)", f"Mixed identifier styles: {dict(styles)}.")

    @staticmethod
    def directed_edges(g: Graph, predicate: Identifier, allowed: set[URIRef]) -> set[tuple[URIRef, URIRef]]:
        return {
            (cast("URIRef", s), cast("URIRef", o))
            for s, o in g.subject_objects(predicate)
            if s in allowed and o in allowed
        }

    @staticmethod
    def components(  # noqa: C901 -- Tarjan's algorithm is intentionally single-pass.
        nodes: Iterable[URIRef], edges: Iterable[tuple[URIRef, URIRef]]
    ) -> list[set[URIRef]]:
        """Tarjan strongly-connected components, no third-party dependency."""
        adj = defaultdict(set)
        for s, o in edges:
            adj[s].add(o)
        visited, low, stack, onstack, i, out = {}, {}, [], set(), 0, []

        def dfs(node: URIRef) -> None:
            nonlocal i
            visited[node] = low[node] = i
            i += 1
            stack.append(node)
            onstack.add(node)
            for nxt in adj[node]:
                if nxt not in visited:
                    dfs(nxt)
                    low[node] = min(low[node], low[nxt])
                elif nxt in onstack:
                    low[node] = min(low[node], visited[nxt])
            if low[node] == visited[node]:
                comp = set()
                while stack:
                    nxt = stack.pop()
                    onstack.remove(nxt)
                    comp.add(nxt)
                    if nxt == node:
                        break
                out.append(comp)

        for n in nodes:
            if n not in visited:
                dfs(n)
        return out

    @staticmethod
    def reachable(
        adj: Mapping[URIRef, set[URIRef]],
        source: URIRef,
        target: URIRef,
        *,
        ignore: tuple[URIRef, URIRef] | None = None,
    ) -> bool:
        seen, q = {source}, deque([source])
        while q:
            node = q.popleft()
            for nxt in adj.get(node, ()):
                if (node, nxt) == ignore:
                    continue
                if nxt == target:
                    return True
                if nxt not in seen:
                    seen.add(nxt)
                    q.append(nxt)
        return False

    def classes_checks(self):  # noqa: C901, PLR0912 -- cohesive class-policy pass.
        classes = self.classes
        edges = self.directed_edges(self.g, RDFS.subClassOf, classes)
        supers, children = defaultdict(set), defaultdict(set)
        for child, parent in edges:
            supers[child].add(parent)
            children[parent].add(child)
        # Orphan = no asserted local class-to-class hierarchy, not no semantic links.
        for c in classes:
            if not supers[c] and not children[c] and (c, RDFS.subClassOf, OWL.Thing) not in self.g:
                self.add("CLS001", c, "No asserted local super-/subclass links.")
            has_instance = any(True for _ in self.g.subjects(RDF.type, c))
            if not has_instance and not children[c]:
                self.add("CLS002", c, "Class has no directly typed instance or subclass in this graph.")
            if len(supers[c]) > self.inheritance_limit:
                self.add("CLS006", c, f"{len(supers[c])} direct superclasses (threshold {self.inheritance_limit}).")
            direct_properties = {p for p in self.g.subjects(RDFS.domain, c) if isinstance(p, URIRef)}
            if len(direct_properties) > self.soup_limit:
                self.add("CLS008", c, f"{len(direct_properties)} properties with asserted domain {c}.")
        for component in self.components(classes, edges):
            if len(component) > 1 or any((c, c) in edges for c in component):
                representative = sorted(component, key=str)[0]
                self.add(
                    "CLS003",
                    representative,
                    "Asserted subclass cycle: " + ", ".join(str(n) for n in sorted(component, key=str)),
                    confidence="certain",
                )
        for c, parent in edges:
            if self.reachable(supers, c, parent, ignore=(c, parent)):
                self.add(
                    "CLS004", c, f"Asserted subclass edge to {parent} is transitively redundant.", confidence="certain"
                )
        # Maximum simple path length in class DAG: strongly connected cycles excluded.
        cyclic = {n for comp in self.components(classes, edges) if len(comp) > 1 for n in comp}
        memo: dict[URIRef, int] = {}
        processing: set[URIRef] = set()

        def depth(c: URIRef) -> int:
            if c in memo:
                return memo[c]
            if c in processing or c in cyclic:
                return 0
            processing.add(c)
            result = 1 + max((depth(x) for x in children[c] if x != c), default=0)
            processing.remove(c)
            memo[c] = result
            return result

        for c in classes:
            if c not in cyclic and depth(c) > self.depth_limit:
                self.add("CLS005", c, f"Asserted subtree depth {depth(c)} exceeds {self.depth_limit}.")
        for c in classes:
            length, n, seen = 0, c, set[URIRef]()
            while len(children[n]) == 1 and n not in seen:
                seen.add(n)
                n = next(iter(children[n]))
                length += 1
            if length >= MINIMUM_SINGLE_CHILD_CHAIN_LENGTH:
                self.add("CLS007", c, f"Single-child hierarchy extends {length} edges below class.")
        for left, right in self.g.subject_objects(OWL.equivalentClass):
            if left in classes and left == right:
                self.add("OWL012", left, "Class is explicitly equivalent to itself.")
            elif left in classes and right in classes:
                ls = {str(x).casefold() for x in self.g.objects(left, RDFS.label)}
                rs = {str(x).casefold() for x in self.g.objects(right, RDFS.label)}
                if ls and (ls & rs):
                    self.add("CLS009", left, f"Equivalent class {right} has an identical label (review duplication).")

    @staticmethod
    def list_items(g: Graph, head: Node, *, limit: int = 500) -> list[Node] | None:
        items: list[Node] = []
        seen: set[Node] = set()
        while head != RDF.nil and head not in seen and len(items) < limit:
            seen.add(head)
            firsts, rests = list(g.objects(head, RDF.first)), list(g.objects(head, RDF.rest))
            if len(firsts) != 1 or len(rests) != 1:
                return None  # Invalid lists are Meta-SHACL / OWL structural checks.
            items.append(firsts[0])
            head = rests[0]
        return items if head == RDF.nil else None

    def owl_checks(self):  # noqa: C901, PLR0912 -- cohesive OWL-policy pass.
        object_props = set(self.g.subjects(RDF.type, OWL.ObjectProperty))
        data_props = set(self.g.subjects(RDF.type, OWL.DatatypeProperty))
        for p in object_props & data_props:
            self.add("OWL003", p, "Property is typed as both object and datatype property.", confidence="certain")
        for p in self.properties:
            domains, ranges = set(self.g.objects(p, RDFS.domain)), set(self.g.objects(p, RDFS.range))
            if len(domains) > 1:
                self.add(
                    "OWL004",
                    p,
                    f"Multiple asserted domains ({len(domains)}) mean intersection, not union.",
                    confidence="certain",
                )
            if len(ranges) > 1:
                self.add(
                    "OWL004",
                    p,
                    f"Multiple asserted ranges ({len(ranges)}) mean intersection, not union.",
                    confidence="certain",
                )
            if not domains:
                self.add("OWL005", p, "Property has no asserted rdfs:domain.")
            if not ranges:
                self.add("OWL006", p, "Property has no asserted rdfs:range.")
        for p, q in self.g.subject_objects(OWL.inverseOf):
            if p == q:
                self.add("OWL007", p, "Property declared inverse of itself.", confidence="certain")
            if p != q and (p, RDF.type, OWL.SymmetricProperty) in self.g:
                self.add("OWL008", p, f"Symmetric property also declared inverse of {q}.")
            if p in data_props or q in data_props:
                self.add("OWL009", p, "owl:inverseOf involves a datatype property.", confidence="certain")
        for t in (OWL.SymmetricProperty, OWL.TransitiveProperty, OWL.AsymmetricProperty, OWL.InverseFunctionalProperty):
            for p in self.g.subjects(RDF.type, t):
                if p in data_props:
                    self.add("OWL009", p, f"Datatype property declared {t}.", confidence="certain")
        for p, chain in self.g.subject_objects(OWL.propertyChainAxiom):
            items = self.list_items(self.g, chain)
            if items is not None and len(items) == 1:
                self.add("OWL010", p, "Property-chain axiom has one operand.", confidence="certain")
        for restriction in self.g.subjects(OWL.allValuesFrom, None):
            # allValuesFrom alone is fully valid OWL. Review only.
            if (restriction, OWL.someValuesFrom, None) not in self.g:
                self.add("OWL011", restriction, "Universal restriction does not imply any property value.")
        for p in object_props:
            for s, o in self.g.subject_objects(p):
                if isinstance(o, Literal):
                    self.add("OWL013", s, f"Object property {p} points to literal {o!r}.", confidence="certain")
        for p in data_props:
            expected = set(self.g.objects(p, RDFS.range))
            for s, o in self.g.subject_objects(p):
                if not isinstance(o, Literal):
                    self.add("OWL014", s, f"Datatype property {p} points to resource {o}.", confidence="certain")
                elif len(expected) == 1:
                    datatype = next(iter(expected))
                    if (
                        str(datatype).startswith(str(XSD))
                        and o.datatype != datatype
                        and not (datatype == XSD.string and o.datatype is None)
                    ):
                        self.add("DATA001", s, f"{p} has range {datatype} but value has datatype {o.datatype}.")
        for p in self.properties:
            for domain in self.g.objects(p, RDFS.domain):
                for s in self.g.subjects(p, None):
                    for actual in self.g.objects(s, RDF.type):
                        if (actual, OWL.disjointWith, domain) in self.g or (domain, OWL.disjointWith, actual) in self.g:
                            self.add(
                                "DATA002",
                                s,
                                f"Usage of {p} infers {domain} but subject is explicitly typed {actual}, "
                                "declared disjoint.",
                            )
        for p in self.g.subjects(RDFS.domain, None):
            if isinstance(p, URIRef) and self.local(p) and not any((p, RDF.type, t) in self.g for t in PROPERTIES):
                self.add("OWL002", p, "Predicate used with rdfs:domain but not declared property.")
        for p in self.g.subjects(RDFS.range, None):
            if isinstance(p, URIRef) and self.local(p) and not any((p, RDF.type, t) in self.g for t in PROPERTIES):
                self.add("OWL002", p, "Predicate used with rdfs:range but not declared property.")
        for c in set(self.g.subjects(RDFS.subClassOf, None)) | set(self.g.objects(None, RDFS.subClassOf)):
            if isinstance(c, URIRef) and self.local(c) and c not in self.classes and c not in (OWL.Thing, OWL.Nothing):
                self.add("OWL001", c, "URI used in subclass axiom but not explicitly declared a class.")
        # Treat undeclared predicates as suspicious only within explicit base namespaces.
        if self.base:
            for p in set(self.g.predicates()):
                if self.local(p) and p not in self.properties:
                    self.add("OWL015", p, "Local predicate is not explicitly declared as a property.")

    def skos_checks(self):  # noqa: C901, PLR0912 -- cohesive SKOS-policy pass.
        concepts = self.concepts
        for c in concepts:
            by_lang = defaultdict(list)
            for label in self.g.objects(c, SKOS.prefLabel):
                if isinstance(label, Literal):
                    by_lang[label.language or "und"].append(label)
            for language, labels in by_lang.items():
                if len(labels) > 1:
                    self.add("SKOS001", c, f"{len(labels)} prefLabels in language {language}.", confidence="certain")
            if not by_lang:
                self.add("SKOS004", c, "Concept has no skos:prefLabel.")
            if (c, SKOS.inScheme, None) not in self.g:
                self.add("SKOS005", c, "Concept is not explicitly in a scheme.")
        labelled_resources: set[Node] = set(concepts) | set(self.g.subjects(SKOS.prefLabel, None))
        for resource in labelled_resources:
            sets = [set(self.g.objects(resource, p)) for p in (SKOS.prefLabel, SKOS.altLabel, SKOS.hiddenLabel)]
            if (sets[0] & sets[1]) or (sets[0] & sets[2]) or (sets[1] & sets[2]):
                self.add(
                    "SKOS002",
                    resource,
                    "Same literal appears in multiple disjoint SKOS label properties.",
                    confidence="certain",
                )
        broader_edges = self.directed_edges(self.g, SKOS.broader, concepts)
        for component in self.components(concepts, broader_edges):
            if len(component) > 1 or any((c, c) in broader_edges for c in component):
                self.add(
                    "SKOS003",
                    sorted(component, key=str)[0],
                    "SKOS broader cycle: " + ", ".join(map(str, sorted(component, key=str))),
                )
        for concept, scheme in self.g.subject_objects(SKOS.topConceptOf):
            if (concept, SKOS.broader, None) in self.g:
                self.add("SKOS006", concept, f"Top concept of {scheme} also has an asserted broader concept.")

    def shapes_checks(self):  # noqa: C901 -- cohesive SHACL-quality pass.
        sg = self.shapes
        if sg is None:
            return
        node_shapes = set(sg.subjects(RDF.type, SH.NodeShape))
        property_shapes = set(sg.subjects(RDF.type, SH.PropertyShape)) | set(sg.objects(None, SH.property))
        for shape in node_shapes:
            if (shape, RDFS.label, None) not in sg or (shape, RDFS.comment, None) not in sg:
                self.add("SHQ004", shape, "Node shape lacks rdfs:label or rdfs:comment.")
        for shape in property_shapes:
            if (shape, SH.name, None) not in sg:
                self.add("SHQ001", shape, "Property shape lacks sh:name.")
            if (shape, SH.description, None) not in sg:
                self.add("SHQ002", shape, "Property shape lacks sh:description.")
        for shape in node_shapes | property_shapes:
            has_constraint = any(
                p
                in (
                    SH.minCount,
                    SH.maxCount,
                    SH.datatype,
                    SH["class"],
                    SH.pattern,
                    SH["in"],
                    SH.node,
                    SH["not"],
                    SH.sparql,
                )
                for p in sg.predicates(shape, None)
            )
            if has_constraint and (shape, SH.message, None) not in sg:
                self.add("SHQ003", shape, "Constraint-bearing shape lacks sh:message.")
            for p in (SH.name, SH.description, SH.message):
                counts = Counter((o.language or "und").lower() for o in sg.objects(shape, p) if isinstance(o, Literal))
                if any(n > 1 for n in counts.values()):
                    self.add("SHQ005", shape, f"Multiple {p} values in the same language.")
        targeted = set(sg.objects(None, SH.targetClass))
        targeted |= {s for s in sg.subjects(RDF.type, RDFS.Class) if s in node_shapes}
        targeted |= {s for s in sg.subjects(RDF.type, OWL.Class) if s in node_shapes}
        for c in self.classes:
            if any(True for _ in self.g.subjects(RDF.type, c)) and c not in targeted:
                self.add(
                    "SHQ006",
                    c,
                    "Class has directly typed instances, but no direct sh:targetClass or implicit class target.",
                )

    def governance(self):
        deprecated = set(self.g.subjects(OWL.deprecated, Literal(True)))
        for term in deprecated:
            for s, p in self.g.subject_predicates(term):
                if p not in (RDFS.label, RDFS.comment, OWL.deprecated, DCTERMS.description, OWL.deprecated):
                    self.add("GOV001", s, f"Deprecated term {term} appears as object of {p}.")
            for s, _o in self.g.subject_objects(term):
                self.add("GOV001", s, f"Deprecated property {term} used in assertion.")
        for c in set(self.g.objects(None, OWL.equivalentClass)) | set(self.g.subjects(OWL.equivalentClass, None)):
            if isinstance(c, URIRef) and self.local(c) and c not in self.classes:
                self.add("GOV003", c, "Local URI used in owl:equivalentClass but not declared a class.")
        for ont in self.ontologies:
            imports = set(self.g.objects(ont, OWL.imports))
            for imported in imports:
                if not isinstance(imported, URIRef):
                    self.add("GOV002", ont, f"Non-IRI import target: {imported}.")


def _shacl_issues(g: Graph, sg: Graph):
    try:
        from pyshacl import validate  # noqa: PLC0415 -- optional dependency, required only with --shapes.
    except ImportError:
        raise RuntimeError("pySHACL is needed for --shapes: pip install pyshacl") from None
    conforms, report, _ = validate(
        g, shacl_graph=sg, inference="none", advanced=True, meta_shacl=True, abort_on_first=False
    )
    if conforms:
        return []
    if not isinstance(report, Graph):
        raise RuntimeError(f"pySHACL returned an unexpected report type: {type(report).__name__}")
    results = []
    for result in report.subjects(RDF.type, SH.ValidationResult):
        focus = str(next(report.objects(result, SH.focusNode), "(unknown)"))
        message = "; ".join(map(str, report.objects(result, SH.resultMessage))) or "SHACL constraint violation"
        src = str(next(report.objects(result, SH.sourceShape), "(unknown)"))
        results.append(Finding("SHACL001", "error", focus, f"{message} [shape: {src}]", FIXES["SHACL001"], "certain"))
    if not results:
        results.append(
            Finding(
                "SHACL001",
                "error",
                "(shapes)",
                "SHACL returned nonconformant without individual result nodes.",
                FIXES["SHACL001"],
                "certain",
            )
        )
    return results


def fingerprint(f: Finding):
    payload = json.dumps([f.rule, f.focus, f.message], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sarif(findings: list[Finding]):
    rules = {f.rule: {"id": f.rule, "shortDescription": {"text": f.rule}} for f in findings}
    return {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [
            {
                "tool": {"driver": {"name": "ontolint", "rules": list(rules.values())}},
                "results": [
                    {
                        "ruleId": f.rule,
                        "level": {"error": "error", "warning": "warning", "info": "note"}[f.severity],
                        "message": {"text": f"{f.message} Focus: {f.focus}. Suggestion: {f.suggestion}"},
                    }
                    for f in findings
                ],
            }
        ],
    }


def _robot_profile_issues(ontology: Path, profile: str, image: str, timeout: int) -> list[Finding]:
    """Run ROBOT profile validation in an isolated Docker container.

    The ontology's parent directory is mounted read-only and the container has no
    network access. Use a digest-pinned ``image`` in CI for reproducibility.
    """
    source = ontology.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    with tempfile.TemporaryDirectory(prefix="ontolint-robot-") as output_dir:
        output = Path(output_dir)
        report = output / "profile.txt"
        command = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--memory",
            "2g",
            "--pids-limit",
            "256",
            "--cpus",
            "2",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "-v",
            f"{source.parent}:/input:ro",
            "-v",
            f"{output}:/output",
            "-w",
            "/output",
            image,
            "validate-profile",
            "--profile",
            profile,
            "--input",
            f"/input/{source.name}",
            "--output",
            "/output/profile.txt",
        ]
        completed = subprocess.run(  # noqa: S603 -- fixed Docker executable and constructed argument list.
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
        if completed.returncode == 0:
            return []
        details = report.read_text(encoding="utf-8", errors="replace").strip() if report.exists() else ""
        details = details or completed.stderr.strip() or completed.stdout.strip() or "ROBOT did not produce a report."
        return [
            Finding(
                "SEM001",
                SEVERITY["SEM001"],
                str(source),
                f"ROBOT OWL {profile} profile validation failed: {details[:4000]}",
                FIXES["SEM001"],
                "certain",
            )
        ]


def main(  # noqa: C901, PLR0915 -- CLI parsing and execution are intentionally colocated.
    argv: Sequence[str] | None = None,
) -> int:
    ap = argparse.ArgumentParser(description="Ontology anti-pattern linter. No automatic network/import access.")
    ap.add_argument("ontology", help="Ontology RDF file (Turtle, RDF/XML, JSON-LD, etc.)")
    ap.add_argument("--shapes", help="Optional SHACL shapes graph (requires pyshacl)")
    ap.add_argument("--base", help="Only lint declared terms in this namespace")
    ap.add_argument("--config", help="Optional JSON policy with ignored_rules, severity_overrides and thresholds")
    ap.add_argument("--baseline", help="JSON of fingerprints to exclude from displayed and gating findings")
    ap.add_argument("--write-baseline", help="Write full set of fingerprints for future differential linting")
    ap.add_argument("--language", action="append", default=[], help="Required label language; repeatable")
    ap.add_argument("--depth-limit", type=int)
    ap.add_argument("--inheritance-limit", type=int)
    ap.add_argument("--soup-limit", type=int)
    ap.add_argument("--owl-profile", choices=("EL", "QL", "RL", "DL", "Full"))
    ap.add_argument("--robot-image", default="ontolint-robot:1.9.11")
    ap.add_argument("--robot-timeout", type=int, default=120)
    ap.add_argument("--format", choices=["text", "json", "sarif"], default="text")
    ap.add_argument("--output", help="Output file (default stdout)")
    ap.add_argument("--fail-on", choices=["error", "warning", "info", "never"], default="error")
    args = ap.parse_args(argv)
    g = Graph()
    stage = "configuration"
    try:
        config = json.loads(Path(args.config).read_text(encoding="utf-8")) if args.config else {}
        stage = "RDF input parsing"
        g.parse(args.ontology)
        sg = Graph().parse(args.shapes) if args.shapes else None
        stage = "lint execution"
        lint = Linter(
            g,
            sg,
            base=args.base or config.get("base"),
            languages=tuple(args.language or config.get("languages", [])),
            depth_limit=args.depth_limit if args.depth_limit is not None else config.get("depth_limit", 7),
            inheritance_limit=args.inheritance_limit
            if args.inheritance_limit is not None
            else config.get("inheritance_limit", 3),
            soup_limit=args.soup_limit if args.soup_limit is not None else config.get("soup_limit", 15),
        )
        issues = lint.run()
        if sg is not None:
            issues += _shacl_issues(g, sg)
        if args.owl_profile:
            issues += _robot_profile_issues(Path(args.ontology), args.owl_profile, args.robot_image, args.robot_timeout)
        ignored = set(config.get("ignored_rules", []))
        changes = config.get("severity_overrides", {})
        if any(level not in ("error", "warning", "info") for level in changes.values()):
            raise ValueError("severity_overrides must be error, warning or info")
        issues = [replace(f, severity=changes.get(f.rule, f.severity)) for f in issues if f.rule not in ignored]
        if args.write_baseline:
            Path(args.write_baseline).write_text(
                json.dumps({"fingerprints": sorted({fingerprint(f) for f in issues})}, indent=2) + "\n",
                encoding="utf-8",
            )
        if args.baseline:
            prior = set(json.loads(Path(args.baseline).read_text(encoding="utf-8")).get("fingerprints", []))
            issues = [f for f in issues if fingerprint(f) not in prior]
    except Exception as exc:
        # Parser/configuration errors are tool failures, not SHACL conformance results.
        code = "INPUT001" if stage == "RDF input parsing" else "TOOL001"
        print(f"{code}: {stage} failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        output = json.dumps(
            {"summary": dict(Counter(x.severity for x in issues)), "findings": [f.to_dict() for f in issues]}, indent=2
        )
    elif args.format == "sarif":
        output = json.dumps(_sarif(issues), indent=2)
    else:
        lines = [f"Ontology linter: {len(issues)} finding(s)"]
        for f in issues:
            lines.append(f"[{f.severity.upper():7}] {f.rule} {f.focus}: {f.message}\n    Fix: {f.suggestion}")
        output = "\n".join(lines)
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
    threshold = {"error": 0, "warning": 1, "info": 2, "never": -1}[args.fail_on]
    return int(threshold >= 0 and any(["error", "warning", "info"].index(x.severity) <= threshold for x in issues))


if __name__ == "__main__":
    sys.exit(main())
