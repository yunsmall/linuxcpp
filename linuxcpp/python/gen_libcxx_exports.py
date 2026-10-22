#!/usr/bin/env python3

"""从 libc++ 运行库对象收集全局符号，生成 EXPORT_SYMBOL_GPL 表。

libcxx_runtime.ko 只有导出过的符号才能被其他模块使用；这里用 nm 枚举所有
已定义的全局符号，跳过局部符号和内核自己的 ksymtab 名称。
"""

import argparse
import re
import subprocess
from pathlib import Path

# Itanium ABI 的全局符号名只含字母、数字和下划线；不是这个形状的（例如
# 编译器生成的 .L 本地标签）不能写进 EXPORT_SYMBOL_GPL
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
EXPORTABLE = set("TWVDBR")


def collect(objects):
    names = set()
    for obj in objects:
        result = subprocess.run(
            ["nm", "-g", "--defined-only", "-P", str(obj)],
            check=True, stdout=subprocess.PIPE, text=True)
        for line in result.stdout.splitlines():
            fields = line.split()
            if len(fields) < 2:
                continue
            name, kind = fields[0], fields[1]
            if kind not in EXPORTABLE:
                continue
            if name.startswith(("__ksymtab", "__kstrtab")):
                continue
            if IDENTIFIER.match(name):
                names.add(name)
    return sorted(names)


def main():
    parser = argparse.ArgumentParser(description="生成 libc++ 内核导出表")
    parser.add_argument("--output", required=True, help="输出 C 文件")
    parser.add_argument("objects", nargs="+", help="libc++ 运行库对象")
    args = parser.parse_args()

    names = collect(args.objects)
    lines = [
        "// 由 gen_libcxx_exports.py 生成，不要手改。",
        "#include <linux/export.h>",
        "",
    ]
    # EXPORT_SYMBOL_GPL 内部会写 extern typeof(sym) sym，必须先有声明。
    # 这里只关心地址，char[] 对函数和数据符号都能取到正确的符号地址。
    lines += [f"extern char {name}[];" for name in names]
    lines.append("")
    lines += [f"EXPORT_SYMBOL_GPL({name});" for name in names]
    Path(args.output).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"导出 {len(names)} 个 libc++ 符号到 {args.output}")


if __name__ == "__main__":
    main()
