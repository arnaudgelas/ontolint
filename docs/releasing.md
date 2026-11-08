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
4. `git push && git push origin vX.Y.Z`

Pushing the tag starts `.github/workflows/release.yml`: it runs the CI workflow, checks that the tag
equals the version in `pyproject.toml`, builds the distributions and publishes them to PyPI from the
`pypi` environment. PyPI refuses to overwrite a version, so a failed publish needs a new version.
