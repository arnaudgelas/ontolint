# JSON-LD written by a Java tool

Real output of Apache Jena's `riot`, kept so that the source-region tests read JSON-LD laid out by
Java's Jackson pretty-printer, not only by RDFLib's writer (issue #7).

| File | Written by | Layout |
|------|------------|--------|
| `pets.ttl` | by hand | the input of both exports |
| `pets.jsonld10.jsonld` | Jena's JSON-LD 1.0 writer: jsonld-java 0.13.4, printed by Jackson 2.15.3 (`DefaultPrettyPrinter`) | `"key" : value`, two-space indent, `[ {` and `}, {` |
| `pets.jsonld11.jsonld` | Jena's default JSON-LD writer (1.1: titanium-json-ld 1.3.2) | `"key": value`, four-space indent, one value per line |

Both files are committed as `riot` wrote them; do not reformat them. The tests pin their SHA-256,
check each writer's layout as the table gives it, and check that each parses to the same graph as
`pets.ttl`. Only the last two can be checked by anyone: that the bytes came from `riot` rests on
this README, and a rerun does not reproduce them (see below).

## Regenerating

Apache Jena 4.10.0 (the last release that runs on Java 11), binary distribution
`apache-jena-4.10.0.zip` from <https://archive.apache.org/dist/jena/binaries/>, SHA-512
`dff0de98ca829f90cda3b8ec2c665414444e9d7b546c049160f2ffcf822750fa77c8e76d083aaa2c9d926303fb2653250097fcded59a49e968814930537eead9`
(checked against the `.sha512` file published next to it). Run with Temurin OpenJDK 11.0.33:

```sh
export JENA_HOME=/path/to/apache-jena-4.10.0
"$JENA_HOME/bin/riot" --formatted=JSONLD10 pets.ttl > pets.jsonld10.jsonld
"$JENA_HOME/bin/riot" --formatted=JSONLD pets.ttl > pets.jsonld11.jsonld
```

Neither writer is deterministic: a rerun may list the `@context` members (1.0) or the `@graph` nodes
(1.1) in another order (checked on 2026-11-13: three 1.1 runs gave two different files). The graph and
the layout stay the same, so a regenerated file passes every test but the digest one: update
`JAVA_DIGESTS` in `tests/test_source_locations.py` together with the files.
