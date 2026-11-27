"""Pinned public repositories for the corpus counts of issues #195 and #196.

A manifest names each repository by https URL, 40-hex commit, licence and, optionally, the directories to check out
(``paths``: a sparse checkout for a repository whose data is a small part of it).  Nothing is vendored: ``fetch``
checks each repository out at its commit and refuses a checkout whose ``HEAD`` differs, since a commit hash covers
every byte under it.  A sparse checkout is cone mode, so ``paths`` are directories.
"""

# ruff: noqa: S603, S607 -- runs git on fixed HTTPS URLs and a commit hash of the manifest.

from __future__ import annotations

import json
import re
import subprocess
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
