"""Single fallback for the package version (a test pins it to ``pyproject.toml``)."""

from __future__ import annotations

from importlib import metadata

FALLBACK_VERSION = "0.5.0"


def package_version() -> str:
    """Return the installed distribution version, or the packaged fallback when not installed."""
    try:
        return metadata.version("ontolint")
    except metadata.PackageNotFoundError:
        return FALLBACK_VERSION
