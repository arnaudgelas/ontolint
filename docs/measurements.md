# Measurements

The `METRIC001`-`METRIC013` rules each compare one figure of the ontology with a threshold, and a
figure is visible only as a finding, when it crosses its threshold. The figures themselves are
*measurements*: named, versioned values that ontolint takes once per file and that the rules read.
`--measurements` publishes them, as a vector, whatever the thresholds:

```bash
ontolint onto.ttl --format json --measurements
```

Each entry of the report's `files` then carries a `measurements` list. Nothing else in the report
changes: findings, fingerprints, baselines and the exit code are the same with and without the flag,
and the text and SARIF formats never show measurements (`--measurements` with another format is a
usage error, exit 2). Measurements are a vector on purpose; ontolint does not compute a single
health score.

The engine is `src/ontolint/rules/measurements.py`; the METRIC specification at the top of
`src/ontolint/rules/metrics.py` names the measurement each rule reads, and
[metric-thresholds.md](metric-thresholds.md) gives the thresholds.

## What every measurement keeps to

- It has an `id`, a `definition_version` and a `population`, the name of what it counts over.
  Every definition starts at version 1; any change to what a measurement counts, a bug fix
  included, increments it, so two values of one version can be compared.
- A ratio is published as its `numerator` and `denominator`, both integers, never as the
  quotient. A mean is a ratio too: the sum over the count. No float is ever printed.
- A measurement that could not be taken is published with a `reason` and no value, never as 0.
  A METRIC rule whose measurement could not be taken fails (`MeasurementUnavailable: <id>:
  <reason>`), even below `metric_min_sample`, so the run exits 2; it never passes.
- An empty population is a measurement that was taken: a ratio of 0 over 0, an empty histogram,
  a count of 0. A consumer must not divide by a denominator of 0.
- "Owned" is ontolint's ownership (the ontology header's namespace or `--base`, README "Scope and
  limitations"). Under `--follow-imports` the graph is the whole closure, as for the rules.
- Everything is read from the asserted graph: nothing is entailed and no reasoner runs.
- A value depends only on the graph, the shapes graph and the policy that shapes a population:
  `--base`, `extra_label_predicates`, `extra_definition_predicates` and the import closure. It never
  depends on a threshold, on which rules ran, on a profile or on a baseline.
- A numerator that a per-term rule also reports is exactly that rule's set: the coverage of labels
  is the classes `LEX001` does not report, the orphans are `CLS001`'s, the unsigned properties those
  `OWL005` and `OWL006` both report, and `SHQ006` reports the instantiated owned classes outside the
  SHACL coverage.
- Which terms are in a numerator (term-level values) is not in the report; the report carries
  counts only.

## Catalogue

In publication order. "Empty population" is the value of an ontology with no owned term (and, for
the SHACL coverage, an empty shapes graph).

| ID | Version | Kind | Population | Counts | Read by | Partitioned | Empty population |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `class_label_coverage` | 1 | ratio | `owned_classes` | owned classes with a label | METRIC001 | yes | 0/0 |
| `class_definition_coverage` | 1 | ratio | `owned_classes` | owned classes with a definition | METRIC002 | yes | 0/0 |
| `property_documentation_coverage` | 1 | ratio | `owned_properties` | owned properties with documentation | METRIC003 | yes | 0/0 |
| `class_fanout` | 1 | ratio | `owned_parent_classes` | direct subclass edges, over the classes that have one | METRIC004 | yes | 0/0 |
| `orphan_classes` | 1 | ratio | `owned_classes` | the classes `CLS001` reports | METRIC005 | yes | 0/0 |
| `relation_properties_per_class` | 1 | ratio | `owned_classes` | owned properties that are not annotation-only, over owned classes | METRIC006, METRIC007 | yes | 0/0 |
| `unsigned_properties` | 1 | ratio | `owned_object_and_datatype_properties` | the properties `OWL005` and `OWL006` both report | METRIC008 | yes | 0/0 |
| `label_language_coverage` | 1 | ratio | `labelled_owned_terms` | labelled terms with a language-tagged label | METRIC009 | yes | 0/0 |
| `foreign_references` | 1 | ratio | `structural_references` | references to a foreign namespace, split by namespace | METRIC010 | no | 0/0 |
| `unresolved_imports` | 1 | count | `graph` | distinct `owl:imports` IRIs not loaded | METRIC011 | no | 0 |
| `definition_length` | 1 | ratio | `defined_owned_classes` | words of the longest definition, summed over the defined classes | METRIC012 | yes | 0/0 |
| `blank_subjects` | 1 | ratio | `non_structural_subjects` | blank subjects | METRIC013 | no | 0/0 |
| `class_depth` | 1 | histogram | `acyclic_owned_classes` | owned classes off the subclass cycles, per depth | none | yes | [] |
| `cyclic_classes` | 1 | ratio | `owned_classes` | owned classes on a subclass cycle | none | yes | 0/0 |
| `hierarchy_components` | 1 | count | `owned_classes` | weakly connected parts of the asserted hierarchy | none | no | 0 |
| `shacl_class_target_coverage` | 1 | ratio | `owned_classes` | owned classes a class target reaches | none | yes | 0/0 |

## Populations and exclusions

Classes are the IRIs typed `owl:Class` or `rdfs:Class`; properties those typed
`owl:ObjectProperty`, `owl:DatatypeProperty`, `owl:AnnotationProperty` or `rdf:Property`. SKOS
concepts and individuals are in no population.

- **`class_label_coverage`.** The numerator is the owned classes with a `Literal` value of a label
  predicate (`rdfs:label`, `skos:prefLabel`, the configured `extra_label_predicates` and the
  predicates below them through `rdfs:subPropertyOf` and `owl:equivalentProperty`), or that are
  `owl:deprecated true`. Exclusions: an IRI-valued label does not count; an empty literal counts;
  `skos:altLabel` and `skos:hiddenLabel` do not count; the language is ignored. `METRIC001`
  reports the classes that are not covered (the population minus the numerator).
- **`class_definition_coverage`.** The numerator is the owned classes that are the subject of a
  definition predicate: `rdfs:comment`, `skos:definition`, `dcterms:description` and the other
  built-in ones, `extra_definition_predicates`, and the predicates below them through the transitive
  closure of asserted `rdfs:subPropertyOf` and `owl:equivalentProperty` triples. Exclusions: any value
  counts (an IRI, an empty literal); `skos:note`, `skos:scopeNote` and the predicates below them do
  not count, unlike for `LEX002`.
- **`property_documentation_coverage`.** The same for the owned properties, annotation properties
  included.
- **`class_fanout`.** The population is the owned classes with at least one owned direct subclass;
  the numerator is the asserted `rdfs:subClassOf` edges between owned classes. Exclusions:
  self-loops, external and blank superclasses. The mean fan-out is numerator over denominator, so the
  numerator is never below the denominator.
- **`orphan_classes`.** The numerator is the owned classes `CLS001` reports: no asserted local
  super- or subclass, no typed instance, not used as a domain, range or restriction filler, no
  `owl:equivalentClass` link, not `rdfs:subClassOf owl:Thing`, not deprecated.
- **`relation_properties_per_class`.** The numerator is the owned properties that are not
  annotation-only (typed `owl:AnnotationProperty` without an object or datatype type), the
  denominator the owned classes. This is not a share: the numerator may exceed the denominator, and
  an ontology with properties but no class publishes n/0.
- **`unsigned_properties`.** The population is the owned IRIs typed `owl:ObjectProperty` or
  `owl:DatatypeProperty`; the numerator those with neither a domain (`rdfs:domain`,
  `schema:domainIncludes`, `dcam:domainIncludes`) nor a range (likewise) that are not deprecated.
  A domain reached through an inverse or a superproperty is not looked for.
- **`label_language_coverage`.** The population is the owned classes and properties with at least
  one `Literal` label (as for `class_label_coverage`); the numerator those with a language-tagged
  one. An `xsd:string` label is untagged; unlabelled terms are not in the population.
- **`foreign_references`.** Not a term population: the denominator counts *triples*,
  `rdfs:subClassOf` from owned classes and `rdfs:domain` and `rdfs:range` from owned properties, to
  IRIs outside the RDF, RDFS, OWL and XSD namespaces. A reference is foreign when the target's
  namespace (the text up to its last `#` or `/`) differs from the subject's and the target is not
  owned; a graph with no ownership information compares namespaces only. Exclusions: blank targets,
  `owl:equivalentClass`, restriction fillers, OBO reuse of another OBO ontology (one shared
  namespace). `by_namespace` gives the foreign references per target namespace, sorted; their counts
  sum to the numerator. A namespace is cut from the target with its userinfo masked, so two targets
  that differ only in their userinfo share one entry.
- **`unresolved_imports`.** Not a term population: the distinct IRI objects of `owl:imports` in the
  whole graph, of every header (the whole closure under `--follow-imports`), minus those the closure
  loaded. This is `METRIC011`'s count. It differs from `SEC007`'s list, which also lists a
  non-IRI `owl:imports` object and names `file:` imports by their display text.
- **`definition_length`.** The population is the owned classes with a `Literal` description (as for
  `class_definition_coverage`); each scores the `\w+` token count of its longest description, and the
  numerator is their sum, so the mean is numerator over denominator. An IRI description is not
  measured; a long `rdfs:comment` masks a short `skos:definition`; properties are not measured.
- **`blank_subjects`.** Not a term population: the distinct subjects of the whole graph that are not
  structural blank nodes (an axiom, restriction, class expression, list cell, reified statement or
  SHACL structure, as `METRIC013` defines them); the numerator is the blank ones.
- **`class_depth`.** Per owned class, the number of classes on the longest chain of asserted
  `rdfs:subClassOf` triples between owned classes from a top class down to it: a class with no owned
  superclass is at depth 1. A class on a subclass cycle (`cyclic_classes`) has no depth: it is left
  out of the population, not counted at 0, and adds no level to its subclasses, so a class whose only
  owned superclasses are on a cycle is at depth 1. A self-loop is ignored. `buckets` lists
  `{value: depth, count: classes}` in ascending depth; the counts sum to the population, the owned
  classes minus `cyclic_classes`' numerator, and no depth is below 1. The largest depth is the
  largest subtree depth `CLS005` compares with `--depth-limit`.
- **`cyclic_classes`.** The numerator is the owned classes on a cycle of asserted `rdfs:subClassOf`
  triples between two or more owned classes (a strongly connected component of more than one class),
  the classes `class_depth` leaves out. Exclusions: a self-loop, which `CLS003` reports too, is not a
  cycle here; a cycle closed through a class that is not owned is not seen.
- **`hierarchy_components`.** The weakly connected components (direction ignored) of the asserted
  `rdfs:subClassOf` triples between owned classes. `owl:Thing` and every class that is not owned are
  left out, so two subtrees under one external superclass are two components; a class with no owned
  sub- or superclass is a component of its own. `CLS001`'s orphans are some of these singletons, not
  all of them.
- **`shacl_class_target_coverage`.** The numerator is the owned classes some class target of the
  shapes graph reaches: a value of `sh:targetClass`, a shape that is also a class (an implicit class
  target), or a subclass of either through the data graph's `rdfs:subClassOf`, transitively, as
  SHACL 1.1 defines a SHACL instance. Absent, with the reason `no SHACL shapes graph was supplied`,
  without `--shapes`; an empty shapes graph gives 0 of the owned classes. Known gaps, shared with
  `SHQ006`: `sh:targetNode`, `sh:targetSubjectsOf`, `sh:targetObjectsOf` and SPARQL targets do not
  count, and a deactivated shape still covers its classes.

## JSON shape

```json
"files": [
  {
    "path": "onto.ttl",
    "summary": {},
    "execution_summary": {},
    "executions": [],
    "measurements": [
      {"id": "class_label_coverage", "definition_version": 1, "kind": "ratio",
       "population": "owned_classes", "numerator": 32, "denominator": 33},
      {"id": "foreign_references", "definition_version": 1, "kind": "ratio",
       "population": "structural_references", "numerator": 3, "denominator": 10,
       "by_namespace": [{"namespace": "http://purl.obolibrary.org/obo/", "count": 3}]},
      {"id": "unresolved_imports", "definition_version": 1, "kind": "count",
       "population": "graph", "value": 1},
      {"id": "class_depth", "definition_version": 1, "kind": "histogram",
       "population": "acyclic_owned_classes", "buckets": [{"value": 1, "count": 4}, {"value": 2, "count": 9}]},
      {"id": "shacl_class_target_coverage", "definition_version": 1, "kind": "ratio",
       "population": "owned_classes", "reason": "no SHACL shapes graph was supplied"}
    ]
  }
]
```

- `measurements` comes after `executions` (and after `module_summary` when there is one), and
  only with `--measurements`. It always lists every measurement of the catalogue, in its order.
  `measurement_partitions` follows it when the file has partitions (see "Partitions").
- A ratio has `numerator` and `denominator`; `foreign_references` also has `by_namespace`, a list
  even when empty. A count has `value`. A histogram has `buckets`, possibly empty.
- A measurement that could not be taken keeps `id`, `definition_version`, `kind` and `population`
  and has a `reason` instead of a value. A computation that failed is published as absent with the
  reason `failed: <ExceptionType>: <message>`; a METRIC rule that read it has failed too.
- The report's `schema_version` stays `1`: the key is additive.
- No IRI userinfo is ever printed: reasons and namespaces are masked.

## Partitions

With module grouping (`--module-by`, `--module-annotation`), named graphs (TriG, N-Quads, JSON-LD) or
an import closure (`--follow-imports`, `--catalog`), the file's entry also carries
`measurement_partitions`: the partitioned measurements (the "Partitioned" column) of the owned terms in
each in-file module, named graph or closure file.

```json
"measurement_partitions": [
  {"by": "file", "path": "onto.ttl", "measurements": []},
  {"by": "file", "path": "modules/core.ttl", "measurements": []},
  {"by": "graph", "path": "onto.ttl", "name": "(default graph)", "measurements": []},
  {"by": "module", "name": "core", "measurements": []}
]
```

- A term is placed exactly where a finding about it is placed: in the closure file that declares it
  (else the root), in the graphs of that file that describe it (else those that mention it), and in
  the modules its annotation names or its namespace is. So a partition's coverage and the findings
  listed for the same module, graph or file come from one placement rule.
- A partition restricts the file's measurement to its terms and never recomputes it: each term keeps
  its value in the whole file (a class's depth, a parent's number of subclasses, counted over the
  whole hierarchy). `relation_properties_per_class` restricts both its properties and its classes.
- A term in two graphs or two modules counts in both. A term without a module annotation is in no
  module. A term is in exactly one closure file, so the `file` partitions of a measurement add up to
  the file's own record.
- Every closure file is listed (the root too, also when the closure is the root alone), and every
  graph of each file's index: one without owned terms shows 0 of 0 (a histogram `[]`). A module is
  listed when an owned class or property is in it.
- `foreign_references`, `unresolved_imports`, `blank_subjects` and `hierarchy_components` are not
  measurements of single owned terms, so they appear only in the file's own record.
- A measurement that could not be taken is absent, with the same reason, in every partition.
- Partitions are listed by kind (files, then graphs, then modules): files in closure order, the root
  first; graphs by file, then `(default graph)` first and the others sorted; modules sorted by name.
  `path` is the report path of the file (for a graph, of the file holding it); `name` is the graph's
  or the module's.

## Limitations

- Every measurement is asserted-only. Unsatisfiable classes, the competency-question pass rate and
  mapping coverage need a reasoner, a CQ manifest or reviewed mappings, and are not measured.
- With `--pattern-library`, the measurements are those of the linted index file's graph; they are
  not split by member ontology as member findings are.
