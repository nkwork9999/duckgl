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
