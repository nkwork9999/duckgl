#!/usr/bin/env python3
"""Exercise a compiled extension through the matching DuckDB CLI and real HTTP."""
import argparse
import json
from pathlib import Path
import queue
import socket
import subprocess
import threading
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duckdb", required=True)
    parser.add_argument("--extension", required=True)
    args = parser.parse_args()
    name = Path(args.extension).stem
    assert name in ("duckdbi", "duckgl")
    extension = str(Path(args.extension).resolve()).replace("'", "''")
    load = f"LOAD '{extension}';"
    command = [args.duckdb, "-no-agent", "-unsigned", "-csv", "-noheader"]

    # Invalid input must produce an ordinary execution error, not invalidate the DB.
    checked = subprocess.run(
        command,
        input=load + f"\nSELECT {name}_start('127.0.0.1', 0);\nSELECT 42;\n",
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert "HTTP port must be between 1 and 65535" in checked.stderr, checked.stderr
    assert "INTERNAL" not in checked.stderr and "not marked as fallible" not in checked.stderr, checked.stderr
    assert checked.stdout.strip() == "42", checked.stdout

    # More than two batches must return a non-NULL value for every call.
    checked = subprocess.run(
        command
        + [
            "-c",
            load + f" SELECT count(*) FROM "
            f"(SELECT {name}_stop() AS message FROM range(4097)) WHERE message = 'No server running';",
        ],
        text=True,
        capture_output=True,
        timeout=30,
        check=True,
    )
    assert checked.stdout.strip() == "4097", checked.stdout

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1
    )
    output = queue.Queue()
    threading.Thread(target=lambda: [output.put(line.rstrip()) for line in process.stdout], daemon=True).start()

    def sql(text):
        process.stdin.write(text + "\n.print READY\n")
        process.stdin.flush()
        lines = []
        while True:
            line = output.get(timeout=30)
            if line == "READY":
                return lines
            lines.append(line)

    def http(route, query=None):
        request = Request(
            f"http://127.0.0.1:{port}" + route,
            data=query.encode() if query is not None else None,
            headers={"Content-Type": "text/plain"},
        )
        with urlopen(request, timeout=10) as response:
            return response.read().decode()

    try:
        sql(load + " CREATE TABLE sample AS SELECT 0 AS amount, NULL::VARCHAR AS missing;")
        started = sql(f"SELECT {name}_start('127.0.0.1', {port});")
        assert len(started) == 1 and str(port) in started[0], started
        assert "Filter tables" in http("/")
        assert any(row["table_name"] == "sample" for row in json.loads(http("/api/tables")))
        assert json.loads(
            http("/api/query", 'SELECT 7 AS "quoted ""column", true AS flag, NULL::INTEGER AS missing')
        ) == [{'quoted "column': 7, 'flag': True, 'missing': None}]
        rows = json.loads(http("/api/query", "SELECT i FROM range(4097) t(i) ORDER BY i"))
        assert len(rows) == 4097 and rows[0] == {"i": 0} and rows[-1] == {"i": 4096}
        assert "error" in json.loads(http("/api/query", "SELECT * FROM nonexistent"))
        assert json.loads(http("/api/query", "SELECT 42 AS answer")) == [{"answer": 42}]
        if name == "duckdbi":
            assert "dashboard" in http("/advanced") and "localStorage" in http("/ui.js")
        stopped = sql(f"SELECT {name}_stop();")
        assert len(stopped) == 1 and "stopped" in stopped[0], stopped
        assert sql(f"SELECT {name}_start(NULL, {port}) IS NULL;") == ["true"]
        assert sql(f"SELECT {name}_stop();") == ["No server running"]
    finally:
        try:
            process.communicate(".quit\n", timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
    assert process.returncode == 0
    print(f"{name}: native extension SQL, metadata, HTTP, errors, NULLs and batches passed")


if __name__ == "__main__":
    main()
