#!/usr/bin/env python3

"""按目标内核和编译器生成 libc_port 的架构相关头文件。

静态头只放函数声明；这里生成：
  errno.h         从 <asm/errno.h> 展开，换架构时错误码跟着内核走
  bits/types.h    time_t/ssize_t/clock_t 等，取编译器内置宏
  bits/limits.h   整数限值，取编译器内置宏
"""

import argparse
import subprocess
import sys
from pathlib import Path

# 让脚本无论从哪个目录调用都能 import 到 linuxcppgen
sys.path.insert(0, str(Path(__file__).resolve().parent))

from linuxcppgen.btf import kernel_include_flags

def is_errno_name(name):
    """只看预处理器输出的标识符，不做任何 C 源码解析"""
    return (len(name) > 1 and name[0] == "E"
            and all(ch.isupper() or ch.isdigit() or ch == "_" for ch in name[1:]))


def numeric_value(value):
    """把宏值规范成整数；不是整数就返回 None"""
    value = value.strip()
    if value.startswith("(") and value.endswith(")"):
        value = value[1:-1].strip()
    try:
        int(value, 0)
    except ValueError:
        return None
    return value


# 某些架构/头组合不定义这些别名，但 POSIX 头里常见，补成指向已有名字
ERRNO_FALLBACK = {
    "ENOTSUP": "EOPNOTSUPP",
    "EWOULDBLOCK": "EAGAIN",
    "EDEADLOCK": "EDEADLK",
}


def dump_macros(cc, flags, includes):
    source = "".join(f"#include <{name}>\n" for name in includes)
    result = subprocess.run(
        cc + flags + ["-dM", "-E", "-x", "c", "-"],
        input=source, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        sys.exit(f"预处理失败:\n{result.stderr}")
    macros = {}
    for line in result.stdout.splitlines():
        if not line.startswith("#define "):
            continue
        rest = line[len("#define "):]
        fields = rest.split(None, 1)
        if len(fields) == 2:
            macros[fields[0]] = fields[1]
    return macros


def require(macros, name):
    if name not in macros:
        sys.exit(f"编译器没有定义 {name}，无法生成 libc 头")
    return macros[name]


def gen_errno(macros):
    numeric = {}
    aliases = {}
    for name, value in macros.items():
        if not is_errno_name(name):
            continue
        number = numeric_value(value)
        if number is not None:
            numeric[name] = number
        elif is_errno_name(value.strip()):
            aliases[name] = value.strip()

    for name, target in ERRNO_FALLBACK.items():
        if name not in numeric and name not in aliases and target in numeric:
            aliases[name] = target

    # 别名要排在目标后面；先放数值，再逐轮放能解析的别名
    ordered_aliases = []
    pending = dict(aliases)
    known = set(numeric)
    while pending:
        progress = False
        for name, target in list(pending.items()):
            if target in known:
                ordered_aliases.append((name, target))
                known.add(name)
                del pending[name]
                progress = True
        if not progress:
            # 目标不在 errno 头里，跳过这个别名，避免生成不存在的枚举值
            for name in pending:
                print(f"警告：忽略无法解析的 errno 别名 {name}", file=sys.stderr)
            break

    lines = [
        "// 由 gen_libc_headers.py 从 <asm/errno.h> 生成，不要手改。",
        "#pragma once",
        "",
        "#ifdef __cplusplus",
        'extern "C" {',
        "#endif",
        "",
        "int *__errno_location(void);",
        "",
        "#ifdef __cplusplus",
        "}",
        "#endif",
        "",
        "#define errno (*__errno_location())",
        "",
        "// 告诉 libc++ 的 errno.h 包装头：错误码已经由这里提供，不要再补宏",
        "#define _LIBCPP_ERRNO_DEFINED_BY_PORT",
        "",
        "enum {",
    ]
    for name in sorted(numeric):
        lines.append(f"\t{name} = {numeric[name]},")
    for name, target in ordered_aliases:
        lines.append(f"\t{name} = {target},")
    lines.append("};")
    lines.append("")
    return "\n".join(lines)


def gen_types(macros):
    wint = macros.get("__WINT_TYPE__", "unsigned int")
    return "\n".join([
        "// 由 gen_libc_headers.py 从编译器内置宏生成，不要手改。",
        "#pragma once",
        "",
        f"typedef {require(macros, '__PTRDIFF_TYPE__')} ssize_t;",
        f"typedef {require(macros, '__INT64_TYPE__')} time_t;",
        "typedef long clock_t;",
        f"typedef {wint} wint_t;",
        "",
    ])


def gen_limits(macros):
    lines = [
        "// 由 gen_libc_headers.py 从编译器内置宏生成，不要手改。",
        "#pragma once",
        "",
    ]

    def define(name, value):
        # 编译器/内核头可能已经定义过，重复定义会在 C++ 编译期刷警告
        lines.extend([f"#ifndef {name}",
                      f"#define {name} {value}",
                      "#endif"])

    define("CHAR_BIT", require(macros, "__CHAR_BIT__"))
    define("SCHAR_MAX", require(macros, "__SCHAR_MAX__"))
    define("SCHAR_MIN", "(-SCHAR_MAX - 1)")
    define("UCHAR_MAX", "(SCHAR_MAX * 2 + 1)")
    define("SHRT_MAX", require(macros, "__SHRT_MAX__"))
    define("SHRT_MIN", "(-SHRT_MAX - 1)")
    define("USHRT_MAX", "(SHRT_MAX * 2 + 1)")
    define("INT_MAX", require(macros, "__INT_MAX__"))
    define("INT_MIN", "(-INT_MAX - 1)")
    define("UINT_MAX", "(INT_MAX * 2U + 1U)")
    define("LONG_MAX", require(macros, "__LONG_MAX__"))
    define("LONG_MIN", "(-LONG_MAX - 1L)")
    define("ULONG_MAX", "(LONG_MAX * 2UL + 1UL)")
    define("LLONG_MAX", require(macros, "__LONG_LONG_MAX__"))
    define("LLONG_MIN", "(-LLONG_MAX - 1LL)")
    define("ULLONG_MAX", "(LLONG_MAX * 2ULL + 1ULL)")
    define("PTRDIFF_MAX", require(macros, "__PTRDIFF_MAX__"))
    define("PTRDIFF_MIN", "(-PTRDIFF_MAX - 1)")
    define("SIZE_MAX", require(macros, "__SIZE_MAX__"))
    define("WCHAR_MAX", macros.get("__WCHAR_MAX__", "2147483647"))
    define("WINT_MAX", macros.get("__WINT_MAX__", "4294967295U"))

    lines.extend([
        "#ifndef CHAR_MIN",
        "#ifdef __CHAR_UNSIGNED__",
        "#define CHAR_MIN 0",
        "#define CHAR_MAX UCHAR_MAX",
        "#else",
        "#define CHAR_MIN SCHAR_MIN",
        "#define CHAR_MAX SCHAR_MAX",
        "#endif",
        "#endif",
        "",
        "#ifndef MB_LEN_MAX",
        "#define MB_LEN_MAX 16",
        "#endif",
        "",
    ])
    return "\n".join(lines)


def write_if_changed(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    path.write_text(text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="生成 libc_port 的架构相关头文件")
    parser.add_argument("--kdir", required=True, help="内核 build 目录")
    parser.add_argument("--out-dir", required=True, help="输出目录（include 根）")
    parser.add_argument("--cc", default="gcc", help="目标 C 编译器")
    parser.add_argument("--cflags", action="append", default=[],
                        help="影响类型宽度的目标参数，如 -fshort-wchar；可重复")
    args = parser.parse_args()

    out = Path(args.out_dir)
    compiler = [args.cc]
    compiler_macros = dump_macros(compiler, args.cflags, [])
    errno_macros = dump_macros(
        compiler, args.cflags + list(kernel_include_flags(args.kdir)),
        ["asm/errno.h"])

    write_if_changed(out / "errno.h", gen_errno(errno_macros))
    write_if_changed(out / "bits" / "types.h", gen_types(compiler_macros))
    write_if_changed(out / "bits" / "limits.h", gen_limits(compiler_macros))
    print(f"libc 头已生成: {out}")


if __name__ == "__main__":
    main()
