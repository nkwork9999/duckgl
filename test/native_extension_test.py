"""Exercise the loaded extension's real HTTP query serialization.

Run with --duckdb /path/to/matching/duckdb --extension /path/to/duckgl.duckdb_extension.
No Python DuckDB package, HTTP mocks, or external services are used.
"""

import argparse
import csv
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duckdb", required=True, type=Path)
    parser.add_argument("--extension", required=True, type=Path)
    args = parser.parse_args()
    extension_name = "duckgl"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base_url = f"http://127.0.0.1:{port}"

    def get(path):
        with urlopen(base_url + path, timeout=10) as response:
            return response.read().decode("utf-8")

    def query(sql):
        request = Request(
            base_url + "/api/query",
            data=sql.encode("utf-8"),
            headers={"Content-Type": "text/plain"},
        )
        with urlopen(request, timeout=10) as response:
            return json.load(response)

    with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryFile(mode="w+t") as log:
        process = subprocess.Popen(
            [str(args.duckdb.resolve()), "-unsigned", "-batch", "-init", "/dev/null"],
            stdin=subprocess.PIPE,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            extension_path = str(args.extension.resolve()).replace("'", "''")
            ready = Path(directory) / "prepared.csv"
            process.stdin.write(
                f"LOAD '{extension_path}';\n"
                "CREATE SCHEMA analytics;\n"
                "CREATE TABLE analytics.orders AS SELECT 42 AS amount;\n"
                f"PREPARE startup AS SELECT {extension_name}_start('127.0.0.1', {port});\n"
                f"COPY (SELECT 1) TO '{ready}';\n"
            )
            process.stdin.flush()
            for attempt in range(150):
                if ready.exists():
                    break
                if process.poll() is not None:
                    raise AssertionError("DuckDB exited while preparing start")
                time.sleep(0.1)
            else:
                raise AssertionError("PREPARE did not finish")
            with socket.socket() as probe:
                probe.settimeout(1)
                assert probe.connect_ex(("127.0.0.1", port)) != 0, "PREPARE started the HTTP server before EXECUTE"
            starts = Path(directory) / "starts.csv"
            process.stdin.write(
                "EXECUTE startup;\n"
                f"COPY (SELECT {extension_name}_start('127.0.0.1', {port}) AS status "
                f"FROM range(3)) TO '{starts}' (FORMAT CSV, HEADER FALSE);\n"
            )
            process.stdin.flush()
            for attempt in range(150):
                try:
                    assert "Filter tables" in get("/")
                    break
                except OSError:
                    if process.poll() is not None:
                        raise AssertionError("DuckDB exited before starting HTTP")
                    time.sleep(0.1)
            else:
                raise AssertionError("HTTP server did not start")

            for attempt in range(150):
                if starts.exists() and len(starts.read_text().splitlines()) == 3:
                    break
                time.sleep(0.1)
            statuses = [row[0] for row in csv.reader(starts.read_text().splitlines())]
            assert len(statuses) == 3 and all(str(port) in status for status in statuses), statuses

            assert {"table_name": "orders", "table_schema": "analytics"} in json.loads(get("/api/tables"))
            # Column names must retain raw spelling, UTF-8 and JSON escapes;
            # boolean/numeric/NULL values must retain their JSON types.
            assert query(
                "SELECT '日本語' AS \"Mixed Case\", 7 AS \"a\"\"b\", "
                "true AS enabled, false AS disabled, 1.25::DECIMAL(5,2) AS amount, "
                "NULL::INTEGER AS missing, 'quoted \"value\"' AS text"
            ) == [
                {
                    "Mixed Case": "日本語",
                    "a\"b": 7,
                    "enabled": True,
                    "disabled": False,
                    "amount": 1.25,
                    "missing": None,
                    "text": 'quoted "value"',
                }
            ]
            assert query("SELECT 1 AS \"日本語\", 2 AS \" \"") == [{"日本語": 1, " ": 2}]
            rows = query(
                "SELECT i AS \"行番号\", i % 2 = 0 AS even, "
                "CASE WHEN i % 3 = 0 THEN NULL ELSE i END AS nullable "
                "FROM range(5001) t(i) WHERE i % 5 <> 1 ORDER BY i"
            )
            assert len(rows) == 4001
            for row in rows:
                i = row["行番号"]
                assert i % 5 != 1
                assert row == {
                    "行番号": i,
                    "even": i % 2 == 0,
                    "nullable": None if i % 3 == 0 else i,
                }
            assert rows[-1]["行番号"] == 5000
            assert query("SELECT 1 AS a WHERE false") == []
            assert "error" in query("SELECT * FROM nonexistent_metadata_fixture")
            for invalid_port in [0, 65536]:
                error = query(f"SELECT {extension_name}_start('127.0.0.1', {invalid_port})")
                assert "HTTP port must be between 1 and 65535" in error["error"]
                assert "not marked as fallible" not in error["error"]
            assert query("SELECT 99 AS recovered") == [{"recovered": 99}]
            assert "buildDuckGLReport" in get("/export.js")
            print(f"{extension_name}: loaded extension HTTP regressions passed (4001 rows)")
        finally:
            if process.poll() is None:
                process.stdin.write(f"SELECT {extension_name}_stop();\n.quit\n")
                process.stdin.flush()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    process.wait(timeout=10)
            log.seek(0)
            output = log.read()
            if process.returncode != 0:
                raise AssertionError(output)
            if "Error:" in output or "INTERNAL Error" in output:
                raise AssertionError(output)


if __name__ == "__main__":
    main()
