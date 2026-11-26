# What Apache Jena does with the SHACL values behind SHQ008, SHQ011 and SHQ015

`docs/severity-decisions.md` ("Engine checks") sets the severity of three SHQ rules from what engines do with a value:
`sh:pattern` `\/` and `[]a]` (accepted by pySHACL and Jena; invalid XPath: **warning**), `[[a]` (Jena refuses: **error**),
an unknown `sh:flags` letter (Jena refuses: **error**) and a derived integer type under `sh:minCount` (Jena accepts it,
pySHACL refuses the shapes graph: **error**, kept). Only pySHACL's behaviour was a test. This directory commits the Jena side.

Each `*.ttl` is a one-property shapes graph that is its own data (`ex:n` is the target node), exactly as it was run:

```sh
"$JENA_HOME/bin/shacl" validate --shapes F.ttl --data F.ttl
```

`cases.json` records, per file, what Jena 4.10.0 did (exit status, `conforms` or `violations` or `error` and the message)
and what ontolint reports for it (`SHQ008`, `SHQ011` and `SHQ015` with their severities). `pattern_violation_control` is a
control: a pattern that the value does not match, so that "conforms" elsewhere is not "never checks".

`tests/test_jena_shacl.py` checks:

- in every run, without Java: that every file is listed and every listed file exists, and that ontolint still reports what
  the case records (so a change of a rule's severity must change the record, and with it the evidence behind the decision);
- only with `ONTOLINT_JENA_HOME` set (`.github/workflows/jena.yml` sets it every Monday): that Jena, run on the jars whose
  digests `tests/jena_support.py` checks, still gives the recorded exit status, outcome and message. A Jena upgrade that
  changes one fails visibly.

## Regenerating

Run the command above with Apache Jena 4.10.0 (see `tests/fixtures/java_jsonld/README.md` for the archive and its SHA-512)
on each file, update `cases.json` with what it printed, and run `ONTOLINT_JENA_HOME=... uv run pytest tests/test_jena_shacl.py`.
A change of what Jena does is a change of the evidence of `docs/severity-decisions.md`: say so there too. A change of a rule's severity edits only the `ontolint` half of a record, and its rationale goes in `docs/severity-decisions.md` ("Limits of this record").

## Limits

One Jena version (4.10.0, the last that runs on Java 11) and one value per rule form. pySHACL's side is
`tests/test_shacl_evidence.py`. TopBraid and the OWL API were not run.
