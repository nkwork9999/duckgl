# Improvement progress

## Map and export capabilities — 2026-10-31

Ten user-facing additions on main: CSV results, JSON results, GeoJSON data,
standalone SVG, PNG overviews, interactive HTML maps, column inspection with
geometry selection, source-CRS transformation, SQL query maps, and feature-property
inspection. The README now documents each output's data source, offline behavior,
coordinate conventions, APIs, examples, tests and troubleshooting.

Validation includes browser downloads and file parsing, real PNG rendering,
saved HTML reopening, and native DuckDB 2.0.0/spatial tests for typed columns,
geometry selection, CRS accuracy and SELECT validation. Earlier catalog and
large-integer fixes are retained.

## Historical improvement batches

Target: 100 independently reviewable improvements. Completed in this batch: 21. The target is not complete. Test cases and formatting edits are not counted separately.

1. JSON column names escape quotes and control bytes.
2. JSON cell strings escape every ASCII control byte.
3. Query error strings use the shared JSON encoder.
4. GeoJSON error strings use the shared JSON encoder.
5. GeoJSON property names and strings use the shared JSON encoder.
6. Numeric query cells retain JSON numeric types.
7. Boolean query cells retain JSON boolean types.
8. Non-finite numeric values are encoded as JSON null.
9. Geometry metadata lookups escape SQL string literals.
10. Geometry SELECT queries escape table and column identifiers.
11. Query result headers and cells render as DOM text.
12. Table selectors use text nodes and event listeners.
13. Table route URLs encode table names.
14. Fallback SELECT queries quote table identifiers.
15. Empty SQL is rejected in the frontend.
16. Invalid ports and empty/NUL hosts are rejected before server replacement.
17. Bind failures are reported synchronously.
18. Browser launch waits for server readiness.
19. Finished listener threads are joined during shutdown.
20. Standalone encoding and frontend regression runners cover hostile names.
21. Linux and macOS CI run the regression suite.

## Validation

Standalone C++ encoding regressions and embedded JavaScript regressions passed. Translation unit passed clang++ syntax checking against miniplot DuckDB headers. Full extension integration remains unverified.

## UI simplification follow-up

The default UI now focuses on table selection, SQL execution and result viewing.
Added searchable schema-aware table selection, keyboard execution, explicit NULL
values, accessible status/focus controls, responsive layouts, failure/retry
feedback and duplicate-request prevention. DuckGL fits map bounds to selected
geometry and queries the selected schema. DuckDBI exposes chart controls only on
request and keeps dashboards/reports at `/advanced`; CSV exports quote values.

Validation: standalone regressions and Playwright browser regressions passed.
Native production HTTP servers passed integration tests against installed DuckDB
1.5.2, including real query results and restart. Browser visualization libraries
are mocked; real map-tile rendering and community extension loader/build CI are
separate checks. These changes do not represent completion of the 100-item target.

Distribution CI follow-up: use DuckDB v1.5.3 and the matching v1.5-variegata
CI tools. The old workflows used incompatible/outdated releases (DuckGL also
used the template extension name). Old musl jobs failed in Docker setup before
compilation. Current cross-platform CI remains to be verified; no platforms
were excluded to hide these failures.
