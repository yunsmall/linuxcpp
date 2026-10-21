#!/usr/bin/env python3

"""linuxcpp 模块构建器。

用户模块目录只需要：
  module.toml   模块/设备/绑定配置
  *.cpp         驱动逻辑（通常一个文件）

构建器生成绑定、C 入口、Kbuild 和 Makefile；后续增量构建直接交给 make。
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:
    sys.exit("需要 Python 3.11+（tomllib）")

from flags import (cxx_compiler, is_compiler_token, probe_c_flags,
                   to_cxx_flags, write_cxxflags)
from mkgen import write_makefile
from paths import INCLUDE_DIR, PY_DIR, SRC_DIR

DEFAULTS = {
    "name": "linuxcpp_module",
    "description": "C++ kernel module built with linuxcpp",
    "license": "GPL",
    "device": "linuxcpp_dev",
    "mode": "0666",
    # file_operations 需要完整定义：misc 注册在 C++ 里构造 fops 表
    "roots": ["file", "file_operations", "kiocb", "iov_iter", "miscdevice", "mutex"],
    "extern": ["misc_register", "misc_deregister", "compat_ptr_ioctl"],
    "thunk": ["copy_to_iter", "copy_from_iter", "copy_from_user", "copy_to_user"],
    "macro": [],
    "headers": [],
    "packed": [],
}


def parse_args():
    parser = argparse.ArgumentParser(description="构建 linuxcpp C++ 内核模块")
    parser.add_argument("module_dir", nargs="?", default=".", help="模块目录")
    parser.add_argument("--kdir", default=f"/lib/modules/{os.uname().release}/build",
                        help="内核 build 目录")
    parser.add_argument("--keep-intermediate", action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("--prepare-only", action="store_true",
                        help="只生成 Makefile、绑定和配置，不调用 make")
    parser.add_argument("-j", "--jobs", type=int, default=None,
                        help="并行任务数，默认不超过 6")
    parser.add_argument("--clean", action="store_true",
                        help="删除 .o/.ko 等构建产物")
    return parser.parse_args()


def run(args, cwd=None):
    print("+", " ".join(args))
    subprocess.run(args, check=True, cwd=cwd)


def load_config(module_dir):
    path = module_dir / "module.toml"
    if not path.exists():
        sys.exit(f"缺少 {path}")
    with open(path, "rb") as handle:
        data = tomllib.load(handle)

    module_cfg = data.get("module", {})
    device_cfg = data.get("device", {})
    bindings_cfg = data.get("bindings", {})

    config = {
        "name": module_cfg.get("name", DEFAULTS["name"]),
        "description": module_cfg.get("description", DEFAULTS["description"]),
        "license": module_cfg.get("license", DEFAULTS["license"]),
        # C 入口只负责 module_init/module_exit，注册设备等逻辑全在 C++ 层；
        # entry 可以换成一个完全自定义的 C 入口
        "entry": module_cfg.get("entry", ""),
        "device": device_cfg.get("name", DEFAULTS["device"]),
        "mode": device_cfg.get("mode", DEFAULTS["mode"]),
        # 核心库 linuxcpp.cpp 总要编译，它依赖这些类型和 misc 注册函数，不能省
        "roots": list(dict.fromkeys(DEFAULTS["roots"] + bindings_cfg.get("roots", []))),
        "extern": list(dict.fromkeys(DEFAULTS["extern"] + bindings_cfg.get("extern", []))),
        "thunk": list(dict.fromkeys(DEFAULTS["thunk"] + bindings_cfg.get("thunk", []))),
        "macro": bindings_cfg.get("macro", DEFAULTS["macro"]),
        "headers": bindings_cfg.get("headers", DEFAULTS["headers"]),
        # 自动修复兜不住时，用户仍可以按名字强制标 packed
        "packed": bindings_cfg.get("packed", DEFAULTS["packed"]),
        "cxx_includes": data.get("build", {}).get("cxx_includes", []),
        "cxx_flags": data.get("build", {}).get("cxx_flags", []),
        # 默认跟随 kbuild 的编译器；填了就用指定值（例如内核 GCC、C++ 用 clang++）
        "cxx": data.get("build", {}).get("cxx", ""),
    }
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", config["name"]):
        sys.exit(f"模块名不合法: {config['name']}")
    return config


def c_string(text):
    return text.replace("\\", "\\\\").replace('"', '\\"')


def write_text_if_changed(path, text):
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    path.write_text(text, encoding="utf-8")


def copy_if_changed(source, target):
    data = source.read_bytes()
    if target.exists() and target.read_bytes() == data:
        return
    shutil.copy2(source, target)


def file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bindings_cache_key(module_dir, config, kdir):
    """绑定只依赖这些输入；设备名/描述变化不应该触发全量 BTF 解析"""
    data = {
        "kdir": str(kdir),
        "roots": config["roots"],
        "extern": config["extern"],
        "thunk": config["thunk"],
        "macro": config["macro"],
        "headers": config["headers"],
        "packed": config["packed"],
        "release": os.uname().release,
    }
    for path in sorted((PY_DIR / "linuxcppgen").glob("*.py")):
        data[f"generator:{path.name}"] = file_digest(path)
    data["generator:gen_bindings.py"] = file_digest(PY_DIR / "gen_bindings.py")
    try:
        stat = Path("/sys/kernel/btf/vmlinux").stat()
        data["btf"] = f"{stat.st_size}:{stat.st_mtime_ns}"
    except OSError:
        pass
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def cxxflags_cache_key(module_dir, config, kdir):
    """kbuild flags 只依赖内核配置、编译器和 module.toml 的 [build]"""
    data = {
        "module_dir": str(module_dir),
        "kdir": str(kdir),
        "cxx": config["cxx"],
        "cxx_flags": config["cxx_flags"],
        "cxx_includes": config["cxx_includes"],
        "flags.py": file_digest(PY_DIR / "flags.py"),
    }
    for name in ("Makefile", "include/config/auto.conf"):
        try:
            stat = (Path(kdir) / name).stat()
            data[name] = f"{stat.st_size}:{stat.st_mtime_ns}"
        except OSError:
            pass
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def bindings_present(module_dir):
    return all(path.exists() for path in (
        module_dir / "generated" / "bindings.h",
        module_dir / "generated" / "bindings.hpp",
        module_dir / "layout_check.c",
        module_dir / "thunks_gen.c",
    ))


def generate_sources(module_dir, config):
    """生成 C 入口；返回入口对象名，供 Kbuild 和 probe 使用"""
    # linuxcpp.c/device.c 会和核心库的 .cpp 抢同一个对象名
    if (module_dir / "linuxcpp.c").exists() or config["entry"] == "linuxcpp.c":
        sys.exit("模块目录不能有 linuxcpp.c：它会和核心库对象重名，请改名")
    if (module_dir / "device.c").exists() or config["entry"] == "device.c":
        sys.exit("模块目录不能有 device.c：它会和核心库对象重名，请改名")
    if config["entry"]:
        # 这些名字由生成器所有，配置成入口会在下次 prepare 时被覆盖
        generated_entries = {"entry_gen", "layout_check", "thunks_gen",
                             "linuxcpp_thunks", "lcpp_ctors", "lcpp_ctors_start",
                             "lcpp_ctors_end", "linuxcpp", "device"}
        if Path(config["entry"]).stem in generated_entries:
            sys.exit(f"entry 不能使用生成文件名: {config['entry']}")
        entry_path = module_dir / config["entry"]
        if not entry_path.exists():
            sys.exit(f"找不到自定义入口文件: {entry_path}")
        # Kbuild 的对象路径按模块根计算，子目录/非 C 文件会生成错误的命令
        if entry_path.suffix != ".c" or entry_path.parent != module_dir:
            sys.exit("自定义 entry 必须是模块根目录下的 .c 文件")
        entry_obj = entry_path.stem + ".o"
    else:
        # 生成的文件名和用户自己的 entry.c 区分开，避免覆盖手写入口
        entry_obj = "entry_gen.o"
        # C 侧永远只有 module_init/module_exit；misc 注册等都在 C++ 的 init/exit 里
        template = (PY_DIR / "raw_top.c.in").read_text(encoding="utf-8")
        replacements = {
            "@@LICENSE@@": c_string(config["license"]),
            "@@DESCRIPTION@@": c_string(config["description"]),
        }
        for key, value in replacements.items():
            template = template.replace(key, value)
        entry_path = module_dir / "entry_gen.c"
        write_text_if_changed(entry_path, template)

    # 设备名/权限从 module.toml 生成，供用户自己的 C++ 初始化代码使用
    try:
        mode = int(config["mode"], 8)
    except ValueError:
        sys.exit(f"device.mode 不是合法的八进制数: {config['mode']}")
    config_hpp = [
        "// 由 build.py 自动生成，不要手改。",
        "#pragma once",
        "",
        f'#define LCPP_MODULE_NAME "{c_string(config["name"])}"',
        f'#define LCPP_DEVICE_NAME "{c_string(config["device"])}"',
        f"#define LCPP_DEVICE_MODE 0{mode:o}",
        "",
    ]
    write_text_if_changed(module_dir / "generated" / "config.hpp",
                          "\n".join(config_hpp))

    copy_if_changed(SRC_DIR / "linuxcpp_thunks.c", module_dir / "linuxcpp_thunks.c")
    for name in ("lcpp_ctors.c", "lcpp_ctors_start.c", "lcpp_ctors_end.c"):
        copy_if_changed(SRC_DIR / name, module_dir / name)

    user_objs = [path.stem + ".o" for path in sorted(module_dir.glob("*.cpp"))
                 if path.stem not in {"linuxcpp", "device"}]
    # 模块自己的 C thunk 也要编译；生成的文件已经单独加入，不能重复
    # entry_gen.c 即使当前用自定义入口也要排除：切换入口后旧文件还留在目录里
    generated_c = {"entry_gen.c", "layout_check.c", "thunks_gen.c",
                   "linuxcpp_thunks.c", "lcpp_ctors.c", "lcpp_ctors_start.c",
                   "lcpp_ctors_end.c", entry_path.name}
    user_c_objs = [path.stem + ".o" for path in sorted(module_dir.glob("*.c"))
                   if path.name not in generated_c
                   and not path.name.endswith(".mod.c")]
    user_stems = {obj[:-2] for obj in user_objs}
    user_c_stems = {obj[:-2] for obj in user_c_objs}
    overlap = user_stems & user_c_stems
    if overlap:
        sys.exit(f"模块目录里有同名 .c 和 .cpp: {', '.join(sorted(overlap))}")
    reserved = {"layout_check", "entry_gen", "linuxcpp_thunks", "thunks_gen",
                "linuxcpp", "device", "lcpp_ctors", "lcpp_ctors_start",
                "lcpp_ctors_end", Path(entry_obj).stem}
    conflict = reserved & (user_stems | user_c_stems)
    if conflict:
        sys.exit(f"模块目录里的源文件和生成对象重名: {', '.join(sorted(conflict))}")
    # 构造/析构数组的边界对象必须排在最前和最后
    objs = (["lcpp_ctors_start.o", "layout_check.o", entry_obj,
             "linuxcpp_thunks.o", "thunks_gen.o", "lcpp_ctors.o",
             "linuxcpp.o", "device.o"] + user_c_objs + user_objs
            + ["lcpp_ctors_end.o"])
    kbuild = [
        f"obj-m := {config['name']}.o",
        f"{config['name']}-y := {' '.join(objs)}",
        f"ccflags-y += -I$(src)/generated -I{INCLUDE_DIR}",
        "",
    ]
    write_text_if_changed(module_dir / "Kbuild", "\n".join(kbuild))
    return entry_obj


def generate_bindings(module_dir, config, kdir):
    cmd = [
        sys.executable, str(PY_DIR / "gen_bindings.py"),
        "--kdir", kdir,
        "--out-dir", str(module_dir / "generated"),
        "--work-dir", str(module_dir),
    ]
    for root in config["roots"]:
        cmd += ["--root", root]
    for func in config["extern"]:
        cmd += ["--extern", func]
    for func in config["thunk"]:
        cmd += ["--thunk", func]
    for macro in config["macro"]:
        cmd += ["--macro", macro]
    for header in config["headers"]:
        cmd += ["--header", header]
    for name in config["packed"]:
        cmd += ["--packed", name]
    run(cmd, cwd=module_dir)


def prepare(module_dir, config, kdir):
    """生成绑定、入口、Kbuild、Makefile 和 flags，不编译"""
    entry_obj = generate_sources(module_dir, config)
    generated = module_dir / "generated"

    # 绑定生成是 prepare 里最重的一步，输入没变就直接复用
    binding_key = bindings_cache_key(module_dir, config, kdir)
    binding_cache = generated / ".bindings.hash"
    if (not bindings_present(module_dir) or not binding_cache.exists()
            or binding_cache.read_text(encoding="utf-8").strip() != binding_key):
        generate_bindings(module_dir, config, kdir)
        binding_cache.write_text(binding_key + "\n", encoding="utf-8")

    # probe_c_flags 会强制 kbuild 编译一次 C 入口，条件没变时也可以复用
    flags_key = cxxflags_cache_key(module_dir, config, kdir)
    flags_cache = generated / ".cxxflags.hash"
    cxxflags_path = generated / "cxxflags.mk"
    if (not cxxflags_path.exists() or not flags_cache.exists()
            or flags_cache.read_text(encoding="utf-8").strip() != flags_key):
        raw_flags = probe_c_flags(module_dir, kdir, entry_obj)
        cxx = cxx_compiler(config, raw_flags[0] if raw_flags else "gcc")
        write_cxxflags(module_dir, config, cxx, to_cxx_flags(raw_flags))
        flags_cache.write_text(flags_key + "\n", encoding="utf-8")

    write_makefile(module_dir, config, kdir)
    (generated / ".prepared").touch()
    # cxxflags 要比 stamp 新，避免 make 每次都尝试重建被 include 的文件
    cxxflags_path.touch()
    return entry_obj


def clean_artifacts(module_dir):
    patterns = ("*.o", "*.ko", "*.mod", "*.mod.c", ".*.cmd", "*.d",
                "modules.order", "Module.symvers", ".module-common.o")
    for pattern in patterns:
        for path in module_dir.glob(pattern):
            path.unlink()
    for name in ("generated/.prepared", "generated/cxxflags.mk",
                 "generated/.bindings.hash", "generated/.cxxflags.hash"):
        path = module_dir / name
        if path.exists():
            path.unlink()


def main():
    args = parse_args()
    module_dir = Path(args.module_dir).resolve()
    if not module_dir.is_dir():
        sys.exit(f"模块目录不存在: {module_dir}")

    if args.clean:
        clean_artifacts(module_dir)
        return

    config = load_config(module_dir)
    # 同名会把核心库的 linuxcpp.o/device.o 顶掉，直接拒绝比静默排除清楚
    for reserved in ("linuxcpp.cpp", "device.cpp"):
        if (module_dir / reserved).exists():
            sys.exit(f"模块目录不能有 {reserved}：它会和核心库对象重名，请改名")
    (module_dir / "generated").mkdir(exist_ok=True)

    jobs = args.jobs if args.jobs is not None else min(6, os.cpu_count() or 1)

    # 第一次构建先生成 Makefile；之后直接交给 make 做依赖检测
    if args.prepare_only or not (module_dir / "Makefile").exists():
        prepare(module_dir, config, args.kdir)
    if args.prepare_only:
        print(f"准备完成，编译命令: make -C {module_dir} -j{jobs}")
        return

    run(["make", "-C", str(module_dir), f"-j{jobs}", "all"])
    print(f"完成: {module_dir / (config['name'] + '.ko')}")


if __name__ == "__main__":
    main()
