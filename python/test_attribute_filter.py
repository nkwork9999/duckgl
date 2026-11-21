import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import duckdb

from duckgl_embedded import (
    AllOf, AnyOf, AttributeColumn, AttributeFilter, FilterOperator, PointLayer, SelectionStatistics, TimeRange, Viewport,
)


class AttributeFilterTests(unittest.TestCase):
    def setUp(self):
        self.db = duckdb.connect()
        self.addCleanup(self.db.close)
        self.db.execute("""
            CREATE TABLE sites(feature_id BIGINT, longitude DOUBLE, latitude DOUBLE,
                               label VARCHAR, elevation DOUBLE, private_flag BOOLEAN);
            INSERT INTO sites VALUES
              (1, 179, 0, 'O''Brien', 120, TRUE),
              (2, -179, 0, 'station', 300, FALSE),
              (3, 0, 0, 'station', 350, TRUE),
              (4, 180, 0, NULL, NULL, TRUE);
        """)
        self.layer = PointLayer(self.db, "sites", attributes={
            "name": AttributeColumn("label", str),
            "height": AttributeColumn("elevation", float),
        })
        self.viewport = Viewport(178, -1, -178, 1)

    def test_typed_tree_filters_points_and_grid_consistently(self):
        spec = AnyOf((AllOf((AttributeFilter("name", FilterOperator.EQ, "O'Brien"),
                             AttributeFilter("height", FilterOperator.LT, 200.0))),
                      AttributeFilter("name", FilterOperator.IS_NULL)))
        self.assertEqual([point.feature_id for point in self.layer.fetch(self.viewport, where=spec)], [1, 4])
        cells = self.layer.fetch_at_zoom(self.viewport, 3, where=spec)
        self.assertEqual(sum(cell.count for cell in cells), 2)

    def test_invalid_specs_are_rejected_before_database_access(self):
        unregistered = AttributeFilter("private_flag", FilterOperator.EQ, True)
        wrong_type = AttributeFilter("height", FilterOperator.GE, "200")
        deep = AttributeFilter("name", FilterOperator.EQ, "station")
        for _ in range(12):
            deep = AnyOf((deep,))
        unused_db = PointLayer(None, "sites", attributes={"height": AttributeColumn("elevation", float)})
        for spec, error in [(unregistered, KeyError), (wrong_type, TypeError), (deep, ValueError)]:
            with self.subTest(spec=spec), self.assertRaises(error):
                unused_db.fetch(self.viewport, where=spec)

    def test_half_open_times_use_absolute_instants_across_midnight_and_dst(self):
        self.db.execute("ALTER TABLE sites ADD COLUMN observed_at TIMESTAMPTZ")
        self.db.execute("""
            UPDATE sites SET observed_at = CASE feature_id
                WHEN 1 THEN TIMESTAMPTZ '2026-11-01 01:30:00-07'
                WHEN 2 THEN TIMESTAMPTZ '2026-11-01 01:30:00-08'
                WHEN 3 THEN TIMESTAMPTZ '2026-11-01 06:00:00Z'
                WHEN 4 THEN TIMESTAMPTZ '2026-11-01 00:00:00-07' END
        """)
        layer = PointLayer(self.db, "sites", time_column="observed_at")
        tz = ZoneInfo("America/Los_Angeles")
        first = datetime(2026, 11, 1, 1, 30, tzinfo=tz, fold=0)
        second = datetime(2026, 11, 1, 1, 30, tzinfo=tz, fold=1)
        self.assertEqual([p.feature_id for p in layer.fetch(self.viewport, time=TimeRange(first, second))], [1])
        since_midnight = TimeRange(datetime(2026, 10, 31, 23, 45, tzinfo=tz), first.astimezone(timezone.utc))
        self.assertEqual([p.feature_id for p in layer.fetch(self.viewport, time=since_midnight)], [4])
        self.assertEqual(sum(c.count for c in layer.fetch_at_zoom(self.viewport, 3, time=since_midnight)), 1)
        with self.assertRaises(ValueError):
            TimeRange(second, first)

    def test_polygon_statistics_use_exact_shape_and_inclusive_boundary(self):
        self.db.load_extension("spatial")
        self.db.execute("INSERT INTO sites VALUES (5,1,1,'edge',NULL,FALSE), (6,1.75,1.75,'outside',500,TRUE)")
        area = ((0, 0), (2, 0), (0, 2), (0, 0))
        self.assertEqual(self.layer.polygon_statistics(area, sum_attribute="height"),
                         SelectionStatistics(2, 350.0))
        with self.assertRaises(KeyError):
            self.layer.polygon_statistics(area, sum_attribute="private_flag")
        crossing = ((0, 0), (2, 2), (0, 2), (2, 0), (0, 0))
        with self.assertRaisesRegex(ValueError, "valid polygon"):
            self.layer.polygon_statistics(crossing)
