"""Input-path handling: deterministic, de-duplicated, platform-independent report paths.

The pure functions take :class:`~pathlib.PurePath` objects so Windows behaviour (drive
letters, backslashes, case-insensitive comparison) can be tested on any platform with
:class:`~pathlib.PureWindowsPath`.  Report paths are POSIX-style and relative to the
working directory when the file lives beneath it; otherwise they are absolute.  Shell
globbing is the shell's job; directories are rejected rather than walked.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePath
from urllib.parse import quote


@dataclass(frozen=True)
class InputFile:
    """One ontology input: the path to read plus its normalised report identity."""

    path: Path
    display: str
    uri: str
    escapes_root: bool = False
    """True for a relative argument that climbs out of the working directory (``../x.ttl``)."""


def _relative(path: PurePath, root: PurePath) -> PurePath | None:
    """Return ``path`` relative to ``root`` when it is beneath it (Windows: case-insensitively)."""
    if not path.is_absolute():
        return path
    try:
        return path.relative_to(root)
    except ValueError:
        return None


def display_path(path: PurePath, root: PurePath) -> str:
    """POSIX-style path used in text, JSON and fingerprints (relative to ``root`` when beneath it)."""
    relative = _relative(path, root)
    return (relative or path).as_posix()


def _file_uri(path: PurePath) -> str:
    """``file:`` URI for an absolute path (drive letters become ``file:///C:/...``, UNC ``file://host/...``)."""
    posix = quote(path.as_posix(), safe="/:")
    if posix.startswith("//"):
        return f"file:{posix}"
    return f"file://{posix}" if posix.startswith("/") else f"file:///{posix}"


def artifact_uri(path: PurePath, root: PurePath) -> str:
    """URI reference for SARIF: percent-encoded relative path, or a ``file:`` URI when outside ``root``."""
    relative = _relative(path, root)
    if relative is None:
        return _file_uri(path)
    return quote(relative.as_posix(), safe="/")


def file_identity(path: Path) -> tuple[object, ...]:
    """Identify the underlying file so aliases (case, symlinks, hard links) de-duplicate."""
    try:
        stat = path.stat()
    except OSError:
        return ("path", os.path.normcase(os.path.abspath(path)))
    return ("file", stat.st_dev, stat.st_ino)


def resolve_inputs(raw: list[str], cwd: Path) -> list[InputFile]:
    """Turn command-line ontology paths into unique inputs ordered by report path.

    Paths are made absolute and lexically normalised (symlinks are not followed for naming).
    Aliases of one file (``./a.ttl``, a symlink, a different-case spelling on a case-insensitive
    file system) collapse to the alphabetically first spelling, so the result never depends on
    argument order.  Directories raise :class:`IsADirectoryError`.  Missing files are kept so that
    parsing reports them as input failures with the usual message.
    """
    unique: dict[tuple[object, ...], InputFile] = {}
    for text in raw:
        path = Path(os.path.normpath(cwd / text))
        if path.is_dir():
            raise IsADirectoryError(f"{text} is a directory; pass explicit files (shell globbing is not performed)")
        escapes = not Path(text).is_absolute() and _relative(path, cwd) is None
        item = InputFile(path, display_path(path, cwd), artifact_uri(path, cwd), escapes)
        key = file_identity(path)
        if key not in unique or item.display < unique[key].display:
            unique[key] = item
    return sorted(unique.values(), key=lambda x: x.display)
