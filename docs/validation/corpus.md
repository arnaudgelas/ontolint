# The validation corpus

Public ontologies, pinned so that a validation run can be repeated by anyone and compared release to release.
The manifest is [`metric-corpus.json`](metric-corpus.json), the one the METRIC calibration already uses
([metric-calibration.md](metric-calibration.md)); `scripts/corpus.py` reads it. No ontology is committed to this
repository.

```bash
uv run python scripts/corpus.py list              # every source: commit, licence, files, runs
uv run python scripts/corpus.py fetch DIR         # download by commit, verify every file's SHA-256
uv run python scripts/corpus.py verify DIR        # offline: is DIR the pinned tree?
uv run python scripts/corpus.py tree DIR          # `<sha256>  <path>` per file, the same for every fetch
uv run python scripts/corpus.py pin OWNER/REPO COMMIT PATH...   # the `files` block of a new source
```

## What the manifest holds

* `entries`: one file each, pinned by URL and SHA-256 (the METRIC calibration corpus, 21 files). Fetched as
  `DIR/<id>`.
  Twenty of them also name a 40-hex `commit` that appears in their URL. `skos-core.rdf` does not: the W3C namespace
  document is mutable and no archive has these bytes, so it is pinned by checksum alone and `fetch` fails the day the
  W3C changes it (a test lists it as the one exception; a follow-up issue tracks replacing it). "Pinned by commit" is therefore true of
  every `sources` item and of 20 of the 21 entries, not of the whole corpus.
* `sources`: a repository at a commit, with the layout a run needs. Fetched as `DIR/<id>/<path>`.

A source states:

| Key | Rule |
| --- | --- |
| `repository` | `owner/name` on GitHub. |
| `commit` | 40 lower-case hex digits. A branch, a tag, `latest` or a short hash is refused, and the URL is built from the repository, the commit and the path, never read from the manifest (the lesson of [#152](https://github.com/arnaudgelas/ontolint/issues/152)). |
| `licence` | An SPDX identifier from the allow-list in `scripts/corpus.py`; a new one is added in the commit that needs it. |
| `files` | Path in the repository and the SHA-256 of its bytes. `fetch` writes nothing that does not match, and names the source and the file. |
| `runs` | One ontolint command each: `inputs` (files of the source), extra `args`, and the `exit_status` it must end with. `{root}` in an argument is the directory of the source, so an import root, one or two catalogs, `--import-dir` or `--shapes` are named where they are fetched. |

The `cco-umbrella` source is the case that needs both: CCO's `AllCoreOntology.ttl` reaches the eleven modules and
BFO through `../` in `src/cco-merged/catalog-v001.xml`, so its run names `--import-root {root}` and that catalog,
and its second run lints the modules with their own catalog.

## Adding a source

1. `uv run python scripts/corpus.py pin OWNER/REPO COMMIT PATH...` prints the `files` block.
2. Add the source to `sources` with its licence, a note on why it is in the corpus, and its runs.
3. `uv run python scripts/corpus.py fetch DIR` and `verify DIR` on a clean directory; `tests/test_corpus.py` checks
   the manifest offline.

`fetch` is the one step that needs the network. A file already in `DIR` with the right checksum is not downloaded
again, and two fetches give trees that `tree` prints identically.
