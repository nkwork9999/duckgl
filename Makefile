PROJ_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
DUCKDB_VERSION=v1.4.2

# Configuration of extension
EXT_NAME=miniplot
EXT_CONFIG=${PROJ_DIR}extension_config.cmake

# Include the Makefile from extension-ci-tools
include extension-ci-tools/makefiles/duckdb_extension.Makefile