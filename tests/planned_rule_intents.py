"""High-level intent of every catalogue rule that is not implemented yet.

These one-line drafts feed the TODO tables of the family pages, ``docs/rules/<family>.md``. They
describe what a rule is meant to detect, not a final specification: the exact definition is fixed
when the rule is built.
``tests/test_rule_docs.py`` requires one entry per proposed rule and none for implemented rules.
"""

from __future__ import annotations

INTENTS: dict[str, str] = {
    # ALIGN: ontology alignment and mapping quality (needs a mapping registry or a reasoner).
    "ALIGN001": "Mapping whose target term is unknown to the mapping registry or the aligned ontology.",
    "ALIGN006": "Mapping to a deprecated or obsolete target term.",
    "ALIGN010": "Equivalence mapping that makes a class unsatisfiable once merged (reasoner).",
    "ALIGN011": "Mapped terms whose labels differ so much that the mapping looks wrong.",
    # COMP: compatibility between two versions of an ontology (needs a diff engine and a reasoner).
    "COMP001": "Term removed from the new version without having been deprecated first.",
    "COMP002": "Existing term whose IRI changed between versions.",
    "COMP004": "Subclass or superclass axiom removed, weakening the hierarchy.",
    "COMP005": "New axiom that makes previously valid data inconsistent (reasoner).",
    "COMP006": "Domain or range narrowed so existing assertions would be reclassified.",
    "COMP007": "Property characteristic changed, for example made functional or transitive.",
    "COMP008": "Cardinality restriction tightened compared with the old version.",
    "COMP010": "Term changed kind, for example class to individual or object to datatype property.",
    "COMP011": "Content changed but owl:versionIRI or owl:versionInfo was not updated.",
    "COMP012": "Version identifier that does not increase relative to the old version.",
    "COMP013": "Import added or removed between versions without a version bump.",
    "COMP014": "Ontology IRI or namespace changed between versions.",
    "COMP015": "Term reintroduced after having been marked obsolete.",
    "COMP016": "Class that becomes unsatisfiable in the new version (reasoner).",
    "COMP017": "Entailed subclass relations that differ from the old version (reasoner).",
    "COMP018": "Breaking changes whose size does not match the version bump (semantic versioning).",
    # CQ: competency questions run as SPARQL queries.
    "CQ001": "Competency question that is not valid SPARQL.",
    "CQ002": "Competency question written as an update or other unsupported query form.",
    "CQ003": "Competency question that returns no result on the ontology.",
    "CQ004": "Competency question that refers to a class or property the ontology does not declare.",
    "CQ005": "Result count that differs from the expected count.",
    "CQ006": "Answers that differ from the expected answers.",
    "CQ007": "Competency question without any expected answer to compare against.",
    "CQ008": "Query that exceeds the time or result budget.",
    "CQ009": "Ontology terms that no competency question exercises.",
    "CQ010": "Duplicate or near-duplicate competency questions.",
    "CQ012": "Question that passed in the baseline run but fails now.",
    "CQ013": "Question without an identifier, natural-language text or requirement link.",
    "CQ014": "Query with unbound variables or a cartesian-product pattern.",
    # FAIR: findability and accessibility checks over HTTP (needs a controlled network backend).
    "FAIR001": "Ontology IRI that does not resolve.",
    "FAIR002": "Sampled term IRIs that cannot be dereferenced.",
    "FAIR003": "Resolution that returns no RDF serialisation through content negotiation.",
    "FAIR005": "Ontology not registered in a public registry such as OBO Foundry, BioPortal or LOV.",
    "FAIR008": "owl:imports target that is unreachable.",
    "FAIR009": "Homepage, documentation or issue-tracker URL that is broken.",
    "FAIR010": "Metadata that cannot be retrieved through HTTP headers or the content of the response.",
    "FAIR012": "Terms reused from external namespaces that no longer resolve.",
    "FAIR013": "Version IRI that serves content which has changed since release.",
    "FAIR014": "Release not published in the expected serialisations.",
    "FAIR015": "Release artefact without a checksum or signature.",
    "FAIR016": "No machine-readable dataset metadata such as VoID or DCAT.",
    "FAIR018": "Share of sampled IRIs returning 4xx or 5xx above a threshold.",
    # GOV: governance and policy (needs a policy file, some rules also need the network).
    "GOV018": "Maintainer identifiers that cannot be resolved (network).",
    # IRI
    "IRI007": "Term IRIs that cannot be dereferenced (needs network access).",
    # OBO: OBO Foundry principles (needs an OBO policy pack).
    # SEC: safe loading and network policy.
    # SEM: reasoner-backed checks.
    "SEM002": "Ontology that is inconsistent.",
    "SEM003": "Classes that are unsatisfiable.",
    "SEM004": "Properties whose axioms make them unusable.",
    "SEM005": "Inferred hierarchy that differs unexpectedly from the asserted one.",
    "SEM006": "Asserted subclass axiom that is already entailed by others.",
    "SEM007": "Classes inferred to be equivalent without being asserted so.",
    "SEM014": "Ontology that cannot be classified within the reasoner's time budget.",
}
