/* 由 gen_libc_shim.py 生成，不要手改 */
#pragma once

typedef __INT8_TYPE__ int8_t;
typedef __UINT8_TYPE__ uint8_t;
typedef __INT16_TYPE__ int16_t;
typedef __UINT16_TYPE__ uint16_t;
typedef __INT32_TYPE__ int32_t;
typedef __UINT32_TYPE__ uint32_t;
typedef __INT64_TYPE__ int64_t;
typedef __UINT64_TYPE__ uint64_t;
typedef __INT_LEAST8_TYPE__ int_least8_t;
typedef __UINT_LEAST8_TYPE__ uint_least8_t;
typedef __INT_LEAST16_TYPE__ int_least16_t;
typedef __UINT_LEAST16_TYPE__ uint_least16_t;
typedef __INT_LEAST32_TYPE__ int_least32_t;
typedef __UINT_LEAST32_TYPE__ uint_least32_t;
typedef __INT_LEAST64_TYPE__ int_least64_t;
typedef __UINT_LEAST64_TYPE__ uint_least64_t;
typedef __INT_FAST8_TYPE__ int_fast8_t;
typedef __UINT_FAST8_TYPE__ uint_fast8_t;
typedef __INT_FAST16_TYPE__ int_fast16_t;
typedef __UINT_FAST16_TYPE__ uint_fast16_t;
typedef __INT_FAST32_TYPE__ int_fast32_t;
typedef __UINT_FAST32_TYPE__ uint_fast32_t;
typedef __INT_FAST64_TYPE__ int_fast64_t;
typedef __UINT_FAST64_TYPE__ uint_fast64_t;
typedef __INTPTR_TYPE__ intptr_t;
typedef __UINTPTR_TYPE__ uintptr_t;
typedef __INTMAX_TYPE__ intmax_t;
typedef __UINTMAX_TYPE__ uintmax_t;

#define INT8_MAX __INT8_MAX__
#define INT8_MIN (-__INT8_MAX__ - 1)
#define INT16_MAX __INT16_MAX__
#define INT16_MIN (-__INT16_MAX__ - 1)
#define INT32_MAX __INT32_MAX__
#define INT32_MIN (-__INT32_MAX__ - 1)
#define INT64_MAX __INT64_MAX__
#define INT64_MIN (-__INT64_MAX__ - 1)
#define INT_LEAST8_MAX __INT_LEAST8_MAX__
#define INT_LEAST8_MIN (-__INT_LEAST8_MAX__ - 1)
#define INT_LEAST16_MAX __INT_LEAST16_MAX__
#define INT_LEAST16_MIN (-__INT_LEAST16_MAX__ - 1)
#define INT_LEAST32_MAX __INT_LEAST32_MAX__
#define INT_LEAST32_MIN (-__INT_LEAST32_MAX__ - 1)
#define INT_LEAST64_MAX __INT_LEAST64_MAX__
#define INT_LEAST64_MIN (-__INT_LEAST64_MAX__ - 1)
#define INT_FAST8_MAX __INT_FAST8_MAX__
#define INT_FAST8_MIN (-__INT_FAST8_MAX__ - 1)
#define INT_FAST16_MAX __INT_FAST16_MAX__
#define INT_FAST16_MIN (-__INT_FAST16_MAX__ - 1)
#define INT_FAST32_MAX __INT_FAST32_MAX__
#define INT_FAST32_MIN (-__INT_FAST32_MAX__ - 1)
#define INT_FAST64_MAX __INT_FAST64_MAX__
#define INT_FAST64_MIN (-__INT_FAST64_MAX__ - 1)
#define INTPTR_MAX __INTPTR_MAX__
#define INTPTR_MIN (-__INTPTR_MAX__ - 1)
#define INTMAX_MAX __INTMAX_MAX__
#define INTMAX_MIN (-__INTMAX_MAX__ - 1)

#define UINT8_MAX __UINT8_MAX__
#define UINT16_MAX __UINT16_MAX__
#define UINT32_MAX __UINT32_MAX__
#define UINT64_MAX __UINT64_MAX__
#define UINT_LEAST8_MAX __UINT_LEAST8_MAX__
#define UINT_LEAST16_MAX __UINT_LEAST16_MAX__
#define UINT_LEAST32_MAX __UINT_LEAST32_MAX__
#define UINT_LEAST64_MAX __UINT_LEAST64_MAX__
#define UINT_FAST8_MAX __UINT_FAST8_MAX__
#define UINT_FAST16_MAX __UINT_FAST16_MAX__
#define UINT_FAST32_MAX __UINT_FAST32_MAX__
#define UINT_FAST64_MAX __UINT_FAST64_MAX__
#define UINTPTR_MAX __UINTPTR_MAX__
#define UINTMAX_MAX __UINTMAX_MAX__

#define PTRDIFF_MAX __PTRDIFF_MAX__
#define PTRDIFF_MIN (-__PTRDIFF_MAX__ - 1)
#define SIZE_MAX __SIZE_MAX__
#define WCHAR_MAX __WCHAR_MAX__
#define WCHAR_MIN __WCHAR_MIN__
#define WINT_MAX __WINT_MAX__
#define WINT_MIN __WINT_MIN__

#ifdef __cplusplus
#define ETL_SHIM_ASSERT(c, m) static_assert(c, m)
#else
/* 老内核可能用 gnu89，不能依赖 _Static_assert 关键字 */
#define ETL_SHIM_ASSERT(c, m) typedef char etl_shim_assert_##__COUNTER__[(c) ? 1 : -1]
#endif
ETL_SHIM_ASSERT(sizeof(int8_t) == 1, "int8_t");
ETL_SHIM_ASSERT(sizeof(uint8_t) == 1, "uint8_t");
ETL_SHIM_ASSERT(sizeof(int16_t) == 2, "int16_t");
ETL_SHIM_ASSERT(sizeof(uint16_t) == 2, "uint16_t");
ETL_SHIM_ASSERT(sizeof(int32_t) == 4, "int32_t");
ETL_SHIM_ASSERT(sizeof(uint32_t) == 4, "uint32_t");
ETL_SHIM_ASSERT(sizeof(int64_t) == 8, "int64_t");
ETL_SHIM_ASSERT(sizeof(uint64_t) == 8, "uint64_t");
ETL_SHIM_ASSERT(sizeof(intptr_t) == sizeof(void *), "intptr_t");
#undef ETL_SHIM_ASSERT
