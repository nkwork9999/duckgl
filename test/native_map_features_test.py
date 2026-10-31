"""Real DuckDB/spatial integration for schema, geometry selection, CRS and SQL maps.

Install spatial in the matching runtime before running. No HTTP or SQL mocks.
"""

import argparse
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class MapFeatures(unittest.TestCase):
    configuration = None

    @classmethod
    def setUpClass(cls):
        if cls.configuration is None:
            raise unittest.SkipTest("Run this script with --duckdb and --extension")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        cls.base = f"http://127.0.0.1:{port}"
        cls.log = tempfile.TemporaryFile(mode="w+t")
        cls.process = subprocess.Popen(
            [str(cls.configuration.duckdb.resolve()), "-unsigned", "-batch", "-init", "/dev/null"],
            stdin=subprocess.PIPE,
            stdout=cls.log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        cls.addClassCleanup(cls.shutdown)
        extension = str(cls.configuration.extension.resolve()).replace("'", "''")
        cls.process.stdin.write(
            f"LOAD '{extension}';\nLOAD spatial;\n"
            'CREATE TABLE places AS SELECT ST_Point(12,34) AS geom, ST_Point(56,78) AS "alt位置", '
            "'text' AS geometry, true AS enabled;\n"
            "CREATE TABLE projected AS SELECT ST_Point(1113194.9079327357, 0) AS shape;\n"
            f"SELECT duckgl_start('127.0.0.1', {port});\n"
        )
        cls.process.stdin.flush()
        for _ in range(150):
            try:
                with urlopen(cls.base + "/", timeout=1):
                    return
            except OSError:
                if cls.process.poll() is not None:
                    break
                time.sleep(0.1)
        raise AssertionError("Native map server failed to start")

    @classmethod
    def shutdown(cls):
        if cls.process.poll() is None:
            cls.process.stdin.write("SELECT duckgl_stop();\n.quit\n")
            cls.process.stdin.flush()
            try:
                cls.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                cls.process.terminate()
                cls.process.wait(timeout=10)
        cls.log.seek(0)
        output = cls.log.read()
        cls.log.close()
        if cls.process.returncode != 0 or "Error:" in output:
            raise AssertionError(output)

    def request(self, path, sql=None):
        request = Request(
            self.base + path, data=None if sql is None else sql.encode(), headers={"Content-Type": "text/plain"}
        )
        try:
            response = urlopen(request, timeout=15)
        except HTTPError as error:
            response = error
        with response:
            body = response.read().decode()
            self.assertNotEqual(response.status, 404, f"Missing endpoint: {path}")
            return json.loads(body)

    def test_columns_distinguish_geometry_types_from_names(self):
        columns = self.request("/api/columns/places")
        self.assertEqual(
            [(c["column_name"], c["is_geometry"]) for c in columns],
            [("geom", True), ("alt位置", True), ("geometry", False), ("enabled", False)],
        )
        self.assertEqual(columns[2]["data_type"], "VARCHAR")

    def test_explicit_geometry_column_and_missing_column(self):
        data = self.request("/api/geojson/places?" + urlencode({"geometry": "alt位置"}))
        self.assertEqual(data["features"][0]["geometry"]["coordinates"], [56, 78])
        error = self.request("/api/geojson/places?geometry=geometry")
        self.assertIn("error", error)
        self.assertEqual(error["features"], [])

    def test_projected_coordinates_are_transformed_with_xy_axis_order(self):
        data = self.request("/api/geojson/projected?source_crs=EPSG%3A3857")
        x, y = data["features"][0]["geometry"]["coordinates"]
        self.assertAlmostEqual(x, 10, places=7)
        self.assertAlmostEqual(y, 0, places=7)
        error = self.request("/api/geojson/projected?source_crs=INVALID")
        self.assertIn("error", error)

    def test_filtered_query_map_with_semicolon_and_quoted_alias(self):
        data = self.request(
            "/api/query-map",
            '''WITH q AS (SELECT * FROM places)
            SELECT "alt位置" AS "shape位置", 'a; b' AS label, enabled FROM q WHERE enabled;''',
        )
        self.assertEqual(
            data["features"],
            [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [56, 78]},
                    "properties": {"label": "a; b", "enabled": True},
                }
            ],
        )
        empty = self.request("/api/query-map", "SELECT geom FROM places WHERE false")
        self.assertEqual(empty["features"], [])

    def test_query_map_rejects_non_select_and_multiple_statements(self):
        for sql in [
            "CREATE TABLE forbidden AS SELECT 1",
            "SELECT geom FROM places; DROP TABLE places",
            "SELECT 42 AS id",
            "",
        ]:
            with self.subTest(sql=sql):
                self.assertIn("error", self.request("/api/query-map", sql))
        self.assertEqual(self.request("/api/query", "SELECT count(*) AS n FROM places"), [{"n": 1}])
        tables = self.request("/api/tables")
        self.assertFalse(any(table["table_name"] == "forbidden" for table in tables))

    def test_query_map_uses_selected_geometry_and_crs(self):
        data = self.request("/api/query-map?source_crs=EPSG%3A3857&geometry=shape", "SELECT * FROM projected")
        self.assertAlmostEqual(data["features"][0]["geometry"]["coordinates"][0], 10, places=7)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duckdb", required=True, type=Path)
    parser.add_argument("--extension", required=True, type=Path)
    MapFeatures.configuration, unittest_args = parser.parse_known_args()
    unittest.main(argv=[__file__, *unittest_args])
