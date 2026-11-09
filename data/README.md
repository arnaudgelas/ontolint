# Crosswalk data

`OOPS_crosswalk.csv` and `OntoSniff_crosswalk.csv` map the entries of two published catalogues of
ontology pitfalls to ontolint rule IDs. They are traceability aids, not claims of identical
behaviour. `rule_catalogue.csv` is ontolint's own catalogue (a copy ships in
`src/ontolint/data/`).

## Sources and attribution

| File | Source | What is reused | Licence of the source |
| --- | --- | --- | --- |
| `OOPS_crosswalk.csv` | OOPS! pitfall catalogue, <https://oops.linkeddata.es/catalogue.jsp> (revision of April 2023, read 2026-11-09) | the pitfall identifiers `P01`-`P41` only | none stated for the catalogue; the OOPS! software is Apache-2.0 (<https://github.com/oeg-upm/OOPS>) |
| `OntoSniff_crosswalk.csv` | OntoSniff anti-pattern catalogue in OntoInk, <https://ise-fizkarlsruhe.github.io/ontoink/ontosniff/> (read 2026-11-09) | the smell numbers 1-17 and their short names | none stated for the documentation (© 2026 ISE – FIZ Karlsruhe); the OntoInk code is MIT |

The `pitfall` column paraphrases each OOPS! pitfall in ontolint's own words; the official titles
are on the catalogue page. The `smell` column gives OntoSniff's short names (one to three words
each) so that entries can be matched. No descriptions or other text from either catalogue are
copied. The `coverage`, `our_rule_ids` and `caveat` columns are ontolint's own and are covered by
this repository's Apache-2.0 licence.

Please cite the sources when you use these mappings:

- Poveda-Villalón, M., Gómez-Pérez, A. and Suárez-Figueroa, M. C. (2014). OOPS! (OntOlogy Pitfall
  Scanner!): An On-line Tool for Ontology Evaluation. *International Journal on Semantic Web and
  Information Systems* 10(2), 7–34.
- Norouzi, E. (2026). *OntoInk: Interactive Ontology Visualization, SHACL Validation, and Live TTL
  Editing for MkDocs* (version 0.8.0) [computer software]. <https://github.com/ISE-FIZKarlsruhe/ontoink>
