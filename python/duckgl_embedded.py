"""Host-side publication of a single GeoJSON snapshot on loopback."""
from dataclasses import dataclass

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


class PointLayer:
    """Read WGS84 points from a trusted host-selected main-schema relation.

    The host provisions a tenant-scoped connection and a primary/unique
    feature_id. Longitudes in the source use the [-180, 180] convention.
    """

    def __init__(self, connection: DuckDBPyConnection, relation: str):
        if type(relation) is not str or not relation or "\0" in relation:
            raise ValueError("relation must be a nonempty name without NUL")
        self._db = connection
        self._relation = '"' + relation.replace('"', '""') + '"'

    def _viewport_filter(self, viewport: Viewport) -> tuple[str, list[float]]:
        if type(viewport) is not Viewport:
            raise TypeError("expected a Viewport")
        longitude_filter = ("(longitude >= ? OR longitude <= ?)" if viewport.west > viewport.east
                            else "longitude BETWEEN ? AND ?")
        predicate = f"""
            WHERE latitude BETWEEN ? AND ?
              AND longitude BETWEEN -180 AND 180 AND {longitude_filter}
        """
        return predicate, [viewport.south, viewport.north, viewport.west, viewport.east]

    def fetch(self, viewport: Viewport) -> list[MapPoint]:
        selection, values = self._viewport_filter(viewport)
        rows = self._db.execute(f"""
            SELECT feature_id, longitude::DOUBLE, latitude::DOUBLE, label
            FROM main.{self._relation} {selection} ORDER BY feature_id
        """, values).fetchall()
        return [MapPoint(*row) for row in rows]

    def fetch_at_zoom(self, viewport: Viewport, zoom: int) -> list[GridCell] | list[MapPoint]:
        """Use a world-aligned degree grid below zoom 14 and points at higher zoom."""
        if type(zoom) is not int or not 0 <= zoom <= 30:
            raise ValueError("zoom must be an integer between 0 and 30")
        if zoom >= 14:
            return self.fetch(viewport)

        selection, values = self._viewport_filter(viewport)
        vertical_cells = 1 << zoom
        rows = self._db.execute(f"""
            WITH dimensions AS (SELECT ?::INTEGER AS n), cells AS (
                SELECT least(2 * n - 1, floor((longitude::DOUBLE + 180) * n / 180))::INTEGER AS x,
                       least(n - 1, floor((latitude::DOUBLE + 90) * n / 180))::INTEGER AS y,
                       longitude::DOUBLE AS lon, latitude::DOUBLE AS lat
                FROM main.{self._relation} CROSS JOIN dimensions {selection}
            )
            SELECT x, y, count(*), avg(lon), avg(lat)
            FROM cells GROUP BY x, y ORDER BY x, y
        """, [vertical_cells, *values]).fetchall()
        return [GridCell(*row) for row in rows]
