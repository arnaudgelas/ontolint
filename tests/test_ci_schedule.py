"""The scheduled checks and the corpus at release: documented, wired, and not silently dropped (#169, #214).

``docs/ci-schedule.md`` is the one table of what runs on a timer; ``docs/releasing.md`` is where a release owner
runs the corpus checks by hand.  These tests keep the two true to ``.github/workflows`` and to the scripts.
"""

# ruff: noqa: PLR2004

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
SCHEDULE = (ROOT / "docs" / "ci-schedule.md").read_text(encoding="utf-8")
RELEASING = (ROOT / "docs" / "releasing.md").read_text(encoding="utf-8")
CORPUS = (WORKFLOWS / "corpus.yml").read_text(encoding="utf-8")
ROW = re.compile(
    r"^\| \[`(?P<file>[\w.-]+\.yml)`\]\([^)]*\) \| `(?P<cron>[^`]+)` \| (?P<timeouts>[\d, ]+) \|", re.MULTILINE
)
CRON = re.compile(r'^\s*- cron: "(?P<cron>[^"]+)"', re.MULTILINE)
TIMEOUT = re.compile(r"^\s*timeout-minutes: (?P<minutes>\d+)", re.MULTILINE)


def _rows() -> dict[str, tuple[str, set[int]]]:
    return {m["file"]: (m["cron"], {int(n) for n in re.findall(r"\d+", m["timeouts"])}) for m in ROW.finditer(SCHEDULE)}


def _scheduled() -> list[str]:
    return sorted(p.name for p in WORKFLOWS.glob("*.yml") if CRON.search(p.read_text(encoding="utf-8")))


def test_every_scheduled_workflow_has_a_row_and_every_row_names_a_scheduled_workflow() -> None:
    assert sorted(_rows()) == _scheduled()
    assert "corpus.yml" in _rows()


@pytest.mark.parametrize("name", sorted(_rows()))
def test_a_row_states_the_cron_and_the_timeouts_the_workflow_has(name: str) -> None:
    text = (WORKFLOWS / name).read_text(encoding="utf-8")
    cron, timeouts = _rows()[name]

    assert [m["cron"] for m in CRON.finditer(text)] == [cron]
    assert {int(m["minutes"]) for m in TIMEOUT.finditer(text)} == timeouts


def test_the_corpus_job_is_weekly_manual_read_only_and_fetches_before_it_checks() -> None:
    assert "workflow_dispatch:" in CORPUS
    assert re.search(r"^permissions:\n  contents: read\n", CORPUS, re.MULTILINE)
    assert "pull_request" not in CORPUS and "push:" not in CORPUS
    assert CORPUS.index("scripts/corpus.py fetch") < CORPUS.index("scripts/corpus_counts.py check")
    assert CORPUS.index("scripts/shq_scope_count.py fetch") < CORPUS.index("scripts/shq_scope_count.py check")


def test_the_corpus_job_runs_the_three_checks_and_a_difference_is_a_failure() -> None:
    for command in (
        "scripts/corpus_counts.py check",
        "scripts/metric_corpus.py check",
        "scripts/shq_scope_count.py check",
    ):
        assert command in CORPUS, command
    # Each check keeps its own exit status, so that a difference is red whatever follows and nothing else is hidden.
    assert CORPUS.count('exit "$status"') == 3
    assert CORPUS.count("|| status=$?") == 3
    assert CORPUS.count("2>&1 || status=$?") == 3, (
        "a refusal printed on stderr (a failed fetch, a bad directory) is kept"
    )
    assert "continue-on-error" not in CORPUS
    assert CORPUS.count("if: ${{ !cancelled() }}") == 3, "each check runs even when the one before it failed"


def test_the_diff_goes_to_the_job_summary_and_is_uploaded_when_the_job_fails() -> None:
    assert CORPUS.count('>> "$GITHUB_STEP_SUMMARY"') == 3
    assert CORPUS.count('if [ "$status" -ne 0 ]; then cat') == 3, "an unchanged corpus writes nothing to the summary"
    upload = CORPUS[CORPUS.index("name: Upload the diff") :]
    assert "if: ${{ !success() }}" in upload  # failure() would skip it on a cancel or a timeout
    assert "actions/upload-artifact@" in upload
    assert "if-no-files-found: ignore" in upload  # a job that fails before a check has no diff to upload


def test_every_action_the_corpus_job_uses_is_pinned_by_commit() -> None:
    uses = re.findall(r"uses: (\S+)", CORPUS)

    assert uses
    for action in uses:
        assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", action), action


def test_the_release_instructions_name_each_check_and_what_to_do_with_a_difference() -> None:
    for command in (
        "scripts/corpus.py fetch",
        "scripts/corpus_counts.py check",
        "scripts/metric_corpus.py check",
        "scripts/shq_scope_count.py fetch",
        "scripts/shq_scope_count.py check",
        "corpus_counts.py record",
        "metric_corpus.py measure",
        "shq_scope_count.py count",
    ):
        assert command in RELEASING, command
    step = RELEASING[RELEASING.index("2. **Review the corpus diff.**") : RELEASING.index("3. `git commit")]
    assert "changelog" in step
    assert "doubled" in step
    assert "reviewer" in step
    assert "block" in step


def test_the_corpus_review_comes_before_the_release_commit_and_the_tag() -> None:
    assert (
        RELEASING.index("Review the corpus diff")
        < RELEASING.index("chore: release X.Y.Z")
        < RELEASING.index("git tag -a")
    )
    assert re.findall(
        r"^(\d)\. ", RELEASING[RELEASING.index("## Steps") : RELEASING.index("Pushing the tag")], re.M
    ) == [
        "1",
        "2",
        "3",
        "4",
        "5",
    ]


@pytest.mark.parametrize(
    "path",
    [
        "docs/validation/shq-scope.md",
        "docs/validation/metric-calibration.md",
        "docs/metric-calibration.md",
        "docs/metric-thresholds.md",
        "scripts/metric_corpus.py",
        "scripts/shq_scope_count.py",
    ],
)
def test_no_page_says_that_nothing_runs_the_corpus_check(path: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")

    assert not re.search(r"nothing runs `{1,2}check`", text), path
    assert "Nothing reruns them" not in text
    assert "belongs to issue #31" not in text


def test_the_cadence_table_names_the_reviewer_of_the_corpus_diff() -> None:
    row = next(line for line in SCHEDULE.splitlines() if line.startswith("| [`corpus.yml`]"))

    assert "release owner" in row
    assert "step 2" in row


def test_the_schedule_page_gives_the_commands_that_reproduce_a_run_without_the_artifact() -> None:
    page = (ROOT / "docs" / "ci-schedule.md").read_text(encoding="utf-8")
    section = page[page.index("### Reproduce a run") :]

    for command in (
        "scripts/corpus.py fetch DIR",
        "scripts/corpus_counts.py check DIR",
        "scripts/metric_corpus.py check DIR",
        "scripts/shq_scope_count.py fetch DIR_SHQ",
        "scripts/shq_scope_count.py check DIR_SHQ",
    ):
        assert command in section, command


BENCHMARKS = (WORKFLOWS / "benchmarks.yml").read_text(encoding="utf-8")


def test_the_benchmark_job_is_weekly_manual_read_only_and_switched_on() -> None:
    assert "workflow_dispatch:" in BENCHMARKS
    assert re.search(r"^permissions:\n  contents: read\n", BENCHMARKS, re.MULTILINE)
    assert "pull_request" not in BENCHMARKS and "push:" not in BENCHMARKS
    assert 'ONTOLINT_BENCH: "1"' in BENCHMARKS
    assert "-m benchmark tests/benchmarks" in BENCHMARKS
    assert "benchmarks.yml" in SCHEDULE


def test_the_benchmark_job_keeps_the_profiles_and_the_log_even_when_the_run_fails() -> None:
    upload = BENCHMARKS[BENCHMARKS.index("name: Upload the logs and profiles") :]

    assert "if: ${{ !cancelled() }}" in upload  # the profiles of a red run are the evidence of a regression
    assert "actions/upload-artifact@" in upload
    assert "retention-days: 30" in upload
    assert "tee benchmark-out/benchmarks.log" in BENCHMARKS
    assert BENCHMARKS.count("set -o pipefail") == 2, "a failing pytest must not be hidden by tee"


def test_every_action_the_benchmark_job_uses_is_pinned_by_commit() -> None:
    uses = re.findall(r"uses: (\S+)", BENCHMARKS)

    assert uses
    for action in uses:
        assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", action), action


def test_no_benchmark_asserts_a_number_of_seconds() -> None:
    source = (ROOT / "tests" / "benchmarks" / "test_linter_benchmarks.py").read_text(encoding="utf-8")

    assert "perf_counter" not in source
    assert "seconds=" not in source


JENA = (WORKFLOWS / "jena.yml").read_text(encoding="utf-8")
JAVA_JSONLD_README = (ROOT / "tests" / "fixtures" / "java_jsonld" / "README.md").read_text(encoding="utf-8")
SOURCE_LOCATIONS_TESTS = (ROOT / "tests" / "test_source_locations.py").read_text(encoding="utf-8")


def test_the_jena_job_is_weekly_manual_and_read_only() -> None:
    assert "workflow_dispatch:" in JENA
    assert re.search(r"^permissions:\n  contents: read\n", JENA, re.MULTILINE)
    assert "pull_request" not in JENA and "push:" not in JENA
    assert "jena.yml" in SCHEDULE


def test_the_jena_zip_is_checked_against_its_published_sha512_before_it_is_unpacked_or_used() -> None:
    step = JENA[JENA.index("name: Download Apache Jena") : JENA.index("name: Run the riot round-trip test")]

    assert "set -euo pipefail" in step, "a failed download or checksum must stop the step"
    assert (
        step.index("curl --fail")
        < step.index("sha512sum --check")
        < step.index("unzip")
        < step.index("ONTOLINT_JENA_HOME")
    )
    assert JENA.index("name: Download Apache Jena") < JENA.index("uv run pytest"), "no test runs before the check"
    assert "archive.apache.org/dist/jena/binaries/" in step


def test_the_jena_job_pins_the_version_the_checksum_the_jdk_and_the_test_it_runs() -> None:
    sha = re.search(r'JENA_SHA512: "([0-9a-f]{128})"', JENA)
    version = re.search(r'JENA_VERSION: "([\d.]+)"', JENA)

    assert sha and version
    assert sha[1] in JAVA_JSONLD_README, "the workflow and the fixture README give the same SHA-512"
    assert f"apache-jena-{version[1]}.zip" in JAVA_JSONLD_README
    assert f"Apache Jena RIOT version {version[1]}" in SOURCE_LOCATIONS_TESTS
    assert "distribution: temurin" in JENA
    assert 'java-version: "11"' in JENA, "4.10.0 is the last Jena release that runs on Java 11"
    assert "-k riot" in JENA
    assert "tests/test_jena_shacl.py" in JENA
    assert "def test_a_java_jsonld_fixture_is_what_riot_writes_today" in SOURCE_LOCATIONS_TESTS


def test_the_riot_test_is_skipped_without_the_switch_the_job_sets() -> None:
    assert 'skipif("ONTOLINT_JENA_HOME" not in os.environ' in SOURCE_LOCATIONS_TESTS
    assert 'echo "ONTOLINT_JENA_HOME=' in JENA
    assert "jena.yml" in JAVA_JSONLD_README, "the fixture README says what runs the check"


def test_every_action_the_jena_job_uses_is_pinned_by_commit() -> None:
    uses = re.findall(r"uses: (\S+)", JENA)

    assert len(uses) >= 3
    for action in uses:
        assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", action), action
