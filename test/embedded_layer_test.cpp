// Exercise the registered extension entry point and its HTTP surface in one process.
#include "../src/duckgl_extension.cpp"
#include <cassert>
#include <iostream>

int main() {
	duckdb::DuckDB db(nullptr);
	duckgl_init(*db.instance);
	duckdb::Connection conn(db);
	auto setup = conn.Query("LOAD spatial; CREATE TABLE private_points AS SELECT ST_Point(1, 2) AS geometry, "
	                        "'station' AS label, 'hidden-value' AS private_column; "
	                        "CREATE VIEW \"approved layer\" AS SELECT geometry, label FROM private_points");
	if (setup->HasError()) {
		std::cerr << setup->GetError() << std::endl;
		return 1;
	}
	auto started = conn.Query("SELECT duckgl_start_layer(0, 'approved layer')");
	if (started->HasError()) {
		std::cerr << started->GetError() << std::endl;
		return 1;
	}
	auto port = started->Fetch()->GetValue(0, 0).GetValue<int32_t>();
	assert(port > 0);
	httplib::Client client("127.0.0.1", port);
	auto layer = client.Get("/api/layer");
	assert(layer && layer->status == 200);
	assert(layer->body.find("FeatureCollection") != std::string::npos);
	assert(layer->body.find("station") != std::string::npos);
	assert(layer->body.find("hidden-value") == std::string::npos);
	auto unknown = client.Get("/api/layer?table=private_points");
	assert(unknown && unknown->status == 400);
	for (auto path : {"/api/query", "/api/query-map"}) {
		auto result = client.Post(path, "", "text/plain");
		assert(result && result->status == 404);
	}
	for (auto path : {"/", "/api/tables", "/api/columns/private_points", "/api/geojson/private_points"}) {
		auto result = client.Get(path);
		assert(result && result->status == 404);
	}
	duckdb::Connection other(db);
	assert(!other.Query("SELECT duckgl_stop_layer()")->Fetch()->GetValue(0, 0).GetValue<bool>());
	assert(!conn.Query("DELETE FROM private_points")->HasError());
	assert(client.Get("/api/layer")->body == layer->body);
	assert(conn.Query("SELECT duckgl_stop_layer()")->Fetch()->GetValue(0, 0).GetValue<bool>());
	assert(!client.Get("/api/layer"));
	std::cout << "Embedded layer registration, projected data, route isolation and shutdown passed\n";
}
