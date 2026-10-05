# Regression tests

Run `bash scripts/test-unit.sh` from the repository root. The tests compile the
production C++ helpers without downloading DuckDB or browser libraries.
The Node.js tests check the embedded frontend syntax and exercise database
strings containing HTML and quotes. They use DOM stubs; browser integration
and DuckDB SQL tests remain separate checks.
