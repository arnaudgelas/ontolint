"""scripts/corpus.py: the validation corpus is pinned by commit and checksum, and fetched reproducibly (#167).

Everything here is offline: the downloads are a fake ``opener`` serving fixed bytes.  The one test that needs the
network is manual (``uv run python scripts/corpus.py fetch DIR`` then ``verify DIR``).
"""

# ruff: noqa: PLR2004

from __future__ import annotations

import copy
import importlib.util
import io
import json
import os
import sys
import urllib.error
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("corpus", ROOT / "scripts" / "corpus.py")
assert spec is not None
assert spec.loader is not None
corpus = importlib.util.module_from_spec(spec)
sys.modules["corpus"] = corpus
spec.loader.exec_module(corpus)
REAL_LOAD = corpus.load

COMMIT = "0123456789abcdef0123456789abcdef01234567"
BODIES = {"src/a.ttl": b"a\n", "src/b.ttl": b"b\n", "src/catalog-v001.xml": b"<catalog/>\n", "../x": b""}
SOURCE: dict[str, Any] = {
    "id": "demo",
    "repository": "owner/repo",
    "commit": COMMIT,
    "licence": "MIT",
    "files": {path: corpus.sha256(body) for path, body in BODIES.items() if not path.startswith("..")},
    "runs": [
        {
            "name": "all",
            "inputs": ["src/a.ttl", "src/b.ttl"],
            "args": ["--catalog", "{root}/src/catalog-v001.xml", "--import-root", "{root}"],
            "exit_status": 0,
        }
    ],
}


def _manifest(tmp_path: Path, *sources: dict[str, Any], entries: list[dict[str, Any]] | None = None) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"entries": entries or [], "sources": list(sources)}), encoding="utf-8")
    return path


class Served:
    """An ``opener`` that serves the bodies of :data:`BODIES` by URL and counts what it was asked."""

    def __init__(self, bodies: dict[str, bytes] | None = None) -> None:
        self.bodies = (
            bodies
            if bodies is not None
            else {
                f"https://raw.githubusercontent.com/owner/repo/{COMMIT}/{path}": body
                for path, body in BODIES.items()
                if not path.startswith("..")
            }
        )
        self.asked: list[str] = []

    def __call__(self, url: str) -> io.BytesIO:
        self.asked.append(url)
        if url not in self.bodies:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)  # type: ignore[arg-type]
        return io.BytesIO(self.bodies[url])


def _source(**changes: Any) -> dict[str, Any]:
    item = copy.deepcopy(SOURCE)
    for key, value in changes.items():
        if value is None:
            item.pop(key, None)
        else:
            item[key] = value
    return item


# -- 1. the committed manifest is pinned, licensed and has no mutable reference ----------------------------------------


def test_every_committed_source_has_a_40_hex_commit_an_allowed_licence_and_no_mutable_reference() -> None:
    manifest = json.loads(corpus.MANIFEST.read_text(encoding="utf-8"))
    sources = corpus.load()

    assert manifest["sources"], "the corpus has at least one repository source"
    assert {s.id for s in sources} >= {item["id"] for item in manifest["sources"]}
    for source in sources:
        assert source.licence in corpus.LICENCES, source.id
        if not source.flat:
            assert corpus.COMMIT.fullmatch(source.commit or ""), source.id
            assert all(corpus.SHA256.fullmatch(d) for d in source.files.values()), source.id
            for path in source.files:
                assert f"/{source.commit}/" in source.location(path)
                assert not any(ref in source.location(path).split("/") for ref in ("main", "master", "HEAD", "latest"))


def test_the_one_single_file_entry_without_a_commit_is_the_documented_one() -> None:
    """``skos-core.rdf`` is pinned by checksum alone (issue #152: the W3C serves one mutable document); no other."""
    unpinned = [s.id for s in corpus.load() if s.flat and s.commit is None]

    assert unpinned == ["skos-core.rdf"]


# -- refusals: a manifest that could name a branch, write outside DIR or hide a licence --------------------------------


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"commit": "main"}, "commit"),
        ({"commit": "master"}, "commit"),
        ({"commit": COMMIT[:7]}, "commit"),
        ({"commit": COMMIT.upper()}, "commit"),
        ({"commit": None}, "commit"),
        ({"ref": "main"}, "unknown keys"),
        ({"branch": "main"}, "unknown keys"),
        ({"url": "https://example.test/latest/x.ttl"}, "unknown keys"),
        ({"repository": "owner"}, "repository"),
        ({"repository": "https://github.com/owner/repo"}, "repository"),
        ({"licence": "proprietary"}, "licence"),
        ({"licence": None}, "licence"),
        ({"id": ""}, "plain name"),
        ({"id": "../x"}, "plain name"),
        ({"id": "a/b"}, "plain name"),
        ({"id": ".hidden"}, "plain name"),
        ({"files": None}, "files"),
        ({"files": {}}, "files"),
        ({"files": {"../escape.ttl": "0" * 64}}, "plain relative path"),
        ({"files": {"/etc/passwd": "0" * 64}}, "plain relative path"),
        ({"files": {"a\\b.ttl": "0" * 64}}, "plain relative path"),
        ({"files": {"C:/x.ttl": "0" * 64}}, "plain relative path"),
        ({"files": {"a//b.ttl": "0" * 64}}, "plain relative path"),
        ({"files": {"./a.ttl": "0" * 64}}, "plain relative path"),
        ({"files": {"src/a.ttl": "XYZ"}}, "SHA-256"),
        ({"files": {"src/a.ttl": "A" * 64}}, "SHA-256"),
        ({"runs": []}, "at least one run"),
        ({"runs": [{"name": "r", "inputs": ["nowhere.ttl"], "exit_status": 0}]}, "not files of the source"),
        ({"runs": [{"name": "r", "inputs": [], "exit_status": 0}]}, "not files of the source"),
        ({"runs": [{"name": "r", "inputs": ["src/a.ttl"], "exit_status": 7}]}, "exit_status"),
        ({"runs": [{"name": "r", "inputs": ["src/a.ttl"], "exit_status": 0, "shell": "x"}]}, "a run has"),
        ({"runs": [{"name": "r", "inputs": ["src/a.ttl"], "args": [1], "exit_status": 0}]}, "string"),
    ],
)
def test_a_source_that_is_not_pinned_licensed_and_plain_is_refused(
    tmp_path: Path, changes: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        corpus.load(_manifest(tmp_path, _source(**changes)))


def test_an_id_used_twice_is_refused_across_entries_and_sources(tmp_path: Path) -> None:
    entry = {
        "id": "demo",
        "url": "https://example.test/demo.ttl",
        "commit": None,
        "licence": "MIT",
        "sha256": "0" * 64,
    }
    with pytest.raises(ValueError, match="appears twice"):
        corpus.load(_manifest(tmp_path, _source(), entries=[entry]))
    with pytest.raises(ValueError, match="appears twice"):
        corpus.load(_manifest(tmp_path, _source(), _source()))


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"url": "http://example.test/x.ttl"}, "https"),
        ({"licence": "proprietary"}, "licence"),
        ({"sha256": "nope"}, "SHA-256"),
        ({"commit": COMMIT, "url": "https://example.test/main/x.ttl"}, "appear in the URL"),
        ({"commit": "main"}, "40 hex"),
    ],
)
def test_a_single_file_entry_is_held_to_the_same_rules(tmp_path: Path, changes: dict[str, Any], message: str) -> None:
    entry = {"id": "x.ttl", "url": "https://example.test/x.ttl", "commit": None, "licence": "MIT", "sha256": "0" * 64}
    with pytest.raises(ValueError, match=message):
        corpus.load(_manifest(tmp_path, entries=[{**entry, **changes}]))


# -- 3. a layout that needs an import root, a catalog or two is expressible --------------------------------------------


def test_the_committed_umbrella_needs_an_import_root_and_two_catalogs() -> None:
    """CCO's umbrella reaches the modules and BFO through ``../``: a run names the import root and each catalog."""
    (cco,) = [s for s in corpus.load() if s.id == "cco-umbrella"]
    umbrella, modules = cco.runs

    assert "--import-root" in umbrella.args
    assert any(arg.endswith("cco-merged/catalog-v001.xml") for arg in umbrella.args)
    assert any(arg.endswith("cco-modules/catalog-v001.xml") for arg in modules.args)
    assert set(umbrella.inputs + modules.inputs) <= set(cco.files)


def test_a_run_may_name_two_catalogs_an_import_directory_and_shapes(tmp_path: Path) -> None:
    run = {
        "name": "layered",
        "inputs": ["src/a.ttl"],
        "args": [
            "--catalog",
            "{root}/src/catalog-v001.xml",
            "--catalog",
            "{root}/src/b.ttl",
            "--import-dir",
            "{root}/src",
            "--shapes",
            "{root}/src/b.ttl",
        ],
        "exit_status": 2,
    }
    (source,) = corpus.load(_manifest(tmp_path, _source(runs=[run])))

    command = source.command(tmp_path, source.runs[0])

    assert command[0] == str(tmp_path / "demo" / "src" / "a.ttl")
    assert command.count("--catalog") == 2
    assert str(tmp_path / "demo" / "src" / "catalog-v001.xml") in command
    assert "{root}" not in " ".join(command)
    assert source.runs[0].exit_status == 2


# -- 2. a hash mismatch ends the fetch and names the source and the file; 4. two fetches give one tree ----------------


def test_a_hash_mismatch_exits_non_zero_names_the_entry_and_writes_nothing(tmp_path: Path) -> None:
    (source,) = corpus.load(_manifest(tmp_path, _source()))
    served = Served()
    served.bodies = {url: body + b"tampered" for url, body in served.bodies.items()}

    with pytest.raises(SystemExit) as refused:
        corpus.fetch(tmp_path / "dir", [source], served)

    assert refused.value.code
    assert "demo: src/" in str(refused.value.code)
    assert "differs from the manifest's" in str(refused.value.code)
    assert not list((tmp_path / "dir").rglob("*.ttl")), "an unverified file is never written"


def test_a_network_failure_names_the_source_and_the_file(tmp_path: Path) -> None:
    (source,) = corpus.load(_manifest(tmp_path, _source()))

    with pytest.raises(SystemExit) as refused:
        corpus.fetch(tmp_path / "dir", [source], Served({}))

    assert "demo: src/" in str(refused.value.code)
    assert "cannot download" in str(refused.value.code)


def test_two_fetches_give_the_same_tree_and_the_second_downloads_nothing(tmp_path: Path) -> None:
    (source,) = corpus.load(_manifest(tmp_path, _source()))
    first, second = tmp_path / "one", tmp_path / "two"
    served = Served()

    done = corpus.fetch(first, [source], served)
    again = Served()
    corpus.fetch(second, [source], again)
    nothing = Served()
    repeated = corpus.fetch(first, [source], nothing)

    assert len(done) == len(source.files)
    assert corpus.tree(first, [source]) == corpus.tree(second, [source])
    assert corpus.verify(first, [source]) == []
    assert repeated == [] and nothing.asked == []


def test_a_file_that_changed_in_the_directory_is_downloaded_again(tmp_path: Path) -> None:
    (source,) = corpus.load(_manifest(tmp_path, _source()))
    corpus.fetch(tmp_path, [source], Served())
    (tmp_path / "demo" / "src" / "a.ttl").write_bytes(b"edited\n")

    edited = corpus.sha256(b"edited\n")
    assert corpus.verify(tmp_path, [source]) == [
        f"demo: src/a.ttl: SHA-256 {edited} differs from the manifest's {source.files['src/a.ttl']}"
    ]
    assert corpus.fetch(tmp_path, [source], Served()) == ["demo: src/a.ttl"]
    assert corpus.verify(tmp_path, [source]) == []


def test_verify_reports_a_missing_file(tmp_path: Path) -> None:
    (source,) = corpus.load(_manifest(tmp_path, _source()))

    assert corpus.verify(tmp_path, [source]) == [f"demo: {path}: missing" for path in source.files]
    with pytest.raises(SystemExit, match="missing"):
        corpus.tree(tmp_path, [source])


@pytest.mark.skipif(sys.platform == "win32", reason="creating a symbolic link needs a privilege on Windows")
def test_fetch_does_not_write_through_a_symbolic_link(tmp_path: Path) -> None:
    (source,) = corpus.load(_manifest(tmp_path, _source()))
    outside = tmp_path / "outside"
    outside.mkdir()
    directory = tmp_path / "dir"
    (directory / "demo").mkdir(parents=True)
    os.symlink(outside, directory / "demo" / "src")

    with pytest.raises(SystemExit, match="symbolic link"):
        corpus.fetch(directory, [source], Served())

    assert list(outside.iterdir()) == []


def test_a_single_file_entry_is_kept_as_dir_slash_id(tmp_path: Path) -> None:
    body = b"@prefix : <https://e/> .\n"
    entry = {
        "id": "x.ttl",
        "url": "https://example.test/x.ttl",
        "commit": None,
        "licence": "MIT",
        "sha256": corpus.sha256(body),
    }
    (source,) = corpus.load(_manifest(tmp_path, entries=[entry]))

    corpus.fetch(tmp_path / "dir", [source], Served({"https://example.test/x.ttl": body}))

    assert (tmp_path / "dir" / "x.ttl").read_bytes() == body
    assert corpus.tree(tmp_path / "dir", [source]) == [f"{corpus.sha256(body)}  x.ttl"]
    assert source.command(tmp_path / "dir", source.runs[0]) == [str(tmp_path / "dir" / "x.ttl")]


# -- pin and the command line ------------------------------------------------------------------------------------------


def test_pin_builds_the_url_from_the_commit_and_hashes_the_bytes() -> None:
    served = Served({f"https://raw.githubusercontent.com/owner/repo/{COMMIT}/a%20b/c.ttl": b"c\n"})

    files = corpus.pin("owner/repo", COMMIT, ["a b/c.ttl"], served)

    assert files == {"a b/c.ttl": corpus.sha256(b"c\n")}
    assert served.asked == [f"https://raw.githubusercontent.com/owner/repo/{COMMIT}/a%20b/c.ttl"]


@pytest.mark.parametrize("commit", ["main", "v1.0", COMMIT[:7], "HEAD"])
def test_pin_refuses_a_branch_a_tag_or_a_short_commit(commit: str) -> None:
    with pytest.raises(SystemExit, match="40-hex"):
        corpus.pin("owner/repo", commit, ["a.ttl"], Served())


def test_the_command_line_lists_fetches_verifies_and_prints_the_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = _manifest(tmp_path, _source())
    monkeypatch.setattr(corpus, "load", lambda: REAL_LOAD(manifest))
    served = Served()
    monkeypatch.setattr(corpus.urllib.request, "urlopen", lambda url, timeout=0: served(url))

    assert corpus.main(["list"]) == 0
    assert "demo: owner/repo@0123456789ab MIT, 3 file(s), runs: ['all']" in capsys.readouterr().out
    assert corpus.main(["verify", str(tmp_path / "dir")]) == 1
    assert "missing" in capsys.readouterr().out
    assert corpus.main(["fetch", str(tmp_path / "dir")]) == 0
    assert corpus.main(["verify", str(tmp_path / "dir")]) == 0
    assert "the corpus is the pinned one" in capsys.readouterr().out
    assert corpus.main(["tree", str(tmp_path / "dir")]) == 0
    assert capsys.readouterr().out.count("  demo/src/") == 3
