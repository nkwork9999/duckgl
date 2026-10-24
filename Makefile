PROJ_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
DUCKDB_VERSION=d54cbbe3df17e8e5ce68312f483b4155836112aa

# Configuration of extension
EXT_NAME=duckgl
EXT_CONFIG=${PROJ_DIR}extension_config.cmake

# Include the Makefile from extension-ci-tools
include extension-ci-tools/makefiles/duckdb_extension.Makefile