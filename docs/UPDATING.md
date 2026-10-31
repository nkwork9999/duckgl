# Updating DuckGL

DuckGL uses DuckDB's internal C++ extension API. Build and load against the same
DuckDB release; a matching version string alone does not make different SDK
revisions ABI compatible.

## Current pins

- Runtime version / extension metadata: `v2.0.0`.
- DuckDB SDK submodule: `d54cbbe3df17e8e5ce68312f483b4155836112aa`.
- CI tools release line: `v2.0-cyanoptera`.
- CI tools submodule: `b8d325c37e82160886579880707493bd358c0e62`.

Keep `DUCKDB_VERSION` in the root Makefile as the runtime release alias.
The SDK source commit is pinned separately in the submodule and distribution
workflow. Encoding a full source SHA as the extension's runtime version can
prevent the official release CLI from loading it.

## Upgrade procedure

1. Choose a DuckDB release and the corresponding extension-ci-tools release line.
2. Update both submodule commits intentionally. Do not track a moving main branch
   as a substitute for a pinned SDK.
3. Update the runtime default in `Makefile` and `duckdb_version`, `duckdb_commit`,
   `ci_tools_version` and reusable workflow references in
   `.github/workflows/MainDistributionPipeline.yml`.
4. Build the extension and load it into the official release CLI with ordinary
   version validation enabled. Use `-unsigned` only for the local unsigned artifact.
5. Run the unit, browser, export and native integration commands in
   [test/README.md](../test/README.md), including spatial map-feature checks.
6. Verify the distribution matrix and community-extension build before claiming
   cross-platform compatibility. Update README version and API notes with the change.

For API changes, consult [DuckDB releases](https://github.com/duckdb/duckdb/releases)
and the relevant headers at the selected SDK revision. Keep scalar functions with
side effects volatile; verify PREPARE, NULL arguments, multirow vectors, recoverable
errors, server shutdown and HTTP query results after each upgrade.
