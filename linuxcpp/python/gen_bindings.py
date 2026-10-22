#!/usr/bin/env python3

"""从内核 BTF 生成 C++ 绑定和布局校验源码。

实现按职责拆在 linuxcppgen/ 下：
  linuxcppgen/btf.py     bpftool 导出和 vmlinux.h 解析
  linuxcppgen/deps.py    类型依赖闭包
  linuxcppgen/types.py   C/C++ 类型生成
  linuxcppgen/decls.py   导出函数、C thunk、对象宏
  linuxcppgen/codegen.py 流程编排

产出：
  generated/bindings.h      C 版本，类型加 lc_ 前缀，用于布局校验
  generated/bindings.hpp    C++ 版本，位于 namespace linuxcpp::abi
  layout_check.c            static_assert 对比生成类型与内核真实布局
"""

import argparse
import os

from linuxcppgen.codegen import generate


def parse_args():
    parser = argparse.ArgumentParser(description="从内核 BTF 生成 C/C++ 绑定")
    parser.add_argument("--kdir", default=f"/lib/modules/{os.uname().release}/build",
                        help="内核 build 目录（指向源码树）")
    parser.add_argument("--btf", default="/sys/kernel/btf/vmlinux",
                        help="btf dump 的输入文件")
    parser.add_argument("--out-dir",
                        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated"))
    parser.add_argument("--work-dir", default=os.getcwd(),
                        help="layout_check.c 和 thunks_gen.c 的输出目录（通常是模块目录）")
    parser.add_argument("--root", action="append", dest="roots",
                        help="需要完整定义的类型，可多次指定")
    parser.add_argument("--namespace", default="linuxcpp::abi",
                        help="C++ 命名空间")
    parser.add_argument("--prefix", default="lc_", help="C 版类型前缀")
    parser.add_argument("--header", action="append", dest="headers",
                        help="解析函数声明用的内核头文件，默认一组常用头")
    parser.add_argument("--extern", action="append", default=[],
                        help="需要生成声明的内核导出函数")
    parser.add_argument("--thunk", action="append", default=[],
                        help="需要生成 C thunk 的 static inline 函数")
    parser.add_argument("--macro", action="append", default=[],
                        help="需要导出为 constexpr 的对象宏（函数宏请手写 thunk）")
    parser.add_argument("--all", action="store_true",
                        help="所有 BTF record 都作为根（全量测试，输出很大）")
    parser.add_argument("--packed", action="append", default=[],
                        help="强制加 packed 的类型（bpftool 的 vmlinux.h 会漏掉 __packed）")
    return parser.parse_args()


if __name__ == "__main__":
    generate(parse_args())
