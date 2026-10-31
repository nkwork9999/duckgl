#include "simple_ui.hpp"
#include "web_encoding.hpp"
#include <cassert>
#include <iostream>
int main() {
	using namespace web_encoding;
	assert(std::string(DUCKGL_SIMPLE_HTML).find("<title>DuckGL</title>") != std::string::npos);
	assert(JsonString("a\"b\\c\n\r\t\b\f") == "\"a\\\"b\\\\c\\n\\r\\t\\b\\f\"");
	assert(JsonString(std::string("\0\1\x1f", 3)) == "\"\\u0000\\u0001\\u001f\"");
	assert(JsonString("日本語") == "\"日本語\"");
	assert(SqlIdentifier("odd\"name") == "\"odd\"\"name\"");
	assert(SqlLiteral("O'Brien") == "'O''Brien'");
	assert(JsonNumber("NaN") == "null");
	assert(JsonNumber("inf") == "null");
	assert(JsonNumber("NULL") == "null");
	assert(JsonNumber("-3.5") == "-3.5");
	// Preserve IDs beyond JavaScript's safe integer range through JSON.parse.
	assert(JsonNumber("9007199254740991") == "9007199254740991");
	assert(JsonNumber("-9007199254740991") == "-9007199254740991");
	assert(JsonNumber("9007199254740992") == "\"9007199254740992\"");
	assert(JsonNumber("-9007199254740993") == "\"-9007199254740993\"");
	assert(JsonNumber("18446744073709551615") == "\"18446744073709551615\"");
	assert(JsonNumber("170141183460469231731687303715884105727") == "\"170141183460469231731687303715884105727\"");
	assert(JsonNumber("0") == "0");
	assert(JsonNumber("1.25") == "1.25");
	assert(JsonNumber("1e+20") == "1e+20");
	std::cout << JsonString(std::string("\0\1\x1f", 3)) << '\n';
}
