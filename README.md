# DuckGL

Interactive geospatial visualization extension for DuckDB - visualize spatial data on an interactive map directly from SQL.

## Overview

DuckGL launches a local web server with an interactive map UI powered by [MapLibre GL](https://maplibre.org/) and [Deck.gl](https://deck.gl/). Browse tables, execute SQL queries, and render GeoJSON layers on a map, all from the DuckDB CLI.

- Interactive map with zoom/pan controls (CartoDB Positron basemap)
- GeoJSON layer rendering for spatial data (requires DuckDB `spatial` extension)
- Built-in SQL editor in the browser UI
- Table browser sidebar
- Query result table display

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

DuckGL automatically detects geometry columns (`geometry`, `geom`, or `the_geom`) in your tables and renders them as GeoJSON layers on the map using `ST_AsGeoJSON()`.

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
