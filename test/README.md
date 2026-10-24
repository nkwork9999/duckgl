# Regression tests

Run `bash scripts/test-unit.sh` for C++ encoding/server helper tests and frontend
syntax and logic checks. Run `npm ci --prefix test`, then
`npx --prefix test playwright install chromium` and `node test/browser.test.cjs`
for browser regressions. Set `UI_BROWSER_CHANNEL=chrome` to use installed Chrome.

The browser tests cover SQL identifier quoting, safe result rendering, NULL and
zero values, table filtering/retry, keyboard execution, duplicate request
prevention, server errors, and mobile layout. DuckGL also checks spatial schema
selection and map bounds; DuckDBI checks chart data and CSV downloads.
HTTP responses and remote visualization libraries are mocked for reproducibility;
these tests do not replace native DuckDB extension or real map-tile integration.

A native HTTP integration test runs the production server against an actual
DuckDB database (without extension-loader metadata). With matching DuckDB headers
and shared library installed, compile `test/native_http_test.cpp` with C++17,
`-I src/include`, the DuckDB include/library paths, and `-lduckdb`, then run it.
It checks HTML routing, real table discovery, JSON values and errors, and restart.
It uses loopback ports 19881 (DuckGL) and 19882 (DuckDBI).

DuckDB v2.0.0 community CI uses source `d54cbbe3df17e8e5ce68312f483b4155836112aa`
(the current untagged SDK reports `v2.0.0-alpha49307`). Build/load the matching
artifact and run:

```sh
python3 test/native_extension_test.py --duckdb build/release/duckdb --extension build/release/extension/duckgl/duckgl.duckdb_extension
```

This uses the actual extension loader and loopback HTTP. It checks that PREPARE
has no server side effect, multirow start results, raw UTF-8/quoted column names,
JSON value types, filtered/multibatch results, errors and connection recovery.
The source distribution pipeline runs it through the Linux post-build hook.
`test/sql/lifecycle.test` also runs in the normal native SQL suite and covers
multirow stop, invalid ports, NULLs and connection reuse.

`node test/export.test.cjs` checks HTML download/escaping/offline behavior, all 305
fixture rows, point/line/polygon-hole SVG output, the printable report's actual
Chromium PDF, and mobile export controls. Visualization libraries and HTTP are
mocked; report generation and PDF rendering are real. Set `DUCKGL_EXPORT_DIR` to
retain the generated HTML/PDF/PNG for visual inspection. The browser workflow
runs this test after the existing browser suite.
