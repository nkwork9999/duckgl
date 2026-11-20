"""Host-side publication of a single GeoJSON snapshot on loopback."""
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
