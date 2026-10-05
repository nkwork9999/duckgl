# Improvement progress

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
