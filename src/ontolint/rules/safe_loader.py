"""Specifications for the safe-loader rules, emitted by the CLI front end while it reads input.

``SEC001``, ``SEC002``, ``SEC003``, ``SEC006``, ``SEC009``, ``SEC010``, ``SEC011``, ``SEC013`` and ``SEC015`` are
raised as :class:`ontolint.loader.InputRejected` by :mod:`ontolint.loader` and :mod:`ontolint.imports`
(``module=""``): no graph exists yet when they apply, so there is no ``run(ctx)``.  The other SEC rules
(``SEC004``, ``SEC005``, ``SEC007``, ``SEC008``, ``SEC012``, ``SEC014``, ``SEC016``) are graph rules in
:mod:`ontolint.rules.safety` and :mod:`ontolint.rules.imports_note`.

What every one of them does to the run (``cli._lint``):

* It is a refusal, not a finding.  The CLI prints ``<ID>: <message>`` on stderr, writes no report (nothing on
  stdout, no ``--output`` file, no baseline) and exits ``2`` whatever ``--fail-on`` says.  Every ontology argument
  is still loaded first, so each refused or unparsable input gets its own line; with several inputs a message that
  does not already name the file ends in `` for <file>``.  The ``--shapes`` file is loaded (through the same
  checks) only once every input loaded; a refused ``--catalog`` or ``--import-dir`` folder (``SEC015``) stops the
  run before any input.
* ``--select``, ``--ignore``, profiles, ``ignored_rules`` and ``severity_overrides`` do not affect them: the loader
  never consults the selection.  Naming one in ``--select`` or ``--ignore`` (by id; the mixed ``SEC`` family
  applies to the graph SEC rules only) is therefore a configuration error, ``TOOL001`` and exit ``2`` before any
  input is read, and naming one in ``ignored_rules`` or ``severity_overrides`` is ``GOV020``, exit ``2``.  The
  limits are per document: each ontology argument, the shapes file, each file
  of an ``owl:imports`` closure and each file of an ``--import-dir`` (a refused ``--import-dir`` file is skipped
  with a ``TOOL010`` warning naming it and the refusal, and the run goes on; a ``catalog-v001.xml`` there, and a
  file that does not parse, are skipped silently, since the folder may hold catalogs and non-RDF files).
* Messages name the file by its report path (relative to the working directory, else absolute) and, for a limit,
  its value and policy key; they quote what was refused (a context IRI, a blocked address, an entity name) but never the
  content of a file outside the input: no external entity, context or import is ever read.
* Why ``error`` and ``deterministic``: the run cannot give any verdict on an input it refused, and every trigger is
  an exact comparison of a measured quantity with a configured limit, or a syntactic fact about the bytes.

The rules:

* **SEC001.** Before parsing, the file's size from ``fstat`` exceeds ``max_input_bytes`` (``--max-input-bytes``,
  default 64 MiB = 67108864 bytes), or the file grew past it while being read (at most ``limit + 1`` bytes are
  ever read).  A file of exactly the limit is accepted.  OASIS catalogs (``--catalog`` and every
  ``catalog-v001.xml`` found next to an input or an imported file) are bounded by the same key.
* **SEC002.** While the parser builds the graph, the store holds more than ``max_triples`` (``--max-triples``,
  default 5,000,000) distinct triples, over all named graphs: the parse stops at the first triple past the limit,
  in-process or in the SEC003 worker, so memory is bounded too.  Exactly ``max_triples`` triples are accepted.
  The same key bounds a whole import closure (SEC015).
* **SEC003.** Only when ``max_parse_seconds`` (``--max-parse-seconds``; a number in ``(0, 86400]``; default unset,
  no budget) is set: the parse then runs in a ``spawn`` worker process and the parent waits that many wall-clock
  seconds, counted from the moment the worker reports it is ready (interpreter start-up and imports have their
  own 120 s limit and fail as INPUT001) until its answer arrives.  On expiry the worker is terminated, then killed
  after a 2 s grace.  The budget covers parsing and encoding the graph in the worker; the parent's size,
  compression and DTD checks and its decoding of the answer are not counted.
* **SEC006.** During the parse, rdflib asks to load a JSON-LD ``@context`` that is not inline: a remote IRI, a
  relative or a local file reference alike.  The request is refused without any I/O.  It takes precedence over
  SEC013 when both happened.
* **SEC009.** The path is not acceptable: a relative argument whose normalised path climbs out of the working
  directory with ``..``; a path whose last component is a symlink resolving outside the working directory; a path
  written inside the working directory that reaches a file outside it through a symlinked directory; a file that
  is not a regular file (device, FIFO, socket; checked on the opened descriptor, without blocking); or an
  ``owl:imports`` target that resolves outside the import root (``--import-root``, default the enclosing git
  repository of the catalog or input) after symlinks are followed.  An absolute path outside the working
  directory with no symlink in its last component is explicit user intent and accepted.
* **SEC010.** The detected syntax is RDF/XML (whatever the extension) or the file is an OASIS catalog, and its
  ``DOCTYPE`` (comments removed; UTF-16/32 recognised by BOM or by the bytes of ``<``, else read as Latin-1)
  declares a ``SYSTEM`` or ``PUBLIC`` identifier, an entity whose value references another entity, or entities
  whose references in the document would expand to more than ``max_input_bytes`` characters (value length times
  the number of ``&name;`` references; exactly the limit is accepted).  Plain internal entities, as Protege
  writes them, are accepted.
* **SEC011.** The file's first bytes are a gzip, bzip2, xz, zip, zstd or 7z signature, whatever its extension.
  Checked after SEC001, before the syntax is chosen.
* **SEC013.** During the parse, code called ``socket.socket.connect``, ``connect_ex`` or ``sendto``,
  ``socket.create_connection``, ``socket.getaddrinfo``, ``gethostbyname``, ``gethostbyname_ex`` or
  ``gethostbyaddr``: the call raises, and the attempt is recorded, so a parser that swallows the exception is
  still refused.  The message names the first blocked call.  The guard is active only while a document is
  parsed; SHACL validation and ROBOT (in a container started with ``--network none``) run outside it.
* **SEC015.** With ``--follow-imports``, ``--catalog`` or ``--import-dir``: an imported file would sit deeper
  than ``max_import_depth`` (policy key, default 16; the root's direct imports are at depth 1, so exactly the
  limit is accepted); loading one more file would exceed ``max_imported_files`` (policy key, default 100, the root
  not counted); the merged closure holds more than ``max_triples`` triples after a file is added; or an
  ``--import-dir`` folder holds more than ``max_imported_files`` files with an RDF suffix (counted before any is
  parsed).  Depth and file count have no CLI flag; ``max_triples`` is ``--max-triples``.
"""

from __future__ import annotations

from ontolint.models import RuleBackend, RuleScope, RuleSpec, Severity


def _spec(rule_id: str, title: str, suggestion: str) -> RuleSpec:
    return RuleSpec(
        rule_id, "SEC", title, Severity.ERROR, suggestion, "deterministic", RuleBackend.CLI, RuleScope.INPUT, ""
    )


SPECS: tuple[RuleSpec, ...] = (
    _spec(
        "SEC001",
        "Input file exceeds the size limit",
        "Split the ontology, or raise --max-input-bytes (or max_input_bytes in the policy) if the size is expected.",
    ),
    _spec(
        "SEC002",
        "Input exceeds the triple limit",
        "Lint a smaller module, or raise --max-triples (or max_triples in the policy) if the size is expected.",
    ),
    _spec(
        "SEC003",
        "Parsing exceeds the time budget",
        "Lint a smaller module, or raise --max-parse-seconds (or max_parse_seconds in the policy) if it is expected.",
    ),
    _spec(
        "SEC006",
        "Remote JSON-LD context refused",
        "Inline the @context in the document; ontolint never downloads contexts.",
    ),
    _spec(
        "SEC009",
        "Unsafe input path",
        "Pass a regular file inside the working directory, not a device, a '..' escape or a link leaving it.",
    ),
    _spec(
        "SEC010",
        "RDF/XML unsafe DTD or entity refused",
        "Remove SYSTEM/PUBLIC identifiers and nested entities; plain internal entities (Protege style) are accepted.",
    ),
    _spec(
        "SEC011",
        "Compressed input refused",
        "Decompress the file yourself and pass the plain RDF serialization.",
    ),
    _spec(
        "SEC013",
        "Network access attempted while disabled",
        "Make the input self-contained; ontolint runs with the network disabled and never fetches resources.",
    ),
    _spec(
        "SEC015",
        "Import closure exceeds its limits",
        "Lint a smaller closure, or raise max_import_depth, max_imported_files or max_triples in the policy if the "
        "size is expected.",
    ),
)
