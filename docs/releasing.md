# Releasing

The version lives in `pyproject.toml` and, as a fallback for uninstalled use, in
`src/ontolint/_version.py` (a test keeps them equal); `uv.lock` records it too. Do not edit them by
hand: `scripts/bump_version.py` changes all three and writes the changelog.

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

PyPI refuses to overwrite a version, so a failed publish needs a new version. A failure in
**Verify** means the release is on PyPI but broken: fix it and release the next patch version.
