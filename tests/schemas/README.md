# Vendored schemas

## `sarif-schema-2.1.0.json`

The OASIS SARIF 2.1.0 JSON schema, used by `tests/test_sarif_schema.py` to validate every shape of
report that `--format sarif` can produce.

| | |
| --- | --- |
| Source | <https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/schemas/sarif-schema-2.1.0.json> |
| Version | SARIF 2.1.0, Errata 01, OASIS Standard |
| Retrieved | 2026-11-08 (byte-identical to the file served at the source URL on that date) |
| SHA-256 | `c3b4bb2d6093897483348925aaa73af03b3e3f4bd4ca38cef26dcb4212a2682e` |

The test suite checks this digest, so the file cannot change without this note changing too.

To refresh it deliberately:

1. Download the file from the source URL above (or from a newer OASIS errata, if one is published)
   into this directory.
2. Run `shasum -a 256 tests/schemas/sarif-schema-2.1.0.json` and update the table above and
   `SCHEMA_SHA256` in `tests/test_sarif_schema.py`.
3. Run the SARIF tests and review any new validation failure as a real conformance bug, not as a
   reason to loosen the test.
