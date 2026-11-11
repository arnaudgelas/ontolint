"""The contracts of the pipeline rules, as specified in ``rules/safe_loader.py`` and ``rules/external.py``.

These rules are emitted by the loader, the CLI and the adapters rather than by a graph rule.  Each test pins
one clause of a specification that no other test states: how the run ends (exit code, report or not), a
boundary just under a limit, or an input path the limit must also cover.  Docker is never started: the ROBOT
subprocess is replaced, as in ``test_robot_summary.py``.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from ontolint import engine, main
from ontolint.loader import NetworkAttempts, _network_problem, network_disabled
from ontolint.models import RuleBackend, RuleSpec
from ontolint.rules.registry import UnknownSelectorError, default_registry
from ontolint.rules.specs import RULE_SPECS
from ontolint.selection import PipelineSelectorError, check_selectors, pipeline_selectors

TOOL_FAILURE = 2
GATED = 1
TTL = "@prefix e: <http://e/> .\ne:a e:p 1, 2, 3, 4 .\n"
OWL = "http://www.w3.org/2002/07/owl#"
EXPANDED = 1000  # characters the entity document expands to
ROBOT_TIMEOUT_DEFAULT = 120


@pytest.fixture
def run(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> Any:
    """Run the CLI in ``tmp_path``; return ``(exit code, stdout, stderr)``."""
    monkeypatch.chdir(tmp_path)

    def _run(*argv: str) -> tuple[int, str, str]:
        code = main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return _run


def _policy(tmp_path: Path, **keys: object) -> str:
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"policy_version": 1, **keys}), encoding="utf-8")
    return str(path)


# --- how a loader rejection ends the run ---------------------------------------------------------------------


def test_one_rejected_input_stops_the_whole_run_without_a_report(tmp_path: Path, run: Any) -> None:
    (tmp_path / "a.ttl").write_text("@prefix e: <http://e/> .\ne:a e:p 1 .\n", encoding="utf-8")
    (tmp_path / "b.ttl").write_text(TTL, encoding="utf-8")
    code, out, err = run("a.ttl", "b.ttl", "--max-triples", "3", "--fail-on", "never", "--format", "json")
    assert (code, out) == (TOOL_FAILURE, "")  # no report, not even for the file that loaded
    assert err == "SEC002: graph has more than 3 triples (max_triples) for b.ttl\n"


def test_the_shapes_file_passes_the_same_size_limit(tmp_path: Path, run: Any) -> None:
    (tmp_path / "a.ttl").write_text(TTL, encoding="utf-8")
    (tmp_path / "s.ttl").write_text(TTL + "# padding\n", encoding="utf-8")
    code, out, err = run("a.ttl", "--shapes", "s.ttl", "--max-input-bytes", str(len(TTL)))
    assert (code, out) == (TOOL_FAILURE, "")
    assert err.startswith("SEC001: s.ttl is ")


def test_a_missing_input_is_input001_and_exit_2(run: Any) -> None:
    code, out, err = run("missing.ttl")
    assert (code, out) == (TOOL_FAILURE, "")
    assert err.startswith("INPUT001: RDF input parsing failed: FileNotFoundError: ")


# --- SEC001 also bounds catalogs -----------------------------------------------------------------------------

CATALOG = (
    '<?xml version="1.0"?>\n<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">'
    '<uri name="https://e.test/m" uri="m.ttl"/><!--{pad}--></catalog>\n'
)


def _catalog_case(tmp_path: Path) -> int:
    """An umbrella importing ``https://e.test/m`` through a catalog; return the catalog's size."""
    (tmp_path / ".git").mkdir()  # the import root
    (tmp_path / "m.ttl").write_text(f"<https://e.test/m> a <{OWL}Ontology> .\n", encoding="utf-8")
    (tmp_path / "u.ttl").write_text(f"<https://e.test/u> <{OWL}imports> <https://e.test/m> .\n", encoding="utf-8")
    catalog = CATALOG.format(pad="x" * 200).encode()
    (tmp_path / "catalog-v001.xml").write_bytes(catalog)
    return len(catalog)


@pytest.mark.parametrize("option", ["--catalog", "--follow-imports"])
def test_a_catalog_over_max_input_bytes_is_sec001(tmp_path: Path, run: Any, option: str) -> None:
    size = _catalog_case(tmp_path)
    argv = ["--catalog", "catalog-v001.xml"] if option == "--catalog" else ["--follow-imports"]
    code, out, err = run("u.ttl", *argv, "--max-input-bytes", str(size - 1), "--select", "ONT001")
    assert (code, out) == (TOOL_FAILURE, "")
    assert err.startswith("SEC001: catalog ") and f"larger than the limit of {size - 1} bytes" in err


def test_a_catalog_at_max_input_bytes_is_read(tmp_path: Path, run: Any) -> None:
    size = _catalog_case(tmp_path)
    code, out, err = run("u.ttl", "--catalog", "catalog-v001.xml", "--max-input-bytes", str(size), "--format", "json")
    assert "SEC0" not in err and code != TOOL_FAILURE
    assert {f["rule"] for f in json.loads(out)["findings"]}.isdisjoint({"SEC007"})  # the import resolved


# --- SEC009: a symlinked directory cannot lead out of the working directory ---------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_a_path_through_a_symlinked_directory_leaving_the_working_dir_is_sec009(tmp_path: Path, run: Any) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "x.ttl").write_text(TTL, encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    (work / "linked").symlink_to(outside, target_is_directory=True)
    os.chdir(work)
    code, out, err = run("linked/x.ttl", "--select", "ONT001")
    assert (code, out) == (TOOL_FAILURE, "")
    target = (outside / "x.ttl").resolve().as_posix()
    assert err == f"SEC009: linked/x.ttl goes through a symlinked directory to {target} outside the working dir\n"


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_a_symlinked_directory_staying_inside_is_accepted(tmp_path: Path, run: Any) -> None:
    (tmp_path / "real").mkdir()
    (tmp_path / "real" / "x.ttl").write_text(TTL, encoding="utf-8")
    (tmp_path / "linked").symlink_to(tmp_path / "real", target_is_directory=True)
    code, _out, err = run("linked/x.ttl", "--select", "ONT001")
    assert code != TOOL_FAILURE and "SEC009" not in err


def test_an_absolute_path_outside_the_working_dir_is_accepted(tmp_path: Path, run: Any) -> None:
    (tmp_path / "x.ttl").write_text(TTL, encoding="utf-8")
    (tmp_path / "work").mkdir()
    os.chdir(tmp_path / "work")
    code, _out, err = run(str(tmp_path / "x.ttl"), "--select", "ONT001")
    assert code != TOOL_FAILURE and err == ""


# --- SEC010: the entity expansion limit is max_input_bytes, inclusive ---------------------------------------


def _entity_document() -> bytes:
    value = "x" * 50
    uses = "&v;" * 20  # 20 * 50 = 1000 characters once expanded
    return (
        f'<?xml version="1.0"?>\n<!DOCTYPE rdf:RDF [<!ENTITY v "{value}">]>\n'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:e="http://e/">'
        f'<rdf:Description rdf:about="http://e/a"><e:p>{uses}</e:p></rdf:Description></rdf:RDF>\n'
    ).encode()


def test_entity_expansion_above_max_input_bytes_is_sec010(tmp_path: Path, run: Any) -> None:
    (tmp_path / "a.rdf").write_bytes(_entity_document())
    assert len(_entity_document()) < EXPANDED - 1  # the file itself is within the size limit
    code, out, err = run("a.rdf", "--max-input-bytes", str(EXPANDED - 1), "--select", "ONT001")
    assert (code, out) == (TOOL_FAILURE, "")
    assert err == "SEC010: a.rdf uses entities that expand to 1000 characters, more than the limit of 999\n"


def test_entity_expansion_at_max_input_bytes_is_accepted(tmp_path: Path, run: Any) -> None:
    (tmp_path / "a.rdf").write_bytes(_entity_document())
    code, _out, err = run("a.rdf", "--max-input-bytes", str(EXPANDED), "--select", "ONT001")
    assert code != TOOL_FAILURE and err == ""


# --- SEC006 / SEC013: what the network guard blocks ----------------------------------------------------------


def test_a_refused_context_is_reported_as_sec006_even_after_other_network_attempts() -> None:
    attempts = NetworkAttempts(network=["resolve 'e.test'"], contexts=["http://e.test/ctx"])
    rejection = _network_problem("a.jsonld", attempts)
    assert rejection is not None and rejection.rule_id == "SEC006"
    rejection = _network_problem("a.jsonld", NetworkAttempts(network=["resolve 'e.test'"]))
    assert rejection is not None and rejection.rule_id == "SEC013"
    assert _network_problem("a.jsonld", NetworkAttempts()) is None


def test_the_guard_blocks_the_c_resolvers_and_udp_and_restores_them() -> None:
    originals = (socket.gethostbyname, socket.gethostbyname_ex, socket.gethostbyaddr, socket.socket.sendto)
    with network_disabled() as attempts:
        for call in (
            lambda: socket.gethostbyname("example.invalid"),
            lambda: socket.gethostbyname_ex("example.invalid"),
            lambda: socket.gethostbyaddr("192.0.2.1"),
        ):
            with pytest.raises(Exception, match="network access is disabled"):
                call()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock, pytest.raises(Exception, match="disabled"):
            sock.sendto(b"x", ("192.0.2.1", 9))
    assert attempts.network == [
        "resolve 'example.invalid'",
        "resolve 'example.invalid'",
        "resolve '192.0.2.1'",
        "sendto ('192.0.2.1', 9)",
    ]
    assert (socket.gethostbyname, socket.gethostbyname_ex, socket.gethostbyaddr, socket.socket.sendto) == originals


# --- SEC015: the closure limits are inclusive -----------------------------------------------------------------


def _two_module_closure(tmp_path: Path) -> None:
    """An umbrella importing two modules through file IRIs (two imported files, depth 1)."""
    (tmp_path / ".git").mkdir()
    iris = []
    for name in ("m1", "m2"):
        module = tmp_path / f"{name}.ttl"
        module.write_text(f"<https://e.test/{name}> a <{OWL}Ontology> .\n", encoding="utf-8")
        iris.append(f"<{module.resolve().as_uri()}>")
    (tmp_path / "u.ttl").write_text(f"<https://e.test/u> <{OWL}imports> {', '.join(iris)} .\n", encoding="utf-8")


def test_a_closure_of_exactly_max_imported_files_is_loaded(tmp_path: Path, run: Any) -> None:
    _two_module_closure(tmp_path)
    code, _out, err = run("u.ttl", "--follow-imports", "--config", _policy(tmp_path, max_imported_files=2))
    assert code != TOOL_FAILURE and "SEC015" not in err
    code, out, err = run("u.ttl", "--follow-imports", "--config", _policy(tmp_path, max_imported_files=1))
    assert (code, out) == (TOOL_FAILURE, "")
    assert err == "SEC015: the import closure has more than 1 files (max_imported_files)\n"


def test_an_import_dir_of_exactly_max_imported_files_is_indexed(tmp_path: Path, run: Any) -> None:
    mirror = tmp_path / "mirror"
    mirror.mkdir()
    for name in ("m1", "m2"):
        (mirror / f"{name}.ttl").write_text(f"<https://e.test/{name}> a <{OWL}Ontology> .\n", encoding="utf-8")
    (tmp_path / "u.ttl").write_text(f"<https://e.test/u> <{OWL}imports> <https://e.test/m1> .\n", encoding="utf-8")
    code, _out, err = run("u.ttl", "--import-dir", "mirror", "--config", _policy(tmp_path, max_imported_files=2))
    assert code != TOOL_FAILURE and "SEC015" not in err
    code, out, err = run("u.ttl", "--import-dir", "mirror", "--config", _policy(tmp_path, max_imported_files=1))
    assert (code, out) == (TOOL_FAILURE, "")
    assert err == "SEC015: --import-dir mirror holds more than 1 files (max_imported_files)\n"


# --- TOOL001: configuration, execution and rule failures -----------------------------------------------------


def test_a_missing_policy_file_is_a_configuration_failure(tmp_path: Path, run: Any) -> None:
    (tmp_path / "a.ttl").write_text(TTL, encoding="utf-8")
    code, out, err = run("a.ttl", "--config", "nope.json")
    assert (code, out) == (TOOL_FAILURE, "")
    assert err.startswith("TOOL001: configuration failed: FileNotFoundError: ")


def test_an_unwritable_baseline_is_a_lint_execution_failure(tmp_path: Path, run: Any) -> None:
    (tmp_path / "a.ttl").write_text(TTL, encoding="utf-8")
    code, out, err = run("a.ttl", "--write-baseline", "no/such/dir/baseline.json")
    assert (code, out) == (TOOL_FAILURE, "")
    assert err.startswith("TOOL001: lint execution failed: FileNotFoundError: ")


OUTPUT_FAILED = "TOOL001: report output failed: "
# A lone surrogate is a valid Turtle escape that no UTF-8 report can hold (JSON escapes it; text cannot).
SURROGATE_TTL = (
    "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
    "<https://example.test/onto> a owl:Ontology .\n"
    "<https://example.test/onto#\\uD800x> a owl:Class .\n"
)


def test_an_output_in_a_missing_directory_is_tool001_and_exit_2(tmp_path: Path, run: Any) -> None:
    (tmp_path / "a.ttl").write_text(TTL, encoding="utf-8")
    code, out, err = run("a.ttl", "--output", "no/such/dir/out.txt")
    assert (code, out) == (TOOL_FAILURE, "")
    assert err.startswith(OUTPUT_FAILED + "FileNotFoundError: ")
    assert err.count("\n") == 1 and "Traceback" not in err


def test_an_output_naming_a_directory_is_tool001_and_exit_2(tmp_path: Path, run: Any) -> None:
    (tmp_path / "a.ttl").write_text(TTL, encoding="utf-8")
    (tmp_path / "out").mkdir()
    code, out, err = run("a.ttl", "--output", "out")
    assert (code, out) == (TOOL_FAILURE, "")
    assert err.startswith(OUTPUT_FAILED)  # IsADirectoryError on POSIX, PermissionError on Windows


if sys.platform == "win32":
    POSIX_NON_ROOT = False
else:
    POSIX_NON_ROOT = os.geteuid() != 0


@pytest.mark.skipif(not POSIX_NON_ROOT, reason="needs POSIX permissions and a non-root user")
def test_an_output_in_a_read_only_directory_is_tool001_and_exit_2(tmp_path: Path, run: Any) -> None:
    (tmp_path / "a.ttl").write_text(TTL, encoding="utf-8")
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        code, out, err = run("a.ttl", "--output", "locked/out.txt")
    finally:
        locked.chmod(0o700)
    assert (code, out) == (TOOL_FAILURE, "")
    assert err.startswith(OUTPUT_FAILED + "PermissionError: ")


def test_an_unencodable_report_keeps_the_previous_output_file(tmp_path: Path, run: Any) -> None:
    (tmp_path / "a.ttl").write_text(SURROGATE_TTL, encoding="utf-8")
    previous = tmp_path / "out.txt"
    previous.write_bytes(b"last good report\n")
    code, out, err = run("a.ttl", "--output", "out.txt")
    assert (code, out) == (TOOL_FAILURE, "")
    assert err.startswith(OUTPUT_FAILED + "UnicodeEncodeError: ")
    assert previous.read_bytes() == b"last good report\n"


def test_an_unencodable_report_on_stdout_is_tool001_and_exit_2(tmp_path: Path, run: Any) -> None:
    (tmp_path / "a.ttl").write_text(SURROGATE_TTL, encoding="utf-8")
    code, out, err = run("a.ttl")
    assert (code, out) == (TOOL_FAILURE, "")
    assert err.startswith(OUTPUT_FAILED + "UnicodeEncodeError: ")
    code, out, _err = run("a.ttl", "--format", "json")  # JSON escapes the surrogate: written as before
    assert code != TOOL_FAILURE and "\\ud800" in out


def test_an_unwritable_output_outranks_a_passing_run(tmp_path: Path, run: Any) -> None:
    (tmp_path / "a.ttl").write_text(TTL, encoding="utf-8")
    code, _out, err = run("a.ttl", "--fail-on", "never", "--output", "no/out.txt")
    assert code == TOOL_FAILURE
    assert err.startswith(OUTPUT_FAILED)


def test_an_unwritable_output_is_named_before_the_broken_rules(
    tmp_path: Path, run: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = next(spec.module for spec in RULE_SPECS if spec.rule_id == "ONT001")

    def boom(_ctx: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setitem(engine.FAMILY_RUNNERS, module, boom)
    (tmp_path / "a.ttl").write_text(TTL, encoding="utf-8")
    code, _out, err = run("a.ttl", "--select", "ONT001", "--fail-on", "never", "--output", "no/out.txt")
    assert code == TOOL_FAILURE
    first, second, rest = err.split("\n", 2)
    assert first.startswith(OUTPUT_FAILED + "FileNotFoundError: ")
    assert (second, rest) == ("TOOL001: rule ONT001 failed for a.ttl: RuntimeError: boom", "")


def test_a_writable_output_holds_the_report_and_a_newline(tmp_path: Path, run: Any) -> None:
    (tmp_path / "a.ttl").write_text(TTL, encoding="utf-8")
    _code, printed, _err = run("a.ttl", "--format", "json")
    code, out, err = run("a.ttl", "--format", "json", "--output", "out.json")
    assert (out, err) == ("", "") and code != TOOL_FAILURE
    assert (tmp_path / "out.json").read_text(encoding="utf-8") == printed


def test_a_failing_rule_module_still_writes_the_report_and_exits_2(
    tmp_path: Path, run: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = next(spec.module for spec in RULE_SPECS if spec.rule_id == "ONT001")

    def boom(_ctx: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setitem(engine.FAMILY_RUNNERS, module, boom)
    (tmp_path / "a.ttl").write_text(TTL, encoding="utf-8")
    code, out, err = run("a.ttl", "--select", "ONT001", "--fail-on", "never", "--format", "json")
    assert code == TOOL_FAILURE
    assert json.loads(out)["execution_summary"]["failed"] == 1
    assert err == "TOOL001: rule ONT001 failed for a.ttl: RuntimeError: boom\n"


# --- SEM001: a finding that gates like any error; ROBOT not answering is a tool failure ----------------------

DL_REPORT = (
    "OWL 2 DL Profile Report: Ontology and imports closure NOT in profile. The following violations are present:\n"
    'Use of undeclared annotation property: <http://e/p> in annotation [Annotation(<http://e/p> "x")]\n'
)


def _fake_robot(monkeypatch: pytest.MonkeyPatch, returncode: int, report: str | None, stderr: str = "") -> list[Any]:
    commands: list[Any] = []

    def fake(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append((command, kwargs))
        output = next(v for v in command if v.endswith(":/output")).removesuffix(":/output")
        if report is not None:
            Path(output, "profile.txt").write_text(report, encoding="utf-8")
        return subprocess.CompletedProcess(command, returncode, "", stderr)

    monkeypatch.setattr("ontolint.engine.shutil.which", lambda _: "docker")
    monkeypatch.setattr("ontolint.adapters.robot.subprocess.run", fake)
    return commands


def test_a_profile_violation_is_one_error_finding_that_gates_exit_1(
    tmp_path: Path, run: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands = _fake_robot(monkeypatch, 1, DL_REPORT)
    (tmp_path / "a.ttl").write_text(TTL, encoding="utf-8")
    code, out, err = run("a.ttl", "--select", "SEM001", "--owl-profile", "DL", "--format", "json")
    (finding,) = json.loads(out)["findings"]
    assert (code, err) == (GATED, "")
    assert (finding["rule"], finding["severity"], finding["confidence"]) == ("SEM001", "error", "certain")
    assert finding["focus"] == "(ontology)"  # not the absolute path: a fingerprint must not depend on the machine
    assert finding["details"] == DL_REPORT.strip()
    assert finding["message"] == (
        "ROBOT OWL DL profile validation failed: 1 violation: Use of undeclared annotation property: http://e/p (1)."
    )
    ((command, kwargs),) = commands
    assert command[command.index("--network") + 1] == "none"
    assert f"{(tmp_path / 'a.ttl').resolve().parent}:/input:ro" in command
    assert kwargs["timeout"] == ROBOT_TIMEOUT_DEFAULT  # --robot-timeout's default
    assert run("a.ttl", "--select", "SEM001", "--owl-profile", "DL", "--fail-on", "never")[0] == 0


def test_robot_exiting_0_is_no_finding(tmp_path: Path, run: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_robot(monkeypatch, 0, None)
    (tmp_path / "a.ttl").write_text(TTL, encoding="utf-8")
    code, out, _err = run("a.ttl", "--select", "SEM001", "--owl-profile", "DL", "--format", "json")
    assert (code, json.loads(out)["findings"]) == (0, [])


@pytest.mark.parametrize(
    "case",
    [
        (125, None, "docker: Error response from daemon: pull access denied"),  # a missing image
        (1, None, "Exception in thread main java.lang.OutOfMemoryError"),  # Java failing, no report
        (1, "/output/profile.txt (Permission denied)", ""),  # the first hosted Validation run
        (1, None, ""),  # nothing at all
    ],
)
def test_robot_failing_without_a_violation_list_is_a_failed_rule_not_a_finding(
    tmp_path: Path, run: Any, monkeypatch: pytest.MonkeyPatch, case: tuple[int, str | None, str]
) -> None:
    returncode, report, stderr = case
    _fake_robot(monkeypatch, returncode, report, stderr=stderr)
    (tmp_path / "a.ttl").write_text(TTL, encoding="utf-8")
    code, out, err = run("a.ttl", "--select", "SEM001", "--owl-profile", "DL", "--format", "json")
    document = json.loads(out)
    assert (code, document["findings"]) == (TOOL_FAILURE, [])
    (execution,) = [x for x in document["files"][0]["executions"] if x["rule"] == "SEM001"]
    assert execution["status"] == "failed"
    assert execution["detail"].startswith(f"ProfileCheckFailed: ROBOT exited {returncode} without a profile report: ")
    assert (report or stderr or "ROBOT did not produce a report.") in execution["detail"]
    assert "TOOL001: rule SEM001 failed for a.ttl" in err


def test_robot_output_quoted_in_a_failure_is_cut_at_500_characters(
    tmp_path: Path, run: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_robot(monkeypatch, 1, None, stderr="x" * 600)
    (tmp_path / "a.ttl").write_text(TTL, encoding="utf-8")
    _code, out, _err = run("a.ttl", "--select", "SEM001", "--owl-profile", "DL", "--format", "json")
    (execution,) = [x for x in json.loads(out)["files"][0]["executions"] if x["rule"] == "SEM001"]
    assert execution["detail"].endswith(": " + "x" * 500 + "…")


def test_a_robot_timeout_is_a_failed_rule_and_exit_2(tmp_path: Path, run: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    def slow(command: list[str], **kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr("ontolint.engine.shutil.which", lambda _: "docker")
    monkeypatch.setattr("ontolint.adapters.robot.subprocess.run", slow)
    (tmp_path / "a.ttl").write_text(TTL, encoding="utf-8")
    code, out, err = run("a.ttl", "--select", "SEM001", "--owl-profile", "DL", "--robot-timeout", "5")
    assert code == TOOL_FAILURE and out
    assert err.startswith("TOOL001: rule SEM001 failed for a.ttl: TimeoutExpired: ")


# --- selection cannot change the pipeline rules ---------------------------------------------------------------

PIPELINE_IDS = tuple(sorted(spec.rule_id for spec in RULE_SPECS if spec.backend is RuleBackend.CLI))
GRAPH_SEC_IDS = ["SEC004", "SEC005", "SEC007", "SEC008", "SEC012", "SEC014"]
PIPELINE_ERROR = "TOOL001: configuration failed: PipelineSelectorError: "
PIPELINE_REASON = (
    ": these name only pipeline rules (safe-loader refusals and front-end diagnostics, never findings), "
    "which always apply whatever the selection; remove them\n"
)


def _valid(tmp_path: Path) -> str:
    (tmp_path / "a.ttl").write_text(TTL, encoding="utf-8")
    return "a.ttl"


def test_the_pipeline_rules_are_the_safe_loader_refusals_and_the_front_end_diagnostics() -> None:
    sec = ["SEC001", "SEC002", "SEC003", "SEC006", "SEC009", "SEC010", "SEC011", "SEC013", "SEC015"]
    expected = ("INPUT001", *sec, "TOOL001")
    assert expected == PIPELINE_IDS


@pytest.mark.parametrize(
    ("argv", "named"),
    [
        (["--select", "SEC001"], "--select SEC001"),
        (["--select", "TOOL001"], "--select TOOL001"),
        (["--select", "TOOL"], "--select TOOL"),  # a family made only of pipeline rules
        (["--select", "input"], "--select INPUT"),  # case-insensitive, like every selector
        (["--select", "INPUT001,LEX002"], "--select INPUT001"),  # one pipeline token spoils the list
        (["--ignore", "SEC001"], "--ignore SEC001"),
        (["--ignore", "SEC013,SEC015"], "--ignore SEC013, SEC015"),
        (["--select", "SEC001", "--ignore", "INPUT"], "--select SEC001; --ignore INPUT"),
        (["--select", "LEX001", "--ignore", "LEX002,tool001"], "--ignore TOOL001"),
    ],
)
def test_a_selector_naming_only_pipeline_rules_is_a_configuration_error(
    tmp_path: Path, run: Any, argv: list[str], named: str
) -> None:
    code, out, err = run(_valid(tmp_path), *argv, "--format", "json")
    assert (code, out) == (TOOL_FAILURE, "")
    assert err == PIPELINE_ERROR + named + PIPELINE_REASON


@pytest.mark.parametrize("rule_id", PIPELINE_IDS)
@pytest.mark.parametrize("option", ["--select", "--ignore"])
def test_every_pipeline_rule_is_rejected_by_either_option(tmp_path: Path, run: Any, option: str, rule_id: str) -> None:
    code, out, err = run(_valid(tmp_path), option, rule_id)
    assert (code, out, err) == (TOOL_FAILURE, "", f"{PIPELINE_ERROR}{option} {rule_id}{PIPELINE_REASON}")


def test_a_typo_next_to_a_pipeline_rule_is_reported_as_the_typo(tmp_path: Path, run: Any) -> None:
    code, out, err = run(_valid(tmp_path), "--select", "SEC001,NOPE999")
    assert (code, out) == (TOOL_FAILURE, "")
    assert err == "TOOL001: configuration failed: UnknownSelectorError: unknown rule selector(s): NOPE999\n"


def test_the_selectors_are_checked_before_any_input_is_read(tmp_path: Path, run: Any) -> None:
    # Without the check first, the refusal of the input (SEC001) would hide the misconfiguration.
    code, out, err = run(_valid(tmp_path), "--max-input-bytes", "10", "--select", "SEC001")
    assert (code, out) == (TOOL_FAILURE, "")
    assert err == f"{PIPELINE_ERROR}--select SEC001{PIPELINE_REASON}"
    code, _, err = run("missing.ttl", "--ignore", "NOPE999")
    assert code == TOOL_FAILURE and err.startswith("TOOL001: configuration failed: UnknownSelectorError: ")


def test_the_mixed_sec_family_selects_and_ignores_its_graph_rules(tmp_path: Path, run: Any) -> None:
    source = _valid(tmp_path)
    code, out, err = run(source, "--select", "SEC", "--format", "json", "--fail-on", "never")
    assert (code, err) == (0, "")
    assert [x["rule"] for x in json.loads(out)["files"][0]["executions"]] == GRAPH_SEC_IDS
    code, out, err = run(source, "--ignore", "SEC", "--format", "json", "--fail-on", "never")
    assert (code, err) == (0, "")
    executions = {x["rule"]: x for x in json.loads(out)["files"][0]["executions"]}
    skipped = {rule for rule, x in executions.items() if x.get("detail") == "ignored by --ignore or profile"}
    assert skipped == set(GRAPH_SEC_IDS)
    assert not set(PIPELINE_IDS) & executions.keys()


@pytest.mark.parametrize(
    "argv",
    [["--ignore", "SEC007"], ["--profile", "strict"], ["--select", "SHACL001"], ["--select", "SEM001"]],
)
def test_selectors_that_can_change_the_run_are_accepted(tmp_path: Path, run: Any, argv: list[str]) -> None:
    code, out, err = run(_valid(tmp_path), *argv, "--format", "json", "--fail-on", "never")
    assert code == 0 and "TOOL001" not in err
    assert json.loads(out)["files"][0]["executions"]


def test_pipeline_selectors_names_the_pipeline_only_tokens_in_order() -> None:
    registry = default_registry()
    tokens = ["TOOL", "SEC001", "SEC", "LEX002", "INPUT001", "NOPE"]
    assert pipeline_selectors(registry, tokens) == ("TOOL", "SEC001", "INPUT001")
    assert pipeline_selectors(registry, ["sec015", "input"]) == ("SEC015", "INPUT")
    assert pipeline_selectors(registry, []) == ()


def test_check_selectors_accepts_the_default_and_reports_typos_first() -> None:
    registry = default_registry()
    check_selectors(registry, (), ())  # nothing named: the default run
    check_selectors(registry, ("SEC", "LEX"), ("SEC007",))
    with pytest.raises(UnknownSelectorError):
        check_selectors(registry, ("SEC001",), ("NOPE999",))
    with pytest.raises(PipelineSelectorError) as raised:
        check_selectors(registry, ("TOOL001", "LEX"), ("SEC002",))
    assert raised.value.named == (("--select", ("TOOL001",)), ("--ignore", ("SEC002",)))


@pytest.mark.parametrize("spec", RULE_SPECS, ids=lambda spec: spec.rule_id)
def test_an_ignore_is_rejected_exactly_for_the_pipeline_rules(spec: RuleSpec) -> None:
    rejected = pipeline_selectors(default_registry(), [spec.rule_id]) == (spec.rule_id,)
    assert rejected is (spec.backend is RuleBackend.CLI)
