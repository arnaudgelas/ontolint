# Releasing

The version lives in `pyproject.toml` and, as a fallback for uninstalled use, in
`src/ontolint/_version.py` (a test keeps them equal); `uv.lock` records it too. Do not edit them by
hand: `scripts/bump_version.py` changes all three, moves the pin of the Action in `release.yml` (step 6 of
the release run, below) and writes the changelog.

```bash
uv run python scripts/bump_version.py patch --dry-run   # show what would change
uv run python scripts/bump_version.py patch             # or minor, major, or X.Y.Z
```

The script edits files only. It never commits, tags or pushes, and it refuses to run when tracked files
have uncommitted changes, when the two version lines disagree, or when the new version is not greater
than the current one. Pre-release versions (`1.0.0rc1`) are not supported.

`CHANGELOG.md` is generated from the conventional-commit subjects since the previous `vX.Y.Z` tag,
grouped as Breaking changes (`type!:` or a `BREAKING CHANGE` trailer), Added (`feat`), Fixed (`fix`),
Performance (`perf`), Documentation (`docs`) and Maintenance (everything else). `chore: release` commits
are left out. When the file does not exist yet it is built from the whole tag history. Edit the new
section by hand if a subject reads badly; the script will not touch earlier sections.

## Steps

1. Run the script, then review `git diff` and edit `CHANGELOG.md` if needed.
   Write the upgrade notes by hand from the `Upgrade note` paragraphs and `BREAKING CHANGE`
   trailers of the `!` commits. A commit that changes a finding's focus or subject changes its
   baseline identity: name each such rule under the baseline entries that stop matching once. A
   commit that changes only a message breaks only version 1 (0.10.x) baselines: say so.
   `git diff vPREV..HEAD -- tests/golden/identities.json` lists the changed identities, SHACL001's
   included; it does not cover the probe cases of SEM001, INPUT001 and TOOL001, so check a change
   to their subject by hand.
2. `git commit -am 'chore: release X.Y.Z'`
3. `git tag -a vX.Y.Z -m 'ontolint X.Y.Z'`
4. `git push && git push origin vX.Y.Z`, with the release commit as the head of `main`: do not push
   it together with later commits. CodeQL scans only the head of each push, so a tagged commit
   with commits pushed on top of it is never scanned and its release run fails at **CodeQL**
   (0.9.0 did). To release several versions, push `main` up to each release commit and its tag,
   one at a time, and wait for CodeQL to finish on each before the next push.

Pushing the tag starts `.github/workflows/release.yml`:

1. **Test** runs the CI workflow, that is the validation gate (`scripts/gate.py`).
2. **CodeQL** waits for the CodeQL scans of the tagged commit and fails unless every one succeeded.
   CodeQL scans the head of each push to `main`, so tag the head and push both together (step 4
   above); a tag on an unscanned commit never releases, and the tag cannot be moved afterwards.
3. **Build** checks that the tag equals the version in `pyproject.toml` and builds the
   distributions.
4. **Publish** uploads them to PyPI from the `pypi` environment (Trusted Publishing).
5. **Verify** installs that exact version from PyPI in a fresh virtual environment, retrying while
   the index catches up, checks `ontolint --version`, lints a one-line file and lists the rules.
   It then checks that PyPI holds exactly the files **Build** made, and verifies each file's PEP 740
   attestation with `pypi-attestations` (the `release` dependency group, locked in `uv.lock`): the
   attestation must name this repository and sign those exact bytes. PyPI's JSON and provenance
   APIs lag an upload too, so both checks retry (20 attempts, 30 s apart) and fail only when the
   file list still differs, or an attestation still does not verify, after the last one.
6. **Action** runs the GitHub Action at the new tag, as a user resolves it
   (`uses: arnaudgelas/ontolint@vX.Y.Z`), on `tests/fixtures/kitchen_sink.ttl`, and checks that the step exited
   `0` and wrote a SARIF 2.1.0 report with results and a Markdown summary. The pin is in
   `.github/workflows/release.yml`; `scripts/bump_version.py` moves it with the version, and a test fails when
   it differs from `pyproject.toml`. The Action installs `ontolint==X.Y.Z` from PyPI, so it runs after
   **Verify**. The Action has no release of its own (no Marketplace listing): the tag is the release.

PyPI refuses to overwrite a version, so a failed publish needs a new version. A failure in
**Verify** or **Action** means the release is on PyPI but broken: fix it and release the next patch version.

`action/requirements.txt` and `action/verify-requirements.txt` are the Action's hash-locked dependency lists
(what ontolint needs, and what checks the PyPI attestation of the ontolint wheel). Regenerate them whenever
`uv.lock` moves (a test compares each with the lock):

```bash
uv export --frozen --no-dev --no-emit-project --format requirements-txt --no-header > action/requirements.txt
uv export --frozen --only-group release --no-emit-project --format requirements-txt --no-header > action/verify-requirements.txt
```

The Action cannot pin the wheel it installs by hash: the hash does not exist when the tag's commit is made.
It checks the wheel's PyPI attestation instead (see the README, "GitHub Action"), so the **Action** job above is
also the first proof that the attestation of the release just published verifies from a fresh runner.
