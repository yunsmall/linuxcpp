"""从 kbuild 抓 C 编译参数，转换成 C++ 编译参数。"""

import os
import re
import shutil
import subprocess
import sys

from paths import INCLUDE_DIR


def is_compiler_token(arg):
    """gcc、gcc-12、clang-18、/usr/bin/clang 都算编译器；distcc 这类 wrapper 不算"""
    name = os.path.basename(arg)
    return re.search(
        r"(?:^|[-/])(?:gcc|g\+\+|clang|clang\+\+|cc|c\+\+)(?:-[\d.]+)?$",
        name) is not None


def cxx_compiler(config, cc):
    """内核可能用 GCC 或 clang 编译，C++ 编译器跟着 kbuild 的 C 编译器走"""
    if config["cxx"]:
        return config["cxx"]
    name = os.path.basename(cc)
    if "clang" in name:
        candidate = name.replace("clang", "clang++", 1)
    elif "gcc" in name:
        candidate = name.replace("gcc", "g++", 1)
    elif name in ("cc", "c++"):
        candidate = "c++"
    else:
        candidate = "g++"
    if shutil.which(candidate):
        return candidate
    # 交叉工具链或只有 cc/gcc 别名时，退回到不带版本号的 C++ 编译器
    return "clang++" if "clang" in candidate else "g++"


def probe_c_flags(module_dir, kdir, target):
    out = subprocess.run(
        # -j1 避免外层 make 的 jobserver 被子 make 误用
        ["make", "-C", kdir, "-j1", f"M={module_dir}", "V=1", "-B", target],
        cwd=module_dir, check=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True,
    ).stdout
    for line in out.splitlines():
        # 内核可能用 gcc-12、/usr/bin/gcc 或 ccache gcc，按 token 找编译器
        tokens = line.split(";")[0].split()
        for index, token in enumerate(tokens):
            if is_compiler_token(token):
                return tokens[index:]
    sys.exit("抓不到 gcc 命令行")


# 生成 libc 头时只需要会改变类型布局的参数：-m32/-m64 决定 long/指针宽度，
# -fshort-wchar 决定 wchar_t 宽度，-funsigned-char 决定 char 是否有符号。
# 内核的其它 -mno-sse/-mcmodel 之类预处理阶段用不到，传了反而增加出错面。
_ABI_FLAGS = {
    "-m32", "-m64", "-mx32",
    "-fshort-wchar", "-funsigned-char", "-fsigned-char", "-fshort-enums",
}
_ABI_PREFIXES = ("-mabi=", "-march=", "-mbig-endian", "-mlittle-endian")


def pick_abi_flags(args):
    """从 kbuild 的 C 命令行里挑出影响整数类型宽度的参数"""
    return [arg for arg in args
            if arg in _ABI_FLAGS or arg.startswith(_ABI_PREFIXES)]


def to_cxx_flags(args):
    result = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "-isystem":
            result += [arg, args[index + 1]]
            index += 2
            continue
        if arg in ("-I", "-include", "-o", "-MF", "-MT", "-MQ"):
            index += 2
            continue
        if arg.startswith(("-I", "-include", "-Wp,-MMD", "-MF", "-MT", "-MQ")):
            index += 1
            continue
        # 裸 -Werror 必须丢：内核开 CONFIG_WERROR 时，C++ 特有的警告
        # （-Wmissing-field-initializers 等）会直接变成错误
        if arg == "-Werror" or arg in (
                "-Werror=missing-prototypes", "-Werror=strict-prototypes",
                "-Werror=old-style-definition", "-Werror=pointer-sign",
                "-Werror=override-init", "-Werror=implicit-int",
                "-Werror=implicit-function-declaration",
                "-Werror=incompatible-pointer-types", "-Werror=int-conversion",
                "-Werror=discarded-qualifiers", "-Werror=designated-init"):
            index += 1
            continue
        # 内核的 C 标准（gnu11/gnu17/gnu89…）对 g++ 都非法，统一丢弃；
        # C++ 标准由下面固定追加的 -std=gnu++20 决定
        if arg in ("-c", "-nostdinc") or arg.startswith("-std="):
            index += 1
            continue
        # 这几个是 C/ObjC 专用，g++ 会刷一堆“valid for C but not C++”
        if arg in ("-Wmissing-prototypes", "-Wstrict-prototypes", "-Wold-style-definition",
                   "-Wno-pointer-sign", "-Wno-override-init"):
            index += 1
            continue
        # C++ 的 patchable section 带 SHF_GNU_RETAIN，链接时不会合并
        if arg.startswith("-fpatchable-function-entry"):
            index += 1
            continue
        # -pg/-mfentry 生成的 __mcount_loc 会引用被 COMDAT 丢弃的虚函数
        if arg in ("-pg", "-mfentry", "-mrecord-mcount", "-DCC_USING_FENTRY"):
            index += 1
            continue
        if is_compiler_token(arg):
            index += 1
            continue
        if arg.endswith((".c", ".o")):
            index += 1
            continue
        result.append(arg)
        index += 1
    return result + [
        "-std=gnu++20", "-fno-exceptions", "-fno-rtti",
        "-fno-threadsafe-statics", "-fno-use-cxa-atexit",
        # union 里的匿名 struct 是 GCC/clang 的扩展，clang 需要显式打开
        "-fms-extensions",
    ]


def cxx_include_flags(module_dir, config):
    includes = [
        f"-I{module_dir}",
        f"-I{module_dir / 'generated'}",
        f"-I{INCLUDE_DIR}",
    ]
    for path in config["cxx_includes"]:
        includes.append(f"-I{module_dir / path}")
    return includes


def make_quote(token):
    """路径带空格时包一层引号；$ 要写成 $$，否则 make 会当变量展开"""
    token = token.replace("$", "$$")
    if not re.search(r"\s", token):
        return token
    return '"' + token.replace('"', '\\"') + '"'


def write_cxxflags(module_dir, config, cxx, flags):
    tokens = cxx_include_flags(module_dir, config) + flags + config["cxx_flags"]
    content = "\n".join([
        "# 由 build.py 生成，不要手改。",
        f"CXX ?= {make_quote(cxx)}",
        "LCPP_CXXFLAGS := " + " ".join(make_quote(token) for token in tokens),
        "",
    ])
    path = module_dir / "generated" / "cxxflags.mk"
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    path.write_text(content, encoding="utf-8")
