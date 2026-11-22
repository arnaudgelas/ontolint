"""The validation corpus: public ontologies pinned by commit and checksum, fetched reproducibly (issue #167).

    uv run python scripts/corpus.py list                       # every source, its commit, licence and runs
    uv run python scripts/corpus.py fetch DIR                  # download every file by commit, verify its SHA-256
    uv run python scripts/corpus.py verify DIR                 # check the files in DIR against the manifest (offline)
    uv run python scripts/corpus.py tree DIR                   # the hash manifest of DIR: ``<sha256>  <path>`` lines
    uv run python scripts/corpus.py pin OWNER/REPO COMMIT PATH...   # the ``files`` block for a new source

The corpus of ``TODO.md`` ("Real-world ontologies") was used by hand.  This module makes it a manifest, the one of
``scripts/metric_corpus.py`` (``docs/validation/metric-corpus.json``): its ``entries`` are single files pinned by
URL and checksum (the METRIC calibration corpus), its ``sources`` are the repositories whose layout a run needs
(an import root, one or two catalogs, shapes).  Nothing is vendored: ``fetch`` writes into a directory of your
own, and refuses what it cannot verify.

A source names its ``repository`` (``owner/name`` on GitHub), a 40-hex ``commit``, an SPDX ``licence`` from
:data:`LICENCES`, its ``files`` (a path in the repository and the SHA-256 of its bytes) and its ``runs``: the
inputs and the extra ontolint arguments of one command, and the exit status it must end with.  ``{root}`` in an
argument stands for the directory of the source, so a catalog or an import root is named where it is fetched.
Every URL is built here from the repository, the commit and the path, never read from the manifest, so a source
cannot name a branch, a tag or a "latest" URL (the lesson of issue #152); a manifest that tries a ``ref``, a ``url``
or a commit that is not 40 hex digits is refused.  ``load`` refuses a path that is not a plain relative one, so a
manifest cannot make ``fetch`` write outside DIR, and an id used twice.

A file already in DIR with the right checksum is not downloaded again.  ``fetch`` writes by renaming a new file into
place, and refuses a directory of the tree that is a symbolic link, so it never writes through one.  Two ``fetch``
runs give trees that ``tree`` prints identically.
"""

# ruff: noqa: S310 -- downloads HTTPS URLs built from a pinned commit and checks every file's SHA-256

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "docs" / "validation" / "metric-corpus.json"
COMMIT = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
RAW_URL = "https://raw.githubusercontent.com/{repository}/{commit}/{path}"
LICENCES = frozenset(
    {
        "Apache-2.0",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "CC-BY-2.0",
        "CC-BY-3.0",
        "CC-BY-4.0",
        "CC-BY-SA-3.0",
        "CC-BY-SA-4.0",
        "CC0-1.0",
        "EPL-2.0",
        "MIT",
        "MPL-2.0",
        "W3C-20150513",
    }
)
"""The SPDX identifiers a corpus file may be under: permissive or share-alike licences that allow it to be fetched and
linted.  A new licence is added here, in the same commit as the source that needs it, so a reviewer sees it."""
KEYS = frozenset({"id", "repository", "commit", "licence", "files", "runs", "note"})
RUN_KEYS = frozenset({"name", "inputs", "args", "exit_status"})
EXIT_STATUSES = (0, 1, 2)
Opener = Callable[[str], IO[bytes]]


class CorpusError(SystemExit):
    """A refusal that ends the command with its message and a non-zero status."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


@dataclass(frozen=True)
class Run:
    """One ontolint command on a source: ``inputs`` (paths in the source), extra ``args`` and the expected exit."""

    name: str
    inputs: tuple[str, ...]
    args: tuple[str, ...]
    exit_status: int


@dataclass(frozen=True)
class Source:
    """A set of files of one repository at one commit, and the commands that lint them."""

    id: str
    repository: str | None
    commit: str | None
    licence: str
    files: Mapping[str, str]  # path in the source -> SHA-256
    runs: tuple[Run, ...]
    url: str | None = None  # a single-file entry of the METRIC corpus: its URL (a source builds its own)

    @property
    def flat(self) -> bool:
        """Whether this is a single file of the METRIC corpus, kept as ``DIR/<id>`` (a source is ``DIR/<id>/...``)."""
        return self.repository is None

    def root(self, directory: Path) -> Path:
        return directory if self.flat else directory / self.id

    def location(self, path: str) -> str:
        if self.url is not None:
            return self.url
        return RAW_URL.format(repository=self.repository, commit=self.commit, path=urllib.parse.quote(path))

    def command(self, directory: Path, run: Run) -> list[str]:
        """The ontolint arguments of ``run``: its inputs and arguments, with ``{root}`` the directory of the source."""
        root = str(self.root(directory))
        return [
            *(str(self.root(directory) / name) for name in run.inputs),
            *(arg.replace("{root}", root) for arg in run.args),
        ]


def _plain_path(source: str, path: object) -> str:
    """``path`` if it is a relative path of plain segments, so that ``DIR / id / path`` stays inside ``DIR / id``."""
    if (
        not isinstance(path, str)
        or not path
        or path.startswith("/")
        or "\\" in path
        or any(part in ("", ".", "..") for part in path.split("/"))
        or re.match(r"[A-Za-z]:", path)
    ):
        raise ValueError(f"{source}: {path!r} is not a plain relative path (no '..', no leading '/', no backslash)")
    return path


def _plain_id(name: object) -> str:
    if (
        not isinstance(name, str)
        or not name
        or name in (".", "..")
        or "/" in name
        or "\\" in name
        or name.startswith(".")
    ):
        raise ValueError(f"{name!r}: a corpus id must be a plain name, without a directory, '..' or a leading '.'")
    return name


def _run(source: str, item: Mapping[str, Any], files: Mapping[str, str]) -> Run:
    extra = set(item) - RUN_KEYS
    if extra or not RUN_KEYS - {"args"} <= set(item):
        raise ValueError(f"{source}: a run has {sorted(RUN_KEYS)} (args optional), not {sorted(item)}")
    inputs = tuple(_plain_path(source, p) for p in item["inputs"])
    if not inputs or not set(inputs) <= set(files):
        raise ValueError(f"{source}: run {item['name']!r} names inputs that are not files of the source")
    args = tuple(item.get("args", ()))
    if not all(isinstance(a, str) for a in args):
        raise ValueError(f"{source}: run {item['name']!r}: every argument is a string")
    if item["exit_status"] not in EXIT_STATUSES:
        raise ValueError(f"{source}: run {item['name']!r}: exit_status is one of {EXIT_STATUSES}")
    return Run(str(item["name"]), inputs, args, int(item["exit_status"]))


def source_of(item: Mapping[str, Any]) -> Source:
    """Validate one ``sources`` item: a pinned repository, an allowed licence, plain paths, runs on its own files."""
    name = _plain_id(item.get("id"))
    extra = set(item) - KEYS
    if extra:
        raise ValueError(f"{name}: unknown keys {sorted(extra)}; a source is pinned by repository and commit only")
    repository, commit = item.get("repository"), item.get("commit")
    if not isinstance(repository, str) or not REPOSITORY.fullmatch(repository):
        raise ValueError(f"{name}: the repository is 'owner/name'")
    if not isinstance(commit, str) or not COMMIT.fullmatch(commit):
        raise ValueError(f"{name}: the commit is 40 lower-case hex digits, never a branch, a tag or 'latest'")
    if item.get("licence") not in LICENCES:
        raise ValueError(f"{name}: the licence {item.get('licence')!r} is not one of {sorted(LICENCES)}")
    raw_files = item.get("files")
    if not isinstance(raw_files, Mapping) or not raw_files:
        raise ValueError(f"{name}: a source lists its files")
    files: dict[str, str] = {}
    for path, digest in raw_files.items():
        files[_plain_path(name, path)] = digest
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            raise ValueError(f"{name}: the SHA-256 of {path} must be 64 lower-case hex digits")
    runs = tuple(_run(name, run, files) for run in item.get("runs", ()))
    if not runs:
        raise ValueError(f"{name}: a source has at least one run")
    return Source(name, repository, commit, str(item["licence"]), files, runs)


def entry_source(item: Mapping[str, Any]) -> Source:
    """One single-file ``entries`` item of the METRIC corpus as a source: one file, linted with no extra argument."""
    name = _plain_id(item.get("id"))
    licence = item.get("licence")
    if licence not in LICENCES:
        raise ValueError(f"{name}: the licence {licence!r} is not one of {sorted(LICENCES)}")
    digest, url = item.get("sha256"), item.get("url")
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        raise ValueError(f"{name}: the SHA-256 must be 64 lower-case hex digits")
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError(f"{name}: the URL must use https")
    commit = item.get("commit")
    if commit is not None and (not isinstance(commit, str) or not COMMIT.fullmatch(commit) or f"/{commit}/" not in url):
        raise ValueError(f"{name}: the commit must be 40 hex digits and appear in the URL")
    return Source(name, None, commit, str(licence), {name: digest}, (Run("default", (name,), (), 0),), url)


def load(path: Path = MANIFEST) -> list[Source]:
    """Every source of the manifest, the single-file entries first; an id given twice is refused."""
    data = json.loads(path.read_text(encoding="utf-8"))
    sources = [entry_source(item) for item in data.get("entries", ())]
    sources += [source_of(item) for item in data.get("sources", ())]
    seen: set[str] = set()
    for source in sources:
        if source.id in seen:
            raise ValueError(f"{source.id}: the id appears twice")
        seen.add(source.id)
    return sources


def sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _target(directory: Path, source: Source, path: str) -> Path:
    """Where ``path`` of ``source`` is kept; refuses a directory of the tree that is a symbolic link."""
    target = source.root(directory) / path
    probe = directory
    for part in target.relative_to(directory).parts[:-1]:
        probe /= part
        if probe.is_symlink():
            raise CorpusError(f"{source.id}: {probe} is a symbolic link; remove it")
    return target


def _read(target: Path) -> bytes | None:
    try:
        if target.is_symlink() or not target.is_file():
            return None
        return target.read_bytes()
    except OSError:
        return None


def _download(open_url: Opener, url: str, what: str) -> bytes:
    """The bytes at ``url``; a network or HTTP failure ends the command naming ``what`` and the URL."""
    try:
        with open_url(url) as response:
            return response.read()
    except (urllib.error.URLError, OSError) as error:
        raise CorpusError(f"{what}: cannot download {url}: {error}") from None


def fetch(directory: Path, sources: Sequence[Source], opener: Opener | None = None) -> list[str]:
    """Download every file of ``sources`` into ``directory``; return what was downloaded, ``<id>: <path>`` each.

    A file whose checksum differs from the manifest's is never written: the command ends naming the source and the
    file.  ``opener`` takes a URL and returns a readable file (``urllib.request.urlopen`` by default).
    """
    open_url = opener or (lambda url: urllib.request.urlopen(url, timeout=120))
    fetched: list[str] = []
    directory.mkdir(parents=True, exist_ok=True)
    for source in sources:
        for path, expected in source.files.items():
            target = _target(directory, source, path)
            current = _read(target)
            if current is not None and sha256(current) == expected:
                continue
            body = _download(open_url, source.location(path), f"{source.id}: {path}")
            digest = sha256(body)
            if digest != expected:
                raise CorpusError(
                    f"{source.id}: {path}: SHA-256 {digest} differs from the manifest's {expected} "
                    f"({source.location(path)})"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".fetch-", delete=False) as handle:
                handle.write(body)
            try:
                os.replace(handle.name, target)
            except OSError:
                Path(handle.name).unlink()
                raise
            fetched.append(f"{source.id}: {path}")
    return fetched


def verify(directory: Path, sources: Sequence[Source]) -> list[str]:
    """What is wrong with ``directory``, one line per missing or altered file; empty when it is the pinned tree."""
    problems: list[str] = []
    for source in sources:
        for path, expected in source.files.items():
            body = _read(_target(directory, source, path))
            if body is None:
                problems.append(f"{source.id}: {path}: missing")
            elif sha256(body) != expected:
                problems.append(f"{source.id}: {path}: SHA-256 {sha256(body)} differs from the manifest's {expected}")
    return problems


def tree(directory: Path, sources: Sequence[Source]) -> list[str]:
    """The pinned tree as it is in ``directory``: ``<sha256>  <id>/<path>`` per file, sorted, missing files refused."""
    lines: list[str] = []
    for source in sources:
        for path in sorted(source.files):
            body = _read(_target(directory, source, path))
            if body is None:
                raise CorpusError(f"{source.id}: {path}: missing; run fetch first")
            lines.append(f"{sha256(body)}  {path if source.flat else f'{source.id}/{path}'}")
    return sorted(lines, key=lambda line: line.split("  ", 1)[1])


def pin(repository: str, commit: str, paths: Sequence[str], opener: Opener | None = None) -> dict[str, str]:
    """The ``files`` block of a new source: each path of ``repository`` at ``commit`` with the SHA-256 of its bytes."""
    if not REPOSITORY.fullmatch(repository) or not COMMIT.fullmatch(commit):
        raise CorpusError("pin takes OWNER/REPO and a 40-hex commit, not a branch or a tag")
    open_url = opener or (lambda url: urllib.request.urlopen(url, timeout=120))
    files: dict[str, str] = {}
    for path in paths:
        url = RAW_URL.format(
            repository=repository, commit=commit, path=urllib.parse.quote(_plain_path(repository, path))
        )
        files[path] = sha256(_download(open_url, url, f"{repository}: {path}"))
    return dict(sorted(files.items()))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The pinned validation corpus (issue #167).")
    parser.add_argument("command", choices=("list", "fetch", "verify", "tree", "pin"))
    parser.add_argument(
        "arguments", nargs="*", help="DIR for fetch, verify and tree; OWNER/REPO COMMIT PATH... for pin"
    )
    args = parser.parse_args(argv)
    if args.command == "pin":
        if len(args.arguments) < 3:  # noqa: PLR2004 -- a repository, a commit and a path
            parser.error("pin needs OWNER/REPO COMMIT PATH...")
        print(json.dumps(pin(args.arguments[0], args.arguments[1], args.arguments[2:]), indent=2))
        return 0
    sources = load()
    if args.command == "list":
        for source in sources:
            where = "" if source.flat else f"{source.repository}@{source.commit[:12] if source.commit else ''} "
            names = [r.name for r in source.runs]
            print(f"{source.id}: {where}{source.licence}, {len(source.files)} file(s), runs: {names}")
        return 0
    if len(args.arguments) != 1:
        parser.error(f"{args.command} needs one directory")
    directory = Path(args.arguments[0])
    if args.command == "fetch":
        for line in fetch(directory, sources):
            print(line, flush=True)
        return 0
    if args.command == "verify":
        problems = verify(directory, sources)
        print("\n".join(problems) if problems else "the corpus is the pinned one")
        return 1 if problems else 0
    print("\n".join(tree(directory, sources)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
