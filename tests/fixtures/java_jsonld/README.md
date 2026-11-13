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
  (a fingerprint, not a model of the printer); and that it loads to the same graph as `pets.ttl`,
  with each node written once;
- only with `ONTOLINT_JENA_HOME` set (CI has no Java, and nothing runs it on a schedule yet, #30):
  that every file of the installation's `lib/`, and its `log4j2.properties`, has the SHA-256 it has
  in the 4.10.0 zip (one digest over the 46 files, so a changed, missing or extra jar fails). The
  test then runs Java itself on exactly those jars, as `bin/riot` would, and never runs `bin/riot`;
  it clears `CLASSPATH`, `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS` and `_JAVA_OPTIONS`, which could
  put another class or an agent ahead of them. It checks that `riot --version` says 4.10.0, then
  that a fresh export of `pets.ttl` equals the file as data and has the same layout. "As data":
  the same context and the same nodes, each written once, with the nodes and each node's values in
  any order (only an `@list` keeps its order).

  This corroborates the files' origin for whoever runs it. It is not enforced. It trusts the JVM
  (`JAVA_HOME`, else `java` on `PATH`), as the tests trust their Python. It does not prove the
  bytes, which neither writer reproduces (see below).

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

Run from any directory: the classes are unpacked into a new temporary directory. Apart from the first
(the call site, with its branch), each command prints a whole method, so the order of its calls shows:

```sh
export JENA_HOME=/path/to/apache-jena-4.10.0
cd "$(mktemp -d)"
unzip -q "$JENA_HOME/lib/jena-arq-4.10.0.jar" 'org/apache/jena/riot/writer/JsonLD10Writer.class'
javap -c -p org/apache/jena/riot/writer/JsonLD10Writer.class | grep -B3 -A3 'JsonUtils.write'
unzip -q "$JENA_HOME/lib/jsonld-java-0.13.4.jar" 'com/github/jsonldjava/utils/JsonUtils.class'
javap -c -p com/github/jsonldjava/utils/JsonUtils.class \
  | sed -n '/writePrettyPrint(java.io.Writer, java.lang.Object)/,/^$/p'
javap -c -p com/github/jsonldjava/utils/JsonUtils.class | sed -n '/static {}/,/^$/p' | grep JsonFactory
unzip -q "$JENA_HOME/lib/jackson-core-2.15.3.jar" \
  'com/fasterxml/jackson/core/base/GeneratorBase.class' 'com/fasterxml/jackson/core/JsonFactory.class'
javap -c -p com/fasterxml/jackson/core/base/GeneratorBase.class \
  | sed -n '/ useDefaultPrettyPrinter()/,/^$/p;/_constructDefaultPrettyPrinter()/,/^$/p'
javap -c -p com/fasterxml/jackson/core/JsonFactory.class \
  | sed -n '/ _createGenerator(java.io.Writer, /,/^$/p' | grep 'Method'
```

What they show (2026-11-13):

- `JsonLD10Writer` calls `writePrettyPrint` when the output is pretty, and `JsonUtils.write` otherwise.
- `writePrettyPrint` calls `createGenerator(Writer)` at offset 4 and `useDefaultPrettyPrinter()` at
  offset 9, with only a store and a load of the generator between them, then `writeObject`.
- `JsonUtils`'s static initialiser makes `JSON_FACTORY` with `new JsonFactory(...)`, the plain class,
  and then only calls `disable` on it, three times.
- `useDefaultPrettyPrinter` keeps a printer already set (`getPrettyPrinter`, `ifnull`), else sets the
  result of `_constructDefaultPrettyPrinter()`, which is `new DefaultPrettyPrinter()`.
- `JsonFactory._createGenerator(Writer, IOContext)` builds a `WriterBasedJsonGenerator` and calls only
  `setHighestNonEscapedChar`, `setCharacterEscapes` and `setRootValueSeparator` on it: it sets no printer.

So the generator `writePrettyPrint` creates has no printer when `useDefaultPrettyPrinter` runs, and gets a
`DefaultPrettyPrinter`. The path was read from the bytecode, not traced at run time.
