"""ROBOT adapter: OWL profile validation and OWL syntax conversion in an isolated Docker container."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from xml.sax.saxutils import quoteattr

from ontolint.models import Finding
from ontolint.rules.specs import FIXES, SEVERITY

# An OWL API profile violation line: ``<kind>[: <subject>] [<axiom> in <ontology>]``.
AXIOM_TYPE = re.compile(r"\[(?P<type>[A-Za-z]+)\(")
SHOWN_KINDS = 10
SHOWN_SUBJECTS = 5
UNPARSED_MESSAGE_LENGTH = 500  # output that is no violation list (a crash) is quoted up to this length

# The isolation every ROBOT container runs under: no network, bounded resources, no capabilities.
ISOLATION = (
    "--network",
    "none",
    "--memory",
    "2g",
    "--pids-limit",
    "256",
    "--cpus",
    "2",
    "--cap-drop",
    "ALL",
    "--security-opt",
    "no-new-privileges",
)

# ROBOT's ``--input-format`` for each OWL syntax :mod:`ontolint.syntax` recognises but RDFLib cannot read.
INPUT_FORMATS = {"owl-functional": "ofn", "owl-manchester": "omn", "owl-xml": "owx"}
# An import declaration in OWL Functional (``Import(<…>)``), Manchester (``Import: <…>``) or OWL/XML syntax.
IMPORT_DECLARATION = re.compile(
    r"Import\(\s*<([^<>\s]+)>\s*\)|Import:\s*<([^<>\s]+)>|<(?:[\w.-]+:)?Import>\s*([^<>\s]+)\s*</"
)
UNLOADABLE_IMPORT = re.compile(r"Could not load imported ontology: <([^<>\s]+)>")
CONVERSION_ATTEMPTS = 4  # an import the declaration pattern missed (a prefixed name) is stubbed on a retry


class ConversionFailed(Exception):
    """ROBOT could not convert a file to Turtle."""


def summarise_profile_report(details: str) -> str | None:
    """Group a ROBOT profile report by violation kind and subject, or ``None`` when it lists no violation.

    ``Use of undeclared annotation property: <…#definition> in annotation [...]`` repeated six times
    becomes ``Use of undeclared annotation property: …#definition (6)``; a line without a subject
    (``Axiom type not allowed in profile [DisjointUnion(...) ...]``) is grouped by its axiom type.
    """
    lines = [line.strip() for line in details.splitlines() if line.strip()]
    start = next((i + 1 for i, line in enumerate(lines) if line.endswith("violations are present:")), None)
    if start is None:
        return None
    kinds: Counter[str] = Counter()
    subjects: dict[str, Counter[str]] = {}
    for line in lines[start:]:
        head, bracket, context = line.partition(" [")
        kind, _colon, subject = head.partition(": ")
        subject = subject.removesuffix(" in annotation").strip().removeprefix("<").removesuffix(">")
        if not subject and bracket and (axiom := AXIOM_TYPE.match("[" + context)) is not None:
            subject = axiom["type"]
        kinds[kind] += 1
        if subject:
            subjects.setdefault(kind, Counter())[subject] += 1
    if not kinds:
        return None
    parts = [_kind_summary(kind, count, subjects.get(kind)) for kind, count in _ranked(kinds)[:SHOWN_KINDS]]
    if len(kinds) > SHOWN_KINDS:
        parts.append(f"{len(kinds) - SHOWN_KINDS} more kinds")
    total = kinds.total()
    return f"{total} violation{'s' if total != 1 else ''}: " + "; ".join(parts) + "."


def _ranked(counter: Counter[str]) -> list[tuple[str, int]]:
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))


def _kind_summary(kind: str, count: int, subjects: Counter[str] | None) -> str:
    ranked = _ranked(subjects or Counter())
    if sum(n for _subject, n in ranked) != count:  # some lines had no subject: give the kind's own count
        return f"{kind} ({count})" if not ranked else f"{kind} ({count}): " + _subjects(ranked)
    return f"{kind}: " + _subjects(ranked)


def _subjects(ranked: list[tuple[str, int]]) -> str:
    shown = ", ".join(f"{subject} ({n})" for subject, n in ranked[:SHOWN_SUBJECTS])
    return shown + (f", {len(ranked) - SHOWN_SUBJECTS} more" if len(ranked) > SHOWN_SUBJECTS else "")


def _host_user() -> list[str]:
    """``--user uid:gid`` of the calling process, or nothing where the OS has no POSIX ids (Windows)."""
    if sys.platform == "win32":
        return []
    return ["--user", f"{os.getuid()}:{os.getgid()}"]


def robot_profile_issues(ontology: Path, profile: str, image: str, timeout: int) -> list[Finding]:
    """Run ROBOT profile validation in an isolated Docker container.

    The ontology's parent directory is mounted read-only and the container has no
    network access. Use a digest-pinned ``image`` in CI for reproducibility.
    On POSIX the container runs as the calling user, so ROBOT can write its report
    into the private (mode 0700) output directory.
    """
    source = ontology.resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    with tempfile.TemporaryDirectory(prefix="ontolint-robot-") as output_dir:
        output = Path(output_dir)
        report = output / "profile.txt"
        command = [
            "docker",
            "run",
            "--rm",
            *ISOLATION,
            *_host_user(),
            "-v",
            f"{source.parent}:/input:ro",
            "-v",
            f"{output}:/output",
            "-w",
            "/output",
            image,
            "validate-profile",
            "--profile",
            profile,
            "--input",
            f"/input/{source.name}",
            "--output",
            "/output/profile.txt",
        ]
        completed = subprocess.run(  # noqa: S603 -- fixed Docker executable and constructed argument list.
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
        if completed.returncode == 0:
            return []
        details = report.read_text(encoding="utf-8", errors="replace").strip() if report.exists() else ""
        details = details or completed.stderr.strip() or completed.stdout.strip() or "ROBOT did not produce a report."
        summary = summarise_profile_report(details)
        if summary is None:
            summary = details[:UNPARSED_MESSAGE_LENGTH]
            if len(details) > UNPARSED_MESSAGE_LENGTH:
                summary += "… (full output in the JSON report)"
        return [
            Finding(
                "SEM001",
                SEVERITY["SEM001"],
                str(source),
                f"ROBOT OWL {profile} profile validation failed: {summary}",
                FIXES["SEM001"],
                "certain",
                details if summary != details else None,  # only when the message abbreviates it
            )
        ]


def robot_convert(source: Path, data: bytes, syntax: str, image: str, timeout: int) -> bytes:
    """Convert one OWL Functional, Manchester or OWL/XML file to Turtle with ROBOT in an isolated container.

    Only ``source`` itself is mounted, read-only, and the container has no network access.  Every import the
    file declares is answered by an empty stub ontology through a generated catalog, so the file converts on
    its own: its ``owl:imports`` survive in the output, and ontolint follows them (or not) under its own
    sandbox rules.  ``syntax`` (from :func:`ontolint.syntax.sniff`) is passed as ROBOT's input format: without
    one, OWL API tries its other parsers after a failed parse, and its OBO parser accepts almost anything.
    """
    if shutil.which("docker") is None:
        raise ConversionFailed("--convert-with-robot needs Docker, and the docker executable was not found on PATH")
    text = data.decode("utf-8", errors="replace")
    imports = {next(iri for iri in match.groups() if iri) for match in IMPORT_DECLARATION.finditer(text)}
    with tempfile.TemporaryDirectory(prefix="ontolint-robot-") as output_dir:
        output = Path(output_dir)
        for _attempt in range(CONVERSION_ATTEMPTS):
            _write_stub_catalog(output, imports)
            completed = _run_conversion(source, syntax, image, timeout, output)
            if completed.returncode == 0:
                return (output / "converted.ttl").read_bytes()
            message = completed.stderr.strip() or completed.stdout.strip() or "ROBOT failed without output."
            missed = UNLOADABLE_IMPORT.search(message)
            if missed is None or missed[1] in imports:
                raise ConversionFailed(_conversion_failure(message, syntax))
            imports.add(missed[1])
    raise ConversionFailed(f"ROBOT still reported an unloadable import after stubbing {len(imports)} imports")


def _run_conversion(
    source: Path, syntax: str, image: str, timeout: int, output: Path
) -> subprocess.CompletedProcess[str]:
    command = [
        "docker",
        "run",
        "--rm",
        *ISOLATION,
        *_host_user(),
        "-v",
        f"{source.resolve()}:/input/{source.name}:ro",
        "-v",
        f"{output}:/output",
        "-w",
        "/output",
        image,
        "convert",
        "--catalog",
        "/output/catalog.xml",
        "--input-format",
        INPUT_FORMATS[syntax],
        "--input",
        f"/input/{source.name}",
        "--format",
        "ttl",
        "--output",
        "/output/converted.ttl",
    ]
    try:
        return subprocess.run(  # noqa: S603 -- fixed Docker executable and constructed argument list.
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise ConversionFailed(f"ROBOT did not finish converting within {timeout} s (--robot-timeout)") from exc


def _write_stub_catalog(output: Path, imports: set[str]) -> None:
    """Map each import IRI to an empty ontology with that IRI; the IRIs come from the input, so they are escaped."""
    entries = []
    for number, iri in enumerate(sorted(imports)):
        stub = f"stub-{number}.owl"
        (output / stub).write_text(
            '<?xml version="1.0"?>\n<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
            f'xmlns:owl="http://www.w3.org/2002/07/owl#"><owl:Ontology rdf:about={quoteattr(iri)}/></rdf:RDF>\n',
            encoding="utf-8",
        )
        entries.append(f"<uri name={quoteattr(iri)} uri={quoteattr(stub)}/>")
    (output / "catalog.xml").write_text(
        '<?xml version="1.0"?>\n<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">'
        + "".join(entries)
        + "</catalog>\n",
        encoding="utf-8",
    )


def _conversion_failure(message: str, syntax: str) -> str:
    reason = message.splitlines()[0][:UNPARSED_MESSAGE_LENGTH]
    if syntax == "owl-manchester":  # the usual cause: an entity whose type only an import declares
        reason += (
            "; ontolint converts each file without its imports, so a Manchester Syntax file must declare every "
            "class and property it uses"
        )
    return f"ROBOT could not convert it to Turtle: {reason}"
