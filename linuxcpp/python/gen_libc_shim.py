#!/usr/bin/env python3

"""生成 ETL 等无 STL 库所需的标准 C 头 shim。

内核模块在 -nostdinc 下没有 libc 头，而 ETL 会 include <stdint.h>、<limits.h>、
<string.h> 等。这里生成一组最小头文件：整数类型和限值直接取编译器的内置宏，
换架构时自动适配；字符串函数按内核导出符号声明；ctype 内核里是 static inline，
没有可链接符号，因此生成内联实现。
"""

import argparse
import os
import re
import subprocess
import sys

# 标准名 → 编译器内置类型宏
STDINT_TYPES = [
    ("int8_t", "__INT8_TYPE__"), ("uint8_t", "__UINT8_TYPE__"),
    ("int16_t", "__INT16_TYPE__"), ("uint16_t", "__UINT16_TYPE__"),
    ("int32_t", "__INT32_TYPE__"), ("uint32_t", "__UINT32_TYPE__"),
    ("int64_t", "__INT64_TYPE__"), ("uint64_t", "__UINT64_TYPE__"),
    ("int_least8_t", "__INT_LEAST8_TYPE__"), ("uint_least8_t", "__UINT_LEAST8_TYPE__"),
    ("int_least16_t", "__INT_LEAST16_TYPE__"), ("uint_least16_t", "__UINT_LEAST16_TYPE__"),
    ("int_least32_t", "__INT_LEAST32_TYPE__"), ("uint_least32_t", "__UINT_LEAST32_TYPE__"),
    ("int_least64_t", "__INT_LEAST64_TYPE__"), ("uint_least64_t", "__UINT_LEAST64_TYPE__"),
    ("int_fast8_t", "__INT_FAST8_TYPE__"), ("uint_fast8_t", "__UINT_FAST8_TYPE__"),
    ("int_fast16_t", "__INT_FAST16_TYPE__"), ("uint_fast16_t", "__UINT_FAST16_TYPE__"),
    ("int_fast32_t", "__INT_FAST32_TYPE__"), ("uint_fast32_t", "__UINT_FAST32_TYPE__"),
    ("int_fast64_t", "__INT_FAST64_TYPE__"), ("uint_fast64_t", "__UINT_FAST64_TYPE__"),
    ("intptr_t", "__INTPTR_TYPE__"), ("uintptr_t", "__UINTPTR_TYPE__"),
    ("intmax_t", "__INTMAX_TYPE__"), ("uintmax_t", "__UINTMAX_TYPE__"),
]

# 有符号限值：MIN 由 MAX 推导，避免另找一套内置宏
STDINT_SIGNED = [
    ("INT8", "__INT8_MAX__"), ("INT16", "__INT16_MAX__"),
    ("INT32", "__INT32_MAX__"), ("INT64", "__INT64_MAX__"),
    ("INT_LEAST8", "__INT_LEAST8_MAX__"), ("INT_LEAST16", "__INT_LEAST16_MAX__"),
    ("INT_LEAST32", "__INT_LEAST32_MAX__"), ("INT_LEAST64", "__INT_LEAST64_MAX__"),
    ("INT_FAST8", "__INT_FAST8_MAX__"), ("INT_FAST16", "__INT_FAST16_MAX__"),
    ("INT_FAST32", "__INT_FAST32_MAX__"), ("INT_FAST64", "__INT_FAST64_MAX__"),
    ("INTPTR", "__INTPTR_MAX__"), ("INTMAX", "__INTMAX_MAX__"),
]

STDINT_UNSIGNED = [
    ("UINT8", "__UINT8_MAX__"), ("UINT16", "__UINT16_MAX__"),
    ("UINT32", "__UINT32_MAX__"), ("UINT64", "__UINT64_MAX__"),
    ("UINT_LEAST8", "__UINT_LEAST8_MAX__"), ("UINT_LEAST16", "__UINT_LEAST16_MAX__"),
    ("UINT_LEAST32", "__UINT_LEAST32_MAX__"), ("UINT_LEAST64", "__UINT_LEAST64_MAX__"),
    ("UINT_FAST8", "__UINT_FAST8_MAX__"), ("UINT_FAST16", "__UINT_FAST16_MAX__"),
    ("UINT_FAST32", "__UINT_FAST32_MAX__"), ("UINT_FAST64", "__UINT_FAST64_MAX__"),
    ("UINTPTR", "__UINTPTR_MAX__"), ("UINTMAX", "__UINTMAX_MAX__"),
]

HEADER = "/* 由 gen_libc_shim.py 生成，不要手改 */\n#pragma once\n"


def collect_macros(cc):
    # 内核用 -funsigned-char -fshort-wchar 编译，__CHAR_UNSIGNED__ 和 wchar
    # 的内置宏必须按同样的选项取，否则 limits.h 的 CHAR_MIN/MAX 是反的
    out = subprocess.run([cc, "-E", "-dM", "-funsigned-char", "-fshort-wchar",
                          "-x", "c", os.devnull],
                         check=True, stdout=subprocess.PIPE, text=True).stdout
    macros = {}
    for line in out.splitlines():
        match = re.match(r"#define (\w+) ?(.*)", line)
        if match:
            macros[match.group(1)] = match.group(2)
    return macros


def need(macros, name):
    if name not in macros:
        sys.exit(f"编译器没有内置宏 {name}，无法生成 shim")


def gen_stdint(macros):
    lines = [HEADER]
    for name, macro in STDINT_TYPES:
        need(macros, macro)
        lines.append(f"typedef {macro} {name};")
    lines.append("")
    for name, macro in STDINT_SIGNED:
        need(macros, macro)
        lines.append(f"#define {name}_MAX {macro}")
        lines.append(f"#define {name}_MIN (-{macro} - 1)")
    lines.append("")
    for name, macro in STDINT_UNSIGNED:
        need(macros, macro)
        lines.append(f"#define {name}_MAX {macro}")
    lines += [
        "",
        "#define PTRDIFF_MAX __PTRDIFF_MAX__",
        "#define PTRDIFF_MIN (-__PTRDIFF_MAX__ - 1)",
        "#define SIZE_MAX __SIZE_MAX__",
        "#define WCHAR_MAX __WCHAR_MAX__",
        "#define WCHAR_MIN __WCHAR_MIN__",
        "#define WINT_MAX __WINT_MAX__",
        "#define WINT_MIN __WINT_MIN__",
        "",
        "#ifdef __cplusplus",
        "#define ETL_SHIM_ASSERT(c, m) static_assert(c, m)",
        "#else",
        "/* 老内核可能用 gnu89，不能依赖 _Static_assert 关键字 */",
        "#define ETL_SHIM_ASSERT(c, m) typedef char etl_shim_assert_##__COUNTER__[(c) ? 1 : -1]",
        "#endif",
        'ETL_SHIM_ASSERT(sizeof(int8_t) == 1, "int8_t");',
        'ETL_SHIM_ASSERT(sizeof(uint8_t) == 1, "uint8_t");',
        'ETL_SHIM_ASSERT(sizeof(int16_t) == 2, "int16_t");',
        'ETL_SHIM_ASSERT(sizeof(uint16_t) == 2, "uint16_t");',
        'ETL_SHIM_ASSERT(sizeof(int32_t) == 4, "int32_t");',
        'ETL_SHIM_ASSERT(sizeof(uint32_t) == 4, "uint32_t");',
        'ETL_SHIM_ASSERT(sizeof(int64_t) == 8, "int64_t");',
        'ETL_SHIM_ASSERT(sizeof(uint64_t) == 8, "uint64_t");',
        'ETL_SHIM_ASSERT(sizeof(intptr_t) == sizeof(void *), "intptr_t");',
        "#undef ETL_SHIM_ASSERT",
        "",
    ]
    return "\n".join(lines)


def gen_limits(macros):
    unsigned_char = "__CHAR_UNSIGNED__" in macros
    char_min = "0" if unsigned_char else "SCHAR_MIN"
    char_max = "UCHAR_MAX" if unsigned_char else "SCHAR_MAX"
    lines = [
        HEADER,
        "#define CHAR_BIT __CHAR_BIT__",
        "#define SCHAR_MIN (-__SCHAR_MAX__ - 1)",
        "#define SCHAR_MAX __SCHAR_MAX__",
        "#define UCHAR_MAX (__SCHAR_MAX__ * 2 + 1)",
        "#define SHRT_MIN (-__SHRT_MAX__ - 1)",
        "#define SHRT_MAX __SHRT_MAX__",
        "#define USHRT_MAX (__SHRT_MAX__ * 2 + 1)",
        "#define INT_MIN (-__INT_MAX__ - 1)",
        "#define INT_MAX __INT_MAX__",
        "#define UINT_MAX (__INT_MAX__ * 2U + 1U)",
        "#define LONG_MIN (-__LONG_MAX__ - 1L)",
        "#define LONG_MAX __LONG_MAX__",
        "#define ULONG_MAX (__LONG_MAX__ * 2UL + 1UL)",
        "#define LLONG_MIN (-__LONG_LONG_MAX__ - 1LL)",
        "#define LLONG_MAX __LONG_LONG_MAX__",
        "#define ULLONG_MAX (__LONG_LONG_MAX__ * 2ULL + 1ULL)",
        f"#define CHAR_MIN {char_min}",
        f"#define CHAR_MAX {char_max}",
        "#define MB_LEN_MAX 16",
        "",
    ]
    return "\n".join(lines)


def gen_string():
    return HEADER + """\
#ifdef __cplusplus
extern "C" {
#endif
void *memcpy(void *, const void *, __SIZE_TYPE__);
void *memmove(void *, const void *, __SIZE_TYPE__);
void *memset(void *, int, __SIZE_TYPE__);
int memcmp(const void *, const void *, __SIZE_TYPE__);
__SIZE_TYPE__ strlen(const char *);
int strcmp(const char *, const char *);
int strncmp(const char *, const char *, __SIZE_TYPE__);
char *strcpy(char *, const char *);
char *strncpy(char *, const char *, __SIZE_TYPE__);
#ifdef __cplusplus
}
#endif
"""


def gen_ctype():
    # 内核的 ctype 是查表 static inline，没有可链接符号，只能给等价实现
    return HEADER + """\
static inline int isdigit(int c) { return c >= '0' && c <= '9'; }
static inline int isalpha(int c) { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z'); }
static inline int isalnum(int c) { return isdigit(c) || isalpha(c); }
static inline int isspace(int c) { return c == ' ' || (c >= '\\t' && c <= '\\r'); }
static inline int isupper(int c) { return c >= 'A' && c <= 'Z'; }
static inline int islower(int c) { return c >= 'a' && c <= 'z'; }
static inline int toupper(int c) { return islower(c) ? c - 'a' + 'A' : c; }
static inline int tolower(int c) { return isupper(c) ? c - 'A' + 'a' : c; }
"""


def gen_assert():
    return HEADER + """\
#define assert(cond) do { if (!(cond)) __builtin_trap(); } while (0)
"""


def gen_stdlib():
    return HEADER + """\
static inline int abs(int x) { return x < 0 ? -x : x; }
static inline long labs(long x) { return x < 0 ? -x : x; }
"""


def gen_math():
    # 内核模块不能用浮点，这里只让头文件存在；真用浮点会在链接期暴露
    return HEADER


def gen_cstddef():
    return HEADER + """\
#include <stddef.h>
namespace std { using ::size_t; using ::ptrdiff_t; }
"""


def gen_new():
    # ETL 的 <new> 只是要 placement new；系统 <new> 会和 linuxcpp.hpp 的定义冲突
    return HEADER + """\
#ifndef LCPP_PLACEMENT_NEW_DEFINED
#define LCPP_PLACEMENT_NEW_DEFINED
inline void *operator new(__SIZE_TYPE__, void *ptr) noexcept { return ptr; }
inline void *operator new[](__SIZE_TYPE__, void *ptr) noexcept { return ptr; }
inline void operator delete(void *, void *) noexcept {}
inline void operator delete[](void *, void *) noexcept {}
#endif
"""


GENERATORS = {
    "stdint.h": gen_stdint,
    "limits.h": gen_limits,
    "string.h": gen_string,
    "ctype.h": gen_ctype,
    "assert.h": gen_assert,
    "stdlib.h": gen_stdlib,
    "math.h": gen_math,
    "cstddef": gen_cstddef,
    "new": gen_new,
}


def main():
    parser = argparse.ArgumentParser(description="生成无 STL 库所需的标准 C 头 shim")
    parser.add_argument("--out-dir", required=True, help="shim 输出目录")
    parser.add_argument("--cc", default=os.environ.get("CC", "gcc"),
                        help="用于读取内置宏的编译器")
    args = parser.parse_args()

    macros = collect_macros(args.cc)
    os.makedirs(args.out_dir, exist_ok=True)
    for name, generator in GENERATORS.items():
        path = os.path.join(args.out_dir, name)
        # 只有整数类型/限值依赖编译器内置宏，其余是固定实现
        text = generator(macros) if generator in (gen_stdint, gen_limits) else generator()
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        print(f"生成 {path}")


if __name__ == "__main__":
    main()
