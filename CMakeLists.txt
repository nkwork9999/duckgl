cmake_minimum_required(VERSION 3.5...3.29)

set(TARGET_NAME duckgl)
set(EXTENSION_NAME ${TARGET_NAME}_extension)
set(LOADABLE_EXTENSION_NAME ${TARGET_NAME}_loadable_extension)

project(${TARGET_NAME})

set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# httplib のインクルードパスを追加
include_directories(src/include)
include_directories(third_party/httplib)

# OpenSSL機能を完全に無効化
add_compile_definitions(
    CPPHTTPLIB_OPENSSL_SUPPORT=0
    CPPHTTPLIB_ZLIB_SUPPORT=0
    CPPHTTPLIB_BROTLI_SUPPORT=0
)

set(EXTENSION_SOURCES src/duckgl_extension.cpp)

build_static_extension(${TARGET_NAME} ${EXTENSION_SOURCES})
build_loadable_extension(${TARGET_NAME} " " ${EXTENSION_SOURCES})

# pthreadをリンク
find_package(Threads REQUIRED)
target_link_libraries(${EXTENSION_NAME} Threads::Threads)
target_link_libraries(${LOADABLE_EXTENSION_NAME} Threads::Threads)

install(
    TARGETS ${EXTENSION_NAME}
    EXPORT "${DUCKDB_EXPORT_SET}"
    LIBRARY DESTINATION "${INSTALL_LIB_DIR}"
    ARCHIVE DESTINATION "${INSTALL_LIB_DIR}")