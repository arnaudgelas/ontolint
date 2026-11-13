# JSON-LD written by a Java tool

Real output of Apache Jena's `riot`, kept so that the source-region tests read JSON-LD laid out by
Java's Jackson pretty-printer, not only by RDFLib's writer (issue #7).

| File | Written by | Layout |
|------|------------|--------|
| `pets.ttl` | by hand | the input of both exports |
| `pets.jsonld10.jsonld` | Jena's JSON-LD 1.0 writer: jsonld-java 0.13.4, printed by Jackson 2.15.3 (`DefaultPrettyPrinter`) | `"key" : value`, two-space indent, `[ {` and `}, {` |
| `pets.jsonld11.jsonld` | Jena's default JSON-LD writer (1.1: titanium-json-ld 1.3.2) | `"key": value`, four-space indent, one value per line |

Both files are byte for byte what `riot` wrote; do not reformat them.

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

The JSON-LD 1.1 output was the same on every run. The JSON-LD 1.0 writer builds its `@context` from a
Java hash map, so a new run may list the `@context` members in another order; the tests do not
depend on that order.
