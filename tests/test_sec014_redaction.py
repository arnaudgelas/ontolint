"""SEC014 never repeats the userinfo it reports: not in a report, a SARIF region lookup or a baseline.

RFC 3986 section 3.2.1: applications should not render the data after the first ``:`` of a userinfo, and a
token may be sent as the user name (:mod:`ontolint.redaction`).  The focus is the IRI with its whole userinfo
replaced by ``****``; the SARIF region is still the credentialed IRI's.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from ontolint import baseline, main
from ontolint.models import Finding
from ontolint.reporting import FileReport, fingerprint

PASSWORD = "s3cret"  # noqa: S105 -- a fake credential the reports must not repeat
CREDENTIALED = f"https://alice:{PASSWORD}@example.test/x"
MASKED = "https://****@example.test/x"
MESSAGE = "IRI embeds a password in its userinfo."
SEE_ALSO = "http://www.w3.org/2000/01/rdf-schema#seeAlso"
# Each input states the credentialed IRI on line 3.
INPUTS = {
    "a.ttl": (
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
        "<https://example.test/onto#D>\n"
        f"    rdfs:seeAlso <{CREDENTIALED}> .\n"
    ),
    "a.rdf": (
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
        '  <rdf:Description rdf:about="https://example.test/onto#D">\n'
        f'    <seeAlso xmlns="http://www.w3.org/2000/01/rdf-schema#" rdf:resource="{CREDENTIALED}"/>\n'
        "  </rdf:Description>\n"
        "</rdf:RDF>\n"
    ),
    "a.jsonld": (f'{{"@id": "https://example.test/onto#D",\n  "{SEE_ALSO}":\n    {{"@id": "{CREDENTIALED}"}}}}\n'),
}
IRI_LINE = 3


@pytest.fixture
def run(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> Any:
    """Run the CLI in ``tmp_path``; return ``(exit code, stdout, stderr)``."""
    monkeypatch.chdir(tmp_path)

    def _run(*argv: str) -> tuple[int, str, str]:
        code = main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return _run


@pytest.mark.parametrize("name", sorted(INPUTS))
@pytest.mark.parametrize("output_format", ["text", "json", "sarif", "markdown"])
def test_no_report_format_repeats_the_password(tmp_path: Path, run: Any, name: str, output_format: str) -> None:
    (tmp_path / name).write_text(INPUTS[name], encoding="utf-8")
    code, out, err = run(name, "--select", "SEC014", "--format", output_format)
    assert code == 1, err
    assert PASSWORD not in out + err
    assert "alice" not in out + err
    assert MASKED in out


@pytest.mark.parametrize("name", sorted(INPUTS))
def test_the_sarif_region_is_the_credentialed_iri(tmp_path: Path, run: Any, name: str) -> None:
    (tmp_path / name).write_text(INPUTS[name], encoding="utf-8")
    _code, out, _err = run(name, "--select", "SEC014", "--format", "sarif")
    [result] = json.loads(out)["runs"][0]["results"]
    assert result["locations"][0]["physicalLocation"]["region"]["startLine"] == IRI_LINE


def test_an_iri_already_spelled_with_the_mask_keeps_its_own_region(tmp_path: Path, run: Any) -> None:
    # Both mask to one focus and one finding; an IRI spelled with the mask is located as itself.
    (tmp_path / "a.ttl").write_text(
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
        "<https://example.test/onto#D> rdfs:seeAlso <https://u:****@h/x> .\n"
        "<https://example.test/onto#E> rdfs:seeAlso <https://u:pw@h/x> .\n",
        encoding="utf-8",
    )
    _code, out, _err = run("a.ttl", "--select", "SEC014", "--format", "sarif")
    [result] = json.loads(out)["runs"][0]["results"]
    assert result["locations"][0]["physicalLocation"]["region"]["startLine"] == 2  # noqa: PLR2004


def test_a_baseline_holds_no_hash_over_the_password(tmp_path: Path, run: Any) -> None:
    (tmp_path / "a.ttl").write_text(INPUTS["a.ttl"], encoding="utf-8")
    code, _out, err = run("a.ttl", "--select", "SEC014", "--write-baseline", "base.json")
    assert code == 1, err
    text = (tmp_path / "base.json").read_text(encoding="utf-8")
    assert PASSWORD not in text
    masked = Finding("SEC014", "error", MASKED, MESSAGE, "")
    assert fingerprint(masked) in json.loads(text)["fingerprints"]
    # A finding masks itself, so the version 1 hash over the credentialed focus is computed by hand.
    payload = json.dumps(["SEC014", CREDENTIALED, MESSAGE], ensure_ascii=False, separators=(",", ":"))
    assert hashlib.sha256(payload.encode()).hexdigest() not in text
    assert Finding("SEC014", "error", CREDENTIALED, MESSAGE, "") == masked
    # Neither hash of the version 2 file is over the password: the identity is (rule, focus, subject).
    written = baseline.dumps(baseline.build([FileReport("a.ttl", "a.ttl", (masked,))]))
    assert json.loads(written)["identities"] == json.loads(text)["identities"]


# The credentialed IRI is stated in the named graph G1 only; the masked focus still names it.
GRAPH = "https://example.test/g1"
DATASETS = {
    "a.trig": (
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
        f"<{GRAPH}> {{\n"
        f"    <https://example.test/onto#D> rdfs:seeAlso <{CREDENTIALED}> .\n"
        "}\n"
    ),
    "a.nq": f"<https://example.test/onto#D> <{SEE_ALSO}> <{CREDENTIALED}> <{GRAPH}> .\n",
}


@pytest.mark.parametrize("name", sorted(DATASETS))
def test_a_dataset_finding_names_the_graph_of_the_credentialed_iri(tmp_path: Path, run: Any, name: str) -> None:
    (tmp_path / name).write_text(DATASETS[name], encoding="utf-8")
    code, out, err = run(name, "--select", "SEC014", "--format", "json")
    assert code == 1, err
    assert PASSWORD not in out + err
    [finding] = json.loads(out)["findings"]
    assert finding["focus"] == MASKED
    assert finding["graphs"] == [GRAPH]
    _code, out, _err = run(name, "--select", "SEC014", "--format", "sarif")
    assert PASSWORD not in out
    [result] = json.loads(out)["runs"][0]["results"]
    assert result["properties"]["graphs"] == [GRAPH]


# SEC016: a token sent as the user name (https://<token>@host) is reported, and masked like a password (#59).
TOKEN = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"  # noqa: S105 -- a fake token the reports must not repeat
TOKEN_ONTOLOGY = (
    "@prefix ex: <https://example.test/onto#> .\n"
    "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
    "ex: a owl:Ontology ;\n"
    f"    owl:imports <https://{TOKEN}@github.com/org/repo/raw/main/x.ttl> .\n"
)
TOKEN_LINE = 4


@pytest.mark.parametrize("output_format", ["text", "json", "sarif", "markdown"])
def test_a_token_as_the_user_name_is_reported_and_never_printed(tmp_path: Path, run: Any, output_format: str) -> None:
    (tmp_path / "token.ttl").write_text(TOKEN_ONTOLOGY, encoding="utf-8")
    code, out, err = run("token.ttl", "--select", "SEC016", "--format", output_format)
    assert code == 0, err  # a warning does not fail the run
    assert TOKEN not in out + err
    assert "SEC016" in out
    assert "https://****@github.com/org/repo/raw/main/x.ttl" in out
    # SEC014 keeps its contract: a user name without a password is not a password.
    code, out, err = run("token.ttl", "--select", "SEC014")
    assert (code, TOKEN not in out + err, "0 finding(s)" in out) == (0, True, True)


def test_the_sarif_region_of_a_token_is_its_iri_and_the_baseline_holds_no_token(tmp_path: Path, run: Any) -> None:
    (tmp_path / "token.ttl").write_text(TOKEN_ONTOLOGY, encoding="utf-8")
    _code, out, _err = run("token.ttl", "--select", "SEC016", "--format", "sarif")
    [result] = json.loads(out)["runs"][0]["results"]
    assert result["ruleId"] == "SEC016"
    assert result["locations"][0]["physicalLocation"]["region"]["startLine"] == TOKEN_LINE
    code, _out, err = run("token.ttl", "--select", "SEC016", "--write-baseline", "base.json")
    assert code == 0, err
    assert TOKEN not in (tmp_path / "base.json").read_text(encoding="utf-8")
    code, out, err = run("token.ttl", "--select", "SEC016", "--baseline", "base.json")
    assert code == 0, err
    assert "0 finding(s)" in out


def test_the_default_run_reports_a_token_and_the_rule_is_ignorable(tmp_path: Path, run: Any) -> None:
    (tmp_path / "token.ttl").write_text(TOKEN_ONTOLOGY, encoding="utf-8")
    _code, out, _err = run("token.ttl", "--format", "json")
    assert TOKEN not in out
    assert [f["rule"] for f in json.loads(out)["findings"] if f["rule"] == "SEC016"] == ["SEC016"]
    _code, out, _err = run("token.ttl", "--format", "json", "--ignore", "SEC016")
    assert [f["rule"] for f in json.loads(out)["findings"] if f["rule"] == "SEC016"] == []
    # The gating profiles fail on a warning, so a token as the user name fails them; the default gate does not.
    assert run("token.ttl")[0] == 0
    assert run("token.ttl", "--profile", "ci")[0] == 1
