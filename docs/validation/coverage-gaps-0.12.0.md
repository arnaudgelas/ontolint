# Coverage-gap findings on CCO, BFO and RO (ontolint 0.12.0)

0.11.0 added findings to OWL010, OWL019, OWL032 to OWL037, OWL040, SHQ008, SHQ011, ALIGN003 and
SKOS009 (CHANGELOG, 0.11.0, "New findings"). They were never counted on the reference
vocabularies, which were not on the development machine (TODO.md, "Coverage gaps"). This page counts those rules on pinned releases of the Common
Core Ontologies (CCO), the Basic Formal Ontology (BFO) and the Relation Ontology (RO) (issue #12).
The severity questions of the specification audit (issue #11) depend on these counts.

**Result: each of the 13 rules reports 0 findings on every file it ran on.** The constructs the rules
judge are present: 220 CCO restrictions, 164 RO property chains, 110 chain-defined and 45
transitive RO properties. Counts taken with rdflib outside ontolint find none of them defective,
and one violation per rule injected into these files is reported, so the zeros are not rules
failing to run. The ontologies publish no SHACL, so SHQ008 and SHQ011 did not run on them. A
supplementary run on the DCAT-AP 3.0.1 shapes also found none.

## Sources

Each release was downloaded at a pinned commit into an empty scratch directory outside the
repository. No corpus file is committed. The archive checksums are those of the GitHub tarballs on
2026-11-11. GitHub does not guarantee stable tarball bytes, so the per-file checksums below are
the reference.

| Source | Release | Commit | Licence | Archive SHA-256 |
| --- | --- | --- | --- | --- |
| [CommonCoreOntology/CommonCoreOntologies](https://github.com/CommonCoreOntology/CommonCoreOntologies) | tag `v2.2` (2026-08-14) | `0bc7d33e1bc09fd4693366119ab4e03cb0340042` | BSD-3-Clause | `50f01bc62726f1ac08bdd9a9b71078e638bf771911523725027542c09bb4df63` |
| [BFO-ontology/BFO-2020](https://github.com/BFO-ontology/BFO-2020) | tag `release-2024-01-29` | `044490fc5100ffed6df7d4d15cbc167698b6fdee` | CC BY 4.0 (README) | `49ced50bd70a3d1b72eece7e301d0a37cfe51fbdcfcc0458c4b1ddb459dd619e` |
| BFO 2.0, OBO PURL `http://purl.obolibrary.org/obo/bfo.owl` (redirects to `bfo_classes_only.owl` of [BFO-ontology/BFO](https://github.com/BFO-ontology/BFO) tag `v2019-08-26`) | `bfo/2019-08-26/bfo.owl` | `6ba1893fbda8e9de9e88743d7fc41aff8822b2da` | CC BY 4.0 (header) | (single file, below) |
| [oborel/obo-relations](https://github.com/oborel/obo-relations) | tag `v2026-09-04` | `091f4761ec84657cc336d623e02006d6c351722c` | CC0 1.0 | `be5fb33b151dae0278b0c43915b7a12c90bad13e04d1c41c87173ffc7c00e886` |
| [SEMICeu/DCAT-AP](https://github.com/SEMICeu/DCAT-AP) (supplementary, SHACL) | tag `3.0.1`, `releases/3.0.1/` | `21f43cee5d61aa29e729e2e9193fc697f7b63861` | CC BY 4.0 | (single files, below) |

Archive URLs: `https://codeload.github.com/<owner>/<repo>/tar.gz/<commit>`. Single files:
`https://raw.githubusercontent.com/<owner>/<repo>/<commit>/<path>`.

## Command

ontolint 0.12.0 (`806dfc1`), Python 3.13.7, from the repository's locked environment. Every file
was linted with this command. The two `--follow-imports` variants add the flags shown in the
table. SHACL files were passed with `--shapes` beside a one-triple data file
(`<https://example.test/o> a owl:Ontology .`).

```sh
ontolint FILE --format json --fail-on never \
  --select OWL010,OWL019,OWL032,OWL033,OWL034,OWL035,OWL036,OWL037,OWL040,SHQ008,SHQ011,ALIGN003,SKOS009,OWL011
```

`--select` makes sure every rule runs whatever the default profile holds. OWL011 is not a
coverage-gap rule; it is included as the baseline for the datatype change of #12 (below). Each
report's `files[].executions` was read to confirm the rule `executed`. Every exit status was 0,
and stderr was empty. Findings were counted per `rule`.

The tarball has no `.git`, and `--import-root` defaults to the enclosing git repository, so
`--follow-imports` runs add `--import-root <CCO>/src`. The `AllCoreOntology.ttl` closure resolved
all eleven modules and BFO through `src/cco-merged/catalog-v001.xml`: a full-rule run reports
findings in seven of its files, and there is no SEC007.

## Counts

Rules in the issue's list, then OWL011. Each row is one file, or one group of files with identical
counts. All counts are findings, not terms.

| Input (path in the release) | SHA-256 | OWL010 | OWL019 | OWL032 | OWL033 | OWL034 | OWL035 | OWL036 | OWL037 | OWL040 | SHQ008 | SHQ011 | ALIGN003 | SKOS009 | OWL011 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CCO `src/cco-merged/CommonCoreOntologiesMerged.ttl` | `a9453382…9baadb42` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | n/r | n/r | 0 | 0 | 0 |
| CCO `src/cco-merged/AllCoreOntology.ttl`, `--follow-imports` (11 modules + BFO) | `11947e11…906a3ea4` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | n/r | n/r | 0 | 0 | 0 |
| CCO `src/cco-modules/*.ttl`, 11 files, each alone | below | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | n/r | n/r | 0 | 0 | 0 |
| CCO `src/cco-modules/*.ttl`, 11 files, each with `--follow-imports` | below | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | n/r | n/r | 0 | 0 | 0 |
| CCO `src/cco-extensions/{Barcode,FamilialRelations,ModalRelation}Ontology.ttl` | below | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | n/r | n/r | 0 | 0 | 0 |
| CCO `src/cco-extensions/candidates/`, 2 files (supplementary: the only cardinalities) | below | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | n/r | n/r | 0 | 0 | 0 |
| CCO `src/cco-imports/bfo-core.ttl` (CCO's BFO 2020 copy) | `128f5fe1…b37a106b` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | n/r | n/r | 0 | 0 | 31 |
| BFO 2020 `src/owl/bfo-core.ttl` | `6944e2c9…d8443a3b` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | n/r | n/r | 0 | 0 | 31 |
| BFO 2020 `src/owl/bfo-core.owl` (RDF/XML) | `af81eb71…0c98039c` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | n/r | n/r | 0 | 0 | 31 |
| BFO 2020 `src/owl/profiles/atemporal/bfo-2020-without-some-all-times.ttl` | `c0e92f69…2ccd7f3f` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | n/r | n/r | 0 | 0 | 14 |
| BFO 2.0 PURL `bfo_classes_only.owl` | `ca399c2b…4f6c4666` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | n/r | n/r | 0 | 0 | 0 |
| RO `ro.owl` (full release, imports merged) | `9a3190d4…94d42f77` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | n/r | n/r | 0 | 0 | 0 |
| RO `ro-base.owl` | `bdfe8dda…cde027fe` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | n/r | n/r | 0 | 0 | 0 |
| RO `core.owl` | `3c8e219f…7a4efeb8` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | n/r | n/r | 0 | 0 | 0 |
| DCAT-AP 3.0.1, 7 SHACL files, `--shapes` (supplementary) | below | – | – | – | – | – | – | – | – | – | 0 | 0 | – | – | – |
| **Total** | | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **107** |

–: the data file is the one-triple placeholder, so the count says nothing. n/r: not run. The rule is `skipped`, with "no SHACL shapes graph was supplied", because the release
has no SHACL. No file of the three repositories mentions `http://www.w3.org/ns/shacl#`.

Full SHA-256 of every linted file:

| File | SHA-256 |
| --- | --- |
| CCO `src/cco-merged/CommonCoreOntologiesMerged.ttl` | `a9453382b25b40781c181d6ba44981f228abb76d90d548846713adba9baadb42` |
| CCO `src/cco-merged/AllCoreOntology.ttl` | `11947e11b89282ca9aba9ae06ae07a563e253af836dbf26d60ecd226906a3ea4` |
| CCO `src/cco-modules/AgentOntology.ttl` | `ab25164d15ef1b89922b87e40f521df32e2a13a8c8121fb84f788d41d2b6e0ec` |
| CCO `src/cco-modules/ArtifactOntology.ttl` | `5819319a6a8fee4c219a9f35a9ec03f36fdf68f6d400accfc3cba67a7661d3f9` |
| CCO `src/cco-modules/CurrencyUnitOntology.ttl` | `74e8c90fd0d8cf3d93bdb7008f66fc27b86f85c11fca1f24a49e9aa4f6def277` |
| CCO `src/cco-modules/EventOntology.ttl` | `fa0063e0d0e2a95bcd32a5ddfe6c9661b540e91f2e4e45fd73c779cc282afed9` |
| CCO `src/cco-modules/ExtendedRelationOntology.ttl` | `280026a63fb7ea85e8d8f03274bef2f5521d6a9208e17bc9117c1c4b9a660aea` |
| CCO `src/cco-modules/FacilityOntology.ttl` | `e1d04c08ca58f28122dfc4c81b83442172c95fe9c4e2697f793797ddb1cf49bd` |
| CCO `src/cco-modules/GeospatialOntology.ttl` | `ab1208db13c8a3f718afa6b9bc8005b2c08a55829c705781f466722fe8a7809b` |
| CCO `src/cco-modules/InformationEntityOntology.ttl` | `294f81969d05af6d941625e08636d7f1289a1e36908aae22ca48d6176417571b` |
| CCO `src/cco-modules/QualityOntology.ttl` | `28e3a4db5a35623839e17e8671051dbe5921ebd9355d320f51bf0e8935f2972f` |
| CCO `src/cco-modules/TimeOntology.ttl` | `e7153579558648934b5d1576bc986b8db4f2d250bbe41932d9802fad7ab2a92e` |
| CCO `src/cco-modules/UnitsOfMeasureOntology.ttl` | `30a1c39d4d74259f8c401282f5b7bd9c485467905f5d27e5f908328bb6bc4149` |
| CCO `src/cco-imports/bfo-core.ttl` | `128f5fe1dab7ee804a3037a836813e5953c846eeeefee883a47d5db0b37a106b` |
| CCO `src/cco-extensions/BarcodeOntology.ttl` | `6ff28b11c7c600c0703ba240cb1bd238b29e819af62960a23305ff6caac5e512` |
| CCO `src/cco-extensions/FamilialRelationsOntology.ttl` | `98e4198780c41706fa072b4bb13de8cf6cd91b3408b224eed6d7b3ab38cae8ee` |
| CCO `src/cco-extensions/ModalRelationOntology.ttl` | `3acad0c74943ee0645f347c8c983e1d7907a18e81df052288c5598b446ab8e27` |
| CCO `src/cco-extensions/candidates/ArgumentsOntology/ArgumentOntology.ttl` | `efccd10eddd6c1faf2b0d3e6b1589529d27cde5208977b37a1fc01465c6d15c1` |
| CCO `src/cco-extensions/candidates/MilitaryRanksOntology/MilitaryRanksOntology.owl` | `a1fb55cf3ff14841a838e58c73f022b055f4d9fc20938fb1e5dfd5fbd5bb85f1` |
| BFO 2020 `src/owl/bfo-core.ttl` | `6944e2c96a0d8709dc15ae5364792019e208061eda3f32311af4f3b8d8443a3b` |
| BFO 2020 `src/owl/bfo-core.owl` | `af81eb7144c3d3db3a2d2beabff9dd299b14a91dc69cc84e663ca91e0c98039c` |
| BFO 2020 `src/owl/profiles/atemporal/bfo-2020-without-some-all-times.ttl` | `c0e92f697f46821f2945b4b93ab8d9f34bf9a013494e3ee13eca7c452ccd7f3f` |
| BFO 2.0 `bfo_classes_only.owl` | `ca399c2b8b79f4d12b296d5c4ea4c00940e1f82cee7d1a50ddc292aa4f6c4666` |
| RO `ro.owl` | `9a3190d49564743aa00f0b0f2e2d9c5fc5673ac7bb3c369284bf490294d42f77` |
| RO `ro-base.owl` | `bdfe8dda3adc4b9cda9d9c843b02e1031772280a92c07003af7c9c22cde027fe` |
| RO `core.owl` | `3c8e219fddd6f772c2d5e27cced12a91e8c3d2431b5e02af58e4ec567a4efeb8` |
| DCAT-AP `releases/3.0.1/shacl/dcat-ap-SHACL.ttl` | `990d3e42721de6a4be8cc338a7171559f195e62dea89c0b56531356b78cc026f` |
| DCAT-AP `releases/3.0.1/shacl/ranges.ttl` | `a6eed0fae8d0f5ca977fe2098ca12081ac60b0efe1ddce802d5c08e49505ebcc` |
| DCAT-AP `releases/3.0.1/html/shacl/shapes.ttl` | `7fe9815e0f32b10f5cbce74fa6ccd0290aae3ef9e5080fb84e2d8093eb984d1d` |
| DCAT-AP `releases/3.0.1/html/shacl/shapes_recommended.ttl` | `9afbf23f1f56d10d6839259684934137e20506a9aedce0249b619bbc593b9abd` |
| DCAT-AP `releases/3.0.1/html/shacl/mdr-vocabularies.shape.ttl` | `2362f83971766a15cc20b2b54420022dc10547dd2c483da02080847c61b4b45a` |
| DCAT-AP `releases/3.0.1/html/shacl/range.ttl` | `24d3bfd0fa17a3d0e877c9ebb91c8174124e5038538e1bf081b2cb679ad0f1b2` |
| DCAT-AP `releases/3.0.1/html/shacl/deprecateduris.ttl` | `30a20a51a487c40ab7ae04f5905f02ef28238ec5cb390e37053334d835021948` |

Not linted: `src/cco-iris/` (the same modules again under dated version IRIs), CCO's
`documentation/archive/` (the 1.x merged files), and RO's `.obo`/`.json` serialisations and `src/`
editors' files. The two candidate extensions are not part of the release; they were added because
they hold the only cardinality restrictions of the three repositories: one
`owl:qualifiedCardinality` in `ArgumentOntology.ttl` and 50 `owl:minQualifiedCardinality` in
`MilitaryRanksOntology.owl`, none on a transitive property and none paired with a maximum.

## What the zeros mean

The rules had material to judge. Counts were taken with ad-hoc rdflib scripts, outside ontolint.
The scripts are not committed; scripting the corpus is issue #31.

| Construct | CCO merged | BFO 2020 core | RO full |
| --- | --- | --- | --- |
| `owl:Restriction` | 220 | 31 | 37 |
| `owl:allValuesFrom` / `owl:someValuesFrom` | 34 / 186 | 31 / 0 | 11 / 21 |
| (qualified) cardinality restrictions | 0 | 0 | 0 (candidates: 51) |
| `owl:hasSelf` | 0 | 0 | 5 |
| `owl:propertyChainAxiom` (2 / 3 operands) | 2 (2 / 0) | 0 | 164 (147 / 17) |
| transitive / chain-defined properties | 8 / 2 | 6 / 0 | 45 / 110 |
| functional, inverse-functional, irreflexive or asymmetric typings (properties) | 11 (10) | 7 (6) | 15 (13) |
| `owl:propertyDisjointWith` axioms | 5 | 0 | 10 |
| `owl:unionOf` / `owl:intersectionOf` / `owl:oneOf` | 38 / 97 / 0 | 22 / 13 / 0 | 25 / 5 / 1 |
| SKOS mapping triples / `skos:related` | 0 / 0 | 0 / 0 | 4 / 0 |

A second script reimplements the non-simple test of OWL 2 Structural Specification section 11.1:
composite properties (144 in RO: transitive or with a chain of two or more), then the closure over
`rdfs:subPropertyOf` upwards and `owl:equivalentProperty` and `owl:inverseOf` both ways. On RO, 219
named properties are non-simple, `owl:topObjectProperty` included. (The first count, taken for this
page, was 220; a rewritten script gives 219. The one-property difference was not traced, and both
agree on everything that follows.)
None of the 13 properties with a simple-only characteristic is among them, the five `owl:hasSelf`
restrictions are on simple properties, and none of the 20 `owl:propertyDisjointWith` sides is
non-simple. CCO and BFO give the same result. A third script checks every list and restriction: every chain has
two or three operands, every union and intersection two or more distinct members, every
restriction exactly one `owl:onProperty` and one constraint, and no filler mixes kinds. Eight RO
chains repeat a property (`p o p`). OWL033 does not judge chains, and a repeated chain member is
legal (SS 9.2.1).

**Positive controls.** To show that no ownership, `--base` or parsing effect hides findings, one
violation per rule was appended to a Turtle re-serialisation of CCO merged and of RO `ro.owl`
(a one-operand chain; a functional transitive property and a cardinality on a transitive property;
a one-member union; duplicate intersection members; a restriction without `owl:onProperty`, one
without a constraint, one with cardinality `-1`, one with min 3 and max 1; an `xsd:string` and an
`rdf:JSON` filler on an object property; an object property with range `rdf:JSON`; an
`skos:exactMatch` chain against an `skos:broadMatch`; `skos:related` beside `skos:broader`), each on
a CCO- or RO-owned term. With ontolint 0.12.0 the re-serialisation alone reports 0; with the
additions, OWL010, OWL032, OWL033, OWL034, OWL036, OWL037, OWL040 (`xsd:string`), ALIGN003 and
SKOS009 report 1 each, OWL019 2 (both injections), and OWL035 2 (the restriction without a
constraint, and the min 3 / max 1 one, which holds two). The `rdf:JSON` lines are not reported:
0.12.0 does not know `rdf:JSON` as a datatype (issue #12). Appending an
`sh:minCount "1"^^xsd:nonNegativeInteger` and an `sh:pattern "^a\\/b"` to `dcat-ap-SHACL.ttl` makes
SHQ008 and SHQ011 report 1 each.

So the counts are true negatives, not rules failing to run:

- **OWL019, "cardinalities on transitive OBO relations".** Not seen. RO has no cardinality
  restriction at all, and OBO ontologies, written for the EL reasoner ELK, rarely use them. RO keeps every simple-only axiom off
  its non-simple properties. Its ODK `test` target runs `robot validate-profile --profile DL`
  (`src/ontology/Makefile`), which rejects them. Ontologies that *use* RO (Uberon, CL, GO-plus) may still put cardinalities on `part of`
  or `has part`. They were not linted here.
- **SHQ008 and SHQ011.** Not exercised: CCO, BFO and RO publish no shapes. DCAT-AP 3.0.1 writes
  every count as a plain Turtle integer (`sh:minCount`, 93 times; `sh:maxCount`, 104 times, all
  `1`), which is `xsd:integer`, and its three `sh:pattern` values (`^https://spdx.org/rdf/terms` and two
  like it) use no `\/` escape. Derived-integer counts and `\/` escapes, if they occur, are more
  likely in shapes that tools generate. No such shapes were in this corpus.
- **ALIGN003, SKOS009.** Not exercised either: the four RO SKOS mappings form no chain, and none of
  the files uses `skos:related`.

## Classification of the findings

None of the 13 rules has a finding to classify. Each count is a true negative, checked outside
ontolint and by the positive controls as above.

OWL011, outside the list, reports 31 universal restrictions of BFO 2020 core (14 in the atemporal
profile), on eight of BFO's parthood, location and occupation relations: `has continuant part` (10),
`continuant part of` (5), `temporal part of` (5), `occurrent part of` (4), `has temporal part` (3),
`has occurrent part` (2), `location of` and `occupies spatial region` (1 each). The filler is the
owning class itself 18 times (`BFO_0000002 ⊑ ∀ BFO_0000176 . BFO_0000002`), a union containing it
10 times (`BFO_0000026 ⊑ ∀ BFO_0000178 . (BFO_0000018 ⊔ BFO_0000026)`), and another class 3 times
(`BFO_0000029 ⊑ ∀ BFO_0000210 . BFO_0000028`). Three samples of the message:

- `BFO_0000002` (continuant): "Universal restriction on BFO_0000176 does not imply any property
  value."
- `BFO_0000004` (independent continuant): the same, on `BFO_0000176` (continuant part of).
- `BFO_0000008` (temporal region): the same, on `BFO_0000132` (occurrent part of).

These are **debatable, leaning false positive**, all 31. The axioms are deliberate typing
constraints, for example every continuant part of a continuant is a continuant. They are not a
missing existential, so OWL011's premise (that the modeller expected a value to exist) does not
hold. The rule is right that `ObjectAllValuesFrom` holds vacuously (Direct Semantics Table 4), and
it is `info`, so it fails no run by default. But its observed precision on the only corpus where it
fires is about 0%, which is evidence for the #11 audit rather than a reason for comfort. On CCO and RO the same BFO axioms are not reported, because their owning class is a
foreign (BFO) IRI there. That is OWL011's ownership exclusion working as specified.

## Implications for the severity decisions (#11)

The corpus gives no evidence of a false positive in any of the 13 rules, and no count to weigh.
The severity decisions must therefore rest on the specifications alone:

- **OWL019 (error).** The OBO relations themselves are clean, so error costs RO nothing. Where
  OWL019 fires, the ontology violates the OWL 2 DL global restriction of SS 11.2, which is an
  error by the rule's own standard. Nothing here argues for a downgrade.
- **OWL035 (error) on `owl:minCardinality` with `owl:maxCardinality` in one restriction.** No
  data: none of the released files has a cardinality restriction, and the 51 in the candidate
  extensions never pair a minimum with a maximum.
- **SHQ008 (error) on derived integers.** No data. SHACL Core requires an `xsd:integer` value for
  `sh:minCount`, `sh:maxCount`, `sh:minLength` and `sh:maxLength` (SHACL sections 4.2 and 4.4), and a value
  typed `xsd:nonNegativeInteger` is not one *by datatype*. Whether that makes a shapes graph
  ill-formed or only non-portable is the #11 question. The corpus does not answer it.
- **SHQ011 (error, heuristic) on `\/`.** No data either. XML Schema regular expressions do not
  define `\/` (XSD 1.1 Part 2, appendix G), so an XPath `matches()` engine rejects it, while Python
  accepts it. A real shapes corpus is needed before committing to error.

To move these decisions from spec to data, the next corpus should hold ontologies that apply RO
(Uberon, CL, OBI, GO-plus), and SHACL produced by tools rather than by hand. Issue #31 tracks
scripting a pinned corpus and its per-rule counts; widening the corpus to those sources is the
"Real-world counts" item of TODO.md ("Coverage gaps").
