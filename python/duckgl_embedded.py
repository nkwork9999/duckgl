"""Host-side publication of a single GeoJSON snapshot on loopback."""
from collections import OrderedDict
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from json import dumps, loads
from math import isfinite
from threading import Event, Lock

from duckdb import DuckDBPyConnection


class PublishedLayer:
    """Publish a host-selected main-schema relation for the lifetime of a with block."""

    def __init__(self, connection: DuckDBPyConnection, view: str):
        if type(view) is not str or not view or "\0" in view:
            raise ValueError("view must be a nonempty relation name without NUL")
        self._db = connection
        self._view = view

    def __enter__(self) -> str:
        port, = self._db.execute("SELECT duckgl_start_layer(0, ?)", [self._view]).fetchone()
        return f"http://127.0.0.1:{port}/api/layer"

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self._db.execute("SELECT duckgl_stop_layer()").fetchone()


@dataclass(frozen=True)
class Viewport:
    west: float
    south: float
    east: float
    north: float

    def __post_init__(self):
        for coordinate, limit in ((self.west, 180), (self.east, 180),
                                  (self.south, 90), (self.north, 90)):
            if type(coordinate) not in (float, int) or not -limit <= coordinate <= limit:
                raise ValueError("viewport coordinates must be finite longitude/latitude degrees")
        if self.south > self.north:
            raise ValueError("south must be at or below north")


@dataclass(frozen=True)
class TimeRange:
    """A half-open interval of absolute instants."""

    start: datetime
    end: datetime

    def __post_init__(self):
        for value in (self.start, self.end):
            if type(value) is not datetime or value.utcoffset() is None:
                raise ValueError("time bounds must be timezone-aware datetimes")
        start = self.start.astimezone(timezone.utc)
        end = self.end.astimezone(timezone.utc)
        if end < start:
            raise ValueError("time range end precedes start")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)


@dataclass(frozen=True)
class MapPoint:
    feature_id: int
    longitude: float
    latitude: float
    label: str | None


@dataclass(frozen=True)
class GridCell:
    x: int
    y: int
    count: int
    longitude: float
    latitude: float


@dataclass(frozen=True)
class SelectionStatistics:
    count: int
    total: float | int | None


class FilterOperator(Enum):
    EQ = "="
    NE = "<>"
    LT = "<"
    LE = "<="
    GT = ">"
    GE = ">="
    IS_NULL = "IS NULL"
    IS_NOT_NULL = "IS NOT NULL"


def _identifier(name):
    if type(name) is not str or not name or "\0" in name:
        raise ValueError("expected a nonempty main-schema identifier without NUL")
    return '"' + name.replace('"', '""') + '"'


@dataclass(frozen=True)
class AttributeColumn:
    """Column name and value type registered by the application host."""

    name: str
    value_type: type

    def __post_init__(self):
        _identifier(self.name)
        if self.value_type not in (str, int, float, bool):
            raise TypeError("expected str, int, float or bool")


@dataclass(frozen=True)
class AttributeFilter:
    column_id: str
    operator: FilterOperator
    value: str | int | float | bool | None = None


@dataclass(frozen=True)
class AllOf:
    terms: tuple["FilterSpec", ...]


@dataclass(frozen=True)
class AnyOf:
    terms: tuple["FilterSpec", ...]


FilterSpec = AttributeFilter | AllOf | AnyOf


class PointLayer:
    """Read WGS84 points from a trusted host-selected main-schema relation.

    The host provisions a tenant-scoped connection and a primary/unique
    feature_id. Longitudes in the source use the [-180, 180] convention.
    """

    def __init__(self, connection: DuckDBPyConnection, relation: str, *, attributes=None,
                 time_column: str | None = None, catalog: str | None = None):
        self._db = connection
        schema = "main" if catalog is None else f"{_identifier(catalog)}.main"
        self._relation = f"{schema}.{_identifier(relation)}"
        self._time_column = None if time_column is None else _identifier(time_column)
        self._attributes = dict(attributes) if attributes is not None else {}
        if any(type(key) is not str or not key or type(col) is not AttributeColumn
               for key, col in self._attributes.items()):
            raise TypeError("attribute registration must map string IDs to AttributeColumns")

    def _attribute_filter(self, spec: FilterSpec) -> tuple[str, list]:
        values = []
        nodes = 0

        def compile_term(term, depth):
            nonlocal nodes
            nodes += 1
            if depth > 8 or nodes > 256:
                raise ValueError("attribute filter exceeds the depth or node limit")
            if type(term) in (AllOf, AnyOf):
                if type(term.terms) is not tuple or not term.terms:
                    raise ValueError("compound filters require a nonempty tuple")
                joiner = " AND " if type(term) is AllOf else " OR "
                return "(" + joiner.join(compile_term(child, depth + 1) for child in term.terms) + ")"
            if type(term) is not AttributeFilter or type(term.operator) is not FilterOperator:
                raise TypeError("expected a typed attribute filter")
            if type(term.column_id) is not str:
                raise TypeError("column IDs must be strings")
            column = self._attributes[term.column_id]
            op = term.operator
            identifier = _identifier(column.name)
            if op in (FilterOperator.IS_NULL, FilterOperator.IS_NOT_NULL):
                if term.value is not None:
                    raise TypeError("null predicates take no value")
                return f"{identifier} {op.value}"
            if type(term.value) is not column.value_type:
                raise TypeError("filter value does not match the registered column type")
            if column.value_type is bool and op not in (FilterOperator.EQ, FilterOperator.NE):
                raise ValueError("boolean filters support equality and null checks")
            if column.value_type is float and not isfinite(term.value):
                raise ValueError("floating-point filter values must be finite")
            if column.value_type is int and not -(1 << 63) <= term.value < (1 << 63):
                raise ValueError("integer filter values must fit a signed 64-bit integer")
            values.append(term.value)
            return f"{identifier} {op.value} ?"

        return compile_term(spec, 1), values

    def _viewport_filter(self, viewport: Viewport, where: FilterSpec | None,
                         time: TimeRange | None) -> tuple[str, list]:
        if type(viewport) is not Viewport:
            raise TypeError("expected a Viewport")
        longitude_filter = ("(longitude >= ? OR longitude <= ?)" if viewport.west > viewport.east
                            else "longitude BETWEEN ? AND ?")
        predicate = f"""
            WHERE latitude BETWEEN ? AND ?
              AND longitude BETWEEN -180 AND 180 AND {longitude_filter}
        """
        values = [viewport.south, viewport.north, viewport.west, viewport.east]
        if time is not None:
            if type(time) is not TimeRange or self._time_column is None:
                raise ValueError("a TimeRange requires a registered TIMESTAMPTZ column")
            predicate += f" AND {self._time_column} >= ?::TIMESTAMPTZ AND {self._time_column} < ?::TIMESTAMPTZ"
            values.extend([time.start, time.end])
        if where is not None:
            clause, bound = self._attribute_filter(where)
            predicate += f" AND ({clause})"
            values.extend(bound)
        return predicate, values

    def fetch(self, viewport: Viewport, *, where: FilterSpec | None = None,
              time: TimeRange | None = None) -> list[MapPoint]:
        selection, values = self._viewport_filter(viewport, where, time)
        rows = self._db.execute(f"""
            SELECT feature_id, longitude::DOUBLE, latitude::DOUBLE, label
            FROM {self._relation} {selection} ORDER BY feature_id
        """, values).fetchall()
        return [MapPoint(*row) for row in rows]

    def fetch_at_zoom(self, viewport: Viewport, zoom: int, *,
                      where: FilterSpec | None = None, time: TimeRange | None = None) -> list[GridCell] | list[MapPoint]:
        """Use a world-aligned degree grid below zoom 14 and points at higher zoom."""
        if type(zoom) is not int or not 0 <= zoom <= 30:
            raise ValueError("zoom must be an integer between 0 and 30")
        if zoom >= 14:
            return self.fetch(viewport, where=where, time=time)

        selection, values = self._viewport_filter(viewport, where, time)
        vertical_cells = 1 << zoom
        rows = self._db.execute(f"""
            WITH cells AS (
                SELECT least(2 * n - 1, floor((longitude::DOUBLE + 180) * n / 180))::INTEGER AS x,
                       least(n - 1, floor((latitude::DOUBLE + 90) * n / 180))::INTEGER AS y,
                       longitude::DOUBLE AS lon, latitude::DOUBLE AS lat
                FROM (SELECT longitude, latitude FROM {self._relation} {selection}) AS points
                CROSS JOIN (SELECT ?::INTEGER AS n) AS dimensions
            )
            SELECT x, y, count(*), avg(lon), avg(lat)
            FROM cells GROUP BY x, y ORDER BY x, y
        """, [*values, vertical_cells]).fetchall()
        return [GridCell(*row) for row in rows]

    def polygon_statistics(self, ring: tuple[tuple[float, float], ...], *,
                           sum_attribute: str | None = None) -> SelectionStatistics:
        """Aggregate original point coordinates inside a closed WGS84 selection ring."""
        if type(ring) is not tuple or not 4 <= len(ring) <= 10_000:
            raise ValueError("a polygon ring must contain 4–10000 coordinate pairs")
        vertices = []
        for point in ring:
            if type(point) is not tuple or len(point) != 2:
                raise TypeError("expected (longitude, latitude) tuples")
            x, y = point
            if type(x) not in (float, int) or type(y) not in (float, int) or not (-180 <= x <= 180 and -90 <= y <= 90):
                raise ValueError("polygon coordinates must be finite WGS84 degrees")
            vertices.append({"x": x, "y": y})
        if ring[0] != ring[-1] or any(abs(a[0] - b[0]) > 180 for a, b in zip(ring, ring[1:])):
            raise ValueError("close the ring and split selections at the antimeridian")

        projection = "NULL"
        if sum_attribute is not None:
            column = self._attributes[sum_attribute]
            if column.value_type not in (int, float):
                raise TypeError("sum requires a registered numeric attribute")
            projection = f"layer.{_identifier(column.name)}"

        west, east = min(p[0] for p in ring), max(p[0] for p in ring)
        south, north = min(p[1] for p in ring), max(p[1] for p in ring)
        valid, count, total = self._db.execute(f"""
            WITH shape AS (
                SELECT ST_MakePolygon(ST_MakeLine(list_transform(
                    ?::STRUCT(x DOUBLE, y DOUBLE)[], lambda p: ST_Point(p.x, p.y)))) AS area
            ), checked AS MATERIALIZED (
                SELECT area, ST_IsValid(area) AS valid FROM shape
            ), points AS (
                SELECT {projection} AS sample, CASE WHEN checked.valid THEN
                    ST_Covers(checked.area, ST_Point(layer.longitude, layer.latitude)) END AS covered
                FROM {self._relation} AS layer CROSS JOIN checked
                WHERE layer.longitude BETWEEN ? AND ? AND layer.latitude BETWEEN ? AND ?
            )
            SELECT (SELECT valid FROM checked), count(*) FILTER (WHERE covered),
                   sum(sample) FILTER (WHERE covered)
            FROM points
        """, [vertices, west, east, south, north]).fetchone()
        if not valid:
            raise ValueError("selection ring must form a valid polygon")
        return SelectionStatistics(count, total)


class BoundaryAssignment(Enum):
    ALL_MATCHES = "all_matches"
    LOWEST_ID = "lowest_id"


@dataclass(frozen=True)
class RegionCounts:
    region_counts: tuple[tuple[int, int], ...]
    unmatched: int
    no_position: int


class RegionalStatistics:
    """Count registered, same-CRS points in regions using inclusive polygon boundaries."""

    def __init__(self, connection: DuckDBPyConnection, points: str, regions: str):
        self._db = connection
        self._points = f"main.{_identifier(points)}"
        self._regions = f"main.{_identifier(regions)}"

    def count(self, assignment: BoundaryAssignment) -> RegionCounts:
        if type(assignment) is not BoundaryAssignment:
            raise TypeError("expected a BoundaryAssignment")
        selected = ("SELECT feature_id, min(region_id) AS region_id FROM covered GROUP BY feature_id"
                    if assignment is BoundaryAssignment.LOWEST_ID else "SELECT feature_id, region_id FROM covered")
        rows, unmatched, missing = self._db.execute(f"""
            WITH input_points AS MATERIALIZED (
                SELECT feature_id, geometry, geometry IS NOT NULL AND NOT ST_IsEmpty(geometry) AS present
                FROM {self._points}
            ), covered AS MATERIALIZED (
                SELECT p.feature_id, r.region_id
                FROM input_points AS p JOIN {self._regions} AS r ON ST_Covers(r.geometry, p.geometry)
                WHERE p.present
            ), assigned AS (
                {selected}
            ), counts AS (
                SELECT region_id, count(*) AS n FROM assigned GROUP BY region_id
            ), output AS (
                SELECT list(struct_pack(id := r.region_id, n := coalesce(c.n, 0)) ORDER BY r.region_id) AS regions
                FROM {self._regions} AS r LEFT JOIN counts AS c USING (region_id)
            ), classified AS (
                SELECT count(*) FILTER (WHERE present AND NOT EXISTS (
                    SELECT 1 FROM covered AS c WHERE c.feature_id = p.feature_id
                )) AS unmatched, count(*) FILTER (WHERE NOT present) AS no_position FROM input_points AS p
            )
            SELECT regions, unmatched, no_position FROM output CROSS JOIN classified
        """).fetchone()
        return RegionCounts(tuple((row["id"], row["n"]) for row in (rows or [])), unmatched, missing)


@dataclass(frozen=True)
class GeometryFeature:
    feature_id: int
    geometry: dict
    attributes: dict


class GeometryLayer:
    """Project registered geometry attributes and select features by a WGS84 viewport."""

    def __init__(self, connection: DuckDBPyConnection, relation: str, *, source_crs: str,
                 attributes: Mapping[str, str] | None = None, catalog: str | None = None):
        if type(source_crs) is not str or not source_crs:
            raise ValueError("the host must provide the source CRS")
        self._db = connection
        self._crs = source_crs
        schema = "main" if catalog is None else f"{_identifier(catalog)}.main"
        self._relation = f"{schema}.{_identifier(relation)}"
        self._attributes = tuple((alias, _identifier(column)) for alias, column in (attributes or {}).items())
        for alias, _ in self._attributes:
            _identifier(alias)

    def fetch(self, viewport: Viewport) -> list[GeometryFeature]:
        """Return each matching ID once, including shapes that touch an edge."""
        if type(viewport) is not Viewport:
            raise TypeError("expected a Viewport")
        if viewport.west <= viewport.east:
            left, right = [viewport.west], [viewport.east]
        else:
            left, right = [viewport.west, -180.0], [180.0, viewport.east]
        fields = "".join(f", source.{name} AS attr_{i}" for i, (_, name) in enumerate(self._attributes))
        projected = "".join(f", features.attr_{i}" for i in range(len(self._attributes)))
        geometry = "source.geometry"
        parameters = [left, right, viewport.south, viewport.north]
        materialization = "NOT MATERIALIZED"
        candidate_bounds, prescan = "", ""
        if self._crs.upper() != "EPSG:4326":
            geometry = "ST_Transform(source.geometry, ?, 'EPSG:4326', true)"
            parameters.append(self._crs)
            materialization = "MATERIALIZED"
            if self._crs.upper() == "EPSG:3857":
                # Mercator is monotonic within each of the split longitude boxes.
                candidate_bounds = """
                    , candidate_bounds AS MATERIALIZED (
                        SELECT ST_Transform(shape, 'EPSG:4326', 'EPSG:3857', true) AS extent
                        FROM viewport_shapes
                    )
                """
                prescan = """
                    AND EXISTS (SELECT 1 FROM candidate_bounds
                                WHERE ST_Intersects_Extent(source.geometry, extent))
                """
        rows = self._db.execute(f"""
            WITH boxes AS (
                SELECT unnest(?::DOUBLE[]) AS west, unnest(?::DOUBLE[]) AS east,
                       ?::DOUBLE AS south, ?::DOUBLE AS north
            ), viewport_shapes AS (
                SELECT CASE WHEN west = east AND south = north THEN ST_Point(west, south)
                       WHEN west = east OR south = north THEN ST_MakeLine(ST_Point(west, south), ST_Point(east, north))
                       ELSE ST_MakeEnvelope(west, south, east, north) END AS shape
                FROM boxes
            ) {candidate_bounds}, features AS {materialization} (
                SELECT source.feature_id, {geometry} AS geometry {fields} FROM {self._relation} AS source
                WHERE source.geometry IS NOT NULL AND NOT ST_IsEmpty(source.geometry) {prescan}
            )
            SELECT features.feature_id, ST_AsGeoJSON(features.geometry) {projected}
            FROM features WHERE EXISTS (
                SELECT 1 FROM viewport_shapes WHERE ST_Intersects_Extent(features.geometry, shape)
                   AND ST_Intersects(features.geometry, shape)
            )
            ORDER BY features.feature_id
        """, parameters).fetchall()
        names = [key for key, _ in self._attributes]
        return [GeometryFeature(key, loads(shape), dict(zip(names, attrs))) for key, shape, *attrs in rows]


@dataclass(frozen=True)
class LayerId:
    value: str

    def __post_init__(self):
        if type(self.value) is not str or not self.value:
            raise ValueError("layer ID must be a nonempty string")


@dataclass(frozen=True)
class RegisteredLayer:
    catalog: str
    relation: str
    version: str
    attributes: Mapping[str, AttributeColumn] | None = None
    time_column: str | None = None
    details: Mapping[str, str] | None = None


@dataclass(frozen=True)
class FeatureDetails:
    feature_id: int
    found: bool
    attributes: dict


class LayerRegistry:
    """Bind versioned point layers to catalog identities and host-supplied grants."""

    def __init__(self, connection: DuckDBPyConnection, layers: Mapping[LayerId, RegisteredLayer],
                 authorize: Callable[[object, LayerId, str], bool]):
        self._db = connection
        self._authorize = authorize
        self._layers = {}
        self._details = {}
        for name, record in layers.items():
            if type(name) is not LayerId or type(record) is not RegisteredLayer:
                raise TypeError("expected LayerId keys and RegisteredLayer values")
            if type(record.version) is not str or not record.version:
                raise ValueError("provide a layer version")
            layer = PointLayer(connection, record.relation, catalog=record.catalog,
                               attributes=record.attributes, time_column=record.time_column)
            self._layers[name] = (record.catalog, self._oid(record.catalog), record.version, layer)
            names = tuple(record.details or ())
            fields = []
            for index, (alias, column) in enumerate((record.details or {}).items()):
                _identifier(alias)
                fields.append(f", source.{_identifier(column)} AS attr_{index}")
            relation = f"{_identifier(record.catalog)}.main.{_identifier(record.relation)}"
            self._details[name] = (names, f'''
                WITH ids AS (
                    SELECT id, min(ord) AS position
                    FROM unnest(?::BIGINT[]) WITH ORDINALITY AS t(id, ord) GROUP BY id
                )
                SELECT ids.id, source.feature_id IS NOT NULL AS found {"".join(fields)}
                FROM ids LEFT JOIN {relation} AS source ON source.feature_id = ids.id
                ORDER BY ids.position
            ''')

    def _oid(self, catalog):
        row = self._db.execute("SELECT database_oid FROM duckdb_databases() WHERE database_name = ?",
                               [catalog]).fetchone()
        if row is None:
            raise LookupError("registered catalog is unavailable")
        return row[0]

    def _resolve(self, principal, layer_id):
        if type(layer_id) is not LayerId:
            raise TypeError("expected a LayerId")
        layer = self._layers.get(layer_id)
        if layer is None:
            raise PermissionError("layer is unavailable to this principal")
        self._validate_access(principal, layer_id, layer)
        return layer

    def _validate_access(self, principal, layer_id, layer):
        catalog, oid, version, _ = layer
        if not self._authorize(principal, layer_id, version):
            raise PermissionError("layer is unavailable to this principal")
        if self._oid(catalog) != oid:
            raise LookupError("registered catalog has changed")

    def fetch(self, principal: object, layer_id: LayerId, viewport: Viewport, *,
              zoom: int | None = None, where: FilterSpec | None = None,
              time: TimeRange | None = None) -> tuple[str, list[MapPoint] | list[GridCell]]:
        """Fetch one authorized layer version, rejecting a replaced catalog."""
        registered = self._resolve(principal, layer_id)
        _, _, version, layer = registered
        result = (layer.fetch(viewport, where=where, time=time) if zoom is None
                  else layer.fetch_at_zoom(viewport, zoom, where=where, time=time))
        self._validate_access(principal, layer_id, registered)
        return version, result

    def details(self, principal: object, layer_id: LayerId, *, version: str,
                feature_ids: list[int]) -> list[FeatureDetails]:
        """Fetch only the declared detail fields for an authorized immutable version."""
        registered = self._resolve(principal, layer_id)
        if type(version) is not str or version != registered[2]:
            raise LookupError("requested layer version has changed")
        if (type(feature_ids) is not list or len(feature_ids) > 256 or
                any(type(key) is not int or not -(1 << 63) <= key < (1 << 63) for key in feature_ids)):
            raise ValueError("provide a list of up to 256 signed 64-bit feature IDs")
        names, query = self._details[layer_id]
        rows = self._db.execute(query, [feature_ids]).fetchall()
        self._validate_access(principal, layer_id, registered)
        return [FeatureDetails(key, found, dict(zip(names, fields)) if found else {})
                for key, found, *fields in rows]


@dataclass(frozen=True)
class TileId:
    zoom: int
    x: int
    y: int

    def __post_init__(self):
        if type(self.zoom) is not int or not 0 <= self.zoom <= 22:
            raise ValueError("zoom must be an integer in [0, 22]")
        if any(type(value) is not int or not 0 <= value < 1 << self.zoom for value in (self.x, self.y)):
            raise ValueError("tile coordinates are outside the zoom level")


class VectorTileLayer:
    """Encode a host-registered EPSG:3857 relation as Mapbox Vector Tiles."""

    def __init__(self, connection: DuckDBPyConnection, relation: str, layer_name: str, *,
                 attributes: Mapping[str, str] | None = None, catalog: str | None = None):
        self._db = connection
        if type(layer_name) is not str or not layer_name or "\0" in layer_name:
            raise ValueError("layer_name must be a nonempty string without NUL")
        self._name = layer_name
        schema = "main" if catalog is None else f"{_identifier(catalog)}.main"
        self._relation = f"{schema}.{_identifier(relation)}"
        attrs = dict(attributes or {})
        aliases = {"feature_id", "geometry"}
        projected = []
        for alias, column in attrs.items():
            name = _identifier(alias)
            if alias.casefold() in aliases:
                raise ValueError("attribute names must be distinct and avoid reserved fields")
            aliases.add(alias.casefold())
            projected.append(f"source.{_identifier(column)} AS {name}")
        self._attributes = "".join(", " + item for item in projected)

    def fetch(self, tile: TileId, *, buffer: int = 256) -> bytes:
        """Return an empty tile as zero bytes. Buffer size is in tile coordinates."""
        if type(tile) is not TileId:
            raise TypeError("expected a TileId")
        _validate_buffer(buffer)
        result, = self._db.execute(f"""
            WITH envelope AS (
                SELECT ST_Extent(ST_TileEnvelope(?, ?, ?)) AS extent, ?::BIGINT AS padding
            ), coverage AS (
                SELECT extent, padding, (ST_XMax(extent) - ST_XMin(extent)) * padding / 4096.0 AS overscan
                FROM envelope
            ), clipped AS MATERIALIZED (
                SELECT source.feature_id,
                       ST_AsMVTGeom(source.geometry, tile.extent, 4096, ?::BIGINT, true) AS geometry
                       {self._attributes}
                FROM {self._relation} AS source CROSS JOIN coverage AS tile
                WHERE source.feature_id >= 0 AND ST_Intersects_Extent(source.geometry,
                    ST_MakeEnvelope(ST_XMin(tile.extent) - overscan, ST_YMin(tile.extent) - overscan,
                                    ST_XMax(tile.extent) + overscan, ST_YMax(tile.extent) + overscan))
            )
            SELECT CASE WHEN count(*) = 0 THEN ''::BLOB
                        ELSE ST_AsMVT(features, ?, 4096, 'geometry', 'feature_id') END
            FROM (SELECT * FROM clipped WHERE geometry IS NOT NULL AND NOT ST_IsEmpty(geometry)
                  ORDER BY feature_id) AS features
        """, [tile.zoom, tile.x, tile.y, buffer, buffer, self._name]).fetchone()
        return result


def _validate_buffer(buffer):
    if type(buffer) is not int or not 0 <= buffer <= 4096:
        raise ValueError("buffer must be an integer in [0, 4096]")


class TileOccupancy:
    """Use point occupancy for a committed Web Mercator snapshot to skip empty tiles."""

    def __init__(self, layer, version, levels):
        self._layer = layer
        self._version = version
        self._levels = levels

    @classmethod
    def build(cls, layer: VectorTileLayer, version: str, *, max_zoom: int = 10,
              max_cells: int = 500_000) -> "TileOccupancy":
        if type(layer) is not VectorTileLayer or type(version) is not str or not version:
            raise TypeError("expected a vector tile layer and a fixed version")
        if type(max_zoom) is not int or not 0 <= max_zoom <= 22:
            raise ValueError("max_zoom must be an integer in [0, 22]")
        if type(max_cells) is not int or max_cells < 1:
            raise ValueError("max_cells must be positive")
        with layer._db.cursor() as tx:
            tx.execute("BEGIN TRANSACTION")
            nonpoints, = tx.execute(f"""
                SELECT count(*) FROM {layer._relation}
                WHERE feature_id >= 0 AND NOT ST_IsEmpty(geometry)
                  AND CASE WHEN ST_GeometryType(geometry) = 'POINT'
                      THEN NOT isfinite(ST_X(geometry)) OR NOT isfinite(ST_Y(geometry))
                      ELSE true END
            """).fetchone()
            if nonpoints:
                raise ValueError("tile occupancy requires a layer of finite Web Mercator points")
            centers = tx.execute(f"""
                WITH levels AS (
                    SELECT zoom, 1::BIGINT << zoom AS side FROM range(? + 1) AS z(zoom)
                ), coordinates AS (
                    SELECT (ST_X(geometry) / 40075016.68557849 + 0.5) AS u,
                           (0.5 - ST_Y(geometry) / 40075016.68557849) AS v
                    FROM {layer._relation} WHERE feature_id >= 0 AND NOT ST_IsEmpty(geometry)
                )
                SELECT DISTINCT zoom, floor(greatest(0, least(side - 1, u * side)))::INT AS x,
                                      floor(greatest(0, least(side - 1, v * side)))::INT AS y
                FROM coordinates CROSS JOIN levels LIMIT ?
            """, [max_zoom, max_cells + 1]).fetchall()
            tx.execute("COMMIT")
        if len(centers) > max_cells:
            raise ValueError("occupied tile count exceeds the registered capacity")
        indexed = {level: set() for level in range(max_zoom + 1)}
        for zoom, x, y in centers:
            indexed[zoom].add((x, y))
        return cls(layer, version, indexed)

    def might_have_feature(self, version: str, tile: TileId, *, buffer: int = 256) -> bool:
        if type(tile) is not TileId:
            raise TypeError("expected a TileId")
        _validate_buffer(buffer)
        if self._version != version or tile.zoom not in self._levels:
            return True
        occupied = self._levels[tile.zoom]
        # A full-tile buffer can include a point on the second tile's near edge.
        offsets = range(-2, 3) if buffer == 4096 else range(-1, 2)
        return any((tile.x + dx, tile.y + dy) in occupied for dx in offsets for dy in offsets)

    def fetch(self, version: str, tile: TileId, *, buffer: int = 256) -> bytes:
        if not self.might_have_feature(version, tile, buffer=buffer):
            return b""
        return self._layer.fetch(tile, buffer=buffer)


@dataclass(frozen=True)
class TileScope:
    """Host-supplied cache identity for a tenant's authorized tile projection."""

    tenant: str
    layer: str
    visibility: str
    version: str | None
    projection: str

    def __post_init__(self):
        required = (self.tenant, self.layer, self.visibility, self.projection)
        if any(type(value) is not str or not value for value in required):
            raise ValueError("tenant, layer, visibility and projection must be nonempty strings")
        if self.version is not None and (type(self.version) is not str or not self.version):
            raise ValueError("version must be a nonempty string or None")


@dataclass(frozen=True)
class TileResponse:
    body: bytes | None
    etag: str | None
    not_modified: bool


class TileCache:
    """An LRU of immutable tiles with byte and entry limits."""

    def __init__(self, *, max_entries: int, max_bytes: int):
        if any(type(value) is not int or value <= 0 for value in (max_entries, max_bytes)):
            raise ValueError("cache limits must be positive integers")
        self._max_entries = max_entries
        self._max_bytes = max_bytes
        self._entries = OrderedDict()
        self._size = 0
        self._lock = Lock()

    def fetch(self, scope: TileScope, tile: TileId, generate: Callable[[], bytes], *,
              authorize: Callable[[TileScope], bool], if_none_match: str | None = None) -> TileResponse:
        """Resolve a tile under current grants and omit its body on an exact ETag match."""
        if type(scope) is not TileScope or type(tile) is not TileId:
            raise TypeError("expected a TileScope and TileId")
        if if_none_match is not None and type(if_none_match) is not str:
            raise TypeError("if_none_match must be an ETag string")
        if not authorize(scope):
            raise PermissionError("tile is unavailable to this principal")
        key = scope, tile
        cached = None
        if scope.version is not None:
            with self._lock:
                cached = self._entries.get(key)
                if cached is not None:
                    self._entries.move_to_end(key)

        if cached is None:
            body = generate()
            if type(body) is not bytes:
                raise TypeError("tile generator must return bytes")
            if not authorize(scope):
                raise PermissionError("tile is unavailable to this principal")
            if scope.version is None:
                return TileResponse(body, None, False)
            identity = dumps((scope.tenant, scope.layer, scope.visibility, scope.version, scope.projection,
                              tile.zoom, tile.x, tile.y), separators=(",", ":")).encode()
            etag = '"' + sha256(identity + b"\0" + body).hexdigest() + '"'
            if len(body) <= self._max_bytes:
                with self._lock:
                    prior = self._entries.pop(key, None)
                    if prior is not None:
                        self._size -= len(prior[0])
                    self._entries[key] = body, etag
                    self._size += len(body)
                    while self._size > self._max_bytes or len(self._entries) > self._max_entries:
                        _, (removed, _) = self._entries.popitem(last=False)
                        self._size -= len(removed)
        else:
            body, etag = cached
        if etag == if_none_match:
            return TileResponse(None, etag, True)
        return TileResponse(body, etag, False)


@dataclass
class _TileFlight:
    cancellation: Event
    subscribers: set[Future]


class TileSubscription:
    """One authorized subscriber to shared generation work."""

    def __init__(self, future, release, authorized):
        self._future = future
        self._release = release
        self._authorized = authorized

    def result(self, timeout=None) -> bytes:
        body = self._future.result(timeout)
        if not self._authorized():
            raise PermissionError("tile is unavailable to this principal")
        return body

    def cancel(self) -> bool:
        if not self._future.cancel():
            return False
        self._release()
        return True


class SharedTileWork:
    """Coalesce in-flight tile generation while tracking subscriber cancellation."""

    def __init__(self, *, workers: int):
        if type(workers) is not int or workers <= 0:
            raise ValueError("workers must be a positive integer")
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="duckgl-tile")
        self._active = {}
        self._closed = False
        self._lock = Lock()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def close(self):
        with self._lock:
            self._closed = True
            flights = tuple(self._active.values())
            self._active.clear()
        for flight in flights:
            flight.cancellation.set()
            for subscriber in flight.subscribers:
                subscriber.cancel()
        self._executor.shutdown(cancel_futures=True)

    def subscribe(self, scope: TileScope, tile: TileId, generate: Callable[[Event], bytes], *,
                  authorize: Callable[[TileScope], bool]) -> TileSubscription:
        if type(scope) is not TileScope or type(tile) is not TileId:
            raise TypeError("expected a TileScope and TileId")
        if not authorize(scope):
            raise PermissionError("tile is unavailable to this principal")
        key = (scope, tile) if scope.version is not None else object()
        subscriber = Future()
        worker = None
        with self._lock:
            if self._closed:
                raise RuntimeError("tile work pool is closed")
            flight = self._active.get(key)
            if flight is None:
                flight = _TileFlight(Event(), set())
                self._active[key] = flight
                worker = self._executor.submit(generate, flight.cancellation)
            flight.subscribers.add(subscriber)
        if worker is not None:
            worker.add_done_callback(lambda completed: self._finish(key, flight, completed))
        return TileSubscription(subscriber, lambda: self._remove(key, flight, subscriber),
                                lambda: authorize(scope))

    def _remove(self, key, flight, subscriber):
        with self._lock:
            if self._active.get(key) is not flight:
                return
            flight.subscribers.discard(subscriber)
            if not flight.subscribers:
                self._active.pop(key)
                flight.cancellation.set()

    def _finish(self, key, flight, worker):
        with self._lock:
            if self._active.get(key) is not flight:
                return
            self._active.pop(key)
            subscribers = tuple(flight.subscribers)
        try:
            body = worker.result()
            if type(body) is not bytes:
                raise TypeError("tile generator must return bytes")
        except BaseException as error:
            for subscriber in subscribers:
                if subscriber.set_running_or_notify_cancel():
                    subscriber.set_exception(error)
        else:
            for subscriber in subscribers:
                if subscriber.set_running_or_notify_cancel():
                    subscriber.set_result(body)
