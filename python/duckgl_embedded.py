"""Host-side publication of a single GeoJSON snapshot on loopback."""
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from math import isfinite

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


class LayerRegistry:
    """Bind versioned point layers to catalog identities and host-supplied grants."""

    def __init__(self, connection: DuckDBPyConnection, layers: Mapping[LayerId, RegisteredLayer],
                 authorize: Callable[[object, LayerId, str], bool]):
        self._db = connection
        self._authorize = authorize
        self._layers = {}
        for name, record in layers.items():
            if type(name) is not LayerId or type(record) is not RegisteredLayer:
                raise TypeError("expected LayerId keys and RegisteredLayer values")
            if type(record.version) is not str or not record.version:
                raise ValueError("provide a layer version")
            layer = PointLayer(connection, record.relation, catalog=record.catalog,
                               attributes=record.attributes, time_column=record.time_column)
            self._layers[name] = (record.catalog, self._oid(record.catalog), record.version, layer)

    def _oid(self, catalog):
        row = self._db.execute("SELECT database_oid FROM duckdb_databases() WHERE database_name = ?",
                               [catalog]).fetchone()
        if row is None:
            raise LookupError("registered catalog is unavailable")
        return row[0]

    def fetch(self, principal: object, layer_id: LayerId, viewport: Viewport, *,
              zoom: int | None = None, where: FilterSpec | None = None,
              time: TimeRange | None = None) -> tuple[str, list[MapPoint] | list[GridCell]]:
        """Fetch one authorized layer version, rejecting a replaced catalog."""
        if type(layer_id) is not LayerId:
            raise TypeError("expected a LayerId")
        layer_info = self._layers.get(layer_id)
        if layer_info is None or not self._authorize(principal, layer_id, layer_info[2]):
            raise PermissionError("layer is unavailable to this principal")
        catalog, oid, version, layer = layer_info
        if self._oid(catalog) != oid:
            raise LookupError("registered catalog has changed")
        result = (layer.fetch(viewport, where=where, time=time) if zoom is None
                  else layer.fetch_at_zoom(viewport, zoom, where=where, time=time))
        if self._oid(catalog) != oid:
            raise LookupError("registered catalog has changed")
        if not self._authorize(principal, layer_id, version):
            raise PermissionError("layer is unavailable to this principal")
        return version, result
