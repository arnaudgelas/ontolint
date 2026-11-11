"""SEC014 never repeats the password it reports: not in a report, a SARIF region lookup or a baseline.

RFC 3986 section 3.2.1: applications should not render the data after the first ``:`` of a userinfo.  The
focus is the IRI with that data replaced by ``****``; the SARIF region is still the credentialed IRI's.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ontolint import baseline, main
from ontolint.models import Finding
from ontolint.reporting import FileReport, fingerprint

PASSWORD = "s3cret"  # noqa: S105 -- a fake credential the reports must not repeat
CREDENTIALED = f"https://alice:{PASSWORD}@example.test/x"
MASKED = "https://alice:****@example.test/x"
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
@pytest.mark.parametrize("output_format", ["text", "json", "sarif"])
def test_no_report_format_repeats_the_password(tmp_path: Path, run: Any, name: str, output_format: str) -> None:
    (tmp_path / name).write_text(INPUTS[name], encoding="utf-8")
    code, out, err = run(name, "--select", "SEC014", "--format", output_format)
    assert code == 1, err
    assert PASSWORD not in out + err
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
    masked = Finding("SEC014", "error", MASKED, "IRI embeds a password for user 'alice'.", "")
    unmasked = Finding("SEC014", "error", CREDENTIALED, masked.message, "")
    assert fingerprint(masked) in json.loads(text)["fingerprints"]
    assert fingerprint(unmasked) not in text
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
