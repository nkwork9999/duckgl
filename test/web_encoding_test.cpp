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
  std::cout << JsonString(std::string("\0\1\x1f", 3)) << '\n';
}
