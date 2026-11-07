"""ROBOT adapter: OWL profile validation in an isolated Docker container."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from ontolint.models import Finding
from ontolint.rules.specs import FIXES, SEVERITY


def robot_profile_issues(ontology: Path, profile: str, image: str, timeout: int) -> list[Finding]:
    """Run ROBOT profile validation in an isolated Docker container.

    The ontology's parent directory is mounted read-only and the container has no
    network access. Use a digest-pinned ``image`` in CI for reproducibility.
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
        return [
            Finding(
                "SEM001",
                SEVERITY["SEM001"],
                str(source),
                f"ROBOT OWL {profile} profile validation failed: {details[:4000]}",
                FIXES["SEM001"],
                "certain",
            )
        ]
