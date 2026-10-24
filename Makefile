PROJ_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
# Keep the runtime version separate from the pinned SDK source commit.
DUCKDB_VERSION ?= v2.0.0

# Configuration of extension
EXT_NAME=duckgl
EXT_CONFIG=${PROJ_DIR}extension_config.cmake

# Include the Makefile from extension-ci-tools
include extension-ci-tools/makefiles/duckdb_extension.Makefile