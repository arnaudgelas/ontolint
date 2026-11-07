Ontology-quality linter: runnable Python starter and 328-rule roadmap
This is a starter implementation, not a claim of full OWL 2 DL validation or complete implementation of 328 ontology checks. It is designed to complement, not replace, RDFLib, pySHACL, OWLAPI/ROBOT, DL reasoners, and expert ontology review.
Included files
- ontolint.py: executable linter, with 61 defined diagnostics (59 Python graph checks, one RDFLib parse/error wrapper, one optional pySHACL validation integration). Findings have rule, severity, focus, message, suggestion, and confidence fields.
- rule_catalogue.csv: 328 candidate rule identifiers, with status for every rule: implemented or proposed. Counts include existing-parser and optional validation backends.
- OOPS_crosswalk.csv: all 41 OOPS! pitfalls, coverage status, candidate implementation mapping, and semantic caveats.
- OntoSniff_crosswalk.csv: all 17 OntoSniff smells, coverage status and mapping.
- config.example.json: configuration, local namespace, severity overrides, suppressed rules.
- examples/broken.ttl, examples/good.ttl, examples/sample-report.json: demonstration inputs and sample findings.
- tests/test_linter.py: regression tests.
Install and run
Python 3.10 or higher:
python -m pip install -e '.[test]'
python -m pytest -q
python ontolint.py examples/broken.ttl --base 'https://example.org/ont#'
python ontolint.py examples/broken.ttl --base 'https://example.org/ont#' --format json --output report.json
python ontolint.py examples/good.ttl --base 'https://example.org/clean#' --fail-on error
For SHACL validation, install pip install -e '.[shacl]' and add --shapes shapes.ttl. This integration was not executed in the packaged test suite because pySHACL was not installed in the build environment. It calls pySHACL with meta_shacl=True and advanced=True; newer SHACL draft features are not guaranteed.

To use a policy file and suppress known findings:
python ontolint.py examples/broken.ttl --config config.example.json --format sarif --output findings.sarif
python ontolint.py examples/broken.ttl --config config.example.json --write-baseline baseline.json
python ontolint.py examples/broken.ttl --config config.example.json --baseline baseline.json --fail-on warning
Exit status: 0 = no findings at or above the requested --fail-on threshold; 1 = threshold exceeded; 2 = tool failure or malformed input. The baseline compares stable hashes of (rule, focus, message) and prevents existing issues from blocking new work; it is not a substitute for version-to-version ontology semantic analysis.
Example policy
{
  "base": "https://example.org/ont#",
  "languages": ["en"],
  "depth_limit": 7,
  "inheritance_limit": 3,
  "soup_limit": 15,
  "ignored_rules": ["CLS002"],
  "severity_overrides": {"ONT003": "error", "OWL005": "info"}
}
Core interpretation principles
1. Syntax and structural validity are different from logical consistency. A successful RDF parse means neither OWL 2 DL compliance nor satisfiability.
2. SHACL validates graph constraints and does not imply domain ontology design quality. Custom SHACL can express many rules, but pySHACL does not supply the cross-project ontology-lint rulebook automatically.
3. Domain/range are inferential. Multiple asserted RDFS domains mean conjunction; a missing global domain/range is often appropriate. Treat OWL004 as a review warning.
4. No evidence does not mean false under OWL's open-world assumption. A class without directly typed instances is not a logical defect. CLS002 is informational.
5. A subclass cycle does not automatically make OWL inconsistent. CLS003 is warning. Equivalent named classes can be intended.
6. owl:allValuesFrom is universally quantified and does not imply existence. OWL011 is review-only.
7. SKOS S13/S14 are formal integrity conditions, but a SKOS skos:broader cycle is not universally forbidden. SKOS003 is informational.
8. Namespace authority cannot be determined reliably from local triples alone. Use an opt-in registry and network checks with timeouts and a URL allowlist.
9. No automatic network fetches or owl:imports resolution. Run in offline/CI contexts without SSRF risks. Include an explicit pinned import closure in a production implementation.
10. No auto-fixing semantic OWL axioms. Suggesting an axiom does not mean its intended meaning is known.
Source coverage and provenance
- OOPS! original pitfall catalogue P01–P41: https://oops.linkeddata.es/catalogue.jsp
- OntoSniff: https://ise-fizkarlsruhe.github.io/ontoink/ontosniff/
- pySHACL: https://github.com/RDFLib/pySHACL
- SHACL Play!: https://shacl-play.sparna.fr/play/
- TopBraid SHACL API: https://github.com/TopQuadrant/shacl
- European Commission's SHACL shape validator best-practice rules: https://www.itb.ec.europa.eu/shacl/shacl/upload
- ROBOT report: https://robot.obolibrary.org/report and OWL profile validation https://robot.obolibrary.org/validate-profile
- Protégé: https://protege.stanford.edu/software.php
- FOOPS! metrics: https://oeg-upm.github.io/fair_ontologies/
- W3C SKOS integrity: https://www.w3.org/TR/skos-reference/
- OBO Foundry principles: https://obofoundry.org/principles/fp-000-summary.html
- W3C 2017 SHACL Recommendation: https://www.w3.org/TR/shacl/
The catalogue lists candidate new checks, not 328 separate standards requirements. Source labels such as OOPS-P14 are traceability identifiers, not claims of identical behavior to upstream tools. Some apparent references in OntoSniff's page (e.g., linking its Lazy Class to OOPS P11) do not correspond to the current OOPS catalogue's definition; this package uses direct conceptual mappings rather than copying those references.
Recommended external integrations (not bundled)
OWLAPI/ROBOT: validate OWL profile and perform reasoning outside Python (using subprocess.run([...], shell=False, timeout=...)), then translate results into the common Finding model. Examples:
robot validate-profile --profile DL --input ontology.owl --output owl-profile.txt
robot report --input ontology.owl --output robot-report.tsv
Protégé and reasoners: HermiT/Pellet/ELK for full-profile or profile-specific consistency, unsatisfiable classes, classification, and explanation. Use ELK for suitable OWL 2 EL ontologies; use HermiT for OWL 2 DL as appropriate. Python graph analysis does not substitute for a DL reasoner.

SHACL Play / TopBraid: SHACL shape catalogs, generation/documentation and inference workflows; TopBraid's SHACL API is Java/Jena-based, not a Python extension to pyshacl.

FAIR / publishing: FOOPS! metrics, dereferenceability checks, HTTP content negotiation, persistent versions, license metadata, documentation, provenance, catalog registration. Network checks must be explicitly enabled and sandboxed.

Semantic change review: compare two ontologies for deleted/renamed terms, changed domains/ranges, added disjointness, removed entailments, altered SHACL constraints and compatibility with competency questions.

Human/AI-assisted review: assess class meaning, domain completeness, wrong owl:equivalentClass, unjustified property characteristics, OntoClean rigidity/identity/unity/dependence metadata, and whether a model answers actual user questions. AI suggestions should carry provenance and require human approval.
Suggested production architecture
ontolint/
    cli.py
    policy.py             # explicit profiles and suppressions
    registry.py           # stable code/source/severity/confidence
    graph_loader.py       # local/imported/named graph provenance
    report.py             # JSON, SARIF, RDF SHACL report, HTML
    rules/
        rdf.py            # beyond-parser graph integrity
        owl.py            # graph-local schema anti-patterns
        hierarchy.py      # SCC, reachability, graph metrics
        lexical.py        # labels, language tags, definitions
        skos.py           # SKOS & SKOS-XL
        shacl_quality.py  # shapes-authoring advice
        publishing.py     # HTTP content negotiation and FAIR
        compatibility.py  # old/new ontology comparisons
        competency.py     # SPARQL competency tests
    backends/
        pyshacl.py        # reuse existing engine
        robot.py          # profile checking and ROBOT report
        reasoner.py       # HermiT/ELK/Pellet integration
    rulepacks/
        generic.yaml
        publication.yaml
        enterprise.yaml
        skos.yaml
        obo.yaml
    tests/
The runnable prototype is intentionally a single file for easy inspection and use. A production project should separate the rule registry from implementations and attach exact source-triple evidence and source-file locations to findings.
What remains to build
See rule_catalogue.csv for the complete proposed backlog. Highest priorities after this starter:
1. Comprehensive test fixtures for all implemented rules and explicit false-positive cases; >95% rule-level unit test coverage.
2. OWLAPI/ROBOT profile checking and HermiT/ELK reasoner adapters.
3. Safe pinned import-closure support with provenance per graph and import-specific false-positive suppression.
4. Shape-authoring checks from the European Commission's extended W3C syntax rules, without duplicating Meta-SHACL checks.
5. Snapshot-to-snapshot semantic regression (OWL entailments, SHACL constraints, competency queries).
6. Opt-in HTTP and FOOPS! publishing checks with privacy/security guardrails.
7. Coverage metrics, rule applicability profiles, actionable evidence, SARIF locations, and trend dashboards.
Baseline limitations of this prototype
- --base is strongly recommended. Without it, every explicitly declared term in the input is considered local, including external terms re-declared in the same graph.
- CLS002 has high false-positive rates in TBox-only ontologies and should normally be disabled in that profile.
- Hierarchy analysis examines asserted subclass statements. It does not compute all entailed subclass relationships, import closures, or OWL class expressions.
- SHQ006 shape coverage only tests directly typed instances and direct class targets; inherited targets, sh:targetNode, sh:targetSubjectsOf, nested shapes, and rules require richer target analysis.
- Cycles are detected using a simple recursive strongly connected components implementation, which may reach Python's recursion limit on very large graphs. Use an iterative graph implementation for large ontologies.
- Severity defaults express ontology-quality policy; only context-sensitive rules should be enabled with an appropriate profile.
- The optional pySHACL integration and non-Turtle serializations have not been exercised by the included regression tests.
- SARIF currently includes rule messages but not exact source line/column locations.
A practical development sequence
Release 0.1: RDFLib parsing + graph-local lexical, taxonomic, OWL and SKOS diagnostics (included).

Release 0.2: richer SHACL shape-quality checks, policy packs, source location and import provenance.

Release 0.3: ROBOT/OWLAPI/description logic reasoner integration.

Release 0.4: diff-based compatibility checks and executable competency questions.

Release 1.0: FAIR/publishing validators, security-hardened network adapters, RDF report export, performance benchmarking, validated presets, and full automated test coverage.
