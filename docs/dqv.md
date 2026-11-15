# Measurements as W3C DQV

`--write-dqv FILE` writes one run's [measurements](measurements.md) as Turtle in the W3C Data Quality
Vocabulary (DQV), so a tool that reads DQV can consume them. It is opt-in: a run without the flag is
unchanged, and with it the findings, fingerprints and exit code are the same.

```bash
ontolint onto.ttl --write-dqv quality-dqv.ttl
SOURCE_DATE_EPOCH=1767323045 ontolint onto.ttl --write-dqv quality-dqv.ttl   # dated, still reproducible
```

It takes exactly one ONTOLOGY, like `--write-quality-snapshot`, and is a projection of the same quality
snapshot ([quality.md](quality.md)): the values are the snapshot's, so the JSON report, the snapshot and
the DQV file never disagree. The term sets of a snapshot are not published: DQV carries values.

## What is published

For each value, one `dqv:QualityMeasurement` that is `dqv:isMeasurementOf` a `dqv:Metric`,
`dqv:computedOn` the ontology (its `owl:versionIRI` when it has one, else its IRI), with a typed
`dqv:value` and `prov:wasGeneratedBy` the run. The run is a `prov:Activity` that `prov:used` the
ontology and `prov:wasAssociatedWith` a `prov:SoftwareAgent` carrying the ontolint version
(`dcterms:hasVersion`).

| Measurement | Published as |
| --- | --- |
| ratio | two measurements, the `numerator` and the `denominator`, both `xsd:integer`; never the quotient |
| count | one `xsd:integer` measurement (`value`) |
| histogram | one `xsd:integer` measurement per bucket (metric `...:bucket:<value>`) and `terms`, the terms it counts |
| not taken (a `reason`) | **no measurement**, never 0; the run carries `rdfs:comment "not measured: <id>: <reason>"` |
| `by_namespace` of a ratio | not published |

An empty population is a measurement that was taken: 0 over 0, or `terms` 0. A consumer must not divide by
a denominator of 0 (see measurements.md).

The catalogue version is the definition version of each measurement, which is part of its metric IRI: a
changed definition is another metric. The rule catalogue has no version of its own; the ontolint version
identifies it.

## IRIs

Everything ontolint mints is in `urn:ontolint:` and is not hosted: `urn:ontolint:metric:<id>:<definition
version>:<part>`, `urn:ontolint:measurement:<hash>`, `urn:ontolint:run:<hash>` and
`urn:ontolint:tool:<version>`. The hashes are of the run's values, so they are stable. The namespace is
not a registered URN namespace and promises nothing but stability of these names. This is a maintainer
decision (issue 22): the alternatives are a `w3id.org` namespace (a promise to maintain a redirect) and
`urn:uuid:` version 5 names (registered, opaque).

Findings are not published (no `dqv:QualityAnnotation`). `dqv:inDimension` is not set: ontolint does not
classify its metrics into DQV dimensions.

## Determinism and masking

The serialisation is sorted Turtle with no blank node; the same run gives the same bytes. There is no
timestamp unless the environment sets `SOURCE_DATE_EPOCH` (a whole number of seconds; empty counts as
unset; anything else is a tool failure, exit 2), which dates the run (`prov:endedAtTime`) and each
measurement (`prov:generatedAtTime`). Every IRI and reason has its userinfo masked, as everywhere else.

## Failures

Exit 2 (`TOOL001`) and no file: the ontology has no single `owl:Ontology` IRI (or more than one
`owl:versionIRI`), the timestamp is unusable, or the file cannot be written.

## Linting the output

The file is data, not an ontology, so it has no `owl:Ontology` header and ONT001 reports that; every other
rule is silent (`ontolint quality-dqv.ttl --ignore ONT001`). A header would need a licence and a creator
that ontolint cannot truthfully claim.

## Consumer

Any DQV reader, for example a DCAT catalogue or a FAIR assessment, can load the file. None is supported or
tested; the consumer is named here only as an example.
