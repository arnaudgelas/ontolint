"""Pinned public repositories, and reading their RDF files, for the corpus counts of issues #195 and #196.

A manifest names each repository by https URL, 40-hex commit, licence and, optionally, the directories to check out
(``paths``: a sparse checkout for a repository whose data is a small part of it).  Nothing is vendored: ``fetch``
checks each repository out at its commit and refuses a checkout whose ``HEAD`` differs, since a commit hash covers
every byte under it.  A sparse checkout is cone mode, so ``paths`` are directories.

The callers are ``scripts/owl_restriction_count.py`` and ``scripts/skos_preflabel_count.py``: a change here is a change
to the evidence of both, so both ``check`` commands (and their tests) must stay green, and a third counter extends the
list.
"""

# ruff: noqa: S603, S607 -- runs git on fixed HTTPS URLs and a commit hash of the manifest.

from __future__ import annotations

import json
import logging
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

COMMIT = re.compile(r"[0-9a-f]{40}")
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
PATH = re.compile(r"[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*")


def load_manifest(path: Path) -> list[dict[str, Any]]:
    """The repositories of a manifest; refuses one that is not pinned to a commit, licensed or safely named."""
    repositories: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))["repositories"]
    seen: set[str] = set()
    for repo in repositories:
        if not ID.fullmatch(repo["id"]) or repo["id"] in seen:
            raise ValueError(f"{repo['id']!r}: an id is a plain file name, given once")
        seen.add(repo["id"])
        if not repo["url"].startswith("https://") or not COMMIT.fullmatch(repo["commit"]) or not repo["licence"]:
            raise ValueError(f"{repo['id']}: a repository has an https URL, a 40-hex commit and a licence")
        for directory in repo.get("paths", []):
            if not PATH.fullmatch(directory) or ".." in directory.split("/"):
                raise ValueError(f"{repo['id']}: {directory!r} is not a relative directory without '..'")
    return repositories


def fetch(directory: Path, repositories: list[dict[str, Any]]) -> None:
    """Check every repository out at its commit into ``directory/<id>`` unless that commit is already there."""
    for repo in repositories:
        target = directory / repo["id"]
        if not (target / ".git").is_dir():
            target.mkdir(parents=True, exist_ok=True)
            paths = repo.get("paths", [])
            steps = [["init", "-q"]]
            if paths:
                steps.append(["sparse-checkout", "set", "--cone", *paths])
            steps += [
                [
                    "fetch",
                    "-q",
                    "--depth",
                    "1",
                    *(["--filter=blob:none"] if paths else []),
                    repo["url"],
                    repo["commit"],
                ],
                ["checkout", "-q", "FETCH_HEAD"],
            ]
            for argv in steps:
                subprocess.run(["git", "-C", str(target), *argv], check=True)
        head = subprocess.run(
            ["git", "-C", str(target), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
        if head != repo["commit"]:
            raise SystemExit(f"{repo['id']}: checked out {head}, the manifest pins {repo['commit']}")
        print(f"{repo['id']}: {head}", flush=True)


# --- reading the RDF files of a checkout (shared by the counting scripts) --------------------------------------------

MAX_BYTES = 5 * 1024 * 1024
FORMATS = {".owl": "xml", ".rdf": "xml", ".xml": "xml", ".ttl": "turtle", ".n3": "n3", ".nt": "nt"}


def rdf_files(root: Path, max_bytes: int = MAX_BYTES) -> list[Path]:
    """The RDF files under ``root`` outside ``.git``, sorted, none a link or over ``max_bytes``."""
    return sorted(
        p
        for p in root.rglob("*")
        if p.suffix.lower() in FORMATS
        and ".git" not in p.parts
        and p.is_file()
        and not p.is_symlink()
        and p.stat().st_size <= max_bytes
    )


def skipped_files(root: Path, max_bytes: int = MAX_BYTES) -> list[str]:
    """The files named like RDF that :func:`rdf_files` leaves out (over the size cap or links), relative to ``root``."""
    read = set(rdf_files(root, max_bytes))
    return sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.suffix.lower() in FORMATS and ".git" not in p.parts and p not in read
    )


def read_repository(
    root: Path, count_graph: Callable[[Any], dict[str, Any] | None], max_bytes: int = MAX_BYTES
) -> dict[str, Any]:
    """Parse every RDF file of ``root`` and keep ``count_graph`` of those it counts (not ``None``).

    A file rdflib cannot read in the format its name says is counted as unparsed, one the cap or a link leaves out is
    listed as skipped: no file named like RDF disappears from the record.
    """
    from rdflib import Graph  # noqa: PLC0415

    files: dict[str, dict[str, Any]] = {}
    parsed = unparsed = 0
    # rdflib logs a lexical form it cannot convert; the corpus is data, not ours.  The caller's logging is restored.
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        for path in rdf_files(root, max_bytes):
            graph = Graph()
            try:
                graph.parse(path, format=FORMATS[path.suffix.lower()])
            except Exception:  # noqa: BLE001 -- not RDF that rdflib reads in the format its name says: unparsed
                unparsed += 1
                continue
            parsed += 1
            if (counted := count_graph(graph)) is not None:
                files[path.relative_to(root).as_posix()] = counted
    finally:
        logging.disable(previous)
    return {"parsed": parsed, "unparsed": unparsed, "skipped": skipped_files(root, max_bytes), "files": files}
