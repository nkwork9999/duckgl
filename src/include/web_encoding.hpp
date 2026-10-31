#pragma once
#include <string>
namespace web_encoding {
inline std::string JsonString(const std::string &value) {
	const char *hex = "0123456789abcdef";
	std::string out = "\"";
	for (unsigned char c : value) {
		switch (c) {
		case '"':
			out += "\\\"";
			break;
		case '\\':
			out += "\\\\";
			break;
		case '\b':
			out += "\\b";
			break;
		case '\f':
			out += "\\f";
			break;
		case '\n':
			out += "\\n";
			break;
		case '\r':
			out += "\\r";
			break;
		case '\t':
			out += "\\t";
			break;
		default:
			if (c < 0x20) {
				out += "\\u00";
				out += hex[c >> 4];
				out += hex[c & 15];
			} else {
				out += static_cast<char>(c);
			}
		}
	}
	return out + "\"";
}
inline std::string SqlIdentifier(const std::string &value) {
	std::string out = "\"";
	for (char c : value) {
		if (c == '"')
			out += '"';
		out += c;
	}
	return out + "\"";
}
inline std::string SqlLiteral(const std::string &value) {
	std::string out = "'";
	for (char c : value) {
		if (c == '\'')
			out += '\'';
		out += c;
	}
	return out + "'";
}
inline std::string JsonNumber(const std::string &value) {
	if (value == "NULL" || value == "nan" || value == "NaN" || value == "inf" || value == "-inf" ||
	    value == "Infinity" || value == "-Infinity")
		return "null";
	// JSON.parse uses IEEE-754 doubles. Keep large integer tokens as text so
	// identifiers retain all digits in the browser and exported reports.
	if (!value.empty()) {
		const auto start = value[0] == '-' ? 1U : 0U;
		const auto digits = value.size() - start;
		if (digits && value.find_first_not_of("0123456789", start) == std::string::npos &&
		    (digits > 16 || (digits == 16 && value.compare(start, digits, "9007199254740991") > 0))) {
			return JsonString(value);
		}
	}
	return value;
}
} // namespace web_encoding
