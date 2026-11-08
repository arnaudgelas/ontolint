# Security policy

ontolint reads ontologies, which are untrusted input. A file that makes it reach the network,
read outside the working directory, expand entities without bound, run out of memory or time
beyond its configured limits, crash instead of reporting a finding, or report a clean result for
an input it did not actually check is a security problem. See "Input safety" in the
[README](README.md#input-safety) for the guarantees the loader is meant to give.

## Reporting a vulnerability

Report it privately through GitHub:
**<https://github.com/arnaudgelas/ontolint/security/advisories/new>**
(Security tab, "Report a vulnerability"). Please do not open a public issue.

Include the ontolint version (`ontolint --version`), the command line, and the smallest input
that reproduces the problem. A fix is released as a patch version, and the advisory is published
once that release is on PyPI.

## Supported versions

Only the latest released minor version receives security fixes. Upgrade to it before reporting.

## Verifying a release

Every release on PyPI was built and uploaded by `.github/workflows/release.yml` with PyPI
Trusted Publishing, which publishes a PEP 740 attestation for each file. PyPI shows it on the
release's "Verified details"; the attestation binds the file to this repository and that
workflow, so a file uploaded any other way would not carry one.
