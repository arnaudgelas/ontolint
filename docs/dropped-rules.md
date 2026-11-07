# Dropped rules

These catalogue entries were removed because they cannot be specified soundly, or because another rule
already covers them. They are listed here so the decision stays visible.

| Rule | Reason |
| --- | --- |
| ALIGN008 | not decidable in one file: mapping provenance normally lives in a separate SSSOM file |
| COMP003 | duplicate of GOV008 (a deprecated term without a replacement) |
| COMP009 | subjective: "meaning changed" has no sound offline definition |
| CQ011 | needs entailment: whether a question depends on inferences that are not materialised is not decidable by a SPARQL runner alone |
| GOV019 | not decidable offline: licence compatibility needs the imported ontologies and a policy table |
| SEM008 | duplicate of SEM002: an individual in disjoint classes makes the ontology inconsistent |
| SEM009 | too vague to specify: "unintended inferred types" depends on author intent |
| SEM010 | too vague to specify: "unexpected inferences" depends on author intent |
| SEM011 | overlaps SEM002: a violated cardinality restriction is an inconsistency |
| SEM012 | duplicate of SEM002: a violated disjointness axiom makes the ontology inconsistent |
| SEM013 | rare and reasoner-specific: needs a complete datatype reasoner (HermiT) and gives no actionable fix |
| SEM015 | duplicate of SEM001, which already validates the EL, QL, RL and DL profiles |
| SEM016 | too vague to specify: no defensible threshold for an inferred hierarchy that is "too large" |
