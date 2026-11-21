import unittest
from concurrent.futures import CancelledError
from threading import Event

import duckdb

from duckgl_embedded import SharedTileWork, TileCache, TileId, TileOccupancy, TileScope, VectorTileLayer


# A small decoder for the wire types in this point/line fixture.
# https://github.com/mapbox/vector-tile-spec/blob/master/2.1/vector_tile.proto
def read_varint(data, offset):
    value = shift = 0
    for index in range(offset, len(data)):
        byte = data[index]
        value |= (byte & 127) << shift
        if byte < 128:
            return value, index + 1
        shift += 7
    raise ValueError("truncated varint")


def fields(data):
    offset = 0
    while offset < len(data):
        key, offset = read_varint(data, offset)
        value, offset = read_varint(data, offset)
        if key & 7 == 2:
            yield key >> 3, data[offset:offset + value]
            offset += value
        else:
            assert key & 7 == 0
            yield key >> 3, value


def decode(tile):
    layer, = [value for field, value in fields(tile) if field == 3]
    keys = [value.decode() for field, value in fields(layer) if field == 3]
    decoded = {}
    for tag, value in fields(layer):
        if tag != 2:
            continue
        feature = dict(fields(value))
        geometry = feature[4]
        coord = [0, 0]
        points = []
        offset = 0
        while offset < len(geometry):
            cmd, offset = read_varint(geometry, offset)
            if cmd & 7 not in (1, 2):
                raise ValueError("unexpected command for point or line")
            for _ in range(cmd >> 3):
                for axis in (0, 1):
                    integer, offset = read_varint(geometry, offset)
                    coord[axis] += (integer >> 1) ^ -(integer & 1)
                points.append(tuple(coord))
        decoded[feature.get(1, 0)] = points
    return keys, decoded


class VectorTileTests(unittest.TestCase):
    def test_point_quantization_clipping_and_adjacent_tile_alignment(self):
        with duckdb.connect() as db:
            db.load_extension("spatial")
            db.execute("""
                CREATE TABLE exported AS
                SELECT 1::BIGINT AS feature_id, ST_Point(0, 0) AS geometry, 'center' AS label, 'hidden' AS private
                UNION ALL
                SELECT 2, ST_GeomFromText('LINESTRING(-1000000 1000000, 1000000 1000000)'), 'line', 'hidden'
            """)
            layer = VectorTileLayer(db, "exported", "test_layer", attributes={"label": "label"})
            keys, whole = decode(layer.fetch(TileId(0, 0, 0)))
            self.assertEqual(keys, ["label"])
            self.assertEqual(whole[1], [(2048, 2048)])
            _, left = decode(layer.fetch(TileId(1, 0, 0), buffer=0))
            _, right = decode(layer.fetch(TileId(1, 1, 0), buffer=0))
            self.assertEqual(left[2][-1], (4096, right[2][0][1]))
            self.assertEqual(right[2][0][0], 0)
            self.assertEqual(layer.fetch(TileId(3, 0, 0)), b"")
            with self.assertRaises(ValueError):
                TileId(1, 2, 0)

    def test_cached_revisits_check_version_projection_and_grants(self):
        cache = TileCache(max_entries=2, max_bytes=16)
        coords = TileId(0, 0, 0)
        visible = {("a", "maps"), ("b", "maps")}
        count = 0
        def authorize(scope):
            return (scope.tenant, scope.layer) in visible
        def generate():
            nonlocal count
            count += 1
            return b"tile"
        base = TileScope("a", "maps", "own", "v1", "public")
        first = cache.fetch(base, coords, generate, authorize=authorize)
        self.assertFalse(first.not_modified)
        self.assertEqual(count, 1)
        revisit = cache.fetch(base, coords, generate, authorize=authorize, if_none_match=first.etag)
        self.assertTrue(revisit.not_modified)
        self.assertIsNone(revisit.body)
        self.assertEqual(count, 1)
        for scope in (TileScope("b", "maps", "own", "v1", "public"),
                      TileScope("a", "maps", "own", "v2", "public"),
                      TileScope("a", "maps", "shared", "v1", "public"),
                      TileScope("a", "maps", "own", "v1", "filtered")):
            result = cache.fetch(scope, coords, generate, authorize=authorize, if_none_match=first.etag)
            self.assertNotEqual(result.etag, first.etag)
            self.assertFalse(result.not_modified)
        self.assertEqual(count, 5)
        visible.remove(("a", "maps"))
        with self.assertRaises(PermissionError):
            cache.fetch(base, coords, generate, authorize=authorize, if_none_match=first.etag)
        self.assertEqual(count, 5)
        dynamic = TileScope("b", "maps", "own", None, "public")
        for _ in range(2):
            result = cache.fetch(dynamic, coords, generate, authorize=authorize)
            self.assertIsNone(result.etag)
            self.assertEqual(result.body, b"tile")
        self.assertEqual(count, 7)

    def test_same_tile_shares_work_and_one_cancel_never_interrupts_other_subscribers(self):
        scope, tile = TileScope("tenant", "layer", "group", "v1", "label"), TileId(0, 0, 0)
        entered, release = Event(), Event()
        calls = []
        def generate(cancel):
            calls.append(cancel)
            entered.set()
            if not release.wait(timeout=10):
                raise TimeoutError("test did not release generator")
            return b"shared"
        with SharedTileWork(workers=2) as work:
            first = work.subscribe(scope, tile, generate, authorize=lambda _: True)
            self.assertTrue(entered.wait(timeout=10))
            others = [work.subscribe(scope, tile, generate, authorize=lambda _: True) for _ in range(99)]
            first.cancel()
            self.assertFalse(calls[0].is_set())
            with self.assertRaises(CancelledError):
                first.result()
            release.set()
            for subscriber in others:
                self.assertEqual(subscriber.result(timeout=10), b"shared")
            self.assertEqual(len(calls), 1)

    def test_last_cancel_signals_generator_and_revoked_subscriber_cannot_read(self):
        scope, tile = TileScope("tenant", "layer", "group", "v1", "label"), TileId(0, 0, 0)
        started, stopped = Event(), Event()
        def generate(cancel):
            started.set()
            if cancel.wait(10):
                stopped.set()
            return b"tile"
        with SharedTileWork(workers=1) as work:
            subscriber = work.subscribe(scope, tile, generate, authorize=lambda _: True)
            self.assertTrue(started.wait(10))
            subscriber.cancel()
            self.assertTrue(stopped.wait(10))

            grant = True
            renewed = work.subscribe(scope, tile, lambda cancel: b"tile", authorize=lambda _: grant)
            grant = False
            with self.assertRaises(PermissionError):
                renewed.result(timeout=10)

    def test_empty_occupancy_skips_sql_only_for_its_unchanged_version(self):
        with duckdb.connect() as db:
            db.load_extension("spatial")
            db.execute("CREATE TABLE points AS SELECT 1::BIGINT AS feature_id, ST_Point(100,100) AS geometry")
            layer = VectorTileLayer(db, "points", "points")
            occupancy = TileOccupancy.build(layer, "v1", max_zoom=6)
            distant = TileId(6, 0, 0)
            center = TileId(6, 32, 31)
            self.assertFalse(occupancy.might_have_feature("v1", distant))
            self.assertTrue(occupancy.might_have_feature("v1", center))
            original_fetch = layer.fetch
            def no_query(*args, **kwargs):
                self.fail("no query needed for an empty tile in the occupied snapshot")
            layer.fetch = no_query
            self.assertEqual(occupancy.fetch("v1", distant), b"")
            layer.fetch = original_fetch
            db.execute("INSERT INTO points VALUES (2, ST_Centroid(ST_TileEnvelope(6,0,0)))")
            self.assertTrue(occupancy.might_have_feature("v2", distant))
            self.assertIn(2, decode(occupancy.fetch("v2", distant))[1])
