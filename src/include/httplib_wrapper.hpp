#ifndef HTTPLIB_WRAPPER_H
#define HTTPLIB_WRAPPER_H

// OpenSSL/zlib/brotliを無効化
// httplib.hはマクロが「定義されているか」で判定するため、
// 事前にundefして定義されていない状態にする
#ifdef CPPHTTPLIB_OPENSSL_SUPPORT
#undef CPPHTTPLIB_OPENSSL_SUPPORT
#endif

#ifdef CPPHTTPLIB_ZLIB_SUPPORT
#undef CPPHTTPLIB_ZLIB_SUPPORT
#endif

#ifdef CPPHTTPLIB_BROTLI_SUPPORT
#undef CPPHTTPLIB_BROTLI_SUPPORT
#endif

// 同じディレクトリのhttplib.hをインクルード
#include "httplib.h"

#endif // HTTPLIB_WRAPPER_H