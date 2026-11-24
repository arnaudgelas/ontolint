"""Run Apache Jena 4.10.0's own jars from an unpacked distribution, after checking every file (``ONTOLINT_JENA_HOME``).

Shared by the tests that need Java (``test_source_locations.py``: ``riot``; ``test_jena_shacl.py``: ``shacl validate``).
What runs comes from the apache-jena-4.10.0.zip whose SHA-512 the README of ``tests/fixtures/java_jsonld`` gives: the
SHA-256 of each file of ``lib/`` and of ``log4j2.properties``, one "path digest" line each, sorted, must give the
digest below.  The tests run Java on exactly these files, as ``bin/riot`` or ``bin/shacl`` would, so they depend
neither on those scripts nor on ``CLASSPATH``.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

JENA_FILES_DIGEST = "b468c814526d32dfd6d98581aa8fcf4c9c9779017b1dfacaaff89fd9ec150f6d"
JENA_FILES_COUNT = 46
# Read by the JVM at start-up: each could add a class or an agent ahead of the verified jars.
JVM_ENVIRONMENT = ("CLASSPATH", "JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS")


def jena_files(home: Path) -> list[Path]:
    """The jars and the logging configuration of ``home``, after checking that they are the distribution's."""
    files = [*sorted((home / "lib").iterdir()), home / "log4j2.properties"]
    listing = "".join(f"{f.relative_to(home).as_posix()} {hashlib.sha256(f.read_bytes()).hexdigest()}\n" for f in files)
    assert (len(files), hashlib.sha256(listing.encode()).hexdigest()) == (JENA_FILES_COUNT, JENA_FILES_DIGEST)
    return files


def run_jena(home: Path, main_class: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run ``main_class`` of the verified jars with the JVM of JAVA_HOME or else of PATH; stderr is kept apart."""
    *jars, logging = jena_files(home)
    java = Path(os.environ["JAVA_HOME"]) / "bin" / "java" if "JAVA_HOME" in os.environ else shutil.which("java")
    assert java is not None, "no java on PATH and no JAVA_HOME"
    argv = [str(java), f"-Dlog4j.configurationFile={logging.as_uri()}", "-cp", os.pathsep.join(map(str, jars))]
    return subprocess.run(  # noqa: S603 -- the maintainer's own JVM, on jars whose digests were just checked
        [*argv, main_class, *args],
        capture_output=True,
        check=check,
        text=True,
        encoding="utf-8",
        env={key: value for key, value in os.environ.items() if key not in JVM_ENVIRONMENT},
    )
