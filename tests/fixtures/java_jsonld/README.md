# JSON-LD written by a Java tool

Real output of Apache Jena's `riot`, kept so that the source-region tests read JSON-LD laid out by
Java's Jackson pretty-printer, not only by RDFLib's writer (issue #7).

| File | Written by | Layout |
|------|------------|--------|
| `pets.ttl` | by hand | the input of both exports |
| `pets.jsonld10.jsonld` | Jena's JSON-LD 1.0 writer: jsonld-java 0.13.4, printed by Jackson 2.15.3 (`DefaultPrettyPrinter`) | `"key" : value`, two-space indent, `[ {` and `}, {` |
| `pets.jsonld11.jsonld` | Jena's default JSON-LD writer (1.1: titanium-json-ld 1.3.2) | `"key": value`, four-space indent, one value per line |

Both files are committed as `riot` wrote them; do not reformat them. What the tests check:

- in every run: each file's SHA-256 (the committed bytes, not who wrote them); the traits of its
  writer's layout that the table lists, plus spaces-only indentation and `@context` after `@graph`
  (a fingerprint, not a model of the printer); and that it loads to the same graph as `pets.ttl`;
- only with `ONTOLINT_JENA_HOME` set (CI has no Java): that a fresh `riot` export of `pets.ttl`
  equals the file as data (the same context and the same nodes, in any order) and has the same
  layout. This is the check of provenance that anyone with Jena 4.10.0 can rerun. It does not
  prove the bytes: neither writer reproduces them (see below).

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
`JAVA_DIGESTS` in `tests/test_source_locations.py` together with the files. To check the committed
files against your Jena:

```sh
ONTOLINT_JENA_HOME=/path/to/apache-jena-4.10.0 uv run pytest tests/test_source_locations.py -k riot
```

## Which printer wrote the 1.0 file

Read from the 4.10.0 distribution's own classes with `javap -c -p` (2026-11-13), not from the
layout:

1. `org.apache.jena.riot.writer.JsonLD10Writer` (`lib/jena-arq-4.10.0.jar`) calls
   `com.github.jsonldjava.utils.JsonUtils.writePrettyPrint` when the format is pretty, as
   `--formatted` is.
2. `JsonUtils.writePrettyPrint` (`lib/jsonld-java-0.13.4.jar`) calls
   `com.fasterxml.jackson.core.JsonGenerator.useDefaultPrettyPrinter()`.
3. In `lib/jackson-core-2.15.3.jar` (`Bundle-Version: 2.15.3`), `GeneratorBase.useDefaultPrettyPrinter`
   sets the result of `_constructDefaultPrettyPrinter()`, which is
   `new com.fasterxml.jackson.core.util.DefaultPrettyPrinter`.

```sh
unzip -q lib/jena-arq-4.10.0.jar 'org/apache/jena/riot/writer/JsonLD10Writer.class'
javap -c -p org/apache/jena/riot/writer/JsonLD10Writer.class | grep JsonUtils.writePretty
unzip -q lib/jsonld-java-0.13.4.jar 'com/github/jsonldjava/utils/JsonUtils.class'
javap -c -p com/github/jsonldjava/utils/JsonUtils.class | grep useDefaultPrettyPrinter
unzip -q lib/jackson-core-2.15.3.jar 'com/fasterxml/jackson/core/base/GeneratorBase.class'
javap -c -p com/fasterxml/jackson/core/base/GeneratorBase.class | grep -A6 '_constructDefaultPrettyPrinter()'
```

`useDefaultPrettyPrinter` keeps a printer already set on the generator, but step 2 calls it right
after `JsonFactory.createGenerator(Writer)` with nothing in between, on a factory that `JsonUtils`
configures only by disabling three features. The path was read, not traced at run time.
