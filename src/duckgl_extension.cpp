#define DUCKDB_EXTENSION_MAIN

#include "duckgl_extension.hpp"
#include "duckdb.hpp"
#include "duckdb/catalog/catalog.hpp"
#include "duckdb/common/exception.hpp"
#include "duckdb/function/scalar_function.hpp"
#include "duckdb/main/connection.hpp"
#include "duckdb/main/database.hpp"
#include "duckdb/parser/parsed_data/create_scalar_function_info.hpp"
#include "web_encoding.hpp"
#include "simple_ui.hpp"

#include <atomic>
#include <memory>
#include <thread>

#include "httplib_wrapper.hpp"

namespace duckdb {

static std::string GetDuckGLHTML() { return DUCKGL_SIMPLE_HTML; }

class DuckGLServer {
private:
  unique_ptr<httplib::Server> server;
  std::thread server_thread;
  std::atomic<bool> running{false};
  DatabaseInstance *db_instance;
  int port;

  static std::string ResultToJSON(duckdb::unique_ptr<QueryResult> result) {
    using namespace web_encoding;
    if (!result || result->HasError()) {
      return "{\"error\":" +
             JsonString(result ? result->GetError() : "Unknown error") + "}";
    }
    std::string json = "[";
    bool first_row = true;
    while (auto chunk = result->Fetch()) {
      for (idx_t row = 0; row < chunk->size(); row++) {
        if (!first_row)
          json += ",";
        first_row = false;
        json += "{";
        for (idx_t col = 0; col < chunk->ColumnCount(); col++) {
          if (col)
            json += ",";
          json += JsonString(result->names[col]) + ":";
          auto value = chunk->GetValue(col, row);
          if (value.IsNull())
            json += "null";
          else if (result->types[col].id() == LogicalTypeId::BOOLEAN)
            json += value.GetValue<bool>() ? "true" : "false";
          else if (result->types[col].IsNumeric())
            json += JsonNumber(value.ToString());
          else
            json += JsonString(value.ToString());
        }
        json += "}";
      }
    }
    return json + "]";
  }

  static string ResultToGeoJSONWithProperties(unique_ptr<QueryResult> result) {
    if (!result || result->HasError()) {
      string err_msg = result ? result->GetError() : "Query failed";
      return "{\"error\":" + web_encoding::JsonString(err_msg) +
             ",\"type\":\"FeatureCollection\",\"features\":[]}";
    }

    auto &names = result->names;
    auto &types = result->types;

    string geojson = "{\"type\":\"FeatureCollection\",\"features\":[";
    bool first_feature = true;

    while (true) {
      auto chunk = result->Fetch();
      if (!chunk || chunk->size() == 0)
        break;

      for (idx_t row = 0; row < chunk->size(); row++) {
        auto geom_val = chunk->GetValue(0, row);
        if (geom_val.IsNull())
          continue;

        if (!first_feature)
          geojson += ",";

        geojson += "{\"type\":\"Feature\",";
        geojson += "\"geometry\":" + geom_val.ToString() + ",";
        geojson += "\"properties\":{";

        bool first_prop = true;
        for (idx_t col = 1; col < chunk->ColumnCount(); col++) {
          auto val = chunk->GetValue(col, row);

          if (!first_prop)
            geojson += ",";
          geojson += web_encoding::JsonString(names[col]) + ":";

          if (val.IsNull()) {
            geojson += "null";
          } else if (types[col].IsNumeric()) {
            geojson += web_encoding::JsonNumber(val.ToString());
          } else {
            geojson += web_encoding::JsonString(val.ToString());
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
  DuckGLServer(DatabaseInstance *db, int port_num)
      : db_instance(db), port(port_num) {}

  ~DuckGLServer() { Stop(); }

  void Start(const string &host) {
    server = make_uniq<httplib::Server>();

    server->Get("/", [](const httplib::Request &, httplib::Response &res) {
      res.set_content(GetDuckGLHTML(), "text/html; charset=utf-8");
    });

    server->Post("/api/query", [this](const httplib::Request &req,
                                      httplib::Response &res) {
      try {
        Connection conn(*db_instance);
        auto result = conn.Query(req.body);
        res.set_content(ResultToJSON(std::move(result)), "application/json");
      } catch (std::exception &e) {
        res.status = 500;
        res.set_content("{\"error\":" + web_encoding::JsonString(e.what()) +
                            "}",
                        "application/json");
      }
    });

    server->Get("/api/tables", [this](const httplib::Request &,
                                      httplib::Response &res) {
      try {
        Connection conn(*db_instance);
        auto result = conn.Query(
            "SELECT table_name, table_schema "
            "FROM information_schema.tables "
            "WHERE table_schema NOT IN ('information_schema', 'pg_catalog')");
        res.set_content(ResultToJSON(std::move(result)), "application/json");
      } catch (std::exception &e) {
        res.status = 500;
        res.set_content("{\"error\":" + web_encoding::JsonString(e.what()) +
                            "}",
                        "application/json");
      }
    });

    server->Get(R"(/api/geojson/(.+))", [this](const httplib::Request &req,
                                               httplib::Response &res) {
      try {
        string table_name = req.matches[1];
        string schema = req.has_param("schema") ? req.get_param_value("schema") : "main";
        Connection conn(*db_instance);

        auto load_result = conn.Query("LOAD spatial;");
        bool has_spatial = !load_result->HasError();

        if (!has_spatial) {
          res.set_content(
              "{\"error\":\"Spatial extension not "
              "available\",\"type\":\"FeatureCollection\",\"features\":[]}",
              "application/json");
          return;
        }

        string check_sql = "SELECT column_name FROM information_schema.columns "
                           "WHERE table_name = " +
                           web_encoding::SqlLiteral(table_name) +
                           " AND table_schema = " + web_encoding::SqlLiteral(schema) + " "
                           "AND (column_name = 'geometry' OR column_name = "
                           "'geom' OR column_name = 'the_geom')";
        auto check_result = conn.Query(check_sql);

        if (!check_result || check_result->HasError()) {
          res.set_content(
              "{\"error\":\"Could not check "
              "columns\",\"type\":\"FeatureCollection\",\"features\":[]}",
              "application/json");
          return;
        }

        auto chunk = check_result->Fetch();
        if (!chunk || chunk->size() == 0) {
          res.set_content(
              "{\"error\":\"No geometry column "
              "found\",\"type\":\"FeatureCollection\",\"features\":[]}",
              "application/json");
          return;
        }

        string geom_col = chunk->GetValue(0, 0).ToString();

        string sql =
            "SELECT ST_AsGeoJSON(" + web_encoding::SqlIdentifier(geom_col) +
            ") as geojson, * EXCLUDE(" + web_encoding::SqlIdentifier(geom_col) +
            ") FROM " + web_encoding::SqlIdentifier(schema) + "." + web_encoding::SqlIdentifier(table_name);
        auto result = conn.Query(sql);

        if (result->HasError()) {
          res.set_content(
              "{\"error\":" + web_encoding::JsonString(result->GetError()) +
                  ",\"type\":\"FeatureCollection\",\"features\":[]}",
              "application/json");
          return;
        }

        res.set_content(ResultToGeoJSONWithProperties(std::move(result)),
                        "application/json");
      } catch (std::exception &e) {
        res.status = 500;
        res.set_content("{\"error\":" + web_encoding::JsonString(e.what()) +
                            ",\"type\":\"FeatureCollection\",\"features\":[]}",
                        "application/json");
      }
    });

    if (!server->bind_to_port(host, port)) {
      throw IOException("Unable to bind HTTP server to %s:%d", host, port);
    }
    running = true;

    server_thread = std::thread([this, host]() {
      server->listen_after_bind();
      running = false;
    });
    server->wait_until_ready();

#ifdef __APPLE__
    system(("open http://localhost:" + std::to_string(port)).c_str());
#elif __linux__
    system(
        ("xdg-open http://localhost:" + std::to_string(port) + " 2>/dev/null &")
            .c_str());
#elif _WIN32
    system(("start http://localhost:" + std::to_string(port)).c_str());
#endif
  }

  void Stop() {
    if (server) {
      server->stop();
      if (server_thread.joinable()) {
        server_thread.join();
      }
      running = false;
    }
  }

  bool IsRunning() const { return running; }
};

static unique_ptr<DuckGLServer> global_server;

inline void DuckGLStartFunction(DataChunk &args, ExpressionState &state,
                                Vector &result) {
  auto &context = state.GetContext();

  auto host = args.data[0].GetValue(0).ToString();
  auto port = args.data[1].GetValue(0).GetValue<int32_t>();
  if (host.empty() || host.find('\0') != std::string::npos) {
    throw InvalidInputException(
        "HTTP host must be non-empty and contain no NUL bytes");
  }
  if (port < 1 || port > 65535) {
    throw InvalidInputException("HTTP port must be between 1 and 65535");
  }

  if (global_server && global_server->IsRunning()) {
    global_server->Stop();
  }

  auto &db = DatabaseInstance::GetDatabase(context);
  global_server = make_uniq<DuckGLServer>(&db, port);
  global_server->Start(host);

  string message =
      "DuckGL server started on " + host + ":" + std::to_string(port);
  result.SetValue(0, Value(message));
}

inline void DuckGLStopFunction(DataChunk &args, ExpressionState &state,
                               Vector &result) {
  if (global_server && global_server->IsRunning()) {
    global_server->Stop();
    result.SetValue(0, Value("DuckGL server stopped"));
  } else {
    result.SetValue(0, Value("No server running"));
  }
}

void DuckglExtension::Load(ExtensionLoader &loader) {
  loader.RegisterFunction(ScalarFunction(
      "duckgl_start", {LogicalType::VARCHAR, LogicalType::INTEGER},
      LogicalType::VARCHAR, DuckGLStartFunction));

  loader.RegisterFunction(ScalarFunction(
      "duckgl_stop", {}, LogicalType::VARCHAR, DuckGLStopFunction));
}

std::string DuckglExtension::Name() { return "duckgl"; }

std::string DuckglExtension::Version() const {
#ifdef EXT_VERSION_DUCKGL
  return EXT_VERSION_DUCKGL;
#else
  return "0.1.0";
#endif
}

} // namespace duckdb

extern "C" {

DUCKDB_EXTENSION_API void
duckgl_duckdb_cpp_init(duckdb::ExtensionLoader &loader) {
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
      duckdb::LogicalType::VARCHAR, duckdb::DuckGLStartFunction));
  catalog.CreateFunction(*con.context, duckgl_start_func);

  duckdb::CreateScalarFunctionInfo duckgl_stop_func(
      duckdb::ScalarFunction("duckgl_stop", {}, duckdb::LogicalType::VARCHAR,
                             duckdb::DuckGLStopFunction));
  catalog.CreateFunction(*con.context, duckgl_stop_func);

  con.Commit();
}

DUCKDB_EXTENSION_API const char *duckgl_version() {
  return duckdb::DuckDB::LibraryVersion();
}
}