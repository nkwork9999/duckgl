// Compile against the same DuckDB headers and library version.
#include "../src/duckgl_extension.cpp"
#include <cassert>
#include <iostream>
int main() {
 duckdb::DuckDB database(nullptr);
 duckdb::Connection connection(database);
 auto setup = connection.Query("CREATE SCHEMA analytics; CREATE TABLE analytics.orders AS SELECT 'quoted \"value\"' AS name, 0 AS amount; INSERT INTO analytics.orders VALUES ('second', NULL)");
 assert(!setup->HasError());
 duckdb::DuckGLServer server(database.instance.get(), 19881);
 server.Start("127.0.0.1");
 httplib::Client client("127.0.0.1", 19881);
 auto page = client.Get("/"); assert(page && page->status == 200 && page->body.find("Filter tables") != std::string::npos);
 auto tables = client.Get("/api/tables"); assert(tables && tables->body.find("analytics") != std::string::npos);
 auto rows = client.Post("/api/query", "SELECT * FROM analytics.orders", "text/plain");
 assert(rows && rows->body.find("\\\"value\\\"") != std::string::npos && rows->body.find("\"amount\":0") != std::string::npos && rows->body.find("null") != std::string::npos);
 auto error = client.Post("/api/query", "SELECT * FROM nonexistent", "text/plain"); assert(error && error->body.find("\"error\"") != std::string::npos);
 server.Stop(); server.Start("127.0.0.1"); assert(client.Get("/")); server.Stop();
 std::cout << "Native DuckDB HTTP integration passed\n";
}
