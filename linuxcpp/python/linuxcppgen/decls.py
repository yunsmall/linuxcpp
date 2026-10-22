"""内核函数声明、C thunk 和对象宏的提取。"""

import os
import random
import shutil
import subprocess
import sys

import clang.cindex as ci

from .btf import kernel_include_flags
from .config import DEFAULT_HEADERS
from .types import cpp_param, cpp_type, gen_func_pointer, gen_type, split_declarator

# 同一个 kdir 在一次生成里会被问很多次；Module.symvers 有几十万行，
# 每次重读会明显拖慢绑定生成
_export_cache = {}


def kernel_exported_symbols(kdir):
    """读内核构建树的 Module.symvers；读不到时返回 None，跳过导出检查"""
    path = os.path.join(kdir, "Module.symvers")
    if path in _export_cache:
        return _export_cache[path]
    symbols = set()
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                fields = line.split()
                if len(fields) >= 2:
                    symbols.add(fields[1])
    except OSError:
        symbols = None
    _export_cache[path] = symbols
    return symbols


def parse_kernel_decls(names, kdir, headers):
    """在真实内核头里找函数声明/定义，签名交给 clang 解析"""
    # 用户额外指定的头 + 默认头，去重保序
    headers = list(dict.fromkeys((headers or []) + DEFAULT_HEADERS))
    source = "".join(f"#include <{header}>\n" for header in headers)
    index = ci.Index.create()
    tu = index.parse("lc_decls.c", args=kernel_include_flags(kdir),
                     unsaved_files=[("lc_decls.c", source)])
    result = {}
    for cursor in tu.cursor.walk_preorder():
        if cursor.kind == ci.CursorKind.FUNCTION_DECL and cursor.spelling in names:
            if cursor.spelling not in result or cursor.is_definition():
                result[cursor.spelling] = cursor
    return result


def find_macros(source, kdir, names):
    """用 libclang 的预处理记录找宏定义，避免手写 #define 解析"""
    index = ci.Index.create()
    options = ci.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD
    tu = index.parse("lc_macros.c", args=kernel_include_flags(kdir),
                     unsaved_files=[("lc_macros.c", source)], options=options)
    targets = set(names)
    found = {}
    # 同名宏取最后一次定义；函数宏用 None 标记
    for cursor in tu.cursor.walk_preorder():
        if cursor.kind != ci.CursorKind.MACRO_DEFINITION:
            continue
        name = cursor.spelling
        if name not in targets:
            continue
        # Python 绑定没暴露 is_macro_function_like()，直接调 libclang C API
        if ci.conf.lib.clang_Cursor_isMacroFunctionLike(cursor):
            found[name] = None
        else:
            tokens = list(cursor.get_tokens())
            found[name] = tokens[1:]
    return found


def parse_macros(names, kdir, headers):
    """把无参对象宏导出成 constexpr；函数宏是 token 替换，不能自动翻译"""
    if not names:
        return []
    headers = list(dict.fromkeys((headers or []) + DEFAULT_HEADERS))
    source = ("#include <linux/errno.h>\n#include <linux/err.h>\n"
              + "".join(f"#include <{header}>\n" for header in headers))
    clang = shutil.which("clang-22") or shutil.which("clang")
    if clang:
        tool, flags = clang, list(kernel_include_flags(kdir))
    else:
        tool = shutil.which("gcc")
        flags = [arg for arg in kernel_include_flags(kdir) if arg != "-Wno-everything"]
    if not tool:
        sys.exit("宏导出需要 clang 或 gcc 预处理器")

    def run(args, text):
        try:
            return subprocess.run(args, input=text, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, check=True).stdout
        except (OSError, subprocess.CalledProcessError):
            sys.exit(f"宏导出失败，无法运行 {tool}")

    definitions = find_macros(source, kdir, names)
    missing = object()
    for name in names:
        tokens = definitions.get(name, missing)
        if tokens is missing:
            sys.exit(f"找不到宏 {name}")
        if tokens is None:
            sys.exit(f"{name} 是函数宏，不能自动导出；请手写 C thunk 或 constexpr 包装")
        if not tokens:
            sys.exit(f"{name} 是空对象宏，不能导出")

    # 用哨兵把每个宏的展开结果隔开；不能依赖“输出行数等于宏数”，
    # 多行展开会让后面的宏全部错位
    sentinel = f"LC_MACRO_EXPAND_{os.getpid()}_{random.randrange(1 << 32):08x}"
    request = source + "\n" + "".join(
        f"{sentinel}_{index}\n{name}\n{sentinel}_{index}_END\n"
        for index, name in enumerate(names))
    values = run([tool, "-E", "-P"] + flags + ["-"], request)
    lines = [line.strip() for line in values.splitlines() if line.strip()]
    expanded = {}
    current = None
    for line in lines:
        if line.startswith(f"{sentinel}_") and line.endswith("_END"):
            current = None
        elif line.startswith(f"{sentinel}_"):
            current = int(line[len(sentinel) + 1:])
            expanded[current] = []
        elif current is not None:
            expanded[current].append(line)

    result = []
    for index, name in enumerate(names):
        parts = expanded.get(index)
        if not parts:
            sys.exit(f"无法展开宏 {name}")
        # 保留换行：字符串字面量/原始字符串里的换行不能被空格替换，
        # 普通表达式里的换行本来就是空白，不影响 C++ 语法
        value = "\n".join(parts)
        if value == name:
            sys.exit(f"无法展开宏 {name}")
        result.append((name, value))
    return result


def c_param(t, name):
    """C 参数声明；函数指针和数组要把名字塞进声明符"""
    if t.kind == ci.TypeKind.POINTER and t.get_pointee().kind == ci.TypeKind.FUNCTIONPROTO:
        return gen_func_pointer(t.get_pointee(), name, lambda n: n, False)
    base, decl = split_declarator(t, name)
    base_type = gen_type(base, lambda n: n, False)
    if base_type is None:
        base_type = t.spelling
    return f"{base_type} {decl}"


def is_func_pointer_type(t):
    return t.kind == ci.TypeKind.POINTER and t.get_pointee().kind == ci.TypeKind.FUNCTIONPROTO


def c_function_head(cursor, prefix, params):
    """拼 C 函数头；返回函数指针时要把名字放进 (*...) 里"""
    ret = cursor.result_type
    params_text = ", ".join(params) if params else "void"
    if is_func_pointer_type(ret):
        fp = ret.get_pointee()
        if is_func_pointer_type(fp.get_result()):
            sys.exit(f"{cursor.spelling} 返回多层函数指针，不能自动生成；请手写")
        ret_params = [gen_type(arg, lambda n: n, False) for arg in fp.argument_types()]
        if fp.is_function_variadic():
            ret_params.append("...")
        ret_base = gen_type(fp.get_result(), lambda n: n, False)
        return (f"{ret_base} (*{prefix}{cursor.spelling}({params_text}))"
                f"({', '.join(ret_params) if ret_params else 'void'})")
    if ret.kind == ci.TypeKind.POINTER and ret.get_pointee().kind in (
            ci.TypeKind.CONSTANTARRAY, ci.TypeKind.INCOMPLETEARRAY):
        base, declarator = split_declarator(ret, "")
        return (f"{gen_type(base, lambda n: n, False)} "
                + declarator.replace(
                    "(*)", f"(*{prefix}{cursor.spelling}({params_text}))", 1))
    return f"{ret.spelling} {prefix}{cursor.spelling}({params_text})"


def gen_c_thunk_head(cursor, prefix):
    """thunk 的函数头，定义和前置声明共用，避免 -Wmissing-prototypes"""
    params = []
    for index, arg in enumerate(cursor.get_arguments()):
        name = arg.spelling or f"arg{index}"
        params.append(c_param(arg.type, name))
    return c_function_head(cursor, prefix, params)


def gen_c_thunk(cursor, prefix):
    if cursor.type.is_function_variadic():
        sys.exit(f"{cursor.spelling} 是变参函数，不能自动生成 C thunk；请手写转发 va_list 的包装")
    args = [arg.spelling or f"arg{index}"
            for index, arg in enumerate(cursor.get_arguments())]
    call = f"{cursor.spelling}({', '.join(args)})"
    body = f"{call};" if cursor.result_type.spelling == "void" else f"return {call};"
    return f"{gen_c_thunk_head(cursor, prefix)}\n{{\n\t{body}\n}}"


def cpp_function_head(cursor, prefix, params, known):
    ret = cursor.result_type
    params_text = ", ".join(params) if params else "void"
    if is_func_pointer_type(ret):
        fp = ret.get_pointee()
        if is_func_pointer_type(fp.get_result()):
            sys.exit(f"{cursor.spelling} 返回多层函数指针，不能自动生成；请手写")
        ret_params = [cpp_type(arg, known) for arg in fp.argument_types()]
        if fp.is_function_variadic():
            ret_params.append("...")
        ret_base = cpp_type(fp.get_result(), known)
        return (f"{ret_base} (*{prefix}{cursor.spelling}({params_text}))"
                f"({', '.join(ret_params) if ret_params else 'void'})")
    if ret.kind == ci.TypeKind.POINTER and ret.get_pointee().kind in (
            ci.TypeKind.CONSTANTARRAY, ci.TypeKind.INCOMPLETEARRAY):
        abstract = cpp_declarator(ret, "", known)
        return abstract.replace(
            "(*)", f"(*{prefix}{cursor.spelling}({params_text}))", 1)
    return f"{cpp_type(ret, known)} {prefix}{cursor.spelling}({params_text})"


def gen_cpp_decl(cursor, prefix, known):
    params = []
    for index, arg in enumerate(cursor.get_arguments()):
        name = arg.spelling or f"arg{index}"
        params.append(cpp_param(arg.type, name, known))
    if cursor.type.is_function_variadic():
        params.append("...")
    return cpp_function_head(cursor, prefix, params, known) + ";"
