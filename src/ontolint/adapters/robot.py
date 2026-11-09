"""ROBOT adapter: OWL profile validation in an isolated Docker container."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from ontolint.models import Finding
from ontolint.rules.specs import FIXES, SEVERITY

# An OWL API profile violation line: ``<kind>[: <subject>] [<axiom> in <ontology>]``.
AXIOM_TYPE = re.compile(r"\[(?P<type>[A-Za-z]+)\(")
SHOWN_KINDS = 10
SHOWN_SUBJECTS = 5
UNPARSED_MESSAGE_LENGTH = 500  # output that is no violation list (a crash) is quoted up to this length


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
