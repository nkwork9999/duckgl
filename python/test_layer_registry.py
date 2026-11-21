import unittest

import duckdb

from duckgl_embedded import LayerId, LayerRegistry, RegisteredLayer, Viewport


class LayerRegistryTests(unittest.TestCase):
    def test_catalog_identity_and_revoked_grants_are_checked_on_every_request(self):
        with duckdb.connect() as db:
            db.execute("""
                ATTACH ':memory:' AS delivery;
                CREATE TABLE main.points AS SELECT 1 AS feature_id, 0.0 AS longitude,
                                                   0.0 AS latitude, 'local' AS label;
                CREATE TABLE delivery.main.points AS SELECT 2 AS feature_id, 0.0 AS longitude,
                                                            0.0 AS latitude, 'authorized' AS label;
            """)
            name = LayerId("stations")
            grants = {("principal", name, "v1")}
            registry = LayerRegistry(db, {name: RegisteredLayer("delivery", "points", "v1")},
                                     lambda principal, layer, version: (principal, layer, version) in grants)
            bounds = Viewport(-1, -1, 1, 1)
            version, features = registry.fetch("principal", name, bounds)
            self.assertEqual(version, "v1")
            self.assertEqual([(p.feature_id, p.label) for p in features], [(2, "authorized")])
            grants.clear()
            with self.assertRaises(PermissionError):
                registry.fetch("principal", name, bounds)
            grants.add(("principal", name, "v1"))
            db.execute("""
                DETACH delivery;
                ATTACH ':memory:' AS delivery;
                CREATE TABLE delivery.main.points AS SELECT 3 AS feature_id, 0.0 AS longitude,
                                                            0.0 AS latitude, 'replacement' AS label;
            """)
            with self.assertRaises(LookupError):
                registry.fetch("principal", name, bounds)

    def test_deferred_details_scope_version_omissions_and_revocation(self):
        with duckdb.connect() as db:
            db.execute("""
                CREATE TABLE points(feature_id BIGINT PRIMARY KEY, longitude DOUBLE, latitude DOUBLE,
                                    label VARCHAR, description VARCHAR, confidential VARCHAR);
                INSERT INTO points VALUES (1, 0, 0, 'Marker', 'Public detail', 'Private detail'),
                                          (2, 0, 0, 'Marker', NULL, 'Other private detail')
            """)
            catalog, = db.execute("SELECT current_database()").fetchone()
            name = LayerId("markers")
            grants = {"allowed"}
            registry = LayerRegistry(db, {
                name: RegisteredLayer(catalog, "points", "new", details={"description": "description"})
            }, lambda principal, layer, version: principal in grants)
            version, markers = registry.fetch("allowed", name, Viewport(-1, -1, 1, 1))
            self.assertEqual(version, "new")
            self.assertNotIn("Public detail", str(markers))
            details = registry.details("allowed", name, version=version, feature_ids=[2, 3, 1, 2])
            self.assertEqual([(d.feature_id, d.found, d.attributes) for d in details], [
                (2, True, {"description": None}), (3, False, {}),
                (1, True, {"description": "Public detail"}),
            ])
            with self.assertRaises(LookupError):
                registry.details("allowed", name, version="old", feature_ids=[1])
            with self.assertRaises((TypeError, ValueError)):
                registry.details("allowed", name, version=version, feature_ids=["1"])
            grants.clear()
            with self.assertRaises(PermissionError):
                registry.details("allowed", name, version=version, feature_ids=[1])
