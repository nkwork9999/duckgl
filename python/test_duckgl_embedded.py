import json
import os
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

import duckdb
from duckgl_embedded import PublishedLayer


class PublishedLayerTests(unittest.TestCase):
    def setUp(self):
        artifact = os.getenv("DUCKGL_TEST_EXTENSION")
        config = {"allow_unsigned_extensions": bool(artifact)}
        if directory := os.getenv("DUCKDB_EXTENSION_DIRECTORY"):
            config["extension_directory"] = directory
        self.db = duckdb.connect(config=config)
        self.addCleanup(self.db.close)
        self.db.load_extension(artifact or "duckgl")
        self.db.load_extension("spatial")
        self.db.execute("""CREATE VIEW "owner's layer" AS
                           SELECT ST_Point(1, 2) AS geometry, '東京' AS label""")

    def test_live_snapshot_and_shutdown_on_exception(self):
        with self.assertRaisesRegex(ValueError, "host error"):
            with PublishedLayer(self.db, "owner's layer") as url:
                with urlopen(url, timeout=3) as response:
                    feature, = json.load(response)["features"]
                self.assertEqual(feature["geometry"], {"type": "Point", "coordinates": [1.0, 2.0]})
                self.assertEqual(feature["properties"], {"label": "東京"})
                with self.assertRaises(HTTPError) as rejected:
                    urlopen(url + "?table=other", timeout=3)
                self.assertEqual(rejected.exception.code, 400)
                raise ValueError("host error")
        self.assertFalse(self.db.execute("SELECT duckgl_stop_layer()").fetchone()[0])

    def test_rejected_second_publisher_preserves_first(self):
        with PublishedLayer(self.db, "owner's layer") as url:
            with self.assertRaises(duckdb.InvalidInputException):
                with PublishedLayer(self.db, "owner's layer"):
                    self.fail("second publisher should not take over")
            with urlopen(url, timeout=3) as response:
                self.assertEqual(response.status, 200)

    def test_disabled_external_access_prevents_publication(self):
        self.db.execute("SET enable_external_access=false")
        with self.assertRaises(duckdb.PermissionException):
            with PublishedLayer(self.db, "owner's layer"):
                self.fail("publication opened a listener")
        self.assertFalse(self.db.execute("SELECT duckgl_stop_layer()").fetchone()[0])
