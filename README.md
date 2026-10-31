# DuckGL

Interactive geospatial visualization extension for DuckDB - visualize spatial data on an interactive map directly from SQL.

## Overview

DuckGL launches a local web server with an interactive map UI powered by [MapLibre GL](https://maplibre.org/) and [Deck.gl](https://deck.gl/). Browse tables, execute SQL queries, and render GeoJSON layers on a map, all from the DuckDB CLI.

- Interactive map with zoom/pan controls (CartoDB Positron basemap)
- GeoJSON layer rendering for spatial data (requires DuckDB `spatial` extension)
- Built-in SQL editor in the browser UI
- Table browser sidebar
- Query result table display
- Database-aware table selection across attached databases
- Exact large-integer IDs in query results and saved reports

## Installation

```sql
INSTALL duckgl FROM community;
LOAD duckgl;
```

## Quick Start

```sql
-- Load the extension
LOAD duckgl;

-- Start the web server (opens browser automatically)
SELECT duckgl_start('127.0.0.1', 8080);

-- Use the browser UI to:
--   1. Browse tables in the sidebar
--   2. Click a table to visualize its geometry on the map
--   3. Write and execute SQL queries

-- Stop the server when done
SELECT duckgl_stop();
```

## Functions

### `duckgl_start(host VARCHAR, port INTEGER) -> VARCHAR`

Starts the DuckGL web server and opens the browser.

| Parameter | Type | Description |
|-----------|------|-------------|
| `host` | VARCHAR | Host address to bind (e.g. `'127.0.0.1'`, `'localhost'`) |
| `port` | INTEGER | Port number (e.g. `8080`) |

Returns a status message like `DuckGL server started on 127.0.0.1:8080`.

### `duckgl_stop() -> VARCHAR`

Stops the running DuckGL web server.

Returns `DuckGL server stopped` or `No server running`.

## Geospatial Visualization

DuckGL detects columns by their `GEOMETRY` type, including columns with custom
names such as `shape` or `位置`. If a table has multiple geometry columns, it
prefers `geometry`, `geom`, then `the_geom` (case insensitive), followed by the
first geometry column in table order. A text column named `geometry` is ignored.
Geometry is rendered using `ST_AsGeoJSON()`; map coordinates must be
longitude/latitude in WGS84. Reproject other coordinate systems in SQL first.

The sidebar displays and searches `database.schema` for each table. Queries,
map requests, and saved report labels use the selected database, so identically
named tables in attached databases remain distinct.

```sql
-- Example: Load spatial data and visualize
INSTALL spatial;
LOAD spatial;
LOAD duckgl;

CREATE TABLE cities AS
SELECT 'Tokyo' as name, ST_Point(139.6917, 35.6895) as geometry
UNION ALL SELECT 'Osaka', ST_Point(135.5023, 34.6937)
UNION ALL SELECT 'Nagoya', ST_Point(136.9066, 35.1815);

SELECT duckgl_start('127.0.0.1', 8080);
-- Click "cities" in the sidebar to see the points on the map
```

## API Endpoints

The web server exposes these endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main HTML UI with map and sidebar |
| `/api/query` | POST | Execute a SQL query (body = SQL string) |
| `/api/tables` | GET | List available tables |
| `/api/geojson/{table}` | GET | Get GeoJSON FeatureCollection for a table |

`/api/tables` returns `table_name`, `table_schema`, and `table_catalog` for each
table. `/api/geojson/{table}` accepts optional `schema` (default `main`) and
`catalog` (default the connection's current database) query parameters. URL-encode
the table path segment and parameter values when names contain special characters.

SQL results and GeoJSON properties preserve Boolean and NULL values. Integer
tokens outside JavaScript's safe range (`-9007199254740991` through
`9007199254740991`) are returned as JSON strings to prevent rounding, for example
`"9007199254740993"`. Other finite numeric values use JSON numbers; non-finite
values use JSON null. Floating-point and decimal values still follow the browser's
normal numeric precision.

## Requirements

- **Internet connection**: Required for map tiles and frontend libraries (MapLibre GL, Deck.gl via CDN)
- **Browser**: Any modern web browser
- **DuckDB spatial extension**: Required for geometry visualization (`INSTALL spatial; LOAD spatial;`)

## Build

```bash
make release
```

## License

MIT License - see [LICENSE](LICENSE) file

## Links

- [DuckDB](https://duckdb.org/)
- [MapLibre GL](https://maplibre.org/)
- [Deck.gl](https://deck.gl/)
- [DuckDB Community Extensions](https://github.com/duckdb/community-extensions)

### Save HTML and PDF reports

Run a query or load a spatial table, then choose **Export HTML** or **Export PDF**.
HTML downloads a standalone report that opens offline. It includes the last
successful SQL query, every returned result row (not just the on-screen 200-row
preview), and an SVG geometry overview when a map table is loaded. The overview
uses longitude/latitude with north up and excludes base-map tiles; it is not a
capture of the current map camera. Saved HTML contains no scripts or SQL requests.

PDF opens the same report in the browser print dialog. Choose **Save as PDF**.
Text remains selectable, including Japanese; table headers repeat across pages.
The snapshot keeps the SQL that produced the results even if the editor is
changed afterward. Reports can include data from the loaded map table and a
separate last successful query, each labeled separately.
