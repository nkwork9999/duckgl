import unittest

import duckdb
from duckgl_embedded import PointLayer, Viewport


class PointViewportTests(unittest.TestCase):
    def test_inclusive_dateline_and_projection(self):
        with duckdb.connect() as db:
            db.execute("""CREATE TABLE "owner's points" AS
                SELECT * FROM (VALUES (1, 180., 0., 'east', 'private'),
                (2, -180., 5., 'west', 'private'), (3, 0., 0., 'out', 'private'),
                (4, 178., NULL, 'null', 'private'), (5, 179., 6., 'out', 'private'))
                t(feature_id, longitude, latitude, label, secret)""")
            layer = PointLayer(db, "owner's points")
            rows = layer.fetch(Viewport(175, 0, -175, 5))
            self.assertEqual([(r.feature_id, r.label) for r in rows], [(1, "east"), (2, "west")])
            self.assertFalse(hasattr(rows[0], "secret"))
            self.assertEqual([r.feature_id for r in layer.fetch(Viewport(0, 0, 180, 5))], [1, 3])

    def test_bad_viewport(self):
        with self.assertRaises(ValueError):
            Viewport(0, -91, 10, 0)
        with self.assertRaises(ValueError):
            Viewport(0, 1, 10, 0)

    def test_grid_counts_boundary_points_once_and_high_zoom_preserves_ids(self):
        with duckdb.connect() as db:
            db.execute("""CREATE TABLE points AS SELECT * FROM (VALUES
                 (1, -180., -90., 'minimum'), (2, -1., -1., NULL),
                 (3, 0., 0., 'boundary'), (4, 180., 90., 'maximum'),
                 (5, 45., NULL, 'missing'))
                 t(feature_id, longitude, latitude, label)""")
            layer = PointLayer(db, "points")
            view = Viewport(-180, -90, 180, 90)
            cells = layer.fetch_at_zoom(view, 1)
            self.assertEqual([(c.x, c.y, c.count) for c in cells], [(0, 0, 1), (1, 0, 1),
                                                                  (2, 1, 1), (3, 1, 1)])
            self.assertEqual(sum(c.count for c in cells), len(layer.fetch(view)))
            self.assertEqual(cells[-1].latitude, 90)
            self.assertEqual(layer.fetch_at_zoom(view, 14), layer.fetch(view))
            with self.assertRaises(ValueError):
                layer.fetch_at_zoom(view, -1)
