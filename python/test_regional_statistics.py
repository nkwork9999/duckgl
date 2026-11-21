import unittest

import duckdb

from duckgl_embedded import BoundaryAssignment, RegionalStatistics


class RegionalStatisticsTests(unittest.TestCase):
    def test_boundary_and_overlap_follow_the_registered_assignment(self):
        with duckdb.connect() as db:
            db.load_extension("spatial")
            db.execute("""
                CREATE TABLE points AS SELECT i AS feature_id, point AS geometry FROM (VALUES
                    (1, ST_Point(0, 0)), (2, ST_Point(1, 1)), (3, ST_Point(2, 2)),
                    (4, ST_Point(5, 5)), (5, NULL), (6, ST_GeomFromText('POINT EMPTY'))) t(i, point);
                CREATE TABLE regions AS SELECT i AS region_id, extent AS geometry FROM (VALUES
                    (20, ST_MakeEnvelope(0, 0, 1.5, 1.5)), (10, ST_MakeEnvelope(1, 1, 3, 3)),
                    (30, ST_MakeEnvelope(6, 6, 7, 7))) t(i, extent);
            """)
            service = RegionalStatistics(db, "points", "regions")
            all_results = service.count(BoundaryAssignment.ALL_MATCHES)
            self.assertEqual(all_results.region_counts, ((10, 2), (20, 2), (30, 0)))
            one = service.count(BoundaryAssignment.LOWEST_ID)
            self.assertEqual(one.region_counts, ((10, 2), (20, 1), (30, 0)))
            self.assertEqual((one.unmatched, one.no_position), (1, 2))
            with self.assertRaises(TypeError):
                service.count("lowest_id")
