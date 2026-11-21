import unittest

import duckdb

from duckgl_embedded import GeometryLayer, Viewport


class GeometryLayerTests(unittest.TestCase):
    def test_dateline_intersections_include_touching_shapes_once_and_project_declared_columns(self):
        with duckdb.connect() as db:
            db.load_extension("spatial")
            db.execute("""
                CREATE TABLE boundary_data AS SELECT * FROM (VALUES
                    (1, ST_GeomFromText('MULTILINESTRING((178 0,180 0),(-180 0,-178 0))'), 'road', 'internal'),
                    (2, ST_Point(-180,0), 'station', 'internal'),
                    (3, ST_Point(0,0), 'unseen', 'internal'),
                    (4, NULL, 'missing', 'internal'),
                    (5, ST_GeomFromText('LINESTRING(172 1,178 1)'), 'touching', 'internal')
                ) pts(feature_id, geometry, label, secret)
            """)
            layer = GeometryLayer(db, "boundary_data", source_crs="EPSG:4326", attributes={"name": "label"})
            result = layer.fetch(Viewport(178, -1, -178, 1))
            self.assertEqual([row.feature_id for row in result], [1, 2, 5])
            self.assertEqual(result[0].geometry["type"], "MultiLineString")
            self.assertEqual(result[0].attributes, {"name": "road"})
            self.assertNotIn("internal", str(result))

    def test_projected_positions_filter_in_display_crs(self):
        with duckdb.connect() as db:
            db.load_extension("spatial")
            db.execute("""
                CREATE TABLE projected AS SELECT 1 AS feature_id,
                    ST_Transform(ST_Point(140,35),'EPSG:4326','EPSG:3857',true) AS geometry
            """)
            layer = GeometryLayer(db, "projected", source_crs="EPSG:3857")
            hit, = layer.fetch(Viewport(139, 34, 141, 36))
            self.assertAlmostEqual(hit.geometry["coordinates"][0], 140)
            self.assertAlmostEqual(hit.geometry["coordinates"][1], 35)
            self.assertEqual(layer.fetch(Viewport(-10, -10, 10, 10)), [])
