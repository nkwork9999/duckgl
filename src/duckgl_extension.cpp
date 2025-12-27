#define DUCKDB_EXTENSION_MAIN

#include "duckgl_extension.hpp"
#include "duckdb.hpp"
#include "duckdb/common/exception.hpp"
#include "duckdb/function/scalar_function.hpp"
#include "duckdb/main/connection.hpp"
#include "duckdb/main/database.hpp"
#include "duckdb/catalog/catalog.hpp"
#include "duckdb/parser/parsed_data/create_scalar_function_info.hpp"

#include <thread>
#include <atomic>
#include <memory>

#include "httplib_wrapper.hpp"

namespace duckdb {

static std::string GetDuckGLHTML() {
    std::string html;
    
    html += R"HTML(
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>DuckGL - DuckDB Geospatial Visualization</title>
    <script src="https://unpkg.com/maplibre-gl@3.6.0/dist/maplibre-gl.js"></script>
    <link href="https://unpkg.com/maplibre-gl@3.6.0/dist/maplibre-gl.css" rel="stylesheet" />
    <script src="https://unpkg.com/deck.gl@^9.0.0/dist.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        #map { position: fixed; top: 0; left: 350px; right: 0; height: 100vh; }
        #sidebar { position: fixed; top: 0; left: 0; width: 350px; height: 100vh; background: #2c3e50; color: #ecf0f1; overflow-y: auto; display: flex; flex-direction: column; z-index: 1000; }
        #header { padding: 20px; background: #34495e; border-bottom: 2px solid #1abc9c; }
        #header h1 { color: #1abc9c; font-size: 24px; margin-bottom: 5px; }
        #header p { color: #95a5a6; font-size: 12px; }
        #content { padding: 20px; flex: 1; overflow-y: auto; }
        .section { margin-bottom: 25px; }
        .section h3 { color: #1abc9c; margin-bottom: 10px; font-size: 16px; }
        #sql-editor { width: 100%; height: 120px; font-family: monospace; background: #34495e; color: #ecf0f1; border: 1px solid #1abc9c; border-radius: 4px; padding: 10px; resize: vertical; }
        button { background: #1abc9c; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; font-size: 14px; margin-top: 10px; }
        button:hover { background: #16a085; }
        .table-item { background: #34495e; padding: 12px; margin: 8px 0; border-radius: 4px; cursor: pointer; border-left: 3px solid transparent; }
        .table-item:hover { background: #3d5a6b; border-left-color: #1abc9c; }
        .table-name { font-weight: bold; color: #ecf0f1; }
        .table-info { font-size: 12px; color: #95a5a6; margin-top: 4px; }
        #status { position: fixed; top: 10px; right: 10px; background: rgba(0,0,0,0.8); color: white; padding: 10px 15px; border-radius: 4px; font-size: 12px; z-index: 1001; }
        .loading { color: #f39c12; }
        .success { color: #2ecc71; }
        .error { color: #e74c3c; }
        #result-panel { position: fixed; bottom: 10px; left: 360px; right: 10px; max-height: 200px; background: rgba(0,0,0,0.9); color: white; padding: 15px; border-radius: 4px; font-size: 12px; overflow: auto; z-index: 1001; display: none; }
        #result-panel.show { display: block; }
        #result-panel table { width: 100%; border-collapse: collapse; }
        #result-panel th, #result-panel td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #444; }
        #result-panel th { background: #1abc9c; color: white; }
        .close-btn { position: absolute; top: 5px; right: 10px; background: none; border: none; color: #95a5a6; font-size: 18px; cursor: pointer; }
    </style>
</head>
<body>
    <div id="map"></div>
    <div id="sidebar">
        <div id="header">
            <h1>DuckGL</h1>
            <p>DuckDB Geospatial Visualization</p>
        </div>
        <div id="content">
            <div class="section">
                <h3>SQL Query</h3>
                <textarea id="sql-editor" placeholder="SELECT * FROM my_table">SELECT 1 as id</textarea>
                <button onclick="executeQuery()">Execute</button>
            </div>
            <div class="section">
                <h3>Tables</h3>
                <div id="tables-list">Loading...</div>
            </div>
        </div>
    </div>
    <div id="status">Initializing...</div>
    <div id="result-panel">
        <button class="close-btn" onclick="closeResults()">x</button>
        <div id="result-content"></div>
    </div>
)HTML";

    html += R"HTML(
    <script>
        let map = null;
        let deckOverlay = null;
        
        function initMap() {
            map = new maplibregl.Map({
                container: 'map',
                style: 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',
                center: [139.7, 35.7],
                zoom: 4
            });
            map.addControl(new maplibregl.NavigationControl(), 'top-right');
            map.on('load', function() {
                const {MapboxOverlay} = deck;
                deckOverlay = new MapboxOverlay({ layers: [] });
                map.addControl(deckOverlay);
                setStatus('Ready', 'success');
            });
        }
        
        function setStatus(msg, type) {
            const s = document.getElementById('status');
            s.textContent = msg;
            s.className = type || 'success';
        }
        
        function closeResults() {
            document.getElementById('result-panel').classList.remove('show');
        }
        
        function showResults(data) {
            const panel = document.getElementById('result-panel');
            const content = document.getElementById('result-content');
            if (!data || data.length === 0) {
                content.innerHTML = '<p>No results</p>';
                panel.classList.add('show');
                return;
            }
            if (data.error) {
                content.innerHTML = '<p style="color:#e74c3c;">Error: ' + data.error + '</p>';
                panel.classList.add('show');
                return;
            }
            const cols = Object.keys(data[0]);
            let h = '<table><thead><tr>';
            cols.forEach(c => h += '<th>' + c + '</th>');
            h += '</tr></thead><tbody>';
            data.slice(0, 50).forEach(row => {
                h += '<tr>';
                cols.forEach(c => h += '<td>' + (row[c] === null ? 'NULL' : row[c]) + '</td>');
                h += '</tr>';
            });
            h += '</tbody></table>';
            content.innerHTML = h;
            panel.classList.add('show');
        }
        
        async function loadTables() {
            try {
                const res = await fetch('/api/tables');
                const data = await res.json();
                const list = document.getElementById('tables-list');
                if (!data || data.length === 0) {
                    list.innerHTML = '<p>No tables</p>';
                    return;
                }
                list.innerHTML = data.map(t => 
                    '<div class="table-item" onclick="loadTableData(\'' + t.table_name + '\')">' +
                    '<div class="table-name">' + t.table_name + '</div></div>'
                ).join('');
            } catch (e) {
                document.getElementById('tables-list').innerHTML = '<p>Failed</p>';
            }
        }
)HTML";

    html += R"HTML(
        async function loadTableData(name) {
            setStatus('Loading ' + name + '...', 'loading');
            try {
                const res = await fetch('/api/geojson/' + name);
                const geojson = await res.json();
                if (geojson.error || !geojson.features || geojson.features.length === 0) {
                    document.getElementById('sql-editor').value = 'SELECT * FROM ' + name + ' LIMIT 100';
                    await executeQuery();
                    return;
                }
                const layer = new deck.GeoJsonLayer({
                    id: name + '-layer',
                    data: geojson,
                    filled: true,
                    stroked: true,
                    getFillColor: [26, 188, 156, 180],
                    getLineColor: [80, 80, 80, 255],
                    getLineWidth: 2,
                    lineWidthMinPixels: 1,
                    getPointRadius: 100,
                    pointRadiusMinPixels: 5,
                    pickable: true
                });
                if (deckOverlay) deckOverlay.setProps({ layers: [layer] });
                setStatus('Loaded ' + geojson.features.length + ' features', 'success');
            } catch (e) {
                setStatus('Error', 'error');
            }
        }
        
        async function executeQuery() {
            const sql = document.getElementById('sql-editor').value;
            setStatus('Executing...', 'loading');
            try {
                const res = await fetch('/api/query', {
                    method: 'POST',
                    headers: { 'Content-Type': 'text/plain' },
                    body: sql
                });
                const result = await res.json();
                if (result.error) {
                    setStatus('Error: ' + result.error, 'error');
                } else {
                    setStatus('Returned ' + result.length + ' rows', 'success');
                }
                showResults(result);
            } catch (e) {
                setStatus('Query failed', 'error');
            }
        }
        
        initMap();
        loadTables();
    </script>
</body>
</html>
)HTML";

    return html;
}

class DuckGLServer {
private:
    unique_ptr<httplib::Server> server;
    std::thread server_thread;
    std::atomic<bool> running{false};
    DatabaseInstance* db_instance;
    int port;
    
    static string ResultToJSON(unique_ptr<QueryResult> result) {
        if (!result || result->HasError()) {
            string err_msg = result ? result->GetError() : "Unknown error";
            string escaped;
            for (char c : err_msg) {
                if (c == '"') escaped += "\\\"";
                else if (c == '\\') escaped += "\\\\";
                else if (c == '\n') escaped += "\\n";
                else escaped += c;
            }
            return "{\"error\": \"" + escaped + "\"}";
        }
        
        string json = "[";
        bool first_row = true;
        
        while (true) {
            auto chunk = result->Fetch();
            if (!chunk || chunk->size() == 0) break;
            
            for (idx_t row = 0; row < chunk->size(); row++) {
                if (!first_row) json += ",";
                json += "{";
                
                bool first_col = true;
                for (idx_t col = 0; col < chunk->ColumnCount(); col++) {
                    if (!first_col) json += ",";
                    
                    auto &col_name = result->names[col];
                    json += "\"" + col_name + "\":";
                    
                    auto val = chunk->GetValue(col, row);
                    if (val.IsNull()) {
                        json += "null";
                    } else {
                        string str_val = val.ToString();
                        json += "\"";
                        for (char c : str_val) {
                            if (c == '"') json += "\\\"";
                            else if (c == '\\') json += "\\\\";
                            else if (c == '\n') json += "\\n";
                            else if (c == '\r') json += "\\r";
                            else if (c == '\t') json += "\\t";
                            else json += c;
                        }
                        json += "\"";
                    }
                    
                    first_col = false;
                }
                
                json += "}";
                first_row = false;
            }
        }
        
        json += "]";
        return json;
    }
    
    static string ResultToGeoJSONWithProperties(unique_ptr<QueryResult> result) {
        if (!result || result->HasError()) {
            string err_msg = result ? result->GetError() : "Query failed";
            return "{\"error\":\"" + err_msg + "\",\"type\":\"FeatureCollection\",\"features\":[]}";
        }
        
        auto& names = result->names;
        auto& types = result->types;
        
        string geojson = "{\"type\":\"FeatureCollection\",\"features\":[";
        bool first_feature = true;
        
        while (true) {
            auto chunk = result->Fetch();
            if (!chunk || chunk->size() == 0) break;
            
            for (idx_t row = 0; row < chunk->size(); row++) {
                auto geom_val = chunk->GetValue(0, row);
                if (geom_val.IsNull()) continue;
                
                if (!first_feature) geojson += ",";
                
                geojson += "{\"type\":\"Feature\",";
                geojson += "\"geometry\":" + geom_val.ToString() + ",";
                geojson += "\"properties\":{";
                
                bool first_prop = true;
                for (idx_t col = 1; col < chunk->ColumnCount(); col++) {
                    auto val = chunk->GetValue(col, row);
                    
                    if (!first_prop) geojson += ",";
                    geojson += "\"" + names[col] + "\":";
                    
                    if (val.IsNull()) {
                        geojson += "null";
                    } else if (types[col].IsNumeric()) {
                        geojson += val.ToString();
                    } else {
                        string str_val = val.ToString();
                        string escaped;
                        for (char c : str_val) {
                            if (c == '"') escaped += "\\\"";
                            else if (c == '\\') escaped += "\\\\";
                            else if (c == '\n') escaped += "\\n";
                            else if (c == '\r') escaped += "\\r";
                            else if (c == '\t') escaped += "\\t";
                            else escaped += c;
                        }
                        geojson += "\"" + escaped + "\"";
                    }
                    first_prop = false;
                }
                
                geojson += "}}";
                first_feature = false;
            }
        }
        
        geojson += "]}";
        return geojson;
    }
    
public:
    DuckGLServer(DatabaseInstance* db, int port_num) 
        : db_instance(db), port(port_num) {
    }
    
    ~DuckGLServer() {
        Stop();
    }
    
    void Start(const string& host) {
        server = make_uniq<httplib::Server>();
        
        server->Get("/", [](const httplib::Request&, httplib::Response& res) {
            res.set_content(GetDuckGLHTML(), "text/html; charset=utf-8");
        });
        
        server->Post("/api/query", [this](const httplib::Request& req, httplib::Response& res) {
            try {
                Connection conn(*db_instance);
                auto result = conn.Query(req.body);
                res.set_content(ResultToJSON(std::move(result)), "application/json");
            } catch (std::exception& e) {
                res.status = 500;
                res.set_content("{\"error\":\"" + string(e.what()) + "\"}", "application/json");
            }
        });
        
        server->Get("/api/tables", [this](const httplib::Request&, httplib::Response& res) {
            try {
                Connection conn(*db_instance);
                auto result = conn.Query(
                    "SELECT table_name, table_schema "
                    "FROM information_schema.tables "
                    "WHERE table_schema NOT IN ('information_schema', 'pg_catalog')"
                );
                res.set_content(ResultToJSON(std::move(result)), "application/json");
            } catch (std::exception& e) {
                res.status = 500;
                res.set_content("{\"error\":\"" + string(e.what()) + "\"}", "application/json");
            }
        });
        
        server->Get(R"(/api/geojson/(.+))", [this](const httplib::Request& req, httplib::Response& res) {
            try {
                string table_name = req.matches[1];
                Connection conn(*db_instance);
                
                auto load_result = conn.Query("LOAD spatial;");
                bool has_spatial = !load_result->HasError();
                
                if (!has_spatial) {
                    res.set_content("{\"error\":\"Spatial extension not available\",\"type\":\"FeatureCollection\",\"features\":[]}", "application/json");
                    return;
                }
                
                string check_sql = "SELECT column_name FROM information_schema.columns "
                                  "WHERE table_name = '" + table_name + "' "
                                  "AND (column_name = 'geometry' OR column_name = 'geom' OR column_name = 'the_geom')";
                auto check_result = conn.Query(check_sql);
                
                if (!check_result || check_result->HasError()) {
                    res.set_content("{\"error\":\"Could not check columns\",\"type\":\"FeatureCollection\",\"features\":[]}", "application/json");
                    return;
                }
                
                auto chunk = check_result->Fetch();
                if (!chunk || chunk->size() == 0) {
                    res.set_content("{\"error\":\"No geometry column found\",\"type\":\"FeatureCollection\",\"features\":[]}", "application/json");
                    return;
                }
                
                string geom_col = chunk->GetValue(0, 0).ToString();
                
                string sql = "SELECT ST_AsGeoJSON(" + geom_col + ") as geojson, * EXCLUDE(" + geom_col + ") FROM \"" + table_name + "\"";
                auto result = conn.Query(sql);
                
                if (result->HasError()) {
                    res.set_content("{\"error\":\"" + result->GetError() + "\",\"type\":\"FeatureCollection\",\"features\":[]}", "application/json");
                    return;
                }
                
                res.set_content(ResultToGeoJSONWithProperties(std::move(result)), "application/json");
            } catch (std::exception& e) {
                res.status = 500;
                res.set_content("{\"error\":\"" + string(e.what()) + "\",\"type\":\"FeatureCollection\",\"features\":[]}", "application/json");
            }
        });
        
        running = true;
        
        server_thread = std::thread([this, host]() {
            server->listen(host.c_str(), port);
        });
        
#ifdef __APPLE__
        system(("open http://localhost:" + std::to_string(port)).c_str());
#elif __linux__
        system(("xdg-open http://localhost:" + std::to_string(port) + " 2>/dev/null &").c_str());
#elif _WIN32
        system(("start http://localhost:" + std::to_string(port)).c_str());
#endif
    }
    
    void Stop() {
        if (running && server) {
            server->stop();
            if (server_thread.joinable()) {
                server_thread.join();
            }
            running = false;
        }
    }
    
    bool IsRunning() const { 
        return running; 
    }
};

static unique_ptr<DuckGLServer> global_server;

inline void DuckGLStartFunction(DataChunk &args, ExpressionState &state, Vector &result) {
    auto &context = state.GetContext();
    
    auto host = args.data[0].GetValue(0).ToString();
    auto port = args.data[1].GetValue(0).GetValue<int32_t>();
    
    if (global_server && global_server->IsRunning()) {
        global_server->Stop();
    }
    
    auto &db = DatabaseInstance::GetDatabase(context);
    global_server = make_uniq<DuckGLServer>(&db, port);
    global_server->Start(host);
    
    string message = "DuckGL server started on " + host + ":" + std::to_string(port);
    result.SetValue(0, Value(message));
}

inline void DuckGLStopFunction(DataChunk &args, ExpressionState &state, Vector &result) {
    if (global_server && global_server->IsRunning()) {
        global_server->Stop();
        result.SetValue(0, Value("DuckGL server stopped"));
    } else {
        result.SetValue(0, Value("No server running"));
    }
}

void DuckglExtension::Load(ExtensionLoader &loader) {
    loader.RegisterFunction(ScalarFunction(
        "duckgl_start",
        {LogicalType::VARCHAR, LogicalType::INTEGER},
        LogicalType::VARCHAR,
        DuckGLStartFunction
    ));
    
    loader.RegisterFunction(ScalarFunction(
        "duckgl_stop",
        {},
        LogicalType::VARCHAR,
        DuckGLStopFunction
    ));
}

std::string DuckglExtension::Name() {
    return "duckgl";
}

std::string DuckglExtension::Version() const {
#ifdef EXT_VERSION_DUCKGL
    return EXT_VERSION_DUCKGL;
#else
    return "0.1.0";
#endif
}

} // namespace duckdb

extern "C" {

DUCKDB_EXTENSION_API void duckgl_duckdb_cpp_init(duckdb::ExtensionLoader &loader) {
    duckdb::DuckglExtension ext;
    ext.Load(loader);
}

DUCKDB_EXTENSION_API void duckgl_init(duckdb::DatabaseInstance &db) {
    duckdb::Connection con(db);
    con.BeginTransaction();
    
    auto &catalog = duckdb::Catalog::GetSystemCatalog(*con.context);
    
    duckdb::CreateScalarFunctionInfo duckgl_start_func(duckdb::ScalarFunction(
        "duckgl_start",
        {duckdb::LogicalType::VARCHAR, duckdb::LogicalType::INTEGER},
        duckdb::LogicalType::VARCHAR,
        duckdb::DuckGLStartFunction
    ));
    catalog.CreateFunction(*con.context, duckgl_start_func);
    
    duckdb::CreateScalarFunctionInfo duckgl_stop_func(duckdb::ScalarFunction(
        "duckgl_stop",
        {},
        duckdb::LogicalType::VARCHAR,
        duckdb::DuckGLStopFunction
    ));
    catalog.CreateFunction(*con.context, duckgl_stop_func);
    
    con.Commit();
}

DUCKDB_EXTENSION_API const char *duckgl_version() {
    return duckdb::DuckDB::LibraryVersion();
}

}